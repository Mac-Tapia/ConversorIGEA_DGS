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
(``union``) son interruptores barra-barra: cerrados, pandapower une sus dos barras (107:RF-25). Las ramas serie
(``serie``: condensadores y reactancias serie) son impedancias de pandapower (107:RF-26).

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
#: 107:RF-26: la base de potencia de las ramas serie (``create_impedance`` las pide en por unidad).
_SN_SERIE_MVA = 100.0


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


def _lados_abiertos(e) -> set[str]:
    """107:RF-27: los lados con el interruptor de cubículo abierto (lista o texto separado por comas)."""
    v = e.get('abierto_en') or ()
    return {x.strip() for x in (v.split(',') if isinstance(v, str) else v) if str(x).strip()}


def _tomas(e) -> dict:
    """107:RF-27: los parámetros de toma de pandapower que trae el elemento."""
    claves = ('tap_side', 'tap_step_percent', 'tap_neutral', 'tap_pos', 'tap_min', 'tap_max')
    t = {k: e[k] for k in claves if e.get(k) is not None}
    # pandapower 3 solo aplica la toma si dice su tipo: la de DIgSILENT es de relación (en fase).
    return {**t, 'tap_changer_type': 'Ratio'} if 'tap_step_percent' in t and 'tap_side' in t else {}


def nominales_comunes(red: RedArea) -> dict[str, float]:
    """107:RF-29: la tensión nominal con que el motor abierto calcula cada barra: la común de su zona galvánica (las
    barras unidas por líneas, acoplamientos y ramas serie, sin transformadores), la más frecuente de la zona (y, si
    empatan, la mayor). En DIgSILENT dos barras de nominal distinta (220 y 221 kV, 60 y 62,4 kV) pueden estar unidas
    por una línea; pandapower trabaja en por unidad de cada barra y esa línea hacía de transformador ideal 220/221 (275
    líneas en la copia de transmisión del 22-11: miles de Mvar y el flujo no convergía)."""
    from collections import Counter

    import networkx as nx

    kv = {b['id']: float(b['kv']) for b in red.de_tipo('barra')}
    grafo = nx.Graph()
    grafo.add_nodes_from(kv)
    for tipo in ('linea', 'union', 'serie'):
        for e in red.de_tipo(tipo):
            if e.get('desde') in kv and e.get('hasta') in kv:
                grafo.add_edge(e['desde'], e['hasta'])
    comun: dict[str, float] = {}
    for zona in nx.connected_components(grafo):
        cuenta = Counter(round(kv[b], 6) for b in zona)
        vn = max(cuenta.items(), key=lambda par: (par[1], par[0]))[0]
        for b in zona:
            comun[b] = vn
    return comun


