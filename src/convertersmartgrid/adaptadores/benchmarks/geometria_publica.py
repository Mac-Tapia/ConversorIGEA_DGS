"""La geometría pública de una empresa: su paquete VNR-GIS publicado por Osinergmin, bajado bajo demanda (112:RF-14).

El control de reidentificación compara el benchmark con la red que la propia empresa publica en el VNR-GIS (T14): si
un alimentador del benchmark cuadra por ICP con uno publicado, se identificaría, y el manifiesto lo declara.

- **Bajo demanda y por empresa** (orden del usuario del 2026-11-14): nada masivo. :func:`plan_descarga` dice qué
  paquete vigente se bajaría, de qué URL oficial y adónde, sin abrir la red; :func:`descargar` lo baja con el gestor
  de descargas del VNR (solo hosts de Osinergmin, SHA-256 y manifiesto de la descarga).
- **Fuera del repositorio y sin fuga al corpus**: el destino tiene que ser una carpeta absoluta fuera del programa y de
  sus datos locales (donde viven el corpus y los datasets del asistente), así que ningún índice ni entrenamiento la
  recoge. El paquete es una fuente aparte; no se ejecuta nada de lo que trae.
- **Lectura**: el paquete se convierte con el ETL del VNR al trío TXT de CYMDIST (``vnr-etl``), y
  :func:`vertices_por_alimentador` toma de ese trío los vértices de cada alimentador.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import numpy as np


class DestinoNoPermitido(ValueError):
    """El destino de la descarga cae dentro del programa o de sus datos locales: el paquete acabaría en el corpus."""


def comprobar_destino(destino: Path | str, *, prohibidas: Iterable[Path | str] | None = None) -> Path:
    """El destino, resuelto, si es absoluto y no cae dentro del programa ni de sus datos locales; si no, un error."""
    from ...dominio.runtime_paths import raiz_local, raiz_programa

    ruta = Path(destino)
    if not ruta.is_absolute():
        raise DestinoNoPermitido(f'el destino tiene que ser una ruta absoluta fuera del programa: {destino}')
    ruta = ruta.resolve()
    for raiz in (prohibidas if prohibidas is not None else (raiz_programa(), raiz_local())):
        raiz = Path(raiz).resolve()
        if ruta == raiz or raiz in ruta.parents:
            raise DestinoNoPermitido('el destino cae dentro del programa o de sus datos locales, donde el corpus y los '
                                     'datasets del asistente lo recogerían: elija una carpeta aparte')
    return ruta


def _normal(texto: str) -> str:
    import unicodedata
    sin_tildes = ''.join(c for c in unicodedata.normalize('NFKD', texto) if not unicodedata.combining(c))
    return ' '.join(sin_tildes.casefold().replace('%20', ' ').split())


def paquete_vigente(empresa: str, publicaciones: Iterable[Any]):
    """La publicación del paquete VNR-GIS vigente de ``empresa`` (por resolución, no por título), o un error claro."""
    from ..entrada.vnr.discovery.official import (is_allowed_official_url, is_vnr_data_package,
                                                              vigentes_por_empresa)

    paquetes = [p for p in publicaciones if is_vnr_data_package(p) and is_allowed_official_url(p.download_url)]
    vigentes = vigentes_por_empresa(paquetes)
    buscada = _normal(empresa)
    candidatos = [p for p in paquetes if vigentes[p.publication_id]['vigente']
                  and (_normal(vigentes[p.publication_id]['empresa']) == buscada
                       or _normal(vigentes[p.publication_id]['empresa']).startswith(buscada + ' '))]
    if not candidatos:
        conocidas = sorted({v['empresa'] for v in vigentes.values()})
        raise LookupError(f'no hay un paquete VNR-GIS vigente de «{empresa}» en lo publicado por Osinergmin; '
                          f'empresas con paquete: {", ".join(conocidas) or "ninguna"}')
    if len(candidatos) > 1:
        raise LookupError(f'«{empresa}» coincide con {len(candidatos)} paquetes vigentes: dé el nombre completo')
    return candidatos[0]


def plan_descarga(empresa: str, destino: Path | str, publicaciones: Iterable[Any]) -> dict[str, Any]:
    """Qué se bajaría, de dónde y adónde. No abre la red: las publicaciones vienen del catálogo oficial ya leído."""
    carpeta = comprobar_destino(destino)
    p = paquete_vigente(empresa, publicaciones)
    nombre = Path(p.file_name or p.download_url.rsplit('/', 1)[-1]).name.replace('%20', ' ')
    return {'empresa': p.company or empresa, 'url': p.download_url, 'resolucion': p.regulatory_reference,
            'ciclo': p.period_label, 'publicacion': p.publication_id, 'destino': str(carpeta / nombre)}


def descargar(plan: dict[str, Any], *, gestor=None, cancelado: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Baja el paquete del plan con el gestor del VNR (hosts de Osinergmin, SHA-256 y manifiesto). Devuelve su manifiesto."""
    from ..entrada.vnr.discovery.download import DownloadManager
    from ..entrada.vnr.discovery.official import DEFAULT_ALLOWED_HOSTS

    destino = comprobar_destino(plan['destino'])
    if gestor is None:
        gestor = DownloadManager(destino.parent, allowed_hosts=list(DEFAULT_ALLOWED_HOSTS))
    manifiesto = gestor.download(plan['url'], destino, publication_id=plan['publicacion'], company=plan['empresa'],
                                 period=plan['ciclo'], cancelled=cancelado)
    return manifiesto.as_dict() if hasattr(manifiesto, 'as_dict') else dict(manifiesto)


def vertices_por_alimentador(trio: Iterable[Path | str]) -> dict[str, np.ndarray]:
    """Los vértices (x, y) de cada alimentador de un trío TXT: los nudos de sus tramos y sus intermedios."""
    from ...dominio.benchmarks.redes import NOMBRES, leer_fichero

    ficheros = [leer_fichero(r, n) for r, n in zip(trio, NOMBRES)]
    red = next(f for f in ficheros if f.nombre == 'RED.txt')
    nudos: dict[str, tuple[float, float]] = {}
    intermedios: dict[str, list[tuple[float, float]]] = {}
    tramos: dict[str, list[tuple[str, str, str]]] = {}
    actual = None
    for e in red.entradas:
        if e[0] == 'feeder':
            actual = dict(zip(e[1], e[2])).get('NetworkID')
            tramos.setdefault(actual, [])
        elif e[0] != 'fila':
            continue
        elif e[1] == 'SECTION' and actual:
            tramos[actual].append((e[2]['SectionID'], e[2]['FromNodeID'], e[2]['ToNodeID']))
        elif e[1] == 'NODE' and e[2].get('CoordX') and e[2].get('CoordY'):
            nudos[e[2]['NodeID']] = (float(e[2]['CoordX']), float(e[2]['CoordY']))
        elif e[1] == 'INTERMEDIATE NODES' and e[2].get('CoordX') and e[2].get('CoordY'):
            intermedios.setdefault(e[2]['SectionID'], []).append((float(e[2]['CoordX']), float(e[2]['CoordY'])))
    salida: dict[str, np.ndarray] = {}
    for red_id, lista in tramos.items():
        puntos: dict[tuple[float, float], None] = {}
        for tramo, a, b in lista:
            for n in (a, b):
                if n in nudos:
                    puntos[nudos[n]] = None
            for p in intermedios.get(tramo, ()):
                puntos[p] = None
        if puntos:
            salida[red_id] = np.array(list(puntos), dtype=float)
    return salida
