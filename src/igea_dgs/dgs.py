from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import math

from .model import FeederModel, Line, Sed
from .schema import DgsSchema, load_schema
from .geography import GeographyManifest, GeoPoint


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


def _type_name(key: str, code: str) -> str:
    if code != 'DEFAULT':
        return code
    return 'DEFAULT_OH' if key.startswith('LINE:') else 'DEFAULT_UG'


def _make_row(schema: DgsSchema, table: str, **values) -> str:
    fields = schema.fields(table)
    return '  ' + ';'.join(_fmt(values.get(field, '')) for field in fields)


def _node_degrees(model: FeederModel) -> dict[str, int]:
    degrees: dict[str, int] = defaultdict(int)
    for line in model.lines:
        degrees[line.from_node] += 1
        degrees[line.to_node] += 1
    return dict(degrees)


def _line_neighbors(model: FeederModel) -> dict[str, list[tuple[str, Line]]]:
    """node_id → [(neighbor_id, Line), ...]"""
    neighbors: dict[str, list[tuple[str, Line]]] = defaultdict(list)
    for line in model.lines:
        neighbors[line.from_node].append((line.to_node, line))
        neighbors[line.to_node].append((line.from_node, line))
    return neighbors


def diagram_anchor_node(model: FeederModel, node_id: str, *, max_stub_m: float = 1.0) -> str:
    """Snap micro service-stub tips to the upstream network bus for graphics.

    CYMDIST often models a ~0.3 m section from a primary SED node to a tip
    terminal where the load hangs. Electrically the load stays on the tip;
    graphically anchoring at the primary keeps SED/load symbols on the feeder.
    """
    neighbors = _line_neighbors(model).get(node_id, ())
    if len(neighbors) != 1:
        return node_id
    other_id, line = neighbors[0]
    if line.length_m <= max_stub_m:
        return other_id
    return node_id


def is_micro_service_stub_line(model: FeederModel, line: Line, *, max_stub_m: float = 1.0) -> bool:
    """True for ≤1 m tip sections that only hang a load/SED off the primary bus.

    These stay in ElmLne/StaCubic (electrical) but must not get IntGrf d_lin:
    at NA205 scale (~2 u/m) they render as dust and look like loose fragments.
    NA205 itself almost never draws such micro stubs (median span ~50 m).
    """
    if line.length_m > max_stub_m:
        return False
    if diagram_anchor_node(model, line.from_node, max_stub_m=max_stub_m) == line.to_node:
        return True
    if diagram_anchor_node(model, line.to_node, max_stub_m=max_stub_m) == line.from_node:
        return True
    return False


def diagram_line_sections(model: FeederModel, *, max_stub_m: float = 1.0) -> set[str]:
    """SectionIDs that receive IntGrf d_lin (excludes micro service stubs)."""
    return {
        line.section_id
        for line in model.lines
        if not is_micro_service_stub_line(model, line, max_stub_m=max_stub_m)
    }


def diagram_line_rail_counts(
    model: FeederModel,
    *,
    max_stub_m: float = 1.0,
) -> tuple[int, int, int]:
    """Return ``(overhead_drawn, underground_drawn, d_lin_graphics)``.

    One IntGrf ``d_lin`` per drawn ElmLne (NA205 pattern). Underground look in
    DigSilent comes from ``ElmLne.inAir=0``, not duplicate graphics.
    """
    drawn = diagram_line_sections(model, max_stub_m=max_stub_m)
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


def visible_pointterm_nodes(model: FeederModel) -> set[str]:
    """Black PointTerm symbols so drawn lines are not floating fragments.

    Rules (aligned with NA205 density — most line ends sit on a PointTerm):
    - every endpoint of a *drawn* ElmLne (``diagram_line_sections``)
    - feeder head / source node
    - graphic anchors of loads/SEDs (upstream bus when tip is a ≤1 m stub)
    Hidden (still in ElmTerm electrical model):
    - micro service-stub tips (≤1 m) whose ``d_lin`` is omitted — never added,
      because anchors resolve to the primary bus
    """
    drawn = diagram_line_sections(model)
    visible: set[str] = {model.source_node}
    for line in model.lines:
        if line.section_id in drawn:
            visible.add(line.from_node)
            visible.add(line.to_node)
    for load in model.loads:
        visible.add(diagram_anchor_node(model, load.node_id))
    for sed in model.seds:
        visible.add(diagram_anchor_node(model, sed.node_id))
    return visible


@dataclass(frozen=True)
class DiagramSymbolLayout:
    """NA205 diagram-unit radii/offsets (same visual weight as reference)."""

    load_radius: float
    sed_radius: float
    source_offset: float
    sed_size: float
    median_segment: float


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


def _diagram_symbol_layout(
    geography: GeographyManifest,
    model: FeederModel,
    map_point,
    *,
    min_segment_m: float = 1.0,
) -> DiagramSymbolLayout:
    """Return NA205 symbol sizes/offsets (not density-adaptive).

    Geographic placement still follows GPS via ``map_point``; only the graphic
    footprint of loads/SEDs/source matches the reference DGS so DigSilent
    schematic and map views keep the same element scale as NA205.
    """
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


