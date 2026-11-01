"""Troncal por el camino más largo, aguas abajo de un nodo y punto de conexión (spec 016).

La troncal de la spec 011 es la de ``ComBbone``, y DIgSILENT solo la dibuja entre
alimentadores con un enlace: IN111 no tenía ninguno y se quedó sin troncal el 2026-10-14,
cuando el usuario pidió pasarla entera a 120 mm². Para las obras la troncal es, en sus
palabras, «el conjunto de tramos continuos que hacen el más largo del alimentador»
(RF-1): aquí se calcula con la red que lee el guion de DIgSILENT, sin PowerFactory, para
probarla con redes sorteadas. El N-1 y la transferencia siguen con la de ``ComBbone``
(RF-10).

El enlace y las cargas nuevas se conectan en el punto de la troncal más cercano, partiendo
el tramo con una barra nueva (RF-15 a RF-20): aquí se elige el tramo, la fracción y si se
usa la barra de un extremo; el guion lo hace con ``Application.SplitLine``.

La troncal es un recorrido de la red de un alimentador, sin mirar los demás (constitución
P2).
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from functools import cached_property
from typing import Iterable, Mapping, NamedTuple, Sequence

from .dgs import _geo_to_meters

#: Dos caminos cuya longitud difiere menos que esto son iguales (m): las longitudes de
#: DIgSILENT son ``float`` en km y la suma depende del orden.
TOLERANCIA_M = 1e-6


class TroncalError(ValueError):
    """La red no permite el cálculo pedido: lo dice con el nombre que falla."""


@dataclass(frozen=True)
class Barra:
    nombre: str
    kv: float | None = None
    gps: tuple[float, float] | None = None
    """(latitud, longitud); ``None`` si DIgSILENT la tiene a 0, 0."""


@dataclass(frozen=True)
class Tramo:
    nombre: str
    desde: str
    hasta: str
    largo_m: float
    cerrado: bool = True
    """Falso si está abierto o fuera de servicio: no cuenta para la troncal (RF-4)."""
    cable: bool = False
    trazado: tuple[tuple[float, float], ...] = ()
    """``GPScoords`` de DIgSILENT, de ``desde`` a ``hasta``."""


@dataclass(frozen=True)
class Red:
    """La red de un alimentador tal como la lee el guion en el caso de la obra (RF-2)."""

    barras: Mapping[str, Barra]
    tramos: Sequence[Tramo]

    @cached_property
    def vecinos(self) -> dict[str, list[tuple[str, Tramo]]]:
        """Barra → (otra barra, tramo) por los tramos cerrados, ordenados por nombre.

        El orden por nombre hace el recorrido independiente del orden en que DIgSILENT
        devuelve los objetos (RF-5).
        """
        out: dict[str, list[tuple[str, Tramo]]] = {}
        for t in self.tramos:
            if not t.cerrado or t.desde == t.hasta:
                continue
            out.setdefault(t.desde, []).append((t.hasta, t))
            out.setdefault(t.hasta, []).append((t.desde, t))
        for lista in out.values():
            lista.sort(key=lambda par: (par[1].nombre, par[0]))
        return out

    def por_nombre(self) -> dict[str, Tramo]:
        return {t.nombre: t for t in self.tramos}


@dataclass(frozen=True)
class Arbol:
    """El recorrido desde la cabecera: de cada barra, el tramo por el que se llega."""

    cabecera: str
    padre: Mapping[str, tuple[str, Tramo] | None]
    distancia_m: Mapping[str, float]
    orden: tuple[str, ...]
    mallas: tuple[str, ...] = ()
    """Tramos cerrados que cierran un anillo: no entran en el árbol y se avisan."""

    def camino(self, barra: str) -> list[Tramo]:
        """Tramos de la cabecera a ``barra``, en ese orden."""
        out = []
        while self.padre[barra] is not None:
            barra, tramo = self.padre[barra]
            out.append(tramo)
        out.reverse()
        return out


def arbol(red: Red, cabecera: str) -> Arbol:
    """Árbol de los caminos más cortos en metros desde la cabecera, por los tramos cerrados.

    La red de distribución es radial, pero el modelo puede traer anillos cerrados: IN111
    del TXT de referencia tiene tres. Un recorrido en anchura cuenta saltos, y con un
    anillo el «camino» de una barra salía por el lado de menos tramos aunque fuera más
    largo. Con los caminos más cortos en metros, cada barra cuelga del lado por el que
    llega la energía. El tramo que cierra un anillo se deja fuera y se dice en ``mallas``,
    sin bloquear. A igual distancia decide el nombre del tramo (RF-5).
    """
    if cabecera not in red.barras and cabecera not in red.vecinos:
        raise TroncalError(f'la cabecera {cabecera} no está en la red del alimentador')
    padre: dict[str, tuple[str, Tramo] | None] = {}
    distancia: dict[str, float] = {}
    orden: list[str] = []
    # (distancia, tramo de llegada, barra, barra de la que viene, tramo). El nombre del
    # tramo es único, así que la tupla nunca llega a comparar el objeto.
    cola: list = [(0.0, '', cabecera, '', None)]
    while cola:
        d, _, u, desde, tramo = heapq.heappop(cola)
        if u in padre:
            continue
        padre[u] = None if tramo is None else (desde, tramo)
        distancia[u] = d
        orden.append(u)
        for v, t in red.vecinos.get(u, ()):
            if v not in padre:
                heapq.heappush(cola, (d + t.largo_m, t.nombre, v, u, t))
    en_arbol = {p[1].nombre for p in padre.values() if p is not None}
    mallas = sorted({t.nombre for t in red.tramos if t.cerrado and t.desde != t.hasta
                     and t.desde in padre and t.hasta in padre and t.nombre not in en_arbol})
    return Arbol(cabecera, padre, distancia, tuple(orden), tuple(mallas))


@dataclass(frozen=True)
class Troncal:
    tramos: tuple[str, ...]
    """De la cabecera al final, en orden."""
    largo_m: float
    mallas: tuple[str, ...] = ()


def troncal(red: Red, cabecera: str) -> Troncal:
    """Los tramos del camino continuo más largo que sale de la cabecera (RF-1, RF-3, RF-4).

    A igual longitud, el camino cuya tupla de nombres de tramo es menor (RF-5).
    """
    a = arbol(red, cabecera)
    maximo = max(a.distancia_m.values())
    finales = [b for b in a.orden if a.distancia_m[b] >= maximo - TOLERANCIA_M]
    caminos = [tuple(t.nombre for t in a.camino(b)) for b in finales]
    mejor = min(caminos)
    largo = sum(red.por_nombre()[n].largo_m for n in mejor)
    return Troncal(mejor, largo, a.mallas)


@dataclass(frozen=True)
class Subarbol:
    """El nodo y todo lo que cuelga de él, visto desde la cabecera (016:RF-64)."""

    nodo: str
    barras: tuple[str, ...]
    tramos: tuple[str, ...]
    entrada: str | None
    """Tramo que llega al nodo desde la cabecera; ``None`` si el nodo es la cabecera."""


def aguas_abajo(red: Red, cabecera: str, nodo: str) -> Subarbol:
    """Barras y tramos del nodo hacia afuera, por los tramos cerrados."""
    a = arbol(red, cabecera)
    if nodo not in a.padre:
        raise TroncalError(f'el nodo {nodo} no está en el alimentador o no tiene camino '
                           f'cerrado desde su cabecera {cabecera}')
    hijos: dict[str, list[tuple[str, Tramo]]] = {}
    for b in a.orden:
        p = a.padre[b]
        if p is not None:
            hijos.setdefault(p[0], []).append((b, p[1]))
    barras, tramos = [nodo], []
    pila = [nodo]
    while pila:
        u = pila.pop()
        for v, t in hijos.get(u, ()):
            barras.append(v)
            tramos.append(t.nombre)
            pila.append(v)
    entrada = a.padre[nodo][1].nombre if a.padre[nodo] is not None else None
    return Subarbol(nodo, tuple(sorted(barras)), tuple(sorted(tramos)), entrada)


def red_de(barras: Iterable[Barra], tramos: Iterable[Tramo]) -> Red:
    return Red({b.nombre: b for b in barras}, tuple(tramos))


# --------------------------------------------------------------------------- conexión
class _Geo(NamedTuple):
    lat: float
    lon: float


Punto = tuple[float, float]
"""(latitud, longitud)."""


def _metros(p: Punto, origen: Punto) -> tuple[float, float]:
    """Metros locales este/norte respecto a ``origen``: la misma cuenta que el diagrama."""
    return _geo_to_meters(_Geo(*p), origen[0], origen[1])


def _sobre_segmento(q, a, b) -> tuple[float, float]:
    """(t en [0, 1], distancia) del punto del segmento a-b más cercano a q, en metros."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo2 = dx * dx + dy * dy
    s = 0.0 if largo2 == 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / largo2))
    return s, math.hypot(q[0] - a[0] - s * dx, q[1] - a[1] - s * dy)


