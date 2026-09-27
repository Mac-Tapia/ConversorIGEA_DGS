from __future__ import annotations

from dataclasses import replace

import pytest

from igea_dgs.load_inventory import (
    build_load_inventory,
    query_load_inventory,
    rows_from_models,
)
from igea_dgs.model import FeederModel, Line, LineType, Load, Node, Sed
from igea_dgs.naming import feeder_short_name
from igea_dgs.reglas import REGLAS_PROYECTO
from synthetic_export import ExportSpec, load_export


pytest.importorskip('pyproj')


def _model() -> FeederModel:
    line_type = LineType(
        key='LINE:T1', code='T1', source_table='LINE',
        r1_ohm_km=0.1, r0_ohm_km=0.3, x1_ohm_km=0.2,
        x0_ohm_km=0.6, b1_source=0.0, b0_source=0.0, ampacity_a=200.0,
    )
    line = Line(
        section_id='S1', from_node='N0', to_node='N1', phase='ABC',
        type_key=line_type.key, source_type_code='T1', length_m=100.0,
        overhead=True,
    )
    load = Load(
        section_id='S1', device_number='D1', customer_number='SE50033',
        location='1', node_id='N1', p_mw=0.15, q_mvar=0.03, pf=0.98,
        connected_kva=200.0, kwh=1200.0, phase='ABC', sed_code='50033',
        display_name='SE50033', customers=12, customer_type='RES', year=2025,
        feeder='NA203', network_id='NETWORK_NA203',
    )
    sed = Sed(
        code='50033', loc_name='SE50033', node_id='N1', design_kva=200.0,
        section_id='S1', device_number='D1', load_key=('S1', 'D1'),
        feeder='NA203', network_id='NETWORK_NA203',
    )
    return FeederModel(
        name='NA203', network_id='NETWORK_NA203', nominal_kv=22.9,
        source_node='N0', nodes={'N0': Node('N0', 0.0, 0.0), 'N1': Node('N1', 1.0, 0.0)},
        lines=[line], loads=[load], devices=[], line_types={line_type.key: line_type},
        section_by_id={'S1': line}, seds=[sed],
    )


def test_inventory_keeps_real_feeder_inside_combined_grid():
    row = rows_from_models([_model()], grid_name='NA203_NA205')[0]

    assert row.name == 'SE50033'
    assert row.grid == 'NA203_NA205'
    assert row.alimentador == 'NA203'
    assert row.network_id == 'NETWORK_NA203'
    assert row.status == 'OK'


def test_inventory_reports_disconnected_and_ambiguous_without_guessing():
    model = _model()
    ambiguous = replace(
        model.loads[0], device_number='D2', display_name='SE50034',
        feeder='NA205', network_id='NETWORK_NA205',
    )
    disconnected = replace(
        model.loads[0], device_number='D3', display_name='SE50035',
    )
    model.loads.extend((ambiguous, disconnected))
    model.islands = {
        'sections': ['S1'], 'nodes': ['N1'], 'loads': ['D3'],
        'seds': [], 'has_loads': True,
    }

    rows = {row.name: row for row in rows_from_models([model])}

    assert rows['SE50034'].status == 'AMBIGUO'
    assert rows['SE50034'].alimentador == 'NA205'
    assert rows['SE50035'].status == 'DESCONECTADO'
    assert 'SOURCE' in rows['SE50035'].diagnostic


def test_inventory_exposes_load_and_transformer_electrical_fields():
    row = rows_from_models([_model()])[0]

    assert row.kw == pytest.approx(150.0)
    assert row.kvar == pytest.approx(30.0)
    assert row.kva == pytest.approx(200.0)
    assert row.voltage_mt_kv == pytest.approx(22.9)
    assert row.voltage_bt_kv == pytest.approx(0.22)
    assert row.uk_pct == pytest.approx(4.0)
    assert row.copper_losses_kw > 0
    assert row.core_losses_kw > 0
    assert row.vector_group == 'Dyn5'


def test_inventory_accepts_arbitrary_feeder_codes(tmp_path):
    dataset = load_export(
        ExportSpec(feeders=3, sections_per_feeder=4, loads_per_feeder=2),
        tmp_path / 'source',
    )
    networks = dataset.feeder_ids()
    expected = {feeder_short_name(network) for network in networks}

    rows = build_load_inventory(
        dataset, networks, reglas=REGLAS_PROYECTO, catalogo=None,
        grid_name='RED_MULTIPLE',
    )

    assert rows
    assert {row.alimentador for row in rows} == expected
    assert {row.grid for row in rows} == {'RED_MULTIPLE'}


def test_inventory_pagination_is_stable():
    first = rows_from_models([_model()])[0]
    rows = tuple(
        replace(first, name=name, device_number=f'D{index}')
        for index, name in enumerate(('SE50031', 'SE50032', 'SE50033'), start=1)
    )

    page = query_load_inventory(rows, offset=1, limit=1)

    assert page.total == 3
    assert page.offset == 1
    assert page.limit == 1
    assert [row.name for row in page.rows] == ['SE50032']


@pytest.mark.parametrize('offset,limit', [(-1, 100), (0, 0), (0, 501)])
def test_inventory_rejects_negative_offset_and_out_of_range_limit(offset, limit):
    rows = rows_from_models([_model()])

    with pytest.raises(ValueError):
        query_load_inventory(rows, offset=offset, limit=limit)


def test_workspace_invalidate_clears_load_inventory_cache(tmp_path):
    from igea_dgs.web.workspace import Workspace

    workspace = Workspace(id='abcdef12', root=tmp_path / 'workspace')
    workspace.load_inventory_cache[('dataset-a', ('NA203',), 'NA203')] = (
        rows_from_models([_model()])
    )

    workspace.invalidate()

    assert workspace.load_inventory_cache == {}
