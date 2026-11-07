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

from convertersmartgrid.digital_twin.contratos_fisicos import (
    APROXIMACIONES,
    CLASES_NO_REPRESENTADAS,
    CONTROLES_LDF,
    MODOS_PQ,
    REPRESENTACION,
    UNIDADES,
    VERSION_GRAFO,
)
from convertersmartgrid.digital_twin.native_snapshot import (
    componentes,
    huella_gps,
    identidad_nativa,
)
from convertersmartgrid.native_action import native_action_block_report

#: Caso del episodio → nombre del caso de estudio que deja la spec 011.
CASOS = {'caso_base': 'Caso base', 'sin_proyecto': 'Sin proyecto', 'con_proyecto': 'Con proyecto',
         'cargas_nuevas': 'Cargas nuevas'}


def _caso(app, nombre: str, anio=None):
    """El caso pedido; con año, el de ese año («Sin proyecto 2025», spec 025): el otro es otra demanda."""
    carpeta = app.GetProjectFolder('study')
    buscado = f'{nombre} {anio}' if anio else nombre
    return next((c for c in (carpeta.GetContents('*.IntCase') if carpeta else [])
                 if c.loc_name == buscado), None)


def caso_nativo(app, proyecto, caso, rol) -> dict:
    """045:RF-1: el rol con la identidad del caso activo en DIgSILENT, no solo lo que pidió el plan."""
    raiz = clave_pf(proyecto)
    return {'rol': rol, 'nombre': caso.loc_name, 'id': identidad_nativa('IntCase', clave_pf(caso), raiz)}


def contexto_del_plan(plan: dict) -> dict:
    """Lo que dice el plan del caso; lo que no dice queda en ``None``, sin suponer."""
    return {'year': plan.get('anio_casos'), 'period': plan.get('periodo'),
            'criterio_fijas': plan.get('criterio_fijas')}


def _version(app) -> str | None:
    try:
        return str(app.GetVersion())
    except Exception:  # noqa: BLE001, S110 - la versión es opcional; se busca en el módulo
        pass
    # PF 2024 no tiene ``GetVersion`` en la aplicación: todas las lecturas del 2026-11-07 (CA101 + PE104)
    # salían sin versión, aunque el módulo dice «24.0.2» (lo que lee ``protecciones_pf.py``).
    # El módulo ya lo importó ``pf_arnes.conectar``; con el doble de las pruebas no está y no hay versión.
    import sys

    version = getattr(sys.modules.get('powerfactory'), '__version__', None)
    return str(version) if version else None


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
        caso = _caso(app, nombre_caso, plan.get('anio_casos'))
        if caso is None:
            return {**lectura, 'error': f'el proyecto no tiene el caso «{nombre_caso}»'}, 2
        caso.Activate()
        lectura['caso_nativo'] = caso_nativo(app, proyecto, caso, plan.get('case'))
    lectura['contexto'] = contexto_del_plan(plan)
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


def _medido(obj, atributo: str) -> float | None:
    """Un resultado del flujo; ``None`` si no lo hay (el grafo también se lee sin flujo, ``solo_tramos``)."""
    try:
        return _num(obj, atributo)
    except Exception:  # noqa: BLE001 - la API lanza si el resultado no existe
        return None


def _faltan(valores: dict) -> list[str]:
    return [k for k, v in valores.items() if v is None]


def _comldf(app) -> dict:
    """045:RF-3: lo que pidió el flujo que dio las etiquetas; un ajuste que no se lee queda en ``None``."""
    ldf = app.GetFromStudyCase('ComLdf')
    return {k: (None if (v := getattr(ldf, k, None)) is None else int(v)) for k in CONTROLES_LDF}


def _central(g, raiz: str, nodos: dict) -> dict | None:
    """Una central con lo escrito y lo medido, sin que uno sustituya a otro (045:RF-3, RF-10)."""
    n = _barra(getattr(g, 'bus1', None), raiz)
    if n not in nodos:
        return None
    unidades = _num(g, 'ngnum')
    p, q = _num(g, 'pgini'), _num(g, 'qgini')
    faltan = _faltan({'pgini': p, 'qgini': q})
    escala = max(int(unidades or 1), 1)
    return {'id': _id(g, raiz), 'clase': g.GetClassName(), 'nodo': n,
            'en_servicio': not int(getattr(g, 'outserv', 0) or 0),
            'p_mw': None if p is None else p * escala, 'q_mvar': None if q is None else q * escala,
            'control': getattr(g, 'av_mode', None), 'usetp': _num(g, 'usetp'),
            'referencia': bool(int(getattr(g, 'ip_ctrl', 0) or 0)),
            'p_medida_mw': _medido(g, 'm:P:bus1'), 'q_medida_mvar': _medido(g, 'm:Q:bus1'),
            **({'faltan': faltan} if faltan else {})}


