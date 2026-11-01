"""047:RF-19 / RF-20: contratos de destilacion; las fixtures no son datos de aceptacion."""
import json
import pytest


def test_maestro_no_inventa_resultados_electricos():
    """047:RF-20: una anotacion de intencion no puede declarar una ejecucion nativa."""
    from convertersmartgrid.asistente import llm_destilacion as m
    r={'texto':'carga la fuente','tarea':'cargar_fuente','datos':[], 'fuentes':[],
       'resultado_electrico':{'convergio':True}}
    with pytest.raises(ValueError,match='resultado electrico'):
        m.respuesta_maestro(r)


def test_datos_reales_exigen_huella_y_archivo(tmp_path):
    """047:RF-20: falla ante evidencia cambiada, ausente o sin custodia."""
    from convertersmartgrid.asistente import llm_destilacion as m
    f=tmp_path/'entrada.txt'; f.write_text('registro de contrato',encoding='utf-8')
    evidencia=m.custodiar(f,localizador='archivo completo')
    assert m.verificar_fuente(evidencia)
    f.write_text('modificado',encoding='utf-8')
    with pytest.raises(ValueError,match='huella'):
        m.verificar_fuente(evidencia)


def test_respuesta_solo_admite_entidades_literales_y_fuentes(tmp_path):
    """047:RF-11 / RF-20: copiar spans no permite inventar datos adicionales."""
    from convertersmartgrid.asistente import llm_destilacion as m
    f=tmp_path/'evidencia.txt';f.write_text('dato de contrato',encoding='utf-8')
    r={'texto':'carga la fuente','tarea':'cargar_fuente','datos':[],
       'fuentes':[m.custodiar(f,localizador='archivo completo')]}
    assert json.loads(m.respuesta_maestro(r))['tarea']=='cargar_fuente'
    r['fuentes']=[]
    with pytest.raises(ValueError,match='fuente'):
        m.respuesta_maestro(r)


def test_cli_conserva_destino_existente(tmp_path,capsys):
    """047:RF-14 / RF-20: rechazar una carpeta previa no debe escribir dentro de ella."""
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('llm_cli',Path(__file__).parents[1]/'tools/llm_destilar.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    antes=list(tmp_path.iterdir())
    args=['preparar','--destino',str(tmp_path),'--workspace','no_existe']
    for n in ('red','cargas','equipos','estructura-pdf','mediciones','nuevos-clientes'):
        args+=['--'+n,'no_existe']
    assert m.main(args)==2
    assert list(tmp_path.iterdir())==antes


def test_config_exportada_conserva_arquitectura_y_retira_nf4():
    """047:RF-19: no anunciar pesos fusionados FP16 como otra base NF4."""
    from convertersmartgrid.asistente import llm_destilacion as m
    assert callable(getattr(m,'config_exportacion',None))
    original={'model_type':'qwen3','hidden_size':12,'quantization_config':{'load_in_4bit':True}}
    salida=m.config_exportacion(original)
    assert salida['model_type']=='qwen3' and salida['hidden_size']==12
    assert 'quantization_config' not in salida and salida['torch_dtype']=='float16'
    assert 'quantization_config' in original


def test_checkpoint_no_se_elige_con_prueba():
    """047:RF-19: seleccionar con los resultados finales produce fuga."""
    from convertersmartgrid.asistente import llm_destilacion as m
    assert callable(getattr(m,'elegir_version_llm',None))
    with pytest.raises(ValueError,match='seleccion'):
        m.elegir_version_llm([{'particion':'prueba'}])


def test_cli_ayuda_no_necesita_pesos_ni_fuente():
    """047:RF-14 / RF-19: consultar opciones no inicia entrenamiento ni importa Torch."""
    import subprocess
    import sys
    from pathlib import Path
    p=Path(__file__).parents[1]/'tools/llm_destilar.py'
    r=subprocess.run([sys.executable,'-X','utf8',str(p),'--help'],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==0 and 'entrenar-epoca' in r.stdout and not r.stderr


def test_no_salta_la_epoca_previa_incompleta():
    """047:RF-19: reanudar no puede omitir datos pendientes de la epoca previa."""
    from convertersmartgrid.asistente import llm_destilacion as m
    cfg={'dataset_hash':'contrato'};base={'id':'base-del-contrato','revision':'primera'}
    estado={'configuracion':cfg,'base':base,'epoca':1,'training_completed':False}
    with pytest.raises(ValueError,match='previa incompleta'):
        m.validar_reanudacion(estado,cfg,2,base)
    m.validar_reanudacion(estado,cfg,1,base)
    m.validar_reanudacion({**estado,'training_completed':True},cfg,2,base)


def test_cambio_de_revision_base_rechaza_reanudar_y_exportar():
    """047:RF-19: la misma arquitectura con otra base no es el alumno entrenado."""
    from convertersmartgrid.asistente import llm_runtime as m
    base={'id':'base-del-contrato','revision':'primera','files':[{'path':'tokenizer.json','sha256':'a'*64}]}
    m.validar_base_checkpoint({'base':base},base)
    for actual in ({**base,'revision':'segunda'},{**base,'files':[{'path':'tokenizer.json','sha256':'b'*64}]}):
        with pytest.raises(ValueError,match='base'):
            m.validar_base_checkpoint({'base':base},actual)
