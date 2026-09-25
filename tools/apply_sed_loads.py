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


def _escribir_carga(obj, row: dict) -> None:
    """Escribe solo las ENTRADAS del modo de la carga (``mode_inp``).

    En PowerFactory, de P, Q, S y cos φ solo dos son datos; los otros se derivan. El
    DGS escribe las cargas en modo ``PC`` (P y cos φ). Asignar además Q y S, como antes,
    hacía que PowerFactory recalculara P desde la S anterior y el cambio se perdía en
    silencio.
    """
    import math

    p = float(row['plini_mw'])
    q = float(row['qlini_mvar'])
    s = float(row.get('slini_mva') or math.hypot(p, q))
    cos = float(row.get('coslini') or (p / s if s else 1.0))
    if int(getattr(obj, 'i_sym', 0) or 0) == 1:
        # Carga desequilibrada (así la escribe el DGS): los datos son P y Q POR FASE y
        # el total es derivado. Se escala cada fase conservando su reparto; si la carga
        # valía cero, se reparte a partes iguales entre las tres.
        fases = ('r', 's', 't')
        p_old = [float(getattr(obj, f'plini{f}', 0.0) or 0.0) for f in fases]
        q_old = [float(getattr(obj, f'qlini{f}', 0.0) or 0.0) for f in fases]
        sp, sq = sum(p_old), sum(q_old)
        p_new = [x * p / sp for x in p_old] if sp else [p / 3.0] * 3
        if sq:
            q_new = [x * q / sq for x in q_old]
        else:
            q_new = [q * (x / p) if p else q / 3.0 for x in p_new]
        for f, pv, qv in zip(fases, p_new, q_new):
            setattr(obj, f'plini{f}', pv)
            setattr(obj, f'qlini{f}', qv)
        return
    modo = str(getattr(obj, 'mode_inp', '') or 'PC').upper()
    if modo == 'PQ':
        obj.plini, obj.qlini = p, q
    elif modo == 'SC':
        obj.slini, obj.coslini = s, cos
    elif modo == 'SP':
        obj.slini, obj.plini = s, p
    elif modo == 'QC':
        obj.qlini, obj.coslini = q, cos
    else:                                   # 'PC' y cualquier otro: P y cos φ
        obj.plini, obj.coslini = p, cos
    # El signo de Q (inductiva/capacitiva) cuando el modo usa cos φ.
    if modo in ('PC', 'SC', 'QC') and hasattr(obj, 'pf_recap'):
        obj.pf_recap = 1 if q < 0 else 0


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
        # Nombre exacto primero: con varios proyectos importados del mismo alimentador,
        # el fragmento elegía el último en orden alfabético, no el que se importó.
        exactos = [p for p in proyectos if p.loc_name == args.project]
        proyectos = exactos or [p for p in proyectos if args.project in p.loc_name]
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
            _escribir_carga(obj, row)
            despues = {'plini': obj.plini, 'qlini': obj.qlini, 'coslini': obj.coslini}
            # Se relee: una asignación que PowerFactory recalcula no es un cambio.
            if abs(float(despues['plini']) - float(row['plini_mw'])) > 1e-6 + 1e-4 * abs(float(row['plini_mw'])):
                fallos.append(f"{code}: PowerFactory conserva P={despues['plini']:.6f} MW "
                              f"(pedido {float(row['plini_mw']):.6f})")
                continue
            aplicados.append({'sed_code': code, 'antes': antes, 'despues': despues})
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
