from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from igea_dgs.dataset import CymdistDataset


def _equipment(code='C2'):
    return {
        'ID': code, 'R1': '0.7', 'R0': '0.7', 'X1': '0.4', 'X0': '1.2',
        'B1': '0', 'B0': '0', 'Amps': '150',
    }


def _dataset() -> CymdistDataset:
    return CymdistDataset(
        red_path=Path('red-original.txt'), loads_path=Path('loads-original.txt'),
        equipment_path=Path('equipment-original.txt'),
        headnodes={'N0': 'F-A', 'N2': 'F-B'},
        nodes={
            'N0': {'NodeID': 'N0', 'CoordX': '0', 'CoordY': '0'},
            'N2': {'NodeID': 'N2', 'CoordX': '20', 'CoordY': '0'},
            'N3': {'NodeID': 'N3', 'CoordX': '30', 'CoordY': '0'},
        },
        sources={
            'F-A': {'NetworkID': 'F-A', 'NodeID': 'N0', 'DesiredVoltage': '10'},
            'F-B': {'NetworkID': 'F-B', 'NodeID': 'N2', 'DesiredVoltage': '10'},
        },
        line_configurations={
            'S1': {
                'SectionID': 'S1', 'LineCableID': 'UNKNOWN-50', 'Overhead': '1',
                'Length': '10', 'Material': 'AAAC', 'SectionMM2': '50',
            },
            'S2': {
                'SectionID': 'S2', 'LineCableID': 'C2', 'Overhead': '1', 'Length': '10',
            },
        },
        sections={
            'S1': {
                'SectionID': 'S1', 'FromNodeID': 'N0', 'ToNodeID': 'N1',
                'ToCoordX': '10', 'ToCoordY': '0', 'Phase': 'ABC',
            },
            'S2': {
                'SectionID': 'S2', 'FromNodeID': 'N2', 'ToNodeID': 'N3', 'Phase': 'ABC',
            },
        },
        section_owner={'S1': 'F-A', 'S2': 'F-B'},
        feeders={'F-A': ('S1',), 'F-B': ('S2',)},
        switch_settings=(), sectionalizer_settings=(), intermediate_nodes=(),
        load_placements={}, customer_loads={}, equipment_tables={'LINE': (_equipment(),)},
    )


def _workspace(tmp_path):
    from igea_dgs.web.readiness import assess_feeder_readiness
    from igea_dgs.web.workspace import Workspace

    dataset = _dataset()
    ws = Workspace(id='abcd1234', root=tmp_path / 'abcd1234')
    ws.dataset = dataset
    ws.active_run_id = ws.loaded_run_id = '20261005T120000-aaaaaaaaaaaa'
    ws.loaded_source_mode = 'txt'
    ws.loaded_source_fingerprint = 'f' * 64
    ws.inventory = {
        'feeders': [
            {'feeder': 'F-A', 'network_id': 'F-A', 'sections': 1},
            {'feeder': 'F-B', 'network_id': 'F-B', 'sections': 1},
        ],
    }
    ws.feeder_readiness = {
        feeder: assess_feeder_readiness(dataset, feeder, {'source_mode': 'txt'}).as_dict()
        for feeder in dataset.feeder_ids()
    }
    snapshot = SimpleNamespace(
        run_id=ws.active_run_id, mode='txt', fingerprint='f' * 64,
        files={'red': SimpleNamespace(sha256='1' * 64, name='red.txt')},
        path_for=lambda _slot: '',
    )
    ws.active_run = lambda: snapshot
    return ws


def _fingerprint(dataset):
    return json.dumps(asdict(dataset), sort_keys=True, default=str)


def test_diagnosis_is_read_only_and_reports_one_many_all(tmp_path):
    from igea_dgs.web.reconstruction_service import diagnose_selection

    ws = _workspace(tmp_path)
    before = _fingerprint(ws.dataset)

    one = diagnose_selection(ws, ['F-A'], all_feeders=False)
    all_rows = diagnose_selection(ws, [], all_feeders=True)

    assert [row['feeder'] for row in one['feeders']] == ['F-A']
    assert [row['feeder'] for row in all_rows['feeders']] == ['F-A', 'F-B']
    assert one['feeders'][0]['readiness'] == 'INVENTORY_ONLY'
    assert _fingerprint(ws.dataset) == before


