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
