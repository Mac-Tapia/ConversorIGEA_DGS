"""Cada salida a la red, declarada y con su interruptor (086:RF-22).

La revisión de la spec 086 encontró que el programa salía a internet desde sitios sueltos
(búsquedas del asistente, OSRM, las teselas del mapa, Codex, Hugging Face, el portal de
Osinergmin) sin un lugar donde verlos ni apagarlos. Un cliente que instala esto en la red de
una distribuidora tiene que saber qué sale, y que por defecto no sale nada.

En desarrollo siguen encendidas, como hasta ahora. En la edición de producto están apagadas y
cada una se enciende con su variable. La variable manda en las dos ediciones; sin ella, lo que el
operador guardó en este equipo desde la web (086:RF-66, hoy solo el fondo de mapa), y si no, la edición.
``tests/test_seguridad_web.py`` recorre el código: un módulo nuevo que abra la red sin estar
aquí la hace fallar.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, MutableMapping
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from .edicion import es_edicion_producto
from .util import importar_opcional, publicar_duradero

_ENCENDIDA = ('1', 'si', 'sí', 'true', 'on')
_APAGADA = ('0', 'no', 'false', 'off')


@dataclass(frozen=True)
class Salida:
    variable: str
    destino: str
    para_que: str
    #: Ficheros, relativos a la raíz del repositorio, que abren esta salida.
    modulos: tuple[str, ...]


SALIDAS: dict[str, Salida] = {
    'internet': Salida('CSG_SALIDA_INTERNET', 'GitHub, PyPI y arXiv',
                       'las búsquedas técnicas del asistente',
                       ('src/convertersmartgrid/asistente/internet.py',)),
    'vias': Salida('CSG_SALIDA_VIAS', 'el enrutador OSRM del perfil de empresa',
                   'trazar una línea nueva por la vía pública',
                   ('src/convertersmartgrid/vias.py',)),
    # 017:RF-111: también la imagen de ubicación del informe, que pide las teselas desde el servidor.
    'teselas': Salida('CSG_SALIDA_TESELAS', 'OpenStreetMap y Esri World Imagery',
                      'el fondo de calles y satélite de la vista previa y del mapa de las cargas nuevas, que pide el '
                      'navegador, y de la imagen de ubicación del informe',
                      ('src/convertersmartgrid/preview.py', 'src/convertersmartgrid/mapa_cargas.py')),
    'codex': Salida('CSG_SALIDA_CODEX', 'el servicio de Codex, por su CLI',
                    'el maestro de destilación del asistente',
                    ('src/convertersmartgrid/asistente/destilacion.py',)),
    'hugging_face': Salida('CSG_SALIDA_HUGGING_FACE', 'Hugging Face',
                           'descargar los modelos del catálogo',
                           ('tools/preparar_modelos_ia.py',)),
    'vnr_oficial': Salida('CSG_SALIDA_VNR_OFICIAL', 'el portal de Osinergmin',
                          'buscar y descargar los paquetes VNR-GIS',
                          ('src/convertersmartgrid/adaptadores/entrada/vnr/discovery/official.py', 'src/convertersmartgrid/adaptadores/entrada/vnr/discovery/download.py')),
    'arcgis': Salida('CSG_SALIDA_ARCGIS', 'el servidor ArcGIS que indique el usuario',
                     'leer una capa de un servicio ArcGIS',
                     ('src/convertersmartgrid/adaptadores/entrada/vnr/connectors/arcgis.py',)),
    # 110:RF-2: enviar un informe con la cuenta del propio operador, solo con el permiso de enviar.
    'correo_google': Salida('CSG_SALIDA_CORREO_GOOGLE', 'la API de Gmail (gmail.googleapis.com)',
                            'enviar un informe por correo con la cuenta de Google del operador',
                            ('src/convertersmartgrid/correo/proveedores.py',)),
    'correo_microsoft': Salida('CSG_SALIDA_CORREO_MICROSOFT', 'Microsoft Graph (graph.microsoft.com)',
                               'enviar un informe por correo con la cuenta de Microsoft del operador',
                               ('src/convertersmartgrid/correo/proveedores.py',)),
}


class SalidaApagada(RuntimeError):
    """Se pidió una salida a la red que está apagada."""


#: 086:RF-69: las que el operador puede cambiar desde la web. El resto, solo con su variable al arrancar.
CAMBIABLES_DESDE_LA_WEB = frozenset({'teselas'})
#: Otra ruta para lo guardado en el equipo; la usan las pruebas, para no leer el de la máquina.
VARIABLE_RUTA_GUARDADAS = 'CSG_SALIDAS_RUTA'

Origen = Literal['variable', 'equipo', 'edicion']


def ruta_guardadas(environ: Mapping[str, str] | None = None) -> Path:
    """086:RF-67: junto a ``config/powerfactory.json`` (103:RF-3), en la carpeta local que una actualización no borra."""
    env = os.environ if environ is None else environ
    otra = str(env.get(VARIABLE_RUTA_GUARDADAS) or '').strip()
    if otra:
        return Path(otra)
    from .runtime_paths import raiz_local
    return raiz_local(environ=env) / 'config' / 'salidas.json'


def salidas_guardadas(environ: Mapping[str, str] | None = None) -> dict[str, bool]:
    """Lo que el operador dejó en este equipo; un fichero roto o ajeno cuenta como nada guardado."""
    try:
        datos = json.loads(ruta_guardadas(environ).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return {k: v for k, v in datos.items() if k in CAMBIABLES_DESDE_LA_WEB and isinstance(v, bool)}


def guardar_salida(nombre: str, encendida: bool, environ: Mapping[str, str] | None = None) -> None:
    """086:RF-67: recuerda en el equipo la elección del operador; solo las que se cambian desde la web."""
    if nombre not in CAMBIABLES_DESDE_LA_WEB:
        raise ValueError(f'La salida {nombre!r} no se cambia desde la web.')
    ruta = ruta_guardadas(environ)
    datos = salidas_guardadas(environ)
    datos[nombre] = bool(encendida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    publicar_duradero(ruta, json.dumps(datos, ensure_ascii=False, sort_keys=True) + '\n')   # 001:RF-5


def estado_salida(nombre: str, environ: Mapping[str, str] | None = None) -> tuple[bool, Origen]:
    """086:RF-66: si está encendida y quién lo decide: la variable, lo guardado en el equipo o la edición."""
    env = os.environ if environ is None else environ
    valor = env.get(SALIDAS[nombre].variable, '').strip().lower()
    if valor in _ENCENDIDA:
        return True, 'variable'
    if valor in _APAGADA:
        return False, 'variable'
    guardada = salidas_guardadas(env).get(nombre)
    if guardada is not None:
        return guardada, 'equipo'
    return not es_edicion_producto(), 'edicion'


def salida_permitida(nombre: str, environ: Mapping[str, str] | None = None) -> bool:
    """Si esta salida puede abrirse: su variable manda; sin ella, lo guardado en el equipo; si no, la edición."""
    return estado_salida(nombre, environ)[0]


def estado_salidas(environ: Mapping[str, str] | None = None) -> list[dict[str, object]]:
    """086:RF-69: cada salida con su estado, su origen y su destino, para la web."""
    filas = []
    for nombre, s in SALIDAS.items():
        encendida, origen = estado_salida(nombre, environ)
        filas.append({'nombre': nombre, 'encendida': encendida, 'origen': origen, 'variable': s.variable,
                      'destino': s.destino, 'para_que': s.para_que,
                      'cambiable': nombre in CAMBIABLES_DESDE_LA_WEB and origen != 'variable'})
    return filas


#: «a el» y «de el» con el artículo en minúscula; «de El Carmen», nombre propio, no se contrae (RAE).
_SIN_CONTRAER = re.compile(r'\b([Aa]|[Dd]e) el\b')


def contraer(texto: str) -> str:
    """«a el» pasa a «al» y «de el» a «del» (086:RF-61).

    Los destinos se escriben con su artículo («el portal de Osinergmin») y se unen a «a» o «de» al armar el texto: la web
    del rc5 decía «La salida a el portal de Osinergmin está apagada».
    """
    return _SIN_CONTRAER.sub(lambda m: m.group(1)[0] + ('l' if m.group(1) in 'Aa' else 'el'), texto)


def motivo_apagada(nombre: str) -> str:
    """Por qué no sale, y cómo se enciende: lo lee el operador, en el aviso o en el registro."""
    s = SALIDAS[nombre]
    # 086:RF-67: la que se cambia desde la web dice también dónde, sin tener que rearrancar.
    web = ' o enciéndala en la web, en «Opciones de conversión»' if nombre in CAMBIABLES_DESDE_LA_WEB else ''
    return contraer(f'La salida a {s.destino} está apagada ({s.para_que}). '
                    f'Para activarla, ponga {s.variable}=1 al arrancar{web}.')


def exigir_salida(nombre: str) -> None:
    """Corta aquí si la salida está apagada, antes de abrir ninguna conexión."""
    if not salida_permitida(nombre):
        raise SalidaApagada(motivo_apagada(nombre))


class DestinoNoPermitido(ValueError):
    """La dirección de una salida no es un servidor público por http o https (086:RF-22)."""


_ESQUEMAS = ('https', 'http')
_PUERTO_DEL_ESQUEMA = {'https': 443, 'http': 80}


def _motivo_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, permitir_intranet: bool) -> str | None:
    """Qué tiene de vedada la IP; None si es pública. La de esta máquina, los metadatos de la nube y lo reservado,
    siempre; la red privada, solo con el permiso de intranet."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped                                   # ::ffff:127.0.0.1 es 127.0.0.1
    if ip.is_unspecified or ip.is_loopback:
        return 'de esta misma máquina'
    if ip.is_link_local:
        return 'de enlace local, donde están los metadatos de la nube'
    if ip.is_multicast:
        return 'de multidifusión'
    if ip.is_private:
        return None if permitir_intranet else 'de una red privada'
    if ip.is_reserved or not ip.is_global:
        return 'reservada, no pública'
    return None


