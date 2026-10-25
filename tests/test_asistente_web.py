"""Spec 026, T6: la consola del asistente en la API de la web."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from igea_dgs.asistente import almacen
from igea_dgs.web import services
from igea_dgs.web.app import create_app

#: Lo que «entiende» el Transformer falso de cada orden de estas pruebas.
ORDENES = {
    'que hay cargado': ('estado', 0.99, {}),
    'lee los proyectos de digsilent': ('leer_proyectos', 0.99, {}),
    'reentrena la pinn': ('gemelo_entrenar', 0.98, {}),
    'xyzzy': ('estado', 0.2, {}),
    'convierte IN111': ('convertir', 0.97, {'alimentadores': [{'valor': 'IN111', 'confianza': 0.9}]}),
    'carga la fuente': ('cargar_fuente', 0.99, {}),
}


class TransformerFalso:
    version = 'falso'

    def predecir(self, texto):
        tarea, confianza, datos = ORDENES[texto]
        return {'tarea': tarea, 'confianza': confianza, 'datos': datos, 'alternativas': [], 'version': 'falso'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('IGEA_TWIN_DATA', str(tmp_path / 'twin'))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (TransformerFalso(), None))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as c:
        app.state.asistente_http = c
        yield c


def _wid(client):
    return client.post('/api/workspaces', json={'name': 'asistente'}).json()['id']


def _esperar(client, job_id, limite=60):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        j = client.get(f'/api/jobs/{job_id}').json()
        if j['status'] in ('done', 'failed', 'cancelled'):
            return j
        time.sleep(0.1)
    raise AssertionError('el trabajo no terminó')


def _orden(client, wid, texto):
    r = client.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': texto})
    assert r.status_code == 200, r.text
    return r.json()


def test_consulta_respondida_al_momento(client):
    """026:RF-1 / 026:RF-9 — la consola recibe la orden; una consulta se responde en la misma
    petición, sin trabajo ni confirmación."""
    r = _orden(client, _wid(client), 'que hay cargado')
    assert r['plan']['tarea'] == 'estado' and not r['plan']['escribe'] and 'trabajo' not in r
    assert 'Sin fuente cargada' in r['respuesta']['texto']


def test_lo_que_solo_lee_se_lanza_sin_confirmar(client, monkeypatch):
    """026:RF-9 / 026:RF-10 — leer los proyectos de DIgSILENT no escribe: se lanza solo, por la
    misma ruta y el mismo carril que la pestaña."""
    monkeypatch.setattr(services, 'pf_projects', lambda ws, ctx: {'projects': [{'name': 'P1'}]})
    r = _orden(client, _wid(client), 'lee los proyectos de digsilent')
    assert r['trabajo']['lane'] == 'asistente'
    fin = _esperar(client, r['trabajo']['id'])
    assert fin['status'] == 'done', fin['error']
    assert fin['result']['pasos'][0]['estado'] == 'done'
    assert fin['result']['resultado'] == {'projects': [{'name': 'P1'}]}


def test_lo_que_escribe_espera_la_confirmacion(client, monkeypatch):
    """026:RF-8 / 026:RF-10 / 026:RF-12 / 026:RF-19 — reentrenar la PINN escribe: el plan
    espera; confirmado, va por la ruta de la web, deja sus entregables y la orden queda como
    ejemplo confirmado."""
    monkeypatch.setattr(services, 'gemelo_entrenar',
                        lambda ws, ctx, forzar=False: {'entrenado': True, 'forzar': forzar, 'informe': 'gemelo.xlsx'})
    wid = _wid(client)
    r = _orden(client, wid, 'reentrena la pinn')
    plan = r['plan']
    assert plan['escribe'] and plan['listo'] and 'trabajo' not in r and plan['pasos'] == ['reentrenar la PINN']
    assert any('confirmación' in x for x in plan['razonamiento'])
    t = client.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar")
    assert t.status_code == 202
    fin = _esperar(client, t.json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert fin['result']['resultado']['forzar'] is True and fin['result']['entregables'] == ['gemelo.xlsx']
    ejemplos = almacen.leer('ejemplos')
    assert ejemplos[-1]['tarea'] == 'gemelo_entrenar' and ejemplos[-1]['origen'] == 'confirmado'


def test_sin_entender_no_se_confirma(client):
    """026:RF-4 — una orden que no se entendió no se puede confirmar."""
    wid = _wid(client)
    plan = _orden(client, wid, 'xyzzy')['plan']
    assert plan['tarea'] is None and not plan['listo']
    assert client.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").status_code == 422


def test_sin_entradas_no_se_ofrece_cargar(client):
    """026:RF-6 / 026:RF-8 — en un espacio sin entradas, «carga la fuente» dice lo que falta y
    no se puede confirmar (fallaba después, en la ruta, con «Faltan entradas», 2026-10-24)."""
    wid = _wid(client)
    plan = _orden(client, wid, 'carga la fuente')['plan']
    assert plan['tarea'] == 'cargar_fuente' and not plan['listo']
    assert any('Faltan entradas' in f and 'RED' in f for f in plan['faltan'])
    assert client.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").status_code == 422


def test_convertir_carga_antes_la_fuente(client, monkeypatch):
    """026:RF-6 / 026:RF-10 — con las entradas puestas y la fuente sin cargar, convertir empieza
    por cargarla, con la misma ruta de la web."""
    monkeypatch.setattr(services, 'check_ready', lambda ws: None)
    plan = _orden(client, _wid(client), 'convierte IN111')['plan']
    assert plan['listo'] and plan['pasos'] == ['cargar la fuente', 'convertir'], plan
    assert any('primero se carga' in x for x in plan['razonamiento'])


def test_correccion_y_registro(client):
    """026:RF-15 / 026:RF-19 / 026:RF-28 — la corrección del operador da un plan nuevo y un
    ejemplo corregido; el registro muestra órdenes y decisiones."""
    wid = _wid(client)
    plan = _orden(client, wid, 'convierte IN111')['plan']
    assert plan['tarea'] == 'convertir'
    r = client.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/corregir",
                    json={'tarea': 'flujo', 'datos': {'alimentadores': ['IN111']}})
    assert r.status_code == 200 and r.json()['plan']['tarea'] == 'flujo'
    ejemplo = almacen.leer('ejemplos')[-1]
    assert ejemplo['tarea'] == 'flujo' and ejemplo['origen'] == 'corregido'
    assert ejemplo['datos'][0][2] == 'alimentadores'
    registro = client.get('/api/asistente/registro').json()
    assert registro['ordenes'][-1]['texto'] == 'convierte IN111'
    assert registro['decisiones'][-1]['decision'] == 'corregida'


def test_rutas_del_gemelo_para_el_asistente(client, monkeypatch):
    """026:RF-11 — el asistente evalúa y reentrena el gemelo por sus rutas (024:RF-74)."""
    monkeypatch.setattr(services, 'gemelo_evaluar', lambda ws, ctx: {'modelo': 'v1', 'por_particion': {}})
    wid = _wid(client)
    j = client.post(f'/api/workspaces/{wid}/digital-twin/evaluar')
    assert j.status_code == 202 and _esperar(client, j.json()['id'])['result']['modelo'] == 'v1'
