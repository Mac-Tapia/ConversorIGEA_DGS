"""Contrato HTTP que consume la interfaz de las tres fuentes aisladas."""

from __future__ import annotations

import time

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402

from igea_dgs.web.app import create_app  # noqa: E402
from synthetic_export import ExportSpec, write_export  # noqa: E402


def _wait(client: TestClient, job: dict) -> dict:
    deadline = time.time() + 30
    while time.time() < deadline:
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state['status'] in {'done', 'failed', 'cancelled'}:
            return state
        time.sleep(0.03)
    raise AssertionError('el trabajo de carga no terminó')


def test_health_declares_the_three_isolated_source_modes(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'missing'))
    with TestClient(create_app(tmp_path / 'web')) as client:
        health = client.get('/api/health').json()
    assert health['source_modes'] == ['txt', 'mdb', 'vnr']
    assert health['slots']['vnr_package']['grupo'] == 'vnr'


def test_workspace_exposes_active_manifest_and_safe_run_history(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'missing'))
    red, loads, equipment = write_export(ExportSpec(feeders=1), tmp_path / 'export')
    with TestClient(create_app(tmp_path / 'web')) as client:
        wid = client.post('/api/workspaces').json()['id']
        for slot, path in (('red', red), ('loads', loads), ('equipment', equipment)):
            with path.open('rb') as handle:
                response = client.post(
                    f'/api/workspaces/{wid}/inputs/{slot}',
                    files={'file': (path.name, handle)},
                )
            assert response.status_code == 200
        state = _wait(client, client.post(f'/api/workspaces/{wid}/load').json())
        assert state['status'] == 'done', state

        workspace = client.get(f'/api/workspaces/{wid}').json()
        run_id = workspace['active_run_id']
        assert workspace['source_mode'] == 'txt'
        assert len(workspace['source_fingerprint']) == 64
        assert workspace['source_manifest_url'].endswith(f'/runs/{run_id}/manifest')

        history = client.get(f'/api/workspaces/{wid}/runs').json()
        assert [(row['run_id'], row['mode']) for row in history] == [(run_id, 'txt')]
        manifest = client.get(workspace['source_manifest_url']).json()
        assert manifest['run_id'] == run_id
        assert {item['slot'] for item in manifest['files']} == {'red', 'loads', 'equipment'}
        assert all('source_path' not in item and len(item['sha256']) == 64 for item in manifest['files'])

        assert client.get(f'/api/workspaces/{wid}/runs/not-valid/manifest').status_code == 404
        other = client.post('/api/workspaces').json()['id']
        assert client.get(f'/api/workspaces/{other}/runs/{run_id}/manifest').status_code == 404
