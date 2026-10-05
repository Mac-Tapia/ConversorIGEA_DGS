"""Puertas de preparación comunes a TXT, MDB y VNR-GIS."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from synthetic_export import ExportSpec, load_export


def _workspace(tmp_path, *, mode: str, blocked: bool = False):
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='readiness', root=tmp_path)
    ws.loaded_source_mode = mode
    ws.dataset = SimpleNamespace()
    ws.loaded_run_id = 'run-1'
    ws.active_run_id = 'run-1'
    ws.inventory = {
        'feeders': [
            {'feeder': 'AL101', 'network_id': 'NET_AL101', 'convertible': True},
            {'feeder': 'AL102', 'network_id': 'NET_AL102', 'convertible': True},
            {'feeder': 'AL103', 'network_id': 'NET_AL103', 'convertible': True},
        ],
    }
    ws.feeder_readiness = {
        f'NET_AL10{i}': {
            'feeder': f'AL10{i}',
            'network_id': f'NET_AL10{i}',
            'status': 'INVENTORY_ONLY' if blocked and i == 2 else 'CONVERSION_READY',
            'blocking_codes': ['MISSING_CONDUCTOR_CATALOG'] if blocked and i == 2 else [],
        }
        for i in range(1, 4)
    }
    return ws


@pytest.mark.parametrize('mode', ['txt', 'mdb', 'vnr'])
def test_selection_one_many_all_is_identical_for_every_source_mode(tmp_path, mode):
    from igea_dgs.web.services import check_selection_readiness

    ws = _workspace(tmp_path, mode=mode)
    assert check_selection_readiness(ws, ['AL101'], False) == ['AL101']
    assert check_selection_readiness(ws, ['AL103', 'AL101'], False) == ['AL103', 'AL101']
    assert check_selection_readiness(ws, [], True) == ['AL101', 'AL102', 'AL103']


@pytest.mark.parametrize('mode', ['txt', 'mdb', 'vnr'])
def test_mixed_selection_fails_as_one_batch_for_every_source_mode(tmp_path, mode):
    from igea_dgs.web.services import UserError, check_selection_readiness

    ws = _workspace(tmp_path, mode=mode, blocked=True)
    with pytest.raises(UserError, match=r'FEEDER_NOT_CONVERSION_READY.*AL102.*MISSING_CONDUCTOR'):
        check_selection_readiness(ws, ['AL101', 'AL102'], False)


def test_exact_catalogue_is_required_per_feeder(tmp_path):
    from igea_dgs.web.readiness import assess_feeder_readiness

    ds = load_export(ExportSpec(feeders=2), tmp_path / 'export')
    feeder = ds.feeder_ids()[0]
    ready = assess_feeder_readiness(ds, feeder, {'source_mode': 'txt'})
    assert ready.status == 'CONVERSION_READY'

    first_section = ds.feeders[feeder][0]
    ds.line_configurations[first_section]['LineCableID'] = 'NO_EXISTE_EN_CATALOGO'
    blocked = assess_feeder_readiness(ds, feeder, {'source_mode': 'txt'})
    assert blocked.status == 'INVENTORY_ONLY'
    assert blocked.blocking_codes == ('MISSING_EXACT_CONDUCTOR_MAPPING',)


def test_feeder_rows_expose_source_and_readiness(tmp_path):
    from igea_dgs.web.services import feeder_rows

    ws = _workspace(tmp_path, mode='vnr', blocked=True)
    ws.loaded_source_fingerprint = 'sha256:test'
    rows = feeder_rows(ws)
    assert rows[0]['readiness'] == 'CONVERSION_READY'
    assert rows[0]['source_run_id'] == 'run-1'
    assert rows[0]['source_mode'] == 'vnr'
    assert rows[1]['readiness'] == 'INVENTORY_ONLY'
    assert rows[1]['blocking_codes'] == ['MISSING_CONDUCTOR_CATALOG']


def test_conversion_preflight_runs_before_converter_writes(tmp_path, monkeypatch):
    from igea_dgs.web import services

    ws = _workspace(tmp_path, mode='vnr', blocked=True)
    ws.dataset = SimpleNamespace()
    ws.loaded_source_fingerprint = 'fingerprint'
    snapshot = SimpleNamespace(
        run_id='run-1', mode='vnr', fingerprint='fingerprint', path_for=lambda _slot: None,
    )
    monkeypatch.setattr(ws, 'active_run', lambda: snapshot)
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr('igea_dgs.batch.convert_selection', forbidden)
    ctx = SimpleNamespace(log=lambda _message: None)
    with pytest.raises(services.UserError, match='FEEDER_NOT_CONVERSION_READY'):
        services.convert(ws, ctx, ['AL101', 'AL102'], False)
    assert called is False
    assert not ws.out_dir.exists()
