#!/usr/bin/env python
"""Guion de DIgSILENT del PIT: exporta la red de transmisión del área y la estudia por año (spec 107, T12).

Corre con el intérprete de PowerFactory, en el carril ``powerfactory`` (P7), y sobre una **copia** del proyecto de
transmisión: nunca sobre el del operador.

* ``--exportar-red``: las barras, la red externa, las líneas, los transformadores de dos y tres devanados y la
  compensación del proyecto activo, en el contrato ``RedArea`` del PIT (``pit/red_area.py``). Lo que DIgSILENT no da
  (un tipo sin asignar, un atributo vacío) no se rellena: el elemento sale sin ese dato y el PIT lo lista en
  ``faltantes`` (107:RF-4). La red externa y la compensación salen con la tensión nominal de su barra, y la red
  externa con su tipo de barra (``bustp``), que dice cuál es la referencia del flujo (107:RF-3).
* Cada elemento lleva un ``id`` único, su ruta desde la red (``<red>.ElmNet/<subestación>.ElmSubstat/<barra>.ElmTerm``),
  y su ``nombre`` aparte: en un proyecto de transmisión las barras de cada subestación se llaman «1», «2», «3»… y el
  nombre solo uniría barras distintas. Las tensiones, las cargabilidades y el estado del estudio usan las mismas claves,
  y así los resultados de DIgSILENT y del motor abierto se emparejan por ``id`` (107:RF-25).
* Los acoplamientos (``ElmCoup``) salen como uniones de barras con su estado (``cerrado``): una barra partida por un
  acoplamiento cerrado es una sola en el flujo (107:RF-25).
* Los condensadores y las reactancias serie (``ElmScap``, ``ElmSind``) salen como ramas ``serie`` con su R y su X en
  ohmios; sin ellos una red de transmisión con compensación serie queda partida (107:RF-26).
* La máquina que DIgSILENT declara de referencia (``ip_ctrl``) sale como red externa de referencia (SL) con su
  consigna de tensión, y la red externa con su consigna de potencia (``pgini``, ``qgini``): un proyecto cuya
  referencia es una máquina y cuyas redes externas son PQ se puede calcular con el motor abierto (107:RF-25).
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


def _id(obj) -> str | None:
    """107:RF-25: el id único de un elemento, su ruta desde la red a la que pertenece (``GetFullName`` desde el
    ``ElmNet``, con ``/``): ``<red>.ElmNet/<subestación>.ElmSubstat/1.ElmTerm``. El ``loc_name`` no basta: en un
    proyecto de transmisión cada subestación tiene sus barras «1», «2», «3»… Un objeto que no cuelga de una red (solo en
    un doble de pruebas) se identifica por su nombre."""
    if obj is None:
        return None
    try:
        completo = str(obj.GetFullName() or '')
    except Exception:  # noqa: BLE001 - justificado: la API de PowerFactory da errores propios; queda el nombre
        completo = ''
    partes = [p for p in completo.split('\\') if p]
    for i, parte in enumerate(partes):
        if parte.endswith('.ElmNet'):
            return '/'.join(partes[i:])
    return str(obj.loc_name)


def _barra(obj, lado: str) -> str | None:
    return _id(_terminal(obj, lado))


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


def _objetos(app, patron: str) -> list:
    return list(app.GetCalcRelevantObjects(patron) or [])


def _fuera_de_servicio(obj) -> bool:
    return _num(obj, 'outserv') == 1


#: 107:RF-27: nanofaradios por kilómetro de cada unidad que DIgSILENT puede declarar para ``cline`` (la del proyecto).
_A_NF_POR_KM = {'pf/km': 1e-3, 'nf/km': 1.0, 'uf/km': 1e3, 'µf/km': 1e3, 'μf/km': 1e3, 'mf/km': 1e6, 'f/km': 1e9}


def _capacitancia_nf_km(tipo) -> float | None:
    """107:RF-27: la capacitancia del tipo de línea en nF/km, desde la unidad que declara el proyecto
    (``GetAttributeUnit``). En la copia de transmisión del 22-11 venía en nF/km y se tomaba como µF/km: 1 000 veces la
    capacidad. Sin unidad legible, la de fábrica de DIgSILENT (µF/km)."""
    c = _num(tipo, 'cline')
    if c is None:
        return None
    try:
        unidad = str(tipo.GetAttributeUnit('cline') or '').strip().lower()
    except Exception:  # noqa: BLE001 - justificado: un doble o una versión sin la función; queda la unidad de fábrica
        unidad = ''
    return c * _A_NF_POR_KM.get(unidad, 1e3)


def _abiertos(obj, lados: tuple[tuple[str, str], ...]) -> list[str] | None:
    """107:RF-27: los lados (con el nombre del contrato) cuyo cubículo tiene un interruptor (``StaSwitch``) abierto:
    DIgSILENT deja la rama desconectada de ese lado aunque esté en servicio."""
    out = []
    for attr, clave in lados:
        cub = getattr(obj, attr, None)
        contenido = getattr(cub, 'GetContents', None)
        if contenido is None:
            continue
        try:
            interruptores = contenido('*.StaSwitch') or []
        except Exception:  # noqa: BLE001  # justificado: un cubículo sin contenido legible no se supone abierto
            continue
        if any(_num(s, 'on_off') == 0 for s in interruptores):
            out.append(clave)
    return out or None


def _paralelo(obj, attr: str) -> int | None:
    """107:RF-27: las unidades en paralelo (``nlnum``, ``ntnum``, ``nt3nm``) cuando son más de una."""
    n = _num(obj, attr)
    return int(n) if n is not None and n > 1 else None


def _toma(tipo, elemento, lado: str, du: str, neutro: str, pos: str, minimo: str, maximo: str) -> dict[str, Any]:
    """107:RF-27: la toma de un devanado: posición del elemento, escalón, neutro y límites del tipo."""
    paso = _num(tipo, du)
    if not paso:
        return {}
    return {'tap_side': lado, 'tap_step_percent': paso, 'tap_neutral': _num(tipo, neutro), 'tap_pos': _num(elemento, pos),
            'tap_min': _num(tipo, minimo), 'tap_max': _num(tipo, maximo)}


def _desfase(grupo) -> float | None:
    """107:RF-28: el desfase en grados de un grupo horario de DIgSILENT (``nt2ag``, ``nt3ag_*``): 30° por hora."""
    return None if grupo is None else (30.0 * grupo) % 360.0


def _desfases_tr3(tipo) -> dict[str, float]:
    """107:RF-28: el desfase de media y de baja de un trafo de tres devanados, relativo al de alta, como lo pide
    pandapower (``shift_mv_degree``, ``shift_lv_degree``)."""
    h = _num(tipo, 'nt3ag_h') or 0.0
    out = {}
    for lado, clave in (('m', 'shift_mv_degree'), ('l', 'shift_lv_degree')):
        g = _num(tipo, f'nt3ag_{lado}')
        if g is not None:
            out[clave] = _desfase(g - h)
    return out


def exportar_red(app, plan: dict) -> list[dict[str, Any]]:
    """Los elementos del proyecto activo en el contrato ``RedArea`` (claves de ``REQUERIDOS``), cada uno con su id
    único (``_id``) y su nombre (107:RF-25)."""
    area, titular = str(plan['area']), str(plan['titular'])
    proyecto = str(plan.get('project') or '')
    comun = {'areas': [area], 'titular': titular}

    def fuente(o):
        return {'proyecto': proyecto, 'objeto': o.GetFullName()}

    def ident(o):
        return {'id': _id(o), 'nombre': str(o.loc_name)}

    out: list[dict[str, Any]] = []
    for b in _objetos(app, '*.ElmTerm'):
        out.append(_sin_vacios({**ident(b), 'tipo': 'barra', 'kv': _num(b, 'uknom'), **comun, 'fuente': fuente(b)}))
    for g in _objetos(app, '*.ElmXnet'):
        # El tipo de barra (``bustp``: SL, PV o PQ) dice cuál es la referencia cuando hay varias (107:RF-3); la
        # consigna de potencia, con qué entra una red externa PQ o PV que no es la referencia (107:RF-25).
        out.append(_sin_vacios({**ident(g), 'tipo': 'red_externa', 'barra': _barra(g, 'bus1'),
                                'kv': _kv_barra(g, 'bus1'), 'vm_pu': _num(g, 'usetp'),
                                'tipo_barra': _texto(g, 'bustp'), 'p_mw': _num(g, 'pgini'),
                                'q_mvar': _num(g, 'qgini'), **comun, 'fuente': fuente(g)}))
    for patron in ('*.ElmSym', '*.ElmGenstat'):
        # 107:RF-25: la máquina de referencia del flujo (``ip_ctrl``) es la barra de suministro cuando la referencia
        # del proyecto no es una red externa. Las demás máquinas no se exportan: su generación es inyección del caso.
        for m in _objetos(app, patron):
            if _fuera_de_servicio(m) or _num(m, 'ip_ctrl') != 1:
                continue
            out.append(_sin_vacios({**ident(m), 'tipo': 'red_externa', 'barra': _barra(m, 'bus1'),
                                    'kv': _kv_barra(m, 'bus1'), 'vm_pu': _num(m, 'usetp'), 'tipo_barra': 'SL',
                                    'maquina_referencia': True, **comun, 'fuente': fuente(m)}))
    for s in _objetos(app, '*.ElmSvs'):
        # 107:RF-28: el SVC regula la tensión de su barra: nudo PV sin potencia activa, con su consigna (usetp) y sus
        # límites de Q (qmax capacitiva; qmin, la inductiva, en negativo). En la copia de transmisión había 13, de hasta
        # 315 Mvar en 500 kV, y no se exportaban.
        if _fuera_de_servicio(s) or _abiertos(s, (('bus1', 'barra'),)):
            continue
        qmin = _num(s, 'qmin')
        out.append(_sin_vacios({**ident(s), 'tipo': 'red_externa', 'barra': _barra(s, 'bus1'),
                                'kv': _kv_barra(s, 'bus1'), 'vm_pu': _num(s, 'usetp'), 'tipo_barra': 'PV',
                                'p_mw': 0.0, 'q_max_mvar': _num(s, 'qmax'),
                                'q_min_mvar': None if qmin is None else -abs(qmin), **comun, 'fuente': fuente(s)}))
    for c in _objetos(app, '*.ElmCoup'):
        # 107:RF-25: el acoplamiento une dos barras de la subestación; abierto, se exporta igual con su estado. Sin
        # estado legible no se supone: queda sin ``cerrado`` y el PIT lo lista en faltantes (107:RF-4).
        if _fuera_de_servicio(c):
            continue
        estado_c = _num(c, 'on_off')
        out.append(_sin_vacios({**ident(c), 'tipo': 'union', 'desde': _barra(c, 'bus1'), 'hasta': _barra(c, 'bus2'),
                                'kv': _kv_barra(c, 'bus1'),
                                'cerrado': None if estado_c is None else estado_c == 1, **comun,
                                'fuente': fuente(c)}))
    for patron, attr_r, attr_x, signo in (('*.ElmScap', 'rcap', 'xcap', -1.0), ('*.ElmSind', 'rrea', 'xrea', 1.0)):
        # 107:RF-26: los condensadores y las reactancias serie son ramas: en la copia de transmisión del 21-11 el Sur
        # solo llegaba a la referencia por las líneas de 500 kV con condensadores serie, y sin ellos quedaban sin
        # suministro 1 499 barras con tensión en DIgSILENT. La reactancia de un condensador (``xcap``, en ohmios) es
        # capacitiva: X negativa. Sin resistencia declarada (el ``ElmScap`` no la trae), 0. Sin reactancia no se
        # supone: queda en faltantes (RF-4).
        for s in _objetos(app, patron):
            if _fuera_de_servicio(s):
                continue
            x = _num(s, attr_x)
            out.append(_sin_vacios({**ident(s), 'tipo': 'serie', 'desde': _barra(s, 'bus1'), 'hasta': _barra(s, 'bus2'),
                                    'kv': _kv_barra(s, 'bus1'), 'r_ohm': _num(s, attr_r) or 0.0,
                                    'x_ohm': None if x is None else signo * x, **comun, 'fuente': fuente(s)}))
    for ln in _objetos(app, '*.ElmLne'):
        if _fuera_de_servicio(ln):                     # 107:RF-27: lo que DIgSILENT tiene fuera no se modela
            continue
        t = getattr(ln, 'typ_id', None)
        out.append(_sin_vacios({
            **ident(ln), 'tipo': 'linea', 'desde': _barra(ln, 'bus1'), 'hasta': _barra(ln, 'bus2'),
            'kv': _num(t, 'uline'), 'longitud_km': _num(ln, 'dline'), 'r_ohm_per_km': _num(t, 'rline'),
            'x_ohm_per_km': _num(t, 'xline'), 'c_nf_per_km': _capacitancia_nf_km(t), 'f_hz': _num(t, 'frnom'),
            'max_i_ka': _num(t, 'sline'), 'paralelo': _paralelo(ln, 'nlnum'),
            'abierto_en': _abiertos(ln, (('bus1', 'desde'), ('bus2', 'hasta'))), **comun, 'fuente': fuente(ln)}))
    for tr in _objetos(app, '*.ElmTr2'):
        if _fuera_de_servicio(tr):
            continue
        t = getattr(tr, 'typ_id', None)
        sn = _num(t, 'strn')
        lado = 'lv' if _num(t, 'tap_side') == 1 else 'hv'
        out.append(_sin_vacios({
            'paralelo': _paralelo(tr, 'ntnum'), 'abierto_en': _abiertos(tr, (('bushv', 'hv'), ('buslv', 'lv'))),
            'shift_degree': _desfase(_num(t, 'nt2ag')),
            **_toma(t, tr, lado, 'dutap', 'nntap0', 'nntap', 'ntpmn', 'ntpmx'),
            **ident(tr), 'tipo': 'trafo2', 'hv': _barra(tr, 'bushv'), 'lv': _barra(tr, 'buslv'),
            'kv': _num(t, 'utrn_h'), 'sn_mva': sn, 'vn_hv_kv': _num(t, 'utrn_h'), 'vn_lv_kv': _num(t, 'utrn_l'),
            'vk_percent': _num(t, 'uktr'), 'vkr_percent': _pct_cobre(_num(t, 'pcutr'), sn),
            'pfe_kw': _num(t, 'pfe'), 'i0_percent': _num(t, 'curmg'), **comun, 'fuente': fuente(tr)}))
    for tr in _objetos(app, '*.ElmTr3'):
        if _fuera_de_servicio(tr):
            continue
        t = getattr(tr, 'typ_id', None)
        sn = {x: _num(t, f'strn3_{x}') for x in 'hml'}
        toma3 = next((d for d in (_toma(t, tr, nombre, f'du3tp_{x}', f'n3tp0_{x}', f'n3tap_{x}', f'n3tmn_{x}', f'n3tmx_{x}')
                                  for x, nombre in (('h', 'hv'), ('m', 'mv'), ('l', 'lv'))) if d), {})
        # DIgSILENT da la tensión de cortocircuito por par de devanados (AT-MT, MT-BT, BT-AT), como pandapower.
        out.append(_sin_vacios({
            **ident(tr), 'tipo': 'trafo3', 'hv': _barra(tr, 'bushv'), 'mv': _barra(tr, 'busmv'),
            'lv': _barra(tr, 'buslv'), 'kv': _num(t, 'utrn3_h'),
            'sn_hv_mva': sn['h'], 'sn_mv_mva': sn['m'], 'sn_lv_mva': sn['l'],
            'vn_hv_kv': _num(t, 'utrn3_h'), 'vn_mv_kv': _num(t, 'utrn3_m'), 'vn_lv_kv': _num(t, 'utrn3_l'),
            'vk_hv_percent': _num(t, 'uktr3_h'), 'vk_mv_percent': _num(t, 'uktr3_m'),
            'vk_lv_percent': _num(t, 'uktr3_l'),
            'vkr_hv_percent': _pct_cobre(_num(t, 'pcut3_h'), sn['h']),
            'vkr_mv_percent': _pct_cobre(_num(t, 'pcut3_m'), sn['m']),
            'vkr_lv_percent': _pct_cobre(_num(t, 'pcut3_l'), sn['l']),
            'pfe_kw': _num(t, 'pfe'), 'i0_percent': _num(t, 'curm3'), 'paralelo': _paralelo(tr, 'nt3nm'),
            'abierto_en': _abiertos(tr, (('bushv', 'hv'), ('busmv', 'mv'), ('buslv', 'lv'))), **toma3,
            **_desfases_tr3(t), **comun,
            'fuente': fuente(tr)}))
    for q in _objetos(app, '*.ElmShnt'):
        if _fuera_de_servicio(q) or _abiertos(q, (('bus1', 'barra'),)):
            continue
        # 107:RF-27: la Q real con sus escalones en servicio (``Qact``); la de una reactancia (shtype 1), inductiva. Con
        # ``qcapn`` las 87 reactancias de la copia de transmisión (hasta 120 Mvar en 500 kV) salían con 0.
        q_real = _num(q, 'Qact')
        if q_real is None:
            q_real = _num(q, 'qcapn')
        if q_real is not None and _num(q, 'shtype') == 1:
            q_real = -abs(q_real)
        out.append(_sin_vacios({**ident(q), 'tipo': 'compensacion', 'barra': _barra(q, 'bus1'),
                                'kv': _kv_barra(q, 'bus1'), 'q_mvar': q_real, **comun,
                                'fuente': fuente(q)}))
    vistos: dict[str, int] = {}
    for e in out:
        vistos[e['id']] = vistos.get(e['id'], 0) + 1
    repetidos = sorted(i for i, n in vistos.items() if n > 1)
    if repetidos:
        # Dos elementos con el mismo id unirían en el motor abierto lo que en DIgSILENT está separado (107:RF-25).
        raise ValueError(f'la red exportada repite el id de {len(repetidos)} elementos ({", ".join(repetidos[:10])}): '
                         'el motor abierto uniría elementos distintos')
    return out


def estado(app) -> dict[str, Any]:
    """Lo que un estudio no puede dejar cambiado (el contrato de ``cambios_de_estado``)."""
    caso = app.GetActiveStudyCase()
    etapa = app.GetRecordingStage() if hasattr(app, 'GetRecordingStage') else None
    variaciones = app.GetProjectFolder('scheme')
    return {'demandas': {_id(c): (float(c.plini), float(c.qlini)) for c in _objetos(app, '*.ElmLod')},
            'variaciones': sorted(v.loc_name for v in (variaciones.GetContents('*.IntScheme') if variaciones else [])),
            'hora': getattr(caso, 'iStudyTime', None), 'etapa': getattr(etapa, 'loc_name', None)}


def _ejecutar(app, clase: str) -> dict[str, Any]:
    orden = app.GetFromStudyCase(clase)
    ret = orden.Execute()
    out: dict[str, Any] = {'orden': clase, 'return_code': ret, 'hecho': ret == 0}
    if clase == 'ComLdf' and ret == 0:
        # 107:RF-25: las mismas claves que ``exportar_red``, para emparejar con el motor abierto por id.
        out['tensiones_pu'] = {_id(b): _num(b, 'm:u') for b in _objetos(app, '*.ElmTerm')}
        out['cargabilidad_pct'] = {_id(o): _num(o, 'c:loading') for patron in ('*.ElmLne', '*.ElmTr2', '*.ElmTr3')
                                   for o in _objetos(app, patron)}
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
