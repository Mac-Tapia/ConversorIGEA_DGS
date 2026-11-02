"""061: observación persistente y operación por la cola real; no sustituye aceptación nativa."""
import json
import threading
import time
from pathlib import Path

import pytest


def test_diario_reabre_contexto_y_detecta_proceso_no_observado(tmp_path):
    """061:RF-1 / 061:RF-2: el contexto inicial no cambia con el espacio ni se reejecuta."""
    from convertersmartgrid.asistente.observacion import RegistroOperaciones
    r=RegistroOperaciones(tmp_path/'operaciones.sqlite3','w')
    r.anotar({'id':'j','workspace_id':'w','status':'queued','kind':'convert','lane':'engine','created_at':1},
             {'source_fingerprint':'original'})
    r.anotar({'id':'j','workspace_id':'w','status':'running','kind':'convert','lane':'engine','created_at':1},
             {'source_fingerprint':'otra'})
    nuevo=RegistroOperaciones(r.ruta,'w')
    fila=nuevo.leer(vivos=set())[0]
    assert fila['contexto']['source_fingerprint']=='original'
    assert fila['seguimiento']=='interrumpido' and fila['status']=='running'
    assert nuevo.leer(vivos={'j'})[0]['seguimiento']=='en_sesion'


def test_diario_rechaza_espacio_ajeno(tmp_path):
    """061:RF-3: el diario de un espacio no admite el trabajo de otro."""
    from convertersmartgrid.asistente.observacion import RegistroOperaciones
    with pytest.raises(ValueError,match='espacio'):
        RegistroOperaciones(tmp_path/'o.sqlite3','a').anotar({'id':'j','workspace_id':'b','status':'done'}, {})


def test_evidencia_se_custodia_sin_promover(tmp_path):
    """061:RF-8 / 061:RF-9: copiar un informe no lo convierte en un modelo activo."""
    from convertersmartgrid.asistente.observacion import registrar_evidencia,leer_evidencias
    p=tmp_path/'entrenamiento.json';p.write_text(json.dumps({'training_completed':True,'promovido':False}))
    raiz=tmp_path/'asistente'
    d=registrar_evidencia(raiz,p,familia='gru',etiqueta='contrato')
    p.write_text('{}')
    e=leer_evidencias(raiz)[0]
    assert e['id']==d['id'] and e['informe']['training_completed'] and not e['activacion_acreditada']
    assert not (raiz/'model_registry').exists()
    (raiz/'observacion/evidencias'/f'{d["id"]}.json').write_text('{}')
    with pytest.raises(ValueError,match='integridad'):leer_evidencias(raiz)


def test_fallo_publicacion_no_deja_trabajo_huerfano():
    """061:RF-10: fallar el diario inicial no reserva un carril para siempre."""
    from convertersmartgrid.web.jobs import JobManager
    def fallar(*args):raise OSError('disco no disponible')
    m=JobManager(fallar)
    try:
        with pytest.raises(OSError):m.submit('w','contrato','no ejecutar',lambda ctx:pytest.fail('ejecutó'))
        assert m.list()==[] and m.en_curso()==0
    finally:m.shutdown()


def test_monitor_api_trabajo_real_y_persistencia(tmp_path,monkeypatch):
    """061:RF-1 / 061:RF-2 / 061:RF-3 / 061:RF-9: se observa una operación real de archivos."""
    from fastapi.testclient import TestClient
    from convertersmartgrid.web.app import create_app
    monkeypatch.setenv('CSG_ASISTENTE_DATA',str(tmp_path/'modelos'))
    monkeypatch.setenv('CSG_WEB_FRONTEND',str(tmp_path/'sin_front'))
    root=tmp_path/'web'
    app=create_app(root)
    with TestClient(app) as c:
        wid=c.post('/api/workspaces').json()['id'];otro=c.post('/api/workspaces').json()['id']
        def operacion(ctx):
            p=tmp_path/'resultado.txt';p.write_text('operación real de contrato',encoding='utf-8')
            ctx.progress(1,1,'archivo guardado')
            return {'bytes':p.stat().st_size}
        job=app.state.jobs.submit(wid,'archivo_contrato','Guardar archivo de prueba',operacion)
        for _ in range(200):
            if job.status in ('done','failed'):break
            time.sleep(.01)
        assert job.status=='done'
        vista=c.get(f'/api/workspaces/{wid}/asistente/monitor')
        assert vista.status_code==200
        data=vista.json();fila=data['trabajos'][0]
        assert fila['id']==job.id and fila['result']['bytes']>0
        assert fila['aceptacion_nativa'] is None
        assert not data['autonomia_habilitada'] and data['modo']=='supervisado'
        assert c.get(f'/api/workspaces/{otro}/asistente/monitor').json()['trabajos']==[]
        assert c.get(f'/api/workspaces/{wid}/asistente/monitor?limite=0').status_code==422
    with TestClient(create_app(root)) as c:
        fila=c.get(f'/api/workspaces/{wid}/asistente/monitor').json()['trabajos'][0]
        assert fila['status']=='done' and fila['seguimiento']=='historico'


