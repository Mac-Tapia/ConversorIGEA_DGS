"""SED cuya carga supera la potencia de su transformador: se llevan al tamaño normalizado.

Por qué hace falta. En CYMDIST la carga de una SED es una carga puntual de media
tensión: el transformador no existe en el cálculo, y el ``ConnectedKVA`` es un dato
para repartir carga, no una impedancia. Este conversor sí modela el transformador
(el triángulo SED de NA205), y ahí un kVA inconsistente con la carga deja de ser
inofensivo. En 260924.mdb, ``SE50111`` declara 1.197 kW sobre 50 kVA: su barra de
baja cae a 0,6 p.u. y el Newton de toda la red se estanca.

Qué se hace. Solo el transformador cuya carga aparente supera su potencia toma el
**menor tamaño normalizado que la cubre**. Los demás conservan el kVA de la base. Cada
cambio se devuelve para que quede escrito en el informe: es una corrección de dato y
tiene que poder revisarse.

La comprobación es **por dispositivo**, no por SED: en la base una SED con varios
transformadores aparece como ``SE20730``, ``SE20730-2``, ``SE20730-3``, cada uno con
su transformador en el modelo, y la carga suele estar entera en el primero. Es ese
transformador el que tiene que darla.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .model import FeederModel

#: Potencias normalizadas de transformadores de distribución, en kVA.
TAMANOS_NORMALIZADOS = (
    5, 10, 15, 25, 37.5, 50, 75, 100, 160, 200, 250, 315, 400, 500, 630, 800,
    1000, 1250, 1600, 2000, 2500, 3150,
)


@dataclass(frozen=True)
class Redimension:
    sed: str
    kva_base: float
    kva_nuevo: float
    carga_kva: float

    def linea(self) -> str:
        return (f'{self.sed}: {self.carga_kva:,.0f} kVA de carga sobre '
                f'{self.kva_base:g} kVA → {self.kva_nuevo:g} kVA '
                f'({self.carga_kva / max(self.kva_base, 1e-9):.1f}× su potencia)')


def redimensionar_sobrecargadas(
    model: FeederModel, *, tamanos=TAMANOS_NORMALIZADOS,
) -> list[Redimension]:
    """Ajusta, en el sitio, los transformadores de SED que no pueden con su carga."""
    carga_kva: dict[tuple[str, str], float] = {}
    for c in model.loads:
        clave = (c.section_id, c.device_number)
        carga_kva[clave] = carga_kva.get(clave, 0.0) + (c.p_mw ** 2 + c.q_mvar ** 2) ** 0.5 * 1000.0
    cambios: list[Redimension] = []
    nuevas = []
    for sed in model.seds:
        s = carga_kva.get(sed.load_key, 0.0)
        if s > float(sed.design_kva):
            nuevo = next((float(t) for t in tamanos if t >= s), float(max(tamanos)))
            if nuevo < s:
                # Más allá del mayor normalizado no se inventa un tamaño: se queda en
                # el mayor y el informe lo dice.
                model.warnings.append(f'{sed.code}: {s:,.0f} kVA de carga supera el mayor '
                                      f'transformador normalizado ({nuevo:g} kVA).')
            cambios.append(Redimension(sed.code, float(sed.design_kva), nuevo, s))
            sed = replace(sed, design_kva=nuevo)
        nuevas.append(sed)
    model.seds = nuevas
    if cambios:
        model.warnings.append(
            f'{len(cambios)} SED con más carga que potencia instalada en la base: se '
            'llevaron al menor tamaño normalizado que la cubre. ' + '; '.join(
                c.linea() for c in cambios))
    return cambios


# ---------------------------------------------------------------------------
# Demanda de relleno o fuera de escala (spec 057)
# ---------------------------------------------------------------------------
#
# Caso real (2026-11-01): la copia VNR-GIS ELOR25_V2 de Electro Oriente trae
# ``Sed.MaxDemTotal`` = 39 kW en sus 8 729 SED, con potencias instaladas de 5 a 2 000 kVA.
# Es un relleno, no una demanda: 470 SED de 5 kVA de NJA202 quedaban al 780 % y el flujo no
# convergía ni bajando toda la demanda por igual (015:RF-38). Aquí no se agranda el
# transformador (eso cambiaría los kVA del «Caso base», 032:RF-1): se corrige la demanda,
# que es el dato que falta, con la potencia instalada, que sí trae la fuente.

#: Factor de potencia de la demanda corregida: el mismo de las SED escaladas (015:RF-54).
FP_CORRECCION = 0.98


@dataclass(frozen=True)
class CorreccionDemanda:
    sed: str
    kva: float
    p_fuente_kw: float
    p_nuevo_kw: float
    regla: str
    q_fuente_kvar: float = 0.0
    q_nuevo_kvar: float = 0.0

    def linea(self) -> str:
        return (f'{self.sed}: {self.p_fuente_kw:g} kW de la fuente ({self.regla}) → '
                f'{self.p_nuevo_kw:.2f} kW, por sus {self.kva:g} kVA')


def _demanda_por_sed(model: FeederModel) -> dict[tuple[str, str], list]:
    por: dict[tuple[str, str], list] = {}
    claves = {s.load_key for s in model.seds}
    for c in model.loads:
        clave = (c.section_id, c.device_number)
        if clave in claves:
            por.setdefault(clave, []).append(c)
    return por


def demanda_fuera_de_escala(model: FeederModel) -> list[tuple[str, str]]:
    """Claves de las SED con demanda de relleno o mayor que su potencia instalada (057:RF-2).

    Relleno: la misma P > 0 en todas las SED con carga, habiendo dos o más potencias
    instaladas distintas; una demanda real no sale igual en una SED de 5 kVA y en una de
    2 000. Una SED en cero no entra: el «Caso base» la deja en cero (nota del 2026-10-30).
    """
    kva = {s.load_key: float(s.design_kva) for s in model.seds if float(s.design_kva) > 0}
    por = {k: v for k, v in _demanda_por_sed(model).items() if k in kva}
    p_kw = {k: sum(c.p_mw for c in v) * 1000.0 for k, v in por.items()}
    s_kva = {k: sum(math.hypot(c.p_mw, c.q_mvar) for c in v) * 1000.0 for k, v in por.items()}
    con_carga = [k for k in por if p_kw[k] > 0]
    fuera = {k for k in con_carga if s_kva[k] > kva[k] * (1 + 1e-9)}
    if (len(con_carga) >= 2 and len({round(p_kw[k], 6) for k in con_carga}) == 1
            and len({kva[k] for k in con_carga}) >= 2):
        fuera.update(con_carga)
    return sorted(fuera)


def regla_de(model: FeederModel, clave: tuple[str, str]) -> str:
    """«relleno» o «supera su potencia», para el informe."""
    kva = {s.load_key: float(s.design_kva) for s in model.seds}
    v = _demanda_por_sed(model).get(clave, [])
    s = sum(math.hypot(c.p_mw, c.q_mvar) for c in v) * 1000.0
    return 'supera su potencia' if s > kva.get(clave, 0.0) * (1 + 1e-9) else 'relleno'


def corregir_demanda(model: FeederModel, claves, factor: float, *,
                     reglas: dict | None = None) -> list[CorreccionDemanda]:
    """En el sitio: la demanda de ``claves`` pasa a kVA × ``factor`` con FP 0,98 (057:RF-3).

    Si una SED tiene varias cargas, se reparte por igual entre ellas. ``reglas`` lleva la
    regla de cada clave tal como estaba en la fuente (para el informe).
    """
    sed_de = {s.load_key: s for s in model.seds}
    seno = math.sqrt(1.0 - FP_CORRECCION ** 2)
    por = _demanda_por_sed(model)
    elegidas = set(claves)
    nuevas, cambios = [], []
    vistos: set[tuple[str, str]] = set()
    for c in model.loads:
        clave = (c.section_id, c.device_number)
        if clave not in elegidas or clave not in sed_de:
            nuevas.append(c)
            continue
        n = len(por.get(clave, [c])) or 1
        s_kva = float(sed_de[clave].design_kva) * factor / n
        nuevas.append(replace(c, p_mw=s_kva * FP_CORRECCION / 1000.0,
                              q_mvar=s_kva * seno / 1000.0, pf=FP_CORRECCION))
        if clave not in vistos:
            vistos.add(clave)
            cambios.append(CorreccionDemanda(
                sed_de[clave].code, float(sed_de[clave].design_kva),
                round(sum(x.p_mw for x in por.get(clave, [c])) * 1000.0, 6),
                round(float(sed_de[clave].design_kva) * factor * FP_CORRECCION, 6),
                (reglas or {}).get(clave, 'relleno'),
                round(sum(x.q_mvar for x in por.get(clave, [c])) * 1000.0, 6),
                round(float(sed_de[clave].design_kva) * factor * seno, 6)))
    model.loads = nuevas
    return cambios
