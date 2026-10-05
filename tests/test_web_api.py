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


def test_powerfactory_usa_un_dgs_unido_para_la_seleccion_exacta(tmp_path):
    import os

    from igea_dgs.web.services import dgs_jobs
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path)
    ws.out_dir.mkdir(parents=True)
    for name in ('AL101', 'AL102', 'RED_UNIDA'):
        (ws.out_dir / f'{name}.dgs').write_text('DGS', encoding='ascii')
    ws.groups['RED_UNIDA'] = {
        'name': 'RED_UNIDA', 'feeders': ['AL101', 'AL102'], 'status': 'ok',
        'converted_at': 20.0,
    }
    ws.conversions = {
        'NET_AL101': {'feeder': 'AL101', 'converted_at': 10.0},
        'NET_AL102': {'feeder': 'AL102', 'converted_at': 11.0},
    }

    jobs, missing = dgs_jobs(ws, ['AL101', 'AL102'])
    assert [job[0] for job in jobs] == ['RED_UNIDA']
    assert missing == []

    ws.groups['RED_UNIDA'] = {
        'name': 'RED_UNIDA', 'feeders': ['AL101', 'AL102', 'AL103'],
        'requested_feeders': ['AL101', 'AL102'], 'status': 'ok',
        'converted_at': 20.0,
    }
    (ws.out_dir / 'AL103.dgs').write_text('DGS', encoding='ascii')
    jobs, missing = dgs_jobs(ws, ['AL101', 'AL102'])
    assert [job[0] for job in jobs] == ['RED_UNIDA']
    assert missing == []

    ws.conversions['NET_AL103'] = {'feeder': 'AL103', 'converted_at': 21.0}
    jobs, missing = dgs_jobs(ws, ['AL101', 'AL102'])
    assert [job[0] for job in jobs] == ['AL101', 'AL102']
    assert missing == []

    ws.conversions['NET_AL102']['converted_at'] = 21.0
    jobs, missing = dgs_jobs(ws, ['AL101', 'AL102'])
    assert [job[0] for job in jobs] == ['AL101', 'AL102']
    assert missing == []

    ws.groups['RED_UNIDA'] = {
        'name': 'RED_UNIDA', 'feeders': ['AL101', 'AL102'], 'status': 'ok',
    }
    os.utime(ws.out_dir / 'AL101.dgs', ns=(10_000, 10_000))
    os.utime(ws.out_dir / 'AL102.dgs', ns=(11_000, 11_000))
    os.utime(ws.out_dir / 'RED_UNIDA.dgs', ns=(20_000, 20_000))
    jobs, missing = dgs_jobs(ws, ['AL101', 'AL102'])
    assert [job[0] for job in jobs] == ['RED_UNIDA']
    assert missing == []

    os.utime(ws.out_dir / 'AL102.dgs', ns=(21_000, 21_000))
    jobs, missing = dgs_jobs(ws, ['AL101', 'AL102'])
    assert [job[0] for job in jobs] == ['AL101', 'AL102']
    assert missing == []


