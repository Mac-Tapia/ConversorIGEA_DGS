from __future__ import annotations

from pathlib import Path

from igea_dgs.load_batch import (
    FeederLoadContext,
    bulk_plan_to_payload,
    build_bulk_update_plan,
    write_bulk_template,
)
from igea_dgs.loads import SHEET_COLUMNS, SheetRead, read_sheet, read_workbook
from igea_dgs.model import FeederModel, Load, Node, Sed


def _model(name: str, sed_code: str = 'SE1001') -> FeederModel:
    section = f'SEC_{name}'
    device = f'DEV_{name}_{sed_code}'
    load = Load(
        section_id=section,
        device_number=device,
        customer_number=f'CUST_{sed_code}',
        location='1',
        node_id='N1',
        p_mw=0.010,
        q_mvar=0.003,
        pf=0.95,
        connected_kva=50.0,
        kwh=0.0,
        phase='ABC',
        sed_code=sed_code,
        display_name=sed_code,
    )
    sed = Sed(
        code=sed_code,
        loc_name=sed_code,
        node_id='N1',
        design_kva=50.0,
        section_id=section,
        device_number=device,
        load_key=(section, device),
    )
    return FeederModel(
        name=name,
        network_id=f'NET_{name}',
        nominal_kv=10.0,
        source_node='N0',
        nodes={'N0': Node('N0', 0.0, 0.0), 'N1': Node('N1', 1.0, 0.0)},
        lines=[],
        loads=[load],
        devices=[],
        line_types={},
        seds=[sed],
    )


def _context(name: str, sed_code: str = 'SE1001') -> FeederLoadContext:
    return FeederLoadContext(
        feeder=name,
        network_id=f'NET_{name}',
        model=_model(name, sed_code),
        project_name=f'IGEA_DGS_CONVERTER_{name}',
        dgs_sha256=f'dgs-{name}',
        metadata_sha256=f'meta-{name}',
        revision='rev-1',
    )


def _sheet(feeder: str, sed_code: str = 'SE1001', kw: str = '20'):
    return read_sheet(
        list(SHEET_COLUMNS),
        [[sed_code, kw, '5', '', '']],
        feeder,
    )


def test_excel_sheets_create_one_plan_per_feeder():
    contexts = {name: _context(name) for name in ('AL209', 'IN111')}
    sheets = {name: _sheet(name) for name in contexts}

    plan = build_bulk_update_plan(contexts, sheets, input_sha256='input-1')

    assert list(plan.feeders) == ['AL209', 'IN111']
    assert all(len(item.updates) == 1 for item in plan.feeders.values())


def test_csv_feeder_column_routes_each_row(tmp_path: Path):
    csv_path = tmp_path / 'cargas.csv'
    csv_path.write_text(
        'Alimentador;SED;Kw;Kvar;(kVA);FP\n'
        'AL209;SE1001;20;5;;\n'
        'IN111;SE1001;30;7;;\n',
        encoding='utf-8',
    )
    contexts = {name: _context(name) for name in ('AL209', 'IN111')}

    plan = build_bulk_update_plan(
        contexts,
        read_workbook(csv_path),
        input_sha256='input-2',
    )

    assert plan.feeders['AL209'].updates[0][1].kw == 20.0
    assert plan.feeders['IN111'].updates[0][1].kw == 30.0


def test_unknown_feeder_blocks_only_that_feeder():
    contexts = {'AL209': _context('AL209')}
    sheets = {'AL209': _sheet('AL209'), 'ZZ999': _sheet('ZZ999')}

    plan = build_bulk_update_plan(contexts, sheets, input_sha256='input-3')

    assert plan.feeders['AL209'].is_applicable is True
    assert 'ZZ999' in plan.blocked_feeders
    assert 'AL209' not in plan.blocked_feeders


def test_no_sheet_is_silently_dropped():
    contexts = {'AL209': _context('AL209')}
    sheets = {
        'AL209': _sheet('AL209'),
        'NOTAS': SheetRead(feeder='NOTAS', errors=['no se encontró la columna de código de SED']),
    }

    plan = build_bulk_update_plan(contexts, sheets, input_sha256='input-4')

    assert plan.ignored_sheets == ['NOTAS']
    assert not any('NOTAS' in error for error in plan.row_errors)


def test_identity_contains_feeder_network_and_sed():
    plan = build_bulk_update_plan(
        {'AL209': _context('AL209')},
        {'AL209': _sheet('AL209')},
        input_sha256='input-identity',
    )

    update = bulk_plan_to_payload(plan)['feeders'][0]['updates'][0]

    assert update['feeder'] == 'AL209'
    assert update['network_id'] == 'NET_AL209'
    assert update['sed_code'] == 'SE1001'


def test_duplicate_sed_in_same_feeder_is_blocking():
    duplicate = read_sheet(
        list(SHEET_COLUMNS),
        [
            ['SE1001', '20', '5', '', ''],
            ['SE1001', '30', '7', '', ''],
        ],
        'AL209',
    )

    plan = build_bulk_update_plan(
        {'AL209': _context('AL209')},
        {'AL209': duplicate},
        input_sha256='input-duplicate',
    )

    assert plan.feeders['AL209'].is_applicable is False
    assert any('repetida' in error for error in plan.blocked_feeders['AL209'])


def test_same_sed_in_different_feeders_is_valid():
    contexts = {name: _context(name, 'SE50033') for name in ('AL209', 'IN111')}
    sheets = {name: _sheet(name, 'SE50033') for name in contexts}

    payload = bulk_plan_to_payload(
        build_bulk_update_plan(contexts, sheets, input_sha256='input-shared-sed')
    )

    assert [item['feeder'] for item in payload['feeders']] == ['AL209', 'IN111']
    assert {
        (row['feeder'], row['network_id'], row['sed_code'])
        for item in payload['feeders'] for row in item['updates']
    } == {
        ('AL209', 'NET_AL209', 'SE50033'),
        ('IN111', 'NET_IN111', 'SE50033'),
    }


def test_same_inputs_produce_same_payload_and_hashes():
    left_contexts = {name: _context(name) for name in ('IN111', 'AL209')}
    right_contexts = {name: left_contexts[name] for name in ('AL209', 'IN111')}
    left_sheets = {name: _sheet(name) for name in ('IN111', 'AL209')}
    right_sheets = {name: left_sheets[name] for name in ('AL209', 'IN111')}

    left = bulk_plan_to_payload(
        build_bulk_update_plan(left_contexts, left_sheets, input_sha256='input-stable')
    )
    right = bulk_plan_to_payload(
        build_bulk_update_plan(right_contexts, right_sheets, input_sha256='input-stable')
    )

    assert left == right
    assert left['batch_id'] == right['batch_id']


def test_bulk_template_preserves_all_feeders(tmp_path: Path):
    contexts = {name: _context(name) for name in ('IN111', 'AL209')}

    xlsx = write_bulk_template(contexts, tmp_path / 'cargas.xlsx')
    csv = write_bulk_template(contexts, tmp_path / 'cargas.csv')

    assert list(read_workbook(xlsx)) == ['AL209', 'IN111']
    assert set(read_workbook(csv)) == {'AL209', 'IN111'}
