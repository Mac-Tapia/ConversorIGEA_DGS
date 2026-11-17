"""La puerta de la web: Host, Origin, token, política de contenido y marcos (086:RF-17, RF-18, RF-19, RF-21).

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
import html
import json
import logging
import os
import re
import secrets
import sys
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

from ..edicion import motivo_ruta_negada
from ..sesion_web import (CABECERA_TOKEN, HOSTS_LOCALES, PARAMETRO_ACCESO, VARIABLE_PUERTO, FiltroSecretos,
                          Sesion, leer_sesion)

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


#: 086:RF-21: las únicas rutas cuyas páginas enseña la propia web en un ``<iframe>``, por su plantilla exacta de
#: Starlette y con la pantalla que las enmarca. Solo ellas se dejan enmarcar, y solo por la web («'self'» y
#: ``SAMEORIGIN``), y siguen aisladas por su ``sandbox``. Todo lo demás, ``DENY`` y ``frame-ancestors 'none'``.
#: Antes la ruta ponía su política sin ``frame-ancestors`` y la puerta le añadía ``DENY``: el marco salía en blanco
#: («Refused to display … X-Frame-Options to 'deny'», revisión en pantalla del 2026-11-14). Una tercera se añade a
#: propósito, aquí y en la spec: una prueba recorre ``app.routes`` y exige que solo estas se dejen enmarcar.
RUTAS_ENMARCABLES: tuple[str, ...] = (
    '/api/workspaces/{wid}/mapa-cargas/pagina',  # «Ubicación de las cargas nuevas» (MapaCargas.tsx)
    '/api/workspaces/{wid}/files/{rel:path}',    # la vista previa del alimentador (Modules.tsx)
    '/api/workspaces/{wid}/plano/pagina',        # «Plano de la red» (PlanoRed.tsx, 111:RF-14)
)


def _patron_de_plantilla(plantilla: str) -> re.Pattern[str]:
    """La plantilla de Starlette como expresión exacta: ``{x}`` es un tramo y ``{x:path}``, el resto de la ruta."""
    partes = []
    for trozo in re.split(r'(\{[^{}]+\})', plantilla):
        if trozo.startswith('{') and trozo.endswith('}'):
            partes.append('.+' if trozo[1:-1].partition(':')[2] == 'path' else '[^/]+')
        else:
            partes.append(re.escape(trozo))
    return re.compile(''.join(partes))


_INCRUSTABLES = tuple(_patron_de_plantilla(p) for p in RUTAS_ENMARCABLES)
#: Lo que FastAPI lee como «falso» en ``download``: con cualquier otro valor la respuesta es una descarga.
_NO_DESCARGA = frozenset({'', '0', 'false', 'f', 'no', 'n', 'off'})
_MARCO_PROPIO = b"frame-ancestors 'self'"
_SIN_MARCO = b"frame-ancestors 'none'"


def es_ruta_enmarcable(ruta: str) -> bool:
    """Si la ruta es una de ``RUTAS_ENMARCABLES``, comparada entera (086:RF-21)."""
    return any(p.fullmatch(ruta) for p in _INCRUSTABLES)


def se_incrusta(metodo: str, ruta: str, consulta: dict[str, str]) -> bool:
    """Si la petición pide una de las páginas que la web enseña en su propio iframe (086:RF-21).

    Es la mitad que se sabe antes de responder; la otra la mira ``_se_deja_enmarcar`` en la respuesta.
    """
    return (metodo in ('GET', 'HEAD') and consulta.get('download', '').strip().lower() in _NO_DESCARGA
            and es_ruta_enmarcable(ruta))


def _directivas(politica: bytes) -> list[bytes]:
    return [d.strip() for d in politica.split(b';') if d.strip()]


def _aislada(politicas: list[bytes]) -> bool:
    """Si alguna de las políticas de la respuesta trae la directiva ``sandbox`` (no basta la palabra en un origen)."""
    return any(d.split()[0].lower() == b'sandbox' for p in politicas for d in _directivas(p))


def _con_marco(politica: bytes, marco: bytes) -> bytes:
    """La política con ``marco`` como su único ``frame-ancestors``: el que trajera la ruta no cuenta, ni para abrir."""
    return b'; '.join([*(d for d in _directivas(politica) if d.split()[0].lower() != b'frame-ancestors'), marco])


def _valor(cabeceras: list, nombre: bytes) -> bytes:
    return next((v for k, v in cabeceras if k.lower() == nombre), b'')


def _se_deja_enmarcar(cabeceras: list) -> bool:
    """La mitad de la respuesta (086:RF-21): una página HTML que se abre en el sitio y va aislada.

    Un error JSON de esas mismas rutas, la misma página como descarga (``Content-Disposition: attachment``) o una página
    sin ``sandbox`` no se dejan enmarcar. Falla cerrado (condición del auditor ca): el aislamiento lo pone la ruta con
    «sandbox» en su política (app.py, mapa_cargas_api.py), y sin él no se enmarca.
    """
    return (_valor(cabeceras, b'content-type').lower().startswith(b'text/html')
            and not _valor(cabeceras, b'content-disposition').strip().lower().startswith(b'attachment')
            and _aislada([v for k, v in cabeceras if k.lower() == b'content-security-policy']))


def cabeceras_de_marco(cabeceras: list, incrustable: bool, politica: bytes) -> list[tuple[bytes, bytes]]:
    """086:RF-21: ``X-Frame-Options`` y ``frame-ancestors`` de TODA respuesta, decididos aquí y no por la ruta.

    Se quita el ``X-Frame-Options`` que traiga la ruta y se pone uno solo; cada política de la respuesta lleva un solo
    ``frame-ancestors``, el de la puerta, y la que no trae política lleva la de la interfaz (``politica``).
    """
    propio = incrustable and _se_deja_enmarcar(cabeceras)
    marco = _MARCO_PROPIO if propio else _SIN_MARCO
    salida, con_politica = [], False
    for nombre, valor in cabeceras:
        clave = nombre.lower()
        if clave == b'x-frame-options':
            continue
        if clave == b'content-security-policy':
            valor, con_politica = _con_marco(valor, marco), True
        salida.append((nombre, valor))
    if not con_politica:
        salida.append((b'content-security-policy', _con_marco(politica, marco)))
    salida.append((b'x-frame-options', b'SAMEORIGIN' if propio else b'DENY'))
    return salida


#: El registro de accesos de uvicorn escribe la URL entera, con el ``acceso=`` del lanzador; el filtro es ya el general.
_SinTokenEnElRegistro = FiltroSecretos


#: 110 (RNF): ninguna dirección de correo ni token del proveedor en el registro de la web. Se deja la primera letra y
#: el dominio (``j…@dominio``), que bastan para reconocer el envío sin publicar la dirección.
_CORREO = re.compile(r'([A-Za-z0-9])[A-Za-z0-9._%+\-]*@([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)')
_PORTADOR = re.compile(r'(Bearer\s+)[^\s,;"\']+', re.IGNORECASE)


def enmascarar_correo(texto: str) -> str:
    """El texto sin direcciones completas ni tokens de portador."""
    return _PORTADOR.sub(r'\1***', _CORREO.sub(lambda m: f'{m.group(1)}…@{m.group(2)}', str(texto)))


#: Un marcador de formato ``%`` de ``logging`` (``%s``, ``%(nombre)s``, ``%5.2f``, ``%%``...): no se enmascara.
_MARCADOR = re.compile(r'%(?:\([^)]*\))?[#0 +\-]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?[diouxXeEfFgGcrsa%]')


def _enmascarar_plantilla(plantilla: str) -> str:
    """La plantilla del mensaje enmascarada solo en su texto, sin comerse ningún marcador ``%``."""
    partes, inicio = [], 0
    for m in _MARCADOR.finditer(plantilla):
        partes += [enmascarar_correo(plantilla[inicio:m.start()]), m.group(0)]
        inicio = m.end()
    return ''.join(partes) + enmascarar_correo(plantilla[inicio:])


class _SinCorreoEnElRegistro(logging.Filter):
    """Enmascara direcciones y tokens en el mensaje ya formateado (110, requisitos no funcionales).

    Se mira el mensaje que se escribiría, no sus piezas: en ``'Bearer %s'`` el token va en un argumento y solo el texto
    completo dice que lo es. Si basta con enmascarar la plantilla y cada argumento, se deja así, y el formateador de
    accesos de uvicorn, que lee los argumentos por posición, sigue funcionando; si no, el registro lleva el mensaje
    enmascarado sin argumentos. Enmascarar la plantilla a ciegas convertía ``'Bearer %s'`` en ``'Bearer ***'``, que
    sobra un argumento, y el registro fallaba al formatearlo («not all arguments converted»).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            completo = record.getMessage()
        except (TypeError, ValueError, KeyError):
            return True  # un registro mal formado lo informa logging; este filtro no lo rompe más
        enmascarado = enmascarar_correo(completo)
        if enmascarado == completo:
            return True
        plantilla = _enmascarar_plantilla(record.msg) if isinstance(record.msg, str) else record.msg
        argumentos = record.args
        if isinstance(argumentos, tuple):
            argumentos = tuple(enmascarar_correo(a) if isinstance(a, str) else a for a in argumentos)
        try:
            por_piezas = str(plantilla) % argumentos if argumentos else str(plantilla)
        except (TypeError, ValueError, KeyError):
            por_piezas = None
        if por_piezas == enmascarado:
            record.msg, record.args = plantilla, argumentos
        else:
            record.msg, record.args = enmascarado, None
        return True