def test_codigo_uno_no_completa_etapa(tmp_path):
    """061:RF-6: código1 del sistema no permite ejecutar etapas siguientes."""
    from convertersmartgrid.asistente.orquestador import PuntoDeControl,Etapa,ejecutar_proyecto
    from types import SimpleNamespace
    control=PuntoDeControl.abrir(tmp_path/'c.json')
    with pytest.raises(RuntimeError,match='código'):
        ejecutar_proyecto({},cliente=SimpleNamespace(cancelado=lambda:False),control=control,
                         proceso=lambda *a:{'codigo':1},etapas=(Etapa('sistema','contrato',proceso=True),))
    assert not control.hecha('sistema')


def test_identidad_checkpoint_y_reinicio_conservan_historia(tmp_path):
    """061:RF-7: el checkpoint de otra fuente no se utiliza ni se borra al reiniciar."""
    from convertersmartgrid.asistente.observacion import preparar_control
    p=tmp_path/'control.json'
    c=preparar_control(p,{'source_fingerprint':'a'},reiniciar=False)
    c.marcar('fuente','hecha')
    with pytest.raises(ValueError,match='identidad'):preparar_control(p,{'source_fingerprint':'b'},reiniciar=False)
    nuevo=preparar_control(p,{'source_fingerprint':'b'},reiniciar=True)
    assert not nuevo.hecha('fuente') and len(list(tmp_path.glob('control.anterior-*.json')))==1


def test_avance_y_cambio_de_fuente_durante_proyecto(tmp_path):
    """061:RF-4 / 061:RF-7: avanza con la fuente cargada por él y para ante un cambio posterior."""
    from types import SimpleNamespace
    from convertersmartgrid.asistente.observacion import preparar_control
    from convertersmartgrid.asistente.orquestador import ejecutar_proyecto,Etapa
    identidad={'fuente':None};visto=[]
    c=preparar_control(tmp_path/'p.json',dict(identidad),reiniciar=False)
    c.identidad_actual=lambda:dict(identidad)
    def paso(*a):identidad['fuente']='cargada';return {'codigo':0}
    r=ejecutar_proyecto({},cliente=SimpleNamespace(cancelado=lambda:False),control=c,proceso=paso,
        etapas=(Etapa('fuente','contrato',proceso=True),),avance=lambda *a:visto.append(a))
    assert r['completo'] and visto[-1]==(1,1,'fuente')
    assert c.estado['identidad']['fuente']=='cargada'
    identidad['fuente']='ajena'
    with pytest.raises(ValueError,match='identidad'):c.validar_identidad()


def test_cancelacion_api_se_refleja_en_monitor(tmp_path,monkeypatch):
    """061:RF-5: cancela por la ruta existente, sin crear otro ejecutor."""
    from fastapi.testclient import TestClient
    from convertersmartgrid.web.app import create_app
    monkeypatch.setenv('CSG_ASISTENTE_DATA',str(tmp_path/'asistente'))
    app=create_app(tmp_path/'web');iniciado=threading.Event()
    with TestClient(app) as cliente:
        wid=cliente.post('/api/workspaces').json()['id']
        def esperar(ctx):
            iniciado.set()
            while not ctx.cancel.wait(.01):pass
            ctx.check_cancel()
        job=app.state.jobs.submit(wid,'contrato_cancelar','Contrato cancelable',esperar,lane='asistente')
        assert iniciado.wait(2)
        assert cliente.post(f'/api/jobs/{job.id}/cancel').status_code==200
        for _ in range(100):
            if job.status=='cancelled':break
            time.sleep(.01)
        vista=cliente.get(f'/api/workspaces/{wid}/asistente/monitor').json()
        assert vista['trabajos'][0]['status']=='cancelled'