def _banco(sh, raiz: str, nodos: dict) -> dict | None:
    """Un banco con su escalón y lo que entrega medido (045:RF-10)."""
    n = _barra(getattr(sh, 'bus1', None), raiz)
    if n not in nodos:
        return None
    total, por_escalon, escalones = _num(sh, 'qtotn'), _num(sh, 'qcapn'), _num(sh, 'ncapa')
    q = total or (por_escalon * (escalones or 1.0) if por_escalon is not None else None)
    return {'id': _id(sh, raiz), 'clase': 'ElmShnt', 'nodo': n, 'en_servicio': not int(getattr(sh, 'outserv', 0) or 0),
            'q_mvar': q, 'escalones': escalones, 'q_medida_mvar': _medido(sh, 'm:Q:bus1'),
            **({'faltan': ['qtotn o qcapn']} if q is None else {})}


def _rama_de_linea(ln, cubs: list, tipo, raiz: str) -> dict:
    n = max(int(getattr(ln, 'nlnum', 1) or 1), 1)
    largo = _num(ln, 'dline')
    r, x, inom = _num(tipo, 'rline'), _num(tipo, 'xline'), _num(tipo, 'sline')
    faltan = _faltan({'dline': largo, 'rline': r, 'xline': x})
    return {'id': _id(ln, raiz), 'clase': 'ElmLne', 'desde': _barra(cubs[0], raiz),
            'hasta': _barra(cubs[1], raiz), 'cerrada': _cerrado(ln, cubs),
            'r_ohm': (r or 0.0) * (largo or 0.0) / n, 'x_ohm': (x or 0.0) * (largo or 0.0) / n,
            'inom_ka': (inom or 0.0) * n, 'km': largo or 0.0, 'fases': _num(tipo, 'nlnph'),
            **({'faltan': faltan} if faltan else {})}


def _rama_de_trafo(tr, hv, lv, tipo, raiz: str) -> dict:
    s, uh, ul = _num(tipo, 'strn'), _num(tipo, 'utrn_h'), _num(tipo, 'utrn_l')
    pcu, uk = _num(tipo, 'pcutr'), _num(tipo, 'uktr')
    faltan = _faltan({'strn': s, 'utrn_h': uh, 'utrn_l': ul, 'pcutr': pcu, 'uktr': uk})
    s, uh = s or 0.0, uh or 0.0
    z_base = uh * uh / s if s else 0.0
    # Las unidades en paralelo, como las ternas de una línea (074:RF-8): sin ellas, SM218 veía al 131 %
    # un transformador que DIgSILENT mide al 65 %.
    u = max(int(_num(tr, 'ntnum') or 1), 1)
    # 045:RF-4: la toma y si la mueve un control. Sin posición ni paso no se sabe la relación efectiva.
    posicion, paso = _num(tr, 'nntap'), _num(tipo, 'dutap')
    faltan += _faltan({'nntap': posicion, 'dutap': paso})
    if _num(tipo, 'dphitap'):
        faltan.append('el desfase por toma (dphitap) no está representado')
    return {'id': _id(tr, raiz), 'clase': 'ElmTr2', 'desde': _barra(hv, raiz),
            'hasta': _barra(lv, raiz), 'cerrada': not int(getattr(tr, 'outserv', 0) or 0),
            'r_ohm': (pcu or 0.0) / 1000 / s * z_base / u if s else 0.0,
            'x_ohm': (uk or 0.0) / 100 * z_base / u,
            'inom_ka': s / (3 ** 0.5 * uh) * u if uh else 0.0,
            'relacion': uh / (ul or uh) if uh else None, 'unidades': u, 'fases': _num(tipo, 'nt2ph'),
            **({'u_desde_kv': uh, 'u_hasta_kv': ul} if uh and ul else {}),
            'toma': {'posicion': posicion, 'neutra': _num(tipo, 'nntap0'), 'paso_pct': paso,
                     'lado': _num(tipo, 'tap_side'), 'automatica': bool(int(getattr(tr, 'ntrcn', 0) or 0))},
            **({'faltan': faltan} if faltan else {})}


