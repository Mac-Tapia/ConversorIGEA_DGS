"""El estudio de planeamiento: de su año de presentación salen todos sus años (spec 072).

El PIDE se presenta cada 4 años y el año 00 es el anterior a la presentación (art. 7.2 de la
metodología): con presentación en 2027, el año 00 es 2026 y el detalle del PIDE va de 2030 a 2033.
Por eso aquí no hay ningún año de calendario escrito: el usuario, el 2026-11-02, «esto no debe ser
fijo porque se presenta cada 4 años». Los desplazamientos salen de la metodología.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


class EstudioError(ValueError):
    """Un estudio que no se puede formar: se dice, no se supone un año."""


@dataclass(frozen=True)
class Estudio:
    """Los años de un estudio, relativos al año 00 y de calendario (072:RF-1, RF-2)."""

    anio_presentacion: int
    anio_base: int
    largo_plazo: tuple[int, ...]
    detalle_pide: tuple[int, ...]
    ciclo_anios: int

    def calendario(self, relativo: int) -> int:
        """El año de calendario de un año relativo al año 00."""
        return self.anio_base + relativo

    def siguiente(self) -> 'Estudio':
        """El estudio del ciclo siguiente: los mismos desplazamientos, otros años."""
        return Estudio(self.anio_presentacion + self.ciclo_anios, self.anio_base + self.ciclo_anios,
                       self.largo_plazo, self.detalle_pide, self.ciclo_anios)

    def resumen(self) -> dict:
        """Lo que se guarda en el informe: los años relativos y su calendario."""
        return {'anio_presentacion': self.anio_presentacion, 'anio_base': self.anio_base,
                'largo_plazo': {f'{a:02d}': self.calendario(a) for a in self.largo_plazo},
                'detalle_pide': {f'{a:02d}': self.calendario(a) for a in self.detalle_pide}}


def _desplazamientos(horizonte: Mapping, clave: str) -> tuple[int, ...]:
    valores = horizonte.get(clave)
    if not valores or any(type(v) is not int or v < 0 for v in valores):
        raise EstudioError(f'la metodología no declara los años «{clave}» como enteros relativos al año 00')
    return tuple(sorted(valores))


def estudio_de(anio_presentacion: int, horizonte: Mapping) -> Estudio:
    """Forma el estudio con el año de presentación y el horizonte de la metodología (072:RF-1, RF-2)."""
    if type(anio_presentacion) is not int or anio_presentacion < 1:
        raise EstudioError(f'año de presentación no válido: {anio_presentacion!r}')
    ciclo = horizonte.get('ciclo_anios')
    if type(ciclo) is not int or ciclo < 1:
        raise EstudioError('la metodología no declara el ciclo de presentación')
    return Estudio(anio_presentacion, anio_presentacion - 1, _desplazamientos(horizonte, 'largo_plazo'),
                   _desplazamientos(horizonte, 'detalle_pide'), ciclo)


def aviso_del_anio_medido(estudio: Estudio, anio_medido: int | None) -> str | None:
    """Si el caso base no se calibró con mediciones del año 00, se dice y se sigue (072:RF-3)."""
    if anio_medido is None:
        return f'no consta el año de la medición del caso base; el año 00 del estudio es {estudio.anio_base}'
    if anio_medido != estudio.anio_base:
        return (f'el caso base se calibró con mediciones de {anio_medido} y el año 00 del estudio, que se '
                f'presenta en {estudio.anio_presentacion}, es {estudio.anio_base}')
    return None
