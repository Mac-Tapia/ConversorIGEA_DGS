"""El ámbito de un área de demanda del PIT: qué elementos de la red le tocan y cuáles no (107:RF-2, 107:RF-11).

Por qué así. El PIT se aprueba por área de demanda, y una línea o una SET puede servir a dos áreas. Mezclar áreas
daría un diagnóstico con la demanda de una y la red de otra; repartir un elemento a partes iguales sería un dato
inventado. Por eso la asignación de lo compartido la declara el perfil (``pit.areas[].compartidos``); sin ella, el
elemento entra en cada área que toca, marcado como compartido sin asignar, y su diagnóstico no se da por completo
(107:RF-4).

Un elemento es del ámbito si declara el área entre las suyas y, además, es de una SET del área o su tensión llega a
la mínima del ámbito (``tension_min_kv``, sin valor por defecto: es de cada área).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from . import PitError

__all__ = ['AreaPit', 'Ambito', 'PitError', 'areas_del_perfil', 'reunir']


@dataclass(frozen=True)
class AreaPit:
    codigo: str
    titulares: tuple[str, ...]
    set: tuple[str, ...]
    set_alimentadores: Mapping[str, tuple[str, ...]]
    tension_min_kv: float
    compartidos: Mapping[str, str]
    #: Ubicación geográfica del área para el COyM (``costa``, ``sierra`` o ``selva``); vacía si el perfil no la declara,
    #: y entonces el COyM por cuadro es un hueco nombrado (aclaración de 107:RF-5). Sin valor por defecto.
    ubicacion: str = ''


@dataclass
class Ambito:
    area: AreaPit
    elementos: list[dict[str, Any]] = field(default_factory=list)
    #: Elementos que tocan varias áreas sin asignación en el perfil: entran, pero su diagnóstico queda incompleto.
    compartidos_sin_asignar: list[str] = field(default_factory=list)
    #: Elementos que declaran esta área y no entran, con su motivo.
    excluidos: dict[str, str] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


def _area(datos: Mapping[str, Any], i: int) -> AreaPit:
    origen = f'pit.areas[{i}]'
    for clave in ('codigo', 'titulares', 'tension_min_kv'):
        if datos.get(clave) in (None, '', []):
            raise PitError(f'{origen}.{clave}: el perfil no lo declara, y el PIT no lo supone')
    if not isinstance(datos.get('set'), (list, tuple)):
        raise PitError(f'{origen}.set: el perfil tiene que declarar la lista de SET del área (puede ser vacía)')
    try:
        tension = float(datos['tension_min_kv'])
    except (TypeError, ValueError):
        raise PitError(f'{origen}.tension_min_kv: tiene que ser un número, no {datos["tension_min_kv"]!r}') from None
    if tension <= 0:
        raise PitError(f'{origen}.tension_min_kv: tiene que ser mayor que 0, no {tension!r}')
    # La ubicación se comprueba contra el cuadro del registro al usarla: la lista de ubicaciones es de la norma.
    ubicacion = str(datos.get('ubicacion') or '').strip().lower()
    return AreaPit(codigo=str(datos['codigo']), titulares=tuple(map(str, datos['titulares'])),
                   set=tuple(map(str, datos['set'])),
                   set_alimentadores={str(s): tuple(map(str, a))
                                      for s, a in (datos.get('set_alimentadores') or {}).items()},
                   tension_min_kv=tension,
                   compartidos={str(k): str(v) for k, v in (datos.get('compartidos') or {}).items()},
                   ubicacion=ubicacion)


def areas_del_perfil(perfil: Mapping[str, Any], codigo: str | None = None) -> list[AreaPit]:
    """Las áreas de ``pit.areas``; con ``codigo``, solo esa (y un error si el perfil no la declara)."""
    pit = perfil.get('pit') if isinstance(perfil, Mapping) else None
    datos = (pit or {}).get('areas') if isinstance(pit, Mapping) else None
    if not datos:
        raise PitError('pit.areas: el perfil no declara ningún área de demanda')
    areas = [_area(a, i) for i, a in enumerate(datos)]
    codigos = [a.codigo for a in areas]
    if len(set(codigos)) != len(codigos):
        raise PitError(f'pit.areas: un código de área repetido en {codigos}')
    if codigo is None:
        return areas
    elegidas = [a for a in areas if a.codigo == codigo]
    if not elegidas:
        raise PitError(f'el perfil no declara el área {codigo!r} en pit.areas (declara {codigos})')
    return elegidas


def reunir(area: AreaPit, elementos: Iterable[Mapping[str, Any]]) -> Ambito:
    """Los elementos del área, en el orden de entrada (determinista), sin los de otras áreas."""
    amb = Ambito(area)
    sets = set(area.set)
    for e in elementos:
        areas = [str(a) for a in (e.get('areas') or ())]
        if area.codigo not in areas:
            continue
        eid = str(e.get('id'))
        if len(areas) > 1:
            asignada = area.compartidos.get(eid)
            if asignada and asignada != area.codigo:
                amb.excluidos[eid] = f'compartido, asignado al área {asignada} en el perfil'
                continue
            if not asignada:
                amb.compartidos_sin_asignar.append(eid)
                amb.avisos.append(f'{eid} es compartido con {", ".join(a for a in areas if a != area.codigo)} y el '
                                  'perfil no lo asigna (pit.areas[].compartidos): su diagnóstico no será completo')
        de_set = e.get('set') is not None and str(e.get('set')) in sets
        kv = e.get('kv')
        if not de_set and (kv is None or float(kv) < area.tension_min_kv):
            amb.excluidos[eid] = (f'tensión {kv} kV menor que la mínima del ámbito ({area.tension_min_kv} kV) y '
                                  'fuera de las SET del área')
            continue
        amb.elementos.append(dict(e))
    return amb
