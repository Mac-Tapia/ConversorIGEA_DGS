#!/usr/bin/env python
"""Prepara o verifica los clones GitHub fijados, sin instalar ni ejecutar terceros.

    python tools/preparar_upstream_ia.py [--verificar] [--catalogo RUTA] [--destino RUTA]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / 'src') not in sys.path:
    sys.path.insert(0, str(RAIZ / 'src'))
from igea_dgs.upstream_ia import preparar_catalogo


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogo', type=Path, default=RAIZ / 'docs/UPSTREAM_IA_LOCK.json')
    parser.add_argument('--destino', type=Path, default=RAIZ / 'external/upstream')
    parser.add_argument('--verificar', action='store_true')
    parser.add_argument('--output-json', type=Path)
    args = parser.parse_args(argv)
    try:
        informe = preparar_catalogo(json.loads(args.catalogo.read_text(encoding='utf-8')),
                                    args.destino, verificar=args.verificar)
    except (OSError, ValueError) as exc:
        informe = {'ok': False, 'error': str(exc)}
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(informe, indent=2, ensure_ascii=False))
    return 0 if informe['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