def _red(pp, red: RedArea, cargas: Mapping[str, tuple[float, float]], fuera: set[str]):
    # 107:RF-27: la frecuencia de las líneas (``f_hz``, la nominal del tipo en DIgSILENT): con la de fábrica de
    # pandapower (50 Hz) la susceptancia de una red de 60 Hz salía un 17 % baja.
    frecuencias = [float(e['f_hz']) for e in red.de_tipo('linea') if e.get('f_hz')]
    net = pp.create_empty_network(f_hz=frecuencias[0] if frecuencias else 50.0)
    bus = {}
    comun = nominales_comunes(red)                     # 107:RF-29
    propia = {b['id']: float(b['kv']) for b in red.de_tipo('barra')}
    for b in red.de_tipo('barra'):
        bus[b['id']] = pp.create_bus(net, vn_kv=comun[b['id']], name=b['id'])
    net.bus['kv_propio'] = [propia[str(n)] for n in net.bus.name]

    def en_comun(barra, vm):
        """107:RF-29: una consigna dada en la nominal propia de la barra, en la común con que se calcula."""
        return float(vm) * propia[barra] / comun[barra]

    for g in referencias(red):
        pp.create_ext_grid(net, bus[g['barra']], vm_pu=en_comun(g['barra'], g['vm_pu']), name=g['id'],
                           in_service=g['id'] not in fuera)
    net['control_remoto'] = []
    for g in inyecciones_externas(red):
        # 107:RF-25: con el convenio de generación de pandapower, la consigna de DIgSILENT (pgini, qgini) tal cual.
        if _tipo_barra(g) == 'PV':
            # 107:RF-28: con sus límites de Q si los trae (un SVC); el flujo los aplica solo si se le pide.
            limites = {k: float(g[c]) for k, c in (('min_q_mvar', 'q_min_mvar'), ('max_q_mvar', 'q_max_mvar'))
                       if g.get(c) is not None}
            i = pp.create_gen(net, bus[g['barra']], p_mw=float(g['p_mw']), vm_pu=en_comun(g['barra'], g['vm_pu']),
                              name=g['id'], in_service=g['id'] not in fuera, **limites)
            remoto = g.get('barra_control')
            if remoto and remoto in bus and remoto == g['barra']:
                # 107:RF-32: el controlador de estación regula la propia barra de la máquina: su consigna, sin vueltas.
                net.gen.at[i, 'vm_pu'] = en_comun(remoto, g['vm_pu'])
            elif remoto and remoto in bus:
                # 107:RF-31: un SVC que regula un nudo remoto (la barra de alta): la consigna es la de ese nudo, y
                # ``calcular`` corrige la tensión del PV hasta cumplirla.
                net['control_remoto'].append((i, bus[remoto], en_comun(remoto, g['vm_pu'])))
        else:
            pp.create_sgen(net, bus[g['barra']], p_mw=float(g['p_mw']), q_mvar=float(g.get('q_mvar') or 0.0),
                           name=g['id'], in_service=g['id'] not in fuera)
    _una_consigna_por_barra(net)
    for e in red.de_tipo('union'):
        # 107:RF-25: un acoplamiento cerrado une sus dos barras (interruptor barra-barra de pandapower).
        pp.create_switch(net, bus[e['desde']], bus[e['hasta']], et='b',
                         closed=bool(e['cerrado']) and e['id'] not in fuera, name=e['id'])
    for e in red.de_tipo('serie'):
        # 107:RF-26: la rama serie como impedancia de pandapower, en por unidad de la tensión de su barra de origen.
        zb = float(net.bus.vn_kv.at[bus[e['desde']]]) ** 2 / _SN_SERIE_MVA
        pp.create_impedance(net, bus[e['desde']], bus[e['hasta']], rft_pu=float(e['r_ohm']) / zb,
                            xft_pu=float(e['x_ohm']) / zb, sn_mva=_SN_SERIE_MVA, name=e['id'],
                            in_service=e['id'] not in fuera)
    lineas, trafos, trafos3 = {}, {}, {}
    for e in red.de_tipo('linea'):
        lineas[e['id']] = pp.create_line_from_parameters(
            net, bus[e['desde']], bus[e['hasta']], length_km=float(e['longitud_km']),
            r_ohm_per_km=float(e['r_ohm_per_km']), x_ohm_per_km=float(e['x_ohm_per_km']),
            c_nf_per_km=float(e['c_nf_per_km']), max_i_ka=float(e['max_i_ka']), name=e['id'],
            # 107:RF-35: la conductancia de la línea, si el tipo la trae.
            g_us_per_km=float(e.get('g_us_per_km') or 0.0),
            parallel=int(e.get('paralelo') or 1), in_service=e['id'] not in fuera)
        for lado in _lados_abiertos(e) & {'desde', 'hasta'}:
            pp.create_switch(net, bus[e[lado]], lineas[e['id']], et='l', closed=False)
    for e in red.de_tipo('trafo2'):
        trafos[e['id']] = pp.create_transformer_from_parameters(
            net, bus[e['hv']], bus[e['lv']], sn_mva=float(e['sn_mva']), vn_hv_kv=float(e['vn_hv_kv']),
            vn_lv_kv=float(e['vn_lv_kv']), vkr_percent=float(e['vkr_percent']), vk_percent=float(e['vk_percent']),
            pfe_kw=float(e['pfe_kw']), i0_percent=float(e['i0_percent']), name=e['id'],
            parallel=int(e.get('paralelo') or 1), in_service=e['id'] not in fuera,
            shift_degree=float(e.get('shift_degree') or 0.0), **_tomas(e))
        for lado in _lados_abiertos(e) & {'hv', 'lv'}:
            pp.create_switch(net, bus[e[lado]], trafos[e['id']], et='t', closed=False)
    for e in red.de_tipo('trafo3'):
        n = int(e.get('paralelo') or 1)                   # 107:RF-27: n unidades iguales: n veces la potencia
        trafos3[e['id']] = pp.create_transformer3w_from_parameters(
            net, bus[e['hv']], bus[e['mv']], bus[e['lv']], vn_hv_kv=float(e['vn_hv_kv']),
            vn_mv_kv=float(e['vn_mv_kv']), vn_lv_kv=float(e['vn_lv_kv']), sn_hv_mva=n * float(e['sn_hv_mva']),
            sn_mv_mva=n * float(e['sn_mv_mva']), sn_lv_mva=n * float(e['sn_lv_mva']),
            vk_hv_percent=float(e['vk_hv_percent']), vk_mv_percent=float(e['vk_mv_percent']),
            vk_lv_percent=float(e['vk_lv_percent']), vkr_hv_percent=float(e['vkr_hv_percent']),
            vkr_mv_percent=float(e['vkr_mv_percent']), vkr_lv_percent=float(e['vkr_lv_percent']),
            pfe_kw=n * float(e['pfe_kw']), i0_percent=float(e['i0_percent']), name=e['id'],
            in_service=e['id'] not in fuera, shift_mv_degree=float(e.get('shift_mv_degree') or 0.0),
            shift_lv_degree=float(e.get('shift_lv_degree') or 0.0), **_tomas(e))
        for lado in _lados_abiertos(e) & {'hv', 'mv', 'lv'}:
            pp.create_switch(net, bus[e[lado]], trafos3[e['id']], et='t3', closed=False)
    for e in red.de_tipo('compensacion'):
        # 107:RF-29: su Q es la de la nominal propia de su barra.
        pp.create_shunt(net, bus[e['barra']], q_mvar=-float(e['q_mvar']), p_mw=0.0, name=e['id'],
                        vn_kv=propia[e['barra']], in_service=e['id'] not in fuera)
    for barra, (p, q) in cargas.items():
        if barra not in bus:
            raise PitError(f'la demanda va a la barra {barra}, que no está en la red del área {red.area}')
        pp.create_load(net, bus[barra], p_mw=float(p), q_mvar=float(q), name=barra)
    return net, bus, lineas, trafos, trafos3


