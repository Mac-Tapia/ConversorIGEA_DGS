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
import convertersmartgrid.sources
import convertersmartgrid.sources.txt, convertersmartgrid.sources.mdb, convertersmartgrid.sources.vnr
cargados = sorted(m for m in sys.modules
                  if m.startswith('convertersmartgrid.web') or m.split('.')[0] in ('fastapi', 'starlette'))
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


def test_la_ruta_antigua_sigue_dando_los_mismos_objetos():
    """001:RF-1 — ``convertersmartgrid.web.sources`` reexporta mientras dura la migración."""
    from convertersmartgrid import sources
    from convertersmartgrid.web import sources as antiguo
    from convertersmartgrid.web.source_runs import SourceSnapshot
    from convertersmartgrid.web.sources.vnr import VnrSourceAdapter

    assert antiguo.adapter_for is sources.adapter_for
    assert SourceSnapshot is sources.snapshot.SourceSnapshot
    assert VnrSourceAdapter is sources.vnr.VnrSourceAdapter
