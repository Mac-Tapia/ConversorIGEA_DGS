"""Spec 011, T16: la API de los estudios y de la transferencia de carga.

La base del ajuste se pone como el resultado de un trabajo ``ajuste_aplicar`` terminado,
el mismo que deja el ajuste de verdad (spec 006): lo que se prueba es qué hace la web
con él. Los guiones son el falso de ``apoyo_pf_web``.
"""
from __future__ import annotations

import json
import time

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo  # noqa: E402
from apoyo_pf_web import guion_falso  # noqa: E402,F401
from igea_dgs.web.app import create_app  # noqa: E402

SIN, CON = 'Sin proyecto', 'Con proyecto'


@pytest.fixture()
def client(tmp_path, monkeypatch, guion_falso):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('IGEA_PERFIL_EMPRESA', str(tmp_path / 'no_hay_perfil.json'))
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        yield c


def _ajuste(client, wid, proyecto='P'):
    """Un ajuste aplicado: A1 cuadró, A2 falló, A3 no cuadró."""
    resultado = {'project': proyecto, 'tolerancia': 0.02, 'informes': [
        {'feeder': 'A1', 'variacion': 'Ajuste_A1_1', 'cuadrado': True,
         'objetivo': {'kw': 1000.0, 'kvar': 300.0}},
        {'feeder': 'A2', 'error': 'el flujo de carga no converge'},
        {'feeder': 'A3', 'variacion': 'Ajuste_A3_1', 'cuadrado': False, 'motivo': 'desvío 3,1 %',
         'objetivo': {'kw': 800.0, 'kvar': 200.0}},
    ]}
    jobs = client.app.state.jobs
    job = jobs.submit(wid, 'ajuste_aplicar', 'Ajuste', lambda _ctx: resultado, lane='powerfactory')
    estado = esperar_trabajo(client, job.public())
    assert estado['status'] == 'done', estado
    return job.id


def _plan(client, wid, ajuste, **kw):
    body = {'project': kw.pop('project', 'P'), 'feeders': ['A1', 'A2', 'A3', 'A4'],
            'estudios': ['flujo', 'contingencias'], 'ajuste_job_id': ajuste, **kw}
    return client.post(f'/api/workspaces/{wid}/pf/estudios/plan', json=body)


def _espacio(client):
    return client.post('/api/workspaces').json()['id']


# --------------------------------------------------------------------------- catálogo y plan
def test_catalogo_de_estudios_y_limites(client):
    """011:RF-23, 011:RF-24, 011:RF-35 — los estudios que se ofrecen, los demás con lo que
    les falta, los límites de por defecto sin perfil y el límite de tiempo."""
    r = client.get('/api/pf/estudios').json()
    assert {e['clave'] for e in r['ofrecidos']} >= {'flujo', 'contingencias', 'troncal'}
    assert all(e['motivo'] for e in r['no_ofrecidos'])
    assert r['limites']['origen'] == 'por defecto' and r['limite_s'] > 0


def test_sin_ajuste_primero_hay_que_calibrar(client):
    """011:RF-13 — sin un ajuste aplicado no hay base: se pide calibrar primero."""
    wid = _espacio(client)
    r = _plan(client, wid, None)
    assert r.status_code == 400 and 'calibrar' in r.json()['detail']


def test_plan_sobre_la_base_del_ultimo_ajuste(client):
    """011:RF-12, 011:RF-14, 011:RF-15 — la base es la del ajuste aplicado; el que falló y el
    que no tiene ajuste quedan fuera con su motivo; el que no cuadró se estudia y se avisa."""
    wid = _espacio(client)
    r = _plan(client, wid, _ajuste(client, wid))
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan['feeders'] == ['A1', 'A3']
    motivos = {x['feeder']: x['motivo'] for x in plan['excluidos']}
    assert set(motivos) == {'A2', 'A4'} and 'no converge' in motivos['A2']
    assert 'variación de ajuste' in motivos['A4']
    assert any('A3' in a and 'no cuadró' in a for a in plan['avisos'])


def test_estudio_que_no_se_ofrece_se_rechaza(client):
    """011:RF-24 — pedir un estudio sin datos se rechaza diciendo qué le falta."""
    wid = _espacio(client)
    r = _plan(client, wid, _ajuste(client, wid), estudios=['cortocircuito'])
    assert r.status_code == 400 and 'cortocircuito' in r.json()['detail'].lower()


def test_limites_del_operador_y_limite_de_tiempo(client):
    """011:RF-35, 011:RF-39 — el operador cambia los límites y el tiempo de cada estudio."""
    wid = _espacio(client)
    r = _plan(client, wid, _ajuste(client, wid), limites={'tension_min_pu': 0.93}, limite_s=600)
    assert r.json()['limites']['tension_min_pu'] == 0.93 and r.json()['limites']['origen'] == 'operador'
    assert r.json()['limite_s'] == 600
    assert _plan(client, wid, _ajuste(client, wid), limite_s=1).status_code == 422


