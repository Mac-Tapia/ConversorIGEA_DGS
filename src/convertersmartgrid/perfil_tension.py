"""Perfil de tensión de un alimentador y bancos ubicados según el perfil (spec 094).

El perfil es la tensión de cada barra de media frente a su distancia eléctrica a la cabecera: la suma del largo de los
tramos por el camino de la red, no la distancia en línea recta, porque dos barras cercanas por GPS pueden colgar de
ramales distintos. AL209 (2026-11-06): de 0,9998 p.u. en la cabecera a 0,9498 p.u. a 20,85 km; la búsqueda del oráculo
(087:RF-55) amontonaba los bancos en el extremo, en barras que eléctricamente son el mismo punto, y el usuario pidió
ubicarlos «de acuerdo al perfil de tensión».

Puro: no habla con DIgSILENT. El grafo es el de ``digital_twin_snapshot_pf.grafo`` y las tensiones, las del flujo.
"""
from __future__ import annotations

import heapq
from collections.abc import Callable, Mapping, Sequence
from typing import Any



def nombre(nodo: str) -> str:
    """El ``loc_name`` de una identidad ``Clase:ruta\\Nombre.Clase``, como ``digital_twin.evolutivo.nombre_corto``
    (la capa de aplicación no importa del gemelo, 002)."""
    return str(nodo).rsplit('\\', 1)[-1].rsplit(':', 1)[-1].rsplit('.', 1)[0]


#: Por debajo de esta tensión nominal una barra es de baja (la de cada SED): no entra en el perfil.
KV_MEDIA_MIN = 1.0
#: Las reglas de ubicación sobre el perfil (RF-4).
REGLAS = ('caida_igual', 'dos_n_mas_uno', 'por_tramo')
#: Un ramal es largo desde esta longitud (km) desde su derivación, si el perfil no da `escalera.ramal_largo_km` (RF-16).
RAMAL_LARGO_KM = 2.0
#: Tope de bancos que se prueban (RF-8): una salvaguarda, la parada la deciden el objetivo, la mejora y el valle.
MAX_BANCOS = 30


def arbol(grafo: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, str | None]]:
    """La distancia eléctrica (km) de cada nodo a la fuente más cercana y su nodo anterior por ese camino (RF-1, RF-17).

    El anterior sale del mismo Dijkstra y solo cambia cuando la distancia baja de verdad: con ramas de largo cero
    (acopladores, transformadores) dos nodos quedaban a la misma distancia, cada uno se tomaba por anterior del otro y
    la calibración de AL209 (2026-11-06) quedó en un bucle sin fin.
    """
    vecinos: dict[str, list[tuple[str, float]]] = {}
    for r in grafo.get('ramas') or []:
        if r.get('cerrada', True) is False:
            continue
        km = float(r.get('largo_km') or 0.0)
        vecinos.setdefault(r['desde'], []).append((r['hasta'], km))
        vecinos.setdefault(r['hasta'], []).append((r['desde'], km))
    dist = {n: 0.0 for n, d in (grafo.get('nodos') or {}).items() if d.get('fuente')}
    previo: dict[str, str | None] = {n: None for n in dist}
    cola = [(0.0, n) for n in dist]
    hechos: set[str] = set()
    while cola:
        d, n = heapq.heappop(cola)
        if n in hechos:
            continue
        hechos.add(n)
        for w, km in vecinos.get(n, ()):
            if w not in hechos and d + km < dist.get(w, float('inf')):
                dist[w], previo[w] = d + km, n
                heapq.heappush(cola, (d + km, w))
    return dist, previo


def distancias(grafo: Mapping[str, Any]) -> dict[str, float]:
    """La distancia eléctrica (km) de cada nodo a la fuente más cercana, por los tramos cerrados (RF-1)."""
    return arbol(grafo)[0]