def test_powerfactory_importa_dgs_aunque_pandapower_avise_isla(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from igea_dgs.web import services
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path)
    dgs = ws.out_dir / 'RED.dgs'
    dgs.parent.mkdir(parents=True)
    dgs.write_text('DGS', encoding='ascii')
    dgs.with_name('RED_feeder_metadata.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(services, 'dgs_jobs', lambda _ws, _feeders: ([('RED', dgs, None)], []))
    monkeypatch.setattr(services, '_script', lambda _name: tmp_path / 'script.py')
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, tmp_path / 'python.exe'))
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda _pf_dir: {})
    monkeypatch.setattr(services, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(services, 'powerfactory_status', lambda: {'interpreter_reason': 'test'})
    monkeypatch.setattr(services, 'pandapower_preflight', lambda *_args: {
        'disponible': True,
        'import_continued': True,
        'avisos': ['PE104: 2 barras sin alimentar. Se continúa con el import DGS completo.'],
        'feeders': [{'feeder': 'PE104', 'barras_sin_alimentar': 2}],
    })
    logs: list[str] = []
    commands: list[list[str]] = []
    ctx = SimpleNamespace(
        log=logs.append,
        progress=lambda *_args: None,
        check_cancel=lambda: None,
        run_process=lambda command, **_kwargs: commands.append(command) or 0,
    )

    result = services.powerfactory_flow(ws, ctx, ['RED'])

    assert result['ok'] == 1
    assert result['preflight']['feeders'][0]['barras_sin_alimentar'] == 2
    assert len(commands) == 1
    assert commands[0][commands[0].index('--import-dgs') + 1] == str(dgs)
    assert commands[0][commands[0].index('--feeder-metadata') + 1] == str(
        dgs.with_name('RED_feeder_metadata.json'))
    assert 'Se continúa con el import DGS completo.' in '\n'.join(logs)


def test_check_powerfactory_exige_metadata_para_no_dejar_columna_vacia(tmp_path, monkeypatch):
    from igea_dgs.web import services
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='w', root=tmp_path)
    ws.out_dir.mkdir(parents=True)
    (ws.out_dir / 'RED.dgs').write_text('DGS', encoding='ascii')
    monkeypatch.setattr(services, '_script', lambda _name: tmp_path / 'script.py')
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, tmp_path / 'python.exe'))

    with pytest.raises(services.UserError, match='Falta la trazabilidad por alimentador'):
        services.check_powerfactory_flow(ws, ['RED'])


def test_health_expone_capacidades_y_presets_sin_crs_en_grados(client):
    body = client.get('/api/health').json()
    assert {'geography', 'xlsx', 'access'} <= set(body['capabilities'])
    codes = [p['code'] for p in body['crs_presets']]
    assert 'EPSG:4326' not in codes, 'un CRS en grados falsea las longitudes (C-01)'


def test_hoja_null_activa_lienzo_dinamico(client):
    wid = _workspace(client)
    fijo = client.put(f'/api/workspaces/{wid}/options', json={'hoja': 'A0'})
    assert fijo.json()['options']['hoja'] == 'A0'
    automatico = client.put(f'/api/workspaces/{wid}/options', json={'hoja': None})
    assert automatico.json()['options']['hoja'] is None


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


