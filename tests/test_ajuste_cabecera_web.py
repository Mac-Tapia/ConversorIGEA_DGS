"""Spec 006: la API del ajuste a la máxima de cabecera (plan y trabajo de DIgSILENT).

El guion de DIgSILENT se sustituye por uno falso que devuelve el plan recibido: aquí se
prueba qué manda la web (objetivo, clientes, kVA de respaldo) y que corre en el carril
``powerfactory``. El guion de verdad se prueba en ``test_ajuste_cabecera_guion.py``.
"""
from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx2')
pytest.importorskip('python_calamine')
pytest.importorskip('openpyxl')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import esperar_trabajo  # noqa: E402
from igea_dgs.web import services  # noqa: E402
from igea_dgs.web.app import create_app  # noqa: E402
from test_demanda_medida_web import CABECERA, CLIENTES, _subir, _xlsx  # noqa: E402

GUION_FALSO = '''
import argparse, json
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--plan'); p.add_argument('--output-json'); p.add_argument('--simular', action='store_true')
p.add_argument('--cancel-file')
a = p.parse_args()
plan = json.loads(Path(a.plan).read_text(encoding='utf-8'))
informe = {'modo': 'simular' if a.simular else 'aplicar', 'cuadrado': not a.simular,
           'recibido': plan}
if plan['project'] == 'SIN_KVA':
    informe = {'error': '1 SED sin potencia instalada: S9. Corríjalas antes de ajustar.'}
Path(a.output_json).write_text(json.dumps(informe), encoding='utf-8')
'''

SUMINISTROS = {'s': [['Suministro', 'Suministro Act', 'SED', 'RADIAL'], [11, 9011, 'E1', 'A1'],
                     [12, 9012, 'E2', 'A2']]}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    guion = tmp_path / 'ajuste_falso.py'
    guion.write_text(GUION_FALSO, encoding='utf-8')
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, sys.executable))
    monkeypatch.setattr(services, '_script', lambda _nombre: guion)
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda _d: None)
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as c:
        yield c


def _maxima(client, medidores=(('A1', 'M1'),)):
    """Espacio con la cabecera subida y la máxima buscada; devuelve (wid, trabajo)."""
    wid = client.post('/api/workspaces').json()['id']
    r = client.post(f'/api/workspaces/{wid}/demanda/cabecera',
                    files=[('files', ('SISTEMA A.xlsx', _xlsx(CABECERA)))])
    assert r.status_code == 200
    job = client.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={'medidores': [
        {'alimentador': a, 'medidor': m} for a, m in medidores]}).json()
    estado = esperar_trabajo(client, job)
    assert estado['status'] == 'done', estado
    return wid, job['id']


def _plan(client, wid, job_id, **kw):
    body = {'project': 'P', 'job_id': job_id, **kw}
    return client.post(f'/api/workspaces/{wid}/demanda/ajuste/plan', json=body)


def test_objetivo_es_la_maxima_de_la_tabla(client):
    """006:RF-1 — el objetivo es el kW y el kVAR que dio el trabajo de la máxima."""
    wid, job = _maxima(client)
    r = _plan(client, wid, job)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['feeder'] == 'A1'
    assert body['objetivo']['kw'] == 107.0 and body['objetivo']['kvar'] == 10.0
    assert body['tolerancia'] == 0.01
    assert any('suministros' in a for a in body['avisos'])
    assert any('entrada' in a.lower() for a in body['avisos'])


def test_varios_medidores_hay_que_elegir(client):
    """006:RF-2 — con varios medidores no se ajusta hasta elegir el de la cabecera."""
    wid, job = _maxima(client, (('A1', 'M1'), ('A1', 'M2')))
    r = _plan(client, wid, job)
    assert r.status_code == 400 and 'elija el medidor' in r.json()['detail']
    r = _plan(client, wid, job, medidor='M1')
    assert r.status_code == 200 and r.json()['objetivo']['kw'] == 107.0
    # M2 solo trae kW: sin kVAR ni FP no hay objetivo (RF-3).
    assert _plan(client, wid, job, medidor='M2').status_code == 400


def test_medidor_sin_maxima_no_se_ajusta(client):
    """006:RF-3 — un medidor sin máxima no da objetivo."""
    wid, job = _maxima(client, (('A1', 'NO'),))
    r = _plan(client, wid, job)
    assert r.status_code == 400 and 'NO' in r.json()['detail']


def test_trabajo_ajeno_o_inexistente(client):
    """006:RF-1 — solo la máxima buscada en este espacio."""
    wid, job = _maxima(client)
    otro = client.post('/api/workspaces').json()['id']
    assert _plan(client, otro, job).status_code == 404
    assert _plan(client, wid, 'no-existe').status_code == 404