def perfil(grafo: Mapping[str, Any], tensiones: Mapping[str, float],
           barras: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Barras de media (de ``barras`` si se dan) con su distancia a la cabecera y su tensión, de la más cercana a la
    más lejana (RF-1). ``tensiones`` va por nombre corto, como ``Oraculo.medir``."""
    dist = distancias(grafo)
    quiero = set(barras) if barras is not None else None
    out = []
    for n, d in (grafo.get('nodos') or {}).items():
        b = nombre(n)
        if d.get('fuente') or float(d.get('kv') or 0.0) < KV_MEDIA_MIN or n not in dist or b not in tensiones:
            continue
        if quiero is not None and b not in quiero:
            continue
        out.append({'barra': b, 'km': round(dist[n], 6), 'u': float(tensiones[b]), 'nodo': n})
    return sorted(out, key=lambda p: (p['km'], p['barra']))


def ejes(grafo: Mapping[str, Any], puntos: Sequence[Mapping[str, Any]], *,
         ramal_largo_km: float) -> list[list[dict[str, Any]]]:
    """La troncal del alimentador y la troncal de cada ramal largo, como listas de barras del perfil (RF-16).

    La troncal es el camino más largo desde la cabecera (016); un ramal es largo si desde su derivación mide al menos
    ``ramal_largo_km`` hasta su barra de media más lejana, y su troncal es ese camino, con la barra de derivación
    delante. Los ramales de un ramal largo se miran igual. Usuario, 2026-11-06: «el camino debe ser solo por la
    troncal y troncales de las ramas largas».
    """
    dist, previo = arbol(grafo)
    por_nodo = {p['nodo']: p for p in puntos}
    hijos: dict[str, list[str]] = {}
    for n, a in previo.items():
        if a is not None:
            hijos.setdefault(a, []).append(n)
    # Tramos desde la fuente: ordena de las hojas hacia la fuente y desempata la distancia cuando hay ramas sin largo.
    saltos: dict[str, int] = {}
    for n in dist:
        pila, x = [], n
        while x is not None and x not in saltos:
            pila.append(x)
            x = previo.get(x)
        base = saltos[x] if x is not None else -1
        for y in reversed(pila):
            base += 1
            saltos[y] = base

    def lejos(n: str) -> tuple[float, int]:
        return dist[n], saltos[n]

    # La barra de media más lejana de cada subárbol, de las hojas hacia la fuente.
    lejana: dict[str, str | None] = {n: (n if n in por_nodo else None) for n in dist}
    for n in sorted(dist, key=lambda x: saltos[x], reverse=True):
        a = previo.get(n)
        if a is not None and lejana[n] is not None and (lejana[a] is None or lejos(lejana[n]) > lejos(lejana[a])):
            lejana[a] = lejana[n]

    def camino(desde: str, hasta: str) -> list[str]:
        nodos, n = [], hasta
        while n is not None and n != desde and len(nodos) <= len(dist):
            nodos.append(n)
            n = previo.get(n)
        return [desde] + nodos[::-1]

    out: list[list[dict[str, Any]]] = []
    # Los nodos que ya son de un eje: desde la barra de derivación, la troncal parecía otro ramal y se volvía a ella.
    usados: set[str] = set()

    def agregar(desde: str, hasta: str) -> None:
        nodos = camino(desde, hasta)
        eje = [dict(por_nodo[n]) for n in nodos if n in por_nodo]
        if len(eje) >= 2:
            out.append(eje)
        usados.update(nodos)
        for v in nodos:
            for c in hijos.get(v, ()):
                fin = lejana.get(c)
                if c not in usados and fin is not None and dist[fin] - dist[v] >= ramal_largo_km:
                    agregar(v, fin)

    for fuente in [n for n, a in previo.items() if a is None]:
        fin = lejana.get(fuente)
        if fin is not None:
            agregar(fuente, fin)
    return out


def _elegir(camino, objetivos: Sequence[float], clave: Callable[[Mapping[str, Any]], float],
            separacion_km: float) -> list[str]:
    """Para cada valor objetivo, la barra del camino más cercana que respeta la separación con las ya elegidas."""
    elegidas: list[Mapping[str, Any]] = []
    for meta in objetivos:
        for p in sorted(camino, key=lambda p: (abs(clave(p) - meta), p['km'])):
            if all(abs(p['km'] - q['km']) >= separacion_km and p['barra'] != q['barra'] for q in elegidas):
                elegidas.append(p)
                break
    return [p['barra'] for p in elegidas]


def ubicaciones(camino: Sequence[Mapping[str, Any]], n: int, regla: str, *, separacion_km: float) -> list[str]:
    """Las ``n`` ubicaciones de banco que da ``regla`` sobre el camino del perfil (RF-4, RF-6).

    ``caida_igual``: donde la caída acumulada llega a i/n de la caída total. ``dos_n_mas_uno``: a 2i/(2n+1) de la
    distancia, la de la carga repartida. ``por_tramo``: el camino en n tramos iguales y en cada uno a sus 2/3.
    """
    if not camino or n < 1:
        return []
    inicio, u0 = camino[0]['km'], camino[0]['u']
    largo = camino[-1]['km'] - inicio
    caida = u0 - min(p['u'] for p in camino)
    if regla == 'caida_igual':
        return _elegir(camino, [caida * i / n for i in range(1, n + 1)], lambda p: u0 - p['u'], separacion_km)
    if regla == 'dos_n_mas_uno':
        return _elegir(camino, [inicio + largo * 2 * i / (2 * n + 1) for i in range(1, n + 1)], lambda p: p['km'],
                       separacion_km)
    if regla == 'por_tramo':
        return _elegir(camino, [inicio + largo * (i + 2 / 3) / n for i in range(n)], lambda p: p['km'],
                       separacion_km)
    raise ValueError(f'regla de ubicación desconocida: {regla}')


def bancos_hasta_objetivo(ejes_: Sequence[Sequence[Mapping[str, Any]]], medir: Callable[[list[str]], tuple[float, float]],
                          *, objetivo: float, mejora_minima: float, valle: Callable[[list[str]], tuple[bool, float]],
                          separacion_km: float = 0.0, max_bancos: int = MAX_BANCOS) -> dict[str, Any]:
    """Bancos de un módulo, uno más cada vez, ubicados por el perfil en la troncal y los ramales largos (RF-8, RF-9,
    RF-16).

    ``medir(barras)`` da (tensión mínima de media de todo el alimentador, pérdidas kW) con un banco en cada barra;
    ``valle(barras)``, si el valle queda en límites y su tensión máxima. En cada paso se prueba un banco más en cada eje,
    con cada regla, dejando los de los demás ejes donde están, y queda el de mayor tensión mínima y, a igualdad, menores
    pérdidas. Se para al llegar al objetivo, si un banco más sube menos de ``mejora_minima`` o si el valle se pasa;
    dice por qué y qué alcanzó.
    """
    v0, perd0 = medir([])
    mejor = {'barras': [], 'regla': None, 'v_min': v0, 'perdidas_kw': perd0, 'valle_max': valle([])[1],
             'motivo': 'objetivo' if v0 >= objetivo else 'sin_ubicacion', 'v_min_sin_bancos': v0, 'objetivo': objetivo,
             'pasos': [], 'por_eje': []}
    if v0 >= objetivo or not ejes_:
        return mejor
    actuales: list[list[str]] = [[] for _ in ejes_]
    for n in range(1, max_bancos + 1):
        opciones = []
        for i, eje in enumerate(ejes_):
            for regla in REGLAS:
                nuevas = ubicaciones(eje, len(actuales[i]) + 1, regla, separacion_km=separacion_km)
                if len(nuevas) != len(actuales[i]) + 1:
                    continue
                prueba = [list(g) for g in actuales]
                prueba[i] = nuevas
                barras = list(dict.fromkeys(b for grupo in prueba for b in grupo))
                if len(barras) != n:
                    continue
                v, perd = medir(barras)
                opciones.append((round(v, 5), -perd, regla, i, prueba, barras))
        if not opciones:
            mejor['motivo'] = 'sin_ubicacion' if not mejor['barras'] else 'separacion'
            return mejor
        v, menos_perd, regla, i, prueba, barras = max(opciones, key=lambda o: (o[0], o[1]))
        mejor['pasos'].append({'bancos': n, 'regla': regla, 'eje': i, 'barras': barras, 'v_min': v,
                               'perdidas_kw': -menos_perd})
        if v - mejor['v_min'] < mejora_minima:
            mejor['motivo'] = 'sin_mejora'
            return mejor
        ok, vmax = valle(barras)
        if not ok:
            mejor['motivo'] = 'valle'
            return mejor
        actuales = prueba
        mejor.update(barras=barras, regla=regla, v_min=v, perdidas_kw=-menos_perd, valle_max=vmax,
                     por_eje=[list(g) for g in actuales])
        if v >= objetivo:
            mejor['motivo'] = 'objetivo'
            return mejor
    mejor['motivo'] = 'tope'
    return mejor
