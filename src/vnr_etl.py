"""002:RF-22: compatibilidad de CLI; la implementación vive en el adaptador VNR.

Conserva también el entry point anterior ``vnr_etl.cli:main`` sin cargar una
segunda copia del módulo. Los consumidores internos usan la ruta canónica.
"""
from __future__ import annotations

import sys

from convertersmartgrid.adaptadores.entrada.vnr import __version__, cli

main = cli.main
sys.modules['vnr_etl.cli'] = cli

if __name__ == '__main__':
    raise SystemExit(main())
