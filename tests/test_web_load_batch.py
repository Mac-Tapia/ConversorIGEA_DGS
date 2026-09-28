from __future__ import annotations

import io
import time
from pathlib import Path

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from synthetic_export import ExportSpec, write_export  # noqa: E402
from igea_dgs.web.app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as value:
        yield value


def _wait(client: TestClient, job: dict, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state['status'] in ('done', 'failed', 'cancelled'):
            return state
        time.sleep(0.02)
    raise AssertionError(f"job {job['id']} no terminó")


def _loaded(client: TestClient, tmp_path: Path) -> tuple[str, list[str]]:
    red, loads, equipment = write_export(
        ExportSpec(feeders=2, sections_per_feeder=3), tmp_path / 'export',
    )
    wid = client.post('/api/workspaces').json()['id']
    for slot, path in (('red', red), ('loads', loads), ('equipment', equipment)):
        with path.open('rb') as stream:
            response = client.post(
                f'/api/workspaces/{wid}/inputs/{slot}',
                files={'file': (path.name, stream)},
            )
        assert response.status_code == 200, response.text
    client.put(f'/api/workspaces/{wid}/options', json={'include_geography': False})
    state = _wait(client, client.post(f'/api/workspaces/{wid}/load').json())
    assert state['status'] == 'done', state
    feeders = [
        row['feeder']
        for row in client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']
    ]
    return wid, feeders


def _multipart(feeders: list[str], filename: str, content: bytes):
    return [
        *(('feeder', (None, feeder)) for feeder in feeders),
        ('file', (filename, content)),
    ]


def _create_plan(client: TestClient, wid: str, feeders: list[str]) -> dict:
    template = client.get(
        f'/api/workspaces/{wid}/load-template',
        params=[*(('feeder', feeder) for feeder in feeders), ('format', 'xlsx')],
    )
    assert template.status_code == 200, template.text
    response = client.post(
        f'/api/workspaces/{wid}/load-batch-plan',
        files=_multipart(feeders, 'cargas.xlsx', template.content),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_bulk_template_contains_all_selected_feeders(client, tmp_path):
    wid, feeders = _loaded(client, tmp_path)

    response = client.get(
        f'/api/workspaces/{wid}/load-template',
        params=[*(('feeder', feeder) for feeder in feeders), ('format', 'xlsx')],
    )

    assert response.status_code == 200, response.text
    workbook = load_workbook(io.BytesIO(response.content), read_only=True)
    try:
        assert workbook.sheetnames == sorted(feeders)
    finally:
        workbook.close()


def test_bulk_plan_processes_every_sheet(client, tmp_path):
    wid, feeders = _loaded(client, tmp_path)
    body = _create_plan(client, wid, feeders)
    assert body['token']
    assert body['feeders'] == sorted(feeders)
    assert set(body['summary_by_feeder']) == set(feeders)
    assert all(value['updates'] > 0 for value in body['summary_by_feeder'].values())


def test_bulk_csv_requires_feeder_for_multiple_models(client, tmp_path):
    wid, feeders = _loaded(client, tmp_path)
    csv_without_feeder = b'SED;Kw;Kvar;(kVA);FP\nSE1001;10;3;;\n'

    response = client.post(
        f'/api/workspaces/{wid}/load-batch-plan',
        files=_multipart(feeders, 'cargas.csv', csv_without_feeder),
    )

    assert response.status_code == 400
    assert 'Alimentador' in response.json()['detail']


def test_plan_rows_are_paginated_without_truncating_totals(client, tmp_path):
    wid, feeders = _loaded(client, tmp_path)
    plan = _create_plan(client, wid, feeders)
    endpoint = f"/api/workspaces/{wid}/load-batch-plans/{plan['token']}/rows"

    first = client.get(endpoint, params={'offset': 0, 'limit': 1}).json()
    second = client.get(endpoint, params={'offset': 1, 'limit': 1}).json()

    assert first['total'] > 1
    assert first['total'] == second['total']
    assert len(first['rows']) == len(second['rows']) == 1
    assert first['rows'][0] != second['rows'][0]


def test_input_change_invalidates_batch_plan(client, tmp_path):
    wid, feeders = _loaded(client, tmp_path)
    plan = _create_plan(client, wid, feeders)
    ws = client.app.state.store.get(wid)
    Path(ws.inputs['loads']['path']).write_text('cambio externo', encoding='utf-8')

    response = client.get(
        f"/api/workspaces/{wid}/load-batch-plans/{plan['token']}/rows"
    )

    assert response.status_code == 400
    assert 'obsoleto' in response.json()['detail'].lower()


def test_dgs_hash_change_invalidates_batch_plan(client, tmp_path):
    wid, feeders = _loaded(client, tmp_path)
    state = _wait(
        client,
        client.post(f'/api/workspaces/{wid}/convert', json={'feeders': feeders}).json(),
    )
    assert state['status'] == 'done', state
    plan = _create_plan(client, wid, feeders)
    ws = client.app.state.store.get(wid)
    conversion = next(iter(ws.conversions.values()))
    dgs = Path(conversion['dgs'])
    dgs.write_bytes(dgs.read_bytes() + b'\n# cambio externo\n')

    response = client.get(
        f"/api/workspaces/{wid}/load-batch-plans/{plan['token']}/rows"
    )

    assert response.status_code == 400
    assert 'obsoleto' in response.json()['detail'].lower()


def test_project_mapping_change_invalidates_batch_plan(client, tmp_path):
    wid, feeders = _loaded(client, tmp_path)
    ws = client.app.state.store.get(wid)
    ws.pf_projects[feeders[0]] = 'PROYECTO_A'
    plan = _create_plan(client, wid, feeders)
    ws.pf_projects[feeders[0]] = 'PROYECTO_B'

    response = client.get(
        f"/api/workspaces/{wid}/load-batch-plans/{plan['token']}/rows"
    )

    assert response.status_code == 400
    assert 'obsoleto' in response.json()['detail'].lower()
