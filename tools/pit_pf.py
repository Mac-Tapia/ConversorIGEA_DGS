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


def _objeto(obj, attr):
    """107:RF-31: el objeto al que apunta un atributo (un nudo de control), o ``None``."""
    try:
        v = obj.GetAttribute(attr)
    except Exception:  # noqa: BLE001  # justificado: la API de PowerFactory da errores propios por un atributo que no
        # existe en esta versión; se intenta leerlo como atributo de Python.
        v = getattr(obj, attr, None)
    return v if hasattr(v, 'GetClassName') else None


def _lista(obj, attr) -> list:
    """107:RF-41: un atributo de lista de objetos (psym de un controlador de estación), o vacía."""
    try:
        v = obj.GetAttribute(attr)
    except Exception:  # noqa: BLE001  # justificado: la API de PowerFactory da errores propios por un atributo que no
        # existe en esta versión; se intenta leerlo como atributo de Python.
        v = getattr(obj, attr, None)
    return list(v) if isinstance(v, (list, tuple)) else []


def _estacion(maquina) -> dict:
    """107:RF-32: la máquina de un controlador de estación (``c_pstac``) en servicio y con control de tensión
    (``i_ctrl`` 0) regula el nudo del controlador (``rembar``) con su consigna (``usetp``); la consigna propia de la
    máquina no cuenta. En la copia de transmisión había 61: dos máquinas en paralelo con 1,000 y 1,002 dejaban su barra
    a 1,02, la del controlador. Sin controlador, o con otro modo, nada."""
    ctrl = _objeto(maquina, 'c_pstac')
    if ctrl is None or _fuera_de_servicio(ctrl) or _num(ctrl, 'i_ctrl') != 0:
        return {}
    nudo, consigna = _objeto(ctrl, 'rembar'), _num(ctrl, 'usetp')
    if nudo is None or consigna is None:
        return {}
    if _num(ctrl, 'i_droop') == 1 and (_num(ctrl, 'ddroop') or 0) > 0 and _num(nudo, 'm:u'):
        # 107:RF-40: con estatismo el controlador no deja su nudo en la consigna, como el SVC de RF-34: el STATCOM de
        # Pucallpa (1 % sobre 80 Mvar) lo dejaba en 0,9927 y con 1,000 el motor abierto subía el grupo 0,006 p.u.
        return {'barra_control': _id(nudo), 'vm_pu': _num(nudo, 'm:u'), 'estatismo_aproximado': True,
                'controlador': _id(ctrl)}
    return {'barra_control': _id(nudo), 'vm_pu': consigna, 'controlador': _id(ctrl)}


def _limites_q(obj, unidades: float, *, solo_resueltos: bool = False) -> dict[str, float]:
    """107:RF-31: los límites de Q en Mvar (convenio de generación): los que resuelve DIgSILENT con su curva de
    capacidad (c:Qmin, c:Qmax) o, si no los da, los nominales por unidad (cQ_min, cQ_max) por el número de unidades."""
    lo, hi = _num(obj, 'c:Qmin'), _num(obj, 'c:Qmax')
    if lo is not None and hi is not None:
        return {'q_min_mvar': lo, 'q_max_mvar': hi}
    if solo_resueltos:
        return {}
    lo, hi = _num(obj, 'cQ_min'), _num(obj, 'cQ_max')
    return {k: v * unidades for k, v in (('q_min_mvar', lo), ('q_max_mvar', hi)) if v is not None}


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


def _potencia_de_carga_tr3(trafo, sn: dict) -> dict[str, float]:
    """107:RF-37: la potencia de referencia de la cargabilidad de cada devanado, la del elemento (Snom_h/m/l) cuando no
    es la del tipo: DIgSILENT carga sobre ella. En la copia de transmisión 20 trafos de tres devanados la tenían distinta
    (132 MVA frente a 80 del tipo) y el motor abierto daba 70,5 % donde DIgSILENT da 42,7 %, con el mismo flujo. La
    impedancia sigue en la base del tipo."""
    out = {}
    for x, clave in (('h', 'sn_carga_hv_mva'), ('m', 'sn_carga_mv_mva'), ('l', 'sn_carga_lv_mva')):
        s_elm = _num(trafo, f'Snom_{x}')
        if s_elm and sn.get(x) and abs(s_elm - sn[x]) > 1e-6:
            out[clave] = s_elm
    return out