def test_reconstruction_is_atomic_keeps_original_and_persists_report(tmp_path):
    from igea_dgs.web.reconstruction_service import reconstruct_selection

    ws = _workspace(tmp_path)
    before = _fingerprint(ws.dataset)

    response = reconstruct_selection(ws, ['F-A'], all_feeders=False)

    assert _fingerprint(ws.dataset) == before
    assert 'N1' not in ws.dataset.nodes
    assert 'N1' in ws.reconstructed_dataset.nodes
    assert ws.reconstructed_dataset.line_configurations['S1']['LineCableID'] == 'UNKNOWN-50'
    assert any(row['ID'] == 'UNKNOWN-50' for row in ws.reconstructed_dataset.equipment_tables['LINE'])
    assert response['feeders'][0]['readiness'] == 'READY_RECONSTRUCTED'
    assert response['assumptions'] >= 1
    assert response['source_sha256'] == {'red': '1' * 64}
    report = ws.out_dir / 'reconstruction_report.json'
    assert report.is_file()
    assert json.loads(report.read_text(encoding='utf-8'))['report_sha256'] == response['report_sha256']
    assert ws.reconstruction_selection == ('F-A',)


def test_reconstruction_rejects_a_stale_loaded_run_before_writing(tmp_path):
    from igea_dgs.web.reconstruction_service import reconstruct_selection
    from igea_dgs.web.services import UserError

    ws = _workspace(tmp_path)
    ws.loaded_run_id = '20261005T120000-bbbbbbbbbbbb'

    with pytest.raises(UserError, match='SOURCE_RUN_MISMATCH'):
        reconstruct_selection(ws, ['F-A'], all_feeders=False)
    assert not ws.out_dir.exists()


def test_api_exposes_diagnose_and_reconstruct_endpoints(tmp_path, monkeypatch):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient

    from igea_dgs.web.app import create_app

    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'no-frontend'))
    with TestClient(create_app(tmp_path / 'web')) as client:
        created = client.post('/api/workspaces').json()
        ws = client.app.state.store.get(created['id'])
        prepared = _workspace(tmp_path / 'prepared')
        for name in (
            'dataset', 'active_run_id', 'loaded_run_id', 'loaded_source_mode',
            'loaded_source_fingerprint', 'inventory', 'feeder_readiness', 'active_run',
        ):
            setattr(ws, name, getattr(prepared, name))

        diagnosed = client.post(
            f'/api/workspaces/{ws.id}/diagnose', json={'feeders': ['F-A'], 'all': False},
        )
        reconstructed = client.post(
            f'/api/workspaces/{ws.id}/reconstruct', json={'feeders': ['F-A'], 'all': False},
        )

        assert diagnosed.status_code == 200
        assert reconstructed.status_code == 200
        assert reconstructed.json()['feeders'][0]['readiness'] == 'READY_RECONSTRUCTED'


def test_conversion_uses_matching_derived_dataset_and_stamps_evidence(tmp_path, monkeypatch):
    from threading import Event

    from igea_dgs.web import services
    from igea_dgs.web.reconstruction_service import reconstruct_selection

    ws = _workspace(tmp_path)
    reconstruct_selection(ws, ['F-A'], all_feeders=False)
    captured = {}

    def fake_convert(dataset, _feeders, out_dir, **_kwargs):
        captured['dataset'] = dataset
        out_dir.mkdir(parents=True, exist_ok=True)
        return {
            'status': 'ok',
            'summary': {'requested': 1, 'ok': 1, 'skipped': 0, 'failed': 0},
            'feeders': [{
                'feeder': 'F-A', 'network_id': 'F-A', 'status': 'ok',
                'counts': {}, 'warnings': [],
            }],
        }

    monkeypatch.setattr('igea_dgs.batch.convert_selection', fake_convert)
    ctx = SimpleNamespace(log=lambda _text: None, progress=lambda *_args: None, cancel=Event())

    result = services.convert(ws, ctx, ['F-A'], False)
    manifest = json.loads((ws.out_dir / 'batch_manifest.json').read_text(encoding='utf-8'))

    assert captured['dataset'] is ws.reconstructed_dataset
    assert result['status'] == 'ok'
    assert manifest['reconstruction']['report_sha256'] == ws.reconstruction_report_hash
    assert manifest['feeders'][0]['reconstruction']['assumptions'] >= 1
