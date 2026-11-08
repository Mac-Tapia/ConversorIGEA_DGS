"""072:RF-18, 072:RF-24, 072:RF-27, 072:RF-28: borde anual web sin motor."""
import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient
from convertersmartgrid.web import services
from convertersmartgrid.web.app import create_app


def raw(value):
    return json.dumps(value).encode()


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'no_front'))
    monkeypatch.setenv('CSG_AUTOENTRENAMIENTO', '0')
    monkeypatch.setattr(services, 'native_action_context', lambda ws, p, fs, a: {'project': p, 'feeders': fs})
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.datos_perfil', lambda: {'estudios': {
        'tension_min_pu': .95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}})
    monkeypatch.setattr('convertersmartgrid.perfil_empresa.estructura_empresa', lambda: None)
    with TestClient(create_app(tmp_path / 'web', host='0.0.0.0')) as c:
        wid = c.post('/api/workspaces', json={'name': 'Prueba anual'}).json()['id']
        yield c, wid


def fuentes(c, wid, **changes):
    evaluation = raw({'estado': 'aceptado', 'uso': 'planeamiento_anual', 'modelo': 'prueba',
        'dataset_sha256': 'd'*64, 'horizonte_anios': 5, 'anio_base': 2030})
    short = {'estado': 'aceptado', 'caso': r'P.IntPrj\Casos\Corto.IntCase',
        'escenario': r'P.IntPrj\Escenarios\Corto.IntScenario', 'anio': 4, 'anio_base': 2030,
        'variaciones': [r'P.IntPrj\Obras\Corto.IntScheme']}
    projection = {'proyecto': 'P', 'anio_base': 2030, 'modelo': 'prueba', 'dataset_sha256': 'd'*64,
        'evaluacion': {'ruta': r'Z:\no_se_debe_leer.json', 'sha256': hashlib.sha256(evaluation).hexdigest()},
        'filas': [{'anio': 5, 'alimentador': 'F1', 'carga': r'P.IntPrj\Red\L.ElmLod',
            'clase': 'escaladas', 'objetivo': 'F1', 'p_kw': 100, 'q_kvar': 10}]}
    projection.update(changes)
    return c.post(f'/api/workspaces/{wid}/pide/fuentes', files={
        'perfil': ('perfil.json', raw(projection), 'application/json'),
        'evaluacion': ('evaluacion.json', evaluation, 'application/json'),
        'corto_plazo': ('corto.json', raw(short), 'application/json')})


def cuerpo(source):
    return {'project': 'P', 'feeders': ['F1'], 'modo': 'anual', 'anual': {
        'estudio_id': 'Ensayo_anual', 'anio_fin': 5, 'corto_plazo': source['corto_plazo'],
        'proyeccion_anual': source['proyeccion_anual'], 'obras_por_anio': []}}


def esperar(c, jid):
    for _ in range(100):
        j = c.get(f'/api/jobs/{jid}').json()
        if j['status'] in ('done', 'failed', 'cancelled'):
            return j
        time.sleep(.02)
    pytest.fail('la cola no terminó')


def test_fuentes_custodiadas_y_controlador_unico_en_carril_pf(api, monkeypatch):
    """072:RF-18, 072:RF-24: el archivo no abre su ruta anidada; el trabajo usa pide_pf."""
    c, wid = api
    uploaded = fuentes(c, wid)
    assert uploaded.status_code == 200, uploaded.text
    calls = []
    def runner(ws, ctx, script, plan, **kw):
        calls.append((script, plan, kw))
        report = ws.out_dir / 'anual.json'
        report.write_text('{}')
        return 0, {'modo': 'anual', 'estado': 'completo', 'anios': [],
            'restitucion': {'ok': True, 'diferencias': []}, 'aceptacion_nativa': False}, report
    monkeypatch.setattr(services, '_guion_pf', runner)
    r = c.post(f'/api/workspaces/{wid}/pide', json=cuerpo(uploaded.json()))
    assert r.status_code == 202, r.text
    fin = esperar(c, r.json()['id'])
    assert fin['lane'] == 'powerfactory' and fin['status'] == 'done', fin
    assert calls[0][0] == 'pide_pf.py' and calls[0][1]['modo'] == 'anual'
    assert calls[0][2]['cancelable'] is True
    assert fin['result']['fuentes']['original_perfil_sha256'] == uploaded.json()['fuentes']['original_perfil_sha256']
    assert fin['result']['aceptacion_nativa'] is False


def test_faltantes_no_encolan_ni_abren_motor(api, monkeypatch):
    """072:RF-28: perfil ausente, identidad ambigua y ruta externa se rechazan antes de encolar."""
    c, wid = api
    monkeypatch.setattr(services, '_guion_pf', lambda *a, **k: pytest.fail('no abrir motor'))
    assert c.post(f'/api/workspaces/{wid}/pide', json={'project':'P','modo':'anual'}).status_code == 422
    uploaded = fuentes(c, wid).json()
    body = cuerpo(uploaded)
    body['anual']['proyeccion_anual']['ruta'] = __file__
    assert c.post(f'/api/workspaces/{wid}/pide', json=body).status_code == 422
    body = cuerpo(uploaded)
    body['anual']['corto_plazo']['caso'] = 'Corto'
    assert c.post(f'/api/workspaces/{wid}/pide', json=body).status_code == 422
    assert not [j for j in c.app.state.jobs.list(wid) if j.kind == 'pide']


