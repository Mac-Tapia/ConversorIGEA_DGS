"""Spec 004: la web del módulo de cargas en DIgSILENT, sin entradas cargadas.

DIgSILENT se sustituye por un guion falso con el mismo contrato que
``tools/cargas_pf.py`` (``--plan``, ``--output-json``, ``--simular``,
``--cancel-file``): así se prueba el camino web → trabajo → proceso → informe sin
PowerFactory (P11).
"""
from __future__ import annotations

import io
import json
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')
openpyxl = pytest.importorskip('openpyxl')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo, vincular_proyecto  # noqa: E402
from igea_dgs.web import services  # noqa: E402
from igea_dgs.web.app import create_app  # noqa: E402

# Imita a tools/cargas_pf.py: escribe un informe con lo que recibió. Con --cancel-file
# espera a que aparezca el fichero (como si estuviera a mitad de un alimentador) y
# termina «el alimentador en curso».
GUION_FALSO = textwrap.dedent('''
    import argparse, json, sys, time
    from pathlib import Path
    p = argparse.ArgumentParser()
    p.add_argument('--plan'); p.add_argument('--output-json')
    p.add_argument('--simular', action='store_true'); p.add_argument('--cancel-file')
    a = p.parse_args()
    plan = json.loads(Path(a.plan).read_text(encoding='utf-8'))
    informe = {'project': plan['project'], 'modo': 'simular' if a.simular else 'aplicar',
               'feeders': [], 'cancelado': False, 'avisos': [],
               'recibido': {'demandas': len(plan['demandas']), 'nuevas': len(plan['nuevas']),
                            'feeders': plan['feeders']}}
    espera = plan['project'] == 'ESPERAR_CANCELACION'
    for f in plan['feeders']:
        if a.cancel_file and Path(a.cancel_file).exists():
            informe['cancelado'] = True
            break
        print('== ' + f, flush=True)
        if espera:
            limite = time.time() + 20
            while not Path(a.cancel_file).exists() and time.time() < limite:
                time.sleep(0.05)
        informe['feeders'].append({'feeder': f})
    Path(a.output_json).write_text(json.dumps(informe), encoding='utf-8')
''')


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    guion = tmp_path / 'cargas_pf_falso.py'
    guion.write_text(GUION_FALSO, encoding='utf-8')
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, sys.executable))
    monkeypatch.setattr(services, '_script', lambda _nombre: guion)
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda _d: None)
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def _wid(client) -> str:
    return client.post('/api/workspaces').json()['id']


