#!/usr/bin/env python
"""Lee el proyecto de DIgSILENT después de una acción, para el gemelo digital (spec 024).

Solo lectura: desactiva y vuelve a activar el proyecto, para que DIgSILENT relea lo que
quedó guardado y no lo que tenía en memoria el proceso que escribió (RF-27); activa el
caso pedido, ejecuta el flujo con lo activo y devuelve tensiones, cargabilidad de líneas y
transformadores, cabeceras y pérdidas, islas, tramos abiertos y la huella del trazado de
los elementos pedidos. No crea, borra ni modifica nada.

    python tools/digital_twin_snapshot_pf.py --plan plan.json --output-json lectura.json

El plan: ``{"project", "folder", "feeders": [...] (en su orden), "case": "con_proyecto",
"variaciones_esperadas": [...], "huellas_gps_de": [...], "native_action_context"}``.

Códigos de salida: 0 leído y convergido, 2 sin proyecto, sin caso o sin converger,
1 error inesperado, 3 sin API.
"""
from __future__ import annotations

import argparse
import json
import math
import traceback
from pathlib import Path

from cargas_pf import _cerrado, activar_proyecto, clave_pf, flujo_de_carga, trazado_de
from estudios_pf import _num, medida

from igea_dgs.digital_twin.native_snapshot import (
    componentes,
    huella_gps,
    identidad_nativa,
)
from igea_dgs.digital_twin.oraculo import VERSION_GRAFO
from igea_dgs.native_action import native_action_block_report

#: Caso del episodio → nombre del caso de estudio que deja la spec 011.
CASOS = {'caso_base': 'Caso base', 'sin_proyecto': 'Sin proyecto', 'con_proyecto': 'Con proyecto'}


def _caso(app, nombre: str):
    carpeta = app.GetProjectFolder('study')
    return next((c for c in (carpeta.GetContents('*.IntCase') if carpeta else [])
                 if c.loc_name == nombre), None)


def _version(app) -> str | None:
    try:
        return str(app.GetVersion())
    except Exception:  # noqa: BLE001 - la versión es opcional en el episodio
        return None


def _estados(app, nombres: set[str]) -> dict[str, dict]:
    """En servicio y cerrado de los interruptores, acopladores y líneas pedidos por nombre.

    Desde la spec 021 los seccionadores y fusibles son ``StaSwitch`` dentro de un cubículo:
    no son tramos, así que su estado se pide aparte (la frontera de IN111–TA225 se corrige
    cerrando un seccionador).
    """
    out = {}
    if not nombres:
        return out
    for clase in ('StaSwitch', 'ElmCoup', 'ElmLne'):
        for o in app.GetCalcRelevantObjects(f'*.{clase}'):
            if o.loc_name in nombres:
                en_servicio = not int(getattr(o, 'outserv', 0) or 0)
                cerrado = en_servicio and int(getattr(o, 'on_off', 1) or 0) != 0
                out[o.loc_name] = {'clase': clase, 'en_servicio': en_servicio, 'cerrado': cerrado}
    return out


def _red(app, raiz: str) -> tuple[list[str], list[tuple[str, str, bool]], list[str], dict]:
    """Barras, tramos (líneas y acopladores con su estado), tramos abiertos y, por barra,
    su nombre y su tensión nominal."""
    barras = list(app.GetCalcRelevantObjects('*.ElmTerm'))
    ids = [identidad_nativa('ElmTerm', clave_pf(b), raiz) for b in barras]
    info = {i: {'nombre': b.loc_name, 'kv': _num(b, 'uknom')} for i, b in zip(ids, barras, strict=True)}
    extremos: dict[str, list] = {}
    objetos = {}
    for barra, ident in zip(barras, ids, strict=True):
        for cub in barra.GetContents('*.StaCubic') or []:
            o = getattr(cub, 'obj_id', None)
            if o is None or o.GetClassName() not in ('ElmLne', 'ElmCoup'):
                continue
            clave = clave_pf(o)
            objetos[clave] = o
            extremos.setdefault(clave, []).append((ident, cub))
    tramos, abiertos = [], []
    for clave, lados in sorted(extremos.items()):
        if len(lados) != 2:
            continue
        o = objetos[clave]
        cerrado = _cerrado(o, [c for _, c in lados])
        tramos.append((lados[0][0], lados[1][0], cerrado))
        if not cerrado:
            abiertos.append(identidad_nativa(o.GetClassName(), clave, raiz))
    return ids, tramos, abiertos, info


