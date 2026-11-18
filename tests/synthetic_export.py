"""Generador de exports CYMDIST sintéticos de las pruebas: vive en ``convertersmartgrid.dominio.benchmarks.sintetico``.

Se movió al núcleo en la spec 112 (T13, opción A), porque el benchmark publicable sale de ``ExportSpec`` y el código de
``src/`` no puede importar de ``tests/``. Aquí se reexporta por nombre —también lo privado que alguna prueba usa—, para
que ninguna prueba cambie y la salida siga siendo la misma byte a byte (lo comprueba
``tests/test_benchmarks_sintetico.py``).
"""

from __future__ import annotations

from pathlib import Path

from convertersmartgrid.dominio.benchmarks.sintetico import (  # noqa: F401
    _SIZES_CACHE,
    CRS_SINTETICO,
    FMT_BD_CABLE,
    FMT_BD_LINE,
    FMT_CUSTOMERLOADS,
    FMT_FEEDER,
    FMT_HEADNODES,
    FMT_INTERMEDIATE,
    FMT_LINECONF,
    FMT_LOADS,
    FMT_NODE,
    FMT_OVERHEAD_SETTING,
    FMT_SECTION,
    FMT_SECTION_COMPLETO,
    FMT_SOURCE,
    FMT_SOURCE_COMPLETO,
    FMT_SWITCH,
    FMT_UNDERGROUND_SETTING,
    ExportSpec,
    FeederSize,
    _pad,
    write_export,
)


def load_export(spec: ExportSpec, out_dir: Path):
    """Genera el export y lo devuelve ya leído como ``CymdistDataset``.

    Se queda en las pruebas: usa el lector (capa de adaptadores) y el generador del núcleo es de dominio.
    """
    from convertersmartgrid.adaptadores.dataset import CymdistDataset

    red, carga, equipo = write_export(spec, out_dir)
    return CymdistDataset.from_files(red, carga, equipo)
