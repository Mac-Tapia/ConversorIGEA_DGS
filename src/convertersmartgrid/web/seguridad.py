"""La puerta de la web: Host, Origin, token y política de contenido (086:RF-17, RF-18, RF-19, RF-21).

La revisión de la spec 086 reprodujo que una página cualquiera del navegador podía usar la API en
127.0.0.1: por DNS rebinding (Host ajeno), por CSRF (Origin ajeno) y abriendo el WebSocket entre
orígenes. Va en un solo middleware ASGI, y no ruta por ruta, para que una ruta nueva nazca cerrada.

En el navegador el token va en una cookie ``HttpOnly`` y ``SameSite=Strict`` que se entrega al abrir
la dirección del lanzador. Las descargas son ``<a href>`` y ``window.location``, y el WebSocket del
navegador no admite cabeceras: con un token en JavaScript habría que ponerlo en cada URL, y de ahí al
historial. Los programas locales lo mandan en cabecera (``sesion_web.cabeceras_locales``).
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets
import sys
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

from ..sesion_web import (CABECERA_TOKEN, HOSTS_LOCALES, PARAMETRO_ACCESO, VARIABLE_PUERTO, Sesion,
                          leer_sesion)

VARIABLE_HOSTS = 'CSG_WEB_HOSTS'
#: Lo que dura el token anterior tras arrancar. Basta para que una pestaña abierta se reconecte
#: (lo intenta cada 1,5 s, ``useWorkspace.ts``) y evite que el lanzador abra otra (001:RF-35).
RELEVO_S = 120.0
METODOS_SEGUROS = frozenset({'GET', 'HEAD', 'OPTIONS'})
_FORMA_HOST = re.compile(r'(?:\[(::1)\]|([A-Za-z0-9.-]+))(?::\d{1,5})?')
SIN_SESION = ('Esta pestaña no tiene sesión con el Conversor. Ábralo con el acceso directo '
              '«ConverterSmartGrid»; cada arranque usa una sesión nueva.')


def nombre_cookie(puerto: int) -> str:
    # Las cookies no distinguen puertos: dos webs en la misma máquina se pisarían la sesión.
    return f'csg_sesion_{puerto}'


def _politica_interfaz(host: str) -> str:
    """Solo lo propio. ``ws://`` aparte porque ``'self'`` no lo cubre en todos los navegadores."""
    return (f"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' ws://{host}; "
            "img-src 'self' data: blob:; font-src 'self' data:; object-src 'none'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


class _SinTokenEnElRegistro(logging.Filter):
    """El registro de accesos de uvicorn escribe la URL entera, con el ``acceso=`` del lanzador."""

    _ACCESO = re.compile(rf'({PARAMETRO_ACCESO}=)[^&\s"]+')

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._ACCESO.sub(r'\1***', a) if isinstance(a, str) else a for a in record.args)
        return True


def _instalar_filtro_registro() -> None:
    registro = logging.getLogger('uvicorn.access')
    if not any(isinstance(f, _SinTokenEnElRegistro) for f in registro.filters):
        registro.addFilter(_SinTokenEnElRegistro())


def _nombre_de_host(host: str) -> str:
    """El nombre de una cabecera Host, sin puerto; vacío si no tiene forma de host y puerto.

    Es estricto porque el valor acaba en la política de contenido, y un ``;`` la reescribiría.
    """
    m = _FORMA_HOST.fullmatch(host)
    return (m.group(1) or m.group(2)).lower() if m else ''


def _cabeceras(scope) -> dict[str, str]:
    return {k.decode('latin-1').lower(): v.decode('latin-1') for k, v in scope.get('headers', ())}


def _puerto_de(host: str, scope) -> int:
    try:
        return urlsplit(f'//{host}').port or (scope.get('server') or (None, 80))[1] or 80
    except ValueError:
        return 80


def _es_publica(metodo: str, ruta: str) -> bool:
    """La página y sus ficheros: sin token, para que pueda decir que falta la sesión. Nada más."""
    return metodo in ('GET', 'HEAD') and ruta != '/openapi.json' and ruta != '/api' and not ruta.startswith('/api/')