def _adaptive_scale(
    meter_xy: dict[str, tuple[float, float]],
    visible_ids: set[str],
    *,
    units_per_meter: float = NA205_DIAGRAM_UNITS_PER_METER,
    max_extent: float = NA205_MAX_DIAGRAM_EXTENT,
) -> float:
    """Uniform geographic scale matching NA205 (Ica zone) sheet footprint.

    Uses the same diagram-units-per-meter as NA205. If a feeder's meter span
    would exceed the NA205 canvas, shrink uniformly so the full network fits.
    """
    ids = list(meter_xy)
    if len(ids) < 2:
        ids = [node_id for node_id in visible_ids if node_id in meter_xy]
    if len(ids) < 2:
        return units_per_meter

    xs = [meter_xy[i][0] for i in ids]
    ys = [meter_xy[i][1] for i in ids]
    span_m = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)
    scale_fit = max_extent / span_m
    return min(units_per_meter, scale_fit)


def _diagram_mapper(
    geography: GeographyManifest,
    visible_ids: set[str],
):
    lats = [p.lat for p in geography.nodes.values()]
    lons = [p.lon for p in geography.nodes.values()]
    origin_lat = sum(lats) / len(lats)
    origin_lon = sum(lons) / len(lons)
    meter_xy = {
        node_id: _geo_to_meters(point, origin_lat, origin_lon)
        for node_id, point in geography.nodes.items()
    }
    scale = _adaptive_scale(meter_xy, visible_ids)

    def map_point(point: GeoPoint) -> tuple[float, float]:
        x_m, y_m = _geo_to_meters(point, origin_lat, origin_lon)
        return x_m * scale, y_m * scale

    return map_point, scale


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


