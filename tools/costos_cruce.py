#!/usr/bin/env python
"""Mide cuánto de una red convertida encuentra costo en el SICODI público (spec 072).

Lee el zip del SICODI y el `dataset_inventory.json` de una conversión, y dice por peso de tramos
qué códigos de línea tienen costo y por qué no los demás. No valora obras: solo mide el cruce.

Uso:
    python tools/costos_cruce.py --sicodi <zip> --inventario <json> --sector ST2 --estructura C \
        --resolucion 184-2026-OS/CD --anio 2026 --moneda <moneda> --url <url> --fecha-descarga <fecha> \
        --salida <json>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Mide cuánto de una red encuentra costo en el SICODI (spec 072).')
    p.add_argument('--sicodi', type=Path, required=True, help='Zip público con Instalacion.txt')
    p.add_argument('--inventario', type=Path, required=True, help='dataset_inventory.json de la conversión')
    p.add_argument('--sector', required=True, help='Sector típico del sistema: ST1 a ST4 o SER')
    p.add_argument('--estructura', required=True, help='Código de estructura del SICODI: A, B, C, D o E')
    p.add_argument('--resolucion', required=True, help='Resolución de Osinergmin que publica la fuente')
    p.add_argument('--anio', type=int, required=True, help='Año de la fuente')
    p.add_argument('--moneda', required=True, help='Moneda de los costos; el TXT no la declara')
    p.add_argument('--url', required=True, help='URL de Osinergmin de la fuente')
    p.add_argument('--fecha-descarga', required=True, help='Fecha en que se descargó')
    p.add_argument('--salida', type=Path, help='JSON con el resultado')
    args = p.parse_args(argv)

    from convertersmartgrid.costos_fuentes import CostosError, cruzar_codigos, leer_sicodi

    try:
        tabla = leer_sicodi(args.sicodi, resolucion=args.resolucion, anio=args.anio, moneda=args.moneda,
                            url=args.url, fecha_descarga=args.fecha_descarga)
    except CostosError as exc:
        print(f'ERROR: {exc}')
        return 2
    inventario = json.loads(args.inventario.read_text(encoding='utf-8'))
    usos = [(x['code'], x['sections']) for x in inventario.get('top_line_cable_ids') or []]
    if not usos:
        print('ERROR: el inventario no trae códigos de línea')
        return 2
    r = cruzar_codigos(usos, tabla, sector=args.sector, estructura=args.estructura)
    if args.salida:
        args.salida.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Códigos con costo: {r['codigos_con_costo']} de {r['codigos']}; "
          f"{r['fraccion_con_costo']:.1%} de los tramos listados en el inventario")
    for x in r['sin_costo']:
        print(f"  sin costo: {x['codigo']} ({x['peso']} tramos): {x['motivo']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