class SeguridadWeb:
    """Middleware ASGI, para que cubra también el WebSocket: el de Starlette solo ve HTTP."""

    def __init__(self, app, *, sesion: Sesion, origenes_extra: tuple[str, ...] = (),
                 hosts: frozenset[str] = HOSTS_LOCALES) -> None:
        self.app = app
        self.sesion = sesion
        self.origenes_extra = frozenset(origenes_extra)
        self.hosts = hosts
        self.inicio = time.monotonic()

    def _token_valido(self, candidato: str | None) -> bool:
        return bool(candidato) and hmac.compare_digest(candidato.encode('utf-8'), self.sesion.token.encode('utf-8'))

    def _relevo_valido(self, candidato: str | None) -> bool:
        anterior = self.sesion.anterior
        return (bool(candidato) and bool(anterior) and time.monotonic() - self.inicio <= RELEVO_S
                and hmac.compare_digest(candidato.encode('utf-8'), anterior.encode('utf-8')))

    def _cookie(self, puerto: int) -> tuple[bytes, bytes]:
        valor = f'{nombre_cookie(puerto)}={self.sesion.token}; Path=/; HttpOnly; SameSite=Strict'
        return b'set-cookie', valor.encode('latin-1')

    def _credencial(self, cabeceras: dict[str, str], puerto: int) -> str | None:
        """Lo que trae la petición: cabecera propia o ``Bearer`` de un programa; cookie, del navegador."""
        directa = cabeceras.get(CABECERA_TOKEN.lower())
        if directa:
            return directa
        autorizacion = cabeceras.get('authorization', '')
        if autorizacion.lower().startswith('bearer '):
            return autorizacion[7:].strip()
        # A mano: ``SimpleCookie`` deja de leer en la primera cookie rara de otro programa de 127.0.0.1.
        for trozo in cabeceras.get('cookie', '').split(';'):
            nombre, _igual, valor = trozo.strip().partition('=')
            if nombre == nombre_cookie(puerto):
                return valor
        return None

    def _origen_permitido(self, origen: str, host: str, scope) -> bool:
        esquema = {'ws': 'http', 'wss': 'https'}.get(scope.get('scheme', 'http'), scope.get('scheme', 'http'))
        return origen == f'{esquema}://{host}' or origen in self.origenes_extra

    async def _rechazar(self, scope, receive, send, estado: int, detalle: str) -> None:
        if scope['type'] == 'websocket':
            await receive()           # websocket.connect: se cierra sin aceptar, y el navegador ve el fallo
            await send({'type': 'websocket.close', 'code': 4000 + estado, 'reason': detalle[:100]})
            return
        cuerpo = json.dumps({'detail': detalle}, ensure_ascii=False).encode('utf-8')
        await send({'type': 'http.response.start', 'status': estado,
                    'headers': [(b'content-type', b'application/json'),
                                (b'content-length', str(len(cuerpo)).encode()),
                                (b'x-content-type-options', b'nosniff')]})
        await send({'type': 'http.response.body', 'body': cuerpo})

    async def __call__(self, scope, receive, send) -> None:
        if scope['type'] not in ('http', 'websocket'):
            await self.app(scope, receive, send)
            return
        cabeceras = _cabeceras(scope)
        cliente = (scope.get('client') or ('',))[0]
        # 086:RF-20: aunque alguien lo arranque con ``uvicorn --host 0.0.0.0``, sin pasar por el lanzador.
        if cliente not in HOSTS_LOCALES:
            await self._rechazar(scope, receive, send, 403,
                                 'Esta web solo atiende a esta máquina: no tiene usuarios ni TLS.')
            return
        host = cabeceras.get('host', '')
        if _nombre_de_host(host) not in self.hosts:                                     # 086:RF-17
            await self._rechazar(scope, receive, send, 403, f'Host no permitido: {host[:80]!r}.')
            return
        metodo = scope.get('method', 'GET')
        origen = cabeceras.get('origin')
        es_ws = scope['type'] == 'websocket'
        if origen is None:                                                              # 086:RF-18
            if es_ws or metodo not in METODOS_SEGUROS:
                await self._rechazar(scope, receive, send, 403, 'Falta el Origin de la petición.')
                return
        elif not self._origen_permitido(origen, host, scope):
            await self._rechazar(scope, receive, send, 403, f'Origin no permitido: {origen[:80]!r}.')
            return
        ruta = scope.get('path', '')
        puerto = _puerto_de(host, scope)
        extra: list[tuple[bytes, bytes]] = []
        consulta = dict(parse_qsl((scope.get('query_string') or b'').decode('latin-1')))
        if not es_ws and metodo == 'GET' and PARAMETRO_ACCESO in consulta and _es_publica(metodo, ruta):
            await self._entrar(scope, receive, send, consulta, ruta, puerto)
            return
        if metodo == 'OPTIONS' and origen and 'access-control-request-method' in cabeceras:
            pass      # Consulta previa de CORS, solo de un origen ya admitido: nunca lleva credenciales.
        elif es_ws or not _es_publica(metodo, ruta):                                    # 086:RF-19
            credencial = self._credencial(cabeceras, puerto)
            if not self._token_valido(credencial):
                if not self._relevo_valido(credencial):
                    await self._rechazar(scope, receive, send, 401, SIN_SESION)
                    return
                # Sin esto, la pestaña que se reconecta perdería la sesión en el siguiente arranque.
                extra.append(self._cookie(puerto))

        politica = _politica_interfaz(host).encode('latin-1')

        async def enviar(mensaje) -> None:
            if mensaje['type'] == 'http.response.start':
                existentes = {k.lower() for k, _v in mensaje.get('headers', ())}
                nuevas = list(extra)
                for nombre, valor in ((b'content-security-policy', politica), (b'x-content-type-options', b'nosniff'),
                                      (b'referrer-policy', b'no-referrer'), (b'x-frame-options', b'DENY')):
                    if nombre not in existentes:
                        nuevas.append((nombre, valor))
                mensaje = {**mensaje, 'headers': [*mensaje.get('headers', ()), *nuevas]}
            elif mensaje['type'] == 'websocket.accept' and extra:
                mensaje = {**mensaje, 'headers': [*(mensaje.get('headers') or ()), *extra]}
            await send(mensaje)

        await self.app(scope, receive, enviar)

    async def _entrar(self, scope, receive, send, consulta: dict, ruta: str, puerto: int) -> None:
        """Cambia el ``?acceso=`` del lanzador por la cookie, y lo quita de la barra de direcciones."""
        if not self._token_valido(consulta.get(PARAMETRO_ACCESO)):
            await self._rechazar(scope, receive, send, 401, SIN_SESION)
            return
        resto = urlencode({k: v for k, v in consulta.items() if k != PARAMETRO_ACCESO})
        destino = ruta + (f'?{resto}' if resto else '')
        await send({'type': 'http.response.start', 'status': 303,
                    'headers': [(b'location', destino.encode('latin-1')), self._cookie(puerto),
                                (b'cache-control', b'no-store'), (b'referrer-policy', b'no-referrer'),
                                (b'content-length', b'0')]})
        await send({'type': 'http.response.body', 'body': b''})


def instalar_seguridad(app, origenes_desarrollo: tuple[str, ...]) -> None:
    """Pone la puerta en ``app``; debe añadirse el último, para que quede por fuera de CORS.

    Sin el puerto que pone el lanzador (``uvicorn`` a mano) se sortea un token que nadie conoce: la
    API queda cerrada y la página dice qué hacer, en vez de abierta por no haber pasado por él.
    """
    sesion = None
    puerto = os.environ.get(VARIABLE_PUERTO, '').strip()
    if puerto.isdigit():
        sesion = leer_sesion(int(puerto))
    if sesion is None:
        print('AVISO: sin sesión del lanzador, la API queda cerrada. Arranque con «convertersmartgrid-web».',
              file=sys.stderr)
        sesion = Sesion(secrets.token_urlsafe(32))
    extra = {h.strip().lower() for h in os.environ.get(VARIABLE_HOSTS, '').split(',') if h.strip()}
    _instalar_filtro_registro()
    app.add_middleware(SeguridadWeb, sesion=sesion, origenes_extra=origenes_desarrollo,
                       hosts=HOSTS_LOCALES | frozenset(extra))
