#!/usr/bin/env python
"""Mide cuánto de una red convertida encuentra costo en el SICODI público (spec 072).

Lee el zip del SICODI y el `dataset_inventory.json` de una conversión, y dice por peso de tramos
qué códigos de línea tienen costo y por qué no los demás. Con `--red`, `--cargas`, `--equipos` y
`--alimentador`, además, los metrados de ese alimentador y su valoración.

Con `--obra`, valora los elementos de una obra (JSON, lista de `elemento`, `ambito`, `codigo`,
`cantidad`…): los de distribución con el SICODI y los de transmisión con el libro de módulos
estándar de `--modulos`, cuyas columnas se declaran en `--modulos-columnas` (072:RF-6).

Uso:
    python tools/costos_cruce.py --sicodi <zip> --inventario <json> --sector ST2 --estructura C \
        --resolucion 184-2026-OS/CD --anio 2026 --moneda <moneda> --url <url> --fecha-descarga <fecha> \
        --salida <json>
    python tools/costos_cruce.py --obra <json> --modulos <xlsm> --modulos-columnas <json> \
        --modulos-resolucion 181-2026-OS/CD --modulos-anio 2026 --modulos-moneda <moneda> \
        --modulos-url <url> --modulos-fecha-descarga <fecha> [--sicodi <zip> ...] --salida <json>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _metrados(args, tabla) -> int:
    from convertersmartgrid.dataset import CymdistDataset
    from convertersmartgrid.metrados import metrados_de_lineas, valorar_metrados
    from convertersmartgrid.model import build_feeder_model

    if not (args.cargas and args.equipos and args.alimentador):
        print('ERROR: los metrados piden --red, --cargas, --equipos y --alimentador')
        return 2
    modelo = build_feeder_model(CymdistDataset.from_files(args.red, args.cargas, args.equipos), args.alimentador)
    m = metrados_de_lineas(modelo.lines)
    v = valorar_metrados(m['por_codigo'], tabla, sector=args.sector, estructura=args.estructura)
    print(f"{args.alimentador}: {m['tramos']} tramos, {m['km']:.2f} km, {len(m['por_codigo'])} códigos; "
          f"sin código: {len(m['sin_codigo'])}")
    print(f"Valorados: {v['km_valorados']:.2f} km, {v['total']:,.0f} {v['moneda']}; sin costo: {v['km_sin_costo']:.2f} km")
    for x in v['sin_costo'][:10]:
        print(f"  sin costo: {x['codigo']} ({x['km']:.2f} km): {x['motivo']}")
    if args.salida:
        args.salida.write_text(json.dumps({'metrados': m, 'valoracion': v}, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


def _obra(args, tabla_sicodi) -> int:
    from convertersmartgrid.costos_fuentes import CostosError, leer_modulos_transmision, valorar_obra

    tablas = {'distribucion': tabla_sicodi} if tabla_sicodi is not None else {}
    if args.modulos:
        faltan = [n for n in ('modulos_columnas', 'modulos_resolucion', 'modulos_anio', 'modulos_moneda',
                              'modulos_url', 'modulos_fecha_descarga') if getattr(args, n) in (None, '')]
        if faltan:
            print('ERROR: los módulos piden ' + ', '.join('--' + n.replace('_', '-') for n in faltan))
            return 2
        try:
            tablas['transmision'] = leer_modulos_transmision(
                args.modulos, columnas=json.loads(args.modulos_columnas.read_text(encoding='utf-8')),
                resolucion=args.modulos_resolucion, anio=args.modulos_anio, moneda=args.modulos_moneda,
                url=args.modulos_url, fecha_descarga=args.modulos_fecha_descarga, hoja=args.modulos_hoja)
        except CostosError as exc:
            print(f'ERROR: {exc}')
            return 2
    if not tablas:
        print('ERROR: --obra pide --sicodi, --modulos o los dos')
        return 2
    r = valorar_obra(json.loads(args.obra.read_text(encoding='utf-8')), tablas)
    for moneda, total in r['total_por_moneda'].items():
        print(f'Total valorado: {total:,.2f} {moneda}')
    print(f"Elementos valorados: {len(r['valorados'])}; sin costo: {len(r['sin_costo'])}")
    for x in r['sin_costo']:
        print(f"  sin costo: {x['elemento']} ({x['ambito']}): {x['motivo']}")
    if args.salida:
        args.salida.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Mide cuánto de una red encuentra costo en el SICODI, y valora '
                                            'obras con SICODI y módulos de transmisión (spec 072).')
    p.add_argument('--sicodi', type=Path, help='Zip público con Instalacion.txt')
    p.add_argument('--obra', type=Path, help='JSON con los elementos de una obra a valorar')
    p.add_argument('--modulos', type=Path, help='Libro de módulos estándar de transmisión (.xlsx o .xlsm)')
    p.add_argument('--modulos-columnas', type=Path,
                   help='JSON con el nombre de las columnas codigo, nombre, unidad, total y, si hay, zona')
    p.add_argument('--modulos-hoja', help='Hoja del libro de módulos; por defecto la primera')
    p.add_argument('--modulos-resolucion', help='Resolución de Osinergmin de los módulos')
    p.add_argument('--modulos-anio', type=int, help='Año de los módulos')
    p.add_argument('--modulos-moneda', help='Moneda de los módulos; el libro no se supone')
    p.add_argument('--modulos-url', help='URL de Osinergmin de los módulos')
    p.add_argument('--modulos-fecha-descarga', help='Fecha en que se descargaron los módulos')
    p.add_argument('--inventario', type=Path, help='dataset_inventory.json de la conversión')
    p.add_argument('--red', type=Path, help='TXT RED, para los metrados de un alimentador')
    p.add_argument('--cargas', type=Path, help='TXT CARGA')
    p.add_argument('--equipos', type=Path, help='TXT BD_Equipo')
    p.add_argument('--alimentador', help='Alimentador de los metrados')
    p.add_argument('--sector', help='Sector típico del sistema: ST1 a ST4 o SER (con --inventario o --red)')
    p.add_argument('--estructura', help='Código de estructura del SICODI: A, B, C, D o E (con --inventario o --red)')
    p.add_argument('--resolucion', help='Resolución de Osinergmin que publica el SICODI')
    p.add_argument('--anio', type=int, help='Año del SICODI')
    p.add_argument('--moneda', help='Moneda del SICODI; el TXT no la declara')
    p.add_argument('--url', help='URL de Osinergmin del SICODI')
    p.add_argument('--fecha-descarga', help='Fecha en que se descargó el SICODI')
    p.add_argument('--salida', type=Path, help='JSON con el resultado')
    args = p.parse_args(argv)

    from convertersmartgrid.costos_fuentes import CostosError, cruzar_codigos, leer_sicodi

    tabla = None
    if args.sicodi:
        # Antes eran obligatorios en argparse; con --obra solo de módulos no hay SICODI que declarar.
        faltan = [n for n in ('resolucion', 'anio', 'moneda', 'url', 'fecha_descarga') if getattr(args, n) in (None, '')]
        if faltan:
            print('ERROR: el SICODI pide ' + ', '.join('--' + n.replace('_', '-') for n in faltan))
            return 2
        try:
            tabla = leer_sicodi(args.sicodi, resolucion=args.resolucion, anio=args.anio, moneda=args.moneda,
                                url=args.url, fecha_descarga=args.fecha_descarga)
        except CostosError as exc:
            print(f'ERROR: {exc}')
            return 2
    if args.obra:
        return _obra(args, tabla)
    if tabla is None:
        print('ERROR: indique --sicodi, o --obra con sus fuentes')
        return 2
    if not (args.sector and args.estructura):
        print('ERROR: el cruce con la red pide --sector y --estructura')
        return 2
    if args.red:
        return _metrados(args, tabla)
    if not args.inventario:
        print('ERROR: indique --inventario o --red')
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