def _interpolar(p: Punto, q: Punto, s: float) -> Punto:
    return (p[0] + s * (q[0] - p[0]), p[1] + s * (q[1] - p[1]))


def trazado_de(red: Red, tramo: Tramo) -> tuple[Punto, ...]:
    """El trazado GPS del tramo o, sin él, la recta entre sus dos barras (RF-15)."""
    if len(tramo.trazado) >= 2:
        return tuple(tuple(p) for p in tramo.trazado)
    a, b = red.barras.get(tramo.desde), red.barras.get(tramo.hasta)
    if a is not None and b is not None and a.gps is not None and b.gps is not None:
        return (tuple(a.gps), tuple(b.gps))
    return ()


def _largo_m(trazado: Sequence[Punto]) -> float:
    xy = [_metros(p, trazado[0]) for p in trazado]
    return sum(math.dist(a, b) for a, b in zip(xy, xy[1:]))


def punto_mas_cercano(trazado: Sequence[Punto], punto: Punto) -> tuple[float, float, Punto]:
    """(fracción del trazado desde su inicio, distancia en m, punto) más cercano a ``punto``.

    La fracción se mide en metros a lo largo del trazado, no por vértices: es la que
    reparte la longitud del tramo al partirlo (RF-18). A igual distancia, el primero.
    """
    if len(trazado) < 2:
        raise TroncalError('el tramo no tiene trazado ni coordenadas en sus dos barras')
    xy = [_metros(p, punto) for p in trazado]
    largos = [math.dist(a, b) for a, b in zip(xy, xy[1:])]
    total = sum(largos)
    mejor = None
    acumulado = 0.0
    for i, (a, b) in enumerate(zip(xy, xy[1:])):
        s, d = _sobre_segmento((0.0, 0.0), a, b)
        if mejor is None or d < mejor[1] - TOLERANCIA_M:
            mejor = (acumulado + s * largos[i], d, i, s)
        acumulado += largos[i]
    a_lo_largo, d, i, s = mejor
    return ((a_lo_largo / total if total > 0 else 0.0), d,
            _interpolar(trazado[i], trazado[i + 1], s))


