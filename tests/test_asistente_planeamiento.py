"""Spec 072, T9: el asistente completa un estudio de planeamiento por las rutas de la web, con plan y confirmación.

Rutas, cola y ``services.pide_ejecutar`` reales con ``TestClient``. Solo se sustituyen, como en
``test_pide_web.py``, el guion de DIgSILENT (su informe es el de la prueba) y el perfil de una empresa de
prueba (072:RF-20): sin DIgSILENT ni GPU.
"""
from __future__ import annotations

import time

import pytest

pytest.importorskip('fastapi')

from fastapi.testclient import TestClient

from convertersmartgrid.asistente.ejecutor import pasos
from convertersmartgrid.web import asistente_operacion, services
from convertersmartgrid.web.app import create_app

PLAN = {'tasa_regulada': 0.12, 'tasa_privada': 0.12, 'vida_util_anios': 30, 'horizonte_anios': 20,
        'crecimiento_demanda_anual': 0.04, 'pesos_art_15_3': {'subsanacion_calidad': 1, 'crecimiento_demanda': 1},
        'tarifas': {'MT3': {'energia_punta_kwh': 0.32, 'energia_fuera_punta_kwh': 0.28}}}
PERFIL = {'planificacion': PLAN, 'empresa': 'Empresa de prueba',
          'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}
INFORME = {'anios': [{'anio': 0, 'cabeceras_kw': {'F1': 1000.0}, 'vm_min': 0.93, 'problemas': []},
                     {'anio': 4, 'cabeceras_kw': {'F1': 1170.0}, 'vm_min': 0.92, 'problemas': []}]}


class Transformer:
    tareas = ('pide',)

    def __init__(self, datos):
        self.datos = datos

    def predecir(self, texto):
        return {'tarea': 'pide', 'confianza': 1.0, 'datos': self.datos}


def _datos(**extra):
    return {'proyecto': [{'valor': 'P1'}], 'alimentadores': [{'valor': 'F1'}], **extra}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'gemelo'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'gpu.lock'))
    monkeypatch.setattr(services, 'asistente_vocabulario', lambda ws: {'proyecto': ['P1'], 'alimentadores': ['F1']})
    monkeypatch.setattr(asistente_operacion, 'parametros_de_costeo', lambda _t: None)
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil', lambda *a, **k: PERFIL)
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.estructura_empresa', lambda *a, **k: None)
    monkeypatch.setattr(services, 'native_action_context',
                        lambda _ws, project, feeders, action: {'feeders': ['F1'], 'project': project})
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (0, INFORME, tmp_path / 'pide.json'))
    services._ASISTENTE_PLANES.clear()
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        yield cliente, app
    services._ASISTENTE_PLANES.clear()


def _esperar(cliente, id_trabajo):
    limite = time.monotonic() + 60
    while time.monotonic() < limite:
        r = cliente.get(f'/api/jobs/{id_trabajo}').json()
        if r['status'] in ('done', 'failed', 'cancelled'):
            return r
        time.sleep(0.05)
    pytest.fail('la cola no terminó')


def _proponer(cliente, wid, texto):
    r = cliente.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': texto})
    assert r.status_code == 202, r.text
    fin = _esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin['error']
    return fin['result']['plan']


def test_el_asistente_completa_el_estudio_por_la_ruta_de_la_web(api, monkeypatch):
    """072:RF-18 / 072:RF-4 — con plan y confirmación, el PIDE va por la ruta de la web y deja los dos
    entregables por módulos desde un mismo estudio; antes de confirmar no se ejecuta nada."""
    cliente, app = api
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer(_datos(periodo=[{'valor': '2031'}])), None))
    wid = cliente.post('/api/workspaces', json={'name': 'planeamiento'}).json()['id']
    plan = _proponer(cliente, wid, 'haz el pide de P1 F1 para 2031')
    assert plan['tarea'] == 'pide' and plan['listo'] and plan['espera_confirmacion'], plan['faltan']
    assert plan['pasos'] == ['PIDE'] and not [j for j in app.state.jobs.list(wid) if j.kind == 'pide']
    fin = _esperar(cliente, cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").json()['id'])
    assert fin['status'] == 'done', fin['error']
    hijo = next(j.public() for j in app.state.jobs.list(wid) if j.kind == 'pide')
    assert hijo['status'] == 'done' and hijo['lane'] == 'powerfactory', hijo.get('error')
    resultado = hijo['result']
    assert resultado['estudio']['anio_base'] == 2030
    assert len(resultado['informes_planeamiento']) == 7
    ws = app.state.store.get(wid)
    assert all((ws.out_dir / f).is_file() for f in resultado['informes_planeamiento'])


def test_sin_anio_de_presentacion_el_plan_lo_pide(api, monkeypatch):
    """072:RF-18 / 072:RF-1 — sin año en la orden ni en el perfil no hay estudio: se dice antes de confirmar."""
    cliente, _app = api
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer(_datos()), None))
    wid = cliente.post('/api/workspaces', json={'name': 'sin año'}).json()['id']
    plan = _proponer(cliente, wid, 'haz el pide de P1 F1')
    assert not plan['listo'] and any('año de presentación' in f for f in plan['faltan'])


def test_el_anio_del_perfil_vale_y_se_dice(api, monkeypatch):
    """072:RF-18 / 072:RF-1 — el año que el perfil ya declara sirve, y el plan dice de dónde salió."""
    cliente, _app = api
    monkeypatch.setitem(PERFIL, 'planificacion', {**PLAN, 'anio_presentacion': 2027})
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer(_datos()), None))
    wid = cliente.post('/api/workspaces', json={'name': 'perfil'}).json()['id']
    plan = _proponer(cliente, wid, 'haz el pide de P1 F1')
    assert plan['listo'], plan['faltan']
    assert any('2027' in r and 'perfil' in r for r in plan['razonamiento'])


def test_libros_de_la_orden_llegan_a_la_ruta(api, monkeypatch, tmp_path):
    """072:RF-18 — el libro CAPEX y el Formato 01 que nombra la orden van en el cuerpo de la misma ruta;
    un libro que no existe se dice en el plan."""
    cliente, _app = api
    capex, f01 = tmp_path / 'capex.xlsx', tmp_path / 'formato 01.xlsx'
    capex.write_bytes(b'x')
    f01.write_bytes(b'x')
    texto = f'haz el pide de P1 F1 para 2031 con el capex {capex.as_posix()} y el formato 01 "{f01.as_posix()}"'
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer(_datos(periodo=[{'valor': '2031'}])), None))
    wid = cliente.post('/api/workspaces', json={'name': 'libros'}).json()['id']
    plan = _proponer(cliente, wid, texto)
    assert plan['listo'], plan['faltan']
    extras = services._ASISTENTE_PLANES[wid][plan['id']]['extras']
    assert extras['capex'] == capex.as_posix() and extras['formato_01'] == f01.as_posix()
    cuerpo = pasos('pide', {'proyecto': 'P1', 'alimentadores': ['F1'], 'periodo': '2031'}, extras)[0].cuerpo
    assert cuerpo == {'project': 'P1', 'feeders': ['F1'], 'anio_presentacion': 2031,
                      'capex': capex.as_posix(), 'formato_01': f01.as_posix()}
    falta = _proponer(cliente, wid, f'haz el pide de P1 F1 para 2031 con el capex {(tmp_path / "no.xlsx").as_posix()}')
    assert not falta['listo'] and any('CAPEX' in f and 'no.xlsx' in f for f in falta['faltan'])
