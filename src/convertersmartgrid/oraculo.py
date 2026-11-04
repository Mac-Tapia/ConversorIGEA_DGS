"""Oráculo independiente: el modelo, calculado con pandapower antes de escribir el DGS.

Por qué hace falta. PowerFactory importa casi cualquier cosa: un DGS con toda la red a
0,4 Ω/km, con una SED de 50 kVA que alimenta 1,2 MW o con una rama sin camino a la
fuente se importa sin una queja, y el error aparece horas después, cuando el flujo no
converge o converge con números creíbles y equivocados. pandapower resuelve la misma
red en segundos, sin licencia y en el mismo proceso que el conversor, así que cada
alimentador sale del lote con un veredicto físico además del estructural de
:mod:`convertersmartgrid.validate`.

Qué red calcula. **La que se escribe en el DGS**, no una aproximación:

* una barra por nodo a la tensión del alimentador, y la red externa en la cabecera;
* cada tramo con R1, X1 y la susceptancia B1 del catálogo (µS/km, como ``TypLne.bline``);
* cada SED como en :mod:`convertersmartgrid.dgs`: barra de MT → transformador (misma potencia,
  uk y pérdidas que ``TypTr2``) → barra de 0,22 kV con su carga detrás;
* las cargas sin SED, en su barra de MT;
* seccionadores e interruptores en su extremo de tramo, y los acopladores de los
  puentes fundidos, con su estado normal.

:func:`validar` no corrige. Un veredicto de tensión baja o de sobrecarga describe la red
y no es un error de conversión. Cambiarlo para que «salga bien» produciría justo la
clase de modelo que este proyecto no quiere: uno que converge con datos inventados.
Las correcciones con regla explícita están en :mod:`convertersmartgrid.saneamiento`.

La única corrección propia es :func:`corregir_para_converger` (spec 057), y solo sobre un
dato que falta: la demanda de relleno o mayor que su SED, que pasa a la potencia
instalada que sí trae la fuente, con regla y anotada. Caso real: ELOR25_V2 trae 39 kW en
todas sus SED y NJA202 no convergía ni en DIgSILENT ni aquí.

Donde la red tiene tramos o cargas de menos de tres fases, el veredicto sale del flujo
**desequilibrado**, el mismo que corre DIgSILENT (054:RF-7), y el equilibrado queda como
comparación (082:RF-5, RF-8). Con el equilibrado solo, TI01 de Electro Sur Este daba 0,802 p.u. y
en DIgSILENT tenía 0,790: se importaba por debajo del umbral.

Nada del modelo queda fuera de la red (082:RF-1 a RF-4): un elemento con datos incompletos se
calcula como se pueda y se anota, y ``recuento`` cuadra el modelo con la red por clase. Sin los
bancos, C+æ02 de Luz del Sur daba 0,80 p.u. con 4,6 MW donde DIgSILENT da 0,93, y el oráculo le
quitaba más de la mitad de la demanda sin motivo.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from .model import FeederModel

#: Frecuencia de la red peruana, la misma que ``frnom`` en el DGS.
FRECUENCIA_HZ = 60.0

#: Banda de tensión que se informa como aviso (NTCSE, redes de MT urbanas: ±5 %; se
#: deja algo de holgura porque el flujo es equilibrado).
BANDA_AVISO_PU = (0.925, 1.075)

#: Por debajo de esto no es una red cargada, es un dato roto. En 260924.mdb, la SED
#: SE50111 con 1.197 kW sobre 50 kVA dejaba su barra de baja en 0,6 p.u.
TENSION_DATO_ROTO_PU = 0.80

#: Pérdidas por encima de este porcentaje de la carga delatan impedancias imposibles
#: (un conductor con R de otro orden de magnitud, una longitud en km leída como m).
PERDIDAS_SOSPECHOSAS_PCT = 15.0

#: 082:RF-6: la red externa que pide ``runpp_3ph``. Una cabecera firme, como la ElmXnet del DGS.
_RED_EXTERNA_3F = {'s_sc_max_mva': 1000.0, 'rx_max': 0.1, 'r0x0_max': 1.0, 'x0x_max': 1.0}

#: 082:RF-15: ``uk`` que DIgSILENT da a un ``TypVoltreg`` que no lo dice, y que el DGS no escribe
#: (leído en C+æ02, 2026-11-03). Con X = uk·Un/In, por fase, el oráculo da su misma P y Q.
UK_REGULADOR_PCT = 0.3
#: El tipo no tiene pérdidas (``pcu`` = 0); pandapower no admite R nula en una línea.
_R_REGULADOR_OHM = 1e-6

#: Longitud mínima para pandapower, que no admite líneas de 0 km. Solo afecta al
#: cálculo del oráculo: el modelo y el DGS conservan la longitud de la fuente.
_LONGITUD_MIN_KM = 1e-6

#: Por debajo de esta longitud un tramo se calcula como una conexión (interruptor
#: entre barras) y no como una línea. Un tramo de 0 m llevado a 1 mm daba una
#: impedancia de 10⁻⁷ Ω junto a tramos de decenas de metros: la matriz quedaba mal
#: condicionada y el flujo «no convergía» en redes sanas. Pasaba con toda carga en el
#: punto medio de la disposición completa, que cuelga de una derivación virtual de
#: 0 m. A partir de 1 cm sí converge, y 1 cm de cable no mueve la tensión.
_LARGO_CONEXION_M = 0.01


@dataclass(frozen=True)
class Hallazgo:
    gravedad: str       # 'error' | 'aviso'
    codigo: str         # identificador estable, para filtrar y contar
    texto: str
    elemento: str = ''

    def linea(self) -> str:
        donde = f' [{self.elemento}]' if self.elemento else ''
        return f'{self.gravedad.upper()} {self.codigo}{donde}: {self.texto}'


@dataclass
class InformeOraculo:
    disponible: bool = True
    motivo_no_disponible: str = ''
    convergio: bool = False
    barras: int = 0
    lineas: int = 0
    transformadores: int = 0
    cargas: int = 0
    v_min_pu: float | None = None
    v_max_pu: float | None = None
    barra_v_min: str = ''
    carga_linea_max_pct: float | None = None
    linea_mas_cargada: str = ''
    carga_trafo_max_pct: float | None = None
    trafo_mas_cargado: str = ''
    p_carga_mw: float = 0.0
    p_fuente_mw: float | None = None
    perdidas_mw: float | None = None
    barras_sin_alimentar: int = 0
    #: 082:RF-5: «equilibrado» o «desequilibrado», el flujo del que sale el veredicto.
    flujo: str = 'equilibrado'
    #: 082:RF-7: la tensión mínima de cada fase, en las barras que la tienen.
    v_min_fase: dict[str, float] = field(default_factory=dict)
    #: 082:RF-8: lo que da el flujo equilibrado cuando el veredicto es del desequilibrado.
    equilibrado: dict[str, Any] = field(default_factory=dict)
    #: 082:RF-3: {clase: {'modelo': n, 'red': m}}.
    recuento: dict[str, dict[str, int]] = field(default_factory=dict)
    hallazgos: list[Hallazgo] = field(default_factory=list)

    @property
    def errores(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.gravedad == 'error']

    @property
    def avisos(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.gravedad == 'aviso']

    @property
    def veredicto(self) -> str:
        """``no_disponible`` | ``errores`` | ``avisos`` | ``ok``."""
        if not self.disponible:
            return 'no_disponible'
        if self.errores:
            return 'errores'
        return 'avisos' if self.avisos else 'ok'

    def resumen(self) -> str:
        if not self.disponible:
            return f'oráculo no disponible: {self.motivo_no_disponible}'
        if not self.convergio:
            return f'NO CONVERGE ({len(self.errores)} error(es))'
        return (f'converge; V {self.v_min_pu:.3f}–{self.v_max_pu:.3f} p.u.; '
                f'pérdidas {self.perdidas_mw * 1000:.1f} kW; '
                f'{len(self.errores)} error(es), {len(self.avisos)} aviso(s)')

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d['hallazgos'] = [asdict(h) for h in self.hallazgos]
        d['veredicto'] = self.veredicto
        d['resumen'] = self.resumen()
        return d


def disponible() -> bool:
    try:
        import pandapower  # noqa: F401
    except ImportError:
        return False
    return True


# ---------------------------------------------------------------- construcción de la red

def tiene_fases(model: FeederModel) -> bool:
    """Si algún tramo o carga ocupa menos de tres fases: pide el desequilibrado (082:RF-5)."""
    from .dgs import letras_de_fase

    return (any(len(letras_de_fase(ln.phase)) < 3 for ln in model.lines)
            or any(len(letras_de_fase(c.phase)) < 3 for c in model.loads))


def red_pandapower(model: FeederModel, consigna_pu: float = 1.0, *, por_fases: bool = False):
    """La red del DGS en pandapower. Devuelve ``(net, barra_de_nodo, informe_parcial)``.

    Con ``por_fases``, lista para ``runpp_3ph``: cada carga en sus fases, las secuencias cero del
    catálogo y las SED de menos de tres fases con su transformador (082:RF-6).

    Con la red unida (spec 022), cada barra a su tensión, una red externa por barra de SET
    y por cada alimentador «Sin SET» (o por alimentador, sin estructura), con
    ``consigna_pu``; los interruptores de cabecera y los enlaces como estén.
    """
    import pandapower as pp

    from .dgs import (REF_SED_LV_KV, REF_TR2_UK_PCT, tr2_curmg_pct, tr2_losses_kw,
                      tr2_strn_mva, letras_de_fase)
    from .model import resolve_capacitor_capacity

    informe = InformeOraculo()
    kv = float(model.nominal_kv)
    net = pp.create_empty_network(name=model.name, f_hz=FRECUENCIA_HZ)

    # 082:RF-2: un elemento que cuelga de un nodo sin definir no se salta: su barra se crea, sin
    # camino a la fuente, y el veredicto dice que está sin alimentar.
    citados = {n for ln in model.lines for n in (ln.from_node, ln.to_node)}
    citados.update(s.node_id for s in model.seds)
    citados.update(c.node_id for c in model.loads)
    citados.update(b.node_id for b in model.capacitors)
    citados.update(n for cp in model.couplers for n in (cp.node_a, cp.node_b))
    sin_definir = sorted(citados - set(model.nodes))
    if sin_definir:
        informe.hallazgos.append(Hallazgo(
            'aviso', 'nodo_sin_definir',
            f'{len(sin_definir)} nodo(s) citados y sin definir, calculados sin camino a la fuente: '
            + ', '.join(sin_definir[:5]) + ('…' if len(sin_definir) > 5 else '')))
    nodos = sorted(citados | set(model.nodes))
    info = getattr(model, 'combined', None)

    def kv_de(n: str) -> float:
        return float(info.node_kv.get(n, kv)) if info is not None else kv

    idx = pp.create_buses(net, len(nodos), vn_kv=[kv_de(n) for n in nodos], name=nodos)
    barra = dict(zip(nodos, (int(i) for i in idx)))
    if info is not None:
        from .enlaces import fuentes_de
        for nodo, nombre in sorted(fuentes_de(model).items()):
            if nodo in barra:
                pp.create_ext_grid(net, barra[nodo], vm_pu=consigna_pu, name=nombre, **_RED_EXTERNA_3F)
    else:
        pp.create_ext_grid(net, barra[model.source_node], vm_pu=consigna_pu, name='FUENTE',
                           **_RED_EXTERNA_3F)

    # --- tramos
    lineas = sorted(model.lines, key=lambda ln: ln.section_id)
    omega = 2.0 * math.pi * FRECUENCIA_HZ
    desde, hasta, largo, r, x, c, imax, nombres = [], [], [], [], [], [], [], []
    r0, x0 = [], []
    conexiones = []
    for ln in lineas:
        typ = model.line_types.get(ln.type_key)
        if typ is None:
            # 082:RF-1: se calcula como conexión; el error sigue en pie, sin dar un OK falso.
            informe.hallazgos.append(Hallazgo('error', 'tipo_ausente',
                                              f'tipo {ln.type_key!r} sin definir', ln.section_id))
            conexiones.append(ln)
            continue
        if ln.length_m < _LARGO_CONEXION_M:
            # Ver _LARGO_CONEXION_M: se calcula como conexión, no como línea, así que
            # su impedancia no interviene y no se comprueba.
            conexiones.append(ln)
            continue
        if typ.r1_ohm_km <= 0 and typ.x1_ohm_km <= 0:
            informe.hallazgos.append(Hallazgo(
                'error', 'impedancia_nula',
                f'el tipo {typ.code} tiene R1 = X1 = 0: impedancia nula, calculado como conexión',
                ln.section_id))
            conexiones.append(ln)
            continue
        if typ.r1_ohm_km < 0 or typ.x1_ohm_km < 0:
            informe.hallazgos.append(Hallazgo(
                'error', 'impedancia_negativa',
                f'el tipo {typ.code} tiene R1={typ.r1_ohm_km} X1={typ.x1_ohm_km} Ω/km, calculado '
                'como conexión', ln.section_id))
            conexiones.append(ln)
            continue
        desde.append(barra[ln.from_node])
        hasta.append(barra[ln.to_node])
        largo.append(max(ln.length_m / 1000.0, _LONGITUD_MIN_KM))
        r.append(typ.r1_ohm_km)
        x.append(typ.x1_ohm_km)
        r0.append(typ.r0_ohm_km if typ.r0_ohm_km > 0 else typ.r1_ohm_km)
        x0.append(typ.x0_ohm_km if typ.x0_ohm_km > 0 else typ.x1_ohm_km)
        # B1 del catálogo en µS/km → capacidad en nF/km.
        c.append(max(typ.b1_source, 0.0) * 1e3 / omega)
        imax.append(typ.ampacity_a / 1000.0 if typ.ampacity_a > 0 else 99.0)
        nombres.append(ln.section_id)
    linea_de: dict[str, int] = {}
    if desde:
        ids = pp.create_lines_from_parameters(
            net, desde, hasta, largo, r_ohm_per_km=r, x_ohm_per_km=x, c_nf_per_km=c,
            max_i_ka=imax, name=nombres,
            **({'r0_ohm_per_km': r0, 'x0_ohm_per_km': x0, 'c0_nf_per_km': c} if por_fases else {}))
        linea_de = dict(zip(nombres, (int(i) for i in ids)))

    # --- maniobras en extremo de tramo y acopladores (puentes fundidos)
    sw_bus, sw_el, sw_et, sw_closed, sw_name = [], [], [], [], []
    extremos = {ln.section_id: ln for ln in lineas}
    de_conexion = {ln.section_id for ln in conexiones}
    sin_tramo, fuera_de_extremo, maniobras_en_red = [], [], 0
    for dev in sorted(model.devices, key=lambda d: (d.section_id, d.terminal_side, d.eq_number)):
        if dev.section_id in linea_de:
            # 082:RF-2: una maniobra que no apunta a un extremo de su tramo se pone en el de
            # origen: abierta tiene que seguir cortándolo.
            ln = extremos[dev.section_id]
            nodo = dev.node_id if dev.node_id in (ln.from_node, ln.to_node) else ln.from_node
            if nodo != dev.node_id:
                fuera_de_extremo.append(dev.eq_number or dev.eq_id or dev.section_id)
            sw_bus.append(barra[nodo]); sw_el.append(linea_de[dev.section_id])
            sw_et.append('l'); sw_closed.append(dev.on_off == 1)
            sw_name.append(dev.eq_number or dev.eq_id or dev.section_id)
            maniobras_en_red += 1
        elif dev.section_id in de_conexion:
            maniobras_en_red += 1                # la lleva el tramo-conexión (``abiertos``)
        else:
            sin_tramo.append(dev.eq_number or dev.eq_id or dev.section_id)
    if fuera_de_extremo:
        informe.hallazgos.append(Hallazgo(
            'aviso', 'maniobra_fuera_de_extremo',
            f'{len(fuera_de_extremo)} maniobra(s) que no apuntan a un extremo de su tramo, puestas '
            'en el de origen: ' + ', '.join(fuera_de_extremo[:5])))
    if sin_tramo:
        informe.hallazgos.append(Hallazgo(
            'aviso', 'maniobra_sin_tramo',
            f'{len(sin_tramo)} maniobra(s) de un tramo que no existe, sin efecto en el flujo: '
            + ', '.join(sin_tramo[:5])))
    reguladores = 0
    for cp in model.couplers:
        datos = cp.regulador
        if datos is not None and float(datos.corriente_a or 0.0) > 0:
            # 082:RF-15: un regulador no es un interruptor. En C+æ02 sus 3 consumían 0,23 Mvar en
            # DIgSILENT, y sin ellos el oráculo erraba 0,92 puntos; con esta X, 0,00 (2026-11-03).
            kv_reg = float(datos.nominal_kv or kv_de(cp.node_a))
            x_reg = UK_REGULADOR_PCT / 100.0 * kv_reg * 1000.0 / math.sqrt(3.0) / float(datos.corriente_a)
            pp.create_line_from_parameters(
                net, barra[cp.node_a], barra[cp.node_b], 1.0, _R_REGULADOR_OHM, x_reg, 0.0,
                float(datos.corriente_a) / 1000.0, name=cp.name, in_service=cp.on_off == 1,
                **({'r0_ohm_per_km': _R_REGULADOR_OHM, 'x0_ohm_per_km': x_reg, 'c0_nf_per_km': 0.0}
                   if por_fases else {}))
            reguladores += 1
            continue
        sw_bus.append(barra[cp.node_a]); sw_el.append(barra[cp.node_b])
        sw_et.append('b'); sw_closed.append(cp.on_off == 1); sw_name.append(cp.name)
    # Los tramos-conexión: abiertos si alguna maniobra de ese tramo lo está, como
    # habría quedado la línea con su maniobra abierta.
    abiertos = {d.section_id for d in model.devices if d.on_off != 1}
    for ln in conexiones:
        sw_bus.append(barra[ln.from_node]); sw_el.append(barra[ln.to_node])
        sw_et.append('b'); sw_closed.append(ln.section_id not in abiertos)
        sw_name.append(ln.section_id)
    if sw_bus:
        pp.create_switches(net, sw_bus, sw_el, sw_et, closed=sw_closed, name=sw_name)

    # --- SED: transformador con la carga detrás, como en el DGS
    lado_baja: dict[tuple[str, str], int] = {}
    fase_de_carga = {(c.section_id, c.device_number): letras_de_fase(c.phase) for c in model.loads}
    fases_de_barra: dict[int, str] = {}
    for sed in sorted(model.seds, key=lambda s: s.load_key):
        strn = tr2_strn_mva(sed.design_kva)
        kva = strn * 1000.0
        pcu_kw, pfe_kw = tr2_losses_kw(kva, uk_pct=REF_TR2_UK_PCT)
        bt = int(pp.create_bus(net, vn_kv=REF_SED_LV_KV, name=f'{sed.loc_name}_BT'))
        i0 = tr2_curmg_pct(kva, pfe_kw)
        extra: dict[str, Any] = {}
        if por_fases:
            # 082:RF-6: pandapower solo tiene trafos de tres columnas. Una SED de n fases se da
            # como YNyn de 3/n su potencia, que deja a cada fase la suya y deja pasar la secuencia
            # cero; la de tres fases, Dyn como en el DGS.
            letras = fase_de_carga.get(sed.load_key, 'ABC')
            fases_de_barra[bt] = letras
            multiplo = 3.0 / len(letras)
            strn, i0 = strn * multiplo, i0 / multiplo
            extra = {'vector_group': 'Dyn' if len(letras) == 3 else 'YNyn',
                     'vk0_percent': REF_TR2_UK_PCT, 'vkr0_percent': pcu_kw / kva * 100.0,
                     # 100 veces Z0: con 100 % la secuencia cero se iba por la magnetización y una
                     # SED monofásica caía de menos (lo destapó 082:RF-5).
                     'mag0_percent': 10_000.0, 'mag0_rx': 0.0, 'si0_hv_partial': 0.9}
        pp.create_transformer_from_parameters(
            net, barra[sed.node_id], bt, sn_mva=strn, vn_hv_kv=kv_de(sed.node_id),
            vn_lv_kv=REF_SED_LV_KV,
            vk_percent=REF_TR2_UK_PCT, vkr_percent=pcu_kw / kva * 100.0, pfe_kw=pfe_kw,
            i0_percent=i0, name=f'TR_{sed.loc_name}', **extra)
        lado_baja[sed.load_key] = bt

    # --- cargas
    c_bus, c_p, c_q, c_name = [], [], [], []
    for load in sorted(model.loads, key=lambda ld: (ld.section_id, ld.device_number)):
        clave = (load.section_id, load.device_number)
        bus = lado_baja.get(clave, barra[load.node_id])
        nombre = load.display_name or load.device_number or load.section_id
        letras = letras_de_fase(load.phase)
        if por_fases and len(letras) < 3:
            _carga_por_fases(pp, net, bus, letras, load.p_mw, load.q_mvar, nombre)
            continue
        c_bus.append(bus); c_p.append(load.p_mw); c_q.append(load.q_mvar)
        c_name.append(nombre)
    if c_bus:
        pp.create_loads(net, c_bus, c_p, q_mvar=c_q, name=c_name)
    cargas_asimetricas = len(net.asymmetric_load)

    # --- bancos de condensadores, los mismos que escribe el DGS (082:RF-4)
    sin_potencia, bancos_en_red = [], 0
    for banco in sorted(model.capacitors, key=lambda b: (b.network_id, b.capacitor_id, b.node_id)):
        kv_bus = kv_de(banco.node_id)
        total = resolve_capacitor_capacity(banco, kv_bus).total_kvar
        if total is None:
            sin_potencia.append(banco.capacitor_id)
            continue
        letras = letras_de_fase(banco.phases)
        if por_fases and len(letras) < 3:
            _carga_por_fases(pp, net, barra[banco.node_id], letras, 0.0, -float(total) / 1000.0,
                             f'banco {banco.capacitor_id}', en_servicio=bool(banco.in_service))
        else:
            pp.create_shunt(net, barra[banco.node_id], q_mvar=-float(total) / 1000.0, p_mw=0.0,
                            vn_kv=float(banco.nominal_kv or kv_bus), name=banco.capacitor_id,
                            in_service=bool(banco.in_service))
        bancos_en_red += 1
    if sin_potencia:
        informe.hallazgos.append(Hallazgo(
            'aviso', 'banco_sin_potencia',
            f'{len(sin_potencia)} banco(s) sin potencia en la fuente ni en el catálogo: '
            + ', '.join(sorted(sin_potencia)[:5])))

    informe.barras = len(net.bus)
    informe.lineas = len(net.line) - reguladores
    informe.transformadores = len(net.trafo)
    informe.cargas = len(net.load) + cargas_asimetricas
    informe.p_carga_mw = _p_carga(net)
    # 082:RF-3: se cuenta lo que entró, no lo que se quiso meter.
    informe.recuento = {
        'tramos': {'modelo': len(model.lines), 'red': informe.lineas + len(conexiones)},
        'sed': {'modelo': len(model.seds), 'red': len(net.trafo)},
        'cargas': {'modelo': len(model.loads), 'red': informe.cargas},
        'bancos': {'modelo': len(model.capacitors), 'red': bancos_en_red},
        'maniobras': {'modelo': len(model.devices), 'red': maniobras_en_red},
        'acopladores': {'modelo': len(model.couplers), 'red': len(model.couplers)},
    }
    anotados = {'bancos': len(sin_potencia), 'maniobras': len(sin_tramo)}
    faltan = {clase: n['modelo'] - n['red'] for clase, n in informe.recuento.items()
              if n['modelo'] - n['red'] != anotados.get(clase, 0)}
    if faltan:
        informe.hallazgos.append(Hallazgo(
            'error', 'omitido_en_la_red', f'el modelo y la red no cuadran: {faltan}'))
    if por_fases:
        fases_nodo: dict[str, set[str]] = {}
        for ln in model.lines:
            for n in (ln.from_node, ln.to_node):
                fases_nodo.setdefault(n, set()).update(letras_de_fase(ln.phase))
        for s in model.seds:
            fases_nodo.setdefault(s.node_id, set()).update(fase_de_carga.get(s.load_key, 'ABC'))
        fases_de_barra.update({i: ''.join(sorted(fases_nodo.get(n) or 'ABC'))
                               for n, i in barra.items()})
        net['fases_de_barra'] = fases_de_barra
    return net, barra, informe


def _carga_por_fases(pp, net, bus: int, letras: str, p: float, q: float, nombre: str,
                     *, en_servicio: bool = True) -> None:
    """Una carga de una fase, o entre dos (``delta``: ``a`` es AB, ``b`` BC y ``c`` CA)."""
    if len(letras) == 1:
        f = letras.lower()
        pp.create_asymmetric_load(net, bus, name=nombre, in_service=en_servicio,
                                  **{f'p_{f}_mw': p, f'q_{f}_mvar': q})
    else:
        f = {'AB': 'a', 'BC': 'b', 'AC': 'c'}[letras]
        pp.create_asymmetric_load(net, bus, name=nombre, type='delta', in_service=en_servicio,
                                  **{f'p_{f}_mw': p, f'q_{f}_mvar': q})


def _p_carga(net) -> float:
    total = float(net.load.p_mw.sum()) if len(net.load) else 0.0
    if len(net.asymmetric_load):
        total += float(net.asymmetric_load[['p_a_mw', 'p_b_mw', 'p_c_mw']].sum().sum())
    return total


# ------------------------------------------------------------------- resultados de un flujo

def _ejecutar(pp, net) -> None:
    if 'fases_de_barra' in net:
        from pandapower.pf.runpp_3ph import runpp_3ph

        runpp_3ph(net, init='auto', max_iteration=50, numba=False)
    else:
        # numba=False: sin numba instalado, runpp imprime en cada llamada un aviso de
        # cuatro líneas; en un lote de 96 alimentadores eran 96 avisos que tapaban el
        # Registro. Sin numba, los 96 alimentadores de la entrega de 03/08 se calcularon
        # en 31 s, que es aceptable para una validación previa.
        pp.runpp(net, algorithm='nr', init='auto', max_iteration=30,
                 calculate_voltage_angles=False, numba=False)


def _tensiones(net):
    """La tensión de cada barra alimentada: por fases, la menor de las que la barra tiene."""
    if 'fases_de_barra' not in net:
        return net.res_bus.vm_pu.dropna()
    tabla = net.res_bus_3ph[['vm_a_pu', 'vm_b_pu', 'vm_c_pu']].copy()
    for barra_id, letras in net['fases_de_barra'].items():
        for letra in 'ABC':
            if letra not in letras:
                tabla.at[barra_id, f'vm_{letra.lower()}_pu'] = float('nan')
    return tabla.min(axis=1, skipna=True).dropna()


def _p_fuente(net, eg: int | None = None) -> float:
    if 'fases_de_barra' not in net:
        p = net.res_ext_grid.p_mw
        return float(p.sum() if eg is None else p.at[eg])
    p = net.res_ext_grid_3ph[['p_a_mw', 'p_b_mw', 'p_c_mw']]
    return float((p.sum() if eg is None else p.loc[eg]).sum())


def _carga_lineas(net):
    tabla = net.res_line_3ph if 'fases_de_barra' in net else net.res_line
    return tabla.loading_percent.dropna()


def _carga_trafos(net):
    tabla = net.res_trafo_3ph if 'fases_de_barra' in net else net.res_trafo
    return tabla.loading_percent.dropna()


# ---------------------------------------------------------------------------- veredicto

def validar(model: FeederModel, *, comparar: bool = True) -> InformeOraculo:
    """Calcula el alimentador y devuelve el veredicto. Nunca modifica el modelo.

    ``comparar=False`` se ahorra el flujo equilibrado de comparación (082:RF-8): la bisección de la
    corrección solo necesita el veredicto.
    """
    if getattr(model, 'combined', None) is not None:
        return InformeOraculo(disponible=False, motivo_no_disponible=(
            'red unida de varios alimentadores: conviven tensiones distintas'))
    if not disponible():
        return InformeOraculo(disponible=False, motivo_no_disponible='pandapower no está instalado')

    import pandapower as pp
    from pandapower import topology

    por_fases = tiene_fases(model)
    net, _barra, informe = red_pandapower(model, por_fases=por_fases)
    informe.flujo = 'desequilibrado' if por_fases else 'equilibrado'

    # Barras sin camino a la fuente con los interruptores en su estado normal. Las
    # que llevan carga son un error: esa demanda no la atiende nadie en el flujo.
    sin_alimentar = set(topology.unsupplied_buses(net))
    informe.barras_sin_alimentar = len(sin_alimentar)
    if sin_alimentar:
        con_carga = sorted({str(net.bus.at[b, 'name']) for b in net.load.bus if b in sin_alimentar})
        if con_carga:
            informe.hallazgos.append(Hallazgo(
                'error', 'carga_sin_alimentar',
                f'{len(con_carga)} barra(s) con carga sin camino a la fuente con las '
                f'maniobras en su estado normal: {", ".join(con_carga[:5])}'
                + ('…' if len(con_carga) > 5 else '')))
        else:
            informe.hallazgos.append(Hallazgo(
                'aviso', 'barras_sin_alimentar',
                f'{len(sin_alimentar)} barra(s) sin alimentar y sin carga (ramales tras un '
                'seccionador abierto)'))
        # pandapower las deja fuera del cálculo por su cuenta; se sigue.

    try:
        _ejecutar(pp, net)
        informe.convergio = bool(net.converged)
    except Exception as exc:  # noqa: BLE001 - pandapower lanza varias clases al no converger
        informe.convergio = False
        informe.hallazgos.append(Hallazgo(
            'error', 'no_converge',
            f'el flujo de potencia no converge ({exc.__class__.__name__}). Suele deberse a '
            'una carga o un transformador fuera de escala, o a una impedancia imposible.'))
        return informe

    vm = _tensiones(net)
    # 082:RF-9: ``runpp_3ph`` dice «convergió» con todas las tensiones en nan (TI01 y C+æ02 con
    # toda su demanda): una barra alimentada sin tensión es que no convergió.
    if set(net.bus.index) - sin_alimentar - set(vm.index):
        informe.convergio = False
        informe.hallazgos.append(Hallazgo(
            'error', 'no_converge',
            'el flujo de potencia no converge (barras alimentadas sin tensión). Suele deberse a '
            'una carga o un transformador fuera de escala, o a una impedancia imposible.'))
        return informe
    if por_fases:
        tabla = net.res_bus_3ph
        for letra in 'ABC':
            con = [b for b, f in net['fases_de_barra'].items() if letra in f and b in vm.index]
            valores = tabla.loc[con, f'vm_{letra.lower()}_pu'].dropna()
            if len(valores):
                informe.v_min_fase[letra] = round(float(valores.min()), 4)
        if comparar:
            informe.equilibrado = _comparar_equilibrado(pp, model)
    if len(vm):
        informe.v_min_pu = round(float(vm.min()), 4)
        informe.v_max_pu = round(float(vm.max()), 4)
        informe.barra_v_min = str(net.bus.at[vm.idxmin(), 'name'])
        rotas = vm[vm < TENSION_DATO_ROTO_PU]
        if len(rotas):
            peores = ', '.join(f'{net.bus.at[b, "name"]} ({v:.2f})' for b, v in rotas.nsmallest(5).items())
            informe.hallazgos.append(Hallazgo(
                'error', 'tension_imposible',
                f'{len(rotas)} barra(s) por debajo de {TENSION_DATO_ROTO_PU} p.u.: {peores}. '
                'No es una red cargada, es un dato roto (carga o transformador fuera de escala).'))
        fuera = vm[(vm < BANDA_AVISO_PU[0]) | (vm > BANDA_AVISO_PU[1])]
        if len(fuera) and not len(rotas):
            informe.hallazgos.append(Hallazgo(
                'aviso', 'tension_fuera_de_banda',
                f'{len(fuera)} barra(s) fuera de {BANDA_AVISO_PU[0]}–{BANDA_AVISO_PU[1]} p.u. '
                f'(mínima {informe.v_min_pu} en {informe.barra_v_min}).'))

    if len(net.line):
        carga = _carga_lineas(net)
        if len(carga):
            informe.carga_linea_max_pct = round(float(carga.max()), 1)
            informe.linea_mas_cargada = str(net.line.at[carga.idxmax(), 'name'])
            sobre = carga[carga > 100.0]
            if len(sobre):
                informe.hallazgos.append(Hallazgo(
                    'aviso', 'linea_sobrecargada',
                    f'{len(sobre)} tramo(s) por encima de su ampacidad (máx. '
                    f'{informe.carga_linea_max_pct} % en {informe.linea_mas_cargada}).'))
    if len(net.trafo):
        carga = _carga_trafos(net)
        if len(carga):
            informe.carga_trafo_max_pct = round(float(carga.max()), 1)
            informe.trafo_mas_cargado = str(net.trafo.at[carga.idxmax(), 'name'])
            sobre = carga[carga > 100.0]
            if len(sobre):
                informe.hallazgos.append(Hallazgo(
                    'aviso', 'trafo_sobrecargado',
                    f'{len(sobre)} transformador(es) de SED por encima de su potencia (máx. '
                    f'{informe.carga_trafo_max_pct} % en {informe.trafo_mas_cargado}).'))

    informe.p_fuente_mw = round(_p_fuente(net), 6)
    informe.perdidas_mw = round(informe.p_fuente_mw - informe.p_carga_mw, 6)
    if informe.p_carga_mw > 0:
        pct = informe.perdidas_mw / informe.p_carga_mw * 100.0
        if pct > PERDIDAS_SOSPECHOSAS_PCT:
            informe.hallazgos.append(Hallazgo(
                'aviso', 'perdidas_anomalas',
                f'pérdidas del {pct:.1f} % de la carga: delatan impedancias o longitudes '
                'fuera de escala.'))
    return informe


def _comparar_equilibrado(pp, model: FeederModel) -> dict[str, Any]:
    """082:RF-8: lo que daría el flujo equilibrado, solo para compararlo."""
    net, _barra, _informe = red_pandapower(model)
    try:
        _ejecutar(pp, net)
    except Exception as exc:  # noqa: BLE001 - pandapower lanza varias clases al no converger
        return {'convergio': False, 'motivo': exc.__class__.__name__}
    vm = _tensiones(net)
    return {'convergio': bool(net.converged),
            'v_min_pu': round(float(vm.min()), 4) if len(vm) else None,
            'p_fuente_mw': round(_p_fuente(net), 6)}


# ------------------------------------------------------- corrección antes de importar (057)

#: Ninguna SED corregida pasa de esta fracción de su potencia instalada (057:RF-3).
TOPE_CORRECCION = 0.8
#: Pasos de la bisección del factor: 0,8 / 2⁷ ≈ 0,006, más fino que lo que distingue la
#: calibración de «Sin proyecto», que parte de aquí y lo ajusta a la cabecera.
PASOS_CORRECCION = 7


@dataclass
class CorreccionOraculo:
    """Lo que hizo :func:`corregir_para_converger`. ``convergio`` es ``None`` si no hizo falta
    calcular (ninguna SED de relleno ni fuera de escala)."""

    convergio: bool | None = None
    factor: float | None = None
    cambios: list = field(default_factory=list)
    motivo: str = ''
    #: «relleno» (057) o «por_igual» (080:RF-45).
    regla: str = 'relleno'

    def as_dict(self) -> dict[str, Any]:
        # La auditoría de completitud cuadra la carga del DGS con la entrada más esta
        # diferencia (057:RF-4): la corrección es a propósito y no una pérdida.
        return {'convergio': self.convergio, 'factor': self.factor, 'sed': len(self.cambios),
                'delta_kw': round(sum(c.p_nuevo_kw - c.p_fuente_kw for c in self.cambios), 6),
                'delta_kvar': round(sum(c.q_nuevo_kvar - c.q_fuente_kvar for c in self.cambios), 6),
                'lineas': [c.linea() for c in self.cambios], 'motivo': self.motivo}


def _reducir_por_igual(model: FeederModel, original: list, res: CorreccionOraculo,
                       pasos: int) -> CorreccionOraculo:
    """080:RF-45, 015:RF-38: todas las cargas por un mismo factor, conservando su reparto.

    Es el mayor con el que el flujo converge sin tensiones imposibles. Si ninguno sirve, el
    modelo queda como estaba y se dice: la causa no es la demanda.
    """
    from dataclasses import replace

    from .sed_potencia import CorreccionDemanda

    def aplicar(f: float) -> None:
        model.loads = [replace(c, p_mw=c.p_mw * f, q_mvar=c.q_mvar * f) for c in original]

    def sirve(f: float) -> bool:
        aplicar(f)
        informe = validar(model, comparar=False)
        return informe.convergio is True and not informe.errores

    mejor, bajo, alto = None, 0.0, 1.0
    for _ in range(pasos):
        medio = (bajo + alto) / 2.0
        if sirve(medio):
            mejor, bajo = medio, medio
        else:
            alto = medio
    if mejor is None:
        model.loads = list(original)
        res.convergio = False
        res.motivo = (f'ni con toda la demanda al {1 / 2 ** pasos:.1%} converge el flujo: la causa '
                      'no es la demanda (vea los hallazgos del oráculo)')
        return res
    aplicar(mejor)
    res.convergio, res.factor, res.regla = True, round(mejor, 6), 'por_igual'
    res.cambios = [CorreccionDemanda(
        c.device_number, float(getattr(c, 'connected_kva', 0.0) or 0.0),
        round(c.p_mw * 1000.0, 6), round(c.p_mw * mejor * 1000.0, 6), 'reducción por igual',
        round(c.q_mvar * 1000.0, 6), round(c.q_mvar * mejor * 1000.0, 6)) for c in original]
    return res


def corregir_para_converger(model: FeederModel, *, tope: float = TOPE_CORRECCION,
                            pasos: int = PASOS_CORRECCION) -> CorreccionOraculo:
    """La corrección del «Caso base» (015:RF-38) hecha aquí, antes de importar (spec 057).

    Solo si hay SED con demanda de relleno o mayor que su potencia (057:RF-2) y el flujo no
    converge: esas SED pasan a kVA × factor con FP 0,98, con el mayor factor ≤ ``tope`` con el
    que converge. Las demás cargas quedan como las trae la fuente. Si ninguno converge, el
    modelo queda como estaba y se dice. Determinista: mismos pasos, mismo factor.
    """
    from .sed_potencia import corregir_demanda, demanda_fuera_de_escala, regla_de

    res = CorreccionOraculo()
    claves = demanda_fuera_de_escala(model)
    inf = validar(model, comparar=False)
    if not inf.disponible:
        res.motivo = inf.motivo_no_disponible
        return res
    if inf.convergio and not inf.errores:
        res.convergio = True if claves else None
        return res
    # 080:RF-43: una tensión imposible se busca corregir igual que una no convergencia.
    if any(h.codigo not in ('no_converge', 'tension_imposible') for h in inf.errores):
        # Un tramo sin impedancia o sin tipo no se arregla con la demanda: se dice tal cual.
        res.convergio = False
        res.motivo = '; '.join(h.linea() for h in inf.errores)
        return res
    original = list(model.loads)
    if not claves:
        return _reducir_por_igual(model, original, res, pasos)
    reglas = {k: regla_de(model, k) for k in claves}

    def converge(f: float) -> bool:
        model.loads = list(original)
        corregir_demanda(model, claves, f, reglas=reglas)
        # 080:RF-43: sin tensiones imposibles, o la importación lo rechazaría igualmente (TI01
        # de Electro Sur Este converge al 70 % con 0,68 p.u.).
        informe = validar(model, comparar=False)
        return bool(informe.convergio) and not informe.errores

    mejor = tope if converge(tope) else None
    if mejor is None:
        bajo, alto = 0.0, tope
        for _ in range(pasos):
            medio = (bajo + alto) / 2.0
            if converge(medio):
                mejor, bajo = medio, medio
            else:
                alto = medio
    model.loads = list(original)
    if mejor is None:
        # 080:RF-45: las otras SED también pesan (C+æ02 de Luz del Sur): ahora, todas por igual.
        return _reducir_por_igual(model, original, res, pasos)
    res.cambios = corregir_demanda(model, claves, mejor, reglas=reglas)
    res.factor = round(mejor, 6)
    res.convergio = True
    return res


# ------------------------------------------------------------------- red unida (spec 022)

@dataclass
class VeredictoIsla:
    """El flujo de la isla de una fuente: una barra de SET o un alimentador «Sin SET»."""

    fuente: str
    zonal: str = ''
    convergio: bool = False
    p_mw: float | None = None
    v_min_pu: float | None = None
    barra_v_min: str = ''
    #: Si no converge: hasta qué fracción de su carga converge, y su barra más débil y su
    #: transformador más cargado en ese punto (022:RF-33).
    escala_converge: float | None = None
    trafo_mas_cargado: str = ''
    carga_trafo_pct: float | None = None


@dataclass
class InformeUnido:
    general: InformeOraculo
    islas: list[VeredictoIsla] = field(default_factory=list)

    @property
    def convergio(self) -> bool:
        return self.general.convergio

    def por_zonal(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for i in self.islas:
            z = out.setdefault(i.zonal or 'Sin SET', {'fuentes': 0, 'p_mw': 0.0, 'no_convergen': []})
            z['fuentes'] += 1
            z['p_mw'] += i.p_mw or 0.0
            if not i.convergio:
                z['no_convergen'].append(i.fuente)
        return out

    def as_dict(self) -> dict[str, Any]:
        return {'general': self.general.as_dict(), 'islas': [asdict(i) for i in self.islas],
                'por_zonal': self.por_zonal()}


def _flujo(pp, net) -> bool:
    try:
        _ejecutar(pp, net)
        return bool(net.converged) and bool(_tensiones(net).notna().any())
    except Exception:  # noqa: BLE001 - pandapower lanza varias clases al no converger
        return False


def _islas(net, topology) -> list[tuple[int, set]]:
    grafo = topology.create_nxgraph(net, respect_switches=True)
    out = []
    for comp in topology.connected_components(grafo):
        for eg in net.ext_grid.index[net.ext_grid.bus.isin(comp)]:
            out.append((int(eg), set(comp)))
    return sorted(out, key=lambda p: str(net.ext_grid.at[p[0], 'name']))


def validar_unida(model: FeederModel, consigna_pu: float = 1.0) -> InformeUnido:
    """El flujo de la red unida entera, por SET y zonal (022:RF-28, RF-32, RF-33).

    Se calcula una vez. Si no converge, cada isla sola: la que no converge se nombra, con
    la fracción de su carga con la que sí converge y, en ese punto, su barra más débil y
    su transformador más cargado. En NA205 (2026-10-17) eso habría señalado SE50293: un
    cliente de 1 392 kW en 125 kVA que estancaba el Newton.
    """
    if not disponible():
        return InformeUnido(InformeOraculo(disponible=False,
                                           motivo_no_disponible='pandapower no está instalado'))
    import pandapower as pp
    from pandapower import topology

    por_fases = tiene_fases(model)                                       # 082:RF-10
    net, _barra, informe = red_pandapower(model, consigna_pu, por_fases=por_fases)
    informe.flujo = 'desequilibrado' if por_fases else 'equilibrado'
    resultado = InformeUnido(informe)
    info = model.combined
    zonal_de_fuente: dict[str, str] = {}
    if info is not None:
        zonal_de_fuente = {b.set_codigo: b.zonal for b in info.barras_set}
        zonal_de_fuente.update({f: info.zonal_de.get(f, '') for f in info.sin_set})
    islas = _islas(net, topology)
    for eg, _buses in islas:
        nombre = str(net.ext_grid.at[eg, 'name'])
        resultado.islas.append(VeredictoIsla(nombre, zonal_de_fuente.get(nombre, '')))
    informe.convergio = _flujo(pp, net)
    if informe.convergio:
        for v, (eg, buses) in zip(resultado.islas, islas):
            v.convergio = True
            _medir_isla(net, eg, buses, v)
        vm = _tensiones(net)
        if len(vm):
            informe.v_min_pu = round(float(vm.min()), 4)
            informe.v_max_pu = round(float(vm.max()), 4)
            informe.barra_v_min = str(net.bus.at[vm.idxmin(), 'name'])
        informe.p_fuente_mw = round(_p_fuente(net), 6)
        informe.perdidas_mw = round(informe.p_fuente_mw - informe.p_carga_mw, 6)
        return resultado
    # Cada isla sola, con las demás fuentes fuera de servicio.
    activa = net.ext_grid.in_service.copy()
    p0, q0 = net.load.p_mw.copy(), net.load.q_mvar.copy()
    columnas = ['p_a_mw', 'p_b_mw', 'p_c_mw', 'q_a_mvar', 'q_b_mvar', 'q_c_mvar']
    asimetricas = net.asymmetric_load[columnas].copy()

    def escalar(de_isla, asim_de_isla, f: float) -> None:
        net.load.loc[de_isla, 'p_mw'] = p0[de_isla] * f
        net.load.loc[de_isla, 'q_mvar'] = q0[de_isla] * f
        net.asymmetric_load.loc[asim_de_isla, columnas] = asimetricas[asim_de_isla] * f

    for v, (eg, buses) in zip(resultado.islas, islas):
        net.ext_grid['in_service'] = False
        net.ext_grid.at[eg, 'in_service'] = True
        v.convergio = _flujo(pp, net)
        if v.convergio:
            _medir_isla(net, eg, buses, v)
            continue
        de_isla = net.load.bus.isin(buses)
        asim_de_isla = net.asymmetric_load.bus.isin(buses)
        bajo, alto = 0.0, 1.0
        for _ in range(8):                      # la fracción de carga con la que converge
            medio = (bajo + alto) / 2
            escalar(de_isla, asim_de_isla, medio)
            if _flujo(pp, net):
                bajo = medio
            else:
                alto = medio
        escalar(de_isla, asim_de_isla, bajo)
        if bajo > 0 and _flujo(pp, net):
            v.escala_converge = round(bajo, 3)
            _medir_isla(net, eg, buses, v)
        net.load['p_mw'], net.load['q_mvar'] = p0, q0
        net.asymmetric_load[columnas] = asimetricas
        detalle = (f'; converge con el {bajo:.0%} de su carga, con la barra más débil '
                   f'{v.barra_v_min} ({v.v_min_pu} p.u.) y el transformador más cargado '
                   f'{v.trafo_mas_cargado} ({v.carga_trafo_pct} %)'
                   if v.escala_converge else '; ni con su carga reducida')
        informe.hallazgos.append(Hallazgo(
            'error', 'isla_no_converge', f'la isla de {v.fuente} no converge{detalle} (022:RF-33).',
            v.fuente))
    net.ext_grid['in_service'] = activa
    return resultado


def _medir_isla(net, eg: int, buses: set, v: VeredictoIsla) -> None:
    v.p_mw = round(_p_fuente(net, eg), 6)
    vm = _tensiones(net)
    vm = vm[vm.index.isin(buses)]
    if len(vm):
        v.v_min_pu = round(float(vm.min()), 4)
        v.barra_v_min = str(net.bus.at[vm.idxmin(), 'name'])
    if len(net.trafo):
        carga = _carga_trafos(net)
        carga = carga[carga.index.isin(net.trafo.index[net.trafo.hv_bus.isin(buses)])]
        if len(carga):
            v.carga_trafo_pct = round(float(carga.max()), 1)
            v.trafo_mas_cargado = str(net.trafo.at[carga.idxmax(), 'name'])
