from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
import math

from .model import FeederModel, Line, Sed, decode_phase, split_by_phase
from .schema import DgsSchema, load_schema
from .geography import GeographyManifest, GeoPoint


@dataclass(frozen=True)
class DiagramSheet:
    """Bounding box of the DigSilent IntGrf sheet (diagram units)."""

    scale: float
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    formato: str = ''
    """Formato normalizado (``A0``…) cuando la red se encaja en una hoja; '' si no."""
    orientacion: str = ''

    @property
    def width(self) -> float:
        return self.xmax - self.xmin

    @property
    def height(self) -> float:
        return self.ymax - self.ymin

    @property
    def span(self) -> float:
        return max(self.width, self.height)


@dataclass(frozen=True)
class DgsManifest:
    network_fid: str
    type_fids: dict[str, str]
    node_fids: dict[str, str]
    line_fids: dict[str, str]
    load_fids: dict[tuple[str, str], str]
    source_fid: str
    source_cubic_fid: str
    line_cubic_fids: dict[tuple[str, int], str]
    switch_fids: dict[tuple[str, str, str], str]
    diagram_fid: str = ''
    graphic_fids: dict[str, str] = field(default_factory=dict)
    sed_fids: dict[tuple[str, str], str] = field(default_factory=dict)
    visible_pointterm_nodes: tuple[str, ...] = ()
    diagram_sheet: DiagramSheet | None = None
    diagram_grid_mm: float = 0.0
    """Paso de cuadrícula elegido para la hoja (0 en la escala NA205)."""


class FidRegistry:
    def __init__(self, start: int = 1):
        self._next = start

    def new(self) -> str:
        value = str(self._next)
        self._next += 1
        return value


def _fmt(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float):
        if not math.isfinite(value):
            return ''
        return format(value, '.12g')
    return str(value).replace(';', ',').replace('\r', ' ').replace('\n', ' ').strip()


def _loc_name(value: str) -> str:
    return _fmt(value)[:40]


def _material(code: str) -> str:
    upper = code.upper()
    if upper.startswith('AA'):
        return 'Al'
    if upper.startswith(('CU', 'N', 'EC')):
        return 'Cu'
    return ''


def _type_name(key: str, code: str, kv: float | None = None) -> str:
    """Nombre del TypLne. En una red unida lleva la tensión, y no es cosmético.

    ``TypLne`` guarda la tensión nominal en ``uline``, así que el mismo conductor a
    10 kV y a 22,9 kV son dos tipos distintos en PowerFactory. Sin el sufijo, los dos
    saldrían con el mismo ``loc_name`` y quedarían indistinguibles en el proyecto.
    """
    base = code if code != 'DEFAULT' else (
        'DEFAULT_OH' if key.startswith('LINE:') else 'DEFAULT_UG')
    if kv is None:
        return base
    return f'{base}_{kv:g}kV'.replace('.', '_')


def _make_row(schema: DgsSchema, table: str, **values) -> str:
    fields = schema.fields(table)
    return '  ' + ';'.join(_fmt(values.get(field, '')) for field in fields)


def _node_degrees(model: FeederModel) -> dict[str, int]:
    degrees: dict[str, int] = defaultdict(int)
    for line in model.lines:
        degrees[line.from_node] += 1
        degrees[line.to_node] += 1
    return dict(degrees)


# node_id → [(neighbor_id, Line), ...]. Built once per model and threaded through
# the diagram helpers below. Rebuilding it per lookup turns every diagram pass
# into O(lines²) — see tests/test_performance_budget.py.
LineNeighborIndex = dict[str, list[tuple[str, Line]]]


def _line_neighbors(model: FeederModel) -> LineNeighborIndex:
    """Build the node adjacency index.

    Callers must build this **once** per model and pass it down via the
    ``neighbors`` keyword. Never call this inside a loop over lines.
    """
    neighbors: LineNeighborIndex = defaultdict(list)
    for line in model.lines:
        neighbors[line.from_node].append((line.to_node, line))
        neighbors[line.to_node].append((line.from_node, line))
    return neighbors


def _umbral_tramo_oculto(model: FeederModel, max_stub_m: float | None) -> float:
    """Longitud hasta la que un tramo punta no se dibuja; la decide el modelo.

    Vale 1 m por defecto (``FeederModel.diagram_max_stub_m``). Un modelo que debe
    dibujar todos sus tramos —sin omitir ningún elemento— lo pone a 0. Vive en el
    modelo para que el escritor y el validador no puedan discrepar.
    """
    if max_stub_m is not None:
        return max_stub_m
    return float(getattr(model, 'diagram_max_stub_m', 1.0))


def diagram_anchor_node(
    model: FeederModel,
    node_id: str,
    *,
    max_stub_m: float | None = None,
    neighbors: LineNeighborIndex | None = None,
) -> str:
    """Snap micro service-stub tips to the upstream network bus for graphics.

    CYMDIST often models a ~0.3 m section from a primary SED node to a tip
    terminal where the load hangs. Electrically the load stays on the tip;
    graphically anchoring at the primary keeps SED/load symbols on the feeder.

    Pass ``neighbors`` when calling repeatedly; omitting it rebuilds the whole
    adjacency index for a single lookup.
    """
    max_stub_m = _umbral_tramo_oculto(model, max_stub_m)
    index = _line_neighbors(model) if neighbors is None else neighbors
    adjacent = index.get(node_id, ())
    if len(adjacent) != 1:
        return node_id
    other_id, line = adjacent[0]
    if line.length_m <= max_stub_m:
        return other_id
    return node_id


def is_micro_service_stub_line(
    model: FeederModel,
    line: Line,
    *,
    max_stub_m: float | None = None,
    neighbors: LineNeighborIndex | None = None,
) -> bool:
    """True for ≤1 m tip sections that only hang a load/SED off the primary bus.

    These stay in ElmLne/StaCubic (electrical) but must not get IntGrf d_lin:
    at NA205 scale (~2 u/m) they render as dust and look like loose fragments.
    NA205 itself almost never draws such micro stubs (median span ~50 m).
    """
    max_stub_m = _umbral_tramo_oculto(model, max_stub_m)
    if line.length_m > max_stub_m:
        return False
    index = _line_neighbors(model) if neighbors is None else neighbors
    if diagram_anchor_node(model, line.from_node, max_stub_m=max_stub_m, neighbors=index) == line.to_node:
        return True
    if diagram_anchor_node(model, line.to_node, max_stub_m=max_stub_m, neighbors=index) == line.from_node:
        return True
    return False


def diagram_line_sections(
    model: FeederModel,
    *,
    max_stub_m: float | None = None,
    neighbors: LineNeighborIndex | None = None,
) -> set[str]:
    """SectionIDs that receive IntGrf d_lin (excludes micro service stubs)."""
    index = _line_neighbors(model) if neighbors is None else neighbors
    return {
        line.section_id
        for line in model.lines
        if not is_micro_service_stub_line(model, line, max_stub_m=max_stub_m, neighbors=index)
    }


def diagram_line_rail_counts(
    model: FeederModel,
    *,
    max_stub_m: float | None = None,
    neighbors: LineNeighborIndex | None = None,
    drawn: set[str] | None = None,
) -> tuple[int, int, int]:
    """Return ``(overhead_drawn, underground_drawn, d_lin_graphics)``.

    One IntGrf ``d_lin`` per drawn ElmLne (NA205 pattern). Underground look in
    DigSilent comes from ``ElmLne.inAir=0``, not duplicate graphics.
    """
    if drawn is None:
        drawn = diagram_line_sections(model, max_stub_m=max_stub_m, neighbors=neighbors)
    oh = ug = 0
    for line in model.lines:
        if line.section_id not in drawn:
            continue
        if line.overhead:
            oh += 1
        else:
            ug += 1
    return oh, ug, oh + ug


def parallel_circuit_graphic_offsets(
    model: FeederModel,
    *,
    offset_du: float = 4.0,
) -> dict[str, float]:
    """Signed diagram offset for true parallel circuits (same From↔To).

    CYMDIST encodes doble circuito as two SECTION rows sharing endpoints.
    Both ElmLne are kept electrically; graphics are offset so DigSilent shows
    two distinct ternaries instead of overlapping ghosts.
    """
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for line in model.lines:
        key = tuple(sorted((line.from_node, line.to_node)))
        groups[key].append(line.section_id)
    offsets: dict[str, float] = {}
    for sids in groups.values():
        if len(sids) < 2:
            continue
        ordered = sorted(sids)
        n = len(ordered)
        for i, sid in enumerate(ordered):
            offsets[sid] = (i - (n - 1) / 2.0) * offset_du
    return offsets


