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

def red_pandapower(model: FeederModel, consigna_pu: float = 1.0):
    """La red del DGS en pandapower. Devuelve ``(net, barra_de_nodo, informe_parcial)``.

    Con la red unida (spec 022), cada barra a su tensión, una red externa por barra de SET
    y por cada alimentador «Sin SET» (o por alimentador, sin estructura), con
    ``consigna_pu``; los interruptores de cabecera y los enlaces como estén.
    """
    import pandapower as pp

    from .dgs import NA205_SED_LV_KV, NA205_TR2_UK_PCT, _tr2_curmg_pct, _tr2_losses_kw, _tr2_strn_mva

    informe = InformeOraculo()
    kv = float(model.nominal_kv)
    net = pp.create_empty_network(name=model.name, f_hz=FRECUENCIA_HZ)

    nodos = sorted(model.nodes)
    info = getattr(model, 'combined', None)

    def kv_de(n: str) -> float:
        return float(info.node_kv.get(n, kv)) if info is not None else kv

    idx = pp.create_buses(net, len(nodos), vn_kv=[kv_de(n) for n in nodos], name=nodos)
    barra = dict(zip(nodos, (int(i) for i in idx)))
    if info is not None:
        from .enlaces import fuentes_de
        for nodo, nombre in sorted(fuentes_de(model).items()):
            if nodo in barra:
                pp.create_ext_grid(net, barra[nodo], vm_pu=consigna_pu, name=nombre)
    else:
        pp.create_ext_grid(net, barra[model.source_node], vm_pu=consigna_pu, name='FUENTE')

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
            net, barra[sed.node_id], bt, sn_mva=strn, vn_hv_kv=kv_de(sed.node_id),
            vn_lv_kv=NA205_SED_LV_KV,
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
        informe = validar(model)
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
    inf = validar(model)
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
        informe = validar(model)
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
        pp.runpp(net, algorithm='nr', init='auto', max_iteration=30,
                 calculate_voltage_angles=False, numba=False)
        return bool(net.converged)
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

    net, _barra, informe = red_pandapower(model, consigna_pu)
    resultado = InformeUnido(informe)
    if informe.errores:
        return resultado
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
        vm = net.res_bus.vm_pu.dropna()
        if len(vm):
            informe.v_min_pu = round(float(vm.min()), 4)
            informe.v_max_pu = round(float(vm.max()), 4)
            informe.barra_v_min = str(net.bus.at[vm.idxmin(), 'name'])
        informe.p_fuente_mw = round(float(net.res_ext_grid.p_mw.sum()), 6)
        informe.perdidas_mw = round(informe.p_fuente_mw - informe.p_carga_mw, 6)
        return resultado
    # Cada isla sola, con las demás fuentes fuera de servicio.
    activa = net.ext_grid.in_service.copy()
    p0, q0 = net.load.p_mw.copy(), net.load.q_mvar.copy()
    for v, (eg, buses) in zip(resultado.islas, islas):
        net.ext_grid['in_service'] = False
        net.ext_grid.at[eg, 'in_service'] = True
        v.convergio = _flujo(pp, net)
        if v.convergio:
            _medir_isla(net, eg, buses, v)
            continue
        de_isla = net.load.bus.isin(buses)
        bajo, alto = 0.0, 1.0
        for _ in range(8):                      # la fracción de carga con la que converge
            medio = (bajo + alto) / 2
            net.load.loc[de_isla, 'p_mw'] = p0[de_isla] * medio
            net.load.loc[de_isla, 'q_mvar'] = q0[de_isla] * medio
            if _flujo(pp, net):
                bajo = medio
            else:
                alto = medio
        net.load.loc[de_isla, 'p_mw'] = p0[de_isla] * bajo
        net.load.loc[de_isla, 'q_mvar'] = q0[de_isla] * bajo
        if bajo > 0 and _flujo(pp, net):
            v.escala_converge = round(bajo, 3)
            _medir_isla(net, eg, buses, v)
        net.load['p_mw'], net.load['q_mvar'] = p0, q0
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
    v.p_mw = round(float(net.res_ext_grid.at[eg, 'p_mw']), 6)
    vm = net.res_bus.vm_pu[net.res_bus.index.isin(buses)].dropna()
    if len(vm):
        v.v_min_pu = round(float(vm.min()), 4)
        v.barra_v_min = str(net.bus.at[vm.idxmin(), 'name'])
    if len(net.res_trafo):
        de = net.trafo.hv_bus.isin(buses)
        carga = net.res_trafo.loading_percent[de].dropna()
        if len(carga):
            v.carga_trafo_pct = round(float(carga.max()), 1)
            v.trafo_mas_cargado = str(net.trafo.at[carga.idxmax(), 'name'])
