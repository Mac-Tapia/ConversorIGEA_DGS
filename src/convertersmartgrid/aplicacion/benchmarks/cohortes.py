"""Cohortes de evaluación por empresa y por tiempo (112:RF-6, RF-9).

La unidad de partición es el componente conexo que une a los alimentadores que comparten un cliente o un medidor
(unión-búsqueda, como ``asistente/dataset_entrenamiento.py:particionar_dataset``): un cliente transferido entre dos
alimentadores arrastra a los dos a la misma partición, y ningún alimentador ni cliente cae en dos.

- Por empresa, «una fuera»: la prueba es la empresa retenida entera; el resto se reparte por componentes entre
  entrenamiento, selección y calibración. Se valida con ``particionar_registros`` en modo ``generalizacion``.
- Por tiempo: corte por fecha con una franja de un horizonte sin datos en ninguna parte; la prueba son componentes
  retenidos después de la franja y el resto, otros componentes antes del corte.
- Con una sola empresa no hay cohorte por empresa, y el plan lo dice con :data:`FRASE_UNA_EMPRESA` (RF-9).

La empresa de un origen es la huella de su perfil, nunca su nombre (P13); en el benchmark, ``E1…En``.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..evaluacion_modelos import Particiones, PoliticaEvaluacion, particionar_registros
from ...dominio.util import cuenta

FRASE_UNA_EMPRESA = 'La generalización entre empresas no está demostrada: solo hay datos de una empresa'
#: Reparto de lo que no es prueba, por componentes: entrenamiento, selección y calibración.
FRACCIONES = (0.7, 0.15, 0.15)
#: Parte de los componentes que el corte por tiempo retiene para la prueba.
FRACCION_PRUEBA_TIEMPO = 0.2
_PARTES_AJUSTE = ('entrenamiento', 'seleccion', 'calibracion')


@dataclass(frozen=True)
class Registro:
    id: str
    empresa: str
    alimentador: str
    clientes: tuple[str, ...] = ()
    t: datetime | None = None


@dataclass
class Cohorte:
    nombre: str
    tipo: str                    # «empresa» o «tiempo»
    particiones: Particiones
    retenida: str | None = None
    descartados: int = 0


@dataclass
class Plan:
    cohortes: list[Cohorte] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def seudonimos_de_empresa(huellas: Iterable[str]) -> dict[str, str]:
    """``E1…En`` por el orden de las huellas: no depende del orden de llegada ni deja ver la huella."""
    return {h: f'E{i}' for i, h in enumerate(sorted(set(huellas)), start=1)}


def componentes(registros: Sequence[Registro]) -> dict[str, str]:
    """El componente de cada registro: alimentadores unidos por los clientes que comparten. O(registros·clientes)."""
    padre: dict[str, str] = {}

    def raiz(x: str) -> str:
        padre.setdefault(x, x)
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    def unir(a: str, b: str) -> None:
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            padre[max(ra, rb)] = min(ra, rb)

    for r in registros:
        nodo = f'A:{r.alimentador}'
        raiz(nodo)
        for c in r.clientes:
            unir(nodo, f'C:{c}')
    return {r.id: raiz(f'A:{r.alimentador}') for r in registros}


def _orden(componente: str) -> str:
    # El orden de reparto no sigue el nombre: así los primeros alimentadores no caen siempre en entrenamiento.
    return hashlib.sha256(componente.encode('utf-8')).hexdigest()


def _repartir(comps: Iterable[str]) -> dict[str, str]:
    ordenados = sorted(set(comps), key=_orden)
    n = len(ordenados)
    sel = max(1, round(n * FRACCIONES[1])) if n >= 3 else 0
    cal = max(1, round(n * FRACCIONES[2])) if n >= 3 else 0
    salida = {}
    for i, c in enumerate(ordenados):
        salida[c] = 'seleccion' if i < sel else 'calibracion' if i < sel + cal else 'entrenamiento'
    return salida


def _validar(filas: list[dict]) -> Particiones:
    return particionar_registros(filas, PoliticaEvaluacion(modo='generalizacion'))


def por_empresa(registros: Sequence[Registro], comp: dict[str, str]) -> list[Cohorte]:
    empresas_de: dict[str, set[str]] = {}
    for r in registros:
        empresas_de.setdefault(comp[r.id], set()).add(r.empresa)
    mixtos = [c for c, e in empresas_de.items() if len(e) > 1]
    if mixtos:
        raise ValueError(f'{cuenta(len(mixtos), "componente une", "componentes unen")} alimentadores de más de una empresa: dejar una empresa '
                         'fuera mezclaría las particiones')
    cohortes = []
    for empresa in sorted({r.empresa for r in registros}):
        resto = _repartir(comp[r.id] for r in registros if r.empresa != empresa)
        filas = [{'record_id': r.id, 'group_id': comp[r.id], 'sistema': r.empresa,
                  'particion': 'prueba' if r.empresa == empresa else resto[comp[r.id]]} for r in registros]
        cohortes.append(Cohorte(f'empresa:{empresa}', 'empresa', _validar(filas), retenida=empresa))
    return cohortes


def por_tiempo(registros: Sequence[Registro], comp: dict[str, str], *, corte: datetime,
               horizonte: timedelta) -> Cohorte:
    ordenados = sorted(set(comp.values()), key=_orden)
    n_prueba = max(1, round(len(ordenados) * FRACCION_PRUEBA_TIEMPO))
    de_prueba = set(ordenados[:n_prueba])
    resto = _repartir(ordenados[n_prueba:])
    filas, descartados = [], 0
    for r in registros:
        c = comp[r.id]
        if r.t is None:
            descartados += 1
        elif c in de_prueba and r.t >= corte + horizonte:
            filas.append({'record_id': r.id, 'group_id': c, 'sistema': 'despues', 'particion': 'prueba'})
        elif c not in de_prueba and r.t < corte:
            filas.append({'record_id': r.id, 'group_id': c, 'sistema': 'antes', 'particion': resto[c]})
        else:
            descartados += 1      # la franja, y lo que cruzaría el corte dentro de un mismo componente
    return Cohorte('tiempo', 'tiempo', _validar(filas), descartados=descartados)


def planificar(registros: Sequence[Registro], *, corte: datetime, horizonte: timedelta) -> Plan:
    """Las cohortes de una evaluación: por empresa si hay más de una, y siempre por tiempo."""
    comp = componentes(registros)
    plan = Plan()
    if len({r.empresa for r in registros}) > 1:
        plan.cohortes += por_empresa(registros, comp)
    else:
        plan.avisos.append(FRASE_UNA_EMPRESA)
    plan.cohortes.append(por_tiempo(registros, comp, corte=corte, horizonte=horizonte))
    return plan
