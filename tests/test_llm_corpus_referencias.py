"""047:RF-19 / RF-20: particiones y prompts; no se sustituyen datos reales por fixtures."""
import pytest
import random


def test_particion_contexto_es_estable_y_no_mezcla_alimentadores():
    """047:RF-20: variantes del mismo contexto conservan su particion."""
    from igea_dgs.asistente import llm_destilacion as m
    assert callable(getattr(m,'parte_contexto',None))
    assert m.parte_contexto('fuente','contexto')==m.parte_contexto('fuente','contexto')


def test_objetivo_causal_no_incluye_tokens_del_prompt():
    """047:RF-19: aprender la respuesta no equivale a repetir la entrada."""
    from igea_dgs.asistente import llm_destilacion as m
    assert callable(getattr(m,'objetivo_causal',None))
    entrada,objetivo=m.objetivo_causal([1,2,3],[4,5],max_tokens=8)
    assert entrada==[1,2,3,4,5] and objetivo==[-100,-100,-100,4,5]
    with pytest.raises(ValueError,match='trunc'):
        m.objetivo_causal([1,2,3],[4,5],max_tokens=4)


def test_generador_real_no_usa_relleno_inventado():
    """047:RF-20: a diferencia del generador sintetico, no hay fallback aleatorio."""
    from igea_dgs.asistente import llm_destilacion as m
    assert callable(getattr(m,'renderizar_orden',None))
    for i in range(100):
        texto,datos=m.renderizar_orden('[convierte|exporta] {alimentadores}',
                                      {'alimentadores':'valor del contrato'},random.Random(i))
        a,b,tipo=datos[0]
        assert texto[a:b]=='valor del contrato' and tipo=='alimentadores'
    with pytest.raises(ValueError,match='valor real'):
        m.renderizar_orden('convierte {alimentadores}',{},random.Random(0))


def test_corpus_sin_contextos_reales_no_se_entrena():
    """047:RF-20: ausencia de registros observados es un error, no un corpus simulado."""
    from igea_dgs.asistente import llm_destilacion as m
    assert callable(getattr(m,'construir_corpus_real',None))
    with pytest.raises(ValueError,match='contextos reales'):
        m.construir_corpus_real([], {})


def test_reparto_conserva_pares_del_mismo_proyecto():
    """047:RF-20: estratificar el grafo de vinculos antes de mirar rendimiento."""
    from igea_dgs.asistente import llm_destilacion as m
    assert callable(getattr(m,'repartir_contextos',None))
    vinculos={str(i):['grupo del contrato'] for i in range(40)}
    partes,semilla=m.repartir_contextos('fuente del contrato',vinculos)
    assert len(partes)==40 and all(list(partes.values()).count(p)>=2 for p in m.PARTICIONES)
    assert (partes,semilla)==m.repartir_contextos('fuente del contrato',vinculos)


def test_lector_no_puede_abrir_otra_particion_con_archivo_renombrado(tmp_path):
    """047:RF-19: el entrenador debe leer solo el archivo de entrenamiento sellado."""
    from igea_dgs.asistente import llm_destilacion as m
    assert callable(getattr(m,'leer_particion_real',None))
    (tmp_path/'dataset_manifest.json').write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='particion'):
        m.leer_particion_real(tmp_path,'entrenamiento')


def test_ordenes_humanas_se_reservan_sin_inflar_repeticiones():
    """047:RF-11 / RF-19: las humanas independientes no pueden entrar en el ajuste."""
    from igea_dgs.asistente import llm_destilacion as m
    assert callable(getattr(m,'reservar_humanas',None))
    r={'texto':'carga la fuente','tarea':'cargar_fuente','datos':[],'origen':'confirmado'}
    assert len(m.reservar_humanas([r,r]))==1


