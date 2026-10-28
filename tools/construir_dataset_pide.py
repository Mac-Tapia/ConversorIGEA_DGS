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
    parser.add_argument('--solo-ejemplos', action='store_true',
                        help='no reconstruye: saca del corpus de --destino los ejemplos del agente '
                             '(artículos, formatos e informes 4.1 y 4.2; spec 027, RF-48 y RF-50)')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.solo_ejemplos:
        from igea_dgs.asistente.ejemplos_pide import construir, resumen
        from igea_dgs.pide_dataset import cargar_contrato

        datos = construir(args.destino, cargar_contrato(args.contrato))
        ruta = args.destino / 'ejemplos_agente.json'
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding='utf-8')
        for linea in resumen(datos):
            print(linea)
        print(f'Ejemplos en {ruta}')
        return 0
    if not args.raiz.is_dir():
        _parser().error(f'no existe la raíz: {args.raiz}')
    summary = construir_dataset(args.raiz, args.destino, args.empresa, args.contrato,
                                sin_texto=args.sin_texto, max_chars=args.max_chars)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