def _instalar_filtro_registro() -> None:
    """086:RF-19: el filtro en el raíz, en ``uvicorn.access`` y en cada manejador que ya exista.

    El filtro de un registro solo ve lo que se escribe en ese mismo registro, no lo que sube de sus hijos: lo de
    ``convertersmartgrid.asistente`` pasa por los manejadores, y ahí va también. El fichero rotativo, que puede
    crearse después, lo lleva desde que nace (``registro_rotativo.configurar_registro``).
    """
    raiz = logging.getLogger()
    destinos: list[logging.Filterer] = [raiz, logging.getLogger('uvicorn.access'), *raiz.handlers]
    for registro in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(registro, logging.Logger):
            destinos.extend(registro.handlers)
    if logging.lastResort is not None:
        destinos.append(logging.lastResort)
    for destino in destinos:
        if not any(isinstance(f, FiltroSecretos) for f in destino.filters):
            destino.addFilter(FiltroSecretos())
    # 110 (RNF): además, sin direcciones de correo ni tokens del proveedor en el registro de accesos.
    acceso = logging.getLogger('uvicorn.access')
    if not any(isinstance(f, _SinCorreoEnElRegistro) for f in acceso.filters):
        acceso.addFilter(_SinCorreoEnElRegistro())


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
        cabeceras = {k.decode('latin-1').lower(): v.decode('latin-1') for k, v in scope.get('headers', ())}
        # 086:RF-19: quien llega con un enlace de un arranque anterior es una persona, no un programa,
        # y veía un JSON crudo. Solo la navegación recibe la página: la API sigue dando su JSON.
        pagina = estado == 401 and scope.get('method') == 'GET' and 'text/html' in cabeceras.get('accept', '')
        if pagina:
            cuerpo = (f'<!doctype html><html lang="es"><meta charset="utf-8"><title>ConverterSmartGrid</title>'
                      f'<body style="font:16px system-ui;margin:3rem"><h1>ConverterSmartGrid</h1>'
                      f'<p>{html.escape(detalle)}</p></body></html>').encode('utf-8')
        else:
            cuerpo = json.dumps({'detail': detalle}, ensure_ascii=False).encode('utf-8')
        await send({'type': 'http.response.start', 'status': estado,
                    'headers': [(b'content-type', b'text/html; charset=utf-8' if pagina else b'application/json'),
                                (b'content-length', str(len(cuerpo)).encode()),
                                (b'x-content-type-options', b'nosniff'), (b'x-frame-options', b'DENY'),
                                (b'content-security-policy', _SIN_MARCO)]})
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

        incrustable = not es_ws and se_incrusta(metodo, ruta, consulta)
        politica = _politica_interfaz(host).encode('latin-1')

        async def enviar(mensaje) -> None:
            if mensaje['type'] == 'http.response.start':
                propias = cabeceras_de_marco(list(mensaje.get('headers', ())), incrustable, politica)
                existentes = {k.lower() for k, _v in propias}
                nuevas = list(extra)
                for nombre, valor in ((b'x-content-type-options', b'nosniff'), (b'referrer-policy', b'no-referrer')):
                    if nombre not in existentes:
                        nuevas.append((nombre, valor))
                mensaje = {**mensaje, 'headers': [*propias, *nuevas]}
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
                                (b'x-frame-options', b'DENY'), (b'content-security-policy', _SIN_MARCO),
                                (b'content-length', b'0')]})
        await send({'type': 'http.response.body', 'body': b''})


class AlcanceEdicion:
    """086:RF-16: una beta que el operador apagó se niega aquí, y no ruta por ruta: la lista está en ``edicion.py``,
    y ocultar el botón dejaba la ruta abierta a cualquier petición. Sin betas apagadas no se niega nada."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        motivo = motivo_ruta_negada(scope.get('path', '')) if scope['type'] == 'http' else None
        if motivo is None:
            await self.app(scope, receive, send)
            return
        cuerpo = json.dumps({'detail': motivo}, ensure_ascii=False).encode('utf-8')
        await send({'type': 'http.response.start', 'status': 403,
                    'headers': [(b'content-type', b'application/json'), (b'content-length', str(len(cuerpo)).encode())]})
        await send({'type': 'http.response.body', 'body': cuerpo})


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