def _una_consigna_por_barra(net) -> None:
    """107:RF-31: pandapower no admite dos consignas de tensión distintas en la misma barra. En la copia de transmisión
    había máquinas en paralelo con 1,000 y 1,002: manda la de la red externa de la barra si la hay y, si no, la de la
    primera máquina; las demás se igualan a ella y se avisa."""
    net['avisos_consigna'] = []
    if not len(net.gen):
        return
    externas = {int(b): float(v) for b, v in zip(net.ext_grid.bus, net.ext_grid.vm_pu)}
    for b, grupo in net.gen[net.gen.in_service].groupby('bus'):
        manda = externas.get(int(b), float(grupo.vm_pu.iloc[0]))
        distintas = grupo[(grupo.vm_pu - manda).abs() > 1e-9]
        if len(distintas):
            net.gen.loc[distintas.index, 'vm_pu'] = manda
            nombres = ', '.join(str(n) for n in distintas.name)
            net['avisos_consigna'].append(f'{nombres}: otra consigna de tensión en la misma barra; se toma {manda:.4f}')


#: 107:RF-33: por debajo de esta tensión (en la nominal propia) la solución puede ser la de tensión baja; los pasos de la
#: carga del segundo intento, cada uno desde la solución del anterior.
_V_BAJA_PU = 0.8
_PASOS_CARGA = (0.5, 0.75, 1.0)


