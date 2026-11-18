"""Motores del PIT y su matriz de capacidades estudio × motor (107:RF-3, 107:RF-5).

Por qué una matriz. El PIT tiene que poder estudiarse sin licencia de DIgSILENT, pero el cortocircuito y la
confiabilidad de ``ComRel3`` no tienen equivalente abierto en el repositorio. La matriz hace que lo que un motor no
calcula **falte y se diga**, en vez de inventarse; y cada resultado nombra el motor que lo dio.

- ``abierto`` (pandapower, por defecto): flujo, tensión, cargabilidad y N-1; la confiabilidad se reduce a la potencia
  que queda sin servir en cada contingencia, y lo dice.
- ``digsilent`` (si hay licencia y el operador lo pide): todo, por ``tools/pit_pf.py`` en el carril ``powerfactory``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ...dominio.pit import PitError
from ...aplicacion.pit.red_area import RedArea
from .red_pandapower import calcular

__all__ = ['ESTUDIOS', 'MOTORES', 'Capacidad', 'capacidad', 'ejecutar', 'elegir_motor']

MOTORES = ('abierto', 'digsilent')
ESTUDIOS = ('flujo', 'tension', 'cargabilidad', 'n_1', 'confiabilidad', 'cortocircuito')
NO_DISPONIBLE = 'no disponible con el motor abierto'


@dataclass(frozen=True)
class Capacidad:
    motor: str
    estudio: str
    alcance: str  # 'completo', 'reducido' o 'no_disponible'
    texto: str

    @property
    def disponible(self) -> bool:
        return self.alcance != 'no_disponible'


_MATRIZ: dict[tuple[str, str], tuple[str, str]] = {
    **{('abierto', e): ('completo', 'pandapower, Newton-Raphson') for e in ('flujo', 'tension', 'cargabilidad', 'n_1')},
    ('abierto', 'confiabilidad'): ('reducido', 'solo la potencia sin servir en cada contingencia; la confiabilidad '
                                               f'de ComRel3 está {NO_DISPONIBLE}'),
    ('abierto', 'cortocircuito'): ('no_disponible', f'cortocircuito {NO_DISPONIBLE}'),
    **{('digsilent', e): ('completo', 'DIgSILENT PowerFactory (ComLdf, ComSimoutage, ComRel3, ComShc)')
       for e in ESTUDIOS},
}


def capacidad(motor: str, estudio: str) -> Capacidad:
    if motor not in MOTORES:
        raise PitError(f'motor {motor!r} desconocido; los motores son {MOTORES}')
    if estudio not in ESTUDIOS:
        raise PitError(f'estudio {estudio!r} desconocido; los estudios son {ESTUDIOS}')
    alcance, texto = _MATRIZ[(motor, estudio)]
    return Capacidad(motor, estudio, alcance, texto)


def elegir_motor(pedido: str | None, licencia: bool) -> str:
    """El abierto por defecto; DIgSILENT solo si se pide y hay licencia (pedirlo sin ella es un error, no un cambio
    callado de motor, porque los dos no dan las mismas cifras)."""
    if pedido in (None, '', 'abierto'):
        return 'abierto'
    if pedido != 'digsilent':
        raise PitError(f'motor {pedido!r} desconocido; los motores son {MOTORES}')
    if not licencia:
        raise PitError('se pidió DIgSILENT y no hay licencia: el estudio puede hacerse con el motor abierto')
    return 'digsilent'


def ejecutar(estudio: str, red: RedArea, cargas: Mapping[str, tuple[float, float]], *, motor: str = 'abierto',
             fuera: Iterable[str] = ()) -> dict[str, Any]:
    """Un estudio con un motor; el resultado nombra siempre el motor y su alcance."""
    cap = capacidad(motor, estudio)
    base = {'motor': motor, 'estudio': estudio, 'alcance': cap.alcance, 'texto': cap.texto}
    if not cap.disponible:
        return {**base, 'disponible': False}
    if motor == 'digsilent':
        raise PitError('DIgSILENT corre en su carril con tools/pit_pf.py; aquí solo se leen sus resultados')
    r = calcular(red, cargas, fuera=fuera)
    return {**base, 'disponible': True, 'resultado': r}
