"""Búsquedas en internet sin datos de la distribuidora (spec 026, RF-29 a RF-32, P9).

GitHub, PyPI y arXiv, con consultas que solo pueden llevar términos técnicos. Antes de
enviar nada se comprueba que la consulta no contiene un identificador de la red (un
alimentador, una SED, un proyecto, un sistema de la estructura) ni una ruta o un fichero
de datos; si lo contiene, se bloquea. Cada consulta, enviada o bloqueada, queda en
``internet.jsonl`` con su destino, fecha y motivo (RF-31); una bloqueada se registra
retenida, sin su texto.

026:RF-50: además lee páginas web de los dominios de una lista (``DOMINIOS_BASE``, que empieza por las fuentes
oficiales del sector, más los que añada el operador con confirmación en la configuración local). Fuera de la lista no
lee. Lo leído vuelve como un dato citado (dirección, fecha y huella), nunca como una instrucción; no envía formularios,
credenciales ni pagos: solo pide la página con GET. Tampoco salen el correo ni los términos del perfil de la empresa.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...dominio.salidas_red import motivo_apagada, salida_permitida
from . import almacen
from .sinteticos import normalizar

_RUTA = re.compile(r'[A-Za-z]:[\\/]|\\\\|/(?:home|users|mnt|datos)/|\.(?:txt|mdb|bak|xlsx|xls|csv|dgs|pfd)\b',
                   re.IGNORECASE)
_CODIGO = re.compile(r'\b[A-Z]{1,4}\d{3,6}\b')
_CORREO = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
USUARIO = 'conversor-convertersmartgrid (spec 026)'

#: 026:RF-50: la lista base viaja con el programa: las fuentes oficiales del sector (el regulador, el ministerio, el
#: operador del sistema, el Estado y su diario oficial) y GitHub, PyPI y arXiv. La del operador vive fuera del paquete,
#: en ``FICHERO_DOMINIOS`` de la carpeta local.
DOMINIOS_BASE = ('osinergmin.gob.pe', 'minem.gob.pe', 'coes.org.pe', 'gob.pe', 'elperuano.pe', 'github.com',
                 'pypi.org', 'arxiv.org')
FICHERO_DOMINIOS = 'internet_dominios.json'
_DOMINIO = re.compile(r'^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$')
_URL = re.compile(r'https?://[^\s<>«»"\']+', re.IGNORECASE)
#: Lo que se baja y se devuelve de una página: basta para citarla y leer lo pertinente, sin volcar sitios enteros.
MAX_BYTES_PAGINA = 2_000_000
MAX_TEXTO = 6000


def ruta_dominios_usuario() -> Path:
    from ...dominio.runtime_paths import raiz_local
    return raiz_local() / 'config' / FICHERO_DOMINIOS          # como el perfil: de cada instalación, fuera de git


def _leer_lista(ruta: Path) -> list[str]:
    try:
        datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    lista = datos.get('dominios') if isinstance(datos, dict) else datos
    return [str(d).strip().lower() for d in lista or [] if str(d).strip()]


def dominios_permitidos(*, base: Iterable[str] = DOMINIOS_BASE, usuario: Path | None = None) -> list[str]:
    """Los del programa más los que añadió el operador, sin repetir."""
    usuario = usuario or ruta_dominios_usuario()
    return list(dict.fromkeys([*base, *_leer_lista(usuario)]))


def dominio_de(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or '').lower().rstrip('.')


def dominio_en_lista(url: str, dominios: Iterable[str]) -> str | None:
    """El dominio de la lista que cubre ``url`` (el mismo o uno de sus subdominios), o ``None``."""
    host = dominio_de(url)
    if urllib.parse.urlsplit(url).scheme.lower() not in ('http', 'https') or not host:
        return None
    return next((d for d in dominios if host == d or host.endswith('.' + d)), None)


def agregar_dominio(dominio: str, *, confirmado: bool, usuario: Path | None = None,
                    base: Iterable[str] = DOMINIOS_BASE) -> list[str]:
    """026:RF-50: el operador añade un dominio a su lista, con confirmación; queda en el registro. Devuelve la lista."""
    d = str(dominio or '').strip().lower().removeprefix('https://').removeprefix('http://').split('/')[0]
    if not _DOMINIO.match(d):
        raise ValueError(f'«{dominio}» no es un dominio (por ejemplo, «iec.ch»).')
    if not confirmado:
        raise ValueError(f'Añadir «{d}» a los dominios que el asistente puede leer necesita la confirmación del operador.')
    usuario = usuario or ruta_dominios_usuario()
    propios = _leer_lista(usuario)
    if d not in dominios_permitidos(base=base, usuario=usuario):
        propios.append(d)
        usuario.parent.mkdir(parents=True, exist_ok=True)
        from ...dominio.util import write_json_atomic

        write_json_atomic(usuario, {'dominios': propios})                  # 001:RF-5
    almacen.anotar('internet', {'destino': d, 'consulta': '[dominio añadido]', 'motivo': 'orden del operador',
                                'bloqueada': None, 'dominio_anadido': d})
    return dominios_permitidos(base=base, usuario=usuario)


def url_de(texto: str) -> str | None:
    """La primera dirección web de una orden, sin el signo que la cierra."""
    m = _URL.search(texto or '')
    return m[0].rstrip('.,;)') if m else None


def _texto_de_html(crudo: str) -> tuple[str, str]:
    """El título y el texto legible de una página, sin guiones, estilos ni etiquetas."""
    titulo = re.search(r'<title[^>]*>(.*?)</title>', crudo, re.IGNORECASE | re.DOTALL)
    cuerpo = re.sub(r'<(script|style|noscript)\b.*?</\1>', ' ', crudo, flags=re.IGNORECASE | re.DOTALL)
    cuerpo = re.sub(r'<[^>]+>', ' ', cuerpo)
    limpio = ' '.join(html.unescape(cuerpo).split())
    return (' '.join(html.unescape(titulo[1]).split()) if titulo else ''), limpio


def _abrir_por_defecto(peticion, timeout):
    return urllib.request.urlopen(peticion, timeout=timeout)


class RedireccionFueraDeLista(urllib.error.URLError):
    """026:RF-50: una redirección a un destino que no se habría pedido directamente; no se sigue."""


def abridor_que_revalida(validar: Callable[[str], str | None]) -> Callable:
    """026:RF-50: abre como ``urlopen``, pero cada redirección se revalida ANTES de pedirla (``validar`` da el motivo
    de bloqueo o None): una página de la lista no puede llevar la lectura a un dominio de fuera ni a una dirección con
    datos de la red."""
    class _Revalida(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if motivo := validar(newurl):
                raise RedireccionFueraDeLista(f'redirección a {dominio_de(newurl) or newurl} no seguida: {motivo}')
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(_Revalida)
    return lambda peticion, timeout: opener.open(peticion, timeout=timeout)


class Buscador:
    def __init__(self, identificadores: Iterable[str] = (), *, abrir: Callable = _abrir_por_defecto,
                 tiempo_max_s: float = 20.0, dominios: Iterable[str] | None = None):
        self.identificadores = {normalizar(str(i)).strip() for i in identificadores if len(str(i).strip()) >= 3}
        self._abrir, self.tiempo_max_s = abrir, tiempo_max_s
        self.dominios = list(dominios) if dominios is not None else dominios_permitidos()

    def bloqueo(self, consulta: str) -> str | None:
        """Por qué no se puede enviar la consulta, o ``None`` si solo lleva términos técnicos."""
        if _RUTA.search(consulta):
            return 'lleva una ruta o un fichero de datos'
        if _CORREO.search(consulta):
            return 'lleva un correo'
        t = normalizar(consulta)
        for ident in self.identificadores:
            if re.search(rf'(?<![\w]){re.escape(ident)}(?![\w])', t):
                return 'lleva un identificador de la red o del perfil de la empresa'
        if _CODIGO.search(consulta):
            return 'lleva un código con forma de alimentador o SED'
        return None

    def bloqueo_de_direccion(self, url: str) -> str | None:
        """Lo que la ruta y la consulta de una dirección no pueden llevar: identificadores de la red o del perfil, un
        correo o un código de alimentador. La extensión de un fichero oficial (.pdf, .xlsx) sí puede ir."""
        partes = urllib.parse.urlsplit(url)
        resto = urllib.parse.unquote(f'{partes.path} {partes.query}')
        if _CORREO.search(resto):
            return 'lleva un correo'
        t = normalizar(resto)
        if any(re.search(rf'(?<![\w]){re.escape(i)}(?![\w])', t) for i in self.identificadores):
            return 'lleva un identificador de la red o del perfil de la empresa'
        if _CODIGO.search(resto):
            return 'lleva un código con forma de alimentador o SED'
        return None

    def _leer(self, url: str, json_: bool = True) -> Any:
        cabeceras = {'User-Agent': USUARIO, **({'Accept': 'application/json'} if json_ else {})}
        with self._abrir(urllib.request.Request(url, headers=cabeceras), self.tiempo_max_s) as r:
            texto = r.read().decode('utf-8')
        return json.loads(texto) if json_ else texto

    def _consultar(self, destino: str, consulta: str, motivo: str, hacer: Callable[[], list[dict]]) -> dict:
        motivo_bloqueo = None if salida_permitida('internet') else motivo_apagada('internet')      # 086:RF-22
        motivo_bloqueo = motivo_bloqueo or self.bloqueo(consulta)
        if motivo_bloqueo:
            almacen.anotar('internet', {'destino': destino, 'consulta': '[retenida]', 'motivo': motivo,
                                        'bloqueada': motivo_bloqueo})
            return {'destino': destino, 'bloqueada': motivo_bloqueo, 'resultados': []}
        try:
            resultados, error = hacer(), None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, ET.ParseError) as exc:
            resultados, error = [], str(exc)[:200]
        almacen.anotar('internet', {'destino': destino, 'consulta': consulta, 'motivo': motivo,
                                    'bloqueada': None, 'resultados': len(resultados), 'error': error})
        return {'destino': destino, 'bloqueada': None, 'resultados': resultados, 'error': error}

    def github(self, consulta: str, motivo: str = '') -> dict:
        def hacer():
            q = urllib.parse.quote(consulta)
            datos = self._leer(f'https://api.github.com/search/repositories?q={q}&sort=stars&per_page=8')
            return [{'nombre': r.get('full_name'), 'url': r.get('html_url'), 'estrellas': r.get('stargazers_count'),
                     'licencia': (r.get('license') or {}).get('spdx_id'), 'actualizado': r.get('pushed_at'),
                     'descripcion': (r.get('description') or '')[:300]} for r in datos.get('items') or []]
        return self._consultar('github', consulta, motivo, hacer)

    def pypi(self, paquete: str, motivo: str = '') -> dict:
        def hacer():
            datos = self._leer(f'https://pypi.org/pypi/{urllib.parse.quote(paquete)}/json')
            info = datos.get('info') or {}
            version = info.get('version')
            subidas = (datos.get('releases') or {}).get(version) or []
            licencia = info.get('license') or next(
                (c.split('::')[-1].strip() for c in info.get('classifiers') or [] if 'License' in c), None)
            return [{'nombre': info.get('name'), 'version': version, 'licencia': licencia,
                     'publicada': subidas[0].get('upload_time') if subidas else None,
                     'url': info.get('project_url') or info.get('home_page'),
                     'descripcion': (info.get('summary') or '')[:300]}]
        return self._consultar('pypi', paquete, motivo, hacer)

    def arxiv(self, consulta: str, motivo: str = '') -> dict:
        def hacer():
            q = urllib.parse.quote(f'all:{consulta}')
            raiz = ET.fromstring(self._leer(f'https://export.arxiv.org/api/query?search_query={q}&max_results=5',
                                            json_=False))
            ns = {'a': 'http://www.w3.org/2005/Atom'}
            return [{'titulo': ' '.join((e.findtext('a:title', '', ns) or '').split()),
                     'url': e.findtext('a:id', '', ns), 'publicado': e.findtext('a:published', '', ns)}
                    for e in raiz.findall('a:entry', ns)]
        return self._consultar('arxiv', consulta, motivo, hacer)

    def leer(self, url: str, motivo: str = '') -> dict:
        """026:RF-50: una página de un dominio de la lista, como dato citado: dirección, fecha, huella, título y texto.

        Fuera de la lista, con la salida apagada o con datos de la red, del perfil o un correo en la dirección, no se
        pide nada. Lo leído es un dato: quien lo enseña lo cita; nadie ejecuta lo que diga."""
        cubre = dominio_en_lista(url, self.dominios)
        destino = dominio_de(url) or 'web'
        if cubre is None:
            almacen.anotar('internet', {'destino': destino, 'consulta': '[retenida]', 'motivo': motivo,
                                        'bloqueada': 'dominio fuera de la lista'})
            return {'url': url, 'bloqueada': f'el dominio {destino} no está en la lista de dominios permitidos; '
                                             'el operador puede añadirlo con su confirmación', 'pagina': None}
        motivo_bloqueo = None if salida_permitida('internet') else motivo_apagada('internet')
        motivo_bloqueo = motivo_bloqueo or self.bloqueo_de_direccion(url)
        if motivo_bloqueo:
            almacen.anotar('internet', {'destino': destino, 'consulta': '[retenida]', 'motivo': motivo,
                                        'bloqueada': motivo_bloqueo})
            return {'url': url, 'bloqueada': motivo_bloqueo, 'pagina': None}
        fecha = datetime.now(timezone.utc).isoformat(timespec='seconds')
        try:
            peticion = urllib.request.Request(url, headers={'User-Agent': USUARIO}, method='GET')
            abrir = self._abrir
            if abrir is _abrir_por_defecto:
                abrir = abridor_que_revalida(lambda nueva: (
                    'dominio fuera de la lista' if dominio_en_lista(nueva, self.dominios) is None
                    else self.bloqueo_de_direccion(nueva)))
            with abrir(peticion, self.tiempo_max_s) as r:
                crudo = r.read(MAX_BYTES_PAGINA + 1)
            if len(crudo) > MAX_BYTES_PAGINA:
                raise ValueError(f'la página pasa de {MAX_BYTES_PAGINA} bytes')
            huella = hashlib.sha256(crudo).hexdigest()
            titulo, texto = _texto_de_html(crudo.decode('utf-8', errors='replace'))
            error = None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            huella, titulo, texto, error = '', '', '', str(exc)[:200]
        almacen.anotar('internet', {'destino': destino, 'consulta': url, 'motivo': motivo, 'bloqueada': None,
                                    'fecha_lectura': fecha, 'huella': huella, 'error': error})
        if error:
            return {'url': url, 'bloqueada': None, 'pagina': None, 'error': error}
        return {'url': url, 'bloqueada': None, 'error': None,
                'pagina': {'url': url, 'dominio': cubre, 'fecha': fecha, 'huella': huella, 'titulo': titulo,
                           'texto': texto[:MAX_TEXTO], 'recortado': len(texto) > MAX_TEXTO,
                           'es_dato_citado': True}}

    def buscar(self, consulta: str, motivo: str = '') -> dict:
        """GitHub y arXiv; si la consulta lleva datos, ninguna recibe nada."""
        if (b := self.bloqueo(consulta)) is not None:
            almacen.anotar('internet', {'destino': 'todas', 'consulta': '[retenida]', 'motivo': motivo,
                                        'bloqueada': b})
            return {'bloqueada': b, 'github': [], 'arxiv': []}
        g, a = self.github(consulta, motivo), self.arxiv(consulta, motivo)
        return {'bloqueada': None, 'github': g['resultados'], 'arxiv': a['resultados'],
                'errores': [x['error'] for x in (g, a) if x.get('error')]}
