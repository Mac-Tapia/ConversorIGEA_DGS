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


def _client_con_dataset(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from igea_dgs.web.app import create_app

    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'no-frontend'))
    client = TestClient(create_app(tmp_path / 'web'))
    client.__enter__()
    created = client.post('/api/workspaces').json()
    ws = client.app.state.store.get(created['id'])
    prepared = _workspace(tmp_path / 'prepared')
    for name in (
        'dataset', 'active_run_id', 'loaded_run_id', 'loaded_source_mode',
        'loaded_source_fingerprint', 'inventory', 'feeder_readiness', 'active_run',
    ):
        setattr(ws, name, getattr(prepared, name))
    return client, ws


def test_api_exposes_diagnose_and_reconstruct_endpoints(tmp_path, monkeypatch):
    """001:RF-8 — diagnosticar y reconstruir son trabajos del carril engine (202 + Job)."""
    pytest.importorskip('fastapi')
    from apoyo import esperar_trabajo

    client, ws = _client_con_dataset(tmp_path, monkeypatch)
    try:
        diagnosed = client.post(
            f'/api/workspaces/{ws.id}/diagnose', json={'feeders': ['F-A'], 'all': False},
        )
        assert diagnosed.status_code == 202
        assert diagnosed.json()['lane'] == 'engine'
        diagnosed = esperar_trabajo(client, diagnosed.json())
        reconstructed = client.post(
            f'/api/workspaces/{ws.id}/reconstruct', json={'feeders': ['F-A'], 'all': False},
        )
        assert reconstructed.status_code == 202
        assert reconstructed.json()['lane'] == 'engine'
        reconstructed = esperar_trabajo(client, reconstructed.json())

        assert diagnosed['status'] == 'done'
        assert diagnosed['result']['feeders'][0]['feeder'] == 'F-A'
        assert reconstructed['status'] == 'done'
        assert reconstructed['result']['feeders'][0]['readiness'] == 'READY_RECONSTRUCTED'
        # El avance llega por el registro de eventos que sirve el WebSocket.
        progresos = [
            e['data']['progress'] for e in ws.events.since(0)
            if e['type'] == 'job' and e['data']['id'] == reconstructed['id']
            and e['data']['progress']
        ]
        assert progresos[-1]['index'] == progresos[-1]['total'] > 1
    finally:
        client.__exit__(None, None, None)


def test_api_rechaza_la_seleccion_al_momento_sin_crear_trabajo(tmp_path, monkeypatch):
    """001:RF-8 — un alimentador desconocido es un 400 de la petición, no un trabajo fallido."""
    pytest.importorskip('fastapi')

    client, ws = _client_con_dataset(tmp_path, monkeypatch)
    try:
        for ruta in ('diagnose', 'reconstruct'):
            response = client.post(
                f'/api/workspaces/{ws.id}/{ruta}', json={'feeders': ['NO-EXISTE'], 'all': False},
            )
            assert response.status_code == 400
            assert 'UNKNOWN_FEEDER' in response.json()['detail']
        assert client.app.state.jobs.list(ws.id) == []
    finally:
        client.__exit__(None, None, None)


def test_cancelar_la_reconstruccion_conserva_el_dataset_anterior(tmp_path, monkeypatch):
    """001:RF-9 — cancelar a mitad deja activa la reconstrucción anterior y su informe."""
    import threading

    from igea_dgs.web import reconstruction_service
    from igea_dgs.web.jobs import CANCELLED, JobManager
    from igea_dgs.web.reconstruction_service import reconstruct_selection

    ws = _workspace(tmp_path)
    reconstruct_selection(ws, ['F-A'], all_feeders=False)
    anterior = ws.reconstructed_dataset
    hash_anterior = ws.reconstruction_report_hash
    informe = (ws.out_dir / 'reconstruction_report.json').read_bytes()

    en_marcha, seguir = threading.Event(), threading.Event()
    original = reconstruction_service.repair_discontinuities

    def lento(*args, **kwargs):
        en_marcha.set()
        seguir.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(reconstruction_service, 'repair_discontinuities', lento)
    jobs = JobManager(lambda *_args: None)
    job = jobs.submit(ws.id, 'reconstruct', 'Reconstruir', lambda ctx: reconstruct_selection(
        ws, ['F-A', 'F-B'], all_feeders=False, ctx=ctx))
    assert en_marcha.wait(10)
    jobs.cancel(job.id)
    seguir.set()
    jobs.shutdown(timeout_s=10)

    assert job.status == CANCELLED
    assert ws.reconstructed_dataset is anterior
    assert ws.reconstruction_report_hash == hash_anterior
    assert ws.reconstruction_selection == ('F-A',)
    assert (ws.out_dir / 'reconstruction_report.json').read_bytes() == informe


def test_tras_el_punto_sin_retorno_la_cancelacion_no_entra():
    """001:RF-9 — un trabajo que ya publicó no puede acabar «cancelado»."""
    import threading

    from igea_dgs.web.jobs import DONE, JobManager

    publicado, seguir = threading.Event(), threading.Event()

    def trabajo(ctx):
        ctx.sin_retorno()
        publicado.set()
        seguir.wait(10)
        return 'publicado'

    jobs = JobManager(lambda *_args: None)
    job = jobs.submit('ws', 'reconstruct', 'Reconstruir', trabajo)
    assert publicado.wait(10)
    jobs.cancel(job.id)
    assert not job.cancel.is_set()
    seguir.set()
    jobs.shutdown(timeout_s=10)

    assert job.status == DONE
    assert job.result == 'publicado'


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
