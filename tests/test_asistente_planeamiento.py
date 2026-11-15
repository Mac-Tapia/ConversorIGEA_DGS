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


# ------------------------------------------------------------------ corto plazo, PIDE y largo plazo desde la orden
class OtraTarea(Transformer):
    """El modelo en uso entiende otra cosa: el tipo de análisis lo dice la orden, no el modelo (072:RF-29)."""

    tareas = ('pide', 'obras_escalera', 'informe_estudio', 'evaluar_carga_nueva')

    def __init__(self, tarea, datos):
        super().__init__(datos)
        self.tarea = tarea

    def predecir(self, texto):
        return {'tarea': self.tarea, 'confianza': 1.0, 'datos': self.datos}


def test_largo_plazo_plantea_las_obras_sin_aplicarlas(api, monkeypatch):
    """072:RF-29 / 072:RF-34 / 072:RF-35 / 072:RF-18 — «el planeamiento de largo plazo» va a la ruta del PIDE con
    ``plazo='largo_plazo'`` e ``implementar=False``: antes acababa en un PIDE que aplicaba obras en «Con proyecto»."""
    cliente, app = api
    monkeypatch.setattr(services, '_asistente_modelos',
                        lambda: (OtraTarea('obras_escalera', _datos(periodo=[{'valor': '2031'}])), None))
    wid = cliente.post('/api/workspaces', json={'name': 'largo plazo'}).json()['id']
    plan = _proponer(cliente, wid, 'haz el planeamiento de largo plazo de P1 F1 para 2031')
    assert plan['tarea'] == 'pide' and plan['listo'] and plan['espera_confirmacion'], plan['faltan']
    assert any('largo plazo' in r for r in plan['razonamiento'])
    extras = services._ASISTENTE_PLANES[wid][plan['id']]['extras']
    cuerpo = pasos('pide', {'proyecto': 'P1', 'alimentadores': ['F1'], 'periodo': '2031'}, extras)[0].cuerpo
    assert cuerpo['plazo'] == 'largo_plazo' and cuerpo['implementar'] is False
    fin = _esperar(cliente, cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").json()['id'])
    assert fin['status'] == 'done', fin['error']
    hijo = next(j.public() for j in app.state.jobs.list(wid) if j.kind == 'pide')
    assert hijo['status'] == 'done', hijo.get('error')
    assert hijo['title'].startswith('Plan de largo plazo')
    # Solo los módulos del plan de largo plazo, no los siete de los dos entregables (072:RF-34).
    assert 0 < len(hijo['result']['informes_planeamiento']) < 7


def test_el_pide_es_el_de_siempre(api, monkeypatch):
    """072:RF-29 / 072:RF-18 — la orden del PIDE manda el mismo cuerpo que antes: sin plazo y aplicando sus obras."""
    cliente, _app = api
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer(_datos(periodo=[{'valor': '2031'}])), None))
    wid = cliente.post('/api/workspaces', json={'name': 'pide'}).json()['id']
    plan = _proponer(cliente, wid, 'haz el pide de P1 F1 para 2031')
    assert plan['tarea'] == 'pide' and plan['listo'], plan['faltan']
    extras = services._ASISTENTE_PLANES[wid][plan['id']]['extras']
    cuerpo = pasos('pide', {'proyecto': 'P1', 'alimentadores': ['F1'], 'periodo': '2031'}, extras)[0].cuerpo
    assert cuerpo == {'project': 'P1', 'feeders': ['F1'], 'anio_presentacion': 2031}


@pytest.mark.parametrize('texto', ['haz el planeamiento de P1 F1 para 2031',
                                   'haz el pide y el largo plazo de P1 F1 para 2031'])
def test_tipo_de_analisis_ambiguo_se_pregunta(api, monkeypatch, texto):
    """072:RF-29 — sin decir cuál, o diciendo dos, el plan pregunta: corto plazo, PIDE o largo plazo."""
    cliente, _app = api
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (Transformer(_datos(periodo=[{'valor': '2031'}])), None))
    wid = cliente.post('/api/workspaces', json={'name': 'ambiguo'}).json()['id']
    plan = _proponer(cliente, wid, texto)
    assert plan['tarea'] == 'pide' and not plan['listo']
    assert any('corto plazo' in f and 'PIDE' in f and 'largo plazo' in f for f in plan['faltan']), plan['faltan']


