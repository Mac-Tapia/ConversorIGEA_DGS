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
#: Tope de bancos que se prueban (RF-8): una salvaguarda, la parada la deciden el objetivo, la mejora y el valle.
MAX_BANCOS = 30


def distancias(grafo: Mapping[str, Any]) -> dict[str, float]:
    """La distancia eléctrica (km) de cada nodo a la fuente más cercana, por los tramos cerrados (RF-1)."""
    vecinos: dict[str, list[tuple[str, float]]] = {}
    for r in grafo.get('ramas') or []:
        if r.get('cerrada', True) is False:
            continue
        km = float(r.get('largo_km') or 0.0)
        vecinos.setdefault(r['desde'], []).append((r['hasta'], km))
        vecinos.setdefault(r['hasta'], []).append((r['desde'], km))
    dist = {n: 0.0 for n, d in (grafo.get('nodos') or {}).items() if d.get('fuente')}
    cola = [(0.0, n) for n in dist]
    while cola:
        d, n = heapq.heappop(cola)
        if d > dist.get(n, float('inf')):
            continue
        for w, km in vecinos.get(n, ()):
            if d + km < dist.get(w, float('inf')):
                dist[w] = d + km
                heapq.heappush(cola, (d + km, w))
    return dist


def _previos(grafo: Mapping[str, Any]) -> dict[str, str | None]:
    """El nodo anterior de cada uno por el camino más corto desde la fuente."""
    dist = distancias(grafo)
    previo: dict[str, str | None] = {n: None for n, d in (grafo.get('nodos') or {}).items() if d.get('fuente')}
    for r in grafo.get('ramas') or []:
        if r.get('cerrada', True) is False:
            continue
        km = float(r.get('largo_km') or 0.0)
        for a, b in ((r['desde'], r['hasta']), (r['hasta'], r['desde'])):
            if a in dist and b in dist and b not in previo and abs(dist[a] + km - dist[b]) < 1e-9:
                previo[b] = a
    return previo


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


def camino_al_minimo(grafo: Mapping[str, Any], puntos: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Las barras del perfil por el camino de la cabecera a la de menor tensión, en orden de distancia (RF-4)."""
    if not puntos:
        return []
    peor = min(puntos, key=lambda p: (p['u'], -p['km']))
    previo = _previos(grafo)
    en_camino, n = set(), peor['nodo']
    while n is not None:
        en_camino.add(n)
        n = previo.get(n)
    return [dict(p) for p in puntos if p['nodo'] in en_camino]


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
    largo, u0 = camino[-1]['km'], camino[0]['u']
    caida = u0 - min(p['u'] for p in camino)
    if regla == 'caida_igual':
        return _elegir(camino, [caida * i / n for i in range(1, n + 1)], lambda p: u0 - p['u'], separacion_km)
    if regla == 'dos_n_mas_uno':
        return _elegir(camino, [largo * 2 * i / (2 * n + 1) for i in range(1, n + 1)], lambda p: p['km'], separacion_km)
    if regla == 'por_tramo':
        return _elegir(camino, [largo * (i + 2 / 3) / n for i in range(n)], lambda p: p['km'], separacion_km)
    raise ValueError(f'regla de ubicación desconocida: {regla}')


def bancos_hasta_objetivo(camino: Sequence[Mapping[str, Any]], medir: Callable[[list[str]], tuple[float, float]], *,
                          objetivo: float, mejora_minima: float, valle: Callable[[list[str]], tuple[bool, float]],
                          separacion_km: float = 0.0, max_bancos: int = MAX_BANCOS) -> dict[str, Any]:
    """Bancos de un módulo, uno más cada vez y ubicados por el perfil, hasta el objetivo (RF-8, RF-9).

    ``medir(barras)`` da (tensión mínima de media, pérdidas kW) con un banco en cada barra; ``valle(barras)``, si el
    valle queda en límites y su tensión máxima. Para cada número de bancos se queda con la regla de mayor tensión
    mínima y, a igualdad, menores pérdidas. Se para al llegar al objetivo, si un banco más sube menos de
    ``mejora_minima`` o si el valle se pasa; dice por qué y qué alcanzó.
    """
    v0, perd0 = medir([])
    mejor = {'barras': [], 'regla': None, 'v_min': v0, 'perdidas_kw': perd0, 'valle_max': valle([])[1],
             'motivo': 'objetivo' if v0 >= objetivo else 'sin_ubicacion', 'v_min_sin_bancos': v0, 'objetivo': objetivo,
             'pasos': []}
    if v0 >= objetivo:
        return mejor
    for n in range(1, max_bancos + 1):
        opciones = []
        for regla in REGLAS:
            barras = ubicaciones(camino, n, regla, separacion_km=separacion_km)
            if len(barras) == n:
                v, perd = medir(barras)
                opciones.append((round(v, 5), -perd, regla, barras))
        if not opciones:
            mejor['motivo'] = 'sin_ubicacion' if not mejor['barras'] else 'separacion'
            return mejor
        v, menos_perd, regla, barras = max(opciones, key=lambda o: (o[0], o[1]))
        mejor['pasos'].append({'bancos': n, 'regla': regla, 'barras': barras, 'v_min': v, 'perdidas_kw': -menos_perd})
        if v - mejor['v_min'] < mejora_minima:
            mejor['motivo'] = 'sin_mejora'
            return mejor
        ok, vmax = valle(barras)
        if not ok:
            mejor['motivo'] = 'valle'
            return mejor
        mejor.update(barras=barras, regla=regla, v_min=v, perdidas_kw=-menos_perd, valle_max=vmax)
        if v >= objetivo:
            mejor['motivo'] = 'objetivo'
            return mejor
    mejor['motivo'] = 'tope'
    return mejor
