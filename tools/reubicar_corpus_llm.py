#!/usr/bin/env python
"""Custodiar un corpus LLM tras un traslado exacto de datos, sin entrenar (047/065)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'src') not in sys.path:
    sys.path.insert(0, str(REPO / 'src'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for nombre in ('origen', 'destino', 'raiz-anterior', 'raiz-nueva'):
        parser.add_argument('--' + nombre, type=Path, required=True)
    parser.add_argument('--ejecutar', action='store_true', help='Publicar la nueva versión; por defecto solo validar.')
    parser.add_argument('--max-bytes', type=int, default=1024 ** 3, help='Cuota total de la nueva custodia.')
    args = parser.parse_args(argv)
    try:
        from convertersmartgrid.asistente.reubicacion_corpus import reubicar_corpus
        informe = reubicar_corpus(args.origen, args.destino, args.raiz_anterior, args.raiz_nueva,
                                  ejecutar=args.ejecutar, max_bytes=args.max_bytes)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'ejecutado': False, 'error': str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps(informe, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