def partir(largo: float, fraccion: float) -> tuple[float, float]:
    """Longitudes de los dos tramos, que suman la del original (RF-18)."""
    primero = largo * fraccion
    return primero, largo - primero


def cortar_trazado(trazado: Sequence[Punto], fraccion: float
                   ) -> tuple[tuple[Punto, ...], tuple[Punto, ...]]:
    """El trazado de cada mitad: ``SplitLine`` deja el entero en las dos (T1 de la 016)."""
    if len(trazado) < 2:
        return tuple(trazado), tuple(trazado)
    xy = [_metros(p, trazado[0]) for p in trazado]
    largos = [math.dist(a, b) for a, b in zip(xy, xy[1:])]
    objetivo = sum(largos) * min(1.0, max(0.0, fraccion))
    acumulado = 0.0
    for i, largo in enumerate(largos):
        if acumulado + largo >= objetivo or i == len(largos) - 1:
            s = 0.0 if largo == 0 else min(1.0, (objetivo - acumulado) / largo)
            corte = _interpolar(trazado[i], trazado[i + 1], s)
            return tuple(trazado[:i + 1]) + (corte,), (corte,) + tuple(trazado[i + 1:])
        acumulado += largo
    raise AssertionError('inalcanzable')


@dataclass(frozen=True)
class Conexion:
    """Dónde se conecta: dentro de un tramo, que se parte, o en una barra existente."""

    tramo: str
    """Tramo más cercano, se parta o no."""
    fraccion: float
    """Desde la barra ``desde`` del tramo, en [0, 1]: ``SplitLine`` la pide en % desde bus1."""
    gps: Punto
    distancia_m: float
    """Del punto pedido al de conexión."""
    barra: str | None = None
    """Barra existente en que se conecta sin partir (RF-20, RF-67); ``None`` si se parte."""

    @property
    def parte(self) -> bool:
        return self.barra is None


def conexion_en(red: Red, tramo: Tramo, punto: Punto, minima_m: float | None) -> Conexion:
    """El punto de ``tramo`` más cercano a ``punto``, o la barra de un extremo.

    Se usa la barra si el punto queda a menos de ``minima_m`` de ella a lo largo del
    trazado (RF-20); sin distancia mínima, solo si coincide con ella (RF-67).
    """
    trazado = trazado_de(red, tramo)
    fraccion, distancia, gps = punto_mas_cercano(trazado, punto)
    total = _largo_m(trazado)
    al_desde, al_hasta = fraccion * total, (1 - fraccion) * total
    cerca = min(al_desde, al_hasta)
    if cerca <= TOLERANCIA_M or (minima_m is not None and cerca < float(minima_m)):
        barra = tramo.desde if al_desde <= al_hasta else tramo.hasta
        fraccion, gps = (0.0, trazado[0]) if barra == tramo.desde else (1.0, trazado[-1])
        distancia = math.hypot(*_metros(gps, punto))
        return Conexion(tramo.nombre, fraccion, tuple(gps), distancia, barra)
    return Conexion(tramo.nombre, fraccion, tuple(gps), distancia)


