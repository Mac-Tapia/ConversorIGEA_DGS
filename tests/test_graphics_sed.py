"""Focused tests for PointTerm filtering, SED naming and graphic helpers."""

from __future__ import annotations

from igea_dgs.dgs import _line_irot, _radial_offsets, visible_pointterm_nodes
from igea_dgs.model import (
    FeederModel,
    Line,
    LineType,
    Load,
    Node,
    SwitchingDevice,
    extract_sed_code,
    sed_loc_name,
)


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


def test_radial_offsets_spread_shared_node_loads():
    one = _radial_offsets(1, 40.0)
    assert len(one) == 1
    three = _radial_offsets(3, 40.0)
    assert len(three) == 3
    assert len({(round(x, 6), round(y, 6)) for x, y in three}) == 3


def _toy_model() -> FeederModel:
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
            sed_code='SE100', display_name='SE100',
        ),
    ]
    devices = [
        SwitchingDevice('SWITCH', 'S1', 'S', 0, 'SRC', 'EQ1', 'SW1', 'ABC', 1, 0, 0),
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
        seds=[],
    )


def test_visible_pointterm_rules():
    model = _toy_model()
    visible = visible_pointterm_nodes(model)
    # Branch node A (deg 3), source SRC (head), open stub D (deg 1 no load)
    assert 'A' in visible
    assert 'SRC' in visible
    assert 'D' in visible
    # Chain node B (deg 2) and load terminal C stay electrical-only
    assert 'B' not in visible
    assert 'C' not in visible