def validar_destino(url: str, *, resolver: bool = True, permitir_intranet: bool = False) -> None:
    """Que ``url`` vaya a un servidor público por http o https; si no, ``DestinoNoPermitido`` con el motivo.

    La URL de ArcGIS la escribe el usuario y la de OSRM viene del perfil, y llegaban tal cual a ``requests`` y a
    ``urlopen``: ``file://``, ``http://127.0.0.1`` (la API de la propia web) o ``http://169.254.169.254`` (las
    credenciales de una máquina en la nube) se consultaban (auditoría b4, H8). Se resuelve el nombre y se mira cada
    IP que devuelve, no el texto: un nombre público que el DNS apunta a 10.0.0.5 queda fuera igual.

    ``resolver=False`` solo mira la forma y las IP escritas: con la salida apagada no se consulta ni el DNS, que ya
    es salir a la red. ``permitir_intranet`` abre la red privada (10/8, 172.16/12, 192.168/16, fc00::/7) para el
    servidor ArcGIS de una distribuidora en su propia red; nadie lo enciende todavía.
    """
    _resolver(url, resolver=resolver, permitir_intranet=permitir_intranet)


@dataclass(frozen=True)
class DestinoFijado:
    """Un destino ya resuelto y validado: la conexión va a ``ip`` y TLS y ``Host`` siguen con ``host`` (086:RF-22)."""

    url: str
    esquema: str
    host: str
    puerto: int
    ip: str


