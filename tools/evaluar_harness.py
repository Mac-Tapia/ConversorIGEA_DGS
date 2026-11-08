"""Entrada de consola del arnés de evaluación: no carga motores ni altera los modelos activos.

    python tools/evaluar_harness.py {sellar,replay,ordenes,importar,verificar} --help
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from convertersmartgrid.evaluacion_harness.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