def test_lote_de_cargas_reparte_un_excel_entre_alimentadores(client, export):
    """Un solo Excel con SED de dos alimentadores → un plan por alimentador, en el orden elegido."""
    openpyxl = pytest.importorskip('openpyxl')
    import csv
    import io

    wid = _loaded(client, export)
    nombres = [r['feeder'] for r in client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']]
    seds = {}
    for name in nombres:
        r = client.get(f'/api/workspaces/{wid}/feeders/{name}/load-template', params={'format': 'csv'})
        if r.status_code == 200:
            filas = list(csv.reader(io.StringIO(r.content.decode('utf-8-sig')), delimiter=';'))
            if len(filas) > 1:
                seds[name] = filas[1][1]                # primera SED (col 0 = feeder)
    if len(seds) < 2:
        pytest.skip('el export sintético no trae dos alimentadores con SED')
    a, b = list(seds)[:2]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'TODAS'                                  # no es ningún alimentador
    ws.append(['SED', 'Kw', 'Kvar', '(kVA)', 'FP'])
    ws.append([seds[a], 12, 4, None, None])
    ws.append([seds[b], None, None, 50, 0.9])
    buf = io.BytesIO()
    wb.save(buf)

    r = client.post(f'/api/workspaces/{wid}/lote/plan',
                    data={'project': 'PROYECTO_PF', 'feeders': [b, a]},
                    files={'update_file': ('cargas.xlsx', buf.getvalue())})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['kind'] == 'lote' and body['project'] == 'PROYECTO_PF'
    assert body['order'] == [b, a], 'el orden es el de la selección'
    assert {f['feeder']: f['updates'] for f in body['feeders_summary']} == {a: 1, b: 1}
    assert body['row_errors'] == [] and body['applicable'] is True


def test_lote_sin_ficheros_o_sin_alimentadores_es_error_de_usuario(client, export):
    wid = _loaded(client, export)
    name = client.get(f'/api/workspaces/{wid}/feeders').json()['feeders'][0]['feeder']
    r = client.post(f'/api/workspaces/{wid}/lote/plan', data={'project': 'P', 'feeders': [name]})
    assert r.status_code == 400 and 'Excel' in r.json()['detail']
    r = client.post(f'/api/workspaces/{wid}/lote/plan', data={'project': 'P', 'feeders': ['NO_EXISTE']},
                    files={'update_file': ('c.csv', b'SED;Kw\n')})
    assert r.status_code == 400 and 'NO_EXISTE' in r.json()['detail']


def test_aplicar_un_lote_que_no_existe_es_404(client, export):
    wid = _loaded(client, export)
    assert client.post(f'/api/workspaces/{wid}/lote/abc/apply').status_code == 404


def test_lote_con_evaluacion_tecnico_economica_valora_la_etapa(client, export):
    """Con costes, cada alimentador con SED nuevas lleva la inversión de su etapa."""
    openpyxl = pytest.importorskip('openpyxl')
    import io
    import json as _json

    wid = _loaded(client, export, geography=True)
    name = client.get(f'/api/workspaces/{wid}/feeders').json()['feeders'][0]['feeder']
    plantilla = client.get(f'/api/workspaces/{wid}/feeders/{name}/create-template', params={'format': 'xlsx'})
    if plantilla.status_code != 200:
        pytest.skip(plantilla.json()['detail'])
    nodos = openpyxl.load_workbook(io.BytesIO(plantilla.content))['nodos_validos']
    nodo = nodos['A2'].value
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = name
    ws.append(['SED', 'nodo_conexion', 'kVA_instalado', '(kVA)', 'FP'])
    ws.append(['SE_NUEVA_1', nodo, 100, 40, 0.9])
    buf = io.BytesIO()
    wb.save(buf)
    economia = {
        'costos': {'sed_fijo_usd': 1000, 'trafo_usd_por_kva': 50, 'linea_usd_por_km': 0},
        'tec': {'inicio': 2026, 'fin': 2046, 'interes_pct': 12, 'perdidas_usd_kwh': 0.1},
    }
    r = client.post(f'/api/workspaces/{wid}/lote/plan',
                    data={'project': 'P', 'feeders': [name], 'economia': _json.dumps(economia)},
                    files={'create_file': ('nuevas.xlsx', buf.getvalue())})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['tec']['inicio'] == 2026
    fila = body['feeders_summary'][0]
    assert fila['create'] == 1
    assert fila['inversion_kusd'] == pytest.approx(6.0)        # 1000 + 50·100 US$


def test_lote_economia_invalida_es_error_de_usuario(client, export):
    import json as _json

    wid = _loaded(client, export)
    name = client.get(f'/api/workspaces/{wid}/feeders').json()['feeders'][0]['feeder']
    malo = {'costos': {'trafo_usd_por_kva': 10}, 'tec': {'inicio': 2030, 'fin': 2020}}
    r = client.post(f'/api/workspaces/{wid}/lote/plan',
                    data={'project': 'P', 'feeders': [name], 'economia': _json.dumps(malo)},
                    files={'create_file': ('n.csv', b'SED;CoordX;CoordY;kVA_instalado\n')})
    assert r.status_code == 400 and 'anterior al de inicio' in r.json()['detail']
    r = client.post(f'/api/workspaces/{wid}/lote/plan',
                    data={'project': 'P', 'feeders': [name], 'economia': '{no es json'},
                    files={'create_file': ('n.csv', b'SED\n')})
    assert r.status_code == 422