def resolver_destino(url: str, *, permitir_intranet: bool = False) -> DestinoFijado:
    """Resuelve el nombre de ``url``, valida TODAS sus IP como ``validar_destino`` y devuelve la primera para fijarla."""
    destino = _resolver(url, resolver=True, permitir_intranet=permitir_intranet)
    assert destino is not None                                  # con resolver=True siempre hay IP
    return destino


def _resolver(url: str, *, resolver: bool, permitir_intranet: bool) -> DestinoFijado | None:
    partes = urlsplit((url or '').strip())
    esquema = partes.scheme.lower()
    if esquema not in _ESQUEMAS:
        raise DestinoNoPermitido(f'Solo se consultan direcciones http o https, no «{esquema or "sin esquema"}»: {url}')
    try:
        host, puerto = partes.hostname, partes.port or _PUERTO_DEL_ESQUEMA[esquema]
    except ValueError as exc:
        raise DestinoNoPermitido(f'La dirección {url} no se entiende: {exc}') from None
    if not host:
        raise DestinoNoPermitido(f'La dirección {url} no dice a qué servidor va.')
    try:
        ips = [ipaddress.ip_address(host)]
    except ValueError:
        if not resolver:
            return None
        try:
            info = socket.getaddrinfo(host, puerto, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError) as exc:
            raise DestinoNoPermitido(f'El servidor {host} no se resuelve: {exc}') from None
        ips = [ipaddress.ip_address(str(fila[4][0]).split('%', 1)[0]) for fila in info]
    if not ips:
        raise DestinoNoPermitido(f'El servidor {host} no se resuelve: el DNS no dio ninguna dirección.')
    for ip in ips:
        motivo = _motivo_ip(ip, permitir_intranet)
        if motivo is not None:
            quien = host if str(ip) == host else f'{host} va a {ip}'
            raise DestinoNoPermitido(f'{quien}, una dirección {motivo}: no se consulta.')
    return DestinoFijado(url, esquema, host, puerto, str(ips[0]))