# --------------------------------------------------------------------------- trabajo
def _ejecutar(client, wid, token):
    r = client.post(f'/api/workspaces/{wid}/pf/estudios/{token}/ejecutar')
    assert r.status_code == 202, r.text
    return r.json()


def test_casos_y_luego_cada_estudio_sin_y_con_proyecto(client):
    """011:RF-25, 011:RF-12, 011:RF-37 — en un trabajo del carril de DIgSILENT: prepara los
    casos con la base, y ejecuta los estudios primero en «Sin proyecto» y después los mismos
    en «Con proyecto»; deja los dos ficheros para descargar."""
    wid = _espacio(client)
    token = _plan(client, wid, _ajuste(client, wid)).json()['token']
    estado = esperar_trabajo(client, _ejecutar(client, wid, token))
    assert estado['status'] == 'done', estado
    assert estado['lane'] == 'powerfactory'
    res = estado['result']
    assert res['casos']['recibido']['base']['variaciones'] == ['Ajuste_A1_1', 'Ajuste_A3_1']
    assert [(e['caso'], e['estudio']) for e in res['estudios']] == [
        (SIN, 'flujo'), (SIN, 'contingencias'), (CON, 'flujo'), (CON, 'contingencias')]
    # 011:RF-68: las obras activas de cada caso llegan al resultado.
    assert {e['caso']: e['obras_activas'] for e in res['estudios']} == {SIN: [], CON: ['Obra_terna_A1']}
    assert sorted(res['ficheros']) == sorted(f'estudios_{n}_{token}.csv'
                                             for n in ('resultados', 'violaciones'))
    for nombre in res['ficheros']:
        assert client.get(f'/api/workspaces/{wid}/files/{nombre}').status_code == 200


def test_sin_cargas_nuevas_solo_sin_proyecto(client):
    """011:RF-9, 011:RF-25 — si «Con proyecto» no tiene cargas nuevas, solo se estudia «Sin
    proyecto»."""
    wid = _espacio(client)
    token = _plan(client, wid, _ajuste(client, wid, 'SIN_CARGAS'), project='SIN_CARGAS').json()['token']
    estado = esperar_trabajo(client, _ejecutar(client, wid, token))
    assert {e['caso'] for e in estado['result']['estudios']} == {SIN}


def test_base_borrada_no_estudia_nada(client):
    """011:RF-16 — si una variación de la base ya no existe, no se estudia nada y se nombra."""
    wid = _espacio(client)
    token = _plan(client, wid, _ajuste(client, wid, 'BASE_BORRADA'),
                  project='BASE_BORRADA').json()['token']
    estado = esperar_trabajo(client, _ejecutar(client, wid, token))
    assert estado['status'] == 'failed' and 'Ajuste_A1_1' in estado['error']


def _limite_corto(client, wid, token, segundos):
    """El plan ya guardado con un límite menor que el mínimo del formulario, para no esperar."""
    ws = client.app.state.store.get(wid)
    ruta = ws.cargas_planes[token]['path']
    plan = json.loads(open(ruta, encoding='utf-8').read())
    plan['limite_s'] = segundos
    open(ruta, 'w', encoding='utf-8').write(json.dumps(plan))


def test_estudio_que_pasa_su_limite_no_para_los_demas(client):
    """011:RF-39, 011:RF-40 — cada estudio en su proceso: el que pasa su límite se termina, se
    informa como no terminado y se sigue con el siguiente."""
    wid = _espacio(client)
    token = _plan(client, wid, _ajuste(client, wid, 'LENTO'), project='LENTO').json()['token']
    _limite_corto(client, wid, token, 1.0)
    estado = esperar_trabajo(client, _ejecutar(client, wid, token), timeout=120)
    assert estado['status'] == 'done', estado
    por = {(e['caso'], e['estudio']): e for e in estado['result']['estudios']}
    assert por[(SIN, 'contingencias')]['no_terminado'] is True
    assert por[(CON, 'flujo')]['no_terminado'] is False and (CON, 'contingencias') in por


