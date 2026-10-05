"""Comprobación mínima del entorno que usa el lanzador web de Windows."""
from __future__ import annotations

import importlib
from collections.abc import Callable

REQUIRED_MODULES = (
    'igea_dgs',
    'pyproj',
    'fastapi',
    'uvicorn',
    'multipart',
    # Tercera fuente: VNR-GIS y su normalización GIS/topológica.
    'vnr_etl',
    'requests',
    'shapely',
    'networkx',
    'yaml',
    'geopandas',
)


def missing_dependencies(
    importer: Callable[[str], object] = importlib.import_module,
) -> tuple[str, ...]:
    missing: list[str] = []
    for name in REQUIRED_MODULES:
        try:
            importer(name)
        except (ImportError, OSError):
            missing.append(name)
    return tuple(missing)


def main() -> int:
    missing = missing_dependencies()
    if missing:
        print('Dependencias faltantes: ' + ', '.join(missing))
        return 1
    print('Entorno web listo: TXT, MDB y VNR-GIS.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
