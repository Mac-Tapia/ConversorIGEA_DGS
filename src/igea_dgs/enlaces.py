"""Puntos de enlace y caminos cerrados de la red unida (spec 022, RF-26 a RF-31, RF-34).

La red de distribución se opera radial: cada barra se alimenta desde una sola SET por un
solo camino, y los alimentadores se enlazan con maniobras normalmente abiertas. El usuario,
el 2026-10-17: «lo que debe identificar son los puntos de enlace y abrirlos para ejecutar
el flujo de potencia; ahí debe trabajar el oráculo», y los anillos dentro de un mismo
alimentador «debe abrirlos» (IN111 trae tres en el TXT de referencia).

Los enlaces entre alimentadores ya salen de la unión (:class:`~igea_dgs.combine.TiePoint`,
abiertos). Aquí se buscan los caminos cerrados que queden —por tramos y maniobras
cerrados— entre dos SET, entre dos alimentadores o dentro de uno, y se abre en cada uno la
maniobra más lejana de su fuente o, si no tiene ninguna, el tramo más lejano.
"""
from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass, replace

from .model import FeederModel, SwitchingDevice

_RAIZ = '\x00raiz'


@dataclass(frozen=True)
class Apertura:
    """Lo que se abrió para que la red quede radial (022:RF-34)."""

    elemento: str
    clase: str              # 'acoplador' | 'maniobra' | 'tramo'
    motivo: str             # 'entre_set' | 'entre_alimentadores' | 'anillo'
    alimentadores: tuple[str, ...]
    sets: tuple[str, ...]

    def texto(self) -> str:
        que = {'entre_set': 'camino cerrado entre ' + ' y '.join(self.sets),
               'entre_alimentadores': 'camino cerrado entre ' + ' y '.join(self.alimentadores),
               'anillo': f'anillo de {self.alimentadores[0]}'}[self.motivo]
        return f'{self.clase} {self.elemento} abierto: {que} (022:RF-30, RF-31)'


def enlaces(model: FeederModel) -> list[dict]:
    """Los puntos de enlace con sus dos alimentadores y sus dos SET (022:RF-26, RF-27)."""
    info = model.combined
    if info is None:
        return []
    set_de = {c.feeder: c.set_codigo for c in info.cabeceras}
    return [{'nombre': t.name, 'nodo': t.original_node, 'alimentadores': (t.feeder_a, t.feeder_b),
             'sets': (set_de.get(t.feeder_a, 'Sin SET'), set_de.get(t.feeder_b, 'Sin SET')),
             'kv': t.nominal_kv} for t in info.ties]


def fuentes_de(model: FeederModel) -> dict[str, str]:
    """Nodo fuente → alimentador o barra: las barras de SET y las cabeceras «Sin SET»."""
    info = model.combined
    if info is not None and info.barras_set:
        out = {b.node_id: b.set_codigo for b in info.barras_set}
        for f in info.feeders:
            if f.name in info.sin_set:
                out[f.source_node] = f.name
        return out
    if info is not None:
        return {f.source_node: f.name for f in info.feeders}
    return {model.source_node: model.name}


def _aristas(model: FeederModel):
    """(nombre, clase, a, b, largo, abierta) de tramos y acopladores. Un tramo con una
    maniobra abierta está abierto; con una cerrada, es «maniobra» (se abre ella)."""
    maniobras = defaultdict(list)
    for d in model.devices:
        if isinstance(d, SwitchingDevice) and d.section_id:
            maniobras[d.section_id].append(d)
    out = []
    for ln in model.lines:
        ds = maniobras.get(ln.section_id, [])
        abierta = any(int(d.on_off) == 0 for d in ds)
        out.append((ln.section_id, 'maniobra' if ds else 'tramo', ln.from_node, ln.to_node,
                    float(ln.length_m or 0.0), abierta))
    for c in model.couplers:
        out.append((c.name, 'acoplador', c.node_a, c.node_b, 0.0, int(c.on_off) == 0))
    return out


def _arbol(aristas, fuentes):
    vecinos = defaultdict(list)
    for i, (nombre, _cl, a, b, largo, abierta) in enumerate(aristas):
        if not abierta and a != b:
            vecinos[a].append((b, i))
            vecinos[b].append((a, i))
    for f in fuentes:
        vecinos[_RAIZ].append((f, -1))
    dist, padre, raiz_de = {}, {}, {}
    cola = [(0.0, '', _RAIZ, None, -1)]
    while cola:
        d, _n, u, de, i = heapq.heappop(cola)
        if u in dist:
            continue
        dist[u], padre[u] = d, (de, i)
        raiz_de[u] = u if de == _RAIZ else raiz_de.get(de)
        for v, j in sorted(vecinos.get(u, ()), key=lambda p: (aristas[p[1]][0] if p[1] >= 0 else '', p[0])):
            if v not in dist:
                largo = aristas[j][4] if j >= 0 else 0.0
                heapq.heappush(cola, (d + largo, aristas[j][0] if j >= 0 else v, v, u, j))
    en_arbol = {i for _de, i in padre.values() if i is not None and i >= 0}
    return dist, padre, raiz_de, en_arbol


