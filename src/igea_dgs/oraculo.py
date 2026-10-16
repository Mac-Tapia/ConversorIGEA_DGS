"""Oráculo independiente: el modelo, calculado con pandapower antes de escribir el DGS.

Por qué hace falta. PowerFactory importa casi cualquier cosa: un DGS con toda la red a
0,4 Ω/km, con una SED de 50 kVA que alimenta 1,2 MW o con una rama sin camino a la
fuente se importa sin una queja, y el error aparece horas después, cuando el flujo no
converge o converge con números creíbles y equivocados. pandapower resuelve la misma
red en segundos, sin licencia y en el mismo proceso que el conversor, así que cada
alimentador sale del lote con un veredicto físico además del estructural de
:mod:`igea_dgs.validate`.

Qué red calcula. **La que se escribe en el DGS**, no una aproximación:

* una barra por nodo a la tensión del alimentador, y la red externa en la cabecera;
* cada tramo con R1, X1 y la susceptancia B1 del catálogo (µS/km, como ``TypLne.bline``);
* cada SED como en :mod:`igea_dgs.dgs`: barra de MT → transformador (misma potencia,
  uk y pérdidas que ``TypTr2``) → barra de 0,22 kV con su carga detrás;
* las cargas sin SED, en su barra de MT;
* seccionadores e interruptores en su extremo de tramo, y los acopladores de los
  puentes fundidos, con su estado normal.

Qué **no** hace: corregir. Un veredicto de tensión baja o de sobrecarga describe la red
y no es un error de conversión. Cambiarlo para que «salga bien» produciría justo la
clase de modelo que este proyecto no quiere: uno que converge con datos inventados.
Las correcciones con regla explícita están en :mod:`igea_dgs.saneamiento`. Este módulo
dice si el resultado se sostiene.

El flujo es **equilibrado** (secuencia positiva). Las cargas monofásicas se reparten en
las tres fases, así que la caída de tensión de un ramal monofásico se subestima. Sirve
para detectar errores de datos, que mueven la tensión decenas de puntos, no para
sustituir el estudio desequilibrado de PowerFactory.
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

def red_pandapower(model: FeederModel):
    """La red del DGS en pandapower. Devuelve ``(net, barra_de_nodo, informe_parcial)``."""
    import pandapower as pp

    from .dgs import NA205_SED_LV_KV, NA205_TR2_UK_PCT, _tr2_curmg_pct, _tr2_losses_kw, _tr2_strn_mva

    informe = InformeOraculo()
    kv = float(model.nominal_kv)
    net = pp.create_empty_network(name=model.name, f_hz=FRECUENCIA_HZ)

    nodos = sorted(model.nodes)
    idx = pp.create_buses(net, len(nodos), vn_kv=kv, name=nodos)
    barra = dict(zip(nodos, (int(i) for i in idx)))
    pp.create_ext_grid(net, barra[model.source_node], vm_pu=1.0, name='FUENTE')

    # --- tramos
    lineas = sorted(model.lines, key=lambda ln: ln.section_id)
    omega = 2.0 * math.pi * FRECUENCIA_HZ
    desde, hasta, largo, r, x, c, imax, nombres = [], [], [], [], [], [], [], []
    conexiones = []
    for ln in lineas:
        typ = model.line_types.get(ln.type_key)
        if typ is None:
            informe.hallazgos.append(Hallazgo('error', 'tipo_ausente',
                                              f'tipo {ln.type_key!r} sin definir', ln.section_id))
            continue
        if ln.length_m < _LARGO_CONEXION_M:
            # Ver _LARGO_CONEXION_M: se calcula como conexión, no como línea, así que
            # su impedancia no interviene y no se comprueba.
            conexiones.append(ln)
            continue
        if typ.r1_ohm_km <= 0 and typ.x1_ohm_km <= 0:
            informe.hallazgos.append(Hallazgo(
                'error', 'impedancia_nula',
                f'el tipo {typ.code} tiene R1 = X1 = 0: impedancia nula, el flujo no la resuelve',
                ln.section_id))
            continue
        if typ.r1_ohm_km < 0 or typ.x1_ohm_km < 0:
            informe.hallazgos.append(Hallazgo(
                'error', 'impedancia_negativa',
                f'el tipo {typ.code} tiene R1={typ.r1_ohm_km} X1={typ.x1_ohm_km} Ω/km', ln.section_id))
            continue
        desde.append(barra[ln.from_node])
        hasta.append(barra[ln.to_node])
        largo.append(max(ln.length_m / 1000.0, _LONGITUD_MIN_KM))
        r.append(typ.r1_ohm_km)
        x.append(typ.x1_ohm_km)
        # B1 del catálogo en µS/km → capacidad en nF/km.
        c.append(max(typ.b1_source, 0.0) * 1e3 / omega)
        imax.append(typ.ampacity_a / 1000.0 if typ.ampacity_a > 0 else 99.0)
        nombres.append(ln.section_id)
    linea_de: dict[str, int] = {}
    if desde:
        ids = pp.create_lines_from_parameters(
            net, desde, hasta, largo, r_ohm_per_km=r, x_ohm_per_km=x, c_nf_per_km=c,
            max_i_ka=imax, name=nombres)
        linea_de = dict(zip(nombres, (int(i) for i in ids)))

    # --- maniobras en extremo de tramo y acopladores (puentes fundidos)
    sw_bus, sw_el, sw_et, sw_closed, sw_name = [], [], [], [], []
    for dev in sorted(model.devices, key=lambda d: (d.section_id, d.terminal_side, d.eq_number)):
        if dev.section_id in linea_de and dev.node_id in barra:
            sw_bus.append(barra[dev.node_id]); sw_el.append(linea_de[dev.section_id])
            sw_et.append('l'); sw_closed.append(dev.on_off == 1)
            sw_name.append(dev.eq_number or dev.eq_id or dev.section_id)
    for cp in model.couplers:
        if cp.node_a in barra and cp.node_b in barra:
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
    for sed in sorted(model.seds, key=lambda s: s.load_key):
        if sed.node_id not in barra:
            continue
        strn = _tr2_strn_mva(sed.design_kva)
        kva = strn * 1000.0
        pcu_kw, pfe_kw = _tr2_losses_kw(kva, uk_pct=NA205_TR2_UK_PCT)
        bt = int(pp.create_bus(net, vn_kv=NA205_SED_LV_KV, name=f'{sed.loc_name}_BT'))
        pp.create_transformer_from_parameters(
            net, barra[sed.node_id], bt, sn_mva=strn, vn_hv_kv=kv, vn_lv_kv=NA205_SED_LV_KV,
            vk_percent=NA205_TR2_UK_PCT, vkr_percent=pcu_kw / kva * 100.0, pfe_kw=pfe_kw,
            i0_percent=_tr2_curmg_pct(kva, pfe_kw), name=f'TR_{sed.loc_name}')
        lado_baja[sed.load_key] = bt

    # --- cargas
    c_bus, c_p, c_q, c_name = [], [], [], []
    for load in sorted(model.loads, key=lambda ld: (ld.section_id, ld.device_number)):
        clave = (load.section_id, load.device_number)
        bus = lado_baja.get(clave, barra.get(load.node_id))
        if bus is None:
            continue
        c_bus.append(bus); c_p.append(load.p_mw); c_q.append(load.q_mvar)
        c_name.append(load.display_name or load.device_number or load.section_id)
    if c_bus:
        pp.create_loads(net, c_bus, c_p, q_mvar=c_q, name=c_name)

    informe.barras = len(net.bus)
    informe.lineas = len(net.line)
    informe.transformadores = len(net.trafo)
    informe.cargas = len(net.load)
    informe.p_carga_mw = float(net.load.p_mw.sum()) if len(net.load) else 0.0
    return net, barra, informe


# ---------------------------------------------------------------------------- veredicto

def validar(model: FeederModel) -> InformeOraculo:
    """Calcula el alimentador y devuelve el veredicto. Nunca modifica el modelo."""
    if getattr(model, 'combined', None) is not None:
        return InformeOraculo(disponible=False, motivo_no_disponible=(
            'red unida de varios alimentadores: conviven tensiones distintas'))
    if not disponible():
        return InformeOraculo(disponible=False, motivo_no_disponible='pandapower no está instalado')

    import pandapower as pp
    from pandapower import topology

    net, _barra, informe = red_pandapower(model)
    if informe.errores:
        # Con un tramo sin impedancia la matriz es singular: calcular solo añadiría un
        # «no converge» que tapa la causa, que ya está dicha.
        return informe

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
        # numba=False: sin numba instalado, runpp imprime en cada llamada un aviso de
        # cuatro líneas; en un lote de 96 alimentadores eran 96 avisos que tapaban el
        # Registro. Sin numba, los 96 alimentadores de la entrega de 03/08 se calcularon
        # en 31 s, que es aceptable para una validación previa.
        pp.runpp(net, algorithm='nr', init='auto', max_iteration=30,
                 calculate_voltage_angles=False, numba=False)
        informe.convergio = bool(net.converged)
    except Exception as exc:  # noqa: BLE001 - pandapower lanza varias clases al no converger
        informe.convergio = False
        informe.hallazgos.append(Hallazgo(
            'error', 'no_converge',
            f'el flujo de potencia no converge ({exc.__class__.__name__}). Suele deberse a '
            'una carga o un transformador fuera de escala, o a una impedancia imposible.'))
        return informe

    vm = net.res_bus.vm_pu.dropna()
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

    if len(net.res_line):
        carga = net.res_line.loading_percent.dropna()
        if len(carga):
            informe.carga_linea_max_pct = round(float(carga.max()), 1)
            informe.linea_mas_cargada = str(net.line.at[carga.idxmax(), 'name'])
            sobre = carga[carga > 100.0]
            if len(sobre):
                informe.hallazgos.append(Hallazgo(
                    'aviso', 'linea_sobrecargada',
                    f'{len(sobre)} tramo(s) por encima de su ampacidad (máx. '
                    f'{informe.carga_linea_max_pct} % en {informe.linea_mas_cargada}).'))
    if len(net.res_trafo):
        carga = net.res_trafo.loading_percent.dropna()
        if len(carga):
            informe.carga_trafo_max_pct = round(float(carga.max()), 1)
            informe.trafo_mas_cargado = str(net.trafo.at[carga.idxmax(), 'name'])
            sobre = carga[carga > 100.0]
            if len(sobre):
                informe.hallazgos.append(Hallazgo(
                    'aviso', 'trafo_sobrecargado',
                    f'{len(sobre)} transformador(es) de SED por encima de su potencia (máx. '
                    f'{informe.carga_trafo_max_pct} % en {informe.trafo_mas_cargado}).'))

    informe.p_fuente_mw = round(float(net.res_ext_grid.p_mw.sum()), 6)
    informe.perdidas_mw = round(informe.p_fuente_mw - informe.p_carga_mw, 6)
    if informe.p_carga_mw > 0:
        pct = informe.perdidas_mw / informe.p_carga_mw * 100.0
        if pct > PERDIDAS_SOSPECHOSAS_PCT:
            informe.hallazgos.append(Hallazgo(
                'aviso', 'perdidas_anomalas',
                f'pérdidas del {pct:.1f} % de la carga: delatan impedancias o longitudes '
                'fuera de escala.'))
    return informe