def visible_pointterm_nodes(
    model: FeederModel,
    *,
    neighbors: LineNeighborIndex | None = None,
    drawn: set[str] | None = None,
) -> set[str]:
    """Black PointTerm symbols so drawn lines are not floating fragments.

    Rules (aligned with NA205 density — most line ends sit on a PointTerm):
    - every endpoint of a *drawn* ElmLne (``diagram_line_sections``)
    - feeder head / source node
    - graphic anchors of loads/SEDs (upstream bus when tip is a ≤1 m stub)
    Hidden (still in ElmTerm electrical model):
    - micro service-stub tips (≤1 m) whose ``d_lin`` is omitted — never added,
      because anchors resolve to the primary bus
    """
    index = _line_neighbors(model) if neighbors is None else neighbors
    if drawn is None:
        drawn = diagram_line_sections(model, neighbors=index)
    visible: set[str] = {model.source_node}
    for line in model.lines:
        if line.section_id in drawn:
            visible.add(line.from_node)
            visible.add(line.to_node)
    for load in model.loads:
        visible.add(diagram_anchor_node(model, load.node_id, neighbors=index))
    for sed in model.seds:
        visible.add(diagram_anchor_node(model, sed.node_id, neighbors=index))
    # Red unida: la cabecera de CADA alimentador lleva su fuente dibujada.
    combinado = getattr(model, 'combined', None)
    for ref in (getattr(combinado, 'feeders', None) or ()):
        visible.add(ref.source_node)
    # Interruptores sin tramo: sin sus dos PointTerm el símbolo quedaría conectado a
    # la nada en el diagrama.
    for acoplador in getattr(model, 'couplers', ()):
        visible.add(acoplador.node_a)
        visible.add(acoplador.node_b)
    for enlace in (getattr(combinado, 'ties', None) or ()):
        visible.add(enlace.node_a)
        visible.add(enlace.node_b)
    return visible


@dataclass(frozen=True)
class DiagramSymbolLayout:
    """Radios, desplazamientos y tamaños de símbolo en unidades de diagrama.

    En la escala NA205 son los de la referencia. En una hoja normalizada salen de la
    cuadrícula (ver :func:`_diagram_symbol_layout`).
    """

    load_radius: float
    sed_radius: float
    source_offset: float
    sed_size: float
    median_segment: float
    parallel_offset: float = 4.0
    grid: float = 0.0
    """Paso de la cuadrícula de la hoja (mm); 0 en la escala NA205."""
    symbol_mm: float = 0.0
    """Tamaño objetivo de un símbolo sobre la hoja (mm); 0 en la escala NA205."""
    sizes: tuple[tuple[str, float], ...] = ()

    def tam(self, simbolo: str) -> float:
        """``rSizeX``/``rSizeY`` del símbolo: multiplicador de su tamaño propio en PF."""
        return dict(self.sizes).get(
            simbolo, NA205_SED_SIZE if simbolo == 'SecSubProd' else NA205_SYMBOL_SIZE)


# Reference IntGrf conventions (Ica / Nazca geographic export NA205):
# PointTerm / d_lin / d_load / d_net → rSizeX=rSizeY=1
# SecSubProd (SED triangle) → rSizeX=rSizeY=5
NA205_SYMBOL_SIZE = 1.0
NA205_SED_SIZE = 5.0
# Offsets in diagram units at NA205 geographic scale (~2.08 u/m).
NA205_LOAD_RADIUS = 40.0
NA205_SED_RADIUS = 20.0
NA205_SOURCE_OFFSET = 40.0
# Inside ElmSubstat (double-click triangle): LV bus like NA205 SE_*_2.
NA205_SED_LV_KV = 0.22
# DigSilent feeder colour (NA205 uses 10/11); one ElmFeeder per converted network.
NA205_FEEDER_ICOLOR = 11
# Offset between true parallel circuits sharing the same From↔To endpoints.
PARALLEL_CIRCUIT_OFFSET_DU = 4.0


#: Formatos de hoja de PowerFactory 2024 (Sys\Lib, ``SetFormat``), en mm, apaisados.
FORMATOS_HOJA: dict[str, tuple[float, float]] = {
    'A0': (1188.0, 840.0), 'A1': (840.0, 594.0), 'A2': (594.0, 420.0),
    'A3': (420.0, 297.0), 'A4': (297.0, 210.0),
}

#: Tamaño propio de cada símbolo en la biblioteca de PowerFactory 2024: el mayor lado
#: de ``IntSym.rBoundSzX/Y``, leído de Sys\Lib\Grf. ``rSizeX`` lo multiplica.
TAMANO_PROPIO_SIMBOLO: dict[str, float] = {
    'PointTerm': 1.3125, 'd_couple': 4.375, 'd_load': 6.5625, 'd_net': 6.5625,
    'SecSubProd': 8.0, 'd_lin': 8.75,
}

#: Pasos de cuadrícula normalizados (mm), de menor a mayor.
CUADRICULAS_MM = (0.05, 0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 5.0)

#: Tamaño relativo de cada símbolo respecto al símbolo tipo de la hoja.
PROPORCION_SIMBOLO = {
    'PointTerm': 0.5, 'd_couple': 1.0, 'd_load': 1.0, 'd_net': 1.5,
    'SecSubProd': 1.2, 'd_lin': 0.6,
}


def formato_hoja(nombre: str) -> tuple[float, float]:
    clave = (nombre or '').strip().upper()
    if clave not in FORMATOS_HOJA:
        raise ValueError(f'Formato de hoja desconocido: {nombre!r}. '
                         f'Use uno de {", ".join(FORMATOS_HOJA)}.')
    return FORMATOS_HOJA[clave]


