from __future__ import annotations

import hashlib
import time

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402

from igea_dgs.web.app import create_app  # noqa: E402
from igea_dgs.web.workspace import Workspace  # noqa: E402
from synthetic_export import ExportSpec, write_export  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as test_client:
        yield test_client


def _workspace(client: TestClient) -> str:
    response = client.post('/api/workspaces')
    assert response.status_code == 201
    return response.json()['id']


def test_upload_records_sha256_size_and_original_name(client, tmp_path):
    wid = _workspace(client)
    content = b'[ALIAS]\nFORMAT_ALIAS=From,To\nA,B\n'

    response = client.post(
        f'/api/workspaces/{wid}/inputs/aliases',
        files={'file': ('catalogo original.json', content)},
    )

    assert response.status_code == 200
    meta = response.json()['workspace']['inputs']['aliases']
    assert meta['sha256'] == hashlib.sha256(content).hexdigest()
    assert meta['size'] == len(content)
    assert isinstance(meta['mtime_ns'], int)
    assert meta['original_name'] == 'catalogo original.json'
    assert meta['stale'] is False


def test_changed_input_invalidates_loaded_dataset_and_inventory(tmp_path):
    source = tmp_path / 'red.txt'
    source.write_text('version uno', encoding='utf-8')
    workspace = Workspace(id='abcdef12', root=tmp_path / 'workspace')
    workspace.set_input('red', source, origin='server')
    workspace.dataset = object()
    workspace.inventory = {'totals': {'feeders': 1}}
    workspace.load_inventory_cache[('dataset',)] = ('cached',)
    time.sleep(0.002)
    source.write_text('version dos con cambio', encoding='utf-8')

    public = workspace.public()

    assert workspace.dataset is None
    assert workspace.inventory is None
    assert workspace.load_inventory_cache == {}
    assert public['inputs']['red']['stale'] is True
    assert public['inputs']['red']['custody_error']
    assert public['missing_inputs']


def test_ambiguous_input_has_stable_error_code(client, tmp_path):
    red, _loads, _equipment = write_export(ExportSpec(feeders=1), tmp_path / 'export')
    wid = _workspace(client)
    files = [
        ('files', ('red_a.txt', red.read_bytes())),
        ('files', ('red_b.txt', red.read_bytes())),
    ]

    response = client.post(f'/api/workspaces/{wid}/inputs-auto', files=files)

    assert response.status_code == 200
    diagnostic = response.json()['unassigned'][0]
    assert diagnostic['code'] == 'INPUT_FILE_AMBIGUOUS'
    assert diagnostic['context'] == {'slot': 'red'}


def test_user_error_response_keeps_detail_and_adds_code_context(client):
    wid = _workspace(client)

    response = client.get(f'/api/workspaces/{wid}/electrical-inventory')

    assert response.status_code == 400
    assert response.json() == {
        'detail': 'Primero cargue y liste los alimentadores (paso 2).',
        'code': 'WORKSPACE_NOT_LOADED',
        'context': {'workspace_id': wid},
    }


def test_reloaded_workspace_revalidates_input_fingerprints(tmp_path):
    source = tmp_path / 'red.txt'
    source.write_text('original', encoding='utf-8')
    root = tmp_path / 'workspace'
    workspace = Workspace(id='abcdef12', root=root)
    workspace.set_input('red', source, origin='server')
    original_hash = workspace.inputs['red']['sha256']
    time.sleep(0.002)
    source.write_text('modificado', encoding='utf-8')

    reloaded = Workspace.load(root)

    assert reloaded.inputs['red']['sha256'] == original_hash
    assert reloaded.inputs['red']['stale'] is True
    assert reloaded.inputs['red']['current_sha256'] != original_hash
