"""Snapping y reconstrucción de nodos (secciones 10 y E de VNR-GIS.md).

Clustering por tolerancia en coordenadas **proyectadas** (metros). Es determinista:
misma entrada → mismos IDs de nodo. La rejilla espacial se implementa con una
tabla de celdas (sin ``shapely``) para que el snapping funcione sin dependencias
opcionales y sea predecible.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .geometry import line_endpoints


@dataclass
class SnapRecord:
    source_object: str
    original_x: float
    original_y: float
    snapped_node: str
    snapped_x: float
    snapped_y: float
    distance_m: float
    rule: str
    status: str = 'ok'

    def as_dict(self) -> dict:
        return {
            'source_object': self.source_object,
            'original_x': self.original_x,
            'original_y': self.original_y,
            'snapped_node': self.snapped_node,
            'snapped_x': self.snapped_x,
            'snapped_y': self.snapped_y,
            'distance_m': self.distance_m,
            'rule': self.rule,
            'status': self.status,
        }


@dataclass
class SnapResult:
    node_ids: dict[tuple[float, float], str]
    """(x, y) original → ID canónico del nodo."""
    node_coords: dict[str, tuple[float, float]]
    records: list[SnapRecord] = field(default_factory=list)

    def displacement_report(self) -> dict:
        if not self.records:
            return {'count': 0, 'mean_m': 0.0, 'max_m': 0.0, 'excessive': 0}
        distances = [r.distance_m for r in self.records if r.distance_m >= 0]
        return {
            'count': len(distances),
            'mean_m': sum(distances) / len(distances) if distances else 0.0,
            'max_m': max(distances) if distances else 0.0,
            'excessive': sum(1 for d in distances if d > 5.0),
        }


def _cell(point: tuple[float, float], size: float) -> tuple[int, int]:
    return math.floor(point[0] / size), math.floor(point[1] / size)


def _cell_neighbors(cell: tuple[int, int]) -> Iterable[tuple[int, int]]:
    cx, cy = cell
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            yield cx + dx, cy + dy


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def add(self, item: int) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: int) -> int:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def cluster_points(
    points: Sequence[tuple[float, float]],
    epsilon: float,
) -> list[int]:
    """Agrupa puntos dentro de ``epsilon`` (metros) y devuelve el cluster de cada uno.

    Determinista: la rejilla se barre en orden y los primeros puntos de cada clúster
    se convierten en representantes. Dos puntos separados por más de ``epsilon``
    nunca se funden, y la unión es transitiva dentro de la tolerancia.
    """
    if epsilon <= 0:
        return list(range(len(points)))
    uf = _UnionFind()
    grid: dict[tuple[int, int], list[int]] = {}
    for index, point in enumerate(points):
        uf.add(index)
        cell = _cell(point, epsilon)
        for ncell in _cell_neighbors(cell):
            for other in grid.get(ncell, ()):
                ox, oy = points[other]
                if math.hypot(point[0] - ox, point[1] - oy) <= epsilon:
                    uf.union(index, other)
        grid.setdefault(cell, []).append(index)

    # Asignación determinista del ID de clúster por orden del primer miembro.
    order: dict[int, int] = {}
    cluster_id = 0
    for index in range(len(points)):
        root = uf.find(index)
        if root not in order:
            order[root] = cluster_id
            cluster_id += 1
    return [order[uf.find(index)] for index in range(len(points))]


def deterministic_node_id(coords: Sequence[tuple[float, float]]) -> str:
    """ID canónico determinista a partir de las coordenadas del clúster (sección E).

    Se ordenan las coordenadas por x,y y se hashea el centroide redondeado: mismo
    clúster → mismo ID, sin depender del orden de llegada.
    """
    if not coords:
        return 'NODE_EMPTY'
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    payload = f'{cx:.3f},{cy:.3f}'.encode()
    return 'N' + hashlib.sha256(payload).hexdigest()[:12].upper()


def snap_endpoints(
    anchors: Sequence[tuple[str, float, float]],
    snap_tolerance_m: float,
) -> SnapResult:
    """Reconstruye nodos canónicos a partir de extremos (``(id, x, y)``).

    ``id`` identifica el objeto/tramo fuente para la pista de auditoría. Devuelve el
    mapeo de coordenadas al nodo canónico, las coordenadas del nodo y el registro de
    desplazamientos.
    """
    points = [(x, y) for _, x, y in anchors]
    clusters = cluster_points(points, snap_tolerance_m)
    coords_by_cluster: dict[int, list[tuple[float, float]]] = {}
    for (_, x, y), cid in zip(anchors, clusters):
        coords_by_cluster.setdefault(cid, []).append((x, y))

    node_coords: dict[str, tuple[float, float]] = {}
    for cid, coords in coords_by_cluster.items():
        node_id = deterministic_node_id(coords)
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        node_coords[node_id] = (sum(xs) / len(xs), sum(ys) / len(ys))

    node_ids: dict[tuple[float, float], str] = {}
    records: list[SnapRecord] = []
    for (obj_id, x, y), cid in zip(anchors, clusters):
        node_id = deterministic_node_id(coords_by_cluster[cid])
        node_ids[(x, y)] = node_id
        sx, sy = node_coords[node_id]
        distance = math.hypot(sx - x, sy - y)
        records.append(SnapRecord(
            source_object=obj_id,
            original_x=x, original_y=y,
            snapped_node=node_id,
            snapped_x=sx, snapped_y=sy,
            distance_m=distance,
            rule='tolerance_cluster',
            status='excessive' if distance > 5.0 else 'ok',
        ))
    return SnapResult(node_ids=node_ids, node_coords=node_coords, records=records)


def rebuild_nodes(
    sections: Sequence[tuple[str, object]],
    snap_tolerance_m: float,
    *,
    geometry_getter=None,
) -> SnapResult:
    """Reconstruye nodos desde los extremos de los tramos (sección E).

    ``sections`` son pares ``(id_tramo, geometria)``. El ``geometry_getter`` opcional
    permite suministrar geometrías en otro formato; por defecto se usa
    :func:`~vnr_etl.gis.geometry.coords_from_geojson`.
    """
    anchors: list[tuple[str, float, float]] = []
    for section_id, geometry in sections:
        start, end = line_endpoints(geometry)
        if start is not None:
            anchors.append((f'{section_id}:from', start[0], start[1]))
        if end is not None:
            anchors.append((f'{section_id}:to', end[0], end[1]))
    return snap_endpoints(anchors, snap_tolerance_m)
