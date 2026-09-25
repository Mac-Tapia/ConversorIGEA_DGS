"""La API web recorre el mismo camino que la GUI de escritorio, con el mismo motor.

Se usa el export sintético: no depende de los TXT reales y ejercita las dos
disposiciones de export (ver ``tests/synthetic_export.py``).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402

from synthetic_export import ExportSpec, write_export  # noqa: E402
from igea_dgs.web.app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def export(tmp_path):
    return write_export(ExportSpec(feeders=3), tmp_path / 'export')


def _wait(client, job: dict, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state['status'] in ('done', 'failed', 'cancelled'):
            return state
        time.sleep(0.05)
    raise AssertionError(f'el trabajo {job["title"]} no terminó en {timeout} s')


def _workspace(client) -> str:
    r = client.post('/api/workspaces')
    assert r.status_code == 201
    return r.json()['id']


def _upload(client, wid: str, slot: str, path: Path) -> dict:
    with path.open('rb') as fh:
        r = client.post(f'/api/workspaces/{wid}/inputs/{slot}', files={'file': (path.name, fh)})
    assert r.status_code == 200, r.text
    return r.json()


def _loaded(client, export, *, geography: bool = False) -> str:
    wid = _workspace(client)
    red, loads, equip = export
    for slot, path in (('red', red), ('loads', loads), ('equipment', equip)):
        _upload(client, wid, slot, path)
    client.put(f'/api/workspaces/{wid}/options', json={'include_geography': geography})
    job = client.post(f'/api/workspaces/{wid}/load').json()
    state = _wait(client, job)
    assert state['status'] == 'done', state
    return wid


def test_health_expone_capacidades_y_presets_sin_crs_en_grados(client):
    body = client.get('/api/health').json()
    assert {'geography', 'xlsx', 'access'} <= set(body['capabilities'])
    codes = [p['code'] for p in body['crs_presets']]
    assert 'EPSG:4326' not in codes, 'un CRS en grados falsea las longitudes (C-01)'


def test_flujo_completo_subir_cargar_convertir_descargar(client, export):
    wid = _loaded(client, export)
    feeders = client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']
    assert len(feeders) == 3
    name = feeders[0]['feeder']

    job = client.post(f'/api/workspaces/{wid}/convert', json={'feeders': [name]}).json()
    state = _wait(client, job)
    assert state['status'] == 'done', state
    assert state['result']['summary']['ok'] == 1

    row = next(f for f in client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']
               if f['feeder'] == name)
    assert row['conversion']['status'] == 'ok'
    assert row['conversion']['dgs'] == f'{name}.dgs'

    dgs = client.get(f'/api/workspaces/{wid}/files/{name}.dgs', params={'download': 1})
    assert dgs.status_code == 200 and len(dgs.content) > 100
    z = client.get(f'/api/workspaces/{wid}/outputs.zip', params={'feeder': [name]})
    assert z.status_code == 200 and z.content[:2] == b'PK'


def test_el_estado_de_conversion_se_acumula_entre_lotes(client, export):
    """batch_manifest.json solo recuerda el último lote; la tabla recuerda todos."""
    wid = _loaded(client, export)
    names = [f['feeder'] for f in client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']]
    for name in names[:2]:
        _wait(client, client.post(f'/api/workspaces/{wid}/convert', json={'feeders': [name]}).json())
    rows = client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']
    assert sum(1 for r in rows if r['conversion'] and r['conversion']['status'] == 'ok') == 2


def test_el_registro_numera_los_eventos_para_no_perder_lineas(client, export):
    wid = _loaded(client, export)
    events = client.get(f'/api/workspaces/{wid}/events').json()
    seqs = [e['seq'] for e in events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    assert any('Carga e inventario' in e['data'].get('text', '') for e in events if e['type'] == 'log')
    later = client.get(f'/api/workspaces/{wid}/events', params={'since': seqs[-1]}).json()
    assert later == []


def test_websocket_entrega_el_registro(client, export):
    wid = _loaded(client, export)
    with client.websocket_connect(f'/api/workspaces/{wid}/ws?since=0') as ws:
        batch = ws.receive_json()
    assert batch and batch[0]['seq'] == 1


def test_un_fichero_en_la_casilla_equivocada_avisa_pero_entra(client, export):
    red, loads, equip = export
    wid = _workspace(client)
    body = _upload(client, wid, 'loads', equip)
    assert body['warning'], 'el catálogo en la casilla de CARGA debe avisar'
    assert body['workspace']['inputs']['loads']['name'] == equip.name


def test_asignacion_automatica_por_contenido(client, export):
    wid = _workspace(client)
    files = [('files', (p.name, p.read_bytes())) for p in reversed(export)]
    body = client.post(f'/api/workspaces/{wid}/inputs-auto', files=files).json()
    assert {a['slot'] for a in body['assigned']} == {'red', 'loads', 'equipment'}
    assert body['workspace']['missing_inputs'] == []


def test_convertir_sin_cargar_es_error_de_usuario_y_no_500(client, export):
    wid = _workspace(client)
    for slot, path in zip(('red', 'loads', 'equipment'), export):
        _upload(client, wid, slot, path)
    r = client.post(f'/api/workspaces/{wid}/convert', json={'all': True})
    assert r.status_code == 400
    assert 'Primero cargue' in r.json()['detail']


def test_crs_en_grados_se_rechaza_antes_de_convertir(client, export):
    pytest.importorskip('pyproj')
    wid = _loaded(client, export, geography=True)
    r = client.put(f'/api/workspaces/{wid}/options', json={'source_crs': 'EPSG:4326'})
    assert r.json()['warning']
    r = client.post(f'/api/workspaces/{wid}/convert', json={'all': True})
    assert r.status_code == 400


def test_cambiar_una_entrada_invalida_lo_cargado(client, export):
    wid = _loaded(client, export)
    assert client.get(f'/api/workspaces/{wid}').json()['loaded']
    _upload(client, wid, 'loads', export[1])
    assert not client.get(f'/api/workspaces/{wid}').json()['loaded']


def test_no_se_sirven_ficheros_fuera_de_la_salida(client, export):
    wid = _workspace(client)
    r = client.get(f'/api/workspaces/{wid}/files/../workspace.json')
    assert r.status_code in (400, 404)


def test_el_espacio_sobrevive_a_un_reinicio(tmp_path, export, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    root = tmp_path / 'web'
    with TestClient(create_app(root)) as c:
        wid = _workspace(c)
        _upload(c, wid, 'red', export[0])
        c.put(f'/api/workspaces/{wid}/options', json={'source_crs': 'EPSG:32717'})
    with TestClient(create_app(root)) as c:
        body = c.get(f'/api/workspaces/{wid}').json()
    assert body['inputs']['red']['name'] == export[0].name
    assert body['options']['source_crs'] == 'EPSG:32717'
    assert body['loaded'] is False, 'el dataset no se persiste: se vuelve a cargar'


def test_plantilla_de_cargas_y_plan_sin_powerfactory(client, export):
    pytest.importorskip('openpyxl')
    wid = _loaded(client, export)
    name = client.get(f'/api/workspaces/{wid}/feeders').json()['feeders'][0]['feeder']
    r = client.get(f'/api/workspaces/{wid}/feeders/{name}/load-template', params={'format': 'csv'})
    if r.status_code == 400:
        pytest.skip(r.json()['detail'])
    assert r.status_code == 200
    plan = client.post(f'/api/workspaces/{wid}/feeders/{name}/load-plan',
                       files={'file': (f'{name}_cargas.csv', r.content)})
    assert plan.status_code == 200, plan.text
    body = plan.json()
    assert body['token'] and body['feeder'] == name
    assert 'summary' in body


def test_procesos_en_paralelo_se_eligen_y_se_validan(client):
    health = client.get('/api/health').json()
    assert health['parallel']['auto'] >= 1 and health['parallel']['cpus'] >= 1
    assert health['default_options']['workers'] == 0, 'automático por defecto'

    wid = _workspace(client)
    r = client.put(f'/api/workspaces/{wid}/options', json={'workers': 2})
    assert r.status_code == 200 and r.json()['options']['workers'] == 2
    for fuera_de_rango in (-1, 999):
        r = client.put(f'/api/workspaces/{wid}/options', json={'workers': fuera_de_rango})
        assert r.status_code == 422, fuera_de_rango


def test_convertir_en_paralelo_da_lo_mismo_que_en_serie(client, tmp_path):
    export = write_export(ExportSpec(feeders=5, sections_per_feeder=6, seed=7), tmp_path / 'export')
    resultados = {}
    for workers in (1, 2):
        wid = _loaded(client, export)
        client.put(f'/api/workspaces/{wid}/options', json={'workers': workers})
        job = client.post(f'/api/workspaces/{wid}/convert', json={'all': True}).json()
        state = _wait(client, job, timeout=120)
        assert state['status'] == 'done', state
        assert state['result']['workers'] == workers
        assert state['result']['summary']['ok'] == 5
        nombres = [f['feeder'] for f in client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']]
        resultados[workers] = {
            n: client.get(f'/api/workspaces/{wid}/files/{n}.dgs', params={'download': 1}).content
            for n in nombres
        }
    assert resultados[1] == resultados[2]