def _corto_plazo(api, monkeypatch, texto='estudio de corto plazo con la carga MINERA de 800 kW en F1 de P1 barra B7'):
    cliente, app = api
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco',
                        lambda ws, project, token=None: {'id': 'disco:t1', 'project': 'P1', 'feeders': ['F1']})
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (OtraTarea('informe_estudio', _datos()), None))
    wid = cliente.post('/api/workspaces', json={'name': 'corto plazo'}).json()['id']
    ws = app.state.store.get(wid)
    ws.informes.setdefault('formularios', {})['P1'] = {'estudio': {'solicitante': 'c'}}
    return cliente, wid, _proponer(cliente, wid, texto)


def test_corto_plazo_encadena_las_cuatro_etapas_en_orden(api, monkeypatch):
    """072:RF-29 / 072:RF-31 / 072:RF-32 / 072:RF-33 — «estudio de corto plazo con la carga X» es una lista de etapas
    con un solo clic: la carga, la escalera de obras, los estudios y el informe de estudio, en ese orden."""
    llamadas = []
    monkeypatch.setattr(services, 'agente_proyecto', lambda ws, ctx, datos, base, http=None, reiniciar=False, **kw: (
        llamadas.append((datos, kw)) or {'completo': True, 'etapas': {'informe': {'estado': 'hecha', 'resultado': {
            'informe': 'estudio.docx'}}}, 'datos': datos}))
    cliente, wid, plan = _corto_plazo(api, monkeypatch)
    assert plan['tarea'] == 'evaluar_carga_nueva' and plan['modo'] == 'etapas', plan
    assert plan['listo'] and plan['escribe'], plan['faltan']
    assert [p.split(' ')[0] for p in plan['pasos']] == ['carga', 'obras', 'estudios', 'informe']
    assert not llamadas
    fin = _esperar(cliente, cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar").json()['id'])
    assert fin['status'] == 'done', fin['error']
    (datos, kw), = llamadas
    assert [e.tarea for e in kw['etapas']] == ['carga_nueva_sola', 'obras_escalera', 'estudios', 'informe_estudio']
    assert datos['nueva']['Kw'] == 800.0 and datos['formulario'] == {'solicitante': 'c'}
    assert 'corto' in kw['control'] and 'estudio.docx' in fin['result']['entregables']


def test_corto_plazo_sin_calibracion_ni_formulario_lo_dice(api, monkeypatch):
    """072:RF-33 / 070:RF-51 — la escalera y los estudios parten de la calibración, y el informe de su formulario."""
    cliente, _app = api
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *_a, **_k: None)
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (OtraTarea('informe_estudio', _datos()), None))
    wid = cliente.post('/api/workspaces', json={'name': 'sin nada'}).json()['id']
    plan = _proponer(cliente, wid, 'estudio de corto plazo con la carga MINERA de 800 kW en F1 de P1 barra B7')
    assert plan['tarea'] == 'evaluar_carga_nueva' and not plan['listo']
    assert any('calibración' in f for f in plan['faltan']) and any('formulario' in f for f in plan['faltan'])


class WebCortoPlazo:
    """La API de la web, sustituida: cada POST es un trabajo que termina; los planes devuelven su ficha."""

    def __init__(self):
        self.llamadas = []

    def request(self, metodo, url, **kw):
        ruta = url.split('/api/workspaces/w', 1)[-1] if '/api/workspaces/w' in url else url.split('/api', 1)[-1]
        self.llamadas.append((metodo, ruta, kw.get('json') or kw.get('data')))

        class R:
            def __init__(s, codigo, datos):
                s.status_code, s._d, s.content, s.text = codigo, datos, b'x', str(datos)

            def json(s):
                return s._d

        if ruta.startswith('/jobs/'):
            return R(200, {'id': ruta[6:], 'status': 'done', 'result': {}})
        if ruta.startswith('/demanda/ajuste/ultimo'):
            return R(200, {'ajuste': {'id': 'disco:t'}})
        if ruta.startswith('/pf/estudios?'):
            return R(200, {'ofrecidos': [{'clave': 'tension'}]})
        if ruta in ('/lote/plan', '/pf/estudios/plan'):
            return R(200, {'token': 'tk'})
        return R(202, {'id': ruta.strip('/').replace('/', '_'), 'status': 'queued'})


