"""De ``RedArea`` a pandapower: el flujo del motor abierto para la red de transmisión del área (107:RF-3, RF-5).

Por qué no se reutiliza ``oraculo.red_pandapower`` ni sus auxiliares. Aquel construye un ``FeederModel`` de MT
(barra por nodo, SED a 0,22 kV), por fases y sin transformadores de tres devanados; sus auxiliares (``_ejecutar``,
``_tensiones``…) son privados, y usarlos crearía accesos privados entre módulos (``tools/arquitectura.py``). Aquí se
llama a pandapower directamente con los mismos parámetros de cálculo (Newton-Raphson, ``numba=False``, para que no
imprima su aviso en cada llamada), y de ``oraculo`` solo se usa ``disponible()``.

La referencia del flujo es la barra de suministro que trae la propia red: su red externa (la red equivalente de la SET
de cabecera o el punto de entrega del COES que exporta DIgSILENT como ``ElmXnet``). No se elige una barra cualquiera:
``referencias`` toma la única red externa o, si hay varias, las que la red declara de referencia (``tipo_barra`` SL, el
``bustp`` de DIgSILENT). Una red sin red externa, o con varias sin esa declaración, o con una que se declara PV o PQ
sin su consigna, es un ``PitError`` que lo nombra (107:RF-3, RF-4).

En un proyecto de transmisión la referencia puede ser una máquina (``ip_ctrl`` de DIgSILENT) y las redes externas,
PQ: ``tools/pit_pf.py`` exporta esa máquina como red externa SL, y cada red externa PQ o PV entra con su consigna
(``p_mw``, ``q_mvar``; la PV, con su tensión) como generación estática o generador de pandapower. Los acoplamientos
(``union``) son interruptores barra-barra: cerrados, pandapower une sus dos barras (107:RF-25).

La compensación capacitiva entra con ``q_mvar`` negativo, que es el convenio de pandapower para un banco que entrega
reactiva. ``fuera`` saca de servicio elementos para el N-1. La potencia sin servir es la de las cargas que quedan en
barras sin tensión (aisladas de la red externa).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .. import oraculo
from ...dominio.pit import PitError
from ...aplicacion.pit.red_area import RedArea

__all__ = ['ResultadoFlujo', 'calcular', 'inyecciones_externas', 'referencias']


@dataclass
class ResultadoFlujo:
    motor: str
    converge: bool
    fuera: tuple[str, ...] = ()
    tensiones_pu: dict[str, float] = field(default_factory=dict)
    cargabilidad_pct: dict[str, float] = field(default_factory=dict)
    #: Elemento → (P MW, Q Mvar) en su extremo de envío (``desde`` de la línea, ``hv`` del transformador), para el
    #: unifilar del F-212 (107:RF-15).
    flujos: dict[str, tuple[float, float]] = field(default_factory=dict)
    perdidas_mw: float | None = None
    p_sin_servir_mw: float = 0.0
    sin_tension: list[str] = field(default_factory=list)
    mensaje: str = ''


#: El tipo de barra de la red externa que la hace referencia del flujo (``bustp`` de DIgSILENT).
_REFERENCIA = 'SL'
#: Los tipos de barra de una red externa que no es la referencia y entra con su consigna (107:RF-25).
_CON_CONSIGNA = ('PQ', 'PV')


def _tipo_barra(g: Mapping) -> str:
    return str(g.get('tipo_barra') or '').strip().upper()


def referencias(red: RedArea) -> list[dict]:
    """Las redes externas que son la referencia del flujo: la barra de suministro que da la propia red (107:RF-3).

    Con una sola red externa, esa, salvo que se declare PV o PQ. Con varias, las que la red declara ``tipo_barra`` SL
    (una red externa SL o la máquina de referencia de DIgSILENT, 107:RF-25); todas deben declarar su tipo. Una PQ o PV
    no es la referencia: entra con su consigna (``inyecciones_externas``), y sin ella es un error. Nunca se toma la
    primera por su orden: lo que no deja decidir la referencia es un ``PitError`` con las redes externas y lo que les
    falta.
    """
    externas = red.de_tipo('red_externa')
    if not externas:
        raise PitError(f'la red del área {red.area} no tiene barra de suministro: ninguna red externa (la red equivalente '
                       'de la SET de cabecera o el punto de entrega del COES) ni máquina de referencia, y sin ella el '
                       'flujo no tiene referencia')
    tipos = {g['id']: _tipo_barra(g) for g in externas}
    desconocidos = [i for i, t in tipos.items() if t and t not in (_REFERENCIA, *_CON_CONSIGNA)]
    sin_consigna = [g['id'] for g in externas if tipos[g['id']] in _CON_CONSIGNA and g.get('p_mw') in (None, '')]
    if desconocidos or sin_consigna:
        nombradas = sorted(desconocidos + sin_consigna)
        raise PitError(f'la red del área {red.area} declara {", ".join(f"{i} ({tipos[i]})" for i in nombradas)} sin '
                       f'su consigna de potencia (p_mw): el PIT modela la red externa de referencia ({_REFERENCIA}) y '
                       f'una PQ o PV solo como inyección con su consigna; dé su consigna, declárela {_REFERENCIA} o '
                       'quítela')
    if len(externas) > 1 and not all(tipos.values()):
        sin = sorted(i for i, t in tipos.items() if not t)
        raise PitError(f'la red del área {red.area} tiene {len(externas)} redes externas ({", ".join(sorted(tipos))}) '
                       f'y {", ".join(sin)} no declara su tipo de barra: diga cuáles son la referencia del flujo '
                       f'(tipo_barra {_REFERENCIA}, el bustp de DIgSILENT)')
    refs = [g for g in externas if tipos[g['id']] in ('', _REFERENCIA)]
    if not refs:
        raise PitError(f'la red del área {red.area} no tiene barra de suministro de referencia: '
                       f'{", ".join(f"{i} ({tipos[i]})" for i in sorted(tipos))} no son {_REFERENCIA} y no hay '
                       'máquina de referencia (el ip_ctrl de DIgSILENT); declare la referencia del flujo')
    return refs


def inyecciones_externas(red: RedArea) -> list[dict]:
    """107:RF-25: las redes externas PQ o PV que no son la referencia, con su consigna (la comprueba ``referencias``)."""
    return [g for g in red.de_tipo('red_externa') if _tipo_barra(g) in _CON_CONSIGNA]


def _red(pp, red: RedArea, cargas: Mapping[str, tuple[float, float]], fuera: set[str]):
    net = pp.create_empty_network()
    bus = {}
    for b in red.de_tipo('barra'):
        bus[b['id']] = pp.create_bus(net, vn_kv=float(b['kv']), name=b['id'])
    for g in referencias(red):
        pp.create_ext_grid(net, bus[g['barra']], vm_pu=float(g['vm_pu']), name=g['id'], in_service=g['id'] not in fuera)
    for g in inyecciones_externas(red):
        # 107:RF-25: con el convenio de generación de pandapower, la consigna de DIgSILENT (pgini, qgini) tal cual.
        if _tipo_barra(g) == 'PV':
            pp.create_gen(net, bus[g['barra']], p_mw=float(g['p_mw']), vm_pu=float(g['vm_pu']), name=g['id'],
                          in_service=g['id'] not in fuera)
        else:
            pp.create_sgen(net, bus[g['barra']], p_mw=float(g['p_mw']), q_mvar=float(g.get('q_mvar') or 0.0),
                           name=g['id'], in_service=g['id'] not in fuera)
    for e in red.de_tipo('union'):
        # 107:RF-25: un acoplamiento cerrado une sus dos barras (interruptor barra-barra de pandapower).
        pp.create_switch(net, bus[e['desde']], bus[e['hasta']], et='b',
                         closed=bool(e['cerrado']) and e['id'] not in fuera, name=e['id'])
    lineas, trafos, trafos3 = {}, {}, {}
    for e in red.de_tipo('linea'):
        lineas[e['id']] = pp.create_line_from_parameters(
            net, bus[e['desde']], bus[e['hasta']], length_km=float(e['longitud_km']),
            r_ohm_per_km=float(e['r_ohm_per_km']), x_ohm_per_km=float(e['x_ohm_per_km']),
            c_nf_per_km=float(e['c_nf_per_km']), max_i_ka=float(e['max_i_ka']), name=e['id'],
            in_service=e['id'] not in fuera)
    for e in red.de_tipo('trafo2'):
        trafos[e['id']] = pp.create_transformer_from_parameters(
            net, bus[e['hv']], bus[e['lv']], sn_mva=float(e['sn_mva']), vn_hv_kv=float(e['vn_hv_kv']),
            vn_lv_kv=float(e['vn_lv_kv']), vkr_percent=float(e['vkr_percent']), vk_percent=float(e['vk_percent']),
            pfe_kw=float(e['pfe_kw']), i0_percent=float(e['i0_percent']), name=e['id'],
            in_service=e['id'] not in fuera)
    for e in red.de_tipo('trafo3'):
        trafos3[e['id']] = pp.create_transformer3w_from_parameters(
            net, bus[e['hv']], bus[e['mv']], bus[e['lv']], vn_hv_kv=float(e['vn_hv_kv']),
            vn_mv_kv=float(e['vn_mv_kv']), vn_lv_kv=float(e['vn_lv_kv']), sn_hv_mva=float(e['sn_hv_mva']),
            sn_mv_mva=float(e['sn_mv_mva']), sn_lv_mva=float(e['sn_lv_mva']),
            vk_hv_percent=float(e['vk_hv_percent']), vk_mv_percent=float(e['vk_mv_percent']),
            vk_lv_percent=float(e['vk_lv_percent']), vkr_hv_percent=float(e['vkr_hv_percent']),
            vkr_mv_percent=float(e['vkr_mv_percent']), vkr_lv_percent=float(e['vkr_lv_percent']),
            pfe_kw=float(e['pfe_kw']), i0_percent=float(e['i0_percent']), name=e['id'],
            in_service=e['id'] not in fuera)
    for e in red.de_tipo('compensacion'):
        pp.create_shunt(net, bus[e['barra']], q_mvar=-float(e['q_mvar']), p_mw=0.0, name=e['id'],
                        in_service=e['id'] not in fuera)
    for barra, (p, q) in cargas.items():
        if barra not in bus:
            raise PitError(f'la demanda va a la barra {barra}, que no está en la red del área {red.area}')
        pp.create_load(net, bus[barra], p_mw=float(p), q_mvar=float(q), name=barra)
    return net, bus, lineas, trafos, trafos3


def calcular(red: RedArea, cargas: Mapping[str, tuple[float, float]], *, fuera: Iterable[str] = ()) -> ResultadoFlujo:
    """Flujo de potencia con pandapower; ``cargas`` es barra → (P MW, Q Mvar)."""
    if not oraculo.disponible():
        raise PitError('pandapower no está instalado: el motor abierto del PIT no puede calcular')
    import pandapower as pp

    fuera = set(fuera)
    desconocidos = fuera - red.ids()
    if desconocidos:
        raise PitError(f'no se puede sacar de servicio {sorted(desconocidos)}: no están en la red del área')
    net, bus, lineas, trafos, trafos3 = _red(pp, red, cargas, fuera)
    res = ResultadoFlujo('abierto', False, tuple(sorted(fuera)))
    if not net.ext_grid.in_service.any():
        res.mensaje = ('el flujo no se puede calcular: ' + ', '.join(sorted(fuera)) + ' fuera de servicio deja la red '
                       'sin barra de suministro')
        return res
    try:
        pp.runpp(net, algorithm='nr', init='auto', max_iteration=30, calculate_voltage_angles=False, numba=False)
    except pp.LoadflowNotConverged as exc:
        res.mensaje = f'el flujo no converge con pandapower: {exc}'
        return res
    res.converge = True
    vm = net.res_bus.vm_pu
    for nombre, i in bus.items():
        v = float(vm.at[i])
        if math.isnan(v):
            res.sin_tension.append(nombre)
        else:
            res.tensiones_pu[nombre] = v
    for tabla, ids, p, q in ((net.res_line, lineas, 'p_from_mw', 'q_from_mvar'),
                             (net.res_trafo, trafos, 'p_hv_mw', 'q_hv_mvar'),
                             (net.res_trafo3w, trafos3, 'p_hv_mw', 'q_hv_mvar')):
        for nombre, i in ids.items():
            c = float(tabla.loading_percent.at[i])
            if not math.isnan(c):
                res.cargabilidad_pct[nombre] = c
            pq = (float(tabla[p].at[i]), float(tabla[q].at[i]))
            if not any(math.isnan(x) for x in pq):
                res.flujos[nombre] = pq
    sin = set(res.sin_tension)
    res.p_sin_servir_mw = float(sum(p for b, (p, _q) in cargas.items() if b in sin))
    perdidas = [net.res_line.pl_mw.sum(), net.res_trafo.pl_mw.sum(), net.res_trafo3w.pl_mw.sum()]
    res.perdidas_mw = float(sum(x for x in perdidas if not math.isnan(x)))
    return res
