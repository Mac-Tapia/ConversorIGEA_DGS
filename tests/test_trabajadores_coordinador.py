"""043:RF-13: entrypoints y errores reales; fixtures no son evidencia de entrenamientos."""
from pathlib import Path
import json
import subprocess
import sys
import pytest

RAIZ=Path(__file__).resolve().parents[1]
HERRAMIENTAS=('digital_twin_temporal_entrenar.py','evaluar_evolutivos.py',
              'asistente_embeddings.py','asistente_qlora.py')


@pytest.mark.parametrize('nombre',HERRAMIENTAS)
def test_entrypoint_existe_y_ayuda_sin_modelos(nombre):
    """043:RF-13: la herramienta real debe poder describir su contrato sin CUDA ni datos."""
    f=RAIZ/'tools'/nombre
    assert f.is_file(),nombre
    r=subprocess.run([sys.executable,'-X','utf8',str(f),'--help'],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==0,r.stderr


@pytest.mark.parametrize('nombre,opciones,reporte',[
    ('digital_twin_temporal_entrenar.py',['--cabeceras','ausente.xlsx','--raiz','raiz'],'temporal.json'),
    ('asistente_embeddings.py',['entrenar','--dataset','ausente'],'embeddings/decision.json'),
    ('asistente_qlora.py',['entrenar','--dataset','ausente'],'qlora/training_manifest.json')])
def test_datos_ausentes_dejan_informe_sin_inventar_exito(tmp_path,nombre,opciones,reporte):
    """043:RF-13: bloquear conserva evidencia; no puede declararse entrenamiento completado."""
    salida=tmp_path/reporte
    if nombre=='digital_twin_temporal_entrenar.py':args=opciones+['--output-json',str(salida)]
    else:args=opciones+(['--salida'] if 'qlora' in nombre else ['--destino'])+[str(salida.parent)]
    r=subprocess.run([sys.executable,'-X','utf8',str(RAIZ/'tools'/nombre),*args],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode!=0,r.stdout+r.stderr
    d=json.loads(salida.read_text(encoding='utf-8'))
    assert d['status']=='BLOQUEADO_POR_DATOS' and d['training_completed'] is False
    assert d.get('promovido') is False


def test_ayuda_asistente_admite_el_dataset_del_runner():
    """043:RF-13: el runner no debe enviar una opción inexistente a su propio trabajador."""
    r=subprocess.run([sys.executable,'-X','utf8',str(RAIZ/'tools/asistente_entrenar.py'),'--help'],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==0 and '--dataset-v2' in r.stdout


def test_guardia_del_coordinador_se_hereda_en_un_hijo_real(tmp_path,monkeypatch):
    """043:RF-6 / RF-13: un hijo real comparte la guardia viva sin soltarla ni duplicarla."""
    from convertersmartgrid.training_coordinator import BloqueoGPU
    from tools.reentrenar_modelos import _subproceso
    lock=tmp_path/'gpu.lock';monkeypatch.setenv('CSG_ML_GPU_LOCK',str(lock))
    reporte=tmp_path/'informe.json';script=tmp_path/'worker.py'
    script.write_text('from pathlib import Path\nfrom convertersmartgrid.trabajadores_ml import turno_gpu, escribir_informe\n'
        'with turno_gpu("contrato-sin-calculo-CUDA"):\n'
        f'    escribir_informe(Path({str(reporte)!r}),{{"status":"RECHAZADO","promovido":False,"training_completed":False}})\n',encoding='utf-8')
    with BloqueoGPU(lock,'padre-del-contrato'):
        resultado=_subproceso([sys.executable,str(script)],reporte,'gru')
        assert resultado['returncode']==0 and resultado['status']=='RECHAZADO'
        assert lock.exists()
    assert not lock.exists()


def test_runner_conserva_bloqueo_de_datos_del_worker(tmp_path):
    """043:RF-13: retorno 2 de datos faltantes no debe ocultar su motivo como error de entorno."""
    from tools.reentrenar_modelos import _subproceso
    reporte=tmp_path/'salida/decision.json'
    r=_subproceso([sys.executable,str(RAIZ/'tools/asistente_embeddings.py'),'entrenar',
        '--dataset',str(tmp_path/'ausente'),'--destino',str(reporte.parent)],reporte,'embeddings')
    assert r['status']=='BLOQUEADO_POR_DATOS' and 'dataset' in r['reason']


def test_cabecera_no_oculta_huecos_ni_objetivos_ausentes(tmp_path):
    """046:RF-3 / 043:RF-13: consumir el lector existente sin descartar objetivos ausentes."""
    from datetime import datetime,timedelta
    from openpyxl import Workbook
    from convertersmartgrid.digital_twin.temporal_entrenamiento import cargar_cabeceras
    libro=Workbook();h=libro.active;h.title='Cabecera contrato';h.append(['Fecha','kW'])
    inicio=datetime(2025,1,1)
    h.append([inicio,10.]);h.append([inicio+timedelta(minutes=30),12.])
    f=tmp_path/'cabecera.xlsx';libro.save(f)
    with pytest.raises(ValueError,match='huecos'):
        cargar_cabeceras(f,zona_horaria='UTC')


@pytest.fixture
def dataset_retrieval_contrato(tmp_path):
    """Documentos de contrato, no fuente electrica ni benchmark real del asistente."""
    import hashlib
    d=tmp_path/'dataset';d.mkdir();manifest={'partitions':{}}
    for p in ('train','validation','test'):
        r={'record_id':p,'group_id':p,'quality':'context',
           'texto':f'documento del contrato {p} con contenido verificable de prueba',
           'provenance':{'source_url':'fuente'}}
        f=d/(p+'.jsonl');f.write_text(json.dumps(r)+'\n',encoding='utf-8')
        manifest['partitions'][p]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'count':1}
    (d/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return d


@pytest.mark.parametrize('caso',['duplicada','sin_independencia','extractiva'])
def test_consulta_train_no_se_disfraza_de_prueba_reservada(dataset_retrieval_contrato,caso):
    """043:RF-13 / 047:RF-4: no evaluar sobre las mismas consultas usadas para ajustar."""
    from tools.asistente_embeddings import cargar_dataset
    d=dataset_retrieval_contrato
    train={'pregunta':'consulta del entrenamiento','fuente':'fuente#train','confirmada':True}
    test={**train,'independent_evaluation':True}
    if caso=='sin_independencia':test={'pregunta':'consulta distinta','fuente':'fuente#test','confirmada':True}
    if caso=='extractiva':
        test['pregunta']='documento del contrato train con contenido verificable de prueba'
    else:(d/'retrieval_train.jsonl').write_text(json.dumps(train)+'\n',encoding='utf-8')
    (d/'retrieval_test.jsonl').write_text(json.dumps(test)+'\n',encoding='utf-8')
    with pytest.raises(ValueError,match='independ|entrenamiento'):
        cargar_dataset(d,entrenamiento=False)


def test_recuperacion_admite_documento_compartido_con_consulta_nueva(dataset_retrieval_contrato):
    """047:RF-4 / 043:RF-13: compartir corpus RAG no permite repetir la consulta supervisada."""
    from tools.asistente_embeddings import cargar_dataset
    d=dataset_retrieval_contrato
    (d/'retrieval_test.jsonl').write_text(json.dumps({'pregunta':'consulta independiente del contrato',
        'fuente':'fuente#train','confirmada':True,'independent_evaluation':True})+'\n',encoding='utf-8')
    _,pares=cargar_dataset(d,entrenamiento=False)
    assert len(pares)==1


def test_busqueda_evolutiva_no_se_presenta_como_red_entrenada(tmp_path,capsys):
    """043:RF-13: completar evaluacion de busqueda no inventa un entrenamiento de pesos."""
    from tools.reentrenar_modelos import verificar
    from convertersmartgrid.training_coordinator import ORDEN_MODELOS
    r=tmp_path/'report.json'
    etapas=[{'model':n,'status':'RECHAZADO','training_completed':n!='evolutivos',
             'evaluation_completed':n=='evolutivos'} for n in ORDEN_MODELOS]
    r.write_text(json.dumps({'complete':True,'stages':etapas}),encoding='utf-8')
    assert verificar(r,fail_on_incomplete=True)==0
    d=json.loads(capsys.readouterr().out)
    assert d['all_required_operations_completed'] is True and d['all_trained'] is False


def test_memoria_insuficiente_es_error_de_entorno():
    """043:RF-12 / RF-13: recursos agotados no se diagnostican como datos ausentes."""
    from convertersmartgrid.training_coordinator import MemoriaMLInsuficiente
    from convertersmartgrid.trabajadores_ml import fallo
    assert fallo(MemoriaMLInsuficiente('contrato'))['status']=='ERROR_ENTORNO'


@pytest.mark.parametrize('cambio', ['bajo', 'nan', 'sin_reales', 'retroceso', 'sin_reapertura'])
def test_puertas_dataset_no_aprueban_sin_evidencia(cambio):
    """050:RF-5 / 043:RF-5: pesos guardados no acreditan calidad ni recarga."""
    from convertersmartgrid.asistente.entrenamiento_dataset import puertas_dataset
    prueba = {'acierto_tarea': .99, 'f1_datos': .99, 'ejemplos': 4}
    reales = dict(prueba)
    actual = None
    smoke = {'ok': True}
    if cambio == 'bajo': prueba['f1_datos'] = .2
    if cambio == 'nan': prueba['acierto_tarea'] = float('nan')
    if cambio == 'sin_reales': reales = None
    if cambio == 'retroceso': actual = {**prueba, 'f1_datos': .999}
    if cambio == 'sin_reapertura': smoke = {'ok': False}
    gates = puertas_dataset('ordenes', prueba, reales, actual, smoke)
    assert gates['approved'] is False and gates['fallos']


@pytest.mark.parametrize('solo', ['ordenes', 'informes'])
@pytest.mark.parametrize('quality,smoke_ok', [('gold_human',True),('silver_deterministic',True),('gold_human',False),('gold_native',True)])
def test_dataset_registra_candidato_y_conserva_puntero(tmp_path, monkeypatch, solo, quality, smoke_ok):
    """050:RF-4 / RF-5: candidato íntegro y reabierto, nunca activación individual."""
    from contextlib import nullcontext
    from types import SimpleNamespace
    from convertersmartgrid import trabajadores_ml, training_coordinator
    from convertersmartgrid.asistente import entrenamiento_dataset as worker
    from convertersmartgrid.asistente import transformer, clasificador
    from convertersmartgrid.model_registry import RegistroModelo
    modulo = transformer if solo == 'ordenes' else clasificador
    partes = {p: [{'texto': f'{p} convierte la red', 'quality': quality,
                   'tarea': 'convertir', 'datos': [],
                   'resultado': {'tipo_informe': 'estudio', 'subtipo': 'refuerzo'}}]
              for p in ('train', 'validation', 'test')}
    if solo=='ordenes':
        for p,rows in partes.items():
            rows.append({'texto':f'Informe de red {p}','quality':'gold_human','tipo':'informe',
                         'tarea':'clasificar_informe','datos':[]})
    monkeypatch.setattr(trabajadores_ml, 'leer_dataset_v2', lambda _: (partes, {'sha256': 'a'*64}))
    monkeypatch.setattr(trabajadores_ml, 'turno_gpu', lambda _: nullcontext())
    monkeypatch.setattr(training_coordinator, 'exigir_memoria_ml', lambda *a, **kw: None)
    monkeypatch.setattr(modulo, 'cargar', lambda: None)
    class Red:
        def state_dict(self): return {}
    def entrenar(*args):
        assert len(args[0])==1, 'Las descripciones de informes no son órdenes del operador'
        cfg = args[-1]
        return SimpleNamespace(cfg=cfg, red=Red(), simbolos=['a'], tareas=sorted(transformer.TAREAS),
            subtipos=['refuerzo'], temperatura=1.,
            predecir=lambda _: {'tarea':'convertir', 'datos':[], 'confianza':.99},
            clasificar=lambda _: {'tipo':'estudio','subtipo':'refuerzo','confianza_subtipo':.99})
    monkeypatch.setattr(modulo, 'entrenar', entrenar)
    monkeypatch.setattr(modulo, 'evaluar', lambda modelo, datos: {
        'acierto_tarea':.99, 'f1_datos':.99, 'acierto_tipo':.99, 'acierto_subtipo':.99,
        'ejemplos':len(datos)})
    monkeypatch.setattr(modulo, 'modulo_torch', lambda: SimpleNamespace(
        save=lambda pesos, ruta: ruta.write_bytes(b'pesos-de-contrato-no-red-real')))
    registry = RegistroModelo(tmp_path/'registro')
    family = 'transformer' if solo == 'ordenes' else 'clasificador'
    pointer = registry.raiz/family/'current.json'
    pointer.parent.mkdir(parents=True)
    pointer.write_bytes(b'puntero-previo-intacto')
    monkeypatch.setattr(registry, 'promover', lambda *a: pytest.fail('No debe activar individualmente'))
    reopen = []
    def reabrir(carpeta):
        reopen.append(carpeta)
        saved = json.loads((carpeta/'readback.json').read_text(encoding='utf-8'))
        assert saved['textos'] == [partes['test'][0]['texto']]
        assert saved['predicciones']
        return {'ok':smoke_ok, 'proceso_nuevo':True}
    result = worker.entrenar_dataset(tmp_path/'dataset', tmp_path/'salida', solo=solo,
        semillas=(11,23), epocas=1, registro=registry, reabrir=reabrir)
    assert result['candidate_id'] and result['modelo_registro'] == family
    # Este fixture de una tarea no acredita el examen completo de órdenes.
    aprobado = solo == 'informes' and quality in {'gold_human','gold_native'} and smoke_ok
    assert result['gates']['approved'] is aprobado
    assert result['candidato_aprobado'] is aprobado and result['publicacion_pendiente'] is aprobado
    assert result['status'] == ('PROMOVIDO' if aprobado else 'RECHAZADO')
    assert result['promovido'] is False and len(reopen) == 1
    detail = registry.detalle(family, result['candidate_id'])
    if solo=='ordenes' and quality=='gold_native':
        assert detail['metrics']['reales'] is None, 'Un episodio eléctrico no es una orden humana'
    assert detail['smoke_reload']['ok'] is smoke_ok
    assert set(detail['artifacts']) == {'modelo.json', 'pesos.pt', 'readback.json'}
    assert pointer.read_bytes() == b'puntero-previo-intacto'


def test_dataset_no_aprueba_ordenes_solo_por_promedios():
    """050:RF-7 / 069:RF-17: también rigen cobertura, referencia y rechazo reservados."""
    from convertersmartgrid.asistente.entrenamiento_dataset import puertas_dataset
    metricas={'acierto_tarea':.99,'f1_datos':.99,'ejemplos':4}
    gates=puertas_dataset('ordenes',metricas,metricas,None,{'ok':True})
    assert gates['approved'] is False
    assert any('familia' in f or 'rechazo' in f for f in gates['fallos'])


def test_dataset_aprueba_puertas_comunes_solo_con_examen_completo():
    """050:RF-7: contrato de aprobación, sin afirmar medidas reales de ningún modelo."""
    from convertersmartgrid.asistente.entrenamiento_dataset import puertas_dataset
    from convertersmartgrid.asistente.tareas import TAREAS
    metricas={'acierto_tarea':.99,'f1_datos':.99,'ejemplos':4}
    familias={t:dict(metricas) for t in TAREAS}
    gates=puertas_dataset('ordenes',metricas,metricas,metricas,{'ok':True},
        familias=familias,referencia=familias,rechazo={'ejemplos':100,'rechazada':1.,'se_cuela':0.})
    assert gates['approved'] is True and not gates['fallos']


def test_runner_lenguaje_envia_registro_comun(tmp_path, monkeypatch):
    """050:RF-4: el ciclo puede resolver el candidato del trabajador en su propio registro."""
    from types import SimpleNamespace
    from tools import reentrenar_modelos as runner
    vistos=[]
    monkeypatch.setattr(runner, '_subproceso', lambda cmd, *a: vistos.append(cmd) or {})
    args=SimpleNamespace(dataset=tmp_path/'dataset', vocabulario=None, semillas='11',
                         registro=tmp_path/'registro')
    workers=runner._etapas(args,tmp_path/'corrida')
    next(e for e in workers if e.name == 'transformer').run()
    assert '--registro' in vistos[0]
    assert vistos[0][vistos[0].index('--registro')+1] == str(args.registro)