def punto_en_troncal(red: Red, tramos: Iterable[str], punto: Punto,
                     minima_m: float | None = None) -> Conexion | None:
    """El punto de los ``tramos`` (la troncal) más cercano a ``punto`` (RF-28, RF-45).

    Solo cuentan los tramos con trazado o con GPS en sus dos barras; ``None`` si ninguno
    lo tiene (RF-33, RF-50). A igual distancia, el tramo de nombre menor (RF-5).
    """
    por_nombre = red.por_nombre()
    mejor = None
    for nombre in sorted(tramos):
        trazado = trazado_de(red, por_nombre[nombre])
        if not trazado:
            continue
        _, d, _ = punto_mas_cercano(trazado, punto)
        if mejor is None or d < mejor[0] - TOLERANCIA_M:
            mejor = (d, por_nombre[nombre])
    if mejor is None:
        return None
    return conexion_en(red, mejor[1], punto, minima_m)


def _segmentos(red: Red, tramos: Iterable[str], origen: Punto) -> list:
    """(tramo, punto a, punto b, a en m, b en m) de cada segmento de los trazados."""
    por_nombre = red.por_nombre()
    out = []
    for nombre in sorted(tramos):
        trazado = trazado_de(red, por_nombre[nombre])
        for p, q in zip(trazado, trazado[1:]):
            out.append((nombre, p, q, _metros(p, origen), _metros(q, origen)))
    return out


def _distancia_segmentos(a, b, c, d) -> tuple[float, float]:
    """(distancia, t sobre a-b) del par de puntos más cercanos de dos segmentos, en m."""
    def lado(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1, d2, d3, d4 = lado(c, d, a), lado(c, d, b), lado(a, b, c), lado(a, b, d)
    if d1 * d2 < 0 and d3 * d4 < 0:                       # se cruzan
        return 0.0, d1 / (d1 - d2)
    opciones = [(_sobre_segmento(a, c, d)[1], 0.0), (_sobre_segmento(b, c, d)[1], 1.0)]
    for p in (c, d):
        s, dist = _sobre_segmento(p, a, b)
        opciones.append((dist, s))
    return min(opciones)


def extremos_del_enlace(recibe: Red, candidatos: Iterable[str], cede: Red,
                        troncal_cede: Iterable[str], minima_m: float | None = None
                        ) -> tuple[Conexion, Conexion]:
    """Origen en los tramos candidatos del que recibe y destino en la troncal del que cede.

    El origen es el punto de los candidatos (RF-26) más cercano a la troncal del que cede
    (RF-27); el destino, el punto de esa troncal más cercano al origen (RF-28). Se comparan
    segmento a segmento y se descarta por caja envolvente el par que no puede mejorar: se
    hace una vez por obra, con dos troncales.
    """
    candidatos, troncal_cede = list(candidatos), list(troncal_cede)
    puntos = [p for red, ts in ((recibe, candidatos), (cede, troncal_cede))
              for n in ts for p in trazado_de(red, red.por_nombre()[n])]
    if not puntos:
        raise TroncalError('ningún tramo de los dos alimentadores tiene coordenadas')
    origen = puntos[0]
    de_recibe = _segmentos(recibe, candidatos, origen)
    de_cede = _segmentos(cede, troncal_cede, origen)
    if not de_recibe or not de_cede:
        falta = 'el que recibe' if not de_recibe else 'el que cede'
        raise TroncalError(f'ningún tramo de la troncal de {falta} tiene coordenadas')

    def caja(a, b):
        return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])

    def separacion(c1, c2):
        return math.hypot(max(0.0, c2[0] - c1[2], c1[0] - c2[2]),
                          max(0.0, c2[1] - c1[3], c1[1] - c2[3]))

    cajas_cede = [caja(s[3], s[4]) for s in de_cede]
    mejor = None
    for nombre, p, q, a, b in de_recibe:
        c1 = caja(a, b)
        for (_, _, _, c, d), c2 in zip(de_cede, cajas_cede):
            if mejor is not None and separacion(c1, c2) >= mejor[0] - TOLERANCIA_M:
                continue
            dist, s = _distancia_segmentos(a, b, c, d)
            if mejor is None or dist < mejor[0] - TOLERANCIA_M:
                mejor = (dist, nombre, _interpolar(p, q, s))
    _, nombre, punto = mejor
    salida = conexion_en(recibe, recibe.por_nombre()[nombre], punto, minima_m)
    llegada = punto_en_troncal(cede, troncal_cede, salida.gps, minima_m)
    return salida, llegada
