"""Programa de inversiones del área: cada elemento con su año de puesta en servicio, su titular y su área (107:RF-6).

Sale de la alternativa que elige el operador. Un reemplazo son dos filas del mismo año: la baja del elemento que sale
y el alta del que entra, porque así se publican (alta en un cuadro, baja en otro). Con varios titulares, además del
programa del área hay uno por titular, que es como el regulador asigna la responsabilidad de cada proyecto.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from . import PitError
from .ambito import AreaPit

__all__ = ['CambioPlan', 'FilaPrograma', 'Programa', 'comparar_programas', 'programar']

ACCIONES = ('alta', 'baja', 'reemplazo')


@dataclass(frozen=True)
class FilaPrograma:
    anio: int
    accion: str  # 'alta' o 'baja'
    elemento: str
    tipo: str
    titular: str
    area: str
    instalacion: str = ''
    descripcion: str = ''
    reemplaza: str = ''


@dataclass
class Programa:
    area: str
    filas: list[FilaPrograma] = field(default_factory=list)

    def por_titular(self) -> dict[str, list[FilaPrograma]]:
        out: dict[str, list[FilaPrograma]] = {}
        for f in self.filas:
            out.setdefault(f.titular, []).append(f)
        return dict(sorted(out.items()))

    def como_dict(self) -> dict[str, Any]:
        return {'area': self.area, 'filas': [asdict(f) for f in self.filas],
                'por_titular': {t: [asdict(f) for f in fs] for t, fs in self.por_titular().items()}}


def programar(area: AreaPit, cambios: Iterable[Mapping[str, Any]]) -> Programa:
    """Del conjunto de cambios de la alternativa elegida al programa ordenado por año, acción, titular y elemento."""
    filas = []
    for i, c in enumerate(cambios):
        origen = f'cambio {i + 1} ({c.get("elemento") or "sin elemento"})'
        accion = str(c.get('accion') or '')
        if accion not in ACCIONES:
            raise PitError(f'{origen}: la acción tiene que ser una de {ACCIONES}, no {accion!r}')
        for clave in ('elemento', 'anio', 'titular'):
            if c.get(clave) in (None, ''):
                raise PitError(f'{origen}: sin «{clave}» no se programa')
        titular = str(c['titular'])
        if titular not in area.titulares:
            raise PitError(f'{origen}: el titular {titular!r} no es del área {area.codigo} '
                           f'(pit.areas[].titulares: {list(area.titulares)})')
        comun = {'anio': int(c['anio']), 'tipo': str(c.get('tipo') or ''), 'titular': titular, 'area': area.codigo,
                 'instalacion': str(c.get('instalacion') or ''), 'descripcion': str(c.get('descripcion') or '')}
        if accion == 'reemplazo':
            if not c.get('reemplaza'):
                raise PitError(f'{origen}: un reemplazo dice qué elemento sale («reemplaza»)')
            filas.append(FilaPrograma(accion='baja', elemento=str(c['reemplaza']),
                                      **{**comun, 'descripcion': f'sale por {c["elemento"]}'}))
            filas.append(FilaPrograma(accion='alta', elemento=str(c['elemento']), reemplaza=str(c['reemplaza']),
                                      **comun))
        else:
            filas.append(FilaPrograma(accion=accion, elemento=str(c['elemento']), **comun))
    filas.sort(key=lambda f: (f.anio, f.accion != 'alta', f.titular, f.elemento))
    return Programa(area.codigo, filas)


@dataclass(frozen=True)
class CambioPlan:
    """Un elemento que la modificación del plan vigente elimina, cambia o agrega, con su razón (107:RF-17)."""

    elemento: str
    accion: str  # la del programa: 'alta' o 'baja'
    cambio: str  # 'elimina', 'cambia' o 'agrega'
    razon: str
    antes: Mapping[str, Any] | None
    despues: Mapping[str, Any] | None


def comparar_programas(vigente: Programa, nuevo: Programa, razones: Mapping[str, str]) -> list[CambioPlan]:
    """Lo que el programa nuevo elimina, cambia o agrega respecto del vigente, cada cosa con su razón.

    Las filas se casan por elemento y acción. ``razones`` es elemento → razón, y la da el operador: un cambio sin
    razón es un error que nombra los elementos, porque el regulador pide la razón de cada uno. Dos programas de áreas
    distintas no se comparan.
    """
    if vigente.area != nuevo.area:
        raise PitError(f'el programa vigente es del área {vigente.area} y el nuevo del área {nuevo.area}: '
                       'una modificación se hace sobre la misma área')

    def clave(f: FilaPrograma) -> tuple[str, str]:
        return (f.elemento, f.accion)

    antes = {clave(f): asdict(f) for f in vigente.filas}
    ahora = {clave(f): asdict(f) for f in nuevo.filas}
    for nombre, filas in (('vigente', vigente.filas), ('nuevo', nuevo.filas)):
        cuenta = Counter(clave(f) for f in filas)
        repetidos = sorted(f'{e} ({a})' for (e, a), n in cuenta.items() if n > 1)
        if repetidos:
            raise PitError(f'el programa {nombre} tiene filas repetidas: {repetidos}')
    cambios = []
    for k in sorted(set(antes) | set(ahora)):
        a, d = antes.get(k), ahora.get(k)
        if a == d:
            continue
        tipo = 'elimina' if d is None else 'agrega' if a is None else 'cambia'
        cambios.append((k, tipo, a, d))
    sin_razon = sorted({k[0] for k, *_ in cambios if not str(razones.get(k[0]) or '').strip()})
    if sin_razon:
        raise PitError(f'la modificación del plan necesita la razón de cada cambio; faltan las de {sin_razon}')
    return [CambioPlan(k[0], k[1], tipo, str(razones[k[0]]).strip(), a, d) for k, tipo, a, d in cambios]
