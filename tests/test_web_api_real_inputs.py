"""Aceptación opt-in de las dos entradas reales a través de la API web.

No usa generadores sintéticos. Las rutas se reciben por variables de entorno para
que los archivos operativos, que no son publicables, permanezcan fuera del repo.
Un skip por ausencia de esos archivos no constituye una aprobación.
"""

from __future__ import annotations

import os
from pathlib import Path
import time

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402

from igea_dgs.web.app import create_app  # noqa: E402


FEEDERS = ('NA203', 'NA205', 'PE104', 'CA101')
REAL_INPUTS = {
    'txt': {
        'red': 'IGEA_RED',
        'loads': 'IGEA_LOADS',
        'equipment': 'IGEA_EQUIPMENT',
    },
    'mdb': {
        'mdb': 'IGEA_MDB',
        'equipment_mdb': 'IGEA_EQUIPMENT_MDB',
    },
}


def _paths(mode: str) -> dict[str, Path]:
    paths = {slot: Path(os.environ.get(variable, ''))
             for slot, variable in REAL_INPUTS[mode].items()}
    missing = [REAL_INPUTS[mode][slot] for slot, path in paths.items() if not path.is_file()]
    if missing:
        pytest.skip('Faltan entradas reales: ' + ', '.join(missing))
    return paths


def _wait(client: TestClient, job: dict, timeout: float = 180.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state['status'] in ('done', 'failed', 'cancelled'):
            return state
        time.sleep(0.1)
    raise AssertionError(f"El trabajo real {job['id']} no terminó en {timeout} s")


@pytest.mark.real_reference_inputs
@pytest.mark.parametrize('mode', ('txt', 'mdb'))
def test_real_txt_and_mdb_complete_web_api_flow(mode, tmp_path, monkeypatch):
    paths = _paths(mode)
    monkeypatch.setenv('IGEA_WEB_SERVER_PATHS', '1')
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'frontend-build-not-required'))
    app = create_app(tmp_path / f'web-{mode}')

    with TestClient(app) as client:
        created = client.post('/api/workspaces')
        assert created.status_code == 201, created.text
        wid = created.json()['id']
        options = client.put(
            f'/api/workspaces/{wid}/options',
            json={
                'input_mode': mode,
                'workers': 2,
                'hoja': 'AUTO',
                'include_geography': True,
                'strict': True,
            },
        )
        assert options.status_code == 200, options.text

        for slot, path in paths.items():
            assigned = client.post(
                f'/api/workspaces/{wid}/inputs/{slot}/path', json={'path': str(path)},
            )
            assert assigned.status_code == 200, assigned.text
            meta = assigned.json()['workspace']['inputs'][slot]
            assert meta['origin'] == 'server'
            assert meta['sha256']
            assert meta['size'] == path.stat().st_size

        loaded = _wait(client, client.post(f'/api/workspaces/{wid}/load').json())
        assert loaded['status'] == 'done', loaded
        rows = client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']
        by_name = {row['feeder']: row for row in rows}
        assert set(FEEDERS) <= set(by_name)

        converted = _wait(
            client,
            client.post(
                f'/api/workspaces/{wid}/convert',
                json={'feeders': list(FEEDERS), 'all': False},
            ).json(),
        )
        assert converted['status'] == 'done', converted
        summary = converted['result']['summary']
        assert {key: summary[key] for key in ('requested', 'ok', 'failed', 'skipped')} == {
            'requested': 4, 'ok': 4, 'failed': 0, 'skipped': 0,
        }
        assert summary['status'] == 'completed'
        assert summary['not_processed'] == 0
        assert converted['result']['workers'] == 2

        converted_rows = client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']
        converted_by_name = {row['feeder']: row for row in converted_rows}
        for feeder in FEEDERS:
            assert converted_by_name[feeder]['conversion']['status'] == 'ok'
            inventory = client.get(
                f'/api/workspaces/{wid}/electrical-inventory',
                params={'feeder': feeder, 'limit': 500},
            )
            assert inventory.status_code == 200, inventory.text
            body = inventory.json()
            assert body['total'] > 0
            assert {row['alimentador'] for row in body['rows']} == {feeder}