def _corriente_nominal_ka(linea, tipo) -> float | None:
    """107:RF-36: la corriente nominal de un circuito de la línea, la del tipo (sline) por el factor de reducción del
    elemento (fline), como la usa DIgSILENT en su cargabilidad (Inom_a = sline · fline · nlnum). En la copia de
    transmisión 27 líneas tenían fline entre 0,19 y 1,4, y con la sline sola el motor abierto daba hasta 47 puntos menos
    de carga. Sin fline legible, 1."""
    sline = _num(tipo, 'sline')
    if sline is None:
        return None
    fline = _num(linea, 'fline')
    return sline * (fline if fline and fline > 0 else 1.0)


#: 107:RF-35: µS/km por unidad de la conductancia del tipo de línea (``gline``).
_A_US_POR_KM = {'us/km': 1.0, 'µs/km': 1.0, 'ms/km': 1e3, 'ns/km': 1e-3, 's/km': 1e6}


def _conductancia_us_km(tipo) -> float | None:
    """107:RF-35: la conductancia del tipo de línea en µS/km, desde la unidad que declara el proyecto; sin unidad legible,
    la de fábrica de DIgSILENT (µS/km). En la copia de transmisión 67 tipos la traían y, sin ella, el motor abierto
    perdía unos 100 MW de pérdidas: la máquina de referencia generaba 110 MW menos que en DIgSILENT."""
    g = _num(tipo, 'gline')
    if not g:
        return None
    try:
        unidad = str(tipo.GetAttributeUnit('gline') or '').strip().lower()
    except Exception:  # noqa: BLE001  # justificado: un doble o una versión sin la función; queda la unidad de fábrica
        unidad = ''
    return g * _A_US_POR_KM.get(unidad, 1.0)


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


_PARES_TR3 = (('h', 'vk_hv_percent', 'vkr_hv_percent'), ('m', 'vk_mv_percent', 'vkr_mv_percent'),
              ('l', 'vk_lv_percent', 'vkr_lv_percent'))


def _vk_tr3(tipo, elemento, sn: dict) -> dict[str, float | None]:
    """107:RF-30: las tensiones de cortocircuito de los tres pares (AT-MT, MT-BT, BT-AT) en la toma en que está el
    trafo. Con la impedancia dependiente de la toma (``itapzdep`` = 1), DIgSILENT no usa las nominales (``uktr3_*``,
    ``uktrr3_*``) sino las de la toma: las de la mínima (``uktr3mn_*``) y la máxima (``uktr3mx_*``) en los extremos y,
    entre el neutro y cada extremo, la interpolación lineal. En la copia de transmisión, un trafo de tres devanados de
    prueba estaba en la toma máxima de alta con vk de MT-BT de 10,2 % en vez de 1,7 %: con las nominales el punto
    estrella caía junto a media y no junto a alta, y el motor abierto metía ~460 MW entre media y baja."""
    out: dict[str, float | None] = {}
    for x, vk, vkr in _PARES_TR3:
        out[vk] = _num(tipo, f'uktr3_{x}')
        # La parte resistiva de cada par sobre la potencia del par, como DIgSILENT (``uktrr3_*`` = ``pcut3_*`` /
        # (10 · potencia del par)): con la de un solo devanado, la de MT-BT de un trafo de 240/240/80 MVA salía con
        # 0,052 % en vez de 0,156 % (sonda del 22-11).
        out[vkr] = _pct_cobre(_num(tipo, f'pcut3_{x}'), _potencia_del_par(sn, x))
    lado = next((x for x in 'hml' if _num(tipo, f'du3tp_{x}')), None)
    pos = _num(elemento, f'n3tap_{lado}') if lado else None
    if pos is None:
        return out
    neutro = _num(tipo, f'n3tp0_{lado}') or 0.0
    if _num(tipo, 'itapzdep') == 1:
        _vk_de_la_toma(out, tipo, lado, pos, neutro)
    if _num(tipo, 'itapos') == 0:
        _impedancia_fija_en_ohmios(out, sn, lado, 1 + (pos - neutro) * _num(tipo, f'du3tp_{lado}') / 100)
    return out