def test_cancelar_conserva_los_terminados(client):
    """011:RF-41 — cancelar termina el estudio en curso, no empieza otro y conserva los
    terminados en el resultado y en los ficheros."""
    wid = _espacio(client)
    token = _plan(client, wid, _ajuste(client, wid, 'LENTO'), project='LENTO').json()['token']
    job = _ejecutar(client, wid, token)
    # Se cancela con el segundo estudio (contingencias, que tarda) ya empezado.
    limite = time.time() + 30
    while time.time() < limite:
        progreso = client.get(f"/api/jobs/{job['id']}").json().get('progress') or {}
        if progreso.get('index', 0) >= 1:
            break
        time.sleep(0.1)
    time.sleep(0.5)
    client.post(f"/api/jobs/{job['id']}/cancel")
    estado = esperar_trabajo(client, job, timeout=60)
    assert estado['status'] == 'cancelled'
    res = estado['result']
    assert res['cancelado'] is True
    assert [(e['caso'], e['estudio']) for e in res['estudios']] == [(SIN, 'flujo')]
    assert any(n.startswith('estudios_resultados_') for n in res['ficheros'])


# --------------------------------------------------------------------------- transferencia
def test_transferencia_en_el_carril_de_powerfactory_con_su_fichero(client):
    """011:RF-104, 011:RF-121 — dos alimentadores y los casos elegidos, en un trabajo de
    DIgSILENT, con el fichero descargable."""
    wid = _espacio(client)
    r = client.post(f'/api/workspaces/{wid}/pf/transferencia', json={
        'project': 'P', 'feeders': ['A1', 'A2'], 'casos': [SIN, CON]})
    estado = esperar_trabajo(client, r.json())
    assert estado['status'] == 'done', estado
    assert estado['lane'] == 'powerfactory'
    recibido = estado['result']['informe']['recibido']
    assert recibido['casos'] == [SIN, CON] and recibido['feeders'] == ['A1', 'A2']
    assert recibido['seccionadores'] == []            # sin entrada cargada (RF-129)
    fichero = estado['result']['fichero']
    assert client.get(f'/api/workspaces/{wid}/files/{fichero}').status_code == 200


@pytest.mark.parametrize('feeders', [['A1'], ['A1', 'A1'], ['A1', 'A2', 'A3']])
def test_transferencia_pide_dos_alimentadores_distintos(client, feeders):
    """011:RF-104 — sin dos alimentadores distintos no se encola nada."""
    wid = _espacio(client)
    r = client.post(f'/api/workspaces/{wid}/pf/transferencia', json={'project': 'P', 'feeders': feeders})
    assert r.status_code in (400, 422)


# --------------------------------------------------------------------------- T17b: guiones
def test_guiones_del_proyecto_listados(client):
    """011:RF-27 — los guiones DPL y Python del proyecto, con sus parámetros y objetos, en un
    trabajo del carril de DIgSILENT."""
    wid = _espacio(client)
    estado = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/pf/guiones',
                                                 json={'project': 'P'}).json())
    assert estado['status'] == 'done', estado
    assert estado['lane'] == 'powerfactory'
    (g,) = estado['result']['guiones']
    assert g['nombre'] == 'Revisar' and g['parametros'][0]['nombre'] == 'umbral'


def test_guion_en_los_dos_casos_con_sus_parametros(client):
    """011:RF-28, 011:RF-29 — el guion se ejecuta en «Sin proyecto» y en «Con proyecto» con
    los valores del operador, y devuelve por caso su código y su ventana de salida."""
    wid = _espacio(client)
    estado = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/pf/guiones/ejecutar', json={
        'project': 'P', 'nombre': 'Revisar', 'origen': 'proyecto',
        'parametros': {'umbral': '0.93', 'barra': 'B1.ElmTerm'}}).json())
    assert estado['status'] == 'done', estado
    res = estado['result']['resultados']
    assert [r['caso'] for r in res] == [SIN, CON]
    assert all(r['codigo_guion'] == 0 and not r['error'] for r in res)
    assert res[1]['salida'] == ['con: {"barra": "B1.ElmTerm", "umbral": "0.93"}']


def test_guion_con_error_sigue_con_el_otro_caso(client):
    """011:RF-30 — si el guion devuelve error en un caso, se informa con su código y su
    salida y se sigue con el otro."""
    wid = _espacio(client)
    estado = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/pf/guiones/ejecutar', json={
        'project': 'P', 'nombre': 'FALLA'}).json())
    assert estado['status'] == 'done', estado
    sin, con = estado['result']['resultados']
    assert sin['codigo_guion'] == 3 and 'código 3' in sin['error'] and sin['salida'] == ['algo salió mal']
    assert con['codigo_guion'] == 0 and not con['error']


def test_guion_nunca_en_el_caso_base(client):
    """011:RF-28 — los guiones se ejecutan en «Sin proyecto» o «Con proyecto», no en el
    «Caso base»."""
    wid = _espacio(client)
    estado = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/pf/guiones/ejecutar', json={
        'project': 'P', 'nombre': 'Revisar', 'casos': ['Caso base']}).json())
    assert estado['status'] == 'failed' and 'Caso base' in estado['error']
