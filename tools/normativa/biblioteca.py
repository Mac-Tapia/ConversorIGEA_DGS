"""La biblioteca normativa general desde la consola (107:RF-21): listar, añadir una norma a la capa del usuario y
exportar el dataset (``normas.jsonl`` y ``reglas.jsonl``) para el asistente y los equipos.

    python tools/normativa/biblioteca.py listar [--fecha AAAA-MM-DD]
    python tools/normativa/biblioteca.py agregar mi_norma.json
    python tools/normativa/biblioteca.py exportar <carpeta>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

from convertersmartgrid.aplicacion import biblioteca_normativa as bn  # noqa: E402
from convertersmartgrid.dominio.registro_normativo import RegistroError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = p.add_subparsers(dest='orden', required=True)
    lis = sub.add_parser('listar', help='las normas, su estado y si obligan en la fecha')
    lis.add_argument('--fecha', default=None)
    agr = sub.add_parser('agregar', help='valida un fichero del esquema y lo copia a la capa del usuario')
    agr.add_argument('fichero', type=Path)
    exp = sub.add_parser('exportar', help='normas.jsonl y reglas.jsonl, solo si la huella cambió')
    exp.add_argument('destino', type=Path)
    a = p.parse_args(argv)
    try:
        if a.orden == 'listar':
            r = bn.cargar_biblioteca(a.fecha)
            for acto in sorted(r.normas):
                n = r.normas[acto]
                print(f'{acto} | {n.estado_juridico} | {len(n.reglas)} reglas | '
                      f'{"obliga" if n.obligatoria_en(a.fecha) else "no obliga"}')
            print(f'{len(r.normas)} normas; capa del usuario: {bn.ruta_capa_usuario()}')
        elif a.orden == 'agregar':
            print('añadidas o sustituidas: ' + ', '.join(bn.agregar_norma(a.fichero)))
        else:
            print(json.dumps(bn.exportar_dataset(a.destino), ensure_ascii=False))
    except RegistroError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
