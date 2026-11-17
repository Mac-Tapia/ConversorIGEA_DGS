"""Spec 108, T29 — el estudio del VAD en la web, con sus rutas para la pestaña «Estudio VAD» (108:RF-26).

El detalle del estudio (su armado, sus observaciones, lo que pueden afectar y sus salidas), las observaciones del
regulador (registrar y responder) y el Informe Definitivo como trabajo. Sin datos de ninguna empresa: el perfil es
sintético y el caso, un JSON vacío.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.web import services

TDR = 'rcd-174-2025-os-cd'


@pytest.fixture
def web_vad(tmp_path, monkeypatch):
    import convertersmartgrid.perfil_empresa as perfil_empresa
    from convertersmartgrid.web.app import create_app

    monkeypatch.setattr(perfil_empresa, 'cargar_perfil',
                        lambda *a, **k: perfil_empresa.PerfilEmpresa(nombre='Distribuidora Sintética Norte'))
    for nombre, valor in (('CSG_ASISTENTE_DATA', tmp_path / 'asistente'), ('CSG_TWIN_DATA', tmp_path / 'gemelo'),
                          ('CSG_WEB_FRONTEND', tmp_path / 'sin_front'), ('CSG_ML_GPU_LOCK', tmp_path / 'gpu.lock')):
        monkeypatch.setenv(nombre, str(valor))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (None, None))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        yield cliente, app


def _esperar(cliente, trabajo: dict) -> dict:
    limite = time.monotonic() + 120
    while time.monotonic() < limite:
        r = cliente.get(f"/api/jobs/{trabajo['id']}").json()
        if r['status'] in ('done', 'failed', 'cancelled', 'parcial'):
            return r
        time.sleep(0.05)
    pytest.fail('la cola no terminó')


def _estudio(cliente) -> tuple[str, str]:
    wid = cliente.post('/api/workspaces').json()['id']
    r = cliente.post(f'/api/workspaces/{wid}/vad/estudios', json={'grupo': 1, 'periodo': '2041-2045', 'version_tdr': TDR})
    assert r.status_code == 200, r.text
    return wid, r.json()['id']


def _destino_tabla(cliente, wid: str, eid: str) -> dict:
    """Una tabla del registro que una observación puede afectar, del detalle del estudio."""
    d = cliente.get(f'/api/workspaces/{wid}/vad/{eid}')
    assert d.status_code == 200, d.text
    tablas = [x for x in d.json().get('destinos', []) if x['tipo'] == 'tabla']
    assert tablas, d.json().get('aviso_destinos')
    return tablas[0]


def test_108_rf26_el_detalle_dice_el_estudio_su_armado_sus_destinos_y_sus_salidas(web_vad):
    """108:RF-26 — el detalle trae el estudio y, tras armar, su manifiesto con el estado por sistema, lo que puede
    afectar una observación (tablas del registro y formatos del anexo 2) y las salidas con rutas del espacio; un
    estudio que no existe da 404."""
    cliente, _app = web_vad
    wid, eid = _estudio(cliente)
    d = cliente.get(f'/api/workspaces/{wid}/vad/{eid}')
    assert d.status_code == 200, d.text
    d = d.json()
    assert d['estudio']['id'] == eid and d['armado'] is None and d['observaciones'] == [] and d['pendientes'] == []
    tipos = {x['tipo'] for x in d['destinos']}
    assert {'tabla', 'formato'} <= tipos, d['aviso_destinos']
    caso = [('files', ('sistemas.json', json.dumps({'sistemas': {'S1': {'anexo2': 'a.json'}}}).encode(), 'application/json')),
            ('files', ('a.json', b'{}', 'application/json'))]
    trabajo = cliente.post(f'/api/workspaces/{wid}/vad/{eid}/armar', files=caso)
    assert trabajo.status_code == 202, trabajo.text
    assert _esperar(cliente, trabajo.json())['status'] == 'done'
    d = cliente.get(f'/api/workspaces/{wid}/vad/{eid}').json()
    assert d['armado']['terminado'] is True and set(d['armado']['sistemas']) == {'S1'}
    assert f'vad/{eid}/manifiesto.json' in d['salidas']
    assert all(not s.startswith(('/', '.')) and '\\' not in s and f'vad/{eid}/caso/' not in s for s in d['salidas'])
    assert cliente.get(f'/api/workspaces/{wid}/vad/no-existe').status_code == 404


def test_108_rf26_las_observaciones_se_registran_y_se_responden_por_la_web(web_vad):
    """108:RF-26 — una observación con un destino del estudio se registra pendiente; repetida o con un destino que el
    estudio no tiene da 422; su respuesta con sustento la deja respondida, y un cambio en lo que no afecta da 422;
    responder una que no existe da 404."""
    cliente, _app = web_vad
    wid, eid = _estudio(cliente)
    destino = _destino_tabla(cliente, wid, eid)
    obs = {'numero': '1', 'fecha': '2041-03-01', 'texto': 'Sustente la tabla.', 'afecta': [destino]}
    r = cliente.post(f'/api/workspaces/{wid}/vad/{eid}/observaciones', json=obs)
    assert r.status_code == 200 and r.json() == {'numero': '1', 'estado': 'pendiente'}, r.text
    assert cliente.post(f'/api/workspaces/{wid}/vad/{eid}/observaciones', json=obs).status_code == 422
    ajena = {**obs, 'numero': '2', 'afecta': [{'tipo': 'tabla', 'id': 'no-existe-en-el-registro'}]}
    r = cliente.post(f'/api/workspaces/{wid}/vad/{eid}/observaciones', json=ajena)
    assert r.status_code == 422 and 'no tiene' in r.json()['detail']
    assert cliente.get(f'/api/workspaces/{wid}/vad/{eid}').json()['pendientes'] == ['1']
    ruta = f'/api/workspaces/{wid}/vad/{eid}/observaciones/1/respuesta'
    r = cliente.post(ruta, json={'respuesta': 'Se sustenta.', 'sustento': 'Anexo X', 'cambios': {'tabla otra': 'x'}})
    assert r.status_code == 422
    r = cliente.post(ruta, json={'respuesta': 'Se sustenta.', 'sustento': 'Anexo X'})
    assert r.status_code == 200 and r.json() == {'numero': '1', 'estado': 'respondida'}, r.text
    d = cliente.get(f'/api/workspaces/{wid}/vad/{eid}').json()
    assert d['pendientes'] == [] and d['observaciones'][0]['sustento'] == 'Anexo X'
    assert cliente.post(f'/api/workspaces/{wid}/vad/{eid}/observaciones/9/respuesta',
                        json={'respuesta': 'a', 'sustento': 'b'}).status_code == 404


def test_108_rf26_el_informe_definitivo_es_un_trabajo_con_sus_huecos_nombrados(web_vad, tmp_path):
    """108:RF-26 — con una observación sin responder, o respondida sin decir qué cambió en lo que afecta, el Informe
    Definitivo da 422 antes de encolar; con la respuesta completa se arma como trabajo: cada documento del registro con
    su fichero o con el motivo de su hueco, nunca vacío en silencio, y el detalle lo enseña con las rutas del espacio
    para descargarlo."""
    cliente, _app = web_vad
    wid, eid = _estudio(cliente)
    destino = _destino_tabla(cliente, wid, eid)
    cliente.post(f'/api/workspaces/{wid}/vad/{eid}/observaciones',
                 json={'numero': '1', 'fecha': '2041-03-01', 'texto': 'Sustente.', 'afecta': [destino]})
    ruta = f'/api/workspaces/{wid}/vad/{eid}/informe-definitivo'
    r = cliente.post(ruta)
    assert r.status_code == 422 and '1: sin respuesta' in r.json()['detail']
    respuesta = f'/api/workspaces/{wid}/vad/{eid}/observaciones/1/respuesta'
    cliente.post(respuesta, json={'respuesta': 'Hecho.', 'sustento': 'S'})
    r = cliente.post(ruta)
    assert r.status_code == 422 and 'no dice qué cambió' in r.json()['detail']
    afectado = f"{destino['tipo']} {destino['id']}"
    cliente.post(respuesta, json={'respuesta': 'Hecho.', 'sustento': 'S', 'cambios': {afectado: 'no cambia: ya cumplía'}})
    r = cliente.post(ruta)
    assert r.status_code == 202 and r.json()['kind'] == 'vad_informe_definitivo', r.text
    fin = _esperar(cliente, r.json())
    assert fin['status'] == 'done', fin.get('error')
    docs = fin['result']['documentos']
    assert docs and all(d['ruta'] or d['motivo'] for d in docs)
    assert any(d['ruta_relativa'] for d in docs), 'al menos la respuesta a las observaciones se escribe'
    assert fin['result']['huecos'], 'sin los contenidos del estudio, sus documentos salen como huecos nombrados'
    d = cliente.get(f'/api/workspaces/{wid}/vad/{eid}').json()
    assert d['informe_definitivo']['documentos'] == docs
    assert any(s.startswith(f'vad/{eid}/informe_definitivo/') and s.endswith('.docx') for s in d['salidas'])


def test_108_rf26_el_caso_en_zip_queda_en_la_empresa_y_sirve_para_el_siguiente_armado(web_vad):
    """108:RF-26 con 109:RF-25 — el caso subido como .zip se registra en las fuentes de la empresa (clase «vad_caso») y
    arma; un segundo armado sin fichero toma el vigente de la empresa; sin ninguno, 400 con lo que falta."""
    import io
    import zipfile

    cliente, _app = web_vad
    wid, eid = _estudio(cliente)
    ruta = f'/api/workspaces/{wid}/vad/{eid}/armar'
    r = cliente.post(ruta, data={})
    assert r.status_code == 400 and 'vad_caso' in r.json()['detail']
    paquete = io.BytesIO()
    with zipfile.ZipFile(paquete, 'w') as z:
        z.writestr('sistemas.json', json.dumps({'sistemas': {'S1': {'anexo2': 'a.json'}}}))
        z.writestr('a.json', '{}')
    r = cliente.post(ruta, files=[('files', ('caso.zip', paquete.getvalue(), 'application/zip'))])
    assert r.status_code == 202, r.text
    assert _esperar(cliente, r.json())['status'] == 'done'
    fuentes = cliente.get(f'/api/workspaces/{wid}/fuentes', params={'clase': 'vad_caso'}).json()['fuentes']
    assert [f['nombre'] for f in fuentes] == ['caso.zip'] and fuentes[0]['vigente']
    r = cliente.post(ruta, data={})
    assert r.status_code == 202, r.text
    assert _esperar(cliente, r.json())['status'] == 'done'