def _cuadricula_y_simbolo(segmentos_mm: list[float], lado_menor_mm: float) -> tuple[float, float]:
    """Paso de cuadrícula y tamaño del símbolo tipo, ambos en mm de la hoja.

    El símbolo se mide contra la red dibujada: la mitad del tramo mediano, para que
    dos símbolos seguidos no se toquen. Se acota entre 0,4 mm (legible al imprimir) y
    el 0,8 % del lado menor de la hoja (no tapar la red). La cuadrícula es el mayor paso
    normalizado que cabe cuatro veces en el símbolo, y el símbolo se redondea a un
    múltiplo de ella: así todo encaja en la rejilla de PowerFactory.
    """
    validos = sorted(x for x in segmentos_mm if x > 0)
    mediana = validos[len(validos) // 2] if validos else 5.0
    simbolo = min(max(0.5 * mediana, 0.4), 0.008 * lado_menor_mm)
    grid = CUADRICULAS_MM[0]
    for paso in CUADRICULAS_MM:
        if paso <= simbolo / 4.0:
            grid = paso
    simbolo = max(2 * grid, round(simbolo / grid) * grid)
    return grid, simbolo


def _diagram_symbol_layout(
    geography: GeographyManifest,
    model: FeederModel,
    map_point,
    *,
    min_segment_m: float = 1.0,
    sheet: 'DiagramSheet | None' = None,
) -> DiagramSymbolLayout:
    """Return NA205 symbol sizes/offsets (not density-adaptive).

    Geographic placement still follows GPS via ``map_point``; only the graphic
    footprint of loads/SEDs/source matches the reference DGS so DigSilent
    schematic and map views keep the same element scale as NA205.
    """
    if sheet is not None and sheet.formato:
        # Hoja normalizada: los símbolos se miden en la cuadrícula de la hoja.
        segmentos = [ln.length_m * sheet.scale for ln in model.lines if ln.length_m > 0]
        grid, simbolo = _cuadricula_y_simbolo(segmentos, min(sheet.width, sheet.height))
        tamanos = tuple(
            (nombre, round(PROPORCION_SIMBOLO[nombre] * simbolo / propio, 6))
            for nombre, propio in sorted(TAMANO_PROPIO_SIMBOLO.items())
        )
        return DiagramSymbolLayout(
            load_radius=1.5 * simbolo,
            sed_radius=1.0 * simbolo,
            source_offset=2.0 * simbolo,
            sed_size=dict(tamanos)['SecSubProd'],
            median_segment=simbolo,
            parallel_offset=0.5 * simbolo,
            grid=grid,
            symbol_mm=simbolo,
            sizes=tamanos,
        )
    _ = (geography, model, map_point, min_segment_m)
    return DiagramSymbolLayout(
        load_radius=NA205_LOAD_RADIUS,
        sed_radius=NA205_SED_RADIUS,
        source_offset=NA205_SOURCE_OFFSET,
        sed_size=NA205_SED_SIZE,
        median_segment=NA205_LOAD_RADIUS,
    )


def _geo_to_meters(point: GeoPoint, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    """Local equirectangular meters — preserves X/Y aspect ratio."""
    meters_per_deg_lat = 110540.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(origin_lat))
    x = (point.lon - origin_lon) * meters_per_deg_lon
    y = (point.lat - origin_lat) * meters_per_deg_lat
    return x, y


# Calibrated from referencia NA205 (Ica / Nazca GPS ≈ -14.9°, -75.0°):
# IntGrf extent ≈ 54623 over ≈ 26283 m GPS span → ~2.08 diagram units per meter.
# Same scale keeps schematic + DigSilent Geographic Diagram element sizes aligned
# with NA205; GPSlat/GPSlon on ElmTerm/ElmSubstat place points on the PF map.
NA205_DIAGRAM_UNITS_PER_METER = 2.08
NA205_MAX_DIAGRAM_EXTENT = 55000.0
"""Huella de la hoja de NA205. Es una referencia histórica, **no un tope**.

Tratarla como tope es lo que arruinaba el diagrama de la red unida. Con la hoja fija en
55.000 unidades y una red de 320 km —16,7 veces NA205—, la escala se aplastaba de 2,08
a 0,171 u/m. Los símbolos, que se miden en unidades de diagrama y no en metros, pasaban
a cubrir 29,2 m de terreno en vez de 2,4: doce veces más grandes. Con 7.282 triángulos
de SED sobre la ciudad, el resultado era una mancha en la que no se distinguía la red.

La escala de 2,08 u/m es lo que hay que conservar, porque es lo que hace que un símbolo
mida lo mismo sobre el terreno esté solo su alimentador o esté el sistema entero. Lo que
tiene que crecer es la hoja.
"""

#: Tope absoluto de la hoja, como red de seguridad y no como criterio de dibujo.
#: A 2,08 u/m son unos 960 km de extensión: más que cualquier concesión de distribución.
#: Pasarse de ahí casi siempre significa coordenadas corruptas —un CRS equivocado
#: multiplica las distancias— y entonces sí conviene encoger y que se note.
MAX_DIAGRAM_EXTENT_ABSOLUTO = 2_000_000.0
# Margin so edge symbols (loads/SED/source) and parallel-circuit offsets stay on-sheet.
DIAGRAM_SHEET_MARGIN_DU = max(
    NA205_LOAD_RADIUS,
    NA205_SED_RADIUS,
    NA205_SOURCE_OFFSET,
) + PARALLEL_CIRCUIT_OFFSET_DU + NA205_SYMBOL_SIZE


def _meter_span(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(max(xs) - min(xs), max(ys) - min(ys), 0.0)


def _adaptive_scale(
    meter_xy: dict[str, tuple[float, float]],
    visible_ids: set[str],
    *,
    extra_points: list[tuple[float, float]] | None = None,
    margin_du: float = DIAGRAM_SHEET_MARGIN_DU,
    units_per_meter: float = NA205_DIAGRAM_UNITS_PER_METER,
    max_extent: float = MAX_DIAGRAM_EXTENT_ABSOLUTO,
) -> float:
    """Escala geográfica uniforme: la hoja crece con la red, la escala se mantiene.

    Preserva las proporciones de la topología del TXT (escala isótropa) e incluye los
    vértices intermedios del GIS y un margen para los símbolos, de modo que la hoja de
    DigSILENT cubra todo el mapa y no solo las barras eléctricas.

    Lo que **no** hace, y antes sí: encoger la escala para que la red quepa en una hoja
    de tamaño fijo. Los símbolos se miden en unidades de diagrama, no en metros, así
    que encoger la escala los agranda sobre el terreno. Con los 96 alimentadores
    —320 km— la escala caía a 0,171 u/m y cada triángulo de SED pasaba a cubrir 29 m en
    lugar de 2,4; multiplicado por 7.282 SED, el mapa se volvía ilegible.

    Solo se reduce al chocar con ``max_extent``, que es una red de seguridad contra
    coordenadas corruptas, no un criterio de dibujo.
    """
    points: list[tuple[float, float]] = list(meter_xy.values())
    if extra_points:
        points.extend(extra_points)
    if len(points) < 2:
        points = [meter_xy[i] for i in visible_ids if i in meter_xy]
    if len(points) < 2:
        return units_per_meter

    span_m = max(_meter_span(points), 1e-9)
    usable = max(max_extent - 2.0 * margin_du, max_extent * 0.5)
    return min(units_per_meter, usable / span_m)


def _geography_meter_frame(
    geography: GeographyManifest,
) -> tuple[float, float, dict[str, tuple[float, float]], list[tuple[float, float]]]:
    """Local equirectangular meters from WGS84 — same aspect as TXT projected coords."""
    lats = [p.lat for p in geography.nodes.values()]
    lons = [p.lon for p in geography.nodes.values()]
    origin_lat = sum(lats) / len(lats)
    origin_lon = sum(lons) / len(lons)
    meter_xy = {
        node_id: _geo_to_meters(point, origin_lat, origin_lon)
        for node_id, point in geography.nodes.items()
    }
    extras: list[tuple[float, float]] = []
    for gline in geography.lines.values():
        for point in gline.path:
            extras.append(_geo_to_meters(point, origin_lat, origin_lon))
    return origin_lat, origin_lon, meter_xy, extras


def _diagram_mapper_hoja(geography: GeographyManifest, formato: str):
    """Red entera dentro de una hoja normalizada, con escala isótropa y centrada.

    Las coordenadas son milímetros de la hoja, con el origen en su esquina inferior
    izquierda: PowerFactory dimensiona la hoja importada con el recuadro de los
    gráficos, así que si todo cae en [0, ancho]×[0, alto] la hoja es la pedida y no una
    a medida de metros de ancho. La orientación se elige por la forma de la red.
    """
    ancho, alto = formato_hoja(formato)
    origin_lat, origin_lon, meter_xy, extras = _geography_meter_frame(geography)
    puntos = list(meter_xy.values()) + extras
    xmin = min(p[0] for p in puntos)
    xmax = max(p[0] for p in puntos)
    ymin = min(p[1] for p in puntos)
    ymax = max(p[1] for p in puntos)
    span_x = max(xmax - xmin, 1.0)
    span_y = max(ymax - ymin, 1.0)
    orientacion = 'horizontal'
    if span_y > span_x:
        ancho, alto = alto, ancho
        orientacion = 'vertical'
    # Margen: 4 % del lado menor, holgura para los símbolos de borde (fuente, cargas).
    margen = max(0.04 * min(ancho, alto), 5.0)
    escala = min((ancho - 2 * margen) / span_x, (alto - 2 * margen) / span_y)
    ox = (ancho - span_x * escala) / 2.0 - xmin * escala
    oy = (alto - span_y * escala) / 2.0 - ymin * escala

    def map_point(point: GeoPoint) -> tuple[float, float]:
        x_m, y_m = _geo_to_meters(point, origin_lat, origin_lon)
        return x_m * escala + ox, y_m * escala + oy

    sheet = DiagramSheet(scale=escala, xmin=0.0, ymin=0.0, xmax=ancho, ymax=alto,
                         formato=formato.strip().upper(), orientacion=orientacion)
    return map_point, sheet


def _diagram_mapper(
    geography: GeographyManifest,
    visible_ids: set[str],
    *,
    margin_du: float = DIAGRAM_SHEET_MARGIN_DU,
    formato: str | None = None,
):
    """Return (map_point, DiagramSheet) with scale covering the full network map."""
    if formato:
        return _diagram_mapper_hoja(geography, formato)
    origin_lat, origin_lon, meter_xy, extras = _geography_meter_frame(geography)
    scale = _adaptive_scale(
        meter_xy,
        visible_ids,
        extra_points=extras,
        margin_du=margin_du,
    )

    def map_point(point: GeoPoint) -> tuple[float, float]:
        x_m, y_m = _geo_to_meters(point, origin_lat, origin_lon)
        return x_m * scale, y_m * scale

    sheet_points = [map_point(p) for p in geography.nodes.values()]
    for gline in geography.lines.values():
        sheet_points.extend(map_point(p) for p in gline.path)
    if not sheet_points:
        sheet = DiagramSheet(scale=scale, xmin=0.0, ymin=0.0, xmax=0.0, ymax=0.0)
        return map_point, sheet

    xs = [p[0] for p in sheet_points]
    ys = [p[1] for p in sheet_points]
    sheet = DiagramSheet(
        scale=scale,
        xmin=min(xs) - margin_du,
        ymin=min(ys) - margin_du,
        xmax=max(xs) + margin_du,
        ymax=max(ys) + margin_du,
    )
    return map_point, sheet


def _line_irot(path: list[tuple[float, float]]) -> int:
    if len(path) < 2:
        return 0
    # Prefer mid-segment direction when polyline has bends.
    if len(path) >= 3:
        mid = len(path) // 2
        x0, y0 = path[mid - 1]
        x1, y1 = path[mid]
    else:
        x0, y0 = path[0]
        x1, y1 = path[-1]
    angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
    return int(round(angle)) % 360


def _reduce_points(points: list[tuple[float, float]], maximum: int = 4) -> list[tuple[float, float]]:
    if len(points) <= maximum:
        return points
    indexes = [round(i * (len(points) - 1) / (maximum - 1)) for i in range(maximum)]
    return [points[i] for i in indexes]


def _offset_polyline(
    points: list[tuple[float, float]],
    distance: float,
) -> list[tuple[float, float]]:
    """Offset a polyline by ``distance`` along the left-hand normal."""
    if len(points) < 2 or distance == 0.0:
        return list(points)
    out: list[tuple[float, float]] = []
    last = len(points) - 1
    for i, (x, y) in enumerate(points):
        if i == 0:
            dx = points[1][0] - x
            dy = points[1][1] - y
        elif i == last:
            dx = x - points[i - 1][0]
            dy = y - points[i - 1][1]
        else:
            dx = points[i + 1][0] - points[i - 1][0]
            dy = points[i + 1][1] - points[i - 1][1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        out.append((x + nx * distance, y + ny * distance))
    return out


def ug_parallel_rail_paths(
    center: list[tuple[float, float]],
    *,
    offset: float,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Two parallel paths offset from ``center``, tapered to the same endpoints."""
    if len(center) < 2:
        return list(center), list(center)
    start, end = center[0], center[-1]
    left = _offset_polyline(center, offset)
    right = _offset_polyline(center, -offset)
    left[0] = start
    left[-1] = end
    right[0] = start
    right[-1] = end
    return left, right


def _connector_values(points: list[tuple[float, float]]) -> dict[str, object]:
    points = _reduce_points(points, 4)
    values: dict[str, object] = {'rX:SIZEROW': len(points), 'rY:SIZEROW': len(points)}
    for i, (x, y) in enumerate(points):
        values[f'rX:{i}'] = x
        values[f'rY:{i}'] = y
    return values


def _radial_offsets(count: int, radius: float) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    if count == 1:
        return [(radius, 0.0)]
    return [
        (radius * math.cos(2.0 * math.pi * i / count - math.pi / 2.0),
         radius * math.sin(2.0 * math.pi * i / count - math.pi / 2.0))
        for i in range(count)
    ]


def _sed_stype(sed: Sed) -> str:
    if sed.design_kva > 0:
        return f'{format(sed.design_kva, ".12g")} kVA'
    return ''


def _tr2_strn_mva(design_kva: float) -> float:
    """Transformer rated power in MVA (NA205 TypTr2.strn)."""
    return max(float(design_kva), 1.0) / 1000.0


#: Tensión de cortocircuito que se escribe en TypTr2 mientras no haya ficha.
NA205_TR2_UK_PCT = 4.0


def _tr2_losses_kw(design_kva: float, *, uk_pct: float = NA205_TR2_UK_PCT) -> tuple[float, float]:
    """Pérdidas ``(cobre, hierro)`` en kW, coherentes con la potencia y con ``uk``.

    Hay una restricción física que PowerFactory comprueba y que es fácil violar por
    accidente: la parte resistiva de la impedancia no puede superar la impedancia
    total. En porcentaje, ``uR% = Pcu / Sn · 100`` debe ser menor que ``uk%``.

    La versión anterior calculaba ``Pcu = max(Sn·10, 0.1) kW`` con un suelo fijo de
    0,1 kW. Ese suelo, combinado con el suelo de 1 kVA de :func:`_tr2_strn_mva`, daba
    para una SED de potencia declarada 0 un ``uR%`` del 10 % frente a un ``uk%`` del
    4 %: impedancia imposible. **Y PowerFactory no la descarta sola: rechaza el cálculo
    entero.** Una SED así entre 7.282 dejaba sin flujo de potencia a toda la red, con
    el mensaje «Real part of the positive-sequence impedance too high».

    Ahora las pérdidas salen de los máximos del Reglamento (UE) 548/2014 interpolados
    por potencia —los mismos que usa el catálogo de :mod:`igea_dgs.catalog_data`—, y
    fuera del rango tabulado se recurre al 1 % de la potencia nominal. En ambos casos
    se recorta al 40 % de ``uk%``, que deja el margen que el propio PowerFactory exige
    sin inventar un valor con pinta de medido.

    Sigue sin ser la ficha del transformador instalado, y el catálogo lo dice: estas
    cifras son un tope reglamentario, no un protocolo de ensayo.
    """
    from .catalog_data import TRAFO_PERDIDAS_UE, trafo_interpola

    kva = max(float(design_kva), 1.0)
    pcu = trafo_interpola(kva, TRAFO_PERDIDAS_UE, 2)   # Pk nivel 2, en W
    pfe = trafo_interpola(kva, TRAFO_PERDIDAS_UE, 3)   # Po nivel 2, en W
    pcu_kw = (pcu / 1000.0) if pcu is not None else kva * 0.01
    pfe_kw = (pfe / 1000.0) if pfe is not None else kva * 0.0015

    # uR% = Pcu[kW] / Sn[kVA] · 100  <  uk%. Se deja al 40 % del límite.
    tope_kw = uk_pct * 0.40 * kva / 100.0
    return min(pcu_kw, tope_kw), min(pfe_kw, tope_kw)


def _tr2_curmg_pct(design_kva: float, pfe_kw: float) -> float:
    """Corriente de vacío en %, nunca por debajo de la que exigen las pérdidas.

    PowerFactory comprueba que la corriente de vacío no sea menor que su componente
    activa: ``i0% >= Pfe / Sn · 100``. Escribir ``curmg = 0`` con ``pfe > 0`` provoca
    un aviso por transformador —«No Load Current is smaller than No Load Losses»— y
    PowerFactory la recalcula por su cuenta. Se toma el valor típico de norma y se
    garantiza el mínimo físico.
    """
    from .catalog_data import TRAFO_IO_TIPICO, trafo_interpola

    kva = max(float(design_kva), 1.0)
    tipico = trafo_interpola(kva, TRAFO_IO_TIPICO)
    minimo = pfe_kw / kva * 100.0
    return max(tipico if tipico is not None else 2.0, minimo * 1.05)


def write_dgs(
    model: FeederModel,
    path: Path | str,
    *,
    schema_profile: str = 'pf21_dgs_1_8_4',
    geography: GeographyManifest | None = None,
    trafos: Mapping[float, Mapping[str, float]] | None = None,
) -> DgsManifest:
    """Escribe el DGS del modelo.

    ``trafos`` son los datos de catálogo de los transformadores de SED por potencia
    en kVA —``uk_pct``, ``Pk_W``, ``Po_W`` y opcionalmente ``io_pct``— (ver
    :func:`igea_dgs.catalog.leer_trafos`). Una potencia que el catálogo trae completa
    usa esos valores; las demás, los máximos del Reglamento (:func:`_tr2_losses_kw`).
    """
    schema = load_schema(schema_profile)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    reg = FidRegistry()

    # En una red unida conviven 10 kV y 22,9 kV, así que la tensión es del nodo, no del
    # modelo. `combined` solo está relleno cuando se han unido varios alimentadores
    # (ver igea_dgs.combine); con uno solo, todo esto devuelve model.nominal_kv y el
    # resultado es idéntico al de siempre.
    combinado = getattr(model, 'combined', None)
    node_kv: dict[str, float] = getattr(combinado, 'node_kv', {}) if combinado else {}
    type_kv: dict[str, float] = getattr(combinado, 'type_kv', {}) if combinado else {}

    def kv_de(node_id: str) -> float:
        return node_kv.get(node_id, model.nominal_kv)

    # Nodos sin camino a ninguna fuente. Se escriben fuera de servicio para que el
    # flujo converja, pero siguen en el modelo y se siguen dibujando (ver
    # igea_dgs.combine.CombinedInfo.de_energised).
    sin_alimentar: set[str] = getattr(combinado, 'de_energised', set()) if combinado else set()

    def fuera(node_id: str) -> int:
        return 1 if node_id in sin_alimentar else 0

    general_fid = reg.new()
    network_fid = reg.new()
    diagram_fid = reg.new() if geography is not None else ''
    type_fids = {key: reg.new() for key in sorted(model.line_types)}
    node_fids = {node_id: reg.new() for node_id in sorted(model.nodes)}
    line_fids = {line.section_id: reg.new() for line in sorted(model.lines, key=lambda x: x.section_id)}
    load_keys = sorted((load.section_id, load.device_number) for load in model.loads)
    load_fids = {key: reg.new() for key in load_keys}
    sed_keys = sorted((sed.section_id, sed.device_number) for sed in model.seds)
    sed_fids = {key: reg.new() for key in sed_keys}
    # NA205 triangle interior: MT bus + BT bus + Tr2 + coupler to feeder node.
    sed_mt_fids = {key: reg.new() for key in sed_keys}
    sed_bt_fids = {key: reg.new() for key in sed_keys}
    sed_tr_fids = {key: reg.new() for key in sed_keys}
    sed_coup_fids = {key: reg.new() for key in sed_keys}
    # One TypTr2 per distinct (strn, utrn_h, utrn_l).
    tr2_type_keys: dict[tuple[float, float, float], str] = {}
    for sed in model.seds:
        # La tensión de alta es la del nodo al que cuelga la SED. En una red unida hay
        # SED a 10 kV y a 22,9 kV, y darles todas la tensión del modelo pondría un
        # transformador de 22,9/0,22 kV colgando de una barra de 10 kV.
        key = (
            round(_tr2_strn_mva(sed.design_kva), 9),
            round(kv_de(sed.node_id), 9),
            NA205_SED_LV_KV,
        )
        if key not in tr2_type_keys:
            tr2_type_keys[key] = reg.new()
    source_fid = reg.new()

    rows: dict[str, list[str]] = {name: [] for name in schema.tables}
    rows['General'].append(_make_row(schema, 'General', FID=general_fid, Descr='Version', Val=schema.general_version))
    rows['ElmNet'].append(_make_row(
        schema, 'ElmNet', FID=network_fid, OP='C', loc_name=_loc_name(model.name),
        fold_id='', frnom=60, pDiagram=diagram_fid
    ))
    if geography is not None:
        rows['IntGrfnet'].append(_make_row(
            schema, 'IntGrfnet', FID=diagram_fid, OP='C', loc_name=_loc_name(model.name),
            snap_on=0, grid_on=1, ortho_on=0, pDataFolder=network_fid,
        ))

    seds_by_key = {(sed.section_id, sed.device_number): sed for sed in model.seds}
    for key in sed_keys:
        sed = seds_by_key[key]
        gp = geography.nodes.get(sed.node_id) if geography is not None else None
        rows['ElmSubstat'].append(_make_row(
            schema, 'ElmSubstat', FID=sed_fids[key], OP='C',
            loc_name=_loc_name(sed.loc_name), fold_id=network_fid,
            sShort='T', sType=_sed_stype(sed),
            GPSlat=gp.lat if gp is not None else '',
            GPSlon=gp.lon if gp is not None else '',
        ))

    lv_phase = NA205_SED_LV_KV / math.sqrt(3.0)
    for node_id in sorted(model.nodes):
        gp = geography.nodes[node_id] if geography is not None else None
        kv = kv_de(node_id)
        rows['ElmTerm'].append(_make_row(
            schema, 'ElmTerm', FID=node_fids[node_id], OP='C', loc_name=_loc_name(node_id),
            fold_id=network_fid, typ_id='', systype=0, iUsage=1,
            uknom=kv, unknom=kv / math.sqrt(3.0), iminus=0, outserv=fuera(node_id),
            GPSlat=gp.lat if gp is not None else '', GPSlon=gp.lon if gp is not None else '', vtarget=1,
        ))

    # Internal SED buses (folder children of ElmSubstat) — required for PF double-click SLD.
    for key in sed_keys:
        sed = seds_by_key[key]
        gp = geography.nodes.get(sed.node_id) if geography is not None else None
        sub_fid = sed_fids[key]
        rows['ElmTerm'].append(_make_row(
            schema, 'ElmTerm', FID=sed_mt_fids[key], OP='C',
            loc_name=_loc_name(sed.loc_name), fold_id=sub_fid, typ_id='',
            # La barra MT de la SED está a la tensión de su nodo del alimentador, que
            # en una red unida no tiene por qué ser la del modelo.
            systype=0, iUsage=0, uknom=kv_de(sed.node_id),
            unknom=kv_de(sed.node_id) / math.sqrt(3.0),
            iminus=0, outserv=fuera(sed.node_id),
            GPSlat=gp.lat if gp is not None else '',
            GPSlon=gp.lon if gp is not None else '',
            vtarget=1,
        ))
        rows['ElmTerm'].append(_make_row(
            schema, 'ElmTerm', FID=sed_bt_fids[key], OP='C',
            loc_name=_loc_name(f'{sed.loc_name}_BT'), fold_id=sub_fid, typ_id='',
            systype=0, iUsage=0, uknom=NA205_SED_LV_KV, unknom=lv_phase,
            iminus=0, outserv=fuera(sed.node_id),
            GPSlat=gp.lat if gp is not None else '',
            GPSlon=gp.lon if gp is not None else '',
            vtarget=1,
        ))

    for key in sorted(model.line_types):
        typ = model.line_types[key]
        rated_ka = typ.ampacity_a / 1000.0 if typ.ampacity_a else 0.0
        rows['TypLne'].append(_make_row(
            schema, 'TypLne', FID=type_fids[key], OP='C',
            loc_name=_loc_name(_type_name(key, typ.code, type_kv.get(key))),
            uline=type_kv.get(key, model.nominal_kv),
            sline=rated_ka, InomAir=rated_ka, cohl_=1 if typ.source_table == 'LINE' else 0,
            rline=typ.r1_ohm_km, xline=typ.x1_ohm_km,
            rline0=typ.r0_ohm_km, xline0=typ.x0_ohm_km,
            Ithr=0, tmax=80, rtemp=75, systp=0, nlnph=3, nneutral=0,
            frnom=60, mlei=_material(typ.code),
            # El catálogo CYMDIST trae la susceptancia en µS/km, que es la unidad de
            # TypLne.bline. Escribirla como cero descartaba un dato correcto y dejaba
            # sin corriente capacitiva a los cables, donde vale ~95 µS/km frente a los
            # ~3,7 µS/km de una línea aérea.
            bline=typ.b1_source, bline0=typ.b0_source,
        ))

    for (strn, utrn_h, utrn_l), fid in sorted(tr2_type_keys.items()):
        # Pérdidas del Reglamento (UE) 548/2014 y recortadas para que uR% < uk%.
        # El suelo fijo anterior violaba esa condición en una SED de 0 kVA y
        # PowerFactory rechazaba el cálculo de TODA la red (ver _tr2_losses_kw).
        kva = strn * 1000.0
        uk = NA205_TR2_UK_PCT
        ficha = (trafos or {}).get(round(kva, 3))
        if ficha and all(ficha.get(k) for k in ('uk_pct', 'Pk_W', 'Po_W')):
            # Datos del catálogo. Se respetan salvo que violen uR% < uk%, que
            # PowerFactory rechaza para la red ENTERA; entonces se recorta y se sabe.
            uk = float(ficha['uk_pct'])
            pcutr = min(float(ficha['Pk_W']) / 1000.0, uk * 0.95 * kva / 100.0)
            pfe_kw = float(ficha['Po_W']) / 1000.0
            io = float(ficha.get('io_pct') or 0.0)
            curmg = max(io, pfe_kw / kva * 100.0 * 1.05) if io else _tr2_curmg_pct(kva, pfe_kw)
        else:
            pcutr, pfe_kw = _tr2_losses_kw(kva, uk_pct=uk)
            # Corriente de vacío coherente con las pérdidas en hierro: si curmg queda
            # en cero pero pfe no, PowerFactory avisa por cada transformador —909
            # avisos en trece alimentadores— y la recalcula sola.
            curmg = _tr2_curmg_pct(kva, pfe_kw)
        rows['TypTr2'].append(_make_row(
            schema, 'TypTr2', FID=fid, OP='C',
            loc_name=_loc_name(f'TR_{format(strn * 1000.0, ".12g")}kVA'),
            nt2ph=3, strn=strn, frnom=60, utrn_h=utrn_h, utrn_l=utrn_l,
            uktr=uk, pcutr=pcutr, uk0tr=uk, ur0tr=0,
            tr2cn_h='D', tr2cn_l='YN', nt2ag=5, curmg=curmg, pfe=pfe_kw,
            zx0hl_n=100, itapch=0, tap_side=0, dutap=0, phitr=0,
            nntap0=0, ntpmn=0, ntpmx=0, manuf='',
        ))

    for line in sorted(model.lines, key=lambda x: x.section_id):
        rows['ElmLne'].append(_make_row(
            schema, 'ElmLne', FID=line_fids[line.section_id], OP='C',
            loc_name=_loc_name(line.section_id), fold_id=network_fid,
            typ_id=type_fids[line.type_key], dline=line.length_km, fline=1,
            GPScoords='', nlnum=1, inAir=1 if line.overhead else 0,
        ))

    for key in sed_keys:
        sed = seds_by_key[key]
        strn = _tr2_strn_mva(sed.design_kva)
        typ_key = (round(strn, 9), round(kv_de(sed.node_id), 9), NA205_SED_LV_KV)
        rows['ElmTr2'].append(_make_row(
            schema, 'ElmTr2', FID=sed_tr_fids[key], OP='C',
            loc_name=_loc_name(f'TR_{sed.loc_name}'), fold_id=sed_fids[key],
            typ_id=tr2_type_keys[typ_key], ntnum=1, outserv=fuera(sed.node_id), nntap=0,
            i_auto=0, ntrcn=0, usetp=1, usp_low=0.99, usp_up=1.01, t2ldc=0,
        ))
        rows['ElmCoup'].append(_make_row(
            schema, 'ElmCoup', FID=sed_coup_fids[key], OP='C',
            loc_name=_loc_name(f'SW_{sed.loc_name}'), fold_id=sed_fids[key],
            typ_id='', on_off=1, aUsage='cbk', nphase=3, nneutral=0,
        ))

    loads_by_key = {(x.section_id, x.device_number): x for x in model.loads}
    # NA205 pattern: SED loads live *inside* ElmSubstat (module in the triangle),
    # not as sibling network objects with their own d_load symbol.
    nested_load_keys = {sed.load_key for sed in model.seds}
    for key in load_keys:
        load = loads_by_key[key]
        apparent = math.hypot(load.p_mw, load.q_mvar)
        name = load.display_name or load.customer_number or load.device_number or load.section_id
        fold = sed_fids[key] if key in nested_load_keys else network_fid
        # Fases reales de la carga. Escribir una monofásica como trifásica equilibrada
        # reparte su corriente entre tres conductores en lugar de uno: subestima la
        # caída de tensión de ese ramal y borra el desequilibrio, que el TdR del VAD
        # manda evaluar. i_sym=0 le dice a PowerFactory que use plinir/plinis/plinit.
        letras = decode_phase(load.phase) or 'ABC'
        pr, ps, pt = split_by_phase(load.p_mw, load.phase)
        qr, qs, qt = split_by_phase(load.q_mvar, load.phase)
        rows['ElmLod'].append(_make_row(
            schema, 'ElmLod', FID=load_fids[key], OP='C', loc_name=_loc_name(name),
            fold_id=fold, typ_id='', mode_inp='PC', slini=apparent,
            plini=load.p_mw, qlini=load.q_mvar, coslini=load.pf,
            pf_recap=0, scale0=1, i_scale=1, outserv=fuera(load.node_id),
            classif=_loc_name(load.customer_type)[:20],
            # Denominador de SAIFI y SAIDI: los índices de la NTCSE se ponderan por
            # cliente. Sin esto el análisis de fiabilidad calcula otra cosa.
            #
            # Se escribe SOLO si hay dato. PowerFactory exige NrCust > 0 y rechaza el
            # cero con «Condition for Variable NrCust violated»: mandar cero producía
            # 545 errores de importación en un solo alimentador y, peor, PowerFactory
            # se quedaba con su valor por defecto de 1 sin que el recuento lo dijera.
            # En blanco se aplica ese mismo defecto, pero sin ensuciar el registro.
            NrCust=load.customers if load.customers > 0 else '',
            i_sym=1 if letras == 'ABC' else 0,
            plinir=pr, plinis=ps, plinit=pt,
            qlinir=qr, qlinis=qs, qlinit=qt,
        ))

    # Una red unida tiene una fuente por alimentador: cada uno viene de su propia barra
    # de subestación. Un modelo de un alimentador tiene una sola, y el bucle recorre esa.
    fuentes = [(model.name, model.source_node, source_fid)]
    if combinado is not None and getattr(combinado, 'feeders', None):
        fuentes = [
            (ref.name, ref.source_node, source_fid if i == 0 else reg.new())
            for i, ref in enumerate(combinado.feeders)
        ]
    for nombre_fuente, _nodo_fuente, fid_fuente in fuentes:
        rows['ElmXnet'].append(_make_row(
            schema, 'ElmXnet', FID=fid_fuente, OP='C',
            loc_name=_loc_name(f'External Grid {nombre_fuente}'),
            fold_id=network_fid, snss='', rntxn='', z2tz1='', snssmin='', rntxnmin='', z2tz1min='',
            chr_name='', bustp='SL', pgini=0, qgini=0, phiini=0, usetp=1,
            outserv=0, Kpf=0, K=0,
        ))

    line_cubic_fids: dict[tuple[str, int], str] = {}
    for line in sorted(model.lines, key=lambda x: x.section_id):
        line_fid = line_fids[line.section_id]
        for side, node_id, suffix in ((0, line.from_node, '1'), (1, line.to_node, '2')):
            cubic_fid = reg.new()
            line_cubic_fids[(line.section_id, side)] = cubic_fid
            rows['StaCubic'].append(_make_row(
                schema, 'StaCubic', FID=cubic_fid, OP='C',
                loc_name=_loc_name(f'Cub{suffix}_{line.section_id}'),
                fold_id=node_fids[node_id], obj_bus=side, obj_id=line_fid,
                it2p1=0, it2p2=1, it2p3=2,
            ))

    load_cubic_fids: dict[tuple[str, str], str] = {}
    for key in load_keys:
        load = loads_by_key[key]
        cubic_fid = reg.new()
        load_cubic_fids[key] = cubic_fid
        # Nested SED load hangs on internal BT bus (NA205 SE_*_2), not feeder node.
        fold_term = sed_bt_fids[key] if key in nested_load_keys else node_fids[load.node_id]
        rows['StaCubic'].append(_make_row(
            schema, 'StaCubic', FID=cubic_fid, OP='C',
            loc_name=_loc_name(f'Cub_{load.device_number}'), fold_id=fold_term,
            obj_bus=0, obj_id=load_fids[key], it2p1=0, it2p2=1, it2p3=2,
        ))

    for key in sed_keys:
        # Transformer HV=MT (bus0), LV=BT (bus1)
        rows['StaCubic'].append(_make_row(
            schema, 'StaCubic', FID=reg.new(), OP='C',
            loc_name=_loc_name(f'Cub1_TR_{seds_by_key[key].loc_name}'),
            fold_id=sed_mt_fids[key], obj_bus=0, obj_id=sed_tr_fids[key],
            it2p1=0, it2p2=1, it2p3=2,
        ))
        rows['StaCubic'].append(_make_row(
            schema, 'StaCubic', FID=reg.new(), OP='C',
            loc_name=_loc_name(f'Cub2_TR_{seds_by_key[key].loc_name}'),
            fold_id=sed_bt_fids[key], obj_bus=1, obj_id=sed_tr_fids[key],
            it2p1=0, it2p2=1, it2p3=2,
        ))
        # Coupler: feeder TXT node ↔ internal MT bus
        sed = seds_by_key[key]
        rows['StaCubic'].append(_make_row(
            schema, 'StaCubic', FID=reg.new(), OP='C',
            loc_name=_loc_name(f'Cub1_SW_{sed.loc_name}'),
            fold_id=node_fids[sed.node_id], obj_bus=0, obj_id=sed_coup_fids[key],
            it2p1=0, it2p2=1, it2p3=2,
        ))
        rows['StaCubic'].append(_make_row(
            schema, 'StaCubic', FID=reg.new(), OP='C',
            loc_name=_loc_name(f'Cub2_SW_{sed.loc_name}'),
            fold_id=sed_mt_fids[key], obj_bus=1, obj_id=sed_coup_fids[key],
            it2p1=0, it2p2=1, it2p3=2,
        ))

    # Enlaces entre alimentadores: un ElmCoup NORMALMENTE ABIERTO por cada uno, con su
    # cubículo a cada lado. Abierto (on_off=0) es como opera la red de verdad —los
    # alimentadores son radiales y el enlace solo se cierra para transferir carga— y es
    # lo que necesita ComTieopt (manual §41.6) para tener algo que optimizar.
    tie_rows: list[tuple[object, str]] = []
    for enlace in (getattr(combinado, 'ties', ()) if combinado else ()):
        if enlace.node_a not in node_fids or enlace.node_b not in node_fids:
            continue
        coup_fid = reg.new()
        tie_rows.append((enlace, coup_fid))
        rows['ElmCoup'].append(_make_row(
            schema, 'ElmCoup', FID=coup_fid, OP='C',
            loc_name=_loc_name(enlace.name), fold_id=network_fid, typ_id='',
            on_off=0, aUsage='swt', nphase=3, nneutral=0,
        ))
        for lado, nodo in ((0, enlace.node_a), (1, enlace.node_b)):
            rows['StaCubic'].append(_make_row(
                schema, 'StaCubic', FID=reg.new(), OP='C',
                loc_name=_loc_name(f'Cub{lado + 1}_{enlace.name}'),
                fold_id=node_fids[nodo], obj_bus=lado, obj_id=coup_fid,
                it2p1=0, it2p2=1, it2p3=2,
            ))

    # Interruptores sin tramo: los seccionadores de los tramos puente fundidos (ver
    # igea_dgs.puentes). Uno por dispositivo de la base, con su estado normal, entre
    # las dos barras que unía el puente. Van en la red, no en una SED.
    coupler_rows: list[tuple[object, str]] = []
    for acoplador in sorted(getattr(model, 'couplers', ()),
                            key=lambda c: (c.section_id, c.node_a, c.name)):
        if acoplador.node_a not in node_fids or acoplador.node_b not in node_fids:
            continue
        coup_fid = reg.new()
        coupler_rows.append((acoplador, coup_fid))
        rows['ElmCoup'].append(_make_row(
            schema, 'ElmCoup', FID=coup_fid, OP='C',
            loc_name=_loc_name(acoplador.name), fold_id=network_fid, typ_id='',
            on_off=int(acoplador.on_off), aUsage='swt', nphase=3, nneutral=0,
        ))
        for lado, nodo in ((0, acoplador.node_a), (1, acoplador.node_b)):
            rows['StaCubic'].append(_make_row(
                schema, 'StaCubic', FID=reg.new(), OP='C',
                loc_name=_loc_name(f'Cub{lado + 1}_{acoplador.name}'),
                fold_id=node_fids[nodo], obj_bus=lado, obj_id=coup_fid,
                it2p1=0, it2p2=1, it2p3=2,
            ))

    # Un ElmFeeder por alimentador: es lo que da a PowerFactory la herramienta de
    # coloreado y de recorrido por alimentador. En una red unida son 96, y es
    # precisamente lo que permite seguir distinguiéndolos dentro de la misma grid.
    lineas_ordenadas = sorted(model.lines, key=lambda x: x.section_id)
    for nombre_fuente, nodo_fuente, fid_fuente in fuentes:
        if nodo_fuente not in node_fids:
            continue
        source_cubic_fid = reg.new()
        rows['StaCubic'].append(_make_row(
            schema, 'StaCubic', FID=source_cubic_fid, OP='C',
            loc_name=_loc_name(f'Cub_Source_{nombre_fuente}'),
            fold_id=node_fids[nodo_fuente], obj_bus=0, obj_id=fid_fuente,
            it2p1=0, it2p2=1, it2p3=2,
        ))
        # DigSilent ElmFeeder (NA205): colour/feeder tool anchored on a root StaCubic.
        # Prefer the first outgoing line cubicle at the SOURCE bus; else ElmXnet cubic.
        feeder_cubic_fid = source_cubic_fid
        for line in lineas_ordenadas:
            if line.from_node == nodo_fuente:
                feeder_cubic_fid = line_cubic_fids[(line.section_id, 0)]
                break
            if line.to_node == nodo_fuente:
                feeder_cubic_fid = line_cubic_fids[(line.section_id, 1)]
                break
        rows['ElmFeeder'].append(_make_row(
            schema, 'ElmFeeder', FID=reg.new(), OP='C',
            loc_name=_loc_name(nombre_fuente),
            obj_id=feeder_cubic_fid,
            iorient=0, i_scale=0, Sset=0, icolor=NA205_FEEDER_ICOLOR, outserv=0,
        ))

    switch_fids: dict[tuple[str, str, str], str] = {}
    for device in sorted(model.devices, key=lambda d: (d.section_id, d.terminal_side, d.kind, d.eq_number, d.eq_id)):
        fid = reg.new()
        key = (device.section_id, device.kind, device.eq_number)
        switch_fids[key] = fid
        rows['StaSwitch'].append(_make_row(
            schema, 'StaSwitch', FID=fid, OP='C', loc_name=_loc_name(device.eq_number or device.eq_id or device.kind),
            fold_id=line_cubic_fids[(device.section_id, device.terminal_side)],
            on_off=device.on_off, typ_id='', aUsage='cbk',
        ))

    graphic_fids: dict[str, str] = {}
    visible_nodes: set[str] = set()
    diagram_sheet: DiagramSheet | None = None
    if geography is not None:
        # Build the adjacency index and the drawn-section set once for the whole
        # graphic layer; every helper below reuses them.
        neighbors = _line_neighbors(model)
        drawn_line_sections = diagram_line_sections(model, neighbors=neighbors)
        visible_nodes = visible_pointterm_nodes(model, neighbors=neighbors, drawn=drawn_line_sections)
        formato = getattr(model, 'diagram_sheet', None)
        map_point, diagram_sheet = _diagram_mapper(geography, visible_nodes, formato=formato)
        node_xy = {node_id: map_point(point) for node_id, point in geography.nodes.items()}
        layout = _diagram_symbol_layout(geography, model, map_point, sheet=diagram_sheet)

        # Visible PointTerm only (electrical ElmTerm always exist).
        for node_id in sorted(visible_nodes):
            if node_id not in node_xy:
                continue
            fid = reg.new(); graphic_fids[f'node:{node_id}'] = fid
            x, y = node_xy[node_id]
            rows['IntGrf'].append(_make_row(
                schema, 'IntGrf', FID=fid, OP='C', loc_name=_loc_name(f'G_{node_id}'),
                fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
                rCenterX=x, rCenterY=y, sSymNam='PointTerm', pDataObj=node_fids[node_id],
                iRot=0, rSizeX=layout.tam('PointTerm'), rSizeY=layout.tam('PointTerm'),
            ))

        # Skip micro service-stub d_lin (≤1 m tip→primary). Electrical ElmLne remains;
        # SED/load symbols already snap to the primary via diagram_anchor_node.
        # One d_lin per ElmLne (NA205). Underground style = inAir=0 in DigSilent.
        # True doble circuito (2 SECTION same From↔To) → slight perpendicular offset.
        # drawn_line_sections was already computed above with the shared index.
        circuit_offsets = parallel_circuit_graphic_offsets(
            model, offset_du=layout.parallel_offset,
        )

        for line in sorted(model.lines, key=lambda x: x.section_id):
            if line.section_id not in drawn_line_sections:
                continue
            gline = geography.lines[line.section_id]
            xy_path = [map_point(point) for point in gline.path]
            if line.from_node in node_xy:
                xy_path[0] = node_xy[line.from_node]
            if line.to_node in node_xy:
                xy_path[-1] = node_xy[line.to_node]
            rail_offset = circuit_offsets.get(line.section_id, 0.0)
            if rail_offset:
                left, right = ug_parallel_rail_paths(xy_path, offset=abs(rail_offset))
                xy_path = left if rail_offset > 0 else right
                # Keep terminals on the shared buses so both circuits meet at PointTerms.
                xy_path[0] = node_xy[line.from_node]
                xy_path[-1] = node_xy[line.to_node]
            if len(xy_path) < 2:
                continue
            if len(xy_path) == 2:
                center = ((xy_path[0][0] + xy_path[1][0]) / 2, (xy_path[0][1] + xy_path[1][1]) / 2)
                augmented = [xy_path[0], center, xy_path[1]]
            else:
                augmented = list(xy_path)
                mid = len(augmented) // 2
                center = augmented[mid]
            fid = reg.new()
            graphic_fids[f'line:{line.section_id}'] = fid
            irot = _line_irot(augmented)
            rows['IntGrf'].append(_make_row(
                schema, 'IntGrf', FID=fid, OP='C',
                loc_name=_loc_name(f'G_{line.section_id}'),
                fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
                rCenterX=center[0], rCenterY=center[1], sSymNam='d_lin',
                pDataObj=line_fids[line.section_id],
                iRot=irot, rSizeX=layout.tam('d_lin'), rSizeY=layout.tam('d_lin'),
            ))
            mid = len(augmented) // 2
            left = list(reversed(augmented[:mid + 1]))
            right = list(augmented[mid:])
            left[0] = center
            left[-1] = node_xy[line.from_node]
            right[0] = center
            right[-1] = node_xy[line.to_node]
            for con_nr, con_points in ((0, left), (1, right)):
                con_fid = reg.new()
                rows['IntGrfcon'].append(_make_row(
                    schema, 'IntGrfcon', FID=con_fid, OP='C',
                    loc_name=_loc_name(f'GCO_{con_nr + 1}_{line.section_id}'),
                    fold_id=fid, iDatConNr=con_nr, **_connector_values(con_points),
                ))

        # Interruptores sin tramo: símbolo d_couple entre sus dos barras, a escala real.
        for acoplador, coup_fid in coupler_rows:
            a = node_xy.get(acoplador.node_a)
            b = node_xy.get(acoplador.node_b)
            if a is None or b is None:
                continue
            center = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            fid = reg.new()
            graphic_fids[f'coupler:{acoplador.section_id}:{acoplador.name}'] = fid
            rows['IntGrf'].append(_make_row(
                schema, 'IntGrf', FID=fid, OP='C',
                loc_name=_loc_name(f'G_{acoplador.name}'),
                fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
                rCenterX=center[0], rCenterY=center[1], sSymNam='d_couple',
                pDataObj=coup_fid, iRot=_line_irot([a, center, b]),
                rSizeX=layout.tam('d_couple'), rSizeY=layout.tam('d_couple'),
            ))
            for con_nr, extremo in ((0, a), (1, b)):
                rows['IntGrfcon'].append(_make_row(
                    schema, 'IntGrfcon', FID=reg.new(), OP='C',
                    loc_name=_loc_name(f'GCO_{con_nr + 1}_{acoplador.name}'),
                    fold_id=fid, iDatConNr=con_nr,
                    **_connector_values([center, extremo]),
                ))

        # Enlaces entre alimentadores: sus dos barras son copias del mismo nodo de la
        # base, en el mismo punto. El símbolo se aparta un poco para que se vea.
        for enlace, coup_fid in tie_rows:
            a = node_xy.get(enlace.node_a)
            b = node_xy.get(enlace.node_b)
            if a is None or b is None:
                continue
            center = (a[0] + layout.source_offset / 2, a[1] + layout.source_offset / 2)
            fid = reg.new()
            graphic_fids[f'tie:{enlace.name}'] = fid
            rows['IntGrf'].append(_make_row(
                schema, 'IntGrf', FID=fid, OP='C', loc_name=_loc_name(f'G_{enlace.name}'),
                fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
                rCenterX=center[0], rCenterY=center[1], sSymNam='d_couple',
                pDataObj=coup_fid, iRot=0,
                rSizeX=layout.tam('d_couple'), rSizeY=layout.tam('d_couple'),
            ))
            for con_nr, extremo in ((0, a), (1, b)):
                rows['IntGrfcon'].append(_make_row(
                    schema, 'IntGrfcon', FID=reg.new(), OP='C',
                    loc_name=_loc_name(f'GCO_{con_nr + 1}_{enlace.name}'),
                    fold_id=fid, iDatConNr=con_nr,
                    **_connector_values([center, extremo]),
                ))

        # Free loads only (no SED): d_load on the sheet. SED-backed loads are
        # modules inside SecSubProd — matching NA205, they get no IntGrf.
        free_load_keys = [key for key in load_keys if key not in nested_load_keys]
        loads_by_anchor: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for key in free_load_keys:
            load = loads_by_key[key]
            loads_by_anchor[diagram_anchor_node(model, load.node_id, neighbors=neighbors)].append(key)
        for anchor_id, keys in loads_by_anchor.items():
            node_x, node_y = node_xy[anchor_id]
            offsets = _radial_offsets(len(keys), radius=layout.load_radius)
            for key, (dx, dy) in zip(keys, offsets):
                load = loads_by_key[key]
                x, y = node_x + dx, node_y + dy
                fid = reg.new(); graphic_fids[f'load:{key[0]}:{key[1]}'] = fid
                rows['IntGrf'].append(_make_row(
                    schema, 'IntGrf', FID=fid, OP='C', loc_name=_loc_name(f'G_{load.display_name or load.device_number}'),
                    fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
                    rCenterX=x, rCenterY=y, sSymNam='d_load', pDataObj=load_fids[key],
                    iRot=int(round(math.degrees(math.atan2(dy, dx)))) % 360,
                    rSizeX=layout.tam('d_load'), rSizeY=layout.tam('d_load'),
                ))
                con_fid = reg.new()
                rows['IntGrfcon'].append(_make_row(
                    schema, 'IntGrfcon', FID=con_fid, OP='C',
                    loc_name=_loc_name(f'GCO_{load.device_number}'), fold_id=fid,
                    iDatConNr=0, **_connector_values([(x, y), (node_x, node_y)]),
                ))

        # SEDs → SecSubProd triangle (no IntGrfcon; nested ElmLod is the module).
        seds_by_anchor: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for key in sed_keys:
            sed = seds_by_key[key]
            seds_by_anchor[diagram_anchor_node(model, sed.node_id, neighbors=neighbors)].append(key)
        for anchor_id, keys in seds_by_anchor.items():
            node_x, node_y = node_xy[anchor_id]
            # Single SED sits on the bus; several share a small ring.
            radius = 0.0 if len(keys) == 1 else layout.sed_radius
            offsets = _radial_offsets(len(keys), radius=radius) if radius else [(0.0, 0.0)] * len(keys)
            for key, (dx, dy) in zip(keys, offsets):
                sed = seds_by_key[key]
                x, y = node_x + dx, node_y + dy
                fid = reg.new(); graphic_fids[f'sed:{key[0]}:{key[1]}'] = fid
                rows['IntGrf'].append(_make_row(
                    schema, 'IntGrf', FID=fid, OP='C', loc_name=_loc_name(f'gnoT {sed.loc_name}'),
                    fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
                    rCenterX=x, rCenterY=y, sSymNam='SecSubProd', pDataObj=sed_fids[key],
                    iRot=0, rSizeX=layout.sed_size, rSizeY=layout.sed_size,
                ))

        # Una red externa dibujada por fuente: en una red unida, una por alimentador.
        for indice, (nombre_fuente, nodo_fuente, fid_fuente) in enumerate(fuentes):
            if nodo_fuente not in node_xy:
                continue
            src_x, src_y = node_xy[nodo_fuente]
            sx, sy = src_x - layout.source_offset, src_y + layout.source_offset
            src_graph_fid = reg.new()
            graphic_fids['source' if indice == 0 else f'source:{nombre_fuente}'] = src_graph_fid
            rows['IntGrf'].append(_make_row(
                schema, 'IntGrf', FID=src_graph_fid, OP='C', loc_name=_loc_name(f'G_Source_{nombre_fuente}'),
                fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
                rCenterX=sx, rCenterY=sy, sSymNam='d_net', pDataObj=fid_fuente,
                iRot=0, rSizeX=layout.tam('d_net'), rSizeY=layout.tam('d_net'),
            ))
            src_con_fid = reg.new()
            rows['IntGrfcon'].append(_make_row(
                schema, 'IntGrfcon', FID=src_con_fid, OP='C', loc_name=_loc_name(f'GCO_Source_{nombre_fuente}'),
                fold_id=src_graph_fid, iDatConNr=0, **_connector_values([(sx, sy), (src_x, src_y)]),
            ))

    preamble = [
        '*' * 80,
        '*',
        '* IGEA/CYMDIST to DIgSILENT DGS converter',
        f'* Compatibility profile: {schema.profile}',
        f'* Project: {model.name}',
        '* Reference DGS runtime dependency: NONE',
        '*',
        '*' * 80,
        '',
    ]
    output = list(preamble)
    used_tables = {
        'General', 'ElmNet', 'ElmTerm', 'TypLne', 'ElmLne', 'ElmLod', 'ElmXnet',
        'StaCubic', 'StaSwitch', 'ElmFeeder',
    }
    if sed_keys:
        used_tables |= {'ElmSubstat', 'ElmTr2', 'TypTr2', 'ElmCoup'}
    if rows['ElmCoup']:
        # Los enlaces entre alimentadores también son ElmCoup, y pueden existir en una
        # red sin ninguna SED. Atar la tabla solo a las SED los dejaba fuera del
        # fichero sin ningún aviso: las filas se construían y no se escribían.
        used_tables.add('ElmCoup')
    if geography is not None:
        used_tables |= {'IntGrf', 'IntGrfcon', 'IntGrfnet'}
    for table in schema.table_order:
        if table not in used_tables:
            continue
        output.append(schema.header(table))
        output.extend(rows[table])
        output.extend(['', ''])
    path.write_text('\n'.join(output), encoding='utf-8')

    return DgsManifest(
        network_fid=network_fid,
        type_fids=type_fids,
        node_fids=node_fids,
        line_fids=line_fids,
        load_fids=load_fids,
        source_fid=source_fid,
        source_cubic_fid=source_cubic_fid,
        line_cubic_fids=line_cubic_fids,
        switch_fids=switch_fids,
        diagram_fid=diagram_fid,
        graphic_fids=graphic_fids,
        sed_fids=sed_fids,
        visible_pointterm_nodes=tuple(sorted(visible_nodes)),
        diagram_sheet=diagram_sheet,
        diagram_grid_mm=layout.grid if geography is not None else 0.0,
    )
