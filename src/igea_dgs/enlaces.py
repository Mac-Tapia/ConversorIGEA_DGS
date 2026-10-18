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


#: Distancia máxima entre la red de un alimentador y la de otro para reconstruir el tramo
#: que falta (022:RF-57): TM106 quedaba a 78 m de TM104 y TM101 a 15 m de TM105.
DISTANCIA_MAX_M = 100.0
#: Prefijo del tramo que añade la reconstrucción: no viene de la entrada (completitud).
PREFIJO_RECONSTRUIDO = 'REC_'


@dataclass(frozen=True)
class Reconstruccion:
    """Un alimentador unido por medida a la red de otro (022:RF-57 a RF-60)."""

    alimentador: str
    donante: str
    nodo: str               # el del alimentador reconstruido
    nodo_donante: str
    distancia_m: float
    tramo: str              # el tramo nuevo
    abierto: str            # lo que se abrió: un elemento del donante o el tramo nuevo
    medida_kw: float
    medida_donante_kw: float
    kva_pasado: float
    kva_donante: float
    cargas_pasadas: int

    def texto(self) -> str:
        if not self.cargas_pasadas:
            return (f'{self.alimentador} reconstruido: tramo {self.tramo} de '
                    f'{self.distancia_m:.0f} m hasta {self.donante}, abierto; activado sin carga '
                    'pasada (022:RF-57, RF-59).')
        return (f'{self.alimentador} reconstruido: tramo {self.tramo} de {self.distancia_m:.0f} m '
                f'hasta la red de {self.donante}; abierto {self.abierto} y pasadas '
                f'{self.cargas_pasadas} cargas ({self.kva_pasado:,.0f} de '
                f'{self.kva_donante:,.0f} kVA), por sus medidas {self.medida_kw:,.0f} y '
                f'{self.medida_donante_kw:,.0f} kW (022:RF-57, RF-58).')


def _mas_cercano(model: FeederModel, receptor: str, distancia_max_m: float):
    """(distancia, nodo propio, nodo de otro) más cercanos de la misma tensión, o None."""
    import math

    info = model.combined
    barras = {b.node_id for b in info.barras_set} | {f.source_node for f in info.feeders}
    # Solo los extremos de su red (un tramo): lo que falta está al final. Ni la barra de SET
    # ni las cabeceras, juntas en la SET; en Chincha (2026-10-18) un nodo de TM106 junto a la
    # SET quedaba a 7 m de TM104 y pasaba 2 000 de los 9 000 kVA que tocaban; su final está a 78 m.
    grado: dict[str, int] = defaultdict(int)
    for ln in model.lines:
        grado[ln.from_node] += 1
        grado[ln.to_node] += 1
    propios = sorted(n for n, fs in info.feeder_of_node.items() if receptor in fs
                     and n not in barras and grado[n] == 1)
    kv = next((info.node_kv.get(n) for n in propios if n in info.node_kv), None)

    def xy(nodo):
        p = model.nodes.get(nodo)
        if p is None or p.x is None or p.y is None or p.coord_inferida:
            return None
        return p.x, p.y

    otros = [(m, xy(m)) for m, fs in sorted(info.feeder_of_node.items())
             if receptor not in fs and m not in barras and info.node_kv.get(m) == kv]
    otros = [(m, p) for m, p in otros if p is not None]
    mejor = None
    for n in propios:
        a = xy(n)
        if a is None:
            continue
        for m, b in otros:
            clave = (math.hypot(a[0] - b[0], a[1] - b[1]), n, m)
            if clave[0] <= distancia_max_m and (mejor is None or clave < mejor):
                mejor = clave
    return mejor, propios, kv


