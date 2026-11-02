"""065:RF-22 / RF-23 — flujo real de servicios y cola con almacenamiento aislado."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.asistente import almacen
from convertersmartgrid.web import services
from convertersmartgrid.web.app import create_app


class InterpreteLocalDePrueba:
    def predecir(self, texto):
        return {'tarea': 'gemelo_entrenar', 'confianza': 1.0, 'datos': {}}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'gemelo'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (InterpreteLocalDePrueba(), None))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        yield cliente, app


def esperar(cliente, id_trabajo):
    limite = time.monotonic() + 20
    while time.monotonic() < limite:
        r = cliente.get(f'/api/jobs/{id_trabajo}').json()
        if r['status'] in ('done', 'failed', 'cancelled'):
            return r
        time.sleep(0.02)
    pytest.fail('la cola no terminó')


def proponer(cliente, wid):
    r = cliente.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': 'reentrena la pinn'})
    assert r.status_code == 202
    resultado = esperar(cliente, r.json()['id'])
    assert resultado['status'] == 'done', resultado['error']
    return resultado['result']['plan']


def test_confirmacion_real_registra_permiso_y_herramienta(api, monkeypatch):
    """065:RF-22 / 065:RF-23 — llamada real a API/cola/ejecutor, motor sustituido expresamente."""
    cliente, _ = api
    llamadas = []
    monkeypatch.setattr(services, 'gemelo_entrenar', lambda *_a, **_kw: llamadas.append(True) or {'entrenado': False})
    wid = cliente.post('/api/workspaces', json={'name': 'equipo'}).json()['id']
    plan = proponer(cliente, wid)
    assert not plan['equipo']['permiso_efectivo'] and not llamadas
    r = cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar")
    assert r.status_code == 202
    fin = esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert llamadas == [True]
    filas = almacen.leer('equipo_acciones')
    assert filas[-1]['alcance']['espacio'] == wid and filas[-1]['estado'] == 'terminada'


def test_cambiar_fuente_antes_de_confirmar_falla_sin_herramienta(api, monkeypatch):
    """065:RF-23 / 047:RF-2 — el plan sellado no se reconstruye sobre otra fuente."""
    cliente, _ = api
    llamadas = []
    monkeypatch.setattr(services, 'gemelo_entrenar', lambda *_a, **_kw: llamadas.append(True))
    wid = cliente.post('/api/workspaces', json={'name': 'equipo'}).json()['id']
    plan = proponer(cliente, wid)
    guardado = services._ASISTENTE_PLANES[wid][plan['id']]
    guardado['gobierno'].ws.loaded_source_fingerprint = 'fuente-cambiada'
    r = cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar")
    assert r.status_code == 202
    fin = esperar(cliente, r.json()['id'])
    assert fin['status'] == 'failed' and 'contexto' in fin['error'] and not llamadas


def test_inventario_y_revision_sin_evidencia_son_operativos(api):
    """065:RF-22 / 047:RF-5 / 047:RF-6 — endpoint real revisa en cola y se abstiene."""
    cliente, _ = api
    wid = cliente.post('/api/workspaces', json={'name': 'equipo'}).json()['id']
    assert cliente.get('/api/asistente/equipo').status_code == 200
    plan = proponer(cliente, wid)
    r = cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/revision", json={})
    assert r.status_code == 202, r.text
    fin = esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert not fin['result']['aprobada'] and not fin['result']['autoriza_ejecucion']
    assert len(fin['result']['dictamenes']) == 4
    monitor = cliente.get(f'/api/workspaces/{wid}/asistente/equipo').json()
    assert monitor['revisiones'][-1]['plan'] == plan['id']


def test_correccion_revoca_propuesta_anterior(api):
    """065:RF-23 / 047:RF-10 — cada permiso pertenece a una única propuesta."""
    cliente, _ = api
    wid = cliente.post('/api/workspaces', json={'name': 'equipo'}).json()['id']
    anterior = proponer(cliente, wid)
    r = cliente.post(f"/api/workspaces/{wid}/asistente/{anterior['id']}/corregir", json={'tarea': 'gemelo_entrenar'})
    assert r.status_code == 200
    nuevo = r.json()['plan']
    assert nuevo['id'] != anterior['id'] and not nuevo['equipo']['permiso_efectivo']
    assert cliente.post(f"/api/workspaces/{wid}/asistente/{anterior['id']}/confirmar").status_code == 400


def test_revision_local_con_informe_real_custodiado_sin_ejecutar(api, tmp_path, monkeypatch):
    """047:RF-5/6/7 / 065:RF-23 — custodia real, adaptador LLM con transporte simulado explícito."""
    import io
    import json
    from convertersmartgrid.asistente.equipo import GobiernoEquipo
    from convertersmartgrid.asistente.plan import Plan
    from convertersmartgrid.asistente.observacion import registrar_evidencia
    from convertersmartgrid.asistente.ollama import ClienteOllama
    from convertersmartgrid.asistente import ollama
    cliente, _ = api
    wid = cliente.post('/api/workspaces', json={'name': 'equipo'}).json()['id']
    previo = proponer(cliente, wid)
    ws = services._ASISTENTE_PLANES[wid][previo['id']]['gobierno'].ws
    ws.loaded_source_fingerprint = 'fuente-local'
    ws.loaded_source_mode = 'txt'
    plan = Plan('propuesta-ingenieria', 'revisar obras', 'obras', True, 'trabajo',
                datos={'proyecto': 'P1', 'alimentadores': ['F1']})
    services._ASISTENTE_PLANES[wid][plan.id] = {'plan': plan, 'extras': {},
        'gobierno': GobiernoEquipo.desde_plan(ws, plan)}
    informe = tmp_path / 'evidencia.json'
    informe.write_text(json.dumps({'contexto': {'project': 'P1', 'source_fingerprint': 'fuente-local'},
        'descripcion': 'Ensayo de contrato; no acredita cálculos eléctricos'}), encoding='utf-8')
    registro = registrar_evidencia(ws.out_dir, informe, familia='transformer', etiqueta='contrato')
    peticiones = []
    def abrir(peticion, timeout):
        cuerpo = json.loads(peticion.data)
        peticiones.append(cuerpo)
        dictamen = {'decision': 'favorable', 'evidencia_ids': [registro['id']],
                    'incertidumbres': [], 'contradicciones': []}
        return io.BytesIO(json.dumps({'message': {'content': json.dumps(dictamen)}}).encode())
    monkeypatch.setattr(ollama, 'cliente_configurado', lambda: ClienteOllama(abrir=abrir))
    r = cliente.post(f'/api/workspaces/{wid}/asistente/{plan.id}/revision', json={'max_rondas': 1})
    assert r.status_code == 202, r.text
    fin = esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert len(peticiones) == 4
    assert len(fin['result']['dictamenes']) == 4
    assert fin['result']['aprobada'] and not fin['result']['autoriza_ejecucion']
    assert all('tools' not in p and p['options']['num_predict'] == 512 for p in peticiones)
    assert not almacen.leer('equipo_acciones')
