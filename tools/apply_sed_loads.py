#!/usr/bin/env python
"""Aplica un plan de actualización de cargas SED sobre un proyecto de PowerFactory.

Se ejecuta en un **proceso aparte** y con el Python que exige la API de PowerFactory
(``powerfactory.pyd`` es una extensión binaria atada a una versión de CPython). Por eso
recibe el plan como JSON y no importa nada del paquete ``igea_dgs``: así el motor del
conversor nunca enlaza con la API propietaria.

Uso:

    python tools/apply_sed_loads.py --plan plan.json --project 20260923_IGEA_PA217 \\
        [--dry-run] [--run-load-flow] [--output-json resultado.json]

La localización de cada carga es por ``loc_name`` del ``ElmLod``, que es el código de
SED: los FID cambian en cada conversión y no sirven como clave estable.

Códigos de salida: 0 aplicado, 2 plan inaplicable o SED no encontradas,
3 API de PowerFactory no disponible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Actualiza cargas de SED en PowerFactory')
    p.add_argument('--plan', required=True, help='JSON del plan (igea_dgs.loads.plan_to_payload)')
    p.add_argument('--project', help='Nombre (o fragmento) del proyecto de PowerFactory')
    p.add_argument('--dry-run', action='store_true', help='No escribe: solo informa qué haría')
    p.add_argument('--run-load-flow', action='store_true', help='Ejecuta ComLdf tras aplicar')
    p.add_argument('--output-json', help='Informe del resultado')
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    updates = plan.get('updates') or []
    if not updates:
        print('El plan no contiene actualizaciones.')
        return 2
    if plan.get('row_errors'):
        print(f'El plan tiene {len(plan["row_errors"])} fila(s) con error: no se aplica nada.')
        for err in plan['row_errors'][:10]:
            print('  -', err)
        return 2

    try:
        import powerfactory
    except ImportError as exc:
        print(f'ERROR: API de PowerFactory no disponible ({exc}). '
              'Use el Python de PowerFactory (PF 2024 → 3.12) y PYTHONPATH al API.')
        return 3
    try:
        app = powerfactory.GetApplicationExt()
    except Exception as exc:
        print(f'ERROR: no se pudo conectar a PowerFactory: {exc}')
        return 3

    user = app.GetCurrentUser()
    proyectos = list(user.GetContents('*.IntPrj'))
    if args.project:
        proyectos = [p for p in proyectos if args.project in p.loc_name]
    if not proyectos:
        print(f'ERROR: no se encontró proyecto que contenga {args.project!r}.')
        return 2
    proyecto = sorted(proyectos, key=lambda p: p.loc_name)[-1]
    proyecto.Activate()
    # Sin caso de estudio activo, GetCalcRelevantObjects devuelve 0 elementos.
    carpeta = app.GetProjectFolder('study')
    casos = list(carpeta.GetContents('*.IntCase')) if carpeta else []
    if casos:
        casos[0].Activate()
    print(f'proyecto: {proyecto.loc_name}')
    print(f'caso activo: {app.GetActiveStudyCase()}')

    cargas = {}
    for obj in app.GetCalcRelevantObjects('*.ElmLod'):
        cargas.setdefault(obj.loc_name, []).append(obj)

    aplicados, no_encontrados, ambiguos, fallos = [], [], [], []
    for row in updates:
        code = row['sed_code']
        candidatos = cargas.get(code, [])
        if not candidatos:
            no_encontrados.append(code)
            continue
        if len(candidatos) > 1:
            # No se adivina: dos ElmLod con el mismo loc_name es ambigüedad real.
            ambiguos.append(code)
            continue
        obj = candidatos[0]
        antes = {'plini': obj.plini, 'qlini': obj.qlini, 'coslini': obj.coslini}
        if args.dry_run:
            aplicados.append({'sed_code': code, 'antes': antes, 'despues': None, 'dry_run': True})
            continue
        try:
            obj.plini = float(row['plini_mw'])
            obj.qlini = float(row['qlini_mvar'])
            if row.get('coslini'):
                obj.coslini = float(row['coslini'])
            if row.get('slini_mva') is not None:
                obj.slini = float(row['slini_mva'])
            aplicados.append({
                'sed_code': code, 'antes': antes,
                'despues': {'plini': obj.plini, 'qlini': obj.qlini, 'coslini': obj.coslini},
            })
        except Exception as exc:
            fallos.append(f'{code}: {exc}')

    print(f'\nSED actualizadas : {len(aplicados)}{" (simulación)" if args.dry_run else ""}')
    print(f'SED no halladas  : {len(no_encontrados)}')
    if no_encontrados:
        print('  ', ', '.join(no_encontrados[:12]))
    print(f'SED ambiguas     : {len(ambiguos)}')
    if ambiguos:
        print('  ', ', '.join(ambiguos[:12]))
    print(f'Fallos al escribir: {len(fallos)}')
    for f in fallos[:10]:
        print('  -', f)

    resultado = {
        'project': proyecto.loc_name,
        'feeder': plan.get('feeder'),
        'dry_run': bool(args.dry_run),
        'applied': len(aplicados),
        'not_found': no_encontrados,
        'ambiguous': ambiguos,
        'write_errors': fallos,
        'details': aplicados,
    }

    if args.run_load_flow and not args.dry_run:
        ldf = app.GetFromStudyCase('ComLdf')
        ret = ldf.Execute()
        valido = app.IsLdfValid()
        resultado['load_flow'] = {'return_code': ret, 'ldf_valid': valido, 'converged': ret == 0 and bool(valido)}
        print(f'\nflujo tras actualizar: ComLdf -> {ret}  IsLdfValid -> {valido}')
        if ret == 0 and valido:
            tensiones = []
            for bus in app.GetCalcRelevantObjects('*.ElmTerm'):
                try:
                    if bus.HasResults():
                        tensiones.append(bus.GetAttribute('m:u'))
                except Exception:
                    pass
            if tensiones:
                resultado['load_flow']['vm_min'] = min(tensiones)
                resultado['load_flow']['vm_max'] = max(tensiones)
                print(f'  tensión min {min(tensiones):.4f}  max {max(tensiones):.4f} p.u.')

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(resultado, indent=2, ensure_ascii=False) + '\n', encoding='utf-8',
        )
        print(f'\nInforme: {args.output_json}')

    if no_encontrados or ambiguos or fallos:
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