def _vk_de_la_toma(out: dict, tipo, lado: str, pos: float, neutro: float) -> None:
    """107:RF-30: con ``itapzdep`` = 1, las vk y vkr de la toma: las del extremo y, entre el neutro y él, la
    interpolación lineal."""
    minimo, maximo = _num(tipo, f'n3tmn_{lado}'), _num(tipo, f'n3tmx_{lado}')
    if pos > neutro and maximo is not None and maximo > neutro:
        extremo, fraccion = 'mx', min(1.0, (pos - neutro) / (maximo - neutro))
    elif pos < neutro and minimo is not None and minimo < neutro:
        extremo, fraccion = 'mn', min(1.0, (neutro - pos) / (neutro - minimo))
    else:
        return
    for x, vk, vkr in _PARES_TR3:
        for clave, del_extremo in ((vk, _num(tipo, f'uktr3{extremo}_{x}')), (vkr, _num(tipo, f'uktrr3{extremo}_{x}'))):
            nominal = out[clave]
            if nominal is not None and del_extremo is not None:
                out[clave] = nominal + (del_extremo - nominal) * fraccion


def _impedancia_fija_en_ohmios(out: dict, sn: dict, lado: str, t: float) -> None:
    """107:RF-38: con la toma en el punto estrella (``itapos`` = 0 en el tipo, lo que el conversor de pandapower desde
    DIgSILENT lee como ``tap_at_star_point``), DIgSILENT pone la relación de la toma entre la estrella y la rama del
    devanado, que queda así en ohmios de su lado; el exportador da la toma en el borne, donde pandapower deja esa rama
    en p.u. de la tensión de la toma (la escala con t²). Para que den lo mismo, la rama sale dividida por t² y las
    otras dos quedan: se pasan los tres pares a estrella sobre la potencia de alta, se corrige la rama y se vuelven a
    los pares en la base de cada par (``tap_at_star_point`` de pandapower 3.5 no cambiaba el flujo con la toma). En la
    copia de transmisión, dos trafos de 200/62,46 kV en la toma +2 (t = 1,1) llevaban con las tensiones de DIgSILENT
    94,4 MW cada uno donde DIgSILENT da 116,5; con la rama en ohmios, 116,5, y su red de 60 kV quedaba ±50 MW
    descuadrada; los de la misma ficha con la toma en el borne ya cuadraban."""
    if abs(t - 1.0) < 1e-12:
        return
    base = sn.get('h')
    pares = {x: _potencia_del_par(sn, x) for x in 'hml'}
    if not base or not all(pares.values()):
        return
    i = 'hml'.index(lado)
    for claves in (('vk_hv_percent', 'vk_mv_percent', 'vk_lv_percent'),
                   ('vkr_hv_percent', 'vkr_mv_percent', 'vkr_lv_percent')):
        if any(out.get(k) is None for k in claves):
            continue
        hm, ml, lh = (out[k] * base / pares[x] for k, x in zip(claves, 'hml'))
        z = [(hm + lh - ml) / 2, (hm + ml - lh) / 2, (ml + lh - hm) / 2]
        z[i] /= t * t
        for k, x, par in zip(claves, 'hml', ((0, 1), (1, 2), (2, 0))):
            out[k] = (z[par[0]] + z[par[1]]) * pares[x] / base