class SinClienteHttp(OSError):
    """El intérprete no tiene ``requests`` (el 3.9 de DIgSILENT 2021 solo lleva el paquete y numpy, 103:RF-2).

    Es ``OSError`` para que quien ya trata «no respondió» (OSRM va en recta, 016:RF-85) lo trate igual.
    """


def _requests():
    return importar_opcional('requests', SinClienteHttp(
        'Este Python no tiene «requests», con el que se consulta un servidor externo (ver requirements.txt).'))


@lru_cache(maxsize=1)
def _clase_adaptador_fijado() -> type:
    """``HTTPAdapter`` de requests cuyo pool conecta a la IP ya validada (086:RF-22, rebinding).

    La clase se crea al primer uso porque requests es opcional en el intérprete de DIgSILENT (``SinClienteHttp``),
    no para esconder un ciclo: este módulo no importa nada del programa salvo ``edicion`` y ``util``.
    """
    adapters = importar_opcional('requests.adapters', SinClienteHttp('Este Python no tiene «requests».'))

    class AdaptadorFijado(adapters.HTTPAdapter):
        """La URL que recibe ya lleva la IP; ``server_hostname`` (SNI) y ``assert_hostname`` mantienen el nombre
        original, así que TLS valida el certificado del servidor que se pidió y no el de la IP. Sin reintentos: un
        reintento volvería a esta misma IP, y reintentar lo decide quien llama."""

        def __init__(self, destino: DestinoFijado) -> None:
            self.destino = destino
            super().__init__(max_retries=0)

        def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):  # noqa: ANN001 - de requests
            if self.destino.esquema == 'https':
                pool_kwargs['server_hostname'] = self.destino.host
                pool_kwargs['assert_hostname'] = self.destino.host
            super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

    return AdaptadorFijado


def pedir_a_destino_fijado(url: str, *, timeout: float, params: dict | None = None,
                           cabeceras: Mapping[str, str] | None = None,
                           permitir_intranet: bool = False,
                           devolver_redireccion: bool = False):  # -> requests.Response
    """GET a ``url`` conectando a la IP que se validó, sin seguir redirecciones (086:RF-22). La usan ArcGIS y OSRM.

    Antes se validaba el nombre y luego ``requests``/``urlopen`` lo volvían a resolver al conectar: un DNS que
    respondiera una IP pública a la validación y 127.0.0.1 a la conexión llevaba la consulta a esta máquina
    (DNS rebinding, auditoría b4). Ahora se resuelve una vez, se validan todas las IP y la conexión va a la
    primera; ``Host`` lleva el nombre original. Un 3xx es ``DestinoNoPermitido``: seguirlo saltaría la validación.
    Con ``devolver_redireccion`` el 3xx se devuelve sin seguirlo, y decide :func:`get_sin_redireccion_ajena` (ArcGIS:
    solo el mismo servidor; el salto siguiente vuelve a pasar por aquí y se valida).
    """
    destino = resolver_destino(url, permitir_intranet=permitir_intranet)
    requests = _requests()
    partes = urlsplit(url.strip())
    ip = f'[{destino.ip}]' if ':' in destino.ip else destino.ip
    puerto = f':{partes.port}' if partes.port else ''
    por_ip = urlunsplit((partes.scheme, ip + puerto, partes.path, partes.query, partes.fragment))
    host = f'[{destino.host}]' if ':' in destino.host else destino.host
    with requests.Session() as sesion:
        sesion.trust_env = False                             # sin proxies ni .netrc del entorno, como el asistente
        sesion.mount(f'{destino.esquema}://', _clase_adaptador_fijado()(destino))
        respuesta = sesion.get(por_ip, params=params, timeout=timeout, allow_redirects=False,
                               headers={**(cabeceras or {}), 'Host': host + puerto})
    if 300 <= respuesta.status_code < 400 and not devolver_redireccion:
        raise DestinoNoPermitido(f'{url} redirige ({respuesta.status_code}) a '
                                 f'{respuesta.headers.get("Location", "otro sitio")}: no se siguen redirecciones; '
                                 'ponga la dirección final del servicio.')
    return respuesta