def _camino(padre, nodo) -> list[int]:
    out = []
    while padre.get(nodo, (None, -1))[0] not in (None, _RAIZ):
        de, i = padre[nodo]
        out.append(i)
        nodo = de
    return out


def abrir_caminos_cerrados(model: FeederModel) -> list[Apertura]:
    """Abre lo necesario para que cada barra alimentada lo esté desde una sola fuente por
    un solo camino (022:RF-29 a RF-31). Modifica el modelo y devuelve las aperturas.

    Cada vuelta abre un elemento de un ciclo, que nunca deja barras sin alimentar; se
    recalcula hasta que no quede ninguno. Determinista: a igual distancia, el nombre.
    """
    fuentes = fuentes_de(model)
    info = model.combined
    alim_de_nodo = (info.feeder_of_node if info is not None else {})
    aperturas: list[Apertura] = []
    while True:
        aristas = _aristas(model)
        dist, padre, raiz_de, en_arbol = _arbol(aristas, sorted(fuentes))
        fuera = sorted((i for i, (_n, _c, a, b, _l, abierta) in enumerate(aristas)
                        if not abierta and a != b and a in dist and b in dist and i not in en_arbol),
                       key=lambda i: aristas[i][0])
        if not fuera:
            return aperturas
        k = fuera[0]
        _n, _c, a, b, _l, _ab = aristas[k]
        ca, cb = _camino(padre, a), _camino(padre, b)
        ciclo = (set(ca) ^ set(cb)) | {k}

        def lejania(i):
            x = aristas[i]
            return ((dist.get(x[2], 0.0) + dist.get(x[3], 0.0)) / 2, x[0])

        maniobras = [i for i in ciclo if aristas[i][1] in ('acoplador', 'maniobra')
                     and not (aristas[i][1] == 'acoplador' and aristas[i][0].startswith('CAB_'))]
        elegida = max(maniobras or [i for i in ciclo if aristas[i][1] == 'tramo'] or list(ciclo),
                      key=lejania)
        ra, rb = raiz_de.get(a), raiz_de.get(b)
        barras = {x.node_id for x in info.barras_set} if info is not None else set()
        # La barra de SET es de todos sus alimentadores: no dice de quién es el camino.
        alims = tuple(sorted({f for i in ciclo for n in aristas[i][2:4] if n not in barras
                              for f in alim_de_nodo.get(n, [])}))
        sets_ = tuple(sorted({fuentes[r] for r in (ra, rb) if r in barras}))
        if ra != rb and len(sets_) > 1:
            motivo = 'entre_set'
        elif len(alims) > 1:
            motivo = 'entre_alimentadores'
        else:
            motivo = 'anillo'
        nombre, clase = aristas[elegida][0], aristas[elegida][1]
        _abrir(model, nombre, clase, aristas[elegida], dist)
        aperturas.append(Apertura(nombre, clase, motivo, alims or (model.name,), sets_))


def _abrir(model: FeederModel, nombre: str, clase: str, arista, dist) -> None:
    if clase == 'acoplador':
        model.couplers[:] = [replace(c, on_off=0) if c.name == nombre else c for c in model.couplers]
        return
    if clase == 'maniobra':
        model.devices[:] = [replace(d, on_off=0) if isinstance(d, SwitchingDevice)
                            and d.section_id == nombre else d for d in model.devices]
        return
    # Un tramo sin maniobra: un punto abierto en su extremo más lejano de la fuente.
    _n, _c, a, b, _l, _ab = arista
    lejos, lado = (b, 1) if dist.get(b, 0.0) >= dist.get(a, 0.0) else (a, 0)
    linea = next(ln for ln in model.lines if ln.section_id == nombre)
    feeders = (model.combined.feeder_of_node.get(lejos, ['']) if model.combined else [model.name])
    model.devices.append(SwitchingDevice(
        kind='punto_abierto', section_id=nombre, location='', terminal_side=lado,
        node_id=lejos, eq_id=f'NA_{nombre}', eq_number=f'NA_{nombre}', phase=linea.phase,
        on_off=0, locked=0, eq_state=0, feeder=feeders[0] if feeders else ''))
