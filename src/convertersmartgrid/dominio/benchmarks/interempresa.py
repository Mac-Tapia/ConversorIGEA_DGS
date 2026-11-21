"""Dejar una empresa fuera cada vez: ¿lo aprendido de unas empresas vale para otra? (112:RF-15 a RF-19).

La cohorte por empresa de la 112 (``aplicacion/benchmarks/cohortes.py``) reparte los registros, pero nadie medía con ella
si la conversión VNR o el pronóstico generalizan a una empresa que no se vio. Aquí está el bucle, sin E/S ni librerías:
para cada empresa, se ajusta con las demás y se mide en ella, y el veredicto es «DEMOSTRADA» solo si hay al menos
:data:`MINIMO_EMPRESAS` empresas y todas las retenidas pasan su criterio. Con dos empresas cada pliegue se mide, pero un
solo par no sostiene una generalización: el veredicto es «NO DEMOSTRADA» y lo dice (RF-16).

Lo que se ajusta para la conversión VNR es el catálogo de fichas de conductor: el modelo resuelve un tipo de línea sin
ficha por el código más parecido del catálogo (``model.suggest_catalog_code``), así que una empresa nueva se convierte
bien si las fichas de las demás le dan la impedancia de sus propios conductores. Se mide, por longitud, qué parte de los
tramos de la retenida encuentra una ficha en el catálogo de las otras y qué parte la encuentra dentro de la tolerancia de
su propia ficha (RF-17).
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from ..model import suggest_catalog_code
from ..util import cuenta

#: Por debajo de tres empresas, cada pliegue ajusta con una sola: no es una generalización (Plan Maestro PM-17).
MINIMO_EMPRESAS = 3
DEMOSTRADA = 'DEMOSTRADA'
NO_DEMOSTRADA = 'NO DEMOSTRADA'
#: Diferencia relativa admitida entre la ficha del catálogo y la propia, en R1, X1 y corriente admisible.
TOLERANCIA_FICHA = 0.10
#: Parte de la longitud que tiene que acertar la retenida para que su pliegue pase.
UMBRAL_ACIERTO = 0.90

D = TypeVar('D')
M = TypeVar('M')


@dataclass
class Pliegue:
    retenida: str
    entrenamiento: list[str]
    metricas: dict[str, Any] = field(default_factory=dict)
    pasa: bool = False
    motivo: str = ''


@dataclass
class Resultado(Generic[D]):
    veredicto: str
    motivo: str
    empresas: int
    pliegues: list[Pliegue] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        return {'veredicto': self.veredicto, 'motivo': self.motivo, 'empresas': self.empresas,
                'minimo_empresas': MINIMO_EMPRESAS,
                'pliegues': [{'retenida': p.retenida, 'entrenamiento': list(p.entrenamiento), 'metricas': p.metricas,
                              'pasa': p.pasa, 'motivo': p.motivo} for p in self.pliegues]}


def dejar_una_fuera(datos: Mapping[str, D], ajustar: Callable[[Mapping[str, D]], M],
                    medir: Callable[[M, D], Mapping[str, Any]],
                    criterio: Callable[[Mapping[str, Any]], tuple[bool, str]]) -> Resultado:
    """Un pliegue por empresa: ``ajustar`` solo recibe las demás y ``medir`` solo la retenida (112:RF-15).

    Las claves de ``datos`` ya son seudónimos (``E1…En``): el informe las repite tal cual. El orden es el de las claves,
    así que el resultado no depende del orden de llegada.
    """
    empresas = sorted(datos)
    n = len(empresas)
    pliegues: list[Pliegue] = []
    if n >= 2:
        for retenida in empresas:
            resto = {e: datos[e] for e in empresas if e != retenida}
            modelo = ajustar(resto)
            metricas = dict(medir(modelo, datos[retenida]))
            pasa, motivo = criterio(metricas)
            pliegues.append(Pliegue(retenida, sorted(resto), metricas, bool(pasa), motivo))
    if n < MINIMO_EMPRESAS:
        return Resultado(NO_DEMOSTRADA, f'solo hay {cuenta(n, "empresa", "empresas")}: dejar una fuera cada vez pide al menos '
                                        f'{MINIMO_EMPRESAS}, y con menos la generalización entre empresas no está demostrada',
                         n, pliegues)
    caidas = [p for p in pliegues if not p.pasa]
    if caidas:
        detalle = '; '.join(f'{p.retenida}: {p.motivo}' for p in caidas)
        return Resultado(NO_DEMOSTRADA, f'{cuenta(len(caidas), "empresa retenida no pasa", "empresas retenidas no pasan")} '
                                        f'su criterio ({detalle})', n, pliegues)
    return Resultado(DEMOSTRADA, f'las {n} empresas, cada una retenida, pasan su criterio', n, pliegues)


# ------------------------------------------------------------------ conversión VNR: el catálogo de fichas


@dataclass(frozen=True)
class Ficha:
    r1: float
    x1: float
    amps: float


@dataclass
class RedEmpresa:
    """Lo que la conversión de una empresa necesita del catálogo: sus tramos (código, longitud) y sus propias fichas."""

    tramos: list[tuple[str, float]] = field(default_factory=list)
    fichas: dict[str, Ficha] = field(default_factory=dict)


def ajustar_catalogo(entrenamiento: Mapping[str, RedEmpresa]) -> dict[str, Ficha]:
    """El catálogo de las empresas de entrenamiento; un código repetido se queda con la ficha de la primera por orden."""
    catalogo: dict[str, Ficha] = {}
    for empresa in sorted(entrenamiento):
        for codigo, ficha in sorted(entrenamiento[empresa].fichas.items()):
            catalogo.setdefault(codigo, ficha)
    return catalogo


def _cerca(a: float, b: float, tolerancia: float) -> bool:
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    escala = max(abs(a), abs(b))
    return escala == 0 or abs(a - b) / escala <= tolerancia


def ficha_cerca(catalogo: Ficha, propia: Ficha, tolerancia: float = TOLERANCIA_FICHA) -> bool:
    return all(_cerca(getattr(catalogo, c), getattr(propia, c), tolerancia) for c in ('r1', 'x1', 'amps'))


def medir_catalogo(catalogo: Mapping[str, Ficha], red: RedEmpresa, *,
                   tolerancia: float = TOLERANCIA_FICHA) -> dict[str, Any]:
    """Cobertura y acierto, por longitud, de los tramos de la retenida con el catálogo de las demás (112:RF-17).

    Un tramo cuyo código no tiene ficha propia no se puede juzgar: se cuenta aparte y no entra en las fracciones.
    """
    codigos = sorted(catalogo)
    resueltos: dict[str, str | None] = {}
    total = cubierta = acertada = 0.0
    sin_ficha = tramos = 0
    for codigo, longitud in red.tramos:
        propia = red.fichas.get(codigo)
        if propia is None:
            sin_ficha += 1
            continue
        if codigo not in resueltos:
            resueltos[codigo] = suggest_catalog_code(codigo, codigos)
        tramos += 1
        total += longitud
        elegido = resueltos[codigo]
        if elegido is None:
            continue
        cubierta += longitud
        if ficha_cerca(catalogo[elegido], propia, tolerancia):
            acertada += longitud
    return {'tramos': tramos, 'tramos_sin_ficha_propia': sin_ficha, 'longitud': total,
            'cobertura': cubierta / total if total else None, 'acierto': acertada / total if total else None,
            'codigos': len(resueltos), 'tolerancia_ficha': tolerancia}


def criterio_catalogo(umbral: float = UMBRAL_ACIERTO) -> Callable[[Mapping[str, Any]], tuple[bool, str]]:
    def criterio(m: Mapping[str, Any]) -> tuple[bool, str]:
        acierto = m.get('acierto')
        if acierto is None:
            return False, 'sin tramos con ficha propia que medir'
        if acierto < umbral:
            return False, f'acierta el {acierto:.1%} de la longitud con las fichas de las demás, por debajo del {umbral:.0%}'
        return True, f'acierta el {acierto:.1%} de la longitud'
    return criterio
