"""Focused tests for PointTerm filtering, SED naming and graphic helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from igea_dgs.dgs import (
    NA205_DIAGRAM_UNITS_PER_METER,
    NA205_MAX_DIAGRAM_EXTENT,
    NA205_SED_LV_KV,
    NA205_SED_SIZE,
    NA205_SYMBOL_SIZE,
    _adaptive_scale,
    _line_irot,
    _radial_offsets,
    diagram_line_sections,
    is_micro_service_stub_line,
    visible_pointterm_nodes,
    write_dgs,
)
from igea_dgs.geography import GeoLine, GeoPoint, GeographyManifest
from igea_dgs.model import (
    FeederModel,
    Line,
    LineType,
    Load,
    Node,
    Sed,
    SwitchingDevice,
    extract_sed_code,
    sed_loc_name,
)
from igea_dgs.validate import parse_dgs, validate_dgs


def test_extract_equipment_suffix_from_identifiers():
    assert extract_sed_code('CUST_2010_1042900_SE40699-2') == 'SE40699-2'
    assert extract_sed_code('CUST_2010_1042901_M40699') == 'M40699'
    assert extract_sed_code('DEV_2010_327899_SE40699') == 'SE40699'
    assert extract_sed_code('LOAD_TR12') == 'TR12'
    assert extract_sed_code('no-code-here') == ''
    assert sed_loc_name('M40699') == 'M40699'
    assert sed_loc_name('SE40699') == 'SE40699'


def test_line_irot_follows_geometry():
    assert _line_irot([(0.0, 0.0), (10.0, 0.0)]) == 0
    assert _line_irot([(0.0, 0.0), (0.0, 10.0)]) == 90
    assert _line_irot([(0.0, 0.0), (-10.0, 0.0)]) == 180


def test_ug_parallel_rail_paths_taper_to_shared_endpoints():
    from igea_dgs.dgs import ug_parallel_rail_paths

    center = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    left, right = ug_parallel_rail_paths(center, offset=2.0)
    assert left[0] == (0.0, 0.0) and left[-1] == (20.0, 0.0)
    assert right[0] == (0.0, 0.0) and right[-1] == (20.0, 0.0)
    assert left[1][1] > 0
    assert right[1][1] < 0
    assert abs(left[1][1] - right[1][1]) == pytest.approx(4.0)


def test_underground_span_single_d_lin_and_inair(tmp_path: Path):
    """Overhead=0 → one IntGrf d_lin + inAir=0 (no ghost dual rails)."""
    nodes = {
        'A': Node('A', 0, 0),
        'B': Node('B', 1, 0),
        'C': Node('C', 2, 0),
    }
    lt_oh = LineType('LINE:OH', 'OH', 'LINE', 0.1, 0.1, 0.1, 0.1, 0, 0, 100)
    lt_ug = LineType('CABLE:UG', 'UG', 'CONCENTRIC NEUTRAL CABLE', 0.1, 0.1, 0.1, 0.1, 0, 0, 100)
    lines = [
        Line('OH1', 'A', 'B', 'ABC', 'LINE:OH', 'OH', 50.0, True),
        Line('UG1', 'B', 'C', 'ABC', 'CABLE:UG', 'UG', 80.0, False),
    ]
    model = FeederModel(
        name='UGTOY',
        network_id='NET_UG',
        nominal_kv=13.8,
        source_node='A',
        nodes=nodes,
        lines=lines,
        loads=[],
        devices=[],
        line_types={'LINE:OH': lt_oh, 'CABLE:UG': lt_ug},
        seds=[],
    )
    geo_nodes = {
        'A': GeoPoint(lat=-14.0, lon=-75.0, x=0.0, y=0.0),
        'B': GeoPoint(lat=-14.001, lon=-75.0, x=50.0, y=0.0),
        'C': GeoPoint(lat=-14.002, lon=-75.0, x=130.0, y=0.0),
    }
    geo = GeographyManifest(
        feeder=model.name,
        network_id=model.network_id,
        source_node=model.source_node,
        source_crs='EPSG:4326',
        target_crs='EPSG:4326',
        nodes=geo_nodes,
        lines={
            'OH1': GeoLine('OH1', 'A', 'B', (geo_nodes['A'], geo_nodes['B'])),
            'UG1': GeoLine('UG1', 'B', 'C', (geo_nodes['B'], geo_nodes['C'])),
        },
        source_xy_bounds=(0.0, 0.0, 130.0, 0.0),
        target_bounds=(-14.002, -75.0, -14.0, -75.0),
        intermediate_point_count=0,
        intermediate_section_count=0,
    )
    out = tmp_path / 'ug_single.dgs'
    write_dgs(model, out, geography=geo)
    tables = parse_dgs(out)
    line_rows = {r['loc_name']: r for r in tables['ElmLne']['rows_dict']}
    assert line_rows['UG1']['inAir'] == '0'
    assert line_rows['OH1']['inAir'] == '1'
    ug_fid = line_rows['UG1']['FID']
    oh_fid = line_rows['OH1']['FID']
    ug_grf = [r for r in tables['IntGrf']['rows_dict'] if r.get('pDataObj') == ug_fid]
    oh_grf = [r for r in tables['IntGrf']['rows_dict'] if r.get('pDataObj') == oh_fid]
    assert len(ug_grf) == 1
    assert len(oh_grf) == 1
    assert len(tables['ElmFeeder']['rows_dict']) == 1
    assert tables['ElmFeeder']['rows_dict'][0]['loc_name'] == 'UGTOY'
    report = validate_dgs(model, out, geography=geo)
    assert report['errors_total'] == 0, report


def test_parallel_circuit_offsets_two_abc_same_span():
    from igea_dgs.dgs import parallel_circuit_graphic_offsets

    nodes = {
        'A': Node('A', 0, 0),
        'B': Node('B', 1, 0),
    }
    lt = LineType('LINE:T', 'T', 'LINE', 0.1, 0.1, 0.1, 0.1, 0, 0, 100)
    lines = [
        Line('C1', 'A', 'B', 'ABC', 'LINE:T', 'T', 10.0, True),
        Line('C2', 'A', 'B', 'ABC', 'LINE:T', 'T', 10.0, True),
    ]
    model = FeederModel(
        name='DBL',
        network_id='NET_DBL',
        nominal_kv=13.8,
        source_node='A',
        nodes=nodes,
        lines=lines,
        loads=[],
        devices=[],
        line_types={'LINE:T': lt},
        seds=[],
    )
    offsets = parallel_circuit_graphic_offsets(model, offset_du=4.0)
    assert set(offsets) == {'C1', 'C2'}
    assert offsets['C1'] == pytest.approx(-2.0)
    assert offsets['C2'] == pytest.approx(2.0)


def test_adaptive_scale_matches_na205_units_per_meter():
    # Compact feeder → NA205 geographic scale, not density blow-up.
    meter_xy = {
        'A': (0.0, 0.0),
        'B': (100.0, 0.0),
        'C': (50.0, 80.0),
    }
    scale = _adaptive_scale(meter_xy, set(meter_xy))
    assert scale == NA205_DIAGRAM_UNITS_PER_METER


def test_adaptive_scale_shrinks_oversized_feeders_to_na205_sheet():
    # Span 100 km would exceed NA205 canvas at 2.08 u/m → fit to max extent.
    meter_xy = {
        'A': (0.0, 0.0),
        'B': (100_000.0, 0.0),
    }
    scale = _adaptive_scale(meter_xy, set(meter_xy))
    assert scale == pytest.approx(NA205_MAX_DIAGRAM_EXTENT / 100_000.0)
    assert scale < NA205_DIAGRAM_UNITS_PER_METER


def test_radial_offsets_spread_shared_node_loads():
    one = _radial_offsets(1, 40.0)
    assert len(one) == 1
    three = _radial_offsets(3, 40.0)
    assert len(three) == 3
    assert len({(round(x, 6), round(y, 6)) for x, y in three}) == 3


def _toy_model(*, with_sed: bool = False) -> FeederModel:
    # Topology: source -- A -- B -- C(load) ; A also branches to D
    nodes = {
        'SRC': Node('SRC', 0, 0),
        'A': Node('A', 1, 0),
        'B': Node('B', 2, 0),
        'C': Node('C', 3, 0),
        'D': Node('D', 1, 1),
    }
    lt = LineType('LINE:T', 'T', 'LINE', 0.1, 0.1, 0.1, 0.1, 0, 0, 100)
    lines = [
        Line('S1', 'SRC', 'A', 'ABC', 'LINE:T', 'T', 10, True),
        Line('S2', 'A', 'B', 'ABC', 'LINE:T', 'T', 10, True),
        Line('S3', 'B', 'C', 'ABC', 'LINE:T', 'T', 10, True),
        Line('S4', 'A', 'D', 'ABC', 'LINE:T', 'T', 10, True),
    ]
    loads = [
        Load(
            'S3', 'DEV1', 'CUST_1_SE100', '1', 'C', 0.01, 0.0, 0.97, 50.0, 0.0, 'ABC',
            sed_code='SE100' if with_sed else '', display_name='SE100' if with_sed else 'CUST_1',
        ),
    ]
    devices = [
        SwitchingDevice('SWITCH', 'S1', 'S', 0, 'SRC', 'EQ1', 'SW1', 'ABC', 1, 0, 0),
    ]
    seds: list[Sed] = []
    if with_sed:
        seds = [
            Sed(
                code='SE100',
                loc_name='SE100',
                node_id='C',
                design_kva=50.0,
                section_id='S3',
                device_number='DEV1',
                load_key=('S3', 'DEV1'),
            ),
        ]
    return FeederModel(
        name='TOY',
        network_id='NET_TOY',
        nominal_kv=13.8,
        source_node='SRC',
        nodes=nodes,
        lines=lines,
        loads=loads,
        devices=devices,
        line_types={'LINE:T': lt},
        seds=seds,
    )


def _toy_geography(model: FeederModel) -> GeographyManifest:
    node_ids = sorted(model.nodes)
    nodes = {
        nid: GeoPoint(lat=-14.0 + i * 0.001, lon=-75.0 + i * 0.001, x=float(i), y=0.0)
        for i, nid in enumerate(node_ids)
    }
    lines = {
        line.section_id: GeoLine(
            section_id=line.section_id,
            from_node=line.from_node,
            to_node=line.to_node,
            path=(nodes[line.from_node], nodes[line.to_node]),
        )
        for line in model.lines
    }
    return GeographyManifest(
        feeder=model.name,
        network_id=model.network_id,
        source_node=model.source_node,
        source_crs='EPSG:4326',
        target_crs='EPSG:4326',
        nodes=nodes,
        lines=lines,
        source_xy_bounds=(0.0, 0.0, 4.0, 1.0),
        target_bounds=(-14.004, -75.004, -14.0, -75.0),
        intermediate_point_count=0,
        intermediate_section_count=0,
    )


def test_visible_pointterm_rules():
    model = _toy_model(with_sed=False)
    visible = visible_pointterm_nodes(model)
    # Every drawn-line endpoint gets a PointTerm (NA205: lines are not loose).
    assert 'A' in visible
    assert 'SRC' in visible
    assert 'D' in visible
    assert 'C' in visible
    assert 'B' in visible  # degree-2 chain node still terminates drawn S2/S3


def test_micro_stub_tip_hides_pointterm_and_d_lin():
    """≤1 m service tip: no PointTerm on tip, no d_lin on stub (SED on primary)."""
    nodes = {
        'P': Node('P', 0, 0),
        'TIP': Node('TIP', 1, 0),
    }
    lt = LineType('LINE:T', 'T', 'LINE', 0.1, 0.1, 0.1, 0.1, 0, 0, 100)
    lines = [Line('STUB', 'P', 'TIP', 'ABC', 'LINE:T', 'T', 0.3, True)]
    loads = [
        Load('STUB', 'DEV1', 'CUST_SE1', '1', 'TIP', 0.01, 0.0, 0.97, 50.0, 0.0, 'ABC',
             sed_code='SE1', display_name='SE1'),
    ]
    seds = [
        Sed('SE1', 'SE1', 'TIP', 50.0, 'STUB', 'DEV1', ('STUB', 'DEV1')),
    ]
    model = FeederModel(
        name='STUB',
        network_id='NET_STUB',
        nominal_kv=13.8,
        source_node='P',
        nodes=nodes,
        lines=lines,
        loads=loads,
        devices=[],
        line_types={'LINE:T': lt},
        seds=seds,
    )
    visible = visible_pointterm_nodes(model)
    assert 'P' in visible
    assert 'TIP' not in visible
    assert 'STUB' not in diagram_line_sections(model)


def test_sed_load_nests_inside_triangle_like_na205(tmp_path: Path):
    """ElmSubstat interior: MT+BT buses, Tr2, coupler to feeder, load on BT."""
    model = _toy_model(with_sed=True)
    geo = _toy_geography(model)
    out = tmp_path / 'toy_sed.dgs'
    write_dgs(model, out, geography=geo)
    tables = parse_dgs(out)

    sub = tables['ElmSubstat']['rows_dict'][0]
    lod = tables['ElmLod']['rows_dict'][0]
    assert lod['fold_id'] == sub['FID']
    assert lod['loc_name'] == 'SE100'

    symbols = {r['sSymNam'] for r in tables['IntGrf']['rows_dict']}
    assert 'SecSubProd' in symbols
    assert 'd_load' not in symbols
    assert not any(r.get('pDataObj') == lod['FID'] for r in tables['IntGrf']['rows_dict'])
    sed_grf = next(r for r in tables['IntGrf']['rows_dict'] if r.get('pDataObj') == sub['FID'])
    assert sed_grf['sSymNam'] == 'SecSubProd'
    assert float(sed_grf['rSizeX']) == NA205_SED_SIZE
    assert float(sed_grf['rSizeY']) == NA205_SED_SIZE
    assert not any(c.get('fold_id') == sed_grf['FID'] for c in tables['IntGrfcon']['rows_dict'])

    # Interior electrical (double-click triangle).
    assert len(tables['ElmTr2']['rows_dict']) == 1
    assert tables['ElmTr2']['rows_dict'][0]['fold_id'] == sub['FID']
    assert len(tables['ElmCoup']['rows_dict']) == 1
    assert tables['ElmCoup']['rows_dict'][0]['fold_id'] == sub['FID']
    inner_terms = [r for r in tables['ElmTerm']['rows_dict'] if r.get('fold_id') == sub['FID']]
    assert len(inner_terms) == 2
    uk = sorted(float(r['uknom']) for r in inner_terms)
    assert uk[0] == NA205_SED_LV_KV
    assert uk[1] == model.nominal_kv
    # Load cubicle on BT bus
    bt = next(r for r in inner_terms if float(r['uknom']) < 1.0)
    lod_cub = next(c for c in tables['StaCubic']['rows_dict'] if c.get('obj_id') == lod['FID'])
    assert lod_cub['fold_id'] == bt['FID']

    for row in tables['IntGrf']['rows_dict']:
        if row['sSymNam'] == 'SecSubProd':
            continue
        assert float(row['rSizeX']) == NA205_SYMBOL_SIZE
        assert float(row['rSizeY']) == NA205_SYMBOL_SIZE

    report = validate_dgs(model, out, geography=geo)
    assert report['errors_total'] == 0, report


def test_ica_gps_bounds_enable_digsilent_map(tmp_path: Path):
    """Toy Ica-zone GPS (same CRS path as NA205) lands on valid WGS84 for PF map."""
    model = _toy_model(with_sed=True)
    geo = _toy_geography(model)
    out = tmp_path / 'ica_map.dgs'
    write_dgs(model, out, geography=geo)
    tables = parse_dgs(out)
    terms = tables['ElmTerm']['rows_dict']
    assert terms
    for row in terms:
        lat = float(row['GPSlat'])
        lon = float(row['GPSlon'])
        # Ica / Nazca coastal band used by NA205 reference
        assert -16.0 <= lat <= -13.0
        assert -77.0 <= lon <= -74.0
    subs = tables['ElmSubstat']['rows_dict']
    assert all(r['GPSlat'] and r['GPSlon'] for r in subs)
