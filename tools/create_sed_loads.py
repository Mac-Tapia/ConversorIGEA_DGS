#!/usr/bin/env python
"""Crea SED nuevas en un proyecto de PowerFactory, con su derivación aérea.

Lo que hace por cada SED del plan:

1. Crea la **barra nueva** (``ElmTerm``) en las coordenadas indicadas — GPS si el plan
   las trae en WGS84, y siempre con el nombre ``NODE_<SED>``.
2. La **conecta al nodo más cercano** ya existente con una **línea aérea** nueva
   (``ElmLne``, ``inAir=1``), cuya longitud es la distancia real entre los dos puntos y
   cuyo tipo es el conductor que el plan eligió. Si el ``TypLne`` no existe en el
   proyecto, se crea desde los parámetros del plan.
3. Crea la **SED** (``ElmSubstat``) con sus dos barras internas (MT y BT), su
   ``TypTr2``/``ElmTr2``, el ``ElmCoup`` de enganche y el ``ElmLod`` con la carga.
4. Cablea los **cubículos** (``StaCubic``) de cada extremo.

Se ejecuta en un **proceso aparte** y con el Python que exige la API de PowerFactory
(``powerfactory.pyd`` está atado a una versión de CPython; PF 2024 → 3.12). Por eso
recibe el plan como JSON y no importa nada de ``igea_dgs``: el motor del conversor nunca
enlaza con la API propietaria.

Uso:

    python tools/create_sed_loads.py --plan plan_creacion.json \\
        --project 20260923_IGEA_PA217 [--dry-run] [--run-load-flow] \\
        [--output-json resultado.json]

Códigos de salida: 0 creado, 2 plan inaplicable o algo no se pudo crear,
3 API de PowerFactory no disponible.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Crea SED y su derivación aérea en PowerFactory')
    p.add_argument('--plan', required=True, help='JSON de loads_create.create_plan_to_payload')
    p.add_argument('--project', help='Nombre (o fragmento) del proyecto de PowerFactory')
    p.add_argument('--dry-run', action='store_true', help='No escribe: informa qué haría')
    p.add_argument('--run-load-flow', action='store_true', help='Ejecuta ComLdf al terminar')
    p.add_argument('--output-json', help='Informe del resultado')
    return p


def _activate(app, fragment: str | None):
    """Activa el proyecto y su caso de estudio.

    Sin caso de estudio activo ``GetCalcRelevantObjects`` devuelve 0 elementos, y
    parecería que el proyecto está vacío.
    """
    user = app.GetCurrentUser()
    projects = list(user.GetContents('*.IntPrj'))
    if fragment:
        # Nombre exacto primero; el fragmento solo si no hay coincidencia exacta.
        exactos = [p for p in projects if p.loc_name == fragment]
        projects = exactos or [p for p in projects if fragment in p.loc_name]
    if not projects:
        raise SystemExit(f'ERROR: no se encontró proyecto que contenga {fragment!r}.')
    project = sorted(projects, key=lambda p: p.loc_name)[-1]
    project.Activate()
    folder = app.GetProjectFolder('study')
    cases = list(folder.GetContents('*.IntCase')) if folder else []
    if cases:
        cases[0].Activate()
    return project


def _grid_of(app):
    """Red donde crear los objetos: la que ya tiene las barras del alimentador."""
    nets = app.GetCalcRelevantObjects('*.ElmNet')
    if not nets:
        raise SystemExit('ERROR: el proyecto activo no tiene ninguna ElmNet.')
    # «Summary Grid» es la carpeta resumen de PowerFactory, no la red del alimentador.
    real = [n for n in nets if 'summary' not in n.loc_name.lower()]
    return (real or nets)[0]


def _terminal_type(typ_folder, code: str, spec: dict, nominal_kv: float):
    """Devuelve el TypLne del conductor, creándolo si el proyecto no lo tiene."""
    existing = [t for t in typ_folder.GetContents('*.TypLne') if t.loc_name == code]
    if existing:
        return existing[0], False
    typ = typ_folder.CreateObject('TypLne', code)
    typ.uline = nominal_kv
    typ.sline = spec['conductor_ampacity_a'] / 1000.0
    typ.InomAir = spec['conductor_ampacity_a'] / 1000.0
    typ.cohl_ = 1                      # aéreo
    typ.nlnph = 3
    typ.nneutral = 0
    typ.frnom = 60
    # R/X no viajan en el plan: se dejan a 0 y se avisa. El conversor los tomaría del
    # catálogo BD_Equipo; aquí solo se crea el tipo si no existía ya en el proyecto.
    return typ, True


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    to_create = plan.get('create') or []
    if plan.get('row_errors'):
        print(f'El plan tiene {len(plan["row_errors"])} fila(s) con error: no se crea nada.')
        for err in plan['row_errors'][:10]:
            print('  -', err)
        return 2
    if not to_create:
        print('El plan no contiene SED que crear.')
        return 2

    try:
        import powerfactory
    except ImportError as exc:
        print(f'ERROR: API de PowerFactory no disponible ({exc}). '
              'Use el Python de PowerFactory (PF 2024 → 3.12) con PYTHONPATH al API.')
        return 3
    try:
        app = powerfactory.GetApplicationExt()
    except Exception as exc:
        print(f'ERROR: no se pudo conectar a PowerFactory: {exc}')
        return 3

    project = _activate(app, args.project)
    print(f'proyecto: {project.loc_name}')
    print(f'caso activo: {app.GetActiveStudyCase()}')

    grid = _grid_of(app)
    print(f'red: {grid.loc_name}')
    nominal_kv = float(plan.get('nominal_kv') or 0) or 22.9
    lv_kv = float(plan.get('lv_kv') or 0.22)

    terminals = {t.loc_name: t for t in app.GetCalcRelevantObjects('*.ElmTerm')}
    existing_seds = {s.loc_name for s in app.GetCalcRelevantObjects('*.ElmSubstat')}
    typ_folder = app.GetProjectFolder('equip') or project

    created, failed, skipped, types_made = [], [], [], []

    for spec in to_create:
        code = spec['sed_code']
        if code in existing_seds:
            skipped.append(f'{code}: ya existe un ElmSubstat con ese nombre')
            continue
        anchor = terminals.get(spec['connect_to_node'])
        if anchor is None:
            failed.append(
                f'{code}: la barra {spec["connect_to_node"]!r} no está en el proyecto'
            )
            continue

        if args.dry_run:
            created.append({
                'sed_code': code, 'dry_run': True,
                'connect_to_node': spec['connect_to_node'],
                'distance_m': spec['distance_m'],
                'conductor': spec['conductor_code'],
            })
            continue

        try:
            # 1) Barra nueva en el punto indicado.
            term = grid.CreateObject('ElmTerm', spec['new_node_id'])
            term.uknom = nominal_kv
            term.iUsage = 1
            term.outserv = 0
            for attr, key in (('GPSlat', 'gps_lat'), ('GPSlon', 'gps_lon')):
                if spec.get(key) is not None:
                    try:
                        setattr(term, attr, float(spec[key]))
                    except Exception:
                        pass

            # 2) Derivación aérea desde el nodo más cercano.
            typ, made = _terminal_type(typ_folder, spec['conductor_code'], spec, nominal_kv)
            if made:
                types_made.append(spec['conductor_code'])
            line = grid.CreateObject('ElmLne', spec['new_section_id'])
            line.typ_id = typ
            line.dline = max(float(spec['length_km']), 1e-6)
            line.nlnum = 1
            line.inAir = 1
            cub_a = anchor.CreateObject('StaCubic', f'Cub1_{spec["new_section_id"]}')
            cub_a.obj_id = line
            cub_a.obj_bus = 0
            cub_b = term.CreateObject('StaCubic', f'Cub2_{spec["new_section_id"]}')
            cub_b.obj_id = line
            cub_b.obj_bus = 1

            # 3) SED con sus barras internas, transformador, acoplador y carga.
            substat = grid.CreateObject('ElmSubstat', code)
            substat.sShort = 'T'
            substat.sType = f'{spec["installed_kva"]:g} kVA'
            mt = substat.CreateObject('ElmTerm', code)
            mt.uknom = nominal_kv
            mt.iUsage = 0
            bt = substat.CreateObject('ElmTerm', f'{code}_BT')
            bt.uknom = lv_kv
            bt.iUsage = 0

            tr_type = typ_folder.CreateObject('TypTr2', f'TR_{spec["installed_kva"]:g}kVA_{code}')
            tr_type.nt2ph = 3
            tr_type.strn = float(spec['strn_mva'])
            tr_type.frnom = 60
            tr_type.utrn_h = nominal_kv
            tr_type.utrn_l = lv_kv
            tr_type.uktr = 4.0
            tr_type.pcutr = max(float(spec['strn_mva']) * 10.0, 0.1)
            tr_type.tr2cn_h = 'D'
            tr_type.tr2cn_l = 'YN'
            tr_type.nt2ag = 5

            tr = substat.CreateObject('ElmTr2', f'TR_{code}')
            tr.typ_id = tr_type
            tr.ntnum = 1
            tr.outserv = 0
            cub_h = mt.CreateObject('StaCubic', f'Cub1_TR_{code}')
            cub_h.obj_id = tr
            cub_h.obj_bus = 0
            cub_l = bt.CreateObject('StaCubic', f'Cub2_TR_{code}')
            cub_l.obj_id = tr
            cub_l.obj_bus = 1

            coup = substat.CreateObject('ElmCoup', f'SW_{code}')
            coup.on_off = 1
            coup.aUsage = 'cbk'
            coup.nphase = 3
            cub_c1 = term.CreateObject('StaCubic', f'Cub1_SW_{code}')
            cub_c1.obj_id = coup
            cub_c1.obj_bus = 0
            cub_c2 = mt.CreateObject('StaCubic', f'Cub2_SW_{code}')
            cub_c2.obj_id = coup
            cub_c2.obj_bus = 1

            load = substat.CreateObject('ElmLod', code)
            load.mode_inp = 'PC'
            load.plini = float(spec['plini_mw'])
            load.qlini = float(spec['qlini_mvar'])
            load.coslini = float(spec['coslini']) or 0.95
            load.slini = float(spec['slini_mva'])
            load.outserv = 0
            cub_load = bt.CreateObject('StaCubic', f'Cub_{code}')
            cub_load.obj_id = load
            cub_load.obj_bus = 0

            created.append({
                'sed_code': code,
                'new_node': spec['new_node_id'],
                'connect_to_node': spec['connect_to_node'],
                'distance_m': spec['distance_m'],
                'conductor': spec['conductor_code'],
                'length_km': spec['length_km'],
                'installed_kva': spec['installed_kva'],
                'plini_mw': load.plini,
                'qlini_mvar': load.qlini,
            })
            print(
                f'  + {code}: barra {spec["new_node_id"]} → {spec["connect_to_node"]} '
                f'({spec["distance_m"]:.1f} m, {spec["conductor_code"]})'
            )
        except Exception as exc:
            failed.append(f'{code}: {type(exc).__name__}: {exc}')

    print(f'\nSED creadas   : {len(created)}{" (simulación)" if args.dry_run else ""}')
    print(f'SED omitidas  : {len(skipped)}')
    for s in skipped[:10]:
        print('  -', s)
    print(f'Fallos        : {len(failed)}')
    for f in failed[:10]:
        print('  -', f)
    if types_made:
        print(
            f'TypLne creados sin R/X: {", ".join(sorted(set(types_made)))}. '
            'Revíselos en PowerFactory: el plan no transporta impedancias.'
        )

    result = {
        'project': project.loc_name,
        'feeder': plan.get('feeder'),
        'dry_run': bool(args.dry_run),
        'created': created,
        'skipped': skipped,
        'failed': failed,
        'line_types_created': sorted(set(types_made)),
    }

    if args.run_load_flow and not args.dry_run:
        ldf = app.GetFromStudyCase('ComLdf')
        ret = ldf.Execute()
        valid = app.IsLdfValid()
        result['load_flow'] = {
            'return_code': ret, 'ldf_valid': valid,
            'converged': ret == 0 and bool(valid),
        }
        print(f'\nflujo tras crear: ComLdf -> {ret}  IsLdfValid -> {valid}')
        if ret == 0 and valid:
            voltages = []
            for bus in app.GetCalcRelevantObjects('*.ElmTerm'):
                try:
                    if bus.HasResults():
                        voltages.append((bus.GetAttribute('m:u'), bus.loc_name))
                except Exception:
                    pass
            if voltages:
                voltages.sort()
                result['load_flow']['vm_min'] = voltages[0][0]
                result['load_flow']['vm_min_bus'] = voltages[0][1]
                result['load_flow']['vm_max'] = voltages[-1][0]
                print(
                    f'  tensión min {voltages[0][0]:.4f} p.u. en {voltages[0][1]}  '
                    f'max {voltages[-1][0]:.4f}'
                )
                # Las barras nuevas deben quedar energizadas, no a 0,0 p.u.
                nuevas = {c['new_node'] for c in created if c.get('new_node')}
                muertas = [n for v, n in voltages if n in nuevas and v <= 0.01]
                result['load_flow']['new_buses_unenergised'] = muertas
                if muertas:
                    print(f'  AVISO: barras nuevas sin energizar: {muertas}')

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8',
        )
        print(f'\nInforme: {args.output_json}')

    return 0 if created and not failed else 2


if __name__ == '__main__':
    raise SystemExit(main())