def _xlsx(filas: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    hoja = wb.active
    for fila in filas:
        hoja.append(fila)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _plan(client, wid, *, project='P', feeders=('F1',), demandas=None, nuevas=None,
          nueva=None, economia=None):
    vincular_proyecto(client, wid, project, feeders)
    files = {}
    if demandas is not None:
        files['update_file'] = ('demandas.xlsx', _xlsx(demandas))
    if nuevas is not None:
        files['create_file'] = ('nuevas.xlsx', _xlsx(nuevas))
    data = {'project': project, 'feeders': list(feeders)}
    if nueva is not None:
        data['nueva'] = json.dumps(nueva)
    if economia is not None:
        data['economia'] = economia if isinstance(economia, str) else json.dumps(economia)
    return client.post(f'/api/workspaces/{wid}/lote/plan', data=data, files=files or None)


DEMANDAS = [['SED', 'Kw', 'Kvar', '(kVA)', 'FP'], ['S1', 100, 20, '', ''], ['S2', '', '', 50, 0.9],
            ['S3', 'abc', '', '', '']]


def test_plan_sin_entradas_cargadas(client):
    """004:RF-1 — el plan se prepara en un espacio sin TXT, MDB ni conversión."""
    wid = _wid(client)
    assert client.get(f'/api/workspaces/{wid}').json()['loaded'] is False
    r = _plan(client, wid, feeders=['F1', 'F2'], demandas=DEMANDAS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [d['sed'] for d in body['demandas']] == ['S1', 'S2']
    assert body['applicable'] is True
    assert len(body['row_errors']) == 1 and 'fila 4' in body['row_errors'][0]


def test_uno_o_varios_alimentadores_en_el_orden_elegido(client):
    """004:RF-5 — el mismo plan para uno que para varios, en el orden de la selección."""
    wid = _wid(client)
    uno = _plan(client, wid, feeders=['B'], demandas=DEMANDAS).json()
    varios = _plan(client, wid, feeders=['C', 'A', 'B', 'A'], demandas=DEMANDAS).json()
    assert uno['feeders'] == ['B']
    assert varios['feeders'] == ['C', 'A', 'B']
    assert set(uno) == set(varios)


def test_carga_nueva_del_formulario_pasa_por_el_mismo_lector(client):
    """004:RF-41 — la carga nueva sola (formulario) y el libro en bloque comparten reglas."""
    wid = _wid(client)
    buena = {'SED': 'N1', 'barra': 'B7', 'kVA_instalado': 100, 'Kw': 40, 'FP': 0.95}
    r = _plan(client, wid, nueva=buena)
    assert r.status_code == 200, r.text
    assert [n['sed'] for n in r.json()['nuevas']] == ['N1']
    mala = _plan(client, wid, nueva={'SED': 'N2', 'barra': 'B7', 'Kw': 40}).json()
    assert mala['applicable'] is False
    assert 'kVA_instalado' in mala['row_errors'][0]
    libro = _plan(client, wid, nuevas=[list(buena), list(buena.values())], nueva=buena | {'SED': 'N9'})
    # 008:RF-24: el formulario va delante del libro.
    assert [n['sed'] for n in libro.json()['nuevas']] == ['N9', 'N1']


def test_errores_de_usuario(client):
    """004:RF-1 — sin libros, sin proyecto o con economía mala: 400/422 con el motivo."""
    wid = _wid(client)
    r = _plan(client, wid)
    assert r.status_code == 400 and 'libro' in r.json()['detail']
    r = _plan(client, wid, project=' ', demandas=DEMANDAS)
    assert r.status_code == 400 and 'proyecto' in r.json()['detail']
    malo = {'costos': {'trafo_usd_por_kva': 10}, 'tec': {'inicio': 2030, 'fin': 2020}}
    r = _plan(client, wid, nueva={'SED': 'N', 'barra': 'B', 'kVA_instalado': 50, 'Kw': 5}, economia=malo)
    assert r.status_code == 400 and 'anterior al de inicio' in r.json()['detail']
    r = _plan(client, wid, demandas=DEMANDAS, economia='{no es json')
    assert r.status_code == 422
    assert client.post(f'/api/workspaces/{wid}/lote/abc/apply').status_code == 404


def test_plantillas_vacias(client):
    """004:RF-1 — las plantillas se descargan sin modelo: solo la cabecera."""
    wid = _wid(client)
    for tipo, columna in (('demandas', 'Kw'), ('nuevas', 'kVA_instalado')):
        r = client.get(f'/api/workspaces/{wid}/cargas/plantilla/{tipo}', params={'format': 'csv'})
        assert r.status_code == 200
        lineas = r.content.decode('utf-8-sig').strip().splitlines()
        assert len(lineas) == 1 and columna in lineas[0]


def test_rutas_por_alimentador_retiradas(client):
    """004:RF-5 — no quedan las rutas que necesitaban el modelo de la conversión."""
    wid = _wid(client)
    for ruta in ('feeders/F1/load-template', 'feeders/F1/create-template'):
        assert client.get(f'/api/workspaces/{wid}/{ruta}').status_code in (404, 405)
    for ruta in ('feeders/F1/load-plan', 'feeders/F1/create-plan', 'plans/abc/apply'):
        assert client.post(f'/api/workspaces/{wid}/{ruta}').status_code in (404, 405)


def test_simular_es_un_trabajo_que_no_aplica(client):
    """004:RF-17 — «Simular» lanza el guion con --simular en el carril de DIgSILENT."""
    wid = _wid(client)
    token = _plan(client, wid, feeders=['F1', 'F2'], demandas=DEMANDAS).json()['token']
    job = client.post(f'/api/workspaces/{wid}/lote/{token}/simular')
    assert job.status_code == 202 and job.json()['lane'] == 'powerfactory'
    estado = esperar_trabajo(client, job.json())
    assert estado['status'] == 'done', estado
    informe = estado['result']['informe']
    assert informe['modo'] == 'simular'
    assert informe['recibido'] == {'demandas': 2, 'nuevas': 0, 'feeders': ['F1', 'F2']}


def test_aplicar_devuelve_el_informe_por_alimentador(client):
    """004:RF-20 — el trabajo de aplicar deja el informe del guion, por alimentador."""
    wid = _wid(client)
    token = _plan(client, wid, feeders=['F1', 'F2'], demandas=DEMANDAS).json()['token']
    estado = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/lote/{token}/apply').json())
    assert estado['status'] == 'done', estado
    assert estado['result']['modo'] == 'aplicar'
    assert [f['feeder'] for f in estado['result']['informe']['feeders']] == ['F1', 'F2']


def test_cancelar_avisa_al_guion_y_conserva_el_informe(client):
    """004:RF-19 — cancelar crea el fichero; el guion acaba el alimentador y no empieza otro."""
    wid = _wid(client)
    token = _plan(client, wid, project='ESPERAR_CANCELACION', feeders=['F1', 'F2', 'F3'],
                  demandas=DEMANDAS).json()['token']
    job = client.post(f'/api/workspaces/{wid}/lote/{token}/apply').json()
    limite = time.time() + 20
    while time.time() < limite:
        if client.get(f"/api/jobs/{job['id']}").json()['status'] == 'running':
            break
        time.sleep(0.05)
    time.sleep(0.5)
    client.post(f"/api/jobs/{job['id']}/cancel")
    estado = esperar_trabajo(client, job)
    assert estado['status'] == 'cancelled'
    informe = estado['result']['informe']
    assert informe['cancelado'] is True
    assert [f['feeder'] for f in informe['feeders']] == ['F1'], 'F1 terminó entero; F2 no empezó'


def test_un_plan_de_cargas_sobrevive_a_cambiar_las_entradas(client, tmp_path):
    """004:RF-1 — cargar otro TXT no tira el plan de cargas, que no depende de él."""
    from synthetic_export import ExportSpec, write_export

    wid = _wid(client)
    token = _plan(client, wid, demandas=DEMANDAS).json()['token']
    red, _c, _e = write_export(ExportSpec(feeders=1), tmp_path / 'e')
    with red.open('rb') as fh:
        client.post(f'/api/workspaces/{wid}/inputs/red', files={'file': (red.name, fh)})
    assert client.post(f'/api/workspaces/{wid}/lote/{token}/simular').status_code == 202


def test_el_plan_lleva_la_ruta_y_la_carpeta(client):
    """005:RF-16 — el plan identifica el proyecto por su ruta y lleva la carpeta del perfil."""
    from igea_dgs.web import services

    wid = _wid(client)
    r = _plan(client, wid, project='Oct/SI213', demandas=DEMANDAS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['project'] == 'Oct/SI213' and body['folder'] == services.carpeta_pf()


def test_formulario_delante_del_libro(client):
    """008:RF-24 — la carga del formulario se aplica antes que las del libro."""
    wid = _wid(client)
    fila = {'SED': 'L1', 'barra': 'B1', 'kVA_instalado': 50, 'Kw': 20, 'FP': 0.9}
    libro = [list(fila), list(fila.values()), list((fila | {'SED': 'L2'}).values())]
    r = _plan(client, wid, nuevas=libro, nueva=fila | {'SED': 'FORM'}, demandas=DEMANDAS)
    assert [n['sed'] for n in r.json()['nuevas']] == ['FORM', 'L1', 'L2']


VERIFICAR_FALSO = textwrap.dedent('''
    import argparse, json
    from pathlib import Path
    p = argparse.ArgumentParser(); p.add_argument('--plan'); p.add_argument('--output-json')
    a = p.parse_args()
    plan = json.loads(Path(a.plan).read_text(encoding='utf-8'))
    informe = {'project': plan['project'], 'modo': 'verificar',
               'flujo': {'converged': plan['project'] != 'NO_CONVERGE'},
               'feeders': [{'feeder': f, 'cabecera': {'kw': 1.0, 'kvar': 0.5}} for f in plan['feeders']]}
    Path(a.output_json).write_text(json.dumps(informe), encoding='utf-8')
''')


def test_verificar_convergencia_es_un_trabajo(client, tmp_path, monkeypatch):
    """008:RF-18 / 008:RF-19 — la verificación va al carril powerfactory y devuelve el informe
    del guion; sin proyecto, 422."""
    guion = tmp_path / 'verificar_falso.py'
    guion.write_text(VERIFICAR_FALSO, encoding='utf-8')
    monkeypatch.setattr(services, '_script', lambda _nombre: guion)
    wid = _wid(client)
    url = f'/api/workspaces/{wid}/powerfactory/verificar'
    assert client.post(url, json={'project': ' ', 'feeders': []}).status_code == 422
    for proyecto, converge in (('P', True), ('NO_CONVERGE', False)):
        vincular_proyecto(client, wid, proyecto, ['F1', 'F2'])
        trabajo = client.post(url, json={'project': proyecto, 'feeders': ['F1', 'F2', 'F1']})
        assert trabajo.status_code == 202 and trabajo.json()['lane'] == 'powerfactory'
        estado = esperar_trabajo(client, trabajo.json())
        assert estado['status'] == 'done', estado
        informe = estado['result']['informe']
        assert informe['flujo']['converged'] is converge
        assert [f['feeder'] for f in informe['feeders']] == ['F1', 'F2']


# ----------------------------------------------------------------- spec 007
def _ajuste(client, wid, kind='ajuste_aplicar', project='P', informes=None):
    """Un trabajo de ajuste terminado en el espacio, sin pasar por DIgSILENT."""
    informes = informes if informes is not None else [
        {'feeder': 'F1', 'variacion': 'Ajuste_F1_20261009_120000', 'cuadrado': True,
         'desvio': {'kw': -0.001, 'kvar': 0.002}, 'cabecera': {'kw': 500.0, 'kvar': 90.0},
         'sed': [{'sed': 'S1', 'despues': {'kw': 40.0, 'kvar': 9.0}}]},
        {'feeder': 'F2', 'error': 'F2 no tiene ElmFeeder con cabecera'},
    ]
    resultado = {'project': project, 'informes': informes, 'informe': informes[0]}
    job = client.app.state.jobs.submit(wid, kind, 'ajuste', lambda ctx: resultado, lane='powerfactory')
    assert esperar_trabajo(client, job.public())['status'] == 'done'
    return job.id


def test_plan_con_la_base_del_ajuste(client):
    """007:RF-1 / 007:RF-2 / 007:RF-21 / 007:RF-37 — el plan toma la base del ajuste aplicado del
    mismo proyecto: sus variaciones, si cuadró, las SED calibradas que el libro cambia y los
    alimentadores que quedaron fuera."""
    wid = _wid(client)
    job = _ajuste(client, wid)
    vincular_proyecto(client, wid, 'P', ['F1'])
    data = {'project': 'P', 'feeders': ['F1'], 'ajuste_job_id': job}
    r = client.post(f'/api/workspaces/{wid}/lote/plan', data=data,
                    files={'update_file': ('d.xlsx', _xlsx([['SED', 'Kw', 'Kvar'], ['S1', 55, 12]]))})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['base']['variaciones'] == ['Ajuste_F1_20261009_120000']
    assert body['base']['ajustes'][0]['cuadrado'] is True
    assert body['calibradas_cambiadas'][0]['sed'] == 'S1'
    assert any(a.startswith('F2 queda fuera de la base') for a in body['avisos'])
    plan = json.loads(Path(client.app.state.store.get(wid).cargas_planes[body['token']]['path'])
                      .read_text(encoding='utf-8'))
    assert plan['base']['variaciones'] == ['Ajuste_F1_20261009_120000']


def test_base_de_otro_proyecto_o_de_una_simulacion_se_rechaza(client):
    """007:RF-1 / 007:RF-4 — la base es un ajuste aplicado del mismo proyecto; sin ella, sin base."""
    wid = _wid(client)
    url = f'/api/workspaces/{wid}/lote/plan'
    libro = {'update_file': ('d.xlsx', _xlsx(DEMANDAS))}
    otro = _ajuste(client, wid, project='OTRO')
    vincular_proyecto(client, wid, 'P', ['F1'])
    r = client.post(url, data={'project': 'P', 'feeders': ['F1'], 'ajuste_job_id': otro}, files=libro)
    assert r.status_code == 400 and 'OTRO' in r.json()['detail']
    sim = _ajuste(client, wid, kind='ajuste_simular')
    r = client.post(url, data={'project': 'P', 'feeders': ['F1'], 'ajuste_job_id': sim},
                    files={'update_file': ('d.xlsx', _xlsx(DEMANDAS))})
    assert r.status_code == 400 and 'simulación' in r.json()['detail']
    r = client.post(url, data={'project': 'P', 'feeders': ['F1'], 'ajuste_job_id': 'nada'},
                    files={'update_file': ('d.xlsx', _xlsx(DEMANDAS))})
    assert r.status_code == 404
    # RF-4 / RF-5: sin base, el plan lo dice.
    body = _plan(client, wid, demandas=DEMANDAS).json()
    assert body['base'] is None and 'Sin base' in body['avisos'][0]


def test_ajuste_sin_ninguna_variacion_no_es_base(client):
    """007:RF-37 — si ningún alimentador del ajuste dejó variación, no hay base."""
    wid = _wid(client)
    job = _ajuste(client, wid, informes=[{'feeder': 'F1', 'error': 'no converge'}])
    vincular_proyecto(client, wid, 'P', ['F1'])
    r = client.post(f'/api/workspaces/{wid}/lote/plan', data={'project': 'P', 'feeders': ['F1'],
                    'ajuste_job_id': job}, files={'update_file': ('d.xlsx', _xlsx(DEMANDAS))})
    assert r.status_code == 400 and 'Ningún alimentador' in r.json()['detail']
