"""Geometría auxiliar (sin dependencia de ``shapely`` para el modelo).

Las geometrías se representan como GeoJSON (dict con ``type``/``coordinates``) o
como listas planas de puntos ``(x, y)``. Las funciones aquí solo operan sobre
coordenadas; ``snapping.py`` es quien materializa objetos geométricos cuando
``shapely`` está disponible.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise


def coords_from_geojson(geometry) -> list[tuple[float, float]]:
    """Extrae una lista plana de puntos de una geometría GeoJSON.

    Soporta ``Point``, ``LineString`` y ``MultiLineString`` (los vértices de varios
    tramos se concatenan en orden de aparición). Las demás devuelven lista vacía.
    """
    if not isinstance(geometry, dict):
        return []
    gtype = geometry.get('type')
    coords = geometry.get('coordinates')
    if gtype == 'Point':
        return [(float(coords[0]), float(coords[1]))]
    if gtype == 'LineString':
        return [(float(x), float(y)) for x, y in coords]
    if gtype == 'MultiLineString':
        out: list[tuple[float, float]] = []
        for line in coords:
            out.extend((float(x), float(y)) for x, y in line)
        return out
    return []


def line_endpoints(geometry) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    """Devuelve ``(inicio, final)`` de una geometría de tipo línea."""
    if geometry is None:
        return None, None
    if hasattr(geometry, 'coords'):
        # objeto shapely (si está disponible)
        pts = list(geometry.coords)
        if not pts:
            return None, None
        return tuple(pts[0]), tuple(pts[-1])
    pts = coords_from_geojson(geometry)
    if not pts:
        return None, None
    return pts[0], pts[-1]


def polyline_length_m(points: Sequence[tuple[float, float]]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in pairwise(points):
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def length_pct_delta(gis_m: float, source_m: float, epsilon: float = 1e-9) -> float | None:
    """Delta porcentual entre longitud GIS y fuente (sección G)."""
    if source_m is None or source_m <= epsilon:
        return None
    return 100.0 * abs(gis_m - source_m) / source_m