def test_identidad_no_se_modifica_por_tamper_de_metadatos(tmp_path):
    """061:RF-8: la familia declarada también forma parte de la identidad de evidencia."""
    from convertersmartgrid.asistente.observacion import registrar_evidencia,leer_evidencias
    p=tmp_path/'i.json';p.write_text('{"status":"RECHAZADO"}')
    meta=registrar_evidencia(tmp_path,p,familia='gru',etiqueta='contrato')
    f=tmp_path/'observacion/evidencias'/f'{meta["id"]}.meta.json'
    dato=json.loads(f.read_text());dato['familia']='pinn';f.write_text(json.dumps(dato))
    with pytest.raises(ValueError,match='integridad'):leer_evidencias(tmp_path)


def test_api_rechaza_nuevo_trabajo_si_no_hay_diario(tmp_path,monkeypatch):
    """061:RF-10: error503 visible y cero tareas admitidas sin registro inicial."""
    from fastapi.testclient import TestClient
    from convertersmartgrid.web.app import create_app
    from convertersmartgrid.asistente.observacion import RegistroOperaciones
    monkeypatch.setenv('CSG_ASISTENTE_DATA',str(tmp_path/'asistente'))
    def fallo(*a,**k):raise OSError('sin disco')
    monkeypatch.setattr(RegistroOperaciones,'anotar',fallo)
    app=create_app(tmp_path/'web')
    with TestClient(app) as c:
        wid=c.post('/api/workspaces').json()['id']
        assert c.post(f'/api/workspaces/{wid}/asistente/entrenar').status_code==503
        assert app.state.jobs.en_curso()==0
        monitor=c.get(f'/api/workspaces/{wid}/asistente/monitor').json()
        assert not monitor['registro_integro'] and monitor['errores_observacion']


def test_diario_no_carga_torch_ni_contiene_codigo_ejecutable(tmp_path):
    """061:RF-1 / 061:RF-9: la observación funciona sin iniciar modelos ML."""
    import subprocess,sys
    script=('import sys;from pathlib import Path;'
        'from convertersmartgrid.asistente.observacion import RegistroOperaciones;'
        'r=RegistroOperaciones(Path(sys.argv[1]),"w");'
        'r.anotar({"id":"j","workspace_id":"w","status":"done"},{});'
        'assert r.leer(vivos=set());assert "torch" not in sys.modules')
    r=subprocess.run([sys.executable,'-c',script,str(tmp_path/'o.sqlite3')],capture_output=True,text=True)
    assert r.returncode==0,r.stderr


def test_flujo_respeta_el_servidor_que_lo_encolo(tmp_path,monkeypatch):
    """061:RF-3 / 061:RF-5: el proceso no salta a otro servidor/espacio por un puerto fijo."""
    from types import SimpleNamespace
    from convertersmartgrid.web.workspace import WorkspaceStore
    from convertersmartgrid.web import services
    from convertersmartgrid.asistente import orquestador
    ws=WorkspaceStore(tmp_path/'web').create();vistas=[]
    ctx=SimpleNamespace(job=SimpleNamespace(id='padre'),cancel=threading.Event(),
        run_process=lambda cmd,**kw:vistas.append(cmd) or 0,log=lambda *a:None,progress=lambda *a:None)
    def contrato(datos,**kw):return kw['proceso']('sistema_completo',datos)
    monkeypatch.setattr(orquestador,'ejecutar_proyecto',contrato)
    services.agente_proyecto(ws,ctx,{'sistema':'Sistema de contrato','periodo':'2025-01'},
                             'http://127.0.0.1:9898',http=object())
    cmd=vistas[0]
    assert cmd[cmd.index('--url')+1]=='http://127.0.0.1:9898'
    assert cmd[cmd.index('--espacio')+1]==ws.id
