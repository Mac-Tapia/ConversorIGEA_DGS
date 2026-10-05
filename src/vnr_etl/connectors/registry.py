"""Registro de adaptadores de fuente (sección U10).

Un adaptador se resuelve por la naturaleza de la fuente, no por el nombre de una
empresa. Los adaptadores cuyo driver es opcional se instancian igual; fallan con
``AdapterUnavailable`` solo cuando se usan.
"""

from __future__ import annotations

from pathlib import Path

from .arcgis import ArcGISRestAdapter
from .base import VNRSourceAdapter
from .delimited import DelimitedTextAdapter
from .vector import VectorFileAdapter

ADAPTERS: list[type[VNRSourceAdapter]] = [
    ArcGISRestAdapter,
    VectorFileAdapter,
    DelimitedTextAdapter,
]

SUPPORTED_SOURCE_SUFFIXES = frozenset({
    '.shp', '.gpkg', '.geojson', '.json', '.txt', '.csv', '.tsv',
    '.mdb', '.accdb', '.db', '.sqlite',
})


def iter_supported_sources(root: Path | str) -> list[Path]:
    """Archivos de datos candidatos de un paquete, en orden determinista."""
    path = Path(root)
    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES else []
    return sorted(
        candidate for candidate in path.rglob('*')
        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES
    )


def resolve_adapter(source: str) -> VNRSourceAdapter:
    """Elige el adaptador adecuado para una fuente (URL, archivo o base)."""

    fuente = (source or '').strip()
    if fuente.lower().startswith(('http://', 'https://')):
        return ArcGISRestAdapter(url=fuente)

    path = Path(fuente)
    suffix = path.suffix.lower() if path.is_file() else ('.' + fuente.rsplit('.', 1)[-1]).lower()
    if suffix in ('.shp', '.gpkg', '.geojson', '.json'):
        return VectorFileAdapter(path=fuente)
    if suffix in ('.txt', '.csv', '.tsv'):
        return DelimitedTextAdapter(path=fuente)
    if suffix in ('.zip', '.rar'):
        return VectorFileAdapter(path=fuente)  # se extrae antes (MODE B)
    if suffix in ('.mdb', '.accdb'):
        from .databases import AccessAdapter  # noqa: F401  # importación diferida

        return __import__('vnr_etl.connectors.databases', fromlist=['AccessAdapter']).AccessAdapter(path=fuente)
    if suffix in ('.db', '.sqlite'):
        from .databases import SQLiteAdapter

        return SQLiteAdapter(path=fuente)
    raise ValueError(
        f'No hay adaptador para la fuente {source!r}. Use `python -m vnr_etl probe` '
        'para inspeccionar, o indique un formato soportado.'
    )