def preparar_entorno_sin_red(environ: MutableMapping[str, str] | None = None) -> None:
    """Sin salida a Hugging Face, sus librerías lo saben desde que arranca el proceso.

    ``huggingface_hub`` lee ``HF_HUB_OFFLINE`` al importarse: el que pone ``reranker.py`` al cargar
    el modelo llega tarde si otro lo importó antes, y deja el resto del proceso como le toque.
    Con esto se decide una vez, antes de importar nada, y lo heredan los procesos hijos.
    """
    env = os.environ if environ is None else environ
    if not salida_permitida('hugging_face', env):
        # 086:RF-22: una variable heredada con valor 0 no reabre la salida apagada.
        env['HF_HUB_OFFLINE'] = '1'
        env['TRANSFORMERS_OFFLINE'] = '1'


class RedireccionRechazada(RuntimeError):
    """086:RF-22 (SSRF, BP-29): una respuesta 3xx que lleva a otra máquina no se sigue."""


def mismo_servidor(origen: str):
    """La regla por defecto de las redirecciones: el mismo host y puerto, http o https, y nunca de https a http."""
    from urllib.parse import urlsplit

    o = urlsplit(origen)

    def admitir(destino: str) -> bool:
        d = urlsplit(destino)
        if d.scheme not in ('http', 'https') or (o.scheme == 'https' and d.scheme != 'https'):
            return False
        return ((d.hostname or '').lower().strip('.') == (o.hostname or '').lower().strip('.')
                and (d.port or _PUERTO[d.scheme]) == (o.port or _PUERTO.get(o.scheme, 0)))

    return admitir


_PUERTO = {'http': 80, 'https': 443}


def get_sin_redireccion_ajena(http, url: str, *, admitir=None, max_saltos: int = 5, **kw):
    """086:RF-22 (SSRF-ARCGIS, BP-29): un GET que NO deja que la biblioteca siga las redirecciones.

    ``requests`` las sigue por defecto, y una respuesta 302 del servidor (o de quien se haga pasar por él) hacia 127.0.0.1,
    el servicio de metadatos de la nube u otra máquina de la red interna hacía que el programa la pidiera. Aquí cada salto
    se mira ANTES de pedirlo con ``admitir`` (por defecto, :func:`mismo_servidor` de la URL de partida); el que no pasa se
    rechaza con :class:`RedireccionRechazada`. ``http`` es el módulo ``requests`` (o una sesión) del módulo que declara su
    salida en :data:`SALIDAS`; este no abre la red por su cuenta. ``params`` solo va en la primera petición: la
    dirección de una redirección ya lleva su consulta.
    """
    from urllib.parse import urljoin

    admitir = admitir or mismo_servidor(url)
    actual = url
    for _ in range(max_saltos + 1):
        respuesta = http.get(actual, allow_redirects=False, **kw)
        codigo = int(getattr(respuesta, 'status_code', 200) or 200)
        destino = (getattr(respuesta, 'headers', None) or {}).get('Location')
        if not (300 <= codigo < 400 and destino):
            return respuesta
        siguiente = urljoin(actual, destino)
        cerrar = getattr(respuesta, 'close', None)
        if callable(cerrar):
            cerrar()
        if not admitir(siguiente):
            raise RedireccionRechazada(f'Redirección rechazada de {actual} a {siguiente}: el programa no sigue una '
                                       'redirección a otra máquina.')
        actual = siguiente
        kw.pop('params', None)
    raise RedireccionRechazada(f'Redirección rechazada desde {url}: más de {max_saltos} saltos.')
