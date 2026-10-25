"""Búsquedas en internet sin datos de la distribuidora (spec 026, RF-29 a RF-32, P9).

GitHub, PyPI y arXiv, con consultas que solo pueden llevar términos técnicos. Antes de
enviar nada se comprueba que la consulta no contiene un identificador de la red (un
alimentador, una SED, un proyecto, un sistema de la estructura) ni una ruta o un fichero
de datos; si lo contiene, se bloquea. Cada consulta, enviada o bloqueada, queda en
``internet.jsonl`` con su destino, fecha y motivo (RF-31); una bloqueada se registra
retenida, sin su texto.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from typing import Any

from . import almacen
from .sinteticos import normalizar

_RUTA = re.compile(r'[A-Za-z]:[\\/]|\\\\|/(?:home|users|mnt|datos)/|\.(?:txt|mdb|bak|xlsx|xls|csv|dgs|pfd)\b',
                   re.IGNORECASE)
_CODIGO = re.compile(r'\b[A-Z]{1,4}\d{3,6}\b')
USUARIO = 'conversor-igea-dgs (spec 026)'


def _abrir_por_defecto(peticion, timeout):
    return urllib.request.urlopen(peticion, timeout=timeout)


class Buscador:
    def __init__(self, identificadores: Iterable[str] = (), *, abrir: Callable = _abrir_por_defecto,
                 tiempo_max_s: float = 20.0):
        self.identificadores = {normalizar(str(i)).strip() for i in identificadores if len(str(i).strip()) >= 3}
        self._abrir, self.tiempo_max_s = abrir, tiempo_max_s

    def bloqueo(self, consulta: str) -> str | None:
        """Por qué no se puede enviar la consulta, o ``None`` si solo lleva términos técnicos."""
        if _RUTA.search(consulta):
            return 'lleva una ruta o un fichero de datos'
        t = normalizar(consulta)
        for ident in self.identificadores:
            if re.search(rf'(?<![\w]){re.escape(ident)}(?![\w])', t):
                return 'lleva un identificador de la red'
        if _CODIGO.search(consulta):
            return 'lleva un código con forma de alimentador o SED'
        return None

    def _leer(self, url: str, json_: bool = True) -> Any:
        cabeceras = {'User-Agent': USUARIO, **({'Accept': 'application/json'} if json_ else {})}
        with self._abrir(urllib.request.Request(url, headers=cabeceras), self.tiempo_max_s) as r:
            texto = r.read().decode('utf-8')
        return json.loads(texto) if json_ else texto

    def _consultar(self, destino: str, consulta: str, motivo: str, hacer: Callable[[], list[dict]]) -> dict:
        motivo_bloqueo = self.bloqueo(consulta)
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

    def buscar(self, consulta: str, motivo: str = '') -> dict:
        """GitHub y arXiv; si la consulta lleva datos, ninguna recibe nada."""
        if (b := self.bloqueo(consulta)) is not None:
            almacen.anotar('internet', {'destino': 'todas', 'consulta': '[retenida]', 'motivo': motivo,
                                        'bloqueada': b})
            return {'bloqueada': b, 'github': [], 'arxiv': []}
        g, a = self.github(consulta, motivo), self.arxiv(consulta, motivo)
        return {'bloqueada': None, 'github': g['resultados'], 'arxiv': a['resultados'],
                'errores': [x['error'] for x in (g, a) if x.get('error')]}