def reconstruir_por_medida(model: FeederModel, pedidos: dict[str, float],
                           medidas_kw: dict[str, float], *,
                           distancia_max_m: float = DISTANCIA_MAX_M
                           ) -> tuple[list[Reconstruccion], list[str]]:
    """Une cada alimentador de ``pedidos`` (alimentador → su medida en kW) a la red de otro
    por el tramo que falta y le pasa la parte que le toca (022:RF-57 a RF-60).

    ``medidas_kw`` son las de los demás, para repartir con el donante. Va antes de
    :func:`abrir_caminos_cerrados`: el tramo nuevo y el punto abierto dejan la red radial.
    Devuelve las reconstrucciones y los avisos. Determinista: a igual distancia, el nombre.
    """
    info = model.combined
    if info is None:
        return [], ['La reconstrucción por medida necesita la red unida (022:RF-57).']
    hechas: list[Reconstruccion] = []
    avisos: list[str] = []
    for receptor in sorted(pedidos):
        medida = max(0.0, float(pedidos[receptor] or 0.0))
        mejor, propios, kv = _mas_cercano(model, receptor, distancia_max_m)
        if mejor is None:
            avisos.append(f'{receptor}: ningún nodo de otro alimentador de su tensión a menos de '
                          f'{distancia_max_m:g} m; se convierte como está (022:RF-60).'
                          if kv else f'{receptor}: no está en la red unida (022:RF-60).')
            continue
        d, n, m = mejor
        donante = sorted(f for f in info.feeder_of_node[m] if f != receptor)[0]
        # El árbol antes del tramo nuevo: el camino de la cabecera del donante al nodo de unión.
        aristas = _aristas(model)
        dist, padre, _raiz, _en = _arbol(aristas, sorted(fuentes_de(model)))
        hijos = defaultdict(list)
        for v, (u, _i) in padre.items():
            if u not in (None, _RAIZ):
                hijos[u].append(v)

        def aguas_abajo(v):
            out, pila = set(), [v]
            while pila:
                x = pila.pop()
                if x not in out:
                    out.add(x)
                    pila.extend(hijos.get(x, ()))
            return out

        kva_de = defaultdict(float)
        for s in model.seds:
            kva_de[s.node_id] += float(s.design_kva or 0.0)
        if not model.seds:
            for ld in model.loads:
                kva_de[ld.node_id] += float(ld.connected_kva or 0.0)
        kva_donante = sum(kva_de[x] for x, fs in info.feeder_of_node.items() if donante in fs)
        medida_donante = max(0.0, float(medidas_kw.get(donante) or 0.0))
        objetivo = (kva_donante * medida / (medida + medida_donante)
                    if medida > 0 and medida + medida_donante > 0 else 0.0)
        tramo_nuevo = f'{PREFIJO_RECONSTRUIDO}{receptor}_{m}'[:40]
        # Del mismo tipo que el tramo que llega al nodo propio: es el que se cortó en la base.
        plantilla = next(ln for ln in model.lines if n in (ln.from_node, ln.to_node))
        linea = replace(plantilla, section_id=tramo_nuevo, from_node=n, to_node=m,
                        length_m=round(d, 3), txt_length_m=None, length_source='georef')
        model.lines.append(linea)
        model.section_by_id[tramo_nuevo] = linea
        candidatos = []
        if objetivo > 0:
            for i in _camino(padre, m):
                nombre, clase, a, b, _l, _ab = aristas[i]
                if clase == 'acoplador' and nombre.startswith('CAB_'):
                    continue
                hijo = a if padre.get(a, (None,))[0] == b else b
                abajo = aguas_abajo(hijo)
                kva = sum(kva_de[x] for x in abajo)
                candidatos.append((abs(kva - objetivo), nombre, i, abajo, kva))
        if not candidatos:
            # RF-59: sin medida que pasar, el tramo nuevo queda abierto del lado del donante.
            model.devices.append(SwitchingDevice(
                kind='punto_abierto', section_id=tramo_nuevo, location='', terminal_side=1,
                node_id=m, eq_id=f'NA_{tramo_nuevo}', eq_number=f'NA_{tramo_nuevo}',
                phase=linea.phase, on_off=0, locked=0, eq_state=0, feeder=receptor))
            hechas.append(Reconstruccion(receptor, donante, n, m, d, tramo_nuevo, tramo_nuevo,
                                         medida, medida_donante, 0.0, kva_donante, 0))
            continue
        _err, nombre, i, abajo, kva = min(candidatos, key=lambda c: c[:2])
        _abrir(model, nombre, aristas[i][1], aristas[i], dist)
        red = next((f.network_id for f in info.feeders if f.name == receptor), '')
        for x in abajo:
            info.feeder_of_node[x] = [receptor if f == donante else f
                                      for f in info.feeder_of_node.get(x, [])] or [receptor]
        pasadas = 0
        for k, ld in enumerate(model.loads):
            if ld.node_id in abajo and ld.feeder == donante:
                model.loads[k] = replace(ld, feeder=receptor, network_id=red or ld.network_id)
                pasadas += 1
        for k, s in enumerate(model.seds):
            if s.node_id in abajo and s.feeder == donante:
                model.seds[k] = replace(s, feeder=receptor, network_id=red or s.network_id)
        hechas.append(Reconstruccion(receptor, donante, n, m, d, tramo_nuevo, nombre, medida,
                                     medida_donante, kva, kva_donante, pasadas))
    return hechas, avisos
