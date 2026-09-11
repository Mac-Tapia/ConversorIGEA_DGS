from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import math

from .model import FeederModel
from .schema import load_schema
from .geography import GeographyManifest


def parse_dgs(path: Path | str) -> dict[str, dict]:
    tables: dict[str, dict] = {}
    current: str | None = None
    with Path(path).open('r', encoding='utf-8', errors='replace') as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith('$$'):
                parts = line[2:].split(';')
                current = parts[0]
                fields = [part.split('(')[0].replace(':MATRIX', '') for part in parts[1:]]
                tables[current] = {
                    'header': line,
                    'fields': fields,
                    'rows': [],
                    'rows_dict': [],
                }
                continue
            if current and line and not line.startswith('*'):
                values = line.split(';')
                tables[current]['rows'].append(values)
                tables[current]['rows_dict'].append(dict(zip(tables[current]['fields'], values)))
    return tables


def _total_fids(tables: dict[str, dict]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for name, table in tables.items():
        if 'FID' not in table['fields']:
            continue
        idx = table['fields'].index('FID')
        for row in table['rows']:
            if idx < len(row):
                result.append((row[idx], name))
    return result


def _loc(value: str) -> str:
    return value.replace(';', ',').replace('\n', ' ').replace('\r', ' ')[:40]


def _finite_float(value: str | None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def validate_dgs(
    model: FeederModel,
    dgs_path: Path | str,
    *,
    schema_profile: str = 'pf21_dgs_1_8_4',
    geography: GeographyManifest | None = None,
) -> dict:
    schema = load_schema(schema_profile)
    tables = parse_dgs(dgs_path)
    schema_errors: list[str] = []
    structural_errors: list[str] = []
    connection_errors: list[str] = []
    geographic_errors: list[str] = []
    graphic_errors: list[str] = []

    required = ['General','ElmNet','ElmTerm','TypLne','ElmLne','ElmLod','ElmXnet','StaCubic','StaSwitch']
    if geography is not None:
        required += ['IntGrf','IntGrfcon','IntGrfnet']

    for name in required:
        if name not in tables:
            schema_errors.append(f'Missing required DGS table: {name}')
            continue
        if tables[name]['header'] != schema.header(name):
            schema_errors.append(f'{name}: header does not match schema profile {schema.profile}')

    for name, table in tables.items():
        expected = len(table['fields'])
        for n, row in enumerate(table['rows'], start=1):
            if len(row) != expected:
                structural_errors.append(f'{name} row {n}: {len(row)} fields, expected {expected}')

    fid_pairs = _total_fids(tables)
    fid_counts = Counter(fid for fid, _ in fid_pairs if fid)
    for fid, count in sorted(fid_counts.items()):
        if count > 1:
            owners = [name for value, name in fid_pairs if value == fid]
            structural_errors.append(f'duplicate FID {fid}: {owners}')

    if schema_errors:
        return _report(model, tables, schema, schema_errors, structural_errors, connection_errors,
                       geographic_errors, graphic_errors, geography=geography)

    net_rows = tables['ElmNet']['rows_dict']
    if len(net_rows) != 1:
        structural_errors.append(f'ElmNet rows={len(net_rows)}, expected 1')
    network_fids = {r.get('FID','') for r in net_rows}
    term_rows = tables['ElmTerm']['rows_dict']
    type_rows = tables['TypLne']['rows_dict']
    line_rows = tables['ElmLne']['rows_dict']
    load_rows = tables['ElmLod']['rows_dict']
    source_rows = tables['ElmXnet']['rows_dict']
    cubic_rows = tables['StaCubic']['rows_dict']
    switch_rows = tables['StaSwitch']['rows_dict']

    if len(term_rows) != len(model.nodes) + 2 * len(model.seds):
        structural_errors.append(
            f'ElmTerm count {len(term_rows)} != source nodes {len(model.nodes)} '
            f'+ 2×SED buses {2 * len(model.seds)}'
        )
    if len(type_rows) != len(model.line_types):
        structural_errors.append(f'TypLne count {len(type_rows)} != source line types {len(model.line_types)}')
    if len(line_rows) != len(model.lines):
        structural_errors.append(f'ElmLne count {len(line_rows)} != source lines {len(model.lines)}')
    if len(load_rows) != len(model.loads):
        structural_errors.append(f'ElmLod count {len(load_rows)} != source loads {len(model.loads)}')
    if len(source_rows) != 1:
        structural_errors.append(f'ElmXnet count {len(source_rows)} != expected 1')
    if len(switch_rows) != len(model.devices):
        structural_errors.append(f'StaSwitch count {len(switch_rows)} != source devices {len(model.devices)}')

    substat_rows = tables.get('ElmSubstat', {}).get('rows_dict', [])
    if len(substat_rows) != len(model.seds):
        structural_errors.append(f'ElmSubstat count {len(substat_rows)} != source SEDs {len(model.seds)}')
    tr2_rows = tables.get('ElmTr2', {}).get('rows_dict', [])
    coup_rows = tables.get('ElmCoup', {}).get('rows_dict', [])
    if len(tr2_rows) != len(model.seds):
        structural_errors.append(f'ElmTr2 count {len(tr2_rows)} != source SEDs {len(model.seds)}')
    if len(coup_rows) != len(model.seds):
        structural_errors.append(f'ElmCoup count {len(coup_rows)} != source SEDs {len(model.seds)}')

    term_fids = {r.get('FID','') for r in term_rows}
    type_fids = {r.get('FID','') for r in type_rows}
    line_fids = {r.get('FID','') for r in line_rows}
    load_fids = {r.get('FID','') for r in load_rows}
    source_fids = {r.get('FID','') for r in source_rows}
    sed_fids = {r.get('FID','') for r in substat_rows}
    cubic_fids = {r.get('FID','') for r in cubic_rows}

    for cls, rows in (('ElmLne', line_rows), ('ElmXnet', source_rows), ('ElmSubstat', substat_rows)):
        for r in rows:
            if r.get('fold_id', '') not in network_fids:
                connection_errors.append(f'{cls} {r.get("FID")} references missing ElmNet {r.get("fold_id")}')
    # Feeder buses under ElmNet; SED MT/BT buses under ElmSubstat (NA205 triangle interior).
    allowed_term_folds = network_fids | sed_fids
    for r in term_rows:
        if r.get('fold_id', '') not in allowed_term_folds:
            connection_errors.append(f'ElmTerm {r.get("FID")} fold_id {r.get("fold_id")} not ElmNet/ElmSubstat')
    for r in tr2_rows:
        if r.get('fold_id', '') not in sed_fids:
            connection_errors.append(f'ElmTr2 {r.get("FID")} must fold under ElmSubstat')
    for r in coup_rows:
        if r.get('fold_id', '') not in sed_fids:
            connection_errors.append(f'ElmCoup {r.get("FID")} must fold under ElmSubstat')

    # NA205: SED-backed loads fold under ElmSubstat; free loads stay under ElmNet.
    allowed_load_folds = network_fids | sed_fids
    for r in load_rows:
        fold = r.get('fold_id', '')
        if fold not in allowed_load_folds:
            connection_errors.append(f'ElmLod {r.get("FID")} fold_id {fold} is not ElmNet/ElmSubstat')

    for r in line_rows:
        if r.get('typ_id','') not in type_fids:
            connection_errors.append(f'ElmLne {r.get("FID")} references missing TypLne {r.get("typ_id")}')

    tr2_fids = {r.get('FID', '') for r in tr2_rows}
    coup_fids = {r.get('FID', '') for r in coup_rows}
    valid_objects = line_fids | load_fids | source_fids | tr2_fids | coup_fids
    obj_cubics: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in cubic_rows:
        if r.get('fold_id','') not in term_fids:
            connection_errors.append(f'StaCubic {r.get("FID")} references missing ElmTerm {r.get("fold_id")}')
        if r.get('obj_id','') not in valid_objects:
            connection_errors.append(f'StaCubic {r.get("FID")} references missing object {r.get("obj_id")}')
        obj_cubics[r.get('obj_id','')].append(r)

    for fid in sorted(line_fids):
        cubs = obj_cubics.get(fid, [])
        if len(cubs) != 2:
            connection_errors.append(f'ElmLne {fid} has {len(cubs)} cubicles, expected 2')
        elif {c.get('obj_bus') for c in cubs} != {'0','1'}:
            connection_errors.append(f'ElmLne {fid} cubicles must use obj_bus 0 and 1')
    for fid in sorted(tr2_fids | coup_fids):
        cubs = obj_cubics.get(fid, [])
        if len(cubs) != 2:
            connection_errors.append(f'SED branch {fid} has {len(cubs)} cubicles, expected 2')
        elif {c.get('obj_bus') for c in cubs} != {'0', '1'}:
            connection_errors.append(f'SED branch {fid} cubicles must use obj_bus 0 and 1')
    for fid in sorted(load_fids):
        if len(obj_cubics.get(fid, [])) != 1:
            connection_errors.append(f'ElmLod {fid} has {len(obj_cubics.get(fid, []))} cubicles, expected 1')
    for fid in sorted(source_fids):
        if len(obj_cubics.get(fid, [])) != 1:
            connection_errors.append(f'ElmXnet {fid} has {len(obj_cubics.get(fid, []))} cubicles, expected 1')

    for r in switch_rows:
        if r.get('fold_id','') not in cubic_fids:
            connection_errors.append(f'StaSwitch {r.get("FID")} fold_id {r.get("fold_id")} is not a StaCubic')
        if r.get('on_off','') not in {'0','1'}:
            structural_errors.append(f'StaSwitch {r.get("FID")} invalid on_off={r.get("on_off")!r}')

    term_by_name = {r.get('loc_name',''): r for r in term_rows}
    line_by_name = {r.get('loc_name',''): r for r in line_rows}
    for line in model.lines:
        drow = line_by_name.get(_loc(line.section_id))
        if drow is None:
            connection_errors.append(f'{line.section_id}: no matching ElmLne by loc_name')
            continue
        cubs = obj_cubics.get(drow.get('FID',''), [])
        by_bus = {c.get('obj_bus'): c for c in cubs}
        expected_from = term_by_name.get(_loc(line.from_node), {}).get('FID')
        expected_to = term_by_name.get(_loc(line.to_node), {}).get('FID')
        if by_bus.get('0', {}).get('fold_id') != expected_from:
            connection_errors.append(f'{line.section_id}: FromNode cubicle does not reference {line.from_node}')
        if by_bus.get('1', {}).get('fold_id') != expected_to:
            connection_errors.append(f'{line.section_id}: ToNode cubicle does not reference {line.to_node}')

    load_by_name = {r.get('loc_name',''): r for r in load_rows}
    sed_by_name = {r.get('loc_name', ''): r for r in substat_rows}
    nested_load_keys = {sed.load_key for sed in model.seds}
    # Internal SED buses grouped by parent ElmSubstat.
    terms_by_fold: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in term_rows:
        terms_by_fold[r.get('fold_id', '')].append(r)

    def _finite_uknom(row: dict[str, str]) -> float | None:
        try:
            value = float(row.get('uknom') or '')
        except ValueError:
            return None
        return value if math.isfinite(value) else None

    for load in model.loads:
        name = _loc(load.display_name or load.customer_number or load.device_number or load.section_id)
        drow = load_by_name.get(name)
        if drow is None:
            connection_errors.append(f'{load.device_number}: no matching ElmLod by loc_name')
            continue
        cubs = obj_cubics.get(drow.get('FID',''), [])
        load_key = (load.section_id, load.device_number)
        if load_key in nested_load_keys:
            sed = next(s for s in model.seds if s.load_key == load_key)
            expected_sed = sed_by_name.get(_loc(sed.loc_name))
            if expected_sed is None or drow.get('fold_id') != expected_sed.get('FID'):
                connection_errors.append(
                    f'{load.device_number}: SED load must fold under its ElmSubstat (NA205 triangle module)'
                )
                continue
            # Load cubicle must sit on the internal BT bus (uknom ≈ 0.22 kV).
            bt_terms = [
                t for t in terms_by_fold.get(expected_sed.get('FID', ''), [])
                if (u := _finite_uknom(t)) is not None and u < 1.0
            ]
            bt_fids = {t.get('FID', '') for t in bt_terms}
            if not bt_fids:
                connection_errors.append(f'{sed.code}: ElmSubstat missing BT ElmTerm (uknom<1)')
            elif not cubs or cubs[0].get('fold_id') not in bt_fids:
                connection_errors.append(
                    f'{sed.code}: SED load must connect to internal BT bus (NA205 SE_*_2)'
                )
        else:
            expected_term = term_by_name.get(_loc(load.node_id), {}).get('FID')
            if len(cubs) == 1 and cubs[0].get('fold_id') != expected_term:
                connection_errors.append(
                    f'{load.device_number}: load cubicle does not reference selected node {load.node_id}'
                )
            if drow.get('fold_id') not in network_fids:
                connection_errors.append(f'{load.device_number}: free load must fold under ElmNet')

    tr2_by_fold = {r.get('fold_id', ''): r for r in tr2_rows}
    for sed in model.seds:
        drow = sed_by_name.get(_loc(sed.loc_name))
        if drow is None:
            connection_errors.append(f'{sed.code}: no matching ElmSubstat by loc_name')
            continue
        sub_fid = drow.get('FID', '')
        load = next(
            (item for item in model.loads if (item.section_id, item.device_number) == sed.load_key),
            None,
        )
        if load is None:
            connection_errors.append(f'{sed.code}: missing nested load for SED electrical connection')
            continue
        if load.node_id != sed.node_id:
            connection_errors.append(
                f'{sed.code}: SED node {sed.node_id} differs from load node {load.node_id} (TXT Location)'
            )
            continue
        if sub_fid not in tr2_by_fold:
            connection_errors.append(f'{sed.code}: ElmSubstat missing ElmTr2 (NA205 TR_*)')
        kids = terms_by_fold.get(sub_fid, [])
        mt_terms = [t for t in kids if (u := _finite_uknom(t)) is not None and u >= 1.0]
        bt_terms = [t for t in kids if (u := _finite_uknom(t)) is not None and u < 1.0]
        if len(mt_terms) < 1:
            connection_errors.append(f'{sed.code}: ElmSubstat missing MT ElmTerm')
        if len(bt_terms) < 1:
            connection_errors.append(f'{sed.code}: ElmSubstat missing BT ElmTerm')
        # Coupler must bridge feeder TXT node ↔ internal MT bus.
        expected_feeder = term_by_name.get(_loc(sed.node_id), {}).get('FID')
        mt_fids = {t.get('FID', '') for t in mt_terms}
        linked = False
        for coup in coup_rows:
            if coup.get('fold_id') != sub_fid:
                continue
            cubs = obj_cubics.get(coup.get('FID', ''), [])
            folds = {c.get('fold_id') for c in cubs}
            if expected_feeder in folds and folds & mt_fids:
                linked = True
                break
        if not linked:
            connection_errors.append(
                f'{sed.code}: missing ElmCoup between feeder node {sed.node_id} and MT bus'
            )

    source_length = sum(x.length_km for x in model.lines)
    try:
        dgs_length = sum(float(r.get('dline') or 0.0) for r in line_rows)
    except ValueError:
        dgs_length = float('nan')
        structural_errors.append('ElmLne contains non-numeric dline')
    if math.isfinite(dgs_length) and not math.isclose(source_length, dgs_length, rel_tol=1e-10, abs_tol=1e-9):
        structural_errors.append(f'Line length total mismatch: source={source_length:.12g} km dgs={dgs_length:.12g} km')

    if geography is not None:
        # Geographic coverage and GPS equality.
        if set(geography.nodes) != set(model.nodes):
            geographic_errors.append('Geographic node set differs from electrical model')
        if set(geography.lines) != {x.section_id for x in model.lines}:
            geographic_errors.append('Geographic line set differs from electrical model')
        for node_id, gp in geography.nodes.items():
            row = term_by_name.get(_loc(node_id))
            if row is None:
                geographic_errors.append(f'{node_id}: no ElmTerm for GPS validation')
                continue
            lat = _finite_float(row.get('GPSlat'))
            lon = _finite_float(row.get('GPSlon'))
            if lat is None or lon is None:
                geographic_errors.append(f'{node_id}: missing/non-numeric GPSlat/GPSlon')
                continue
            if not (math.isclose(lat, gp.lat, rel_tol=0.0, abs_tol=1e-8) and math.isclose(lon, gp.lon, rel_tol=0.0, abs_tol=1e-8)):
                geographic_errors.append(f'{node_id}: DGS GPS does not match transformed source coordinate')

        for line in model.lines:
            gline = geography.lines.get(line.section_id)
            if gline is None:
                geographic_errors.append(f'{line.section_id}: missing geographic path for MT section')
                continue
            if gline.from_node != line.from_node or gline.to_node != line.to_node:
                geographic_errors.append(
                    f'{line.section_id}: geography From/To ({gline.from_node}->{gline.to_node}) '
                    f'differs from electrical ({line.from_node}->{line.to_node})'
                )
            if not gline.path:
                geographic_errors.append(f'{line.section_id}: empty geographic path')
            else:
                if gline.path[0] != geography.nodes.get(line.from_node):
                    geographic_errors.append(f'{line.section_id}: path does not start at georeferenced FromNode')
                if gline.path[-1] != geography.nodes.get(line.to_node):
                    geographic_errors.append(f'{line.section_id}: path does not end at georeferenced ToNode')

        for sed in model.seds:
            gp = geography.nodes.get(sed.node_id)
            drow = sed_by_name.get(_loc(sed.loc_name))
            if gp is None:
                geographic_errors.append(f'{sed.code}: SED node {sed.node_id} missing from geography')
                continue
            if drow is None:
                continue
            lat = _finite_float(drow.get('GPSlat'))
            lon = _finite_float(drow.get('GPSlon'))
            if lat is None or lon is None:
                geographic_errors.append(f'{sed.code}: ElmSubstat missing GPSlat/GPSlon for node {sed.node_id}')
            elif not (math.isclose(lat, gp.lat, rel_tol=0.0, abs_tol=1e-8) and math.isclose(lon, gp.lon, rel_tol=0.0, abs_tol=1e-8)):
                geographic_errors.append(
                    f'{sed.code}: ElmSubstat GPS does not match georeferenced node {sed.node_id}'
                )

        # Graphic layer integrity.
        diagram_rows = tables.get('IntGrfnet', {}).get('rows_dict', [])
        graphic_rows = tables.get('IntGrf', {}).get('rows_dict', [])
        con_rows = tables.get('IntGrfcon', {}).get('rows_dict', [])
        if len(diagram_rows) != 1:
            graphic_errors.append(f'IntGrfnet rows={len(diagram_rows)}, expected 1')
        diagram_fid = diagram_rows[0].get('FID','') if diagram_rows else ''
        if net_rows and net_rows[0].get('pDiagram','') != diagram_fid:
            graphic_errors.append('ElmNet.pDiagram does not reference the generated IntGrfnet')

        from .dgs import diagram_anchor_node, diagram_line_sections, visible_pointterm_nodes

        visible_nodes = visible_pointterm_nodes(model)
        for load in model.loads:
            visible_nodes.add(diagram_anchor_node(model, load.node_id))
        for sed in model.seds:
            visible_nodes.add(diagram_anchor_node(model, sed.node_id))
        visible_term_fids = {
            r.get('FID', '') for r in term_rows if r.get('loc_name', '') in {_loc(n) for n in visible_nodes}
        }
        nested_load_fids = {
            load_by_name[_loc(load.display_name or load.customer_number or load.device_number or load.section_id)].get('FID', '')
            for load in model.loads
            if (load.section_id, load.device_number) in nested_load_keys
            and _loc(load.display_name or load.customer_number or load.device_number or load.section_id) in load_by_name
        }
        free_load_fids = load_fids - nested_load_fids
        drawn_sections = diagram_line_sections(model)
        line_by_name = {r.get('loc_name', ''): r for r in line_rows}
        diagram_line_fids = {
            line_by_name[_loc(sid)].get('FID', '')
            for sid in drawn_sections
            if _loc(sid) in line_by_name
        }
        hidden_stub_line_fids = line_fids - diagram_line_fids
        electrical_graphic_objects = visible_term_fids | diagram_line_fids | free_load_fids | source_fids | sed_fids
        graphics_by_object: dict[str, list[dict[str, str]]] = defaultdict(list)
        graphic_fids = {r.get('FID','') for r in graphic_rows}
        symbol_counts: Counter[str] = Counter()
        for r in graphic_rows:
            symbol_counts[r.get('sSymNam', '')] += 1
            if r.get('fold_id','') != diagram_fid:
                graphic_errors.append(f'IntGrf {r.get("FID")} fold_id does not reference diagram')
            if r.get('pDataObj','') not in electrical_graphic_objects:
                graphic_errors.append(f'IntGrf {r.get("FID")} references missing electrical object {r.get("pDataObj")}')
            graphics_by_object[r.get('pDataObj','')].append(r)
        expected_graphics = (
            len(visible_term_fids) + len(diagram_line_fids) + len(free_load_fids)
            + len(source_fids) + len(sed_fids)
        )
        if len(graphic_rows) != expected_graphics:
            graphic_errors.append(f'IntGrf count {len(graphic_rows)} != expected {expected_graphics}')
        if symbol_counts.get('PointTerm', 0) != len(visible_term_fids):
            graphic_errors.append(
                f'PointTerm count {symbol_counts.get("PointTerm", 0)} != visible nodes {len(visible_term_fids)}'
            )
        for fid in diagram_line_fids | free_load_fids | source_fids | sed_fids | visible_term_fids:
            if len(graphics_by_object.get(fid, [])) != 1:
                graphic_errors.append(f'Electrical object {fid} has {len(graphics_by_object.get(fid, []))} graphic objects, expected 1')
        for fid in hidden_stub_line_fids:
            if graphics_by_object.get(fid):
                graphic_errors.append(
                    f'Micro service-stub ElmLne {fid} must not have IntGrf d_lin (electrical-only)'
                )
        for fid in nested_load_fids:
            if graphics_by_object.get(fid):
                graphic_errors.append(f'Nested SED ElmLod {fid} must not have its own IntGrf (module inside triangle)')
        # Degree-2 / load-only terminals must not get a PointTerm.
        for fid in term_fids - visible_term_fids:
            if graphics_by_object.get(fid):
                graphic_errors.append(f'Hidden ElmTerm {fid} unexpectedly has IntGrf PointTerm')

        connectors_by_graphic: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in con_rows:
            if r.get('fold_id','') not in graphic_fids:
                graphic_errors.append(f'IntGrfcon {r.get("FID")} parent {r.get("fold_id")} is not an IntGrf')
            connectors_by_graphic[r.get('fold_id','')].append(r)
        for fid in diagram_line_fids:
            gr = graphics_by_object.get(fid, [])
            if gr and len(connectors_by_graphic.get(gr[0].get('FID',''), [])) != 2:
                graphic_errors.append(f'ElmLne graphic for {fid} does not have exactly two IntGrfcon rows')
            if gr and gr[0].get('sSymNam') != 'd_lin':
                graphic_errors.append(f'ElmLne graphic for {fid} must use sSymNam=d_lin')
        for fid in free_load_fids | source_fids:
            gr = graphics_by_object.get(fid, [])
            if gr and len(connectors_by_graphic.get(gr[0].get('FID',''), [])) != 1:
                graphic_errors.append(f'Load/source graphic for {fid} does not have exactly one IntGrfcon row')
            if fid in free_load_fids and gr and gr[0].get('sSymNam') != 'd_load':
                graphic_errors.append(f'ElmLod graphic for {fid} must use sSymNam=d_load')
            if fid in source_fids and gr and gr[0].get('sSymNam') != 'd_net':
                graphic_errors.append(f'ElmXnet graphic for {fid} must use sSymNam=d_net')
        for fid in sed_fids:
            gr = graphics_by_object.get(fid, [])
            if gr and gr[0].get('sSymNam') != 'SecSubProd':
                graphic_errors.append(f'ElmSubstat graphic for {fid} must use sSymNam=SecSubProd')
            if gr and connectors_by_graphic.get(gr[0].get('FID', '')):
                graphic_errors.append(f'ElmSubstat graphic for {fid} unexpectedly owns IntGrfcon rows')
        for fid in visible_term_fids:
            gr = graphics_by_object.get(fid, [])
            if gr and connectors_by_graphic.get(gr[0].get('FID','')):
                graphic_errors.append(f'ElmTerm graphic for {fid} unexpectedly owns IntGrfcon rows')
            if gr and gr[0].get('sSymNam') != 'PointTerm':
                graphic_errors.append(f'Visible ElmTerm graphic for {fid} must use sSymNam=PointTerm')

    return _report(model, tables, schema, schema_errors, structural_errors, connection_errors,
                   geographic_errors, graphic_errors, geography=geography, dgs_length=dgs_length)


def _report(
    model: FeederModel,
    tables: dict[str, dict],
    schema,
    schema_errors: list[str],
    structural_errors: list[str],
    connection_errors: list[str],
    geographic_errors: list[str],
    graphic_errors: list[str],
    *,
    geography: GeographyManifest | None = None,
    dgs_length: float | None = None,
) -> dict:
    count = lambda table: len(tables.get(table, {}).get('rows', []))
    source_length = sum(x.length_km for x in model.lines)
    if dgs_length is None:
        try:
            dgs_length = sum(float(r.get('dline') or 0.0) for r in tables.get('ElmLne', {}).get('rows_dict', []))
        except ValueError:
            dgs_length = float('nan')
    warnings = list(model.warnings)
    warnings.extend([
        'CYMDIST B1/B0 are retained in the source model but are not transferred to TypLne bline/bline0 until unit equivalence is independently established.',
        'SOURCE short-circuit strength/impedance is not present in the supplied TXT data; ElmXnet short-circuit fields are left unspecified.',
        'PowerFactory import/execution cannot be proven by static validation; generated DGS still requires an import test in the target installation.',
    ])
    if geography is not None:
        warnings.append('Full IGEA line geometry is retained in the geography sidecar; DGS IntGrfcon reduces each connector polyline to a maximum of four points imposed by this schema profile.')
    errors_total = len(schema_errors) + len(structural_errors) + len(connection_errors) + len(geographic_errors) + len(graphic_errors)
    return {
        'feeder': model.name,
        'network_id': model.network_id,
        'nominal_kv': model.nominal_kv,
        'schema_profile': schema.profile,
        'schema_errors': schema_errors,
        'structural_errors': structural_errors,
        'connection_errors': connection_errors,
        'geographic_errors': geographic_errors,
        'graphic_errors': graphic_errors,
        'errors_total': errors_total,
        'warnings': warnings,
        'counts': {
            'source_nodes': len(model.nodes),
            'dgs_nodes': count('ElmTerm'),
            'source_line_types': len(model.line_types),
            'dgs_line_types': count('TypLne'),
            'source_lines': len(model.lines),
            'dgs_lines': count('ElmLne'),
            'source_loads': len(model.loads),
            'dgs_loads': count('ElmLod'),
            'source_devices': len(model.devices),
            'dgs_switches': count('StaSwitch'),
            'dgs_cubicles': count('StaCubic'),
            'dgs_sources': count('ElmXnet'),
            'dgs_seds': count('ElmSubstat'),
            'source_seds': len(model.seds),
            'dgs_diagrams': count('IntGrfnet'),
            'dgs_graphics': count('IntGrf'),
            'dgs_graphic_connections': count('IntGrfcon'),
            'dgs_pointterms': sum(
                1 for r in tables.get('IntGrf', {}).get('rows_dict', [])
                if r.get('sSymNam') == 'PointTerm'
            ),
            'geographic_intermediate_points': geography.intermediate_point_count if geography is not None else 0,
        },
        'length_km': {
            'source': source_length,
            'dgs': dgs_length,
            'difference': dgs_length - source_length if isinstance(dgs_length, float) and math.isfinite(dgs_length) else None,
            'georef_lines': sum(1 for line in model.lines if getattr(line, 'length_source', 'txt') == 'georef'),
            'txt_lines': sum(1 for line in model.lines if getattr(line, 'length_source', 'txt') != 'georef'),
        },
        'load_totals': {
            'p_mw': sum(x.p_mw for x in model.loads),
            'q_mvar': sum(x.q_mvar for x in model.loads),
            'connected_kva': sum(x.connected_kva for x in model.loads),
            'kwh': sum(x.kwh for x in model.loads),
        },
        'line_type_aliases': dict(model.line_type_aliases),
        'unresolved_line_types': sorted(model.unresolved_line_types),
        'runtime_reference_dependency': False,
        'powerfactory_import_tested': False,
        'source_crs': geography.source_crs if geography is not None else None,
        'target_crs': geography.target_crs if geography is not None else None,
    }


def write_validation_reports(report: dict, json_path: Path | str, txt_path: Path | str) -> None:
    json_path = Path(json_path)
    txt_path = Path(txt_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    c = report.get('counts', {})
    length = report.get('length_km', {})
    lines = [
        f"FEEDER VALIDATION: {report.get('feeder','')}",
        '=' * 72,
        f"Network ID: {report.get('network_id','')}",
        f"Nominal voltage: {report.get('nominal_kv','')} kV",
        f"DGS schema: {report.get('schema_profile','')}",
        f"Runtime reference DGS dependency: {report.get('runtime_reference_dependency')}",
        f"PowerFactory import tested: {report.get('powerfactory_import_tested')}",
        '',
        'COUNTS',
        f"  Nodes:       {c.get('source_nodes')} -> {c.get('dgs_nodes')}",
        f"  Lines:       {c.get('source_lines')} -> {c.get('dgs_lines')}",
        f"  Loads:       {c.get('source_loads')} -> {c.get('dgs_loads')}",
        f"  Devices:     {c.get('source_devices')} -> {c.get('dgs_switches')}",
        f"  Cubicles:    {c.get('dgs_cubicles')}",
        f"  Diagrams:    {c.get('dgs_diagrams')}",
        f"  Graphics:    {c.get('dgs_graphics')}",
        f"  Graphic con: {c.get('dgs_graphic_connections')}",
        '',
        f"Line length source: {length.get('source')} km",
        f"Line length DGS:    {length.get('dgs')} km",
        f"Lengths from georef: {length.get('georef_lines')} | from TXT: {length.get('txt_lines')}",
        '',
        f"SCHEMA ERRORS: {len(report.get('schema_errors', []))}",
    ]
    lines.extend(f'  - {x}' for x in report.get('schema_errors', []))
    lines.append(f"STRUCTURAL ERRORS: {len(report.get('structural_errors', []))}")
    lines.extend(f'  - {x}' for x in report.get('structural_errors', []))
    lines.append(f"CONNECTION ERRORS: {len(report.get('connection_errors', []))}")
    lines.extend(f'  - {x}' for x in report.get('connection_errors', []))
    lines.append(f"GEOGRAPHIC ERRORS: {len(report.get('geographic_errors', []))}")
    lines.extend(f'  - {x}' for x in report.get('geographic_errors', []))
    lines.append(f"GRAPHIC ERRORS: {len(report.get('graphic_errors', []))}")
    lines.extend(f'  - {x}' for x in report.get('graphic_errors', []))
    lines.append(f"WARNINGS: {len(report.get('warnings', []))}")
    lines.extend(f'  - {x}' for x in report.get('warnings', []))
    txt_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
