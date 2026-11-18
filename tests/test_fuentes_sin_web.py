"""Los adaptadores de entrada no dependen de la web (spec 001, T5).

Vivían en ``web/sources`` e importaban ``web/source_runs``: el CLI no podía leer como la
web sin arrastrar FastAPI. Se comprueba en un proceso aparte, porque en el de pytest
otras pruebas ya han importado la web.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src'

COMPROBACION = '''
import sys
import convertersmartgrid.adaptadores.sources
import convertersmartgrid.adaptadores.sources.txt, convertersmartgrid.adaptadores.sources.mdb, convertersmartgrid.adaptadores.sources.vnr
cargados = sorted(m for m in sys.modules
                  if m.startswith('convertersmartgrid.presentacion.web') or m.split('.')[0] in ('fastapi', 'starlette'))
print(cargados)
sys.exit(1 if cargados else 0)
'''


def test_importar_los_adaptadores_no_carga_la_web():
    """001:RF-1 — el CLI puede usar los mismos adaptadores sin la capa web."""
    resultado = subprocess.run(
        [sys.executable, '-c', COMPROBACION], capture_output=True, text=True,
        env={**os.environ, 'PYTHONPATH': str(SRC)},
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_002_rf21_la_reexportacion_antigua_de_las_fuentes_ya_no_existe():
    """002:RF-21 — la reexportación temporal de ``web.sources`` se retiró: la ruta antigua no importa y los adaptadores
    viven en ``adaptadores.sources``, con el mismo ``SourceSnapshot`` (valor del dominio) que usa la web."""
    import importlib

    import pytest

    from convertersmartgrid.adaptadores.sources import txt
    from convertersmartgrid.dominio.sources import snapshot
    from convertersmartgrid.presentacion.web.source_runs import SourceSnapshot

    for antigua in ('convertersmartgrid.web.sources', 'convertersmartgrid.presentacion.web.sources'):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(antigua)
    assert SourceSnapshot is snapshot.SourceSnapshot
    assert txt.__name__ == 'convertersmartgrid.adaptadores.sources.txt'
