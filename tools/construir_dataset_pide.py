"""Construye el corpus PIDE universal desde un expediente empresarial de solo lectura."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from igea_dgs.pide_dataset import construir_dataset


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz', required=True, type=Path)
    parser.add_argument('--destino', required=True, type=Path)
    parser.add_argument('--empresa', required=True)
    parser.add_argument('--contrato', required=True, type=Path)
    parser.add_argument('--sin-texto', action='store_true',
                        help='calcula custodia y calidad sin extraer contenido semántico')
    parser.add_argument('--max-chars', type=int, default=1800)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.raiz.is_dir():
        _parser().error(f'no existe la raíz: {args.raiz}')
    summary = construir_dataset(args.raiz, args.destino, args.empresa, args.contrato,
                                sin_texto=args.sin_texto, max_chars=args.max_chars)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