def test_jsonl_regenerado_no_puede_heredar_identidad_del_sellado(tmp_path):
    """047:RF-19 / RF-20: renovar hash de archivo no autoriza cambiar sus registros."""
    import json
    from igea_dgs.asistente import llm_destilacion as m
    f=tmp_path/'fuente.txt';f.write_text('fuente de contrato',encoding='utf-8')
    r={'texto':'carga la fuente','tarea':'cargar_fuente','datos':[], 'particion':'entrenamiento',
       'fuentes':[m.custodiar(f,localizador='contrato')],'quality':'silver_teacher_real_source',
       'observacion_humana':False,'ejecutado':False}
    r['respuesta']=m.respuesta_maestro(r);r['record_id']=m.huella(r)
    p=tmp_path/'entrenamiento.jsonl';p.write_text(json.dumps(r)+'\n',encoding='utf-8')
    meta={'prompt_hash':m.huella(m.sistema_alumno()),'huellas_particion':{'entrenamiento':m.huella([r])},
          'archivos_particion':{'entrenamiento':{**m.custodiar(p,localizador='entrenamiento'),'registros':1}}}
    (tmp_path/'dataset_manifest.json').write_text(json.dumps(meta),encoding='utf-8')
    m.leer_particion_real(tmp_path,'entrenamiento')
    r.pop('record_id');r['texto']='solicitud cambiada';r['record_id']=m.huella(r)
    p.write_text(json.dumps(r)+'\n',encoding='utf-8')
    meta['archivos_particion']['entrenamiento']={**m.custodiar(p,localizador='entrenamiento'),'registros':1}
    (tmp_path/'dataset_manifest.json').write_text(json.dumps(meta),encoding='utf-8')
    with pytest.raises(ValueError,match='subconjunto'):
        m.leer_particion_real(tmp_path,'entrenamiento')


@pytest.fixture
def sellado_contrato(tmp_path):
    """Contrato minimo de cuatro particiones; no es evidencia de datos o pesos reales."""
    import json
    from igea_dgs.asistente import llm_destilacion as m
    origen=tmp_path/'origen';origen.mkdir()
    fuente=origen/'fuente.txt';fuente.write_text('registro de contrato',encoding='utf-8')
    filas=[];contextos=[]
    for parte in m.PARTICIONES:
        c={'network_id':parte,'source_fingerprint':'a'*64,'particion':parte,
           'alimentador':parte,'proyectos':[],'sistema':None,'seds':[],'ruta':str(fuente),'periodos':[]}
        contextos.append(c)
        r={'texto':'carga la fuente '+parte,'tarea':'cargar_fuente','datos':[], 'particion':parte,
           'group_id':m.huella(['grupo',parte]),'context_id':m.huella(['a'*64,parte]),
           'fuentes':[m.custodiar(fuente,localizador='contrato')], 'quality':'silver_teacher_real_source',
           'observacion_humana':False,'ejecutado':False}
        r['respuesta']=m.respuesta_maestro(r);r['record_id']=m.huella(r);filas.append(r)
    meta={'schema_version':2,'dataset_hash':m.huella(filas),'por_particion':{p:1 for p in m.PARTICIONES}}
    for nombre,dato in (('corpus.json',filas),('dataset_manifest.json',meta),('contextos.json',contextos),
                        ('humanas_reservadas.json',[{'texto':'humana reservada del contrato'}])):
        (origen/nombre).write_text(json.dumps(dato),encoding='utf-8')
    destino=tmp_path/'sellado';m.sellar_particiones(origen,destino)
    assert m.auditar_fuentes_corpus(destino)['ok']
    return destino


@pytest.mark.parametrize('texto, error',[('otra solicitud','corpus auditado'),
                                        ('humana reservada del contrato','humana reservada')])
def test_regeneracion_parcial_no_elude_corpus_ni_reserva_humana(sellado_contrato,texto,error):
    """047:RF-19 / RF-20: todos los hashes JSONL renovados no cambian el corpus global aprobado."""
    import json
    from igea_dgs.asistente import llm_destilacion as m
    destino=sellado_contrato;p=destino/'entrenamiento.jsonl'
    r=json.loads(p.read_text(encoding='utf-8'));r.pop('record_id');r['texto']=texto;r['record_id']=m.huella(r)
    p.write_text(json.dumps(r)+'\n',encoding='utf-8')
    meta=json.loads((destino/'dataset_manifest.json').read_text(encoding='utf-8'))
    meta['archivos_particion']['entrenamiento']={**m.custodiar(p,localizador='entrenamiento'),'registros':1}
    meta['huellas_particion']['entrenamiento']=m.huella([r])
    (destino/'dataset_manifest.json').write_text(json.dumps(meta),encoding='utf-8')
    with pytest.raises(ValueError,match=error):
        m.auditar_fuentes_corpus(destino)
