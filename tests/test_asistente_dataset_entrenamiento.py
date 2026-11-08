"""043:RF-3 043:RF-4 — Regresiones del donante de reentrenamiento."""
import json


def test_informes_del_operador_entran_en_dataset_con_sus_etiquetas(tmp_path):
    """043:RF-3 / 050:RF-2: informes confirmados y maestro no tienen la misma calidad."""
    from convertersmartgrid.asistente.dataset_entrenamiento import construir_dataset
    assistant=tmp_path/'assistant';assistant.mkdir()
    filas=[{'texto':'Informe confirmado de refuerzo', 'tipo':'estudio','subtipo':'refuerzo',
            'origen':'corregido','fecha':'2026-11-07T10:00:00-05:00'},
           {'texto':'Informe anotado por maestro', 'tipo':'factibilidad','subtipo':'carga nueva','origen':'maestro'},
           {'texto':'Informe creado por software', 'tipo':'estudio','subtipo':'refuerzo','origen':'generado'}]
    source=assistant/'informes.jsonl'
    source.write_text(''.join(json.dumps(f)+'\n' for f in filas),encoding='utf-8')
    original=source.read_bytes()
    dataset=construir_dataset(assistant,tmp_path/'twin')
    assert len(dataset.registros)==3
    rows={r.texto:r for r in dataset.registros}
    humana=rows[filas[0]['texto']]
    assert humana.tipo=='informe' and humana.quality=='gold_human'
    assert humana.verification=='operator_corrected'
    assert humana.resultado=={'tipo_informe':'estudio','subtipo':'refuerzo'}
    assert rows[filas[1]['texto']].quality=='quarantine'
    assert rows[filas[2]['texto']].quality=='context'
    assert source.read_bytes()==original


def test_informe_invalido_no_se_hace_oro_y_textos_equivalentes_se_agrupan():
    """043:RF-4: corregir la etiqueta no separa copias del mismo informe entre particiones."""
    from convertersmartgrid.asistente.dataset_entrenamiento import normalizar_informe,particionar_dataset
    base={'texto':'Informe de red', 'tipo':'estudio','subtipo':'refuerzo','origen':'confirmado'}
    uno=normalizar_informe(base)
    otro=normalizar_informe({**base,'texto':'INFORME  DE RED','subtipo':'tensión'})
    assert uno.group_id==otro.group_id
    parts=particionar_dataset([uno,otro])
    assert len([k for k,v in parts.items() if v])==1
    assert normalizar_informe({**base,'tipo':'desconocido'}).quality=='quarantine'
    assert normalizar_informe({**base,'texto':' '}).quality=='quarantine'


def test_informes_con_etiquetas_humanas_contradictorias_se_conservan_en_cuarentena(tmp_path):
    """050:RF-9: no resolver por el orden del JSONL una contradicción de la prueba."""
    from convertersmartgrid.asistente.dataset_entrenamiento import construir_dataset
    root=tmp_path/'assistant';root.mkdir()
    filas=[{'texto':'Informe de red','tipo':'estudio','subtipo':s,'origen':'corregido'}
           for s in ['refuerzo','tensión']]
    (root/'informes.jsonl').write_text(''.join(json.dumps(f)+'\n' for f in filas),encoding='utf-8')
    built=construir_dataset(root,tmp_path/'twin')
    assert len(built.registros)==2
    assert all(r.quality=='quarantine' and 'contradictorias' in r.motivo for r in built.registros)


def test_revision_humana_del_informe_conserva_la_procedencia_del_maestro():
    """043:RF-3 / 050:RF-9: confirmar etiquetas no cambia quién las propuso."""
    from convertersmartgrid.asistente.dataset_entrenamiento import normalizar_informe
    revision={'id':'R1','revisor':'usuario','confirmed':True,'source_record_sha256':'a'*64,
              'source_file_sha256':'b'*64,'fecha':'2026-11-07T22:25:00-05:00'}
    record=normalizar_informe({'texto':'Informe revisado','tipo':'estudio','subtipo':'refuerzo',
        'origen':'confirmado','origen_inicial':'maestro','revision_humana':revision})
    assert record.quality=='gold_human' and record.verification=='operator_confirmed'
    assert record.provenance['origen_inicial']=='maestro'
    assert record.provenance['revision_humana']==revision