def grafo(app, proyecto, raiz: str, feeders: list[str], factor: float = 1.0) -> dict:
    """Nodos y ramas en unidades físicas (kV, MW, Mvar, Ω, kA), con su alcance físico (045:RF-3).

    ``p_mw`` y ``q_mvar`` son la demanda neta de la barra; ``carga_*``, ``gen_*`` y ``banco_*``, sus
    partes. Lo que no se puede leer queda en ``None`` y en ``faltan``: un atributo a 0 dejaba una línea
    como acoplador sin decirlo, y una central fuera del grafo, como una carga que nadie compensaba.
    """
    nodos = {}
    for b in app.GetCalcRelevantObjects('*.ElmTerm'):
        nodos[_id(b, raiz)] = {'kv': _num(b, 'uknom'), 'p_mw': 0.0, 'q_mvar': 0.0, 'fuente': False,
                               'carga_p_mw': 0.0, 'carga_q_mvar': 0.0, 'gen_p_mw': 0.0, 'gen_q_mvar': 0.0,
                               'banco_q_mvar': 0.0, 'carga_p_efectiva_mw': None, 'carga_q_efectiva_mvar': None,
                               # 098:RF-30: la tensión del último flujo de DIgSILENT (la que mide la escalera), para
                               # que el oráculo se corrija con ella; ``None`` si se lee sin flujo.
                               'u_medida': _medido(b, 'm:u')}
    medida_p: dict[str, list] = {}
    medida_q: dict[str, list] = {}
    for c in app.GetCalcRelevantObjects('*.ElmLod'):
        if int(getattr(c, 'outserv', 0) or 0):
            continue
        n = _barra(getattr(c, 'bus1', None), raiz)
        if n in nodos:
            escala = (_num(c, 'scale0') or 1.0) * factor
            nodos[n]['carga_p_mw'] += (_num(c, 'plini') or 0.0) * escala
            nodos[n]['carga_q_mvar'] += (_num(c, 'qlini') or 0.0) * escala
            medida_p.setdefault(n, []).append(_medido(c, 'm:Psum:bus1'))
            medida_q.setdefault(n, []).append(_medido(c, 'm:Qsum:bus1'))
    # 015:RF-49: lo escrito no es lo consumido (CA101 escribía 3677 kW y consumía 2686). Se guardan las dos.
    for n, valores in medida_p.items():
        if all(v is not None for v in valores):
            nodos[n]['carga_p_efectiva_mw'] = sum(valores)
    for n, valores in medida_q.items():
        if all(v is not None for v in valores):
            nodos[n]['carga_q_efectiva_mvar'] = sum(valores)
    bancos = [b for sh in app.GetCalcRelevantObjects('*.ElmShnt') if (b := _banco(sh, raiz, nodos))]
    for b in bancos:
        if b['en_servicio'] and b['q_mvar'] is not None:
            nodos[b['nodo']]['banco_q_mvar'] += b['q_mvar']
    generadores = []
    for clase in ('ElmGenstat', 'ElmSym'):
        generadores += [g for o in (app.GetCalcRelevantObjects(f'*.{clase}') or []) if (g := _central(o, raiz, nodos))]
    for g in generadores:
        # La central que inyecta lo escrito resta de la demanda; la de referencia es una fuente, y otra
        # (control de tensión) la rechaza ``validar_alcance_fisico``.
        if g['en_servicio'] and not g['referencia'] and g['control'] in MODOS_PQ:
            nodos[g['nodo']]['gen_p_mw'] += g['p_mw'] or 0.0
            nodos[g['nodo']]['gen_q_mvar'] += g['q_mvar'] or 0.0
    redes = list(app.GetCalcRelevantObjects('*.ElmXnet'))
    fuentes_info = []
    # La consigna de tensión de cada red externa: IN111 está a 1,02 p.u. y TA225 a 1,00, y sin
    # ella el oráculo tenía que adivinar el nivel de toda la red (024, 2026-10-22).
    for x in redes:
        f = _barra(getattr(x, 'bus1', None), raiz)
        if f not in nodos:
            continue
        if (u := _num(x, 'usetp')) is not None:
            nodos[f]['v_pu'] = u
        nodos[f]['angulo_deg'] = _num(x, 'phiini')
        nodos[f]['fuente'] = True
        fuentes_info.append({'id': _id(x, raiz), 'clase': 'ElmXnet', 'nodo': f, 'v_pu': nodos[f].get('v_pu'),
                             'angulo_deg': nodos[f]['angulo_deg'], 'modo': getattr(x, 'bustp', None),
                             'p_medida_mw': _medido(x, 'm:P:bus1'), 'q_medida_mvar': _medido(x, 'm:Q:bus1')})
    for g in generadores:
        if g['en_servicio'] and g['referencia']:
            nodos[g['nodo']].update(fuente=True, angulo_deg=nodos[g['nodo']].get('angulo_deg'))
            if g['usetp'] is not None:
                nodos[g['nodo']]['v_pu'] = g['usetp']
            fuentes_info.append({'id': g['id'], 'clase': g['clase'], 'nodo': g['nodo'], 'v_pu': g['usetp'],
                                 'angulo_deg': None, 'modo': 'referencia', 'p_medida_mw': g['p_medida_mw'],
                                 'q_medida_mvar': g['q_medida_mvar']})
    if not any(d['fuente'] for d in nodos.values()):
        # Sin red externa (el doble de pruebas), la fuente es la barra de cada cabecera; sin consigna,
        # ``validar_alcance_fisico`` lo dice.
        elms = {f.loc_name: f for f in proyecto.GetContents('*.ElmFeeder', 1)}
        for f in [_barra(getattr(elms[f], 'obj_id', None), raiz) for f in feeders if f in elms]:
            if f in nodos:
                nodos[f]['fuente'] = True
    for d in nodos.values():
        d['p_mw'] = d['carga_p_mw'] - d['gen_p_mw']
        d['q_mvar'] = d['carga_q_mvar'] - d['gen_q_mvar'] - d['banco_q_mvar']
    ramas, sin_rama = [], {}
    for ln in app.GetCalcRelevantObjects('*.ElmLne'):
        tipo = getattr(ln, 'typ_id', None)
        cubs = [c for c in (getattr(ln, 'bus1', None), getattr(ln, 'bus2', None)) if c is not None]
        if tipo is None or len(cubs) != 2:
            sin_rama.setdefault('ElmLne', []).append(_id(ln, raiz))
            continue
        ramas.append(_rama_de_linea(ln, cubs, tipo, raiz))
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
            sin_rama.setdefault('ElmTr2', []).append(_id(tr, raiz))
            continue
        ramas.append(_rama_de_trafo(tr, hv, lv, tipo, raiz))
    no_representados = {clase: ids for clase, ids in sin_rama.items()}
    equipos = {'ElmLne': sum(r['clase'] == 'ElmLne' for r in ramas), 'ElmCoup': sum(r['clase'] == 'ElmCoup' for r in ramas),
               'ElmTr2': sum(r['clase'] == 'ElmTr2' for r in ramas), 'ElmShnt': len(bancos),
               'central': len(generadores), 'ElmXnet': len(redes)}
    for clase in CLASES_NO_REPRESENTADAS:
        presentes = app.GetCalcRelevantObjects(f'*.{clase}') or []
        if presentes:
            no_representados[clase] = sorted(_id(o, raiz) for o in presentes)
    no_trifasicas = sum(1 for r in ramas if r.get('fases') is not None and r['fases'] < 3)
    return {'version': VERSION_GRAFO, 'unidades': UNIDADES, 'nodos': nodos, 'ramas': ramas,
            'bancos': bancos, 'generadores': generadores, 'fuentes': fuentes_info,
            'controles': {'comldf': _comldf(app)},
            'alcance_fisico': {'representacion': REPRESENTACION, 'equipos': equipos,
                               'no_representados': no_representados, 'aproximaciones': list(APROXIMACIONES),
                               'ramas_no_trifasicas': no_trifasicas}}


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
    # Toda la red calculable solo cuando el proyecto es de un alimentador, como ``estudios_pf.medidas``:
    # contar por los del plan sumaba las cargas de todos. En CA101 + PE104 (2026-11-07, lectura de solo
    # CA101) la cabecera era 4 655 kW y las pérdidas −4 690 kW, y la aceptación nativa las rechazaba (044 T4).
    for feeder in feeders:
        elm = elms.get(feeder)
        m = medida(elm, app if len(elms) == 1 else None) if elm is not None else {}
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
    from convertersmartgrid.pf_arnes import PFNoDisponible, conectar

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