def write_dgs(
    model: FeederModel,
    path: Path | str,
    *,
    schema_profile: str = 'pf21_dgs_1_8_4',
    geography: GeographyManifest | None = None,
) -> DgsManifest:
    schema = load_schema(schema_profile)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    reg = FidRegistry()

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
        key = (
            round(_tr2_strn_mva(sed.design_kva), 9),
            round(model.nominal_kv, 9),
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

    v_phase = model.nominal_kv / math.sqrt(3.0)
    lv_phase = NA205_SED_LV_KV / math.sqrt(3.0)
    for node_id in sorted(model.nodes):
        gp = geography.nodes[node_id] if geography is not None else None
        rows['ElmTerm'].append(_make_row(
            schema, 'ElmTerm', FID=node_fids[node_id], OP='C', loc_name=_loc_name(node_id),
            fold_id=network_fid, typ_id='', systype=0, iUsage=1,
            uknom=model.nominal_kv, unknom=v_phase, iminus=0, outserv=0,
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
            systype=0, iUsage=0, uknom=model.nominal_kv, unknom=v_phase,
            iminus=0, outserv=0,
            GPSlat=gp.lat if gp is not None else '',
            GPSlon=gp.lon if gp is not None else '',
            vtarget=1,
        ))
        rows['ElmTerm'].append(_make_row(
            schema, 'ElmTerm', FID=sed_bt_fids[key], OP='C',
            loc_name=_loc_name(f'{sed.loc_name}_BT'), fold_id=sub_fid, typ_id='',
            systype=0, iUsage=0, uknom=NA205_SED_LV_KV, unknom=lv_phase,
            iminus=0, outserv=0,
            GPSlat=gp.lat if gp is not None else '',
            GPSlon=gp.lon if gp is not None else '',
            vtarget=1,
        ))

    for key in sorted(model.line_types):
        typ = model.line_types[key]
        rated_ka = typ.ampacity_a / 1000.0 if typ.ampacity_a else 0.0
        rows['TypLne'].append(_make_row(
            schema, 'TypLne', FID=type_fids[key], OP='C',
            loc_name=_loc_name(_type_name(key, typ.code)), uline=model.nominal_kv,
            sline=rated_ka, InomAir=rated_ka, cohl_=1 if typ.source_table == 'LINE' else 0,
            rline=typ.r1_ohm_km, xline=typ.x1_ohm_km,
            rline0=typ.r0_ohm_km, xline0=typ.x0_ohm_km,
            Ithr=0, tmax=80, rtemp=75, systp=0, nlnph=3, nneutral=0,
            frnom=60, mlei=_material(typ.code), bline=0, bline0=0,
        ))

    for (strn, utrn_h, utrn_l), fid in sorted(tr2_type_keys.items()):
        # Defaults calibrated to NA205 TypTr2 band (uk≈3–4 %, Dyn5).
        pcutr = max(strn * 10.0, 0.1)  # kW copper; modest vs rated MVA
        rows['TypTr2'].append(_make_row(
            schema, 'TypTr2', FID=fid, OP='C',
            loc_name=_loc_name(f'TR_{format(strn * 1000.0, ".12g")}kVA'),
            nt2ph=3, strn=strn, frnom=60, utrn_h=utrn_h, utrn_l=utrn_l,
            uktr=4.0, pcutr=pcutr, uk0tr=4.0, ur0tr=0,
            tr2cn_h='D', tr2cn_l='YN', nt2ag=5, curmg=0, pfe=max(strn * 1.5, 0.05),
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
        typ_key = (round(strn, 9), round(model.nominal_kv, 9), NA205_SED_LV_KV)
        rows['ElmTr2'].append(_make_row(
            schema, 'ElmTr2', FID=sed_tr_fids[key], OP='C',
            loc_name=_loc_name(f'TR_{sed.loc_name}'), fold_id=sed_fids[key],
            typ_id=tr2_type_keys[typ_key], ntnum=1, outserv=0, nntap=0,
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
        rows['ElmLod'].append(_make_row(
            schema, 'ElmLod', FID=load_fids[key], OP='C', loc_name=_loc_name(name),
            fold_id=fold, typ_id='', mode_inp='PC', slini=apparent,
            plini=load.p_mw, qlini=load.q_mvar, coslini=load.pf,
            pf_recap=0, scale0=1, i_scale=1, outserv=0, classif='',
        ))

    rows['ElmXnet'].append(_make_row(
        schema, 'ElmXnet', FID=source_fid, OP='C', loc_name=_loc_name(f'External Grid {model.name}'),
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

    source_cubic_fid = reg.new()
    rows['StaCubic'].append(_make_row(
        schema, 'StaCubic', FID=source_cubic_fid, OP='C', loc_name=_loc_name(f'Cub_Source_{model.name}'),
        fold_id=node_fids[model.source_node], obj_bus=0, obj_id=source_fid,
        it2p1=0, it2p2=1, it2p3=2,
    ))

    # DigSilent ElmFeeder (NA205): colour/feeder tool anchored on a root StaCubic.
    # Prefer the first outgoing line cubicle at the SOURCE bus; else ElmXnet cubic.
    feeder_cubic_fid = source_cubic_fid
    for line in sorted(model.lines, key=lambda x: x.section_id):
        if line.from_node == model.source_node:
            feeder_cubic_fid = line_cubic_fids[(line.section_id, 0)]
            break
        if line.to_node == model.source_node:
            feeder_cubic_fid = line_cubic_fids[(line.section_id, 1)]
            break
    rows['ElmFeeder'].append(_make_row(
        schema, 'ElmFeeder', FID=reg.new(), OP='C',
        loc_name=_loc_name(model.name),
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
    if geography is not None:
        visible_nodes = visible_pointterm_nodes(model)
        map_point, _scale = _diagram_mapper(geography, visible_nodes)
        node_xy = {node_id: map_point(point) for node_id, point in geography.nodes.items()}
        layout = _diagram_symbol_layout(geography, model, map_point)

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
                iRot=0, rSizeX=NA205_SYMBOL_SIZE, rSizeY=NA205_SYMBOL_SIZE,
            ))

        # Skip micro service-stub d_lin (≤1 m tip→primary). Electrical ElmLne remains;
        # SED/load symbols already snap to the primary via diagram_anchor_node.
        # One d_lin per ElmLne (NA205). Underground style = inAir=0 in DigSilent.
        # True doble circuito (2 SECTION same From↔To) → slight perpendicular offset.
        drawn_line_sections = diagram_line_sections(model)
        circuit_offsets = parallel_circuit_graphic_offsets(
            model, offset_du=PARALLEL_CIRCUIT_OFFSET_DU,
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
                iRot=irot, rSizeX=NA205_SYMBOL_SIZE, rSizeY=NA205_SYMBOL_SIZE,
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

        # Free loads only (no SED): d_load on the sheet. SED-backed loads are
        # modules inside SecSubProd — matching NA205, they get no IntGrf.
        free_load_keys = [key for key in load_keys if key not in nested_load_keys]
        loads_by_anchor: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for key in free_load_keys:
            load = loads_by_key[key]
            loads_by_anchor[diagram_anchor_node(model, load.node_id)].append(key)
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
                    rSizeX=NA205_SYMBOL_SIZE, rSizeY=NA205_SYMBOL_SIZE,
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
            seds_by_anchor[diagram_anchor_node(model, sed.node_id)].append(key)
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

        src_x, src_y = node_xy[model.source_node]
        sx, sy = src_x - layout.source_offset, src_y + layout.source_offset
        src_graph_fid = reg.new(); graphic_fids['source'] = src_graph_fid
        rows['IntGrf'].append(_make_row(
            schema, 'IntGrf', FID=src_graph_fid, OP='C', loc_name=_loc_name(f'G_Source_{model.name}'),
            fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
            rCenterX=sx, rCenterY=sy, sSymNam='d_net', pDataObj=source_fid,
            iRot=0, rSizeX=NA205_SYMBOL_SIZE, rSizeY=NA205_SYMBOL_SIZE,
        ))
        src_con_fid = reg.new()
        rows['IntGrfcon'].append(_make_row(
            schema, 'IntGrfcon', FID=src_con_fid, OP='C', loc_name=_loc_name(f'GCO_Source_{model.name}'),
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
    )