def _cargabilidad_tr3(net, i, potencias: dict) -> float:
    """107:RF-37: la cargabilidad del trafo3 como la da DIgSILENT: la corriente del devanado más cargado sobre su
    corriente nominal, Snom / (raíz de 3 · tensión nominal del devanado), con la potencia de referencia del elemento
    cuando la trae (si no, la del tipo): Inom_h de un trafo de 132 MVA y 220 kV es 0,3464 kA, la que da DIgSILENT."""
    fila, t3 = net.res_trafo3w.loc[i], net.trafo3w.loc[i]
    cargas = []
    for lado in ('hv', 'mv', 'lv'):
        sn = potencias.get(lado) or float(t3[f'sn_{lado}_mva'])
        corriente = float(fila[f'i_{lado}_ka'])
        if sn and not math.isnan(corriente):
            nominal = sn / (math.sqrt(3) * float(t3[f'vn_{lado}_kv']))
            cargas.append(100.0 * corriente / nominal)
    return max(cargas) if cargas else float('nan')


def _tension_propia(net):
    return net.res_bus.vm_pu * net.bus.vn_kv / net.bus.kv_propio


def _solucion_alta(pp, net, opciones: dict):
    """107:RF-33: si el flujo deja barras por debajo de 0,8 p.u., puede haber caído en la solución de tensión baja de una
    radial larga (en la copia de transmisión, 0,50 p.u. donde DIgSILENT da 1,00). Se repite con la carga, la generación
    y las inyecciones llevadas de la mitad al total, cada paso desde la solución anterior; si converge y su tensión mínima
    es mayor, se queda esa y se avisa. No usa las tensiones de DIgSILENT: el motor abierto vale sin él."""
    v = _tension_propia(net)
    bajas = int((v < _V_BAJA_PU).sum())
    if not bajas:
        return net, None
    import copy

    otra = copy.deepcopy(net)
    tablas = [(t, c) for t, c in (('load', 'p_mw'), ('load', 'q_mvar'), ('sgen', 'p_mw'), ('sgen', 'q_mvar'),
                                  ('gen', 'p_mw')) if len(otra[t])]
    base = {(t, c): otra[t][c].copy() for t, c in tablas}
    try:
        for k, paso in enumerate(_PASOS_CARGA):
            for (t, c), serie in base.items():
                otra[t][c] = serie * paso
            pp.runpp(otra, init='auto' if k == 0 else 'results', **opciones)
        _control_remoto(pp, otra, opciones)
    except pp.LoadflowNotConverged:
        return net, (f'{bajas} barras por debajo de {_V_BAJA_PU} p.u.; el segundo intento por continuación de la carga no '
                     'converge: queda la primera solución')
    if float(_tension_propia(otra).min()) > float(v.min()) + 1e-3:
        return otra, (f'{bajas} barras por debajo de {_V_BAJA_PU} p.u. en el primer flujo (solución de tensión baja); se '
                      f'toma la del segundo intento por continuación de la carga, con mínima '
                      f'{float(_tension_propia(otra).min()):.3f} p.u.')
    return net, None


#: 107:RF-31: la tolerancia y las vueltas del control remoto de tensión (en por unidad de la nominal común).
_TOL_REMOTO_PU = 1e-4
_VUELTAS_REMOTO = 20