def ejecutar(app, plan: dict) -> tuple[dict, int]:
    """Lectura nativa tras reabrir. Devuelve (lectura, código)."""
    lectura = {'project': plan['project'], 'folder': plan.get('folder'),
               'feeders': list(plan.get('feeders') or []), 'pf_version': None,
               'reopen_verified': False, 'topologia': {}, 'flujo': None, 'avisos': []}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**lectura, 'error': f"no existe el proyecto {plan['project']!r}"}, 2
    # Reabrir: lo que cuenta es lo guardado en la base de DIgSILENT (RF-27).
    proyecto.Deactivate()
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**lectura, 'error': 'el proyecto no se pudo volver a activar'}, 2
    nombre_caso = CASOS.get(plan.get('case') or '', plan.get('case'))
    if nombre_caso:
        caso = _caso(app, nombre_caso)
        if caso is None:
            return {**lectura, 'error': f'el proyecto no tiene el caso «{nombre_caso}»'}, 2
        caso.Activate()
    lectura['pf_version'] = _version(app)
    variaciones = sorted(v.loc_name for v in (app.GetActiveNetworkVariations() or []))
    esperadas = set(plan.get('variaciones_esperadas') or [])
    lectura['reopen_verified'] = esperadas <= set(variaciones)
    if not lectura['reopen_verified']:
        lectura['avisos'].append('tras reabrir faltan variaciones esperadas: '
                                 f'{sorted(esperadas - set(variaciones))}')
    escenario = app.GetActiveScenario()
    raiz = clave_pf(proyecto)
    barras, tramos, abiertos, info = _red(app, raiz)
    huellas = {}
    pedidos = set(plan.get('huellas_gps_de') or [])
    for ln in app.GetCalcRelevantObjects('*.ElmLne'):
        if ln.loc_name in pedidos:
            huellas[ln.loc_name] = huella_gps(trazado_de(ln))
    lectura['topologia'] = {'variaciones_activas': variaciones,
                            'escenario': escenario.loc_name if escenario is not None else None,
                            'frontera': abiertos, 'componentes': componentes(barras, tramos),
                            'barras': info, 'huellas_gps': huellas,
                            'estados': _estados(app, set(plan.get('estados_de') or []))}

    flujo = flujo_de_carga(app)
    if not flujo['converged']:
        lectura['flujo'] = None
        lectura['avisos'].append('el flujo no converge tras reabrir')
        return lectura, 2
    lectura['flujo'] = resultados(app, proyecto, raiz, lectura['feeders'])
    # 027:RF-1: con el grafo eléctrico, el episodio de cualquier calibración, obra o estudio
    # enseña al gemelo; los de Nasca y Chincha (2026-10-28) traían 4 067 tensiones y ningún
    # grafo, y solo entrenaban los escenarios de IN111–TA225.
    lectura['topologia']['grafo'] = grafo(app, proyecto, raiz, lectura['feeders'])
    return lectura, 0


# El grafo eléctrico del gemelo: aquí, y no en escenarios_pf, porque lo usan las dos
# herramientas y escenarios_pf ya importa de esta (027:RF-1).
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


def resultados(app, proyecto, raiz: str, feeders: list[str]) -> dict:
    """El flujo ya calculado, con unidades, en la forma del episodio (RF-28).

    La usa también ``tools/pide_pf.py`` en cada año del horizonte (RF-53).
    """
    # Una barra a 0 p.u. no tiene subtensión: está en una isla sin fuente. En la copia de
    # IN111–TA225 (2026-10-21) eran 392 de 2470 barras y la mínima salía «0,0 p.u.».
    tensiones, sin_tension = {}, []
    for b in app.GetCalcRelevantObjects('*.ElmTerm'):
        if b.HasResults() and (u := _num(b, 'm:u')) is not None:
            ident = identidad_nativa('ElmTerm', clave_pf(b), raiz)
            if u > 0:
                tensiones[ident] = u
            else:
                sin_tension.append(ident)
    carga = {'lineas': {}, 'transformadores': {}}
    for clase, grupo in (('ElmLne', 'lineas'), ('ElmTr2', 'transformadores')):
        for o in app.GetCalcRelevantObjects(f'*.{clase}'):
            if (pct := _num(o, 'c:loading')) is not None:
                carga[grupo][identidad_nativa(clase, clave_pf(o), raiz)] = pct
    cabeceras, fps, perdidas = {}, {}, 0.0
    elms = {f.loc_name: f for f in proyecto.GetContents('*.ElmFeeder', 1)}
    for feeder in feeders:
        elm = elms.get(feeder)
        m = medida(elm, app if len(feeders) == 1 else None) if elm is not None else {}
        cabeceras[feeder] = m.get('cabecera_kw')
        kw, kvar = m.get('cabecera_kw'), m.get('cabecera_kvar')
        # El FP de cabecera dice si una caída es de compensación reactiva (RF-50).
        fps[feeder] = (abs(kw) / math.hypot(kw, kvar)
                       if kw is not None and kvar is not None and (kw or kvar) else None)
        if perdidas is not None and m.get('perdidas_kw') is not None:
            perdidas += m['perdidas_kw']
        else:
            perdidas = None
    return {
        'balance': {'unidad': 'kW', 'valores': {'cabeceras': cabeceras}, 'fp_cabeceras': fps},
        'perdidas': ({'unidad': 'kW', 'valores': {'total': perdidas}} if perdidas is not None
                     else {'ausente': 'falta la cabecera o el consumo de algún alimentador'}),
        'cargabilidad': {'unidad': '%', 'valores': carga},
        'tensiones': {'unidad': 'p.u.', 'valores': tensiones, 'sin_tension': sorted(sin_tension)},
        'confiabilidad': {'ausente': 'la lectura no calcula confiabilidad (spec 012)'},
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Lectura de solo lectura de un proyecto de DIgSILENT '
                                            'tras una acción, para el gemelo digital (spec 024)')
    p.add_argument('--plan', required=True)
    p.add_argument('--output-json', required=True)
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    salida = Path(args.output_json)
    accion = (plan.get('native_action_context') or {}).get('action')
    blocked = native_action_block_report(plan, accion or 'digital_twin_snapshot')
    if blocked:
        salida.write_text(json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    from igea_dgs.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('digital_twin_snapshot_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        lectura, codigo = ejecutar(app, plan)
    except Exception as exc:  # noqa: BLE001 - la lectura queda siempre escrita (008:RF-17)
        lectura, codigo = {'project': plan.get('project'), 'error': repr(exc),
                           'traza': traceback.format_exc()}, 1
    salida.write_text(json.dumps(lectura, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Lectura de {plan.get('project')}: código {codigo}")
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
