#!/usr/bin/env python
"""Comprueba que una selección de alimentadores pasa entera del TXT al DGS.

Cuenta en el TXT los tramos, las cargas y los equipos de maniobra de cada alimentador,
los compara con el modelo y con el DGS convertido, y deja ``fidelidad.json`` en la
salida. Sirve para revisar una entrega nueva antes de convertirla toda.

    python tools/fidelidad_seleccion.py --red RED.txt --cargas CARGA.txt --equipos BD.txt \\
        [--alimentadores A B ...] [--muestra 5] [--alias alias.json] [--crs EPSG:xxxx] \\
        [--out output/fidelidad]

Sin ``--alimentadores`` toma los ``--muestra`` primeros convertibles y el primero con
tramos en paralelo (doble circuito), que es donde se han perdido tramos otras veces.
Antes tenía fijadas las rutas de los TXT de Electro Dunas, cinco de sus alimentadores y
su CRS: ahora todo llega por argumentos (spec 009, RF-8; constitución P13).

Códigos de salida: 0 fiel, 2 hay desajustes o errores.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter
from pathlib import Path

from igea_dgs.batch import convert_selection, load_aliases
from igea_dgs.dataset import CymdistDataset
from igea_dgs.inventory import build_dataset_inventory
from igea_dgs.model import build_feeder_model

# La consola de Windows usa cp1252 y la ayuda lleva «→»: con la salida redirigida,
# ``--help`` moría con UnicodeEncodeError antes de escribir nada (2026-10-14).
for _flujo in (sys.stdout, sys.stderr):
    if isinstance(_flujo, io.TextIOWrapper):  # no lo es si alguien la sustituyó (pytest)
        _flujo.reconfigure(encoding='utf-8', errors='replace')


def extremos(sec: dict) -> tuple[str, str]:
    a, b = sec.get('FromNodeID', ''), sec.get('ToNodeID', '')
    return tuple(sorted((a, b)))


def elegir(ds, convertibles: list[dict], muestra: int) -> list[str]:
    """Los ``muestra`` primeros convertibles y el primero con doble circuito."""
    eleccion = [r['feeder'] for r in convertibles[:muestra]]
    for r in convertibles:
        ends = Counter(extremos(ds.sections[sid]) for sid in ds.feeders[r['network_id']])
        if any(c >= 2 for c in ends.values()):
            eleccion.append(r['feeder'])
            break
    return list(dict.fromkeys(eleccion))


def comparar_modelo(ds, eleccion: list[str], aliases) -> bool:
    """Tramos, cargas y equipos del TXT frente al modelo, alimentador por alimentador."""
    fiel = True
    for sel in eleccion:
        nid = ds.resolve_feeder(sel)
        txt_tramos = len(ds.feeders[nid])
        txt_cfg = sum(1 for sid in ds.feeders[nid] if sid in ds.line_configurations)
        txt_cargas = sum(1 for (sid, _) in ds.customer_loads if ds.section_owner.get(sid) == nid)
        txt_sw = sum(1 for r in ds.switch_settings if ds.section_owner.get(r.get('SectionID', '')) == nid)
        txt_secc = sum(1 for r in ds.sectionalizer_settings
                       if ds.section_owner.get(r.get('SectionID', '')) == nid)
        modelo = build_feeder_model(ds, nid, aliases=aliases, strict=True)
        ends = Counter(tuple(sorted((ln.from_node, ln.to_node))) for ln in modelo.lines)
        paralelos = sum(1 for c in ends.values() if c >= 2)
        igual = (len(modelo.lines) == txt_tramos == txt_cfg and len(modelo.loads) == txt_cargas
                 and len(modelo.devices) == txt_sw + txt_secc)
        fiel = fiel and igual
        print(f'{sel}: TXT tramos/config/cargas/sw+secc={txt_tramos}/{txt_cfg}/{txt_cargas}/{txt_sw}+{txt_secc} | '
              f'modelo líneas/cargas/SED/equipos={len(modelo.lines)}/{len(modelo.loads)}/'
              f'{len(modelo.seds)}/{len(modelo.devices)} paralelos={paralelos} {"IGUAL" if igual else "DISTINTO"}')
        for aviso in modelo.warnings:
            print('   AVISO:', aviso[:160])
        if modelo.unresolved_line_types:
            print('   sin resolver:', sorted(modelo.unresolved_line_types)[:12])
    return fiel


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Fidelidad TXT → modelo → DGS de una selección')
    p.add_argument('--red', required=True, type=Path)
    p.add_argument('--cargas', required=True, type=Path)
    p.add_argument('--equipos', required=True, type=Path)
    p.add_argument('--alimentadores', nargs='*', default=[], help='Sin ellos, una muestra')
    p.add_argument('--muestra', type=int, default=5, help='Convertibles a tomar sin --alimentadores')
    p.add_argument('--alias', type=Path, help='JSON de alias de tipos de línea')
    p.add_argument('--crs', default='', help='CRS de origen; sin él, sin georreferenciación')
    p.add_argument('--out', type=Path, default=Path('output') / 'fidelidad')
    args = p.parse_args(argv)

    print('Leyendo los TXT…')
    ds = CymdistDataset.from_files(args.red, args.cargas, args.equipos)
    aliases = load_aliases(args.alias)
    inv = build_dataset_inventory(ds)
    integ = inv['integrity']
    print('Inventario:', inv['totals'])
    print(f"Integridad: {integ['errors']} errores, {integ['warnings']} avisos")
    convertibles = [r for r in inv['feeders'] if r['convertible']]
    eleccion = args.alimentadores or elegir(ds, convertibles, args.muestra)
    print('Selección:', ', '.join(eleccion))

    print('\n=== TXT frente al modelo ===')
    modelo_fiel = comparar_modelo(ds, eleccion, aliases)

    print('\n=== Conversión a DGS ===')
    args.out.mkdir(parents=True, exist_ok=True)
    # Sin CRS no se georreferencia: el motor no supone el de ninguna empresa.
    geo = {'include_geography': True, 'source_crs': args.crs} if args.crs else {'include_geography': False}
    manifest = convert_selection(ds, eleccion, args.out, aliases=aliases, strict=True, **geo)
    dgs_fiel = True
    for item in manifest['feeders']:
        c = item.get('counts') or {}
        lineas = c.get('source_lines') == c.get('dgs_lines')
        cargas = c.get('source_loads') == c.get('dgs_loads')
        dgs_fiel = dgs_fiel and item['status'] == 'ok' and lineas and cargas
        print(f"  {item['feeder']}: {item['status']} errores={item.get('errors_total')} "
              f'líneas={"=" if lineas else "≠"} cargas={"=" if cargas else "≠"} {(item.get("error") or "")[:200]}')

    ok = modelo_fiel and dgs_fiel and manifest['summary']['failed'] == 0
    (args.out / 'fidelidad.json').write_text(json.dumps({
        'seleccion': eleccion, 'inventario': inv['totals'],
        'integridad': {'errores': integ['errors'], 'avisos': integ['warnings']},
        'modelo_fiel': modelo_fiel, 'dgs_fiel': dgs_fiel, 'resumen': manifest['summary'],
    }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('\nRESULTADO:', 'FIEL' if ok else 'HAY DESAJUSTES O ERRORES')
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
