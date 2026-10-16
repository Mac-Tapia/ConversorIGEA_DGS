"""Genera en ``input/`` la tabla de parámetros eléctricos y audita los alimentadores.

    python tools/build_input_catalog.py --red RED.txt --cargas CARGA.txt --equipos BD.txt
    python tools/build_input_catalog.py --mdb BaseDatos.mdb

La tabla sale con lo que el modelo usa hoy, lo que dice la ficha del fabricante cuando
se tiene, y la diferencia entre ambos. Las casillas en blanco son las que hay que
completar con la ficha del proveedor.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

# La consola de Windows usa cp1252 y los mensajes llevan Ω, µ y √. Sin esto el
# programa hace todo el trabajo y muere al imprimir el resultado.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):  # pragma: no cover - consola no reconfigurable
        pass

from igea_dgs.catalog import auditar, escribir_catalogo, input_dir  # noqa: E402
from igea_dgs.model import build_feeder_model  # noqa: E402


def cargar_dataset(args: argparse.Namespace):
    if args.mdb:
        from igea_dgs.access import read_access_dataset
        return read_access_dataset(args.mdb, equipment_path=args.equipment_mdb)
    from igea_dgs.dataset import CymdistDataset
    return CymdistDataset.from_files(args.red, args.cargas, args.equipos)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--red')
    p.add_argument('--cargas')
    p.add_argument('--equipos')
    p.add_argument('--mdb')
    p.add_argument('--equipment-mdb')
    p.add_argument('--feeder', action='append', default=[],
                   help='Limitar a estos alimentadores (por defecto, todos).')
    p.add_argument('--out', help='Ruta del fichero. Por defecto input/catalogo_parametros.xlsx')
    p.add_argument('--base', default='.', help='Carpeta donde se crea input/.')
    args = p.parse_args(argv)

    if not args.mdb and not (args.red and args.cargas and args.equipos):
        p.error('indique --mdb, o bien --red, --cargas y --equipos')

    ds = cargar_dataset(args)
    redes = ds.feeder_ids()
    modelos = []
    fallidos = []
    for net in redes:
        try:
            m = build_feeder_model(ds, net, strict=False)
        except Exception as exc:  # noqa: BLE001 - un alimentador roto no para el catálogo
            fallidos.append(f'{net}: {exc}')
            continue
        if args.feeder and m.name not in args.feeder:
            continue
        modelos.append(m)

    if not modelos:
        print('No se pudo construir ningún alimentador.', file=sys.stderr)
        for f in fallidos:
            print(f'  {f}', file=sys.stderr)
        return 2

    aud = auditar(modelos)
    nominal = modelos[0].nominal_kv
    destino = escribir_catalogo(
        aud, args.out, base=args.base, nominal_kv=nominal,
    )

    print(f'Alimentadores analizados: {len(modelos)}')
    if fallidos:
        print(f'No convertibles (se excluyen del catálogo): {len(fallidos)}')
    print(f'Tipos de línea en uso: {len(aud.usos)}')
    print(f'Potencias de SED distintas: {len(aud.trafos_kva)}')
    print()
    print(aud.resumen())
    print()
    for h in aud.hallazgos[:25]:
        print('  ' + h.linea())
    if len(aud.hallazgos) > 25:
        print(f'  … y {len(aud.hallazgos) - 25} más en la hoja «hallazgos».')
    print()
    print(f'Catálogo escrito en: {destino}')
    print(f'Carpeta de entrada:  {input_dir(args.base)}')
    return 1 if aud.graves else 0


if __name__ == '__main__':
    raise SystemExit(main())