def _potencia_del_par(sn: dict, x: str) -> float | None:
    """107:RF-30: la potencia de referencia del par que DIgSILENT nombra por su primer devanado: AT-MT («h») en
    min(AT, MT), MT-BT («m») en min(MT, BT) y BT-AT («l») en min(BT, AT)."""
    otro = {'h': 'm', 'm': 'l', 'l': 'h'}[x]
    vals = [v for v in (sn.get(x), sn.get(otro)) if v]
    return min(vals) if vals else None


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
    # 107:RF-43: lo que se exporta de máquinas, SVC, compensación y controladores es lo que resuelve el flujo (c:Qmin,
    # c:Qmax, m:Q, m:u). El 24-11, con la copia AD08 recién activada y sin flujo, los SVC salieron con sus nominales
    # (un reactor de 50 Mvar como capacitivo [0, 50]) y el motor abierto quedó a 0,011 p.u. de mediana de DIgSILENT;
    # el 22-11, con el flujo hecho, a 3 barras fuera de 0,005 p.u. Sin flujo resuelto no se inventa nada: el SVC sale
    # sin límites y marcado.
    resuelto = bool(_ejecutar(app, 'ComLdf').get('hecho'))
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
            if _fuera_de_servicio(m):
                continue
            if _num(m, 'ip_ctrl') == 1:
                out.append(_sin_vacios({**ident(m), 'tipo': 'red_externa', 'barra': _barra(m, 'bus1'),
                                        'kv': _kv_barra(m, 'bus1'), 'vm_pu': _num(m, 'usetp'), 'tipo_barra': 'SL',
                                        'maquina_referencia': True, **comun, 'fuente': fuente(m)}))
            elif _texto(m, 'av_mode') == 'constv':
                # 107:RF-31: la máquina con control de tensión es un nudo PV con su consigna, su potencia y sus límites
                # de Q; como inyección fija con la Q que dio DIgSILENT, el motor abierto no convergía desde arranque
                # plano en la copia de transmisión (255 máquinas), y como PV sí. La de Q constante sigue siendo
                # inyección del caso.
                unidades = _num(m, 'ngnum') or 1.0
                p = _num(m, 'pgini')
                out.append(_sin_vacios({**ident(m), 'tipo': 'red_externa', 'barra': _barra(m, 'bus1'),
                                        'kv': _kv_barra(m, 'bus1'), 'vm_pu': _num(m, 'usetp'), 'tipo_barra': 'PV',
                                        'p_mw': None if p is None else p * unidades, **_limites_q(m, unidades),
                                        'maquina': True, **_estacion(m), **comun, 'fuente': fuente(m)}))
    # 107:RF-41: el controlador de estación de cada SVC, por si el SVC no lo enlaza en c_pstac (los controladores de la
    # copia de transmisión nombran sus equipos en psym).
    ctrl_de_svc = {_id(x): c for c in _objetos(app, '*.ElmStactrl')
                   for x in (_lista(c, 'psym') or []) if hasattr(x, 'GetClassName') and x.GetClassName() == 'ElmSvs'}
    for s in _objetos(app, '*.ElmSvs'):
        # 107:RF-28: el SVC regula la tensión de su barra: nudo PV sin potencia activa, con su consigna (usetp) y sus
        # límites de Q (qmax capacitiva; qmin, la inductiva, en negativo). En la copia de transmisión había 13, de hasta
        # 315 Mvar en 500 kV, y no se exportaban.
        if _fuera_de_servicio(s) or _abiertos(s, (('bus1', 'barra'),)):
            continue
        base = {**ident(s), 'tipo': 'red_externa', 'barra': _barra(s, 'bus1'), 'kv': _kv_barra(s, 'bus1'),
                'vm_pu': _num(s, 'usetp'), 'p_mw': 0.0, **comun, 'fuente': fuente(s)}
        if _num(s, 'i_ctrl') == 2:
            # 107:RF-31: con control de Q, el SVC da su Q (qsetp, convenio de generación) y no regula tensión.
            out.append(_sin_vacios({**base, 'tipo_barra': 'PQ', 'q_mvar': _num(s, 'qsetp') or 0.0}))
            continue
        ctrl = _objeto(s, 'c_pstac') or ctrl_de_svc.get(_id(s))
        if (ctrl is not None and not _fuera_de_servicio(ctrl) and _num(ctrl, 'i_ctrl') == 1
                and _num(s, 'm:Q:bus1') is not None):
            # 107:RF-41: un controlador de estación que regula Q (i_ctrl 1) manda sobre la consigna de tensión del SVC:
            # entrega la Q que resolvió DIgSILENT (m:Q, convenio de carga). El del horno de Aceros mantenía 0 Mvar en su
            # cubículo de 220 kV absorbiendo 163,9; como PV a 1,000 el motor abierto subía la barra 0,018 p.u.
            out.append(_sin_vacios({**base, 'tipo_barra': 'PQ', 'q_mvar': -_num(s, 'm:Q:bus1'),
                                    'controlador': _id(ctrl), 'q_resuelta': True}))
            continue
        # 107:RF-43: los límites del SVC son los que resuelve DIgSILENT con la tensión; sus nominales no dicen qué parte es
        # inductiva y cuál capacitiva (qmax es el reactor en los TCR de la copia AD08), así que sin flujo no se usan.
        limites = (_limites_q(s, 1.0, solo_resueltos=True) if resuelto else {}) or {'limites_q_sin_resolver': True}
        # 107:RF-31: el SVC regula un nudo remoto (``p_rem``, la barra de alta en los 13 de la copia de transmisión) y
        # sus límites son los que resuelve DIgSILENT con la tensión (c:Qmin, c:Qmax), si los da; el estatismo se
        # exporta para que se vea, y el motor abierto lo avisa.
        remoto = _objeto(s, 'p_rem')
        estatismo = _num(s, 'ddroop') or None
        if estatismo and _num(s, 'i_droop') == 1 and remoto is not None and _num(remoto, 'm:u'):
            # 107:RF-34: con estatismo el SVC no deja su nudo en la consigna (en la copia de transmisión, 0,9947 con
            # 1,000) y ninguna fórmula con sus atributos reproducía lo medido: se exporta el punto de operación que
            # resolvió DIgSILENT en esa misma red, la tensión del nudo, y el motor abierto lo avisa.
            base = {**base, 'vm_pu': _num(remoto, 'm:u'), 'estatismo_aproximado': True}
        out.append(_sin_vacios({**base, 'tipo_barra': 'PV', **limites,
                                'barra_control': _id(remoto) if remoto is not None else None,
                                'estatismo_pct': estatismo}))
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
            'g_us_per_km': _conductancia_us_km(t),
            'max_i_ka': _corriente_nominal_ka(ln, t), 'paralelo': _paralelo(ln, 'nlnum'),
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
            **_vk_tr3(t, tr, sn),
            'pfe_kw': _num(t, 'pfe'), 'i0_percent': _num(t, 'curm3'), 'paralelo': _paralelo(tr, 'nt3nm'),
            **_potencia_de_carga_tr3(tr, sn),
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
        # 107:RF-39: Qact es la de su nominal propia (ushnm); el motor abierto la monta con la de la barra. En la copia de
        # transmisión una reactancia de 145 kV en una barra de 138 y condensadores de 11,5 kV en una de 10,5 dejaban la
        # radial de Iberia 0,012 p.u. baja y Dolorespata 0,0145 alta; referidas a la barra, por debajo de 0,001.
        kv = _kv_barra(q, 'bus1')
        propia = _num(q, 'ushnm')
        if q_real is not None and kv and propia and abs(propia / kv - 1.0) > 1e-6:
            q_real *= (kv / propia) ** 2
        # 107:RF-42: con el flujo de DIgSILENT hecho, la compensación es una admitancia fija y su Q en la nominal de la
        # barra es −m:Q/u²: vale para cualquier tipo de filtro. Los dos filtros amortiguados de 3,5.º armónico de
        # Antapacay (tipo 4) daban 11,19 Mvar con una Qact que, a su tensión, son 9,22, y la barra quedaba 0,006 baja.
        medida, u = _num(q, 'm:Q:bus1'), _num(_terminal(q, 'bus1'), 'm:u')
        if medida is not None and u and u > 0.05:
            q_real = -medida / u ** 2
        out.append(_sin_vacios({**ident(q), 'tipo': 'compensacion', 'barra': _barra(q, 'bus1'),
                                'kv': kv, 'q_mvar': q_real, **comun,
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