def test_auditoria_de_privacidad_no_confunde_encabezados_con_rutas(tmp_path):
    """043:RF-3: el escape JSON de un salto tras el encabezado no es una ruta."""
    from dataclasses import replace
    from convertersmartgrid.asistente.dataset_entrenamiento import (
        normalizar_informe,auditar_registro,construir_dataset)
    row={'texto':'CONCLUSIONES:\nLa red converge.\nASUNTO:\tRefuerzo',
         'tipo':'estudio','subtipo':'refuerzo','origen':'confirmado'}
    record=normalizar_informe(row)
    assert not auditar_registro(record)
    assert 'contiene ruta local' in auditar_registro(replace(record,texto=r'D:\privado\informe.docx'))
    root=tmp_path/'assistant';root.mkdir()
    (root/'informes.jsonl').write_text(json.dumps(row)+'\n',encoding='utf-8')
    assert len(construir_dataset(root,tmp_path/'twin').registros)==1


def _episode(*, accepted=True):
    return {
        'episode_id': 'e' * 64,
        'clase': 'accepted' if accepted else 'quarantine',
        'fuente': {'source_run_id': 'run-native', 'sha256': 'a' * 64},
        'nativo': {'project': 'P1', 'feeders': ['CA101'], 'pf_version': '2024',
                   'reopen_verified': accepted},
        'accion': {'tipo': 'flujo'},
        'topologia': {'sets': ['CHINCHA']},
        'flujo': {'convergio': accepted},
        'aceptacion': {'estado_nativo': 'aceptado' if accepted else 'rechazado',
                       'bloqueos': [] if accepted else ['no convergió']},
    }


def test_confirmed_order_is_human_gold_and_private_path_is_removed():
    from convertersmartgrid.asistente.dataset_entrenamiento import normalizar_orden

    record = normalizar_orden({
        'texto': r'convierte CA101 desde D:\empresa\fuente.txt',
        'tarea': 'convertir', 'datos': [['alimentadores', 'CA101']],
        'origen': 'confirmado', 'fecha': '2026-10-25T10:00:00-05:00',
    })

    assert record.quality == 'gold_human'
    assert record.alimentadores == ('CA101',)
    assert record.verification == 'operator_confirmed'
    assert 'D:\\empresa' not in json.dumps(record.as_dict())
    assert len(record.record_id) == 64 and len(record.group_id) == 64


def test_orden_historica_con_posiciones_se_traduce_sin_cambiar_la_etiqueta():
    """043:RF-3: almacen usa [inicio,fin,tipo], no [tipo,valor]."""
    from convertersmartgrid.asistente.dataset_entrenamiento import normalizar_orden
    texto='convierte CA101 con catálogo'
    inicio=texto.index('CA101')
    r=normalizar_orden({'texto':texto,'tarea':'convertir','origen':'confirmado',
                       'datos':[[inicio,inicio+5,'alimentadores']]})
    assert r.quality=='gold_human'
    assert r.datos == (('alimentadores','CA101'),)
    assert r.alimentadores==('CA101',)


def test_anotaciones_invalidas_no_desaparecen_como_ordenes_sin_entidades():
    """043:RF-3: no convertir un dato perdido en una etiqueta de ausencia."""
    from convertersmartgrid.asistente.dataset_entrenamiento import normalizar_orden
    base={'texto':'convierte CA101','tarea':'convertir','origen':'confirmado'}
    for datos in ([[0,999,'alimentadores']],[['desconocido','CA101']],
                  [['alimentadores','OTRA']],[[3]],[[True,8,'alimentadores']]):
        r=normalizar_orden({**base,'datos':datos})
        assert r.quality=='quarantine' and r.motivo


def test_native_gold_requires_accepted_converged_evidence():
    from convertersmartgrid.asistente.dataset_entrenamiento import normalizar_episodio

    accepted = normalizar_episodio(_episode())
    rejected = normalizar_episodio(_episode(accepted=False))

    assert accepted.quality == 'gold_native'
    assert accepted.verification == 'powerfactory_reopened'
    assert accepted.evidence_hashes == ('a' * 64,)
    assert rejected.quality == 'quarantine'


