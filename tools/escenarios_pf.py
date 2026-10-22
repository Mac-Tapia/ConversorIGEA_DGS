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

from cargas_pf import _cerrado, activar_proyecto, clave_pf, flujo_de_carga
from digital_twin_snapshot_pf import CASOS, _caso, _red, resultados
from estudios_pf import _num

from igea_dgs.digital_twin.native_snapshot import componentes, identidad_nativa
from igea_dgs.digital_twin.oraculo import VERSION_GRAFO
from igea_dgs.native_action import native_action_block_report


def _id(obj, raiz: str) -> str:
    return identidad_nativa(obj.GetClassName(), clave_pf(obj), raiz)


def _barra(cub, raiz: str) -> str | None:
    barra = getattr(cub, 'cterm', None) or (cub.GetParent() if cub is not None else None)
    return _id(barra, raiz) if barra is not None else None


def grafo(app, proyecto, raiz: str, feeders: list[str], factor: float = 1.0) -> dict:
    """Nodos y ramas con sus parámetros en unidades físicas (kV, MW, Mvar, Ω, kA)."""
    nodos = {}
    for b in app.GetCalcRelevantObjects('*.ElmTerm'):
        nodos[_id(b, raiz)] = {'kv': _num(b, 'uknom'), 'p_mw': 0.0, 'q_mvar': 0.0, 'fuente': False}
    for c in app.GetCalcRelevantObjects('*.ElmLod'):
        if int(getattr(c, 'outserv', 0) or 0):
            continue
        n = _barra(getattr(c, 'bus1', None), raiz)
        if n in nodos:
            escala = (_num(c, 'scale0') or 1.0) * factor
            nodos[n]['p_mw'] += (_num(c, 'plini') or 0.0) * escala
            nodos[n]['q_mvar'] += (_num(c, 'qlini') or 0.0) * escala
    for sh in app.GetCalcRelevantObjects('*.ElmShnt'):
        n = _barra(getattr(sh, 'bus1', None), raiz)
        if n in nodos and not int(getattr(sh, 'outserv', 0) or 0):
            q = _num(sh, 'qtotn') or (_num(sh, 'qcapn') or 0.0) * (_num(sh, 'ncapa') or 1.0)
            nodos[n]['q_mvar'] -= q
    redes = list(app.GetCalcRelevantObjects('*.ElmXnet'))
    fuentes = [_barra(getattr(x, 'bus1', None), raiz) for x in redes]
    # La consigna de tensión de cada red externa: IN111 está a 1,02 p.u. y TA225 a 1,00, y sin
    # ella el oráculo tenía que adivinar el nivel de toda la red (024, 2026-10-22).
    for x, f in zip(redes, fuentes, strict=True):
        if f in nodos and (u := _num(x, 'usetp')) is not None:
            nodos[f]['v_pu'] = u
    if not any(fuentes):
        # Sin red externa (el doble de pruebas), la fuente es la barra de cada cabecera.
        elms = {f.loc_name: f for f in proyecto.GetContents('*.ElmFeeder', 1)}
        fuentes = [_barra(getattr(elms[f], 'obj_id', None), raiz) for f in feeders if f in elms]
    for f in fuentes:
        if f in nodos:
            nodos[f]['fuente'] = True
    ramas = []
    for ln in app.GetCalcRelevantObjects('*.ElmLne'):
        tipo = getattr(ln, 'typ_id', None)
        cubs = [c for c in (getattr(ln, 'bus1', None), getattr(ln, 'bus2', None)) if c is not None]
        if tipo is None or len(cubs) != 2:
            continue
        n = max(int(getattr(ln, 'nlnum', 1) or 1), 1)
        largo = _num(ln, 'dline') or 0.0
        ramas.append({'id': _id(ln, raiz), 'clase': 'ElmLne', 'desde': _barra(cubs[0], raiz),
                      'hasta': _barra(cubs[1], raiz), 'cerrada': _cerrado(ln, cubs),
                      'r_ohm': (_num(tipo, 'rline') or 0.0) * largo / n,
                      'x_ohm': (_num(tipo, 'xline') or 0.0) * largo / n,
                      'inom_ka': (_num(tipo, 'sline') or 0.0) * n})
    # Los acopladores (interruptores y seccionadores de barra): desde la spec 022 la cabecera
    # de cada alimentador es un interruptor en su SET. Sin ellos, de 2470 nodos de IN111–TA225
    # solo 91 quedaban unidos a una fuente (2026-10-22).
    for cp in app.GetCalcRelevantObjects('*.ElmCoup'):
        cubs = [c for c in (getattr(cp, 'bus1', None), getattr(cp, 'bus2', None)) if c is not None]
        if len(cubs) == 2:
            ramas.append({'id': _id(cp, raiz), 'clase': 'ElmCoup', 'desde': _barra(cubs[0], raiz),
                          'hasta': _barra(cubs[1], raiz), 'cerrada': _cerrado(cp, cubs),
                          'r_ohm': 0.0, 'x_ohm': 0.0, 'inom_ka': 0.0})
    for tr in app.GetCalcRelevantObjects('*.ElmTr2'):
        tipo = getattr(tr, 'typ_id', None)
        hv, lv = getattr(tr, 'bushv', None), getattr(tr, 'buslv', None)
        if tipo is None or hv is None or lv is None:
            continue
        s, uh = _num(tipo, 'strn') or 0.0, _num(tipo, 'utrn_h') or 0.0
        z_base = uh * uh / s if s else 0.0
        ramas.append({'id': _id(tr, raiz), 'clase': 'ElmTr2', 'desde': _barra(hv, raiz),
                      'hasta': _barra(lv, raiz), 'cerrada': not int(getattr(tr, 'outserv', 0) or 0),
                      'r_ohm': (_num(tipo, 'pcutr') or 0.0) / 1000 / s * z_base if s else 0.0,
                      'x_ohm': (_num(tipo, 'uktr') or 0.0) / 100 * z_base,
                      'inom_ka': s / (3 ** 0.5 * uh) if uh else 0.0,
                      'relacion': uh / (_num(tipo, 'utrn_l') or uh)})
    return {'version': VERSION_GRAFO, 'nodos': nodos, 'ramas': ramas}


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