def _control_remoto(pp, net, opciones: dict) -> None:
    """107:RF-31: los PV que regulan un nudo remoto (un SVC y su barra de alta). pandapower solo regula la barra del PV:
    tras cada flujo se mueve la consigna del PV lo que le falta al nudo controlado, salvo si está en su límite de Q
    (entonces no sostiene nada), hasta cumplirla o agotar las vueltas."""
    pares = [(g, b, v) for g, b, v in net.get('control_remoto', []) if bool(net.gen.in_service.at[g])]
    for _vuelta in range(_VUELTAS_REMOTO):
        mover = []
        for g, b, objetivo in pares:
            q = float(net.res_gen.q_mvar.at[g])
            qmin = net.gen.min_q_mvar.at[g] if 'min_q_mvar' in net.gen else float('nan')
            qmax = net.gen.max_q_mvar.at[g] if 'max_q_mvar' in net.gen else float('nan')
            en_limite = (not math.isnan(qmin) and q <= qmin + 1e-6) or (not math.isnan(qmax) and q >= qmax - 1e-6)
            falta = objetivo - float(net.res_bus.vm_pu.at[b])
            if not en_limite and abs(falta) > _TOL_REMOTO_PU:
                mover.append((g, falta))
        if not mover:
            return
        # 107:RF-32: las máquinas de un controlador de estación regulan el mismo nudo: lo que le falta se reparte entre
        # las que se mueven, para no pasarse (todas a la vez, cada una con todo, oscilaba).
        nudo_de = {g: b for g, b, _v in pares}
        por_nudo: dict[int, int] = {}
        for g, _falta in mover:
            por_nudo[nudo_de[g]] = por_nudo.get(nudo_de[g], 0) + 1
        for g, falta in mover:
            net.gen.at[g, 'vm_pu'] = float(net.gen.vm_pu.at[g]) + falta / por_nudo[nudo_de[g]]
        pp.runpp(net, init='results', **opciones)


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
        # 107:RF-28: con desfases de grupo de conexión, el flujo calcula con ángulos (si no, pandapower los ignora y una
        # malla por trafos de grupos distintos queda mal).
        angulos = any(float(net[t][c].abs().sum()) > 0 for t, c in (('trafo', 'shift_degree'),
                                                                     ('trafo3w', 'shift_mv_degree'),
                                                                     ('trafo3w', 'shift_lv_degree')) if len(net[t]))
        # 107:RF-31: con PV que traen límites de Q (máquinas y SVC), el flujo los aplica: un PV en su límite pasa a PQ
        # y deja de sostener su consigna, como en DIgSILENT.
        limites_q = bool(len(net.gen)) and bool(net.gen[['min_q_mvar', 'max_q_mvar']].notna().any().any()) \
            if {'min_q_mvar', 'max_q_mvar'} <= set(net.gen.columns) else False
        opciones = dict(algorithm='nr', max_iteration=30, calculate_voltage_angles=angulos, numba=False,
                        enforce_q_lims=limites_q)
        pp.runpp(net, init='auto', **opciones)
        _control_remoto(pp, net, opciones)
        net, aviso_alta = _solucion_alta(pp, net, opciones)
    except pp.LoadflowNotConverged as exc:
        res.mensaje = f'el flujo no converge con pandapower: {exc}'
        return res
    res.converge = True
    # 107:RF-37: los trafo3 con potencia de referencia propia del elemento.
    carga_tr3 = {e['id']: {lado: e.get(f'sn_carga_{lado}_mva') for lado in ('hv', 'mv', 'lv')}
                 for e in red.de_tipo('trafo3') if any(e.get(f'sn_carga_{lado}_mva') for lado in ('hv', 'mv', 'lv'))}
    avisos = list(net.get('avisos_consigna') or []) + ([aviso_alta] if aviso_alta else [])
    aproximados = sorted(g['id'] for g in red.de_tipo('red_externa') if g.get('estatismo_aproximado'))
    if aproximados:
        # 107:RF-34: la limitación, dicha: con otra carga el SVC no reparte por estatismo.
        avisos.append(f"{', '.join(aproximados)}: estatismo aproximado por la tensión resuelta en el caso exportado; con "
                      'otra carga el SVC no reparte por estatismo')
    if avisos:
        res.mensaje = '; '.join(avisos)
    vm = net.res_bus.vm_pu
    for nombre, i in bus.items():
        # 107:RF-29: en la nominal propia de la barra, la que da DIgSILENT.
        v = float(vm.at[i]) * float(net.bus.vn_kv.at[i]) / float(net.bus.kv_propio.at[i])
        if math.isnan(v):
            res.sin_tension.append(nombre)
        else:
            res.tensiones_pu[nombre] = v
    for tabla, ids, p, q in ((net.res_line, lineas, 'p_from_mw', 'q_from_mvar'),
                             (net.res_trafo, trafos, 'p_hv_mw', 'q_hv_mvar'),
                             (net.res_trafo3w, trafos3, 'p_hv_mw', 'q_hv_mvar')):
        for nombre, i in ids.items():
            c = float(tabla.loading_percent.at[i])
            if tabla is net.res_trafo3w and nombre in carga_tr3:
                c = _cargabilidad_tr3(net, i, carga_tr3[nombre])
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