def test_native_sin_reapertura_no_es_gold():
    """043:RF-3 — una etiqueta de aceptación no inventa una reapertura ausente."""
    from convertersmartgrid.asistente.dataset_entrenamiento import normalizar_episodio
    fila = _episode()
    fila['nativo'].pop('reopen_verified')
    assert normalizar_episodio(fila).quality == 'quarantine'


def test_episodio_vigente_se_valida_con_su_contrato():
    """043:RF-3 — aceptar el formato real de 024 sin exigir campos legacy inventados."""
    from test_digital_twin_episode import _payload
    from convertersmartgrid.asistente.dataset_entrenamiento import normalizar_episodio
    payload = _payload()
    # Sin ``topologia.sets``: el sistema nunca lo escribe, y exigirlo mandaba a cuarentena los 66
    # episodios aceptados del buffer real (2026-11-02). Esta prueba lo añadía a mano y lo ocultaba.
    assert 'sets' not in payload['topologia']
    assert normalizar_episodio(payload).quality == 'gold_native'
    # Sin alimentadores no se puede agrupar para evitar fugas entre particiones.
    payload['nativo']['feeders'] = []
    assert normalizar_episodio(payload).quality == 'quarantine'


def test_partition_keeps_group_together_and_excludes_quarantine():
    from convertersmartgrid.asistente.dataset_entrenamiento import normalizar_orden, particionar_dataset

    repeated = [normalizar_orden({'texto': 'reentrena la pinn', 'tarea': 'gemelo_entrenar',
                                  'origen': 'confirmado'}) for _ in range(3)]
    invalid = normalizar_orden({'texto': 'haz algo', 'tarea': '', 'origen': 'inferido'})
    parts = particionar_dataset([*repeated, invalid])

    locations = {name for name, rows in parts.items() for row in rows
                 if row.texto == 'reentrena la pinn'}
    assert len(locations) == 1
    assert not any(row.quality == 'quarantine' for rows in parts.values() for row in rows)


def test_manifest_v2_has_hashes_quality_counts_and_no_leak(tmp_path):
    from convertersmartgrid.asistente.dataset_entrenamiento import (
        escribir_particiones, normalizar_orden, particionar_dataset)

    rows = [normalizar_orden({'texto': f'ordena {i}', 'tarea': 'convertir',
                              'origen': 'confirmado'}) for i in range(20)]
    manifest = escribir_particiones(particionar_dataset(rows), tmp_path)

    assert manifest['schema'] == 'convertersmartgrid-training-dataset-v2'
    assert manifest['sha256'] and manifest['audit']['valid']
    assert manifest['qualities']['gold_human'] == 20
    assert all((tmp_path / f'{name}.jsonl').is_file()
               for name in ('train', 'validation', 'test'))


def test_conversion_event_is_context_and_never_gold(tmp_path):
    from convertersmartgrid.asistente.dataset_entrenamiento import (
        normalizar_evento_conversion, registrar_evento_conversion)

    result = registrar_evento_conversion(
        outbox=tmp_path, source_run_id='run-1', source_mode='txt',
        source_fingerprint='f' * 64, todos_alimentadores=['CA101', 'CA104'],
        manifest={'feeders': [{'network_id': 'CA101', 'status': 'ok'}]})
    payload = json.loads((tmp_path / f"{result['event_id']}.json").read_text())
    records = normalizar_evento_conversion(payload)

    assert result['ok'] and len(records) == 2
    assert {r.quality for r in records} == {'context'}
    assert {r.alimentadores[0] for r in records} == {'CA101', 'CA104'}


def test_web_history_merges_same_source_without_contradicting_reload(tmp_path):
    from convertersmartgrid.asistente.dataset_entrenamiento import (
        construir_dataset, importar_historial_web)

    web = tmp_path / 'web'
    for index, feeder in enumerate(('CA101', 'CA104')):
        run = web / f'w{index}' / 'runs' / f'r{index}'
        (run / 'salida').mkdir(parents=True)
        (run / 'source_manifest.json').write_text(json.dumps({
            'mode': 'txt', 'fingerprint': 'a' * 64}), encoding='utf-8')
        (run / 'salida' / 'dataset_inventory.json').write_text(json.dumps({
            'feeders': [{'network_id': 'CA101'}, {'network_id': 'CA104'}]}), encoding='utf-8')
        (run / 'salida' / 'batch_manifest.json').write_text(json.dumps({
            'feeders': [{'network_id': feeder, 'status': 'ok'}]}), encoding='utf-8')

    assistant = tmp_path / 'assistant'
    report = importar_historial_web(web, assistant / 'conversion_outbox')
    built = construir_dataset(assistant, tmp_path / 'twin')

    assert report['sources'] == 1 and report['runs'] == 2
    assert {r.alimentadores[0]: r.resultado['convertido'] for r in built.registros} == {
        'CA101': True, 'CA104': True}