def test_perfil_no_aceptado_y_fase_incompleta_se_bloquean(api):
    """072:RF-24: subir no concede aceptación y las fases nunca se reparten."""
    c, wid = api
    r = fuentes(c, wid, filas=[{'anio':5,'alimentador':'F1','carga':'L','clase':'escaladas',
        'objetivo':'F1','p_kw':100,'q_kvar':10,'fases': {'r':{'p_kw':100,'q_kvar':10}}}])
    assert r.status_code == 200
    assert c.post(f'/api/workspaces/{wid}/pide', json=cuerpo(r.json())).status_code == 422


def test_cancelacion_conserva_informe_de_restitucion(api, monkeypatch):
    """072:RF-27: la petición de cancelar espera el informe y conserva su restitución."""
    import threading
    c, wid = api
    entered = threading.Event()
    def runner(ws, ctx, script, plan, **kw):
        entered.set()
        assert ctx.cancel.wait(5)
        report = ws.out_dir / 'cancelado.json'
        report.write_text('{}')
        return 0, {'modo':'anual','estado':'cancelado','anios':[],
            'restitucion':{'ok':True,'diferencias':[]},'aceptacion_nativa':False}, report
    monkeypatch.setattr(services, '_guion_pf', runner)
    r = c.post(f'/api/workspaces/{wid}/pide', json=cuerpo(fuentes(c,wid).json()))
    assert r.status_code == 202, r.text
    assert entered.wait(5)
    assert c.post(f"/api/jobs/{r.json()['id']}/cancel").status_code == 200
    fin = esperar(c, r.json()['id'])
    assert fin['status'] == 'cancelled' and fin['result']['restitucion']['ok'] is True


def test_otra_custodia_y_fuente_alterada_no_encolan(api):
    """072:RF-28: una huella válida de otro espacio no concede acceso a su custodia."""
    from pathlib import Path
    c, wid = api
    source = fuentes(c, wid).json()
    otro = c.post('/api/workspaces', json={'name':'Otro espacio'}).json()['id']
    assert c.post(f'/api/workspaces/{otro}/pide',json=cuerpo(source)).status_code == 422
    Path(source['proyeccion_anual']['ruta']).write_text('{}')
    r = c.post(f'/api/workspaces/{wid}/pide',json=cuerpo(source))
    assert r.status_code == 422 and 'huella' in r.json()['detail']
    assert not [j for j in c.app.state.jobs.list(wid) if j.kind == 'pide']


def test_historia_conserva_campos_y_no_admite_anual_oculto(api, monkeypatch):
    """072:RF-18: el contrato nuevo mantiene todas las opciones del PIDE histórico."""
    c, wid = api
    calls=[]
    def history(ws,ctx,p,fs,**kw):
        calls.append((p,fs,kw))
        return {'project':p}
    monkeypatch.setattr(services,'pide_ejecutar',history)
    body={'project':'P','feeders':['F1'],'capex':'capex.xlsx','anio_presentacion':2031,
          'formato_01':'formato.xlsx','implementar':False}
    r=c.post(f'/api/workspaces/{wid}/pide',json=body)
    assert r.status_code==202 and esperar(c,r.json()['id'])['status']=='done'
    assert calls==[('P',['F1'],{'capex':'capex.xlsx','implementar':False,
        'anio_presentacion':2031,'formato_01':'formato.xlsx'})]
    body=cuerpo(fuentes(c,wid).json()); body['modo']='historico'
    assert c.post(f'/api/workspaces/{wid}/pide',json=body).status_code==422


def test_aceptacion_no_se_inventa_al_subir(api):
    """072:RF-24: evaluación rechazada conserva su estado y bloquea antes de la cola."""
    c,wid=api
    evaluation=raw({'estado':'rechazado','uso':'planeamiento_anual','modelo':'prueba',
        'dataset_sha256':'d'*64,'horizonte_anios':5,'anio_base':2030})
    source=fuentes(c,wid).json()
    from pathlib import Path
    profile_path=Path(source['proyeccion_anual']['ruta'])
    original=json.loads((profile_path.parent/'original_perfil.json').read_bytes())
    original['evaluacion']['sha256']=hashlib.sha256(evaluation).hexdigest()
    short=(profile_path.parent/'corto_plazo.json').read_bytes()
    r=c.post(f'/api/workspaces/{wid}/pide/fuentes',files={'perfil':('p.json',raw(original)),
        'evaluacion':('e.json',evaluation),'corto_plazo':('c.json',short)})
    assert r.status_code==200
    rejected=c.post(f'/api/workspaces/{wid}/pide',json=cuerpo(r.json()))
    assert rejected.status_code==422 and 'evaluación aceptada' in rejected.json()['detail']


def test_revalidar_fuentes_antes_del_motor_y_exigir_restitucion(api, monkeypatch):
    """072:RF-27, 072:RF-28: ni TOCTOU antes del arranque ni informe sin relectura da éxito."""
    from pathlib import Path
    c,wid=api
    source=fuentes(c,wid).json()
    ws=c.app.state.store.get(wid)
    plan=services.pide_preparar_anual(ws,'P',['F1'],cuerpo(source)['anual'])
    class Contexto:
        def check_cancel(self): pass
        def log(self,m): pass
    monkeypatch.setattr(services,'_guion_pf',lambda *a,**k:(0,{'estado':'completo'},ws.out_dir/'sin_relectura.json'))
    report=services.pide_anual_ejecutar(ws,Contexto(),plan)
    assert report['estado']=='bloqueado_restitucion' and report['estado_trabajo']=='parcial'
    assert report['aceptacion_nativa'] is False
    Path(source['proyeccion_anual']['ruta']).write_text('{}')
    monkeypatch.setattr(services,'_guion_pf',lambda *a,**k:pytest.fail('no abrir motor tras cambiar fuentes'))
    with pytest.raises(services.UserError,match='huella'):
        services.pide_anual_ejecutar(ws,Contexto(),plan)