@pytest.mark.parametrize('tol', [0.0, 0.0005, 0.2, -1])
def test_tolerancia_fuera_de_rango(client, tol):
    """006:RF-11 — la tolerancia va del 0,1 % al 10 %; fuera de eso, 422."""
    wid, job = _maxima(client)
    assert _plan(client, wid, job, tolerancia=tol).status_code == 422


def test_clientes_del_alimentador_van_al_plan(client):
    """006:RF-5 — el plan lleva los clientes cruzados de ese alimentador, no los demás."""
    wid, job = _maxima(client)
    _subir(client, wid, 'suministros', SUMINISTROS)
    _subir(client, wid, 'clientes', CLIENTES)
    body = _plan(client, wid, job).json()
    assert body['n_clientes'] == 1
    trabajo = client.post(f"/api/workspaces/{wid}/demanda/ajuste/{body['token']}/simular").json()
    plan = esperar_trabajo(client, trabajo)['result']['informe']['recibido']
    assert [c['codigo'] for c in plan['clientes']] == ['11']


def test_simular_y_aplicar_en_el_carril_de_powerfactory(client):
    """006:RF-19 / 006:RF-20 — trabajos del carril powerfactory con el plan preparado."""
    wid, job = _maxima(client)
    token = _plan(client, wid, job, tolerancia=0.02).json()['token']
    for accion, modo in (('simular', 'simular'), ('aplicar', 'aplicar')):
        trabajo = client.post(f'/api/workspaces/{wid}/demanda/ajuste/{token}/{accion}')
        assert trabajo.status_code == 202 and trabajo.json()['lane'] == 'powerfactory'
        estado = esperar_trabajo(client, trabajo.json())
        assert estado['status'] == 'done', estado
        informe = estado['result']['informe']
        assert informe['modo'] == modo
        assert informe['recibido']['tolerancia'] == 0.02
        assert informe['recibido']['variacion'].startswith('Ajuste_A1_')


def test_error_del_guion_llega_al_operador(client):
    """006:RF-24 — una SED sin kVA: el trabajo falla con el mensaje del guion."""
    wid, job = _maxima(client)
    token = client.post(f'/api/workspaces/{wid}/demanda/ajuste/plan',
                        json={'project': 'SIN_KVA', 'job_id': job}).json()['token']
    estado = esperar_trabajo(client, client.post(
        f'/api/workspaces/{wid}/demanda/ajuste/{token}/aplicar').json())
    assert estado['status'] == 'failed' and 'S9' in estado['error']


def test_plan_del_ajuste_no_sirve_para_cargas(client):
    """006:RF-19 — el token del ajuste no lanza el guion de cargas."""
    wid, job = _maxima(client)
    token = _plan(client, wid, job).json()['token']
    r = client.post(f'/api/workspaces/{wid}/lote/{token}/apply')
    assert r.status_code == 400
    assert client.post(f'/api/workspaces/{wid}/demanda/ajuste/zzz/aplicar').status_code == 404


def test_kva_de_respaldo_desde_la_entrada(client, monkeypatch):
    """006:RF-10 — con la entrada cargada, el plan lleva el kVA de cada SED del modelo."""

    class Sed:
        def __init__(self, code, kva):
            self.code, self.design_kva = code, kva

    class Modelo:
        seds = [Sed('E1', 100.0), Sed('E2', 0.0)]

    class Dataset:
        def feeder_ids(self):
            return ['a-1', 'B2']

    wid, job = _maxima(client)
    store = client.app.state.store
    store.get(wid).dataset = Dataset()
    vistos = []
    monkeypatch.setattr(services, 'build_model',
                        lambda ws, feeder, geography=None: vistos.append(feeder) or Modelo())
    token = _plan(client, wid, job).json()['token']
    estado = esperar_trabajo(client, client.post(
        f'/api/workspaces/{wid}/demanda/ajuste/{token}/simular').json())
    assert vistos == ['a-1'], 'el código del libro casa con el de la entrada sin guiones'
    assert estado['result']['informe']['recibido']['kva_entrada'] == {'E1': 100.0}
    assert json.dumps(estado['result']['informe'])


def test_ajuste_en_la_seccion_de_demanda_medida():
    """006:RF-23 — el ajuste va en «Demanda medida», con el proyecto de la pestaña de
    cargas y la máxima buscada. La interfaz no tiene pruebas de navegador: se comprueba
    en el código que la conexión existe."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'components'
    cargas = (src / 'CargasTab.tsx').read_text(encoding='utf-8')
    demanda = (src / 'DemandaMedida.tsx').read_text(encoding='utf-8')
    ajuste = (src / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
    assert '<DemandaMedida project={project} />' in cargas
    assert '<AjusteCabecera project={project} maxima={ultimo} />' in demanda
    assert 'api.ajustePlan' in ajuste and 'job_id: maxima.id' in ajuste
