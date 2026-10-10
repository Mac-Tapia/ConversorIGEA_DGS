"""La API web recorre el mismo camino que la GUI de escritorio, con el mismo motor.

Se usa el export sintético: no depende de los TXT reales y ejercita las dos
disposiciones de export (ver ``tests/synthetic_export.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')

from fastapi.testclient import TestClient  # noqa: E402

from synthetic_export import ExportSpec, write_export  # noqa: E402
from igea_dgs.web.app import create_app  # noqa: E402

from apoyo import esperar_trabajo  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def export(tmp_path):
    return write_export(ExportSpec(feeders=3), tmp_path / 'export')


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
    state = esperar_trabajo(client, job)
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
    state = esperar_trabajo(client, job)
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
        esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/convert', json={'feeders': [name]}).json())
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
        state = esperar_trabajo(client, job, timeout=120)
        assert state['status'] == 'done', state
        assert state['result']['workers'] == workers
        assert state['result']['summary']['ok'] == 5
        nombres = [f['feeder'] for f in client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']]
        resultados[workers] = {
            n: client.get(f'/api/workspaces/{wid}/files/{n}.dgs', params={'download': 1}).content
            for n in nombres
        }
    assert resultados[1] == resultados[2]


# ------------------------------------------------------------ rutas del disco del servidor
def _ruta_local(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'no-frontend'))
    red, _carga, _equipo = write_export(ExportSpec(feeders=2), tmp_path / 'e')
    with TestClient(create_app(tmp_path / 'web', **kwargs)) as c:
        wid = c.post('/api/workspaces').json()['id']
        health = c.get('/api/health').json()
        r = c.post(f'/api/workspaces/{wid}/inputs/red/path', json={'path': str(red)})
    return health['server_paths'], r.status_code


@pytest.mark.parametrize('host', ['0.0.0.0', '192.168.1.20', '::'])
def test_rutas_locales_cerradas_si_escucha_en_red_aunque_la_variable_diga_1(
        tmp_path, monkeypatch, host):
    """001:RF-15 — con host de red, 403 en /inputs/{slot}/path aunque IGEA_WEB_SERVER_PATHS=1."""
    monkeypatch.setenv('IGEA_WEB_SERVER_PATHS', '1')
    assert _ruta_local(tmp_path, monkeypatch, host=host) == (False, 403)


def test_rutas_locales_cerradas_si_no_se_sabe_donde_escucha(tmp_path, monkeypatch):
    """001:RF-15 — sin host (p. ej. `uvicorn --factory` a mano), cerradas por defecto."""
    monkeypatch.delenv('IGEA_WEB_HOST', raising=False)
    monkeypatch.setenv('IGEA_WEB_SERVER_PATHS', '1')
    assert _ruta_local(tmp_path, monkeypatch) == (False, 403)


def test_rutas_locales_abiertas_en_loopback_y_apagables(tmp_path, monkeypatch):
    """001:RF-15 — en 127.0.0.1 se admiten; la variable solo puede apagarlas."""
    monkeypatch.delenv('IGEA_WEB_SERVER_PATHS', raising=False)
    assert _ruta_local(tmp_path / 'a', monkeypatch, host='127.0.0.1') == (True, 200)
    monkeypatch.setenv('IGEA_WEB_HOST', 'localhost')
    assert _ruta_local(tmp_path / 'b', monkeypatch) == (True, 200)
    monkeypatch.setenv('IGEA_WEB_SERVER_PATHS', '0')
    assert _ruta_local(tmp_path / 'c', monkeypatch, host='127.0.0.1') == (False, 403)


def test_el_lanzador_pasa_la_interfaz_de_escucha_a_la_api(monkeypatch):
    """001:RF-15 — `igea-dgs-web --host` llega a create_app, que con factory=True no tiene argumentos."""
    import sys
    import types

    from igea_dgs.web import __main__ as lanzador

    llamadas = []
    monkeypatch.setitem(sys.modules, 'uvicorn', types.SimpleNamespace(
        run=lambda *a, **k: llamadas.append(k)))
    monkeypatch.delenv('IGEA_WEB_HOST', raising=False)
    monkeypatch.setenv('IGEA_WEB_SERVER_PATHS', '1')
    assert lanzador.main(['--host', '0.0.0.0', '--no-browser']) == 0
    assert llamadas and llamadas[0]['host'] == '0.0.0.0'
    import os
    assert os.environ['IGEA_WEB_HOST'] == '0.0.0.0'



# ------------------------------------------------------------ interruptores de conversión
# Cada interruptor del panel «Opciones de conversión» deja su fichero en la salida, tanto
# al convertir alimentadores sueltos como al unirlos. La red unida solo recibía «strict»:
# salía siempre georreferenciada y sin Excel, sin TSV y sin mapa, con los interruptores
# encendidos.
_INTERRUPTORES = {
    'write_preview': ('_preview.html', '_preview.geojson'),
    'export_xlsx': ('.xlsx',),
    'export_tsv': ('_dgs_tables/ElmLne.tsv',),
}


def _salidas(client, wid: str) -> set[str]:
    return {o['path'] for o in client.get(f'/api/workspaces/{wid}/outputs').json()}


def _convertir(client, wid: str, cuerpo: dict) -> dict:
    state = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/convert', json=cuerpo).json(),
                            timeout=120)
    assert state['status'] == 'done', state
    return state


@pytest.mark.parametrize('unir', [False, True], ids=['suelto', 'red_unida'])
@pytest.mark.parametrize('opcion', sorted(_INTERRUPTORES))
def test_cada_interruptor_deja_su_fichero(client, export, opcion, unir):
    wid = _loaded(client, export, geography=True)
    nombres = [f['feeder'] for f in client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']]
    r = client.put(f'/api/workspaces/{wid}/options', json={opcion: True})
    assert r.status_code == 200 and r.json()['options'][opcion] is True
    if unir:
        _convertir(client, wid, {'feeders': nombres[:2], 'unir': True, 'nombre': 'RED'})
        base = 'RED'
    else:
        _convertir(client, wid, {'feeders': nombres[:1]})
        base = nombres[0]
    salidas = _salidas(client, wid)
    assert f'{base}.dgs' in salidas
    for sufijo in _INTERRUPTORES[opcion]:
        assert f'{base}{sufijo}' in salidas, sorted(salidas)
    # Y apagado no deja nada: el fichero sale del interruptor, no de un valor por defecto.
    for otra, sufijos in _INTERRUPTORES.items():
        if otra != opcion:
            assert not any(f'{base}{s}' in salidas for s in sufijos), (otra, sorted(salidas))


def test_la_red_unida_trae_su_mapa_para_la_pestana_de_resultados(client, export):
    wid = _loaded(client, export, geography=True)
    nombres = [f['feeder'] for f in client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']]
    client.put(f'/api/workspaces/{wid}/options', json={'write_preview': True, 'export_xlsx': True})
    _convertir(client, wid, {'feeders': nombres[:2], 'unir': True, 'nombre': 'RED'})
    grupo = next(g for g in client.get(f'/api/workspaces/{wid}').json()['groups'] if g['name'] == 'RED')
    assert grupo['preview_html'] == 'RED_preview.html'
    assert grupo['xlsx'] == 'RED.xlsx'


@pytest.mark.parametrize('unir', [False, True], ids=['suelto', 'red_unida'])
def test_sin_georreferenciacion_no_hay_gps_ni_diagrama(client, export, unir):
    nombres_dgs = {}
    for geo in (True, False):
        wid = _loaded(client, export, geography=geo)
        nombres = [f['feeder'] for f in client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']]
        if unir:
            _convertir(client, wid, {'feeders': nombres[:2], 'unir': True, 'nombre': 'RED'})
            base = 'RED'
        else:
            _convertir(client, wid, {'feeders': nombres[:1]})
            base = nombres[0]
        assert (f'{base}_geography.json' in _salidas(client, wid)) is geo
        nombres_dgs[geo] = client.get(f'/api/workspaces/{wid}/files/{base}.dgs',
                                      params={'download': 1}).content.decode('utf-8', 'replace')
    assert 'IntGrf' in nombres_dgs[True]
    assert 'IntGrf' not in nombres_dgs[False]


@pytest.mark.parametrize('unir', [False, True], ids=['suelto', 'red_unida'])
def test_el_modo_estricto_llega_al_motor(client, export, monkeypatch, unir):
    from igea_dgs import batch

    vistos = []
    original = batch.build_feeder_model

    def espia(*args, **kwargs):
        vistos.append(kwargs.get('strict'))
        return original(*args, **kwargs)

    monkeypatch.setattr(batch, 'build_feeder_model', espia)
    wid = _loaded(client, export)
    nombres = [f['feeder'] for f in client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']]
    client.put(f'/api/workspaces/{wid}/options', json={'strict': False, 'workers': 1})
    cuerpo = ({'feeders': nombres[:2], 'unir': True, 'nombre': 'RED'} if unir
              else {'feeders': nombres[:1]})
    _convertir(client, wid, cuerpo)
    assert vistos and all(v is False for v in vistos), vistos


def test_vista_previa_sin_georreferenciacion_se_rechaza_tambien_al_unir(client, export):
    wid = _loaded(client, export)
    nombres = [f['feeder'] for f in client.get(f'/api/workspaces/{wid}/feeders').json()['feeders']]
    client.put(f'/api/workspaces/{wid}/options', json={'write_preview': True})
    r = client.post(f'/api/workspaces/{wid}/convert',
                    json={'feeders': nombres[:2], 'unir': True, 'nombre': 'RED'})
    assert r.status_code == 400, r.text
    assert 'georreferenciación' in r.json()['detail']
