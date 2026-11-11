"""Spec 072, T17: corto plazo, PIDE y planeamiento de largo plazo se eligen y se distinguen desde la web.

La función pura con la metodología real del repositorio (``config/pide_universal_2017.json``) y dos años de
presentación, y las rutas reales con ``TestClient``. Como en ``test_asistente_planeamiento.py``, solo se sustituyen el
guion de DIgSILENT (su informe es el de la prueba) y el perfil de una empresa de prueba (072:RF-20): sin DIgSILENT ni GPU.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from convertersmartgrid.escalera_optima import OBRAS_DE_LARGO_PLAZO
from convertersmartgrid.estudio_planeamiento import EstudioError, tipos_de_analisis
from convertersmartgrid.informes_planeamiento import MODULOS

RAIZ = Path(__file__).resolve().parent.parent
METODOLOGIA = json.loads((RAIZ / 'config' / 'pide_universal_2017.json').read_text(encoding='utf-8'))
MODULOS_DICT = [{'clave': m.clave, 'entregable': m.entregable, 'titulo': m.titulo, 'formatos': m.formatos} for m in MODULOS]
CORTO = ['bancos', 'seccion', 'terna', 'transferencia', 'regulador']
LARGO = ['nivel', 'expreso', 'set_nueva']


def _tipos(anio=None, periodo=4):
    r = tipos_de_analisis(METODOLOGIA, periodo_corto=periodo, modulos=MODULOS_DICT, obras_corto=CORTO,
                          obras_largo=LARGO, anio_presentacion=anio)
    return r, {t['clave']: t for t in r['tipos']}


def test_tres_tipos_en_su_orden():
    """072:RF-29 — los tres tipos, en el orden en que se encadenan: corto plazo, PIDE y largo plazo."""
    r, _ = _tipos()
    assert [t['clave'] for t in r['tipos']] == ['corto_plazo', 'pide', 'largo_plazo']


@pytest.mark.parametrize('anio', [2027, 2031])
def test_horizonte_de_cada_tipo_desde_la_metodologia(anio):
    """072:RF-30 — los años salen de la metodología y del periodo del perfil; el calendario, del año de presentación."""
    r, t = _tipos(anio)
    h = METODOLOGIA['horizonte']
    assert [a['relativo'] for a in t['pide']['anios']] == h['detalle_pide']
    assert [a['relativo'] for a in t['largo_plazo']['anios']] == h['largo_plazo']
    assert [a['relativo'] for a in t['corto_plazo']['anios']] == [0, 1, 2, 3, 4]
    base = anio - 1
    assert r['estudio']['anio_base'] == base
    assert all(a['calendario'] == base + a['relativo'] for x in t.values() for a in x['anios'])


def test_sin_anio_los_anios_van_solo_relativos_y_el_periodo_es_el_del_perfil():
    """072:RF-30 / 098:RF-37 — sin año de presentación no hay calendario; el corto plazo llega a su periodo."""
    r, t = _tipos(None, periodo=6)
    assert r['estudio'] is None
    assert all(a['calendario'] is None for x in t.values() for a in x['anios'])
    assert t['corto_plazo']['anios'][-1]['relativo'] == 6
    with pytest.raises(EstudioError):
        _tipos(None, periodo=0)


def test_obras_de_cada_tipo_segun_098():
    """072:RF-31 — corto plazo, solo las de implementación inmediata; PIDE y largo plazo también las integrales."""
    _, t = _tipos()
    codigos = lambda xs: [o['codigo'] for o in xs]  # noqa: E731
    assert codigos(t['corto_plazo']['obras_admitidas']) == CORTO
    assert codigos(t['corto_plazo']['obras_excluidas']) == LARGO
    assert codigos(t['pide']['obras_admitidas']) == CORTO + LARGO
    assert codigos(t['largo_plazo']['obras_admitidas']) == CORTO + LARGO
    assert t['largo_plazo']['aplica_obras'] is False and t['corto_plazo']['aplica_obras'] is True
    assert all(o['titulo'] != o['codigo'] for o in t['pide']['obras_admitidas'])


def test_entregables_articulos_y_formatos_de_la_norma():
    """072:RF-32 — PIDE, arts. 11 a 17 con F08 a F15; largo plazo, arts. 6 a 10 con F01 a F07; corto plazo, sus informes."""
    _, t = _tipos(2027)
    assert [a['numero'] for a in t['pide']['articulos']] == list(range(11, 18))
    assert [a['numero'] for a in t['largo_plazo']['articulos']] == list(range(6, 11))
    assert t['pide']['formatos'] == [f'F{n:02d}' for n in range(8, 16)]
    assert t['largo_plazo']['formatos'] == [f'F{n:02d}' for n in range(1, 8)]
    assert {e['clave'] for e in t['largo_plazo']['entregables']} == {'diagnostico', 'alternativas'}
    assert {e['clave'] for e in t['corto_plazo']['entregables']} == {'informe_estudio', 'informe_factibilidad',
                                                                       'libro_informe'}


def test_la_norma_se_dice_con_su_estado_juridico():
    """072:RF-37 — la norma y su estado; marcada como proyecto, no se presenta como vigente."""
    r, _ = _tipos()
    assert r['norma']['acto'] == METODOLOGIA['fuente']['acto']
    assert r['norma']['estado_juridico'] == METODOLOGIA['estado_juridico']
    assert r['norma']['vigente'] is (METODOLOGIA['estado_juridico'] not in ('', 'proyecto'))
    otra = dict(METODOLOGIA, estado_juridico='vigente')
    assert tipos_de_analisis(otra, periodo_corto=4, modulos=MODULOS_DICT, obras_corto=CORTO, obras_largo=LARGO)[
        'norma']['vigente'] is True


# ---------------------------------------------------------------- rutas de la web

pytest.importorskip('fastapi')

from fastapi.testclient import TestClient  # noqa: E402

from convertersmartgrid.web import services  # noqa: E402
from convertersmartgrid.web.app import create_app  # noqa: E402

PLAN = {'tasa_regulada': 0.12, 'tasa_privada': 0.12, 'vida_util_anios': 30, 'horizonte_anios': 20,
        'crecimiento_demanda_anual': 0.04, 'pesos_art_15_3': {'subsanacion_calidad': 1, 'crecimiento_demanda': 1},
        'tarifas': {'MT3': {'energia_punta_kwh': 0.32, 'energia_fuera_punta_kwh': 0.28}}}
INFORME = {'anios': [{'anio': 0, 'cabeceras_kw': {'F1': 1000.0}, 'vm_min': 0.93, 'problemas': []},
                     {'anio': 4, 'cabeceras_kw': {'F1': 1170.0}, 'vm_min': 0.92, 'problemas': []}]}


@pytest.fixture
def api(tmp_path, monkeypatch):
    perfil = {'planificacion': dict(PLAN), 'empresa': 'Empresa de prueba',
              'estudios': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'gemelo'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'gpu.lock'))
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil', lambda *a, **k: perfil)
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.estructura_empresa', lambda *a, **k: None)
    monkeypatch.setattr(services, 'native_action_context',
                        lambda _ws, project, feeders, action: {'feeders': ['F1'], 'project': project})
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: (0, INFORME, tmp_path / 'pide.json'))
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        yield cliente, app, perfil


def _esperar(cliente, id_trabajo):
    limite = time.monotonic() + 60
    while time.monotonic() < limite:
        r = cliente.get(f'/api/jobs/{id_trabajo}').json()
        if r['status'] in ('done', 'failed', 'cancelled'):
            return r
        time.sleep(0.05)
    pytest.fail('la cola no terminó')


def test_ruta_de_los_tipos_con_y_sin_anio(api):
    """072:RF-29, 072:RF-30, 072:RF-31 — la web lee los tipos del servidor; las obras son las de 098:RF-50."""
    cliente, _app, perfil = api
    r = cliente.get('/api/planeamiento/tipos').json()
    assert [t['clave'] for t in r['tipos']] == ['corto_plazo', 'pide', 'largo_plazo']
    assert r['estudio'] is None and r['anio_presentacion_perfil'] is None
    corto = {o['codigo'] for o in r['tipos'][0]['obras_admitidas']}
    assert corto and not corto & OBRAS_DE_LARGO_PLAZO
    assert {o['codigo'] for o in r['tipos'][0]['obras_excluidas']} <= OBRAS_DE_LARGO_PLAZO
    r = cliente.get('/api/planeamiento/tipos', params={'anio_presentacion': 2031}).json()
    assert r['estudio']['anio_base'] == 2030
    perfil['planificacion']['anio_presentacion'] = 2027
    r = cliente.get('/api/planeamiento/tipos').json()
    assert r['estudio']['anio_base'] == 2026 and r['anio_presentacion_perfil'] == 2027
    assert cliente.get('/api/planeamiento/tipos', params={'anio_presentacion': 0}).status_code == 422


def test_largo_plazo_escribe_solo_sus_modulos(api):
    """072:RF-34 — «Planificar» como largo plazo deja solo el diagnóstico y las alternativas del plan."""
    cliente, app, _perfil = api
    wid = cliente.post('/api/workspaces', json={'name': 'largo'}).json()['id']
    r = cliente.post(f'/api/workspaces/{wid}/pide', json={'project': 'P1', 'feeders': ['F1'], 'implementar': False,
                                                         'anio_presentacion': 2031, 'plazo': 'largo_plazo'})
    assert r.status_code == 202, r.text
    fin = _esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert fin['title'].startswith('Plan de largo plazo')
    res = fin['result']
    assert res['plazo'] == 'largo_plazo' and res['implementadas'] == []
    assert [f.split('_')[1] for f in res['informes_planeamiento']] == ['diagnostico', 'alternativas']
    ws = app.state.store.get(wid)
    assert all((ws.out_dir / f).is_file() for f in res['informes_planeamiento'])


def test_pide_escribe_los_dos_entregables(api):
    """072:RF-34 / 072:RF-4 — como PIDE se escriben los siete módulos: el PIDE consume el plan del mismo estudio."""
    cliente, _app, _perfil = api
    wid = cliente.post('/api/workspaces', json={'name': 'pide'}).json()['id']
    r = cliente.post(f'/api/workspaces/{wid}/pide', json={'project': 'P1', 'feeders': ['F1'], 'implementar': False,
                                                         'anio_presentacion': 2031, 'plazo': 'pide'})
    fin = _esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert fin['result']['plazo'] == 'pide' and len(fin['result']['informes_planeamiento']) == 7


def test_largo_plazo_no_aplica_obras(api):
    """072:RF-35 — largo plazo con «aplicar obras» se rechaza antes de encolar."""
    cliente, app, _perfil = api
    wid = cliente.post('/api/workspaces', json={'name': 'aplica'}).json()['id']
    r = cliente.post(f'/api/workspaces/{wid}/pide', json={'project': 'P1', 'feeders': ['F1'], 'implementar': True,
                                                         'anio_presentacion': 2031, 'plazo': 'largo_plazo'})
    assert r.status_code == 422 and 'no las aplica' in r.json()['detail']
    assert not [j for j in app.state.jobs.list(wid) if j.kind == 'pide']


@pytest.mark.parametrize('plazo', ['pide', 'largo_plazo'])
def test_sin_anio_de_presentacion_se_rechaza_antes_de_encolar(api, plazo):
    """072:RF-36 — con tipo PIDE o largo plazo y sin año en la petición ni en el perfil, 422 sin encolar."""
    cliente, app, perfil = api
    wid = cliente.post('/api/workspaces', json={'name': 'sin_anio'}).json()['id']
    cuerpo = {'project': 'P1', 'feeders': ['F1'], 'implementar': False, 'plazo': plazo}
    r = cliente.post(f'/api/workspaces/{wid}/pide', json=cuerpo)
    assert r.status_code == 422 and 'año de presentación' in r.json()['detail']
    assert not [j for j in app.state.jobs.list(wid) if j.kind == 'pide']
    perfil['planificacion']['anio_presentacion'] = 2027                          # el del perfil vale
    assert cliente.post(f'/api/workspaces/{wid}/pide', json=cuerpo).status_code == 202


def test_sin_tipo_sigue_como_siempre(api):
    """072:RF-29 / 072:RF-4 — sin tipo, la petición de antes se admite igual y escribe los dos entregables."""
    cliente, _app, _perfil = api
    wid = cliente.post('/api/workspaces', json={'name': 'antes'}).json()['id']
    r = cliente.post(f'/api/workspaces/{wid}/pide', json={'project': 'P1', 'feeders': ['F1'], 'implementar': False,
                                                         'anio_presentacion': 2031})
    fin = _esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin['error']
    assert fin['result']['plazo'] is None and len(fin['result']['informes_planeamiento']) == 7
    assert cliente.post(f'/api/workspaces/{wid}/pide', json={'project': 'P1', 'plazo': 'corto_plazo'}).status_code == 422
