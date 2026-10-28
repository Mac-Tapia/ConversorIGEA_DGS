#!/usr/bin/env python
"""Escenarios del gemelo digital en una copia del proyecto de DIgSILENT (spec 024, T10).

Copia el proyecto en su carpeta, activa el caso pedido y, para cada escenario (demanda
escalada con el ``ComLdf`` y tramos fuera de servicio), ejecuta el flujo y devuelve sus
resultados y el grafo eléctrico (nodos con su tensión nominal y su demanda; líneas,
acopladores y transformadores con R, X y corriente nominal), que es lo que la PINN
necesita para la pérdida física (RF-11, RF-40). Cada cambio se devuelve a su valor tras
su escenario y la copia se borra al terminar: el proyecto del operador no se toca.

    python tools/escenarios_pf.py --plan plan.json --output-json escenarios.json

El plan: ``{"project", "folder", "feeders", "case", "escenarios": [{"factor_carga",
"tramos_abiertos"}], "solo_tramos": false, "limite_s": 600, "native_action_context"}``.
Con ``solo_tramos`` devuelve los tramos de los alimentadores y el grafo base, sin simular.

Códigos de salida: 0 hecho, 2 sin proyecto o sin caso, 1 error inesperado, 3 sin API.
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

from cargas_pf import activar_proyecto, clave_pf, flujo_de_carga
from digital_twin_snapshot_pf import CASOS, _caso, _red, grafo, resultados

from igea_dgs.digital_twin.native_snapshot import componentes
from igea_dgs.native_action import native_action_block_report


def ejecutar(app, plan: dict, cancelado=lambda: False) -> tuple[dict, int]:
    """Los escenarios en una copia del proyecto. Devuelve (informe, código)."""
    informe = {'project': plan['project'], 'case': plan.get('case'), 'escenarios': [], 'avisos': []}
    original = activar_proyecto(app, plan['project'], plan.get('folder'))
    if original is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r}"}, 2
    feeders = list(plan.get('feeders') or [])
    nombre_copia = f"{original.loc_name}_gemelo_{int(time.time())}"
    # DIgSILENT no copia el proyecto activo: AddCopy devolvía None (IN111–TA225, 2026-10-22).
    original.Deactivate()
    copia = original.GetParent().AddCopy(original, nombre_copia)
    if copia is None:
        return {**informe, 'error': 'DIgSILENT no copió el proyecto'}, 2
    copia.Activate()
    try:
        nombre_caso = CASOS.get(plan.get('case') or '', plan.get('case'))
        if nombre_caso:
            caso = _caso(app, nombre_caso)
            if caso is None:
                return {**informe, 'error': f'el proyecto no tiene el caso «{nombre_caso}»'}, 2
            caso.Activate()
        raiz = clave_pf(copia)
        elms = {f.loc_name: f for f in copia.GetContents('*.ElmFeeder', 1)}
        lineas = {ln.loc_name: ln for f in feeders if f in elms for ln in elms[f].GetObjs('ElmLne')}
        if plan.get('solo_tramos'):
            informe['tramos'] = sorted(lineas)
            informe['grafo'] = grafo(app, copia, raiz, feeders)
            return informe, 0
        ldf = app.GetFromStudyCase('ComLdf')
        escala_original = getattr(ldf, 'scLoadFac', 100.0)
        inicio, limite = time.monotonic(), float(plan.get('limite_s') or 600)
        for e in plan.get('escenarios') or []:
            if cancelado() or time.monotonic() - inicio > limite:
                informe['avisos'].append('presupuesto de tiempo agotado o cancelado: se paró antes')
                break
            abiertos = [lineas[t] for t in e.get('tramos_abiertos') or [] if t in lineas]
            antes = [(ln, getattr(ln, 'outserv', 0)) for ln in abiertos]
            try:
                ldf.scLoadFac = float(escala_original) * float(e['factor_carga'])
                for ln in abiertos:
                    ln.outserv = 1
                flujo = flujo_de_carga(app)
                fila = {'escenario': e, 'converge': flujo['converged']}
                if flujo['converged']:
                    barras, tramos, frontera, info = _red(app, raiz)
                    fila['lectura'] = {
                        'project': plan['project'], 'folder': plan.get('folder'), 'feeders': feeders,
                        'reopen_verified': True,
                        'topologia': {'componentes': componentes(barras, tramos), 'frontera': frontera,
                                      'barras': info, 'grafo': grafo(app, copia, raiz, feeders,
                                                                     float(e['factor_carga']))},
                        'flujo': resultados(app, copia, raiz, feeders)}
                informe['escenarios'].append(fila)
            finally:
                for ln, v in antes:
                    ln.outserv = v
                ldf.scLoadFac = escala_original
        return informe, 0
    finally:
        copia.Deactivate()
        copia.Delete()
        activar_proyecto(app, plan['project'], plan.get('folder'))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Escenarios del gemelo digital en una copia del proyecto '
                                            'de DIgSILENT, borrada al terminar (spec 024, T10)')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    p.add_argument('--cancel-file', help='Si aparece, termina el escenario en curso y para')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    salida = Path(args.output_json)
    blocked = native_action_block_report(plan, 'gemelo_escenarios')
    if blocked:
        salida.write_text(json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    from igea_dgs.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('escenarios_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    cancel = Path(args.cancel_file) if args.cancel_file else None
    try:
        informe, codigo = ejecutar(app, plan, lambda: bool(cancel and cancel.exists()))
    except Exception as exc:  # noqa: BLE001 - el informe queda siempre escrito (008:RF-17)
        informe, codigo = {'project': plan.get('project'), 'error': repr(exc),
                           'traza': traceback.format_exc()}, 1
    salida.write_text(json.dumps(informe, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Escenarios de {plan.get('project')}: {len(informe.get('escenarios') or [])}, código {codigo}")
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
