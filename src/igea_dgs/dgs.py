from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import math

from .model import FeederModel, Sed
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


def visible_pointterm_nodes(model: FeederModel) -> set[str]:
    """Black PointTerm symbols only for topology-relevant buses.

    Rules (aligned with NA205 density ~350–400 on IN111-scale feeders):
    - feeder head / source node
    - real branch nodes (degree >= 3)
    - open stubs (degree 1) without a load
    - maneuver devices only when not a plain degree-2 through node
      ("nodos relevantes de maniobra", not every mid-span switch)
    Hidden (still in ElmTerm electrical model):
    - degree-2 chain nodes (including through switches)
    - terminals whose only role is hosting a load/SED (show d_load / SecSubProd)
    """
    degrees = _node_degrees(model)
    load_nodes = {load.node_id for load in model.loads}
    device_nodes = {device.node_id for device in model.devices}
    visible = {model.source_node}
    for node_id, degree in degrees.items():
        if degree >= 3:
            visible.add(node_id)
            continue
        if degree == 1 and node_id not in load_nodes:
            visible.add(node_id)
            continue
        # Degree-2 through-nodes stay hidden even if a switch sits on the cubicle.
        if degree != 2 and node_id in device_nodes:
            visible.add(node_id)
    return visible


def _geo_to_meters(point: GeoPoint, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    """Local equirectangular meters — preserves X/Y aspect ratio."""
    meters_per_deg_lat = 110540.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(origin_lat))
    x = (point.lon - origin_lon) * meters_per_deg_lon
    y = (point.lat - origin_lat) * meters_per_deg_lat
    return x, y


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def _adaptive_scale(
    meter_xy: dict[str, tuple[float, float]],
    visible_ids: set[str],
    *,
    target_spacing: float = 120.0,
) -> float:
    """Uniform scale from visible-node density (diagram units per meter)."""
    ids = [node_id for node_id in visible_ids if node_id in meter_xy]
    if len(ids) < 2:
        ids = list(meter_xy)
    if len(ids) < 2:
        return 1.0

    # Median nearest-neighbour distance among visible (or all) nodes.
    nearest: list[float] = []
    sample = ids if len(ids) <= 800 else ids[:: max(1, len(ids) // 800)]
    for i, node_id in enumerate(sample):
        x0, y0 = meter_xy[node_id]
        best = float('inf')
        for j, other_id in enumerate(sample):
            if i == j:
                continue
            x1, y1 = meter_xy[other_id]
            dist = math.hypot(x1 - x0, y1 - y0)
            if dist < best:
                best = dist
        if math.isfinite(best) and best > 1e-6:
            nearest.append(best)

    median_nn = _median(nearest)
    if median_nn <= 1e-9:
        # Fallback: fit span into a readable canvas while keeping aspect ratio.
        xs = [meter_xy[i][0] for i in ids]
        ys = [meter_xy[i][1] for i in ids]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
        return 20000.0 / span

    scale = target_spacing / median_nn
    # Keep short GIS segments from collapsing without exploding huge feeders.
    return min(max(scale, 0.05), 50.0)


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
    for node_id in sorted(model.nodes):
        gp = geography.nodes[node_id] if geography is not None else None
        rows['ElmTerm'].append(_make_row(
            schema, 'ElmTerm', FID=node_fids[node_id], OP='C', loc_name=_loc_name(node_id),
            fold_id=network_fid, typ_id='', systype=0, iUsage=1,
            uknom=model.nominal_kv, unknom=v_phase, iminus=0, outserv=0,
            GPSlat=gp.lat if gp is not None else '', GPSlon=gp.lon if gp is not None else '', vtarget=1,
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

    for line in sorted(model.lines, key=lambda x: x.section_id):
        rows['ElmLne'].append(_make_row(
            schema, 'ElmLne', FID=line_fids[line.section_id], OP='C',
            loc_name=_loc_name(line.section_id), fold_id=network_fid,
            typ_id=type_fids[line.type_key], dline=line.length_km, fline=1,
            GPScoords='', nlnum=1, inAir=1 if line.overhead else 0,
        ))

    loads_by_key = {(x.section_id, x.device_number): x for x in model.loads}
    for key in load_keys:
        load = loads_by_key[key]
        apparent = math.hypot(load.p_mw, load.q_mvar)
        name = load.display_name or load.customer_number or load.device_number or load.section_id
        rows['ElmLod'].append(_make_row(
            schema, 'ElmLod', FID=load_fids[key], OP='C', loc_name=_loc_name(name),
            fold_id=network_fid, typ_id='', mode_inp='PC', slini=apparent,
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
        rows['StaCubic'].append(_make_row(
            schema, 'StaCubic', FID=cubic_fid, OP='C',
            loc_name=_loc_name(f'Cub_{load.device_number}'), fold_id=node_fids[load.node_id],
            obj_bus=0, obj_id=load_fids[key], it2p1=0, it2p2=1, it2p3=2,
        ))

    source_cubic_fid = reg.new()
    rows['StaCubic'].append(_make_row(
        schema, 'StaCubic', FID=source_cubic_fid, OP='C', loc_name=_loc_name(f'Cub_Source_{model.name}'),
        fold_id=node_fids[model.source_node], obj_bus=0, obj_id=source_fid,
        it2p1=0, it2p2=1, it2p3=2,
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
                iRot=0, rSizeX=1, rSizeY=1,
            ))

        for line in sorted(model.lines, key=lambda x: x.section_id):
            gline = geography.lines[line.section_id]
            xy_path = [map_point(point) for point in gline.path]
            if len(xy_path) == 2:
                center = ((xy_path[0][0] + xy_path[1][0]) / 2, (xy_path[0][1] + xy_path[1][1]) / 2)
                augmented = [xy_path[0], center, xy_path[1]]
            else:
                augmented = xy_path
                mid = len(augmented) // 2
                center = augmented[mid]
            fid = reg.new(); graphic_fids[f'line:{line.section_id}'] = fid
            irot = _line_irot(augmented)
            rows['IntGrf'].append(_make_row(
                schema, 'IntGrf', FID=fid, OP='C', loc_name=_loc_name(f'G_{line.section_id}'),
                fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
                rCenterX=center[0], rCenterY=center[1], sSymNam='d_lin', pDataObj=line_fids[line.section_id],
                iRot=irot, rSizeX=1, rSizeY=1,
            ))
            mid = len(augmented) // 2
            left = list(reversed(augmented[:mid + 1]))
            right = augmented[mid:]
            for con_nr, con_points in ((0, left), (1, right)):
                con_fid = reg.new()
                rows['IntGrfcon'].append(_make_row(
                    schema, 'IntGrfcon', FID=con_fid, OP='C',
                    loc_name=_loc_name(f'GCO_{con_nr + 1}_{line.section_id}'),
                    fold_id=fid, iDatConNr=con_nr, **_connector_values(con_points),
                ))

        # Loads: radial around shared node (NA205 d_load).
        loads_by_node: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for key in load_keys:
            loads_by_node[loads_by_key[key].node_id].append(key)
        for node_id, keys in loads_by_node.items():
            node_x, node_y = node_xy[node_id]
            offsets = _radial_offsets(len(keys), radius=55.0)
            for key, (dx, dy) in zip(keys, offsets):
                load = loads_by_key[key]
                x, y = node_x + dx, node_y + dy
                fid = reg.new(); graphic_fids[f'load:{key[0]}:{key[1]}'] = fid
                rows['IntGrf'].append(_make_row(
                    schema, 'IntGrf', FID=fid, OP='C', loc_name=_loc_name(f'G_{load.display_name or load.device_number}'),
                    fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
                    rCenterX=x, rCenterY=y, sSymNam='d_load', pDataObj=load_fids[key],
                    iRot=int(round(math.degrees(math.atan2(dy, dx)))) % 360,
                    rSizeX=1, rSizeY=1,
                ))
                con_fid = reg.new()
                rows['IntGrfcon'].append(_make_row(
                    schema, 'IntGrfcon', FID=con_fid, OP='C',
                    loc_name=_loc_name(f'GCO_{load.device_number}'), fold_id=fid,
                    iDatConNr=0, **_connector_values([(x, y), (node_x, node_y)]),
                ))

        # SEDs identifiable from TXT → SecSubProd (do not invent otherwise).
        seds_by_node: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for key in sed_keys:
            seds_by_node[seds_by_key[key].node_id].append(key)
        for node_id, keys in seds_by_node.items():
            node_x, node_y = node_xy[node_id]
            # Place SED symbols on a smaller ring so they sit near the bus/load.
            offsets = _radial_offsets(len(keys), radius=28.0)
            for key, (dx, dy) in zip(keys, offsets):
                sed = seds_by_key[key]
                x, y = node_x + dx, node_y + dy
                fid = reg.new(); graphic_fids[f'sed:{key[0]}:{key[1]}'] = fid
                rows['IntGrf'].append(_make_row(
                    schema, 'IntGrf', FID=fid, OP='C', loc_name=_loc_name(f'gnoT {sed.loc_name}'),
                    fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
                    rCenterX=x, rCenterY=y, sSymNam='SecSubProd', pDataObj=sed_fids[key],
                    iRot=0, rSizeX=5, rSizeY=5,
                ))

        src_x, src_y = node_xy[model.source_node]
        sx, sy = src_x - 80.0, src_y + 80.0
        src_graph_fid = reg.new(); graphic_fids['source'] = src_graph_fid
        rows['IntGrf'].append(_make_row(
            schema, 'IntGrf', FID=src_graph_fid, OP='C', loc_name=_loc_name(f'G_Source_{model.name}'),
            fold_id=diagram_fid, iCol=1, iVis=1, iLevel=1,
            rCenterX=sx, rCenterY=sy, sSymNam='d_net', pDataObj=source_fid,
            iRot=0, rSizeX=1, rSizeY=1,
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
    used_tables = {'General', 'ElmNet', 'ElmTerm', 'TypLne', 'ElmLne', 'ElmLod', 'ElmXnet', 'StaCubic', 'StaSwitch'}
    if sed_keys:
        used_tables.add('ElmSubstat')
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
