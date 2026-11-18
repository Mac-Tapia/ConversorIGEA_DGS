"""Dimensionamiento de la empresa modelo sobre el modelo rural del Anexo 6, con el motor físico (spec 108, RF-7).

El Anexo 6 conserva la traza real (``vad.anexo6.traza_real``, T5) y adapta el equipamiento: «Se adecuarán las
potencias de los transformadores de acuerdo a la demanda en el año base y su crecimiento vegetativo» y «la elección de
los calibres óptimos para red troncal y derivaciones se realizará considerando la corriente económica». Este módulo
hace esa adaptación y nada más:

- **Transformación** (``vad.anexo6.sed``): los kVA de la demanda ajustada de cada SED se asignan a la menor potencia de
  la «tabla de transformadores normalizados» que los cubre. El Anexo no da esa tabla: la regla registra la
  interpretación de f4, que son las potencias con costo en el SICODI del periodo por sector típico y tipo de SED
  (:class:`TablaTransformadores`, con la huella del SICODI del que salió). Un punto trifásico por debajo del umbral de
  la regla recibe la potencia ajustada de la regla, y una demanda sobre el tope de la regla va en módulos iguales.
  Una asignación a una potencia no normalizada lleva nota.
- **Conductor de MT** (``vad.anexo6.mt.calibre_economico``, ``vad.anexo6.mt.tensiones_y_secciones``,
  ``vad.anexo6.mt.fases_y_material``): por la corriente de cada tramo, calculada con el flujo del oráculo, se elige el
  conductor cuyo rango de corriente económica la contiene. El Anexo dice que esos rangos «los sustenta la empresa en
  hoja de cálculo»: entran como :class:`RangoEconomico`, con su sustento, y sin ellos el tramo no se adapta y se
  nombra. Nunca un conductor por debajo de la sección mínima de su material. INTERPRETACIÓN (decisión de f4,
  2026-11-15, VAD-A6 T7): AAAC (aleación de aluminio) y ACSR (aluminio con alma de acero) cuentan como conductores de
  Al para la sección mínima de ``vad.anexo6.mt.tensiones_y_secciones`` («desde 25 mm² en Al»), porque su conductor es
  aluminio (:data:`MATERIAL_DEL_CONDUCTOR`); cada uno lleva nota.
- **Pérdidas**: las de potencia, del flujo de ``oraculo.validar`` sobre la red dimensionada; las de energía, con el
  factor de pérdidas empírico de ``informes.factor_de_perdidas`` y los coeficientes del registro
  (``vad.anexo4.factor_perdidas_empirico``). La caída de tensión de la MT se comprueba contra
  ``vad.anexo6.mt.caida_tension_max``: fuera de banda, el Anexo pide una compensación mínima que aquí no se calcula y
  se nombra.

**Ningún vértice cambia**: el :class:`Dimensionamiento` guarda el mismo :class:`~.modelo_rural.ModeloRural`, cuyas
huellas se comprueban antes de empezar. **Un conductor sin ``rline`` o ``xline`` es un hueco nombrado, no 0 Ω**: su
alimentador no se calcula, y un candidato así no se elige nunca. Lo que el Anexo no fija (las secciones equivalentes
de los tramos de menos de tres fases, la BT por tramo, los km de terceros) queda como hueco o como interpretación
anotada, nunca como un número supuesto.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import asdict, dataclass, field

from ..entrada.vnr.models.canonical import ConductorType
from ..dgs import letras_de_fase
from ..informes import (
    HORAS_ANIO,
    InformeError,
    coeficientes_factor_de_perdidas,
    factor_de_perdidas,
)
from ...dominio.model import FeederModel, Line, LineType, Load, Node, Sed
from ..oraculo import (
    InformeOraculo,
    disponible,
    ejecutar,
    red_pandapower,
    tiene_fases,
    validar,
)
from ...dominio.registro_normativo import RegistroError, RegistroNormativo, ReglaVigente
from ...aplicacion.vad import VadError
from .modelo_rural import ModeloRural, TramoRural, hash_vertices

REGLA_SED = 'vad.anexo6.sed'
REGLA_CALIBRE_MT = 'vad.anexo6.mt.calibre_economico'
REGLA_FASES_MATERIAL = 'vad.anexo6.mt.fases_y_material'
REGLA_CAIDA_MT = 'vad.anexo6.mt.caida_tension_max'
REGLA_SECCIONES_MT = 'vad.anexo6.mt.tensiones_y_secciones'
REGLA_BT = 'vad.anexo6.bt'
REGLA_TERCEROS = 'vad.anexo6.terceros'
#: Las reglas del registro en que se apoya el dimensionamiento: sin una de ellas no se dimensiona (108:RF-9).
REGLAS = (REGLA_SED, REGLA_CALIBRE_MT, REGLA_FASES_MATERIAL, REGLA_CAIDA_MT, REGLA_SECCIONES_MT, REGLA_BT,
          REGLA_TERCEROS)
#: Los datos de ``vad.anexo6.sed`` del punto trifásico pequeño: el umbral («menores a 5 kVA», línea 6796) y la potencia
#: ajustada («se asigna una potencia ajustada de 10 kVA»). El umbral es un dato del registro y no se lee del nombre de
#: la clave (decisión de f4, 2026-11-15, VAD-A6 T7).
_CLAVE_UMBRAL = 'trifasico_umbral_kVA'
_CLAVE_AJUSTADA = 'trifasico_menor_5kVA_asigna_kVA'
#: Material de la aleación → material de ``seccion_min_mm2`` cuyo mínimo le aplica. INTERPRETACIÓN (decisión de f4,
#: 2026-11-15, VAD-A6 T7): AAAC y ACSR son conductores de aluminio; su mínimo es el del Al.
MATERIAL_DEL_CONDUCTOR = {'aaac': 'al', 'acsr': 'al'}
#: «Cu en lugar de Al» (``vad.anexo6.mt.fases_y_material``, valor ``zonas_corrosivas``).
_SUSTITUCION = re.compile(r'^\s*(\S+)\s+en lugar de\s+(\S+)\s*$')
#: Etiqueta de la carga detrás de cada SED en la red del oráculo, como ``Load.device_number``.
_CARGA_SED = 'SED'


@dataclass(frozen=True)
class DemandaSed:
    """La demanda ajustada de una SED, ya proyectada al periodo (la da la caracterización de la T4).

    ``origen`` dice de dónde sale: una demanda sin origen no dimensiona nada.
    """

    kw: float
    kvar: float
    fases: str
    origen: str

    def __post_init__(self) -> None:
        if not (math.isfinite(self.kw) and math.isfinite(self.kvar)) or self.kw < 0:
            raise VadError(f'demanda no válida: {self.kw!r} kW, {self.kvar!r} kvar')
        if not str(self.origen or '').strip():
            raise VadError('la demanda de una SED tiene que decir de dónde sale (origen)')

    @property
    def kva(self) -> float:
        return math.hypot(self.kw, self.kvar)


@dataclass(frozen=True)
class TablaTransformadores:
    """La «tabla de transformadores normalizados» según la interpretación registrada en ``vad.anexo6.sed``.

    ``potencias``: (sector típico, tipo de SED) → kVA con costo en el SICODI del periodo. ``huella_fuente`` es la del
    SICODI del que se leyó (se lee por su huella, nunca una versión fija). ``no_normalizadas``: las potencias de la
    lista que existen en el parque sin ser normalizadas; una asignación a ellas lleva nota.
    """

    potencias: Mapping[tuple[str, str], tuple[float, ...]]
    huella_fuente: str
    no_normalizadas: frozenset[float]

    def __post_init__(self) -> None:
        if not str(self.huella_fuente or '').strip():
            raise VadError('la tabla de transformadores tiene que llevar la huella del SICODI del que sale')
        for clave, lista in self.potencias.items():
            if not lista or any(not math.isfinite(p) or p <= 0 for p in lista):
                raise VadError(f'la tabla de transformadores de {clave} trae potencias no válidas: {lista!r}')


@dataclass(frozen=True)
class RangoEconomico:
    """El rango de corriente económica de un conductor, que sustenta la empresa (``vad.anexo6.mt.calibre_economico``)."""

    conductor: str
    desde_a: float
    hasta_a: float
    sustento: str

    def __post_init__(self) -> None:
        if not (0 <= self.desde_a < self.hasta_a) or not math.isfinite(self.hasta_a):
            raise VadError(f'rango económico no válido de {self.conductor}: {self.desde_a!r}–{self.hasta_a!r} A')
        if not str(self.sustento or '').strip():
            raise VadError(f'el rango económico de {self.conductor} no dice su sustento (la hoja de la empresa)')


@dataclass(frozen=True)
class SedDimensionada:
    sed: str
    alimentador: str
    nodo: str
    kva_real: float | None
    kva_demanda: float | None
    kva_modelo: float | None
    """La potencia de la empresa modelo; ``None`` si no se pudo asignar (el motivo está en ``nota`` y en huecos)."""
    modulos: int
    nota: str = ''

    @property
    def cambia(self) -> bool:
        return self.kva_modelo is not None and self.kva_modelo != self.kva_real


@dataclass(frozen=True)
class TramoDimensionado:
    tramo: str
    alimentador: str
    nivel: str
    clase: str
    fases: str
    huella: str
    """La huella de vértices del modelo rural, la misma: el dimensionamiento no toca la traza."""
    conductor_real: str
    conductor_modelo: str | None
    """``None`` si el tramo no se adapta; el motivo está en ``nota``."""
    corriente_a: float | None
    nota: str = ''


@dataclass(frozen=True)
class PerdidasAlimentador:
    alimentador: str
    calculado: bool
    motivo: str = ''
    flujo: str = ''
    veredicto: str = ''
    p_fuente_kw: float | None = None
    perdidas_kw: float | None = None
    perdidas_pct: float | None = None
    caida_mt_pct: float | None = None
    caida_max_pct: float | None = None
    factor_carga: float | None = None
    factor_perdidas: float | None = None
    perdidas_kwh_anio: float | None = None


@dataclass(frozen=True)
class Dimensionamiento:
    """La empresa modelo dimensionada sobre la traza real: lo que necesita el costo estándar de la T7."""

    modelo: ModeloRural
    sed: tuple[SedDimensionada, ...]
    tramos: tuple[TramoDimensionado, ...]
    perdidas: tuple[PerdidasAlimentador, ...]
    criterios: Mapping[str, Mapping[str, str]]
    """Clave del registro → su cita y su huella."""
    huecos: tuple[str, ...]
    notas: tuple[str, ...]
    redes: Mapping[str, FeederModel] = field(default_factory=dict)
    """La red dimensionada de cada alimentador calculado, tal como la ve el oráculo."""
    huella: str = ''
    tabla_huella: str = ''
    """La huella del SICODI del que salió la tabla de transformadores: el costo estándar (T7) la compara con la suya."""

    @property
    def completo(self) -> bool:
        return not self.huecos and self.modelo.completo

    def hash_vertices(self) -> dict[str, str]:
        return {t.tramo: t.huella for t in self.modelo.tramos}


def _cita(v: ReglaVigente) -> dict[str, str]:
    r = v.regla
    return {'cita': f'{v.norma.acto}, {r.articulo_o_anexo}, {r.pagina}, líneas {r.lineas}', 'huella': v.huella()}


def _reglas(registro: RegistroNormativo, fecha: str | None) -> dict[str, ReglaVigente]:
    out = {}
    for clave in REGLAS:
        try:
            out[clave] = registro.regla(clave, fecha)
        except RegistroError as exc:
            raise VadError(f'el dimensionamiento se apoya en la regla {clave} del Anexo 6: {exc}') from exc
    return out


def _umbral(valor: Mapping) -> tuple[float, float]:
    """(umbral, potencia ajustada) del punto trifásico pequeño, leídos de la regla, no del código."""
    faltan = [k for k in (_CLAVE_UMBRAL, _CLAVE_AJUSTADA) if k not in valor]
    if faltan:
        raise VadError(f'la regla {REGLA_SED} no trae {", ".join(faltan)} (punto trifásico pequeño)')
    return float(valor[_CLAVE_UMBRAL]), float(valor[_CLAVE_AJUSTADA])


def _material(nombre: str, minimos: Mapping[str, float]) -> str | None:
    """La clave de ``seccion_min_mm2`` del material, con las aleaciones de :data:`MATERIAL_DEL_CONDUCTOR`."""
    nombre = str(nombre or '').strip().lower()
    nombre = MATERIAL_DEL_CONDUCTOR.get(nombre, nombre)
    return next((k for k in minimos if k.lower() == nombre), None)


def _sin_impedancia(c: ConductorType) -> str:
    """El motivo si el conductor no tiene ``rline`` o ``xline`` utilizables; vacío si los tiene."""
    r, x = c.r1_ohm_km, c.x1_ohm_km
    if r is None or x is None or not (math.isfinite(r) and math.isfinite(x)):
        return f'conductor {c.conductor_code}: sin rline o xline (R1={r!r}, X1={x!r} Ω/km); no entra con 0 Ω'
    if r < 0 or x < 0 or (r == 0 and x == 0):
        return f'conductor {c.conductor_code}: R1={r!r}, X1={x!r} Ω/km no es una impedancia; no entra con 0 Ω'
    return ''


# ------------------------------------------------------------------------------------------------- transformación

def _dimensionar_sed(modelo: ModeloRural, regla: ReglaVigente, demanda: Mapping[str, DemandaSed],
                     tabla: TablaTransformadores, sector_de: Mapping[str, str], tipo_de_sed: Mapping[str, str],
                     huecos: list[str], notas: list[str]) -> list[SedDimensionada]:
    valor = regla.regla.valor
    umbral, ajustada = _umbral(valor)
    tope, modulo = float(valor['demanda_mayor_kVA']), float(valor['modulo_kVA'])
    out = []
    for s in modelo.sed:
        d = demanda.get(s.sed)
        sector, tipo = sector_de.get(s.alimentador), tipo_de_sed.get(s.sed)
        motivo = ''
        if d is None:
            motivo = 'sin demanda ajustada'
        elif d.kva <= 0:
            motivo = 'demanda nula: no hay kVA que asignar'
        elif not sector:
            motivo = f'su alimentador {s.alimentador} no tiene sector típico'
        elif not tipo:
            motivo = 'sin tipo de SED'
        elif (sector, tipo) not in tabla.potencias:
            motivo = f'sin potencias con costo en el SICODI para ({sector}, {tipo})'
        if motivo:
            huecos.append(f'SED {s.sed}: {motivo}; no se dimensiona ({REGLA_SED})')
            out.append(SedDimensionada(s.sed, s.alimentador, s.nodo, s.kva, d.kva if d else None, None, 0, motivo))
            continue
        lista = sorted(tabla.potencias[(sector, tipo)])
        kva = d.kva
        nota = []
        if kva > tope:
            # «Para demandas superiores a 350 kVA, se adoptan múltiples módulos iguales de 300 kVA» (6798-6799).
            n = math.ceil(kva / modulo)
            kva_modelo, modulos = n * modulo, n
            nota.append(f'{n} módulo(s) de {modulo:g} kVA (demanda sobre {tope:g} kVA)')
            if modulo not in lista:
                notas.append(f'SED {s.sed}: el módulo de {modulo:g} kVA no tiene costo en el SICODI para '
                             f'({sector}, {tipo})')
        else:
            objetivo = kva
            if len(letras_de_fase(d.fases)) == 3 and kva < umbral:
                objetivo = ajustada
                nota.append(f'punto trifásico de {kva:.3g} kVA < {umbral:g}: potencia ajustada {ajustada:g} kVA')
            cubren = [p for p in lista if p >= objetivo]
            if not cubren:
                motivo = (f'demanda de {objetivo:.4g} kVA sobre la mayor potencia con costo ({lista[-1]:g} kVA) en '
                          f'({sector}, {tipo})')
                huecos.append(f'SED {s.sed}: {motivo}; no se dimensiona ({REGLA_SED})')
                out.append(SedDimensionada(s.sed, s.alimentador, s.nodo, s.kva, kva, None, 0, motivo))
                continue
            kva_modelo, modulos = cubren[0], 1
        if kva_modelo in tabla.no_normalizadas:
            nota.append(f'{kva_modelo:g} kVA es una potencia no normalizada (interpretación de {REGLA_SED})')
        out.append(SedDimensionada(s.sed, s.alimentador, s.nodo, s.kva, kva, kva_modelo, modulos, '; '.join(nota)))
    return out


# --------------------------------------------------------------------------------------------- flujo del oráculo

def _correr(net) -> bool:
    """El mismo flujo que ``oraculo.validar`` (``oraculo.ejecutar``), sin repetir sus llamadas a pandapower."""
    import pandapower as pp
    from pandapower.powerflow import LoadflowNotConverged

    try:
        ejecutar(pp, net)
    except LoadflowNotConverged:
        return False
    return bool(net.converged)


def _corrientes(net) -> dict[str, float]:
    """Tramo → corriente en A; con el flujo desequilibrado, la de la fase más cargada."""
    if 'fases_de_barra' in net:
        tabla = net.res_line_3ph
        columnas = [c for c in tabla.columns if re.fullmatch(r'i_[abc]_(from|to)_ka', c)]
        valores = tabla[columnas].max(axis=1)
    else:
        valores = net.res_line.i_ka
    return {str(net.line.at[i, 'name']): float(v) * 1000.0 for i, v in valores.items() if math.isfinite(float(v))}


def _caida_mt(net, barras_mt: Collection[int]) -> float | None:
    """(1 − la menor tensión de las barras de MT) en %, con la red externa en 1 p.u."""
    if 'fases_de_barra' in net:
        tabla, fases = net.res_bus_3ph, net['fases_de_barra']
        minimos = []
        for b in barras_mt:
            for letra in fases.get(b, 'ABC'):
                v = float(tabla.at[b, f'vm_{letra.lower()}_pu'])
                if math.isfinite(v):
                    minimos.append(v)
    else:
        minimos = [float(v) for b, v in net.res_bus.vm_pu.items() if b in barras_mt and math.isfinite(float(v))]
    return round((1.0 - min(minimos)) * 100.0, 4) if minimos else None


def _red(alimentador: str, kv: float, cabecera: str, tramos: Sequence[TramoRural],
         conductor: Mapping[str, ConductorType], seds: Sequence[SedDimensionada],
         demanda: Mapping[str, DemandaSed]) -> FeederModel:
    """La red MT del alimentador como la calcula el oráculo: el modelo rural no cambia; solo se lee."""
    nodos = sorted({n for t in tramos for n in (t.desde, t.hasta)} | {cabecera})
    lineas, tipos = [], {}
    for t in tramos:
        c = conductor[t.tramo]
        lineas.append(Line(t.tramo, t.desde, t.hasta, t.fases, c.conductor_code, c.conductor_code,
                           float(t.longitud_m), True))
        tipos[c.conductor_code] = LineType(c.conductor_code, c.conductor_code, 'vad', float(c.r1_ohm_km), 0.0,
                                           float(c.x1_ohm_km), 0.0, 0.0, 0.0, float(c.ampacity_a or 0.0))
    sed_red, cargas = [], []
    for s in seds:
        d = demanda[s.sed]
        sed_red.append(Sed(s.sed, s.sed, s.nodo, float(s.kva_modelo), s.sed, _CARGA_SED, (s.sed, _CARGA_SED),
                           feeder=alimentador))
        cargas.append(Load(s.sed, _CARGA_SED, '', '', s.nodo, d.kw / 1000.0, d.kvar / 1000.0, d.kw / d.kva,
                           float(s.kva_modelo), 0.0, d.fases, sed_code=s.sed, feeder=alimentador))
    return FeederModel(alimentador, alimentador, kv, cabecera, {n: Node(n, None, None) for n in nodos}, lineas,
                       cargas, [], tipos, seds=sed_red, fuente='vad')


def _flujo(fm: FeederModel) -> tuple[bool, dict[str, float], float | None, str]:
    """(convergió, corrientes por tramo, caída de la MT en %, motivo) con la red de ``oraculo.red_pandapower``."""
    net, barra, informe = red_pandapower(fm, por_fases=tiene_fases(fm))
    if informe.errores:
        return False, {}, None, '; '.join(h.linea() for h in informe.errores)
    if not _correr(net):
        return False, {}, None, 'el flujo de potencia no converge'
    return True, _corrientes(net), _caida_mt(net, set(barra.values())), ''


# --------------------------------------------------------------------------------------------------- conductor

@dataclass(frozen=True)
class _Candidato:
    conductor: ConductorType
    material: str
    rango: RangoEconomico


def _candidatos(conductores: Mapping[str, ConductorType], rangos: Mapping[str, RangoEconomico],
                minimos: Mapping[str, float], huecos: list[str]) -> list[_Candidato]:
    """Los conductores que se pueden elegir: con impedancia, material de la regla, sección mínima y rango sustentado."""
    out, sin_rango = [], []
    for codigo, c in sorted(conductores.items()):
        motivo = _sin_impedancia(c)
        material = _material(c.material, minimos)
        if motivo:
            if codigo in rangos:
                huecos.append(f'{motivo}: candidato excluido ({REGLA_CALIBRE_MT})')
            continue
        if codigo not in rangos:
            sin_rango.append(codigo)
            continue
        if material is None:
            huecos.append(f'conductor {codigo}: material {c.material!r} sin sección mínima en {REGLA_SECCIONES_MT}; '
                          f'candidato excluido')
            continue
        if c.section_mm2 is None or c.section_mm2 < float(minimos[material]):
            continue
        out.append(_Candidato(c, material, rangos[codigo]))
    if sin_rango:
        huecos.append(f'conductores sin rango de corriente económica sustentado ({REGLA_CALIBRE_MT}: «los sustenta la '
                      f'empresa»), no se eligen: {", ".join(sin_rango)}')
    return sorted(out, key=lambda k: (k.material, k.conductor.section_mm2, k.conductor.conductor_code))


def _elegir(corriente: float, material: str, candidatos: Sequence[_Candidato]) -> tuple[ConductorType | None, str]:
    propios = [k for k in candidatos if k.material == material]
    if not propios:
        return None, f'sin candidatos de material {material} con rango económico sustentado'
    for k in propios:
        if k.rango.desde_a <= corriente <= k.rango.hasta_a:
            return k.conductor, ''
    if corriente < min(k.rango.desde_a for k in propios):
        k = min(propios, key=lambda k: (k.rango.desde_a, k.conductor.section_mm2))
        return k.conductor, f'{corriente:.3g} A bajo todos los rangos: el de rango menor'
    return None, f'{corriente:.3g} A fuera del rango económico de todos los candidatos de {material}'


# ------------------------------------------------------------------------------------------------------ armado

def dimensionar(modelo: ModeloRural, *, registro: RegistroNormativo, cabeceras: Mapping[str, str],
                conductor_de: Mapping[str, str], conductores: Sequence[ConductorType],
                rangos: Sequence[RangoEconomico], demanda: Mapping[str, DemandaSed], tabla: TablaTransformadores,
                sector_de: Mapping[str, str], tipo_de_sed: Mapping[str, str],
                factor_carga: Mapping[str, float] | None = None, corrosivos: Collection[str] = (),
                fecha: str | None = None) -> Dimensionamiento:
    """La empresa modelo sobre la traza real: potencia de cada SED, conductor de MT y pérdidas (108:RF-7).

    ``cabeceras``: alimentador → nodo de la fuente. ``conductor_de``: tramo → código del conductor real (el
    ``conductor_code`` del VNR). ``conductores``: el catálogo, con R1 y X1 (``rline`` y ``xline``) y la sección.
    ``rangos``: la corriente económica de cada conductor candidato, con su sustento. ``demanda``: SED → demanda
    ajustada. ``sector_de`` y ``tipo_de_sed``: el sector típico por alimentador y el tipo de cada SED, para la tabla.
    ``factor_carga``: alimentador → factor de carga, para las pérdidas de energía. ``corrosivos``: tramos en zona
    corrosiva, que cambian de material según la regla. El modelo rural no se toca.
    """
    reglas = _reglas(registro, fecha)
    criterios: dict[str, Mapping[str, str]] = {c: _cita(v) for c, v in reglas.items()}
    for t in modelo.tramos:
        if t.vertices and hash_vertices(t.vertices) != t.huella:
            raise VadError(f'el tramo {t.tramo} no tiene la huella de sus vértices: se respetarán las trazas')
    if factor_carga:
        try:
            *_coef, cita = coeficientes_factor_de_perdidas(registro, fecha)
        except InformeError as exc:
            raise VadError(str(exc)) from exc
        criterios['vad.anexo4.factor_perdidas_empirico'] = {
            'cita': cita, 'huella': registro.regla('vad.anexo4.factor_perdidas_empirico', fecha).huella()}
    huecos: list[str] = []
    notas: list[str] = [(f'tabla de transformadores: potencias con costo en el SICODI de huella '
                         f'{tabla.huella_fuente} (interpretación de {REGLA_SED})')]

    catalogo: dict[str, ConductorType] = {}
    for c in conductores:
        if c.conductor_code in catalogo:
            raise VadError(f'el conductor {c.conductor_code} está dos veces en el catálogo')
        catalogo[c.conductor_code] = c
    por_conductor: dict[str, RangoEconomico] = {}
    for r in rangos:
        if r.conductor in por_conductor:
            raise VadError(f'el conductor {r.conductor} tiene dos rangos económicos')
        if r.conductor not in catalogo:
            raise VadError(f'el rango económico es de {r.conductor}, que no está en el catálogo')
        por_conductor[r.conductor] = r
    secciones = reglas[REGLA_SECCIONES_MT].regla.valor
    minimos = secciones['seccion_min_mm2']
    tensiones = {float(k) for k in secciones['fase_fase_kV']} | {float(secciones['fase_neutro_kV'])}
    fases_material = reglas[REGLA_FASES_MATERIAL].regla.valor
    sustitucion = _SUSTITUCION.match(str(fases_material['zonas_corrosivas']))
    if sustitucion is None:
        raise VadError(f'la regla {REGLA_FASES_MATERIAL} no dice qué material sustituye a cuál en zona corrosiva')
    nuevo_material, viejo_material = sustitucion.group(1), sustitucion.group(2)
    monofasica_a = float(fases_material['monofasica_si_corriente_menor_A'])
    caida_max = float(reglas[REGLA_CAIDA_MT].regla.valor)
    candidatos = _candidatos(catalogo, por_conductor, minimos, huecos)
    for aleacion in sorted({c.material for c in catalogo.values()
                            if str(c.material or '').strip().lower() in MATERIAL_DEL_CONDUCTOR}):
        notas.append(f'material {aleacion}: cuenta como {_material(aleacion, minimos)} para la sección mínima de '
                     f'{REGLA_SECCIONES_MT} (interpretación de f4: su conductor es aluminio)')

    seds = _dimensionar_sed(modelo, reglas[REGLA_SED], demanda, tabla, sector_de, tipo_de_sed, huecos, notas)
    if not disponible():
        raise VadError('el dimensionamiento necesita el motor físico (pandapower) y no está instalado')

    tramos_out: list[TramoDimensionado] = []
    perdidas: list[PerdidasAlimentador] = []
    redes: dict[str, FeederModel] = {}
    menos_de_tres = False
    for alimentador in sorted({t.alimentador for t in modelo.tramos if t.nivel == 'MT'}):
        mt = [t for t in modelo.tramos if t.alimentador == alimentador and t.nivel == 'MT']
        propias = [s for s in seds if s.alimentador == alimentador]
        motivos, real = [], {}
        for t in mt:
            codigo = str(conductor_de.get(t.tramo) or '')
            c = catalogo.get(codigo)
            if not codigo:
                motivos.append(f'tramo {t.tramo}: la fuente no da su conductor')
            elif c is None:
                motivos.append(f'tramo {t.tramo}: el conductor {codigo} no está en el catálogo')
            elif _sin_impedancia(c):
                motivos.append(f'tramo {t.tramo}: {_sin_impedancia(c)}')
            else:
                real[t.tramo] = c
            if t.longitud_m is None:
                motivos.append(f'tramo {t.tramo}: sin longitud')
            if not t.en_servicio:
                motivos.append(f'tramo {t.tramo}: fuera de servicio en la fuente')
        kvs = sorted({t.tension_kv for t in mt if t.tension_kv is not None})
        cabecera = cabeceras.get(alimentador, '')
        if len(kvs) != 1:
            motivos.append(f'la MT trae {len(kvs)} tensiones {kvs}; una red, una tensión')
        elif kvs[0] not in tensiones:
            notas.append(f'alimentador {alimentador}: {kvs[0]:g} kV no es una de las tensiones del Anexo 6 '
                         f'{sorted(tensiones)} ({REGLA_SECCIONES_MT})')
        nodos_mt = {n for t in mt for n in (t.desde, t.hasta)}
        if cabecera not in nodos_mt:
            motivos.append(f'su cabecera {cabecera or "(sin dar)"} no está en su red MT')
        for s in propias:
            if s.kva_modelo is None:
                motivos.append(f'SED {s.sed} sin dimensionar')
            elif s.nodo not in nodos_mt:
                motivos.append(f'SED {s.sed}: su nodo {s.nodo} no está en la red MT')
        if motivos:
            motivo = '; '.join(motivos)
            huecos.append(f'alimentador {alimentador}: no se calcula ({motivo})')
            perdidas.append(PerdidasAlimentador(alimentador, False, motivo))
            tramos_out.extend(TramoDimensionado(t.tramo, alimentador, t.nivel, t.clase, t.fases, t.huella,
                                                str(conductor_de.get(t.tramo) or ''), None, None,
                                                'sin flujo del alimentador') for t in mt)
            continue

        base = _red(alimentador, kvs[0], cabecera, mt, real, propias, demanda)
        convergio, corrientes, _caida, motivo = _flujo(base)
        if not convergio:
            huecos.append(f'alimentador {alimentador}: el flujo con los conductores reales no se resuelve ({motivo})')
            perdidas.append(PerdidasAlimentador(alimentador, False, motivo))
            tramos_out.extend(TramoDimensionado(t.tramo, alimentador, t.nivel, t.clase, t.fases, t.huella,
                                                real[t.tramo].conductor_code, None, None, motivo) for t in mt)
            continue
        elegido: dict[str, ConductorType] = {}
        for t in mt:
            c_real = real[t.tramo]
            corriente = corrientes.get(t.tramo)
            if corriente is None:
                # oraculo.red_pandapower calcula como conexión un tramo de menos de 1 cm: no tiene corriente propia.
                huecos.append(f'tramo {t.tramo}: el oráculo lo calcula como conexión, sin corriente; no se adapta')
                elegido[t.tramo] = c_real
                tramos_out.append(TramoDimensionado(t.tramo, alimentador, t.nivel, t.clase, t.fases, t.huella,
                                                    c_real.conductor_code, None, None, 'conexión sin corriente'))
                continue
            material = _material(c_real.material, minimos)
            if material is not None and t.tramo in corrosivos and material.lower() == viejo_material.lower():
                material = _material(nuevo_material, minimos)
            nota = []
            if len(letras_de_fase(t.fases)) < 3:
                menos_de_tres = True
            elif corriente < monofasica_a:
                nota.append(f'trifásico con {corriente:.3g} A < {monofasica_a:g} A: candidato a red monofásica '
                            f'({REGLA_FASES_MATERIAL}); la proporción de fases se conserva')
            if material is None:
                c, motivo = None, f'material {c_real.material!r} sin sección mínima en {REGLA_SECCIONES_MT}'
            else:
                c, motivo = _elegir(corriente, material, candidatos)
            if c is None:
                huecos.append(f'tramo {t.tramo}: no se adapta ({motivo}); el flujo usa el conductor real '
                              f'{c_real.conductor_code}')
                nota.append(motivo)
            elif motivo:
                nota.append(motivo)
            if c is not None and c.ampacity_a and corriente > c.ampacity_a:
                huecos.append(f'tramo {t.tramo}: {corriente:.3g} A sobre la ampacidad de {c.conductor_code} '
                              f'({c.ampacity_a:g} A)')
            elegido[t.tramo] = c if c is not None else c_real
            tramos_out.append(TramoDimensionado(t.tramo, alimentador, t.nivel, t.clase, t.fases, t.huella,
                                                c_real.conductor_code, c.conductor_code if c is not None else None,
                                                round(corriente, 6), '; '.join(nota)))

        red = _red(alimentador, kvs[0], cabecera, mt, elegido, propias, demanda)
        convergio, _corr, caida, motivo = _flujo(red)
        informe: InformeOraculo = validar(red, comparar=False)
        if not (convergio and informe.convergio) or informe.perdidas_mw is None:
            motivo = motivo or informe.resumen()
            huecos.append(f'alimentador {alimentador}: el flujo de la red dimensionada no se resuelve ({motivo})')
            perdidas.append(PerdidasAlimentador(alimentador, False, motivo, informe.flujo, informe.veredicto))
            continue
        redes[alimentador] = red
        perdidas_kw = informe.perdidas_mw * 1000.0
        p_fuente_kw = float(informe.p_fuente_mw) * 1000.0
        fc = (factor_carga or {}).get(alimentador)
        fp = kwh = None
        if fc is None:
            huecos.append(f'alimentador {alimentador}: sin factor de carga, sin pérdidas de energía')
        else:
            try:
                fp = factor_de_perdidas(fc, registro, fecha)
            except InformeError as exc:
                raise VadError(f'alimentador {alimentador}: {exc}') from exc
            kwh = perdidas_kw * HORAS_ANIO * fp
        if caida is not None and caida > caida_max:
            huecos.append(f'alimentador {alimentador}: caída de tensión de {caida:.3g} % sobre el {caida_max:g} % de '
                          f'{REGLA_CAIDA_MT}; el Anexo pide una compensación mínima que no se calcula aquí')
        perdidas.append(PerdidasAlimentador(
            alimentador, True, '', informe.flujo, informe.veredicto, p_fuente_kw, perdidas_kw,
            100.0 * perdidas_kw / p_fuente_kw if p_fuente_kw > 0 else None, caida, caida_max, fc, fp, kwh))

    if menos_de_tres:
        notas.append(f'tramos de menos de tres fases: {REGLA_FASES_MATERIAL} pide secciones equivalentes y el Anexo no '
                     f'da la equivalencia; se elige con la corriente de fase del flujo desequilibrado')
    bt = sorted(t.tramo for t in modelo.tramos if t.nivel == 'BT')
    if bt:
        huecos.append(f'BT: {len(bt)} tramo(s) sin dimensionar; la demanda viene por SED y no por tramo, y los '
                      f'calibres de {REGLA_BT} necesitan la de cada tramo')
    huecos.append(f'{REGLA_TERCEROS}: la fuente no da el propietario de cada tramo; no se excluyen km de terceros')

    sed_t = tuple(sorted(seds, key=lambda s: s.sed))
    tramos_t = tuple(sorted(tramos_out, key=lambda t: t.tramo))
    perdidas_t = tuple(sorted(perdidas, key=lambda p: p.alimentador))
    contenido = {'sed': [asdict(s) for s in sed_t], 'tramos': [asdict(t) for t in tramos_t],
                 'perdidas': [asdict(p) for p in perdidas_t], 'criterios': criterios,
                 'trazas': {t.tramo: t.huella for t in modelo.tramos}, 'tabla': tabla.huella_fuente,
                 'fundamento': modelo.fundamento}
    huella = hashlib.sha256(json.dumps(contenido, sort_keys=True, ensure_ascii=False, default=str)
                            .encode('utf-8')).hexdigest()
    return Dimensionamiento(modelo, sed_t, tramos_t, perdidas_t, dict(sorted(criterios.items())), tuple(huecos),
                            tuple(notas), dict(sorted(redes.items())), huella, tabla.huella_fuente)
