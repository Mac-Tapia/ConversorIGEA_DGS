"""Escenarios y aprendizaje activo del gemelo digital (spec 024, T10; RF-11, RF-12, RF-40, RF-41).

Un modelo no aprende de una sola maniobra (RF-11): alrededor de cada estado aceptado se
genera una matriz de escenarios (demanda escalada y tramos fuera de servicio), se simulan
en DIgSILENT sobre una copia del proyecto y entran al búfer como ``counterfactual``. Cuando
ya hay un oráculo, se eligen primero los escenarios donde más duda (RF-40); sin él, los
más distintos entre sí. Todo dentro del presupuesto de licencia del perfil (RF-41).

Solo escala y maniobras: nunca SED ni cargas inventadas (memoria del proyecto).
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

#: Particiones del aprendizaje (RF-12) y su peso.
PARTICIONES = (('entrenamiento', 0.7), ('validacion', 0.15), ('prueba', 0.15))


@dataclass(frozen=True)
class Escenario:
    """Una variante del estado base: demanda escalada y tramos abiertos."""

    factor_carga: float
    tramos_abiertos: tuple[str, ...] = ()

    @property
    def clave(self) -> str:
        return hashlib.sha256(json.dumps([round(self.factor_carga, 4), sorted(self.tramos_abiertos)])
                              .encode()).hexdigest()[:16]


def rango_medido(curvas: Iterable[Sequence[float]], margen: float = 0.1) -> tuple[float, float] | None:
    """Del total coincidente de las cabeceras, su mínimo y su máximo relativos a la punta, con
    ``margen`` por encima (027:RF-4): los factores fijos 0,7–1,3 no cubrían el valle de la
    noche, donde una cabecera rural baja al 30 % de su punta, y el gemelo solo veía la punta."""
    series = [[float(v) for v in c] for c in curvas if c]
    if not series:
        return None
    largo = min(len(s) for s in series)
    total = [sum(s[i] for s in series) for i in range(largo)]
    punta = max(total) if total else 0.0
    if punta <= 0:
        return None
    return max(min(total) / punta, 0.0), 1.0 + margen


def factores_hipercubo(minimo: float, maximo: float, n: int, semilla: int = 0) -> tuple[float, ...]:
    """``n`` factores de demanda por hipercubo latino en ``[minimo, maximo]`` (027:RF-4): uno en
    cada franja de igual ancho, en una posición sorteada dentro de ella, y en orden creciente.
    Determinista por semilla."""
    if n <= 0 or maximo <= minimo:
        return ()
    rnd = random.Random(semilla)
    ancho = (maximo - minimo) / n
    return tuple(round(minimo + (k + rnd.random()) * ancho, 4) for k in range(n))


def matriz(tramos: Sequence[str], *, factores: Sequence[float] = (0.7, 0.85, 1.0, 1.15, 1.3),
           contingencias: int = 20, semilla: int = 0) -> list[Escenario]:
    """Factores de demanda por cada estado: intacto y con un tramo fuera (N-1) sorteado.

    Determinista por semilla, para poder repetir la misma matriz.
    """
    rnd = random.Random(semilla)
    elegidos = rnd.sample(sorted(tramos), min(contingencias, len(tramos)))
    out = [Escenario(float(f)) for f in factores]
    out += [Escenario(float(f), (t,)) for t in elegidos for f in factores]
    return out


def familia(episodio: Mapping[str, Any]) -> str:
    """Familia topológica: proyecto, alimentadores y tramos abiertos, sin la demanda.

    Las variantes de una misma maniobra comparten familia, y una familia cae entera en una
    sola partición: si no, el modelo se examinaría con lo que ya vio (RF-12).
    """
    nativo = episodio.get('nativo') or {}
    accion = episodio.get('accion') or {}
    abiertos = sorted((accion.get('escenario') or {}).get('tramos_abiertos') or
                      (episodio.get('topologia') or {}).get('frontera') or [])
    base = [nativo.get('project'), sorted(nativo.get('feeders') or []), abiertos]
    return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:16]


def particion(clave_familia: str) -> str:
    """Partición fija de una familia, por su huella (RF-12): no cambia al crecer el búfer."""
    x = int(clave_familia[:8], 16) / 0xFFFFFFFF
    acumulado = 0.0
    for nombre, peso in PARTICIONES:
        acumulado += peso
        if x <= acumulado:
            return nombre
    return PARTICIONES[-1][0]


def elegir(escenarios: Sequence[Escenario], n: int,
           incertidumbre: Callable[[Escenario], float] | None = None,
           hechos: Iterable[str] = ()) -> list[Escenario]:
    """Los ``n`` escenarios que más enseñan y que aún no se simularon (RF-40).

    Con oráculo, los de mayor incertidumbre; sin él, los más alejados de lo ya elegido en
    demanda y tramos (máxima diversidad), empezando por el intacto a demanda nominal.
    """
    hechos = set(hechos)
    pendientes = [e for e in escenarios if e.clave not in hechos]
    if incertidumbre is not None:
        return sorted(pendientes, key=lambda e: (-incertidumbre(e), e.clave))[:n]
    elegidos: list[Escenario] = []
    while pendientes and len(elegidos) < n:
        def lejania(e: Escenario) -> float:
            if not elegidos:
                return -abs(e.factor_carga - 1.0) - len(e.tramos_abiertos)
            return min(abs(e.factor_carga - x.factor_carga)
                       + (0 if set(e.tramos_abiertos) == set(x.tramos_abiertos) else 1)
                       for x in elegidos)
        mejor = max(pendientes, key=lambda e: (lejania(e), e.clave))
        elegidos.append(mejor)
        pendientes.remove(mejor)
    return elegidos


@dataclass
class Presupuesto:
    """Segundos de DIgSILENT que puede usar el aprendizaje activo (RF-41)."""

    segundos: float
    reloj: Callable[[], float] = time.monotonic
    inicio: float = field(init=False)

    def __post_init__(self):
        self.inicio = self.reloj()

    @property
    def restante(self) -> float:
        return self.segundos - (self.reloj() - self.inicio)

    def alcanza(self, estimado_s: float) -> bool:
        return self.restante >= estimado_s