def test_normative_unknown_license_is_quarantined(tmp_path):
    from convertersmartgrid.asistente.dataset_entrenamiento import importar_normativa

    root = tmp_path / 'normativa'
    (root / 'textos').mkdir(parents=True)
    (root / 'textos' / 'n.txt').write_text('Límite de tensión.', encoding='utf-8')
    (root / 'manifest.json').write_text(json.dumps({'documentos': [{
        'id': 'n1', 'sha256': 'abc', 'texto': 'textos/n.txt',
        'url': 'https://example.test/norma', 'license': '',
    }]}), encoding='utf-8')

    records = importar_normativa(root)

    assert len(records) == 1 and records[0].quality == 'quarantine'
    assert 'licencia' in records[0].motivo


def test_descubre_ciento_un_alimentadores_sin_inferir_identidad_mdb(tmp_path):
    from convertersmartgrid.asistente.dataset_entrenamiento import descubrir_alimentadores_inventarios

    ruta = tmp_path / 'w' / 'runs' / 'r' / 'salida'
    ruta.mkdir(parents=True)
    feeders = [{'network_id': f'NET_2030_{i}_AA{i:03d}'} for i in range(101)]
    (ruta / 'dataset_inventory.json').write_text(
        json.dumps({'feeders': feeders}), encoding='utf-8')
    codigos = descubrir_alimentadores_inventarios(tmp_path)
    assert set(codigos) == {f['network_id'] for f in feeders}


def test_identidad_explicita_prevalece_sobre_nombre_de_red(tmp_path):
    """043:RF-2 043:RF-3 — pertenencia explícita y códigos universales, sin regex de empresa."""
    from convertersmartgrid.asistente.dataset_entrenamiento import descubrir_alimentadores_inventarios
    (tmp_path / 'dataset_inventory.json').write_text(json.dumps({'feeders': [
        {'network_id': 'NET_2030_1_AA001', 'feeder': 'Ramal rural/Sur'},
        {'network_id': 'Identificador-no-convencional'},
    ]}), encoding='utf-8')
    assert set(descubrir_alimentadores_inventarios(tmp_path)) == {
        'Ramal rural/Sur', 'Identificador-no-convencional'}


def test_episodios_de_un_alimentador_no_se_reparten_entre_particiones():
    """043:RF-4 — SM218, NA203, AL105 y CA101 caían en varias particiones (2026-11-02): se evaluaba
    con redes ya vistas al entrenar, y la auditoría no lo veía. Van juntos, y la auditoría lo vigila."""
    from dataclasses import replace

    from convertersmartgrid.asistente.calidad_datos import auditar_contaminacion
    from convertersmartgrid.asistente.dataset_entrenamiento import normalizar_episodio, particionar_dataset

    registros = []
    for i in range(40):
        fila = _episode()
        fila['episode_id'] = f'{i:064d}'
        fila['fuente']['source_run_id'] = f'run-{i}'
        fila['nativo']['feeders'] = ['SM218'] if i % 2 else ['SM218', f'OTRO{i}']
        fila['accion']['tipo'] = f'tarea{i}'
        registros.append(normalizar_episodio(fila))
    partes = particionar_dataset(registros)
    assert sorted(len(v) for v in partes.values()) == [0, 0, 40], 'todos comparten SM218'
    assert auditar_contaminacion(partes)['valid'] is True
    # Un reparto que los separa no se publica.
    a, b = registros[0], replace(registros[1], record_id='x')
    informe = auditar_contaminacion({'train': (a,), 'test': (b,)})
    assert informe['valid'] is False and 'SM218' in informe['feeder_leaks']
