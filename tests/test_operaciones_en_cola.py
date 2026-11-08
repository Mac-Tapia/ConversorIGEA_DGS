"""065:RF-18 / 065:RF-19: inferencia, catálogo y ZIP fuera del request."""
import io
import threading
import time
import zipfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from convertersmartgrid.web.app import create_app
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    with TestClient(create_app(tmp_path / 'datos')) as c:
        yield c


def _workspace(client):
    return client.post('/api/workspaces').json()['id']


def _finished(client, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get('/api/jobs/' + job_id).json()
        if result['status'] in {'done', 'failed', 'cancelled'}:
            return result
        time.sleep(.02)
    raise AssertionError('No terminó el trabajo')


def test_inferencia_puede_esperar_sin_retener_la_peticion(client, monkeypatch):
    """065:RF-18 — mientras el modelo espera, HTTP admite health y cancelación."""
    from convertersmartgrid.web import services
    entered, release = threading.Event(), threading.Event()
    def slow(ws, texto, trabajos):
        entered.set()
        assert release.wait(5)
        return {'plan': {'listo': False, 'texto': texto}}
    monkeypatch.setattr(services, 'asistente_orden', slow)
    try:
        r = client.post(f'/api/workspaces/{_workspace(client)}/asistente/orden', json={'texto': 'consulta'})
        assert r.status_code == 202
        assert entered.wait(2)
        assert client.get('/api/health').status_code == 200
        assert client.post('/api/jobs/' + r.json()['id'] + '/cancel').status_code == 200
    finally:
        release.set()
    assert _finished(client, r.json()['id'])['status'] == 'cancelled'


def test_refresh_vnr_se_encola_y_cache_se_consulta_sin_red(client, monkeypatch):
    """065:RF-18 — el catálogo lento tiene progreso y no bloquea el estado guardado."""
    import convertersmartgrid.adaptadores.entrada.vnr.discovery.official as official
    from convertersmartgrid.adaptadores.entrada.vnr.discovery.catalog import PublicationCatalog
    entered, release = threading.Event(), threading.Event()
    def slow(*args, **kw):
        entered.set()
        assert release.wait(5)
        return PublicationCatalog(), {'total': 0}
    monkeypatch.setattr(official, 'refresh_official_catalog', slow)
    try:
        r = client.post(f'/api/workspaces/{_workspace(client)}/vnr/publications/refresh')
        assert r.status_code == 202
        assert entered.wait(2)
        assert client.get('/api/vnr/publications').status_code == 200
        assert client.get('/api/health').status_code == 200
    finally:
        release.set()
    assert _finished(client, r.json()['id'])['status'] == 'done'


def test_zip_tiene_trabajo_y_descarga_controlada(client):
    """065:RF-18 / 065:RF-19 — ZIP conserva los archivos, pertenece al espacio y limpia scratch."""
    wid, other = _workspace(client), _workspace(client)
    ws = client.app.state.store.get(wid)
    source = ws.out_dir / 'A.dgs'
    source.write_bytes(b'contenido de A')
    r = client.post(f'/api/workspaces/{wid}/outputs/archive', json={'feeders': ['A']})
    assert r.status_code == 202
    job = _finished(client, r.json()['id'])
    assert job['status'] == 'done', job
    wrong = client.get(f'/api/workspaces/{other}/outputs.zip', params={'job': job['id']})
    assert wrong.status_code == 404
    download = client.get(job['result']['download'])
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.content)) as zf:
        assert zf.read('A.dgs') == b'contenido de A'
    assert source.read_bytes() == b'contenido de A'
    assert client.get(job['result']['download']).status_code == 410


def test_cuota_subida_conserva_entrada_previa_y_no_deja_parciales(client, monkeypatch):
    """065:RF-19 / 065:RF-12 — rechazar un archivo grande no borra la versión previa."""
    monkeypatch.setenv('CSG_UPLOAD_MAX_BYTES', '64')
    wid = _workspace(client)
    ws = client.app.state.store.get(wid)
    target = ws.upload_target('aliases', 'tipos.json')
    target.write_bytes(b'{"anterior": true}')
    r = client.post(f'/api/workspaces/{wid}/inputs/aliases',
                    files={'file': ('tipos.json', b'x' * 65, 'application/json')})
    assert r.status_code == 413
    assert target.read_bytes() == b'{"anterior": true}'
    assert not list(ws.root.rglob('*.part'))


def test_zip_sobre_cuota_no_publica_archivo(client, monkeypatch):
    """065:RF-19 — el presupuesto limita el trabajo real, no solo el Content-Length."""
    monkeypatch.setenv('CSG_ARCHIVE_MAX_BYTES', '64')
    wid = _workspace(client)
    ws = client.app.state.store.get(wid)
    (ws.out_dir / 'A.dgs').write_bytes(b'x' * 65)
    r = client.post(f'/api/workspaces/{wid}/outputs/archive', json={'feeders': ['A']})
    assert r.status_code == 202
    job = _finished(client, r.json()['id'])
    assert job['status'] == 'failed'
    assert 'cuota' in job['error'].lower()
    assert (ws.out_dir / 'A.dgs').is_file()