def test_corto_plazo_va_por_las_rutas_de_la_web_en_orden(tmp_path):
    """072:RF-33 / 072:RF-18 — la carga, la escalera, los estudios y el informe, por sus rutas y en ese orden."""
    from convertersmartgrid.asistente.ejecutor import ClienteWeb
    from convertersmartgrid.asistente.orquestador import ETAPAS_CORTO_PLAZO, PuntoDeControl, ejecutar_proyecto

    web = WebCortoPlazo()
    datos = {'proyecto': 'P1', 'alimentadores': ['F1'], 'sed': 'MINERA', 'formulario': {'solicitante': 'c'},
             'nueva': {'Kw': 800.0, 'FP': .98, 'barra': 'B7', 'SED': 'MINERA', 'alimentador': 'F1', 'nombre': 'MINERA'}}
    r = ejecutar_proyecto(datos, cliente=ClienteWeb(web, 'http://x', 'w', intervalo_s=0),
                          control=PuntoDeControl.abrir(tmp_path / 'corto.json'),
                          proceso=lambda *_a: pytest.fail('sin procesos'), etapas=ETAPAS_CORTO_PLAZO)
    assert r['completo']
    rutas = [x[1] for x in web.llamadas if x[0] == 'POST']
    assert rutas == ['/lote/plan', '/lote/tk/apply', '/pf/obras/escalera', '/pf/estudios/plan',
                     '/pf/estudios/tk/ejecutar', '/informes/estudio']


def test_un_ejemplo_neutro_de_cada_tipo_y_el_interprete_lo_respeta():
    """072:RF-29 — el catálogo trae un ejemplo sin datos de ninguna empresa de cada tipo de análisis, y el intérprete
    manda el corto y el largo plazo a su tarea aunque el modelo en uso entienda otra; consultar no es planificar."""
    from convertersmartgrid.asistente.interprete import interpretar
    from convertersmartgrid.asistente.sinteticos import normalizar
    from convertersmartgrid.asistente.tareas import TAREAS, TIPOS_DE_ANALISIS, tipos_de_analisis_de

    for tipo, tarea in TIPOS_DE_ANALISIS.items():
        assert [p for p in TAREAS[tarea].plantillas if tipos_de_analisis_de(normalizar(p)) == [tipo]], tipo
    otra = OtraTarea('estado', {})
    assert interpretar('haz el planeamiento de largo plazo de P1 F1', transformer=otra).tarea == 'pide'
    assert interpretar('corre el estudio de corto plazo con la carga S9 en F1 de P1', transformer=otra).tarea == 'evaluar_carga_nueva'
    assert interpretar('dame los resultados del largo plazo de P1',
                       transformer=OtraTarea('resultados_pide', {})).tarea == 'resultados_pide'
    assert interpretar('¿qué es el largo plazo?', transformer=OtraTarea('pregunta', {})).tarea == 'pregunta'
    assert tipos_de_analisis_de(normalizar('haz el pide de P1 con el libro "D:/largo plazo/capex.xlsx"')) == ['pide']


def test_f6_el_subtipo_dudoso_no_entra_en_el_plan(api, monkeypatch):
    """026:RF-14 — «informe de estudio eléctrico del …» salía de «transferencia» al 75 %, y ese subtipo se guardaba como
    etiqueta del informe: por debajo del umbral vale el del formulario del 4.4; por encima, el del clasificador."""
    cliente, _app = api

    class Clasificador:
        def __init__(self, confianza):
            self.confianza = confianza

        def clasificar(self, texto):
            return {'tipo': 'estudio', 'subtipo': 'transferencia', 'confianza_tipo': .99, 'confianza_subtipo': self.confianza}

    monkeypatch.setattr(services, '_asistente_modelos', lambda: (OtraTarea('informe_estudio', _datos()), None))
    for confianza, entra in ((.75, False), (.95, True)):
        monkeypatch.setattr(services, '_asistente_clasificador', lambda c=confianza: Clasificador(c))
        wid = cliente.post('/api/workspaces', json={'name': f'subtipo {confianza}'}).json()['id']
        plan = _proponer(cliente, wid, 'genera el informe de estudio electrico del F1 de P1')
        assert (plan['datos'].get('subtipo') == 'transferencia') is entra, plan['datos']
        assert any('subtipo' in r for r in plan['razonamiento'])
