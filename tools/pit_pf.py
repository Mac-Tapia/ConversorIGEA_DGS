#!/usr/bin/env python
"""Guion de DIgSILENT del PIT: exporta la red de transmisión del área y la estudia por año (spec 107, T12).

Corre con el intérprete de PowerFactory, en el carril ``powerfactory`` (P7), y sobre una **copia** del proyecto de
transmisión: nunca sobre el del operador.

* ``--exportar-red``: las barras, la red externa, las líneas, los transformadores de dos y tres devanados y la
  compensación del proyecto activo, en el contrato ``RedArea`` del PIT (``pit/red_area.py``). Lo que DIgSILENT no da
  (un tipo sin asignar, un atributo vacío) no se rellena: el elemento sale sin ese dato y el PIT lo lista en
  ``faltantes`` (107:RF-4). La red externa y la compensación salen con la tensión nominal de su barra, y la red
  externa con su tipo de barra (``bustp``), que dice cuál es la referencia del flujo (107:RF-3).
* Sin esa opción, por cada año del plan (``anios``: año → caso de estudio): ``ComLdf``, ``ComSimoutage`` y ``ComRel3``,
  los que pida el plan en ``estudios``. Antes y después se lee el estado del caso (demanda de las cargas, variaciones,
  hora de estudio y etapa que graba) y ``estudios_red_pf.cambios_de_estado`` comprueba que no quedó nada cambiado.

    python tools/pit_pf.py --plan plan.json --output-json informe.json [--exportar-red]

El plan lleva ``project``, ``folder``, ``area`` y ``titular`` (los que asigna el perfil al proyecto exportado), y,
para estudiar, ``anios`` y ``estudios``. Códigos de salida: 0 hecho, 2 no se pudo o quedó algo cambiado (el informe dice
qué), 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from pathlib import Path
from typing import Any

ESTUDIOS = ('ComLdf', 'ComSimoutage', 'ComRel3')


def _num(obj, attr) -> float | None:
    """El valor numérico de un atributo, o ``None`` si DIgSILENT no lo da: el PIT lo lista en ``faltantes`` (107:RF-4)
    en vez de rellenarlo."""
    if obj is None:
        return None
    try:
        v = float(obj.GetAttribute(attr))
    except Exception:  # noqa: BLE001 - justificado: la API de PowerFactory da errores propios por un atributo sin
        # resultados o que no existe en esta versión; se intenta leerlo como atributo de Python.
        try:
            v = float(getattr(obj, attr))
        except (AttributeError, TypeError, ValueError):
            return None  # justificado: el dato no está y queda en faltantes, nombrado (107:RF-4)
    return v if math.isfinite(v) else None


def _terminal(obj, lado: str):
    cub = getattr(obj, lado, None)
    return cub.GetParent() if cub is not None else None


def _barra(obj, lado: str) -> str | None:
    padre = _terminal(obj, lado)
    return padre.loc_name if padre is not None else None


def _kv_barra(obj, lado: str) -> float | None:
    """La tensión nominal de la barra a la que se conecta: la red externa y la compensación no tienen tensión propia,
    y sin ella ``ambito.reunir`` las dejaría fuera del ámbito por tensión y la red quedaría sin su barra de suministro
    (107:RF-3)."""
    return _num(_terminal(obj, lado), 'uknom')


def _texto(obj, attr) -> str | None:
    """El valor de texto de un atributo, sin espacios, o ``None`` si DIgSILENT no lo da."""
    try:
        v = obj.GetAttribute(attr)
    except Exception:  # noqa: BLE001 - justificado: la API de PowerFactory da errores propios por un atributo que no
        # existe en esta versión; se intenta leerlo como atributo de Python.
        v = getattr(obj, attr, None)
    v = str(v).strip() if v is not None else ''
    return v or None


def _sin_vacios(e: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in e.items() if v is not None}


def _pct_cobre(pcu_kw: float | None, sn_mva: float | None) -> float | None:
    """La resistencia del ensayo de cortocircuito en %: pérdidas en el cobre entre la potencia nominal."""
    return 100.0 * pcu_kw / (1000.0 * sn_mva) if pcu_kw is not None and sn_mva else None


def exportar_red(app, plan: dict) -> list[dict[str, Any]]:
    """Los elementos del proyecto activo en el contrato ``RedArea`` (claves de ``REQUERIDOS``)."""
    area, titular = str(plan['area']), str(plan['titular'])
    proyecto = str(plan.get('project') or '')
    comun = {'areas': [area], 'titular': titular}

    def fuente(o):
        return {'proyecto': proyecto, 'objeto': o.GetFullName()}

    out: list[dict[str, Any]] = []
    for b in app.GetCalcRelevantObjects('*.ElmTerm'):
        out.append(_sin_vacios({'id': b.loc_name, 'tipo': 'barra', 'kv': _num(b, 'uknom'), **comun,
                                'fuente': fuente(b)}))
    for g in app.GetCalcRelevantObjects('*.ElmXnet'):
        # El tipo de barra (``bustp``: SL, PV o PQ) dice cuál es la referencia cuando hay varias (107:RF-3).
        out.append(_sin_vacios({'id': g.loc_name, 'tipo': 'red_externa', 'barra': _barra(g, 'bus1'),
                                'kv': _kv_barra(g, 'bus1'), 'vm_pu': _num(g, 'usetp'),
                                'tipo_barra': _texto(g, 'bustp'), **comun, 'fuente': fuente(g)}))
    for ln in app.GetCalcRelevantObjects('*.ElmLne'):
        t = getattr(ln, 'typ_id', None)
        c_uf = _num(t, 'cline')
        out.append(_sin_vacios({
            'id': ln.loc_name, 'tipo': 'linea', 'desde': _barra(ln, 'bus1'), 'hasta': _barra(ln, 'bus2'),
            'kv': _num(t, 'uline'), 'longitud_km': _num(ln, 'dline'), 'r_ohm_per_km': _num(t, 'rline'),
            'x_ohm_per_km': _num(t, 'xline'), 'c_nf_per_km': c_uf * 1000.0 if c_uf is not None else None,
            'max_i_ka': _num(t, 'sline'), **comun, 'fuente': fuente(ln)}))
    for tr in app.GetCalcRelevantObjects('*.ElmTr2'):
        t = getattr(tr, 'typ_id', None)
        sn = _num(t, 'strn')
        out.append(_sin_vacios({
            'id': tr.loc_name, 'tipo': 'trafo2', 'hv': _barra(tr, 'bushv'), 'lv': _barra(tr, 'buslv'),
            'kv': _num(t, 'utrn_h'), 'sn_mva': sn, 'vn_hv_kv': _num(t, 'utrn_h'), 'vn_lv_kv': _num(t, 'utrn_l'),
            'vk_percent': _num(t, 'uktr'), 'vkr_percent': _pct_cobre(_num(t, 'pcutr'), sn),
            'pfe_kw': _num(t, 'pfe'), 'i0_percent': _num(t, 'curmg'), **comun, 'fuente': fuente(tr)}))
    for tr in app.GetCalcRelevantObjects('*.ElmTr3'):
        t = getattr(tr, 'typ_id', None)
        sn = {x: _num(t, f'strn3_{x}') for x in 'hml'}
        # DIgSILENT da la tensión de cortocircuito por par de devanados (AT-MT, MT-BT, BT-AT), como pandapower.
        out.append(_sin_vacios({
            'id': tr.loc_name, 'tipo': 'trafo3', 'hv': _barra(tr, 'bushv'), 'mv': _barra(tr, 'busmv'),
            'lv': _barra(tr, 'buslv'), 'kv': _num(t, 'utrn3_h'),
            'sn_hv_mva': sn['h'], 'sn_mv_mva': sn['m'], 'sn_lv_mva': sn['l'],
            'vn_hv_kv': _num(t, 'utrn3_h'), 'vn_mv_kv': _num(t, 'utrn3_m'), 'vn_lv_kv': _num(t, 'utrn3_l'),
            'vk_hv_percent': _num(t, 'uktr3_h'), 'vk_mv_percent': _num(t, 'uktr3_m'),
            'vk_lv_percent': _num(t, 'uktr3_l'),
            'vkr_hv_percent': _pct_cobre(_num(t, 'pcut3_h'), sn['h']),
            'vkr_mv_percent': _pct_cobre(_num(t, 'pcut3_m'), sn['m']),
            'vkr_lv_percent': _pct_cobre(_num(t, 'pcut3_l'), sn['l']),
            'pfe_kw': _num(t, 'pfe'), 'i0_percent': _num(t, 'curm3'), **comun, 'fuente': fuente(tr)}))
    for q in app.GetCalcRelevantObjects('*.ElmShnt'):
        out.append(_sin_vacios({'id': q.loc_name, 'tipo': 'compensacion', 'barra': _barra(q, 'bus1'),
                                'kv': _kv_barra(q, 'bus1'), 'q_mvar': _num(q, 'qcapn'), **comun,
                                'fuente': fuente(q)}))
    return out


def estado(app) -> dict[str, Any]:
    """Lo que un estudio no puede dejar cambiado (el contrato de ``cambios_de_estado``)."""
    caso = app.GetActiveStudyCase()
    etapa = app.GetRecordingStage() if hasattr(app, 'GetRecordingStage') else None
    variaciones = app.GetProjectFolder('scheme')
    return {'demandas': {c.loc_name: (float(c.plini), float(c.qlini)) for c in app.GetCalcRelevantObjects('*.ElmLod')},
            'variaciones': sorted(v.loc_name for v in (variaciones.GetContents('*.IntScheme') if variaciones else [])),
            'hora': getattr(caso, 'iStudyTime', None), 'etapa': getattr(etapa, 'loc_name', None)}


def _ejecutar(app, clase: str) -> dict[str, Any]:
    orden = app.GetFromStudyCase(clase)
    ret = orden.Execute()
    out: dict[str, Any] = {'orden': clase, 'return_code': ret, 'hecho': ret == 0}
    if clase == 'ComLdf' and ret == 0:
        out['tensiones_pu'] = {b.loc_name: _num(b, 'm:u') for b in app.GetCalcRelevantObjects('*.ElmTerm')}
        out['cargabilidad_pct'] = {o.loc_name: _num(o, 'c:loading') for patron in ('*.ElmLne', '*.ElmTr2', '*.ElmTr3')
                                   for o in app.GetCalcRelevantObjects(patron)}
    if clase == 'ComRel3' and ret == 0:
        out['indices'] = {k: _num(orden, k) for k in ('c:SAIFI', 'c:SAIDI', 'c:ENS')}
    return out


def estudiar(app, plan: dict) -> tuple[dict[str, Any], int]:
    """Cada estudio del plan en el caso de cada año; nada queda cambiado (o el informe lo dice y sale con 2)."""
    from convertersmartgrid.aplicacion.estudios_red_pf import cambios_de_estado

    pedidos = list(plan.get('estudios') or ESTUDIOS)
    desconocidos = [e for e in pedidos if e not in ESTUDIOS]
    if desconocidos:
        return {'error': f'estudios desconocidos {desconocidos}; los del PIT son {list(ESTUDIOS)}'}, 2
    informe: dict[str, Any] = {'motor': 'digsilent', 'anios': {}, 'cambios': []}
    estudios = app.GetProjectFolder('study')
    casos = {c.loc_name: c for c in (estudios.GetContents('*.IntCase', 1) if estudios else [])}
    previo = app.GetActiveStudyCase()
    antes = estado(app)
    try:
        for anio, nombre in sorted((plan.get('anios') or {}).items()):
            caso = casos.get(nombre)
            if caso is None:
                informe['anios'][anio] = {'error': f'el proyecto no tiene el caso {nombre!r}'}
                continue
            caso.Activate()
            informe['anios'][anio] = {'caso': nombre, 'estudios': [_ejecutar(app, e) for e in pedidos]}
    finally:
        if previo is not None:
            previo.Activate()
        informe['cambios'] = cambios_de_estado(antes, estado(app))
    if informe['cambios']:
        informe['error'] = 'el estudio dejó cambiado: ' + ', '.join(informe['cambios'])
        return informe, 2
    return informe, 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Red de transmisión del área y sus estudios por año en DIgSILENT (spec 107)')
    p.add_argument('--plan', required=True, help='JSON con project, folder, area, titular, anios y estudios')
    p.add_argument('--output-json', required=True, help='Informe que lee el PIT')
    p.add_argument('--exportar-red', action='store_true', help='Solo exportar la red al contrato RedArea')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    from convertersmartgrid.adaptadores.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('pit_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3
    try:
        from cargas_pf import activar_proyecto

        if activar_proyecto(app, plan['project'], plan.get('folder')) is None:
            informe, codigo = {'error': f'No se encontró el proyecto {plan["project"]!r}.'}, 2
        elif args.exportar_red:
            informe, codigo = {'elementos': exportar_red(app, plan)}, 0
        else:
            informe, codigo = estudiar(app, plan)
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        traceback.print_exc()
        informe, codigo = {'error': f'Error inesperado: {exc}'}, 1
    Path(args.output_json).write_text(json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n',
                                      encoding='utf-8')
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
