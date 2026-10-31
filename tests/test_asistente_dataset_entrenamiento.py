"""043:RF-3 043:RF-4 — Regresiones del donante de reentrenamiento."""
import json


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
    from igea_dgs.asistente.dataset_entrenamiento import normalizar_orden

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


def test_native_gold_requires_accepted_converged_evidence():
    from igea_dgs.asistente.dataset_entrenamiento import normalizar_episodio

    accepted = normalizar_episodio(_episode())
    rejected = normalizar_episodio(_episode(accepted=False))

    assert accepted.quality == 'gold_native'
    assert accepted.verification == 'powerfactory_reopened'
    assert accepted.evidence_hashes == ('a' * 64,)
    assert rejected.quality == 'quarantine'


def test_native_sin_reapertura_no_es_gold():
    """043:RF-3 — una etiqueta de aceptación no inventa una reapertura ausente."""
    from igea_dgs.asistente.dataset_entrenamiento import normalizar_episodio
    fila = _episode()
    fila['nativo'].pop('reopen_verified')
    assert normalizar_episodio(fila).quality == 'quarantine'


def test_episodio_vigente_se_valida_con_su_contrato():
    """043:RF-3 — aceptar el formato real de 024 sin exigir campos legacy inventados."""
    from test_digital_twin_episode import _payload
    from igea_dgs.asistente.dataset_entrenamiento import normalizar_episodio
    payload = _payload()
    payload['topologia']['sets'] = ['SET1']
    assert normalizar_episodio(payload).quality == 'gold_native'


def test_partition_keeps_group_together_and_excludes_quarantine():
    from igea_dgs.asistente.dataset_entrenamiento import normalizar_orden, particionar_dataset

    repeated = [normalizar_orden({'texto': 'reentrena la pinn', 'tarea': 'gemelo_entrenar',
                                  'origen': 'confirmado'}) for _ in range(3)]
    invalid = normalizar_orden({'texto': 'haz algo', 'tarea': '', 'origen': 'inferido'})
    parts = particionar_dataset([*repeated, invalid])

    locations = {name for name, rows in parts.items() for row in rows
                 if row.texto == 'reentrena la pinn'}
    assert len(locations) == 1
    assert not any(row.quality == 'quarantine' for rows in parts.values() for row in rows)


def test_manifest_v2_has_hashes_quality_counts_and_no_leak(tmp_path):
    from igea_dgs.asistente.dataset_entrenamiento import (
        escribir_particiones, normalizar_orden, particionar_dataset)

    rows = [normalizar_orden({'texto': f'ordena {i}', 'tarea': 'convertir',
                              'origen': 'confirmado'}) for i in range(20)]
    manifest = escribir_particiones(particionar_dataset(rows), tmp_path)

    assert manifest['schema'] == 'igea-dgs-training-dataset-v2'
    assert manifest['sha256'] and manifest['audit']['valid']
    assert manifest['qualities']['gold_human'] == 20
    assert all((tmp_path / f'{name}.jsonl').is_file()
               for name in ('train', 'validation', 'test'))


def test_conversion_event_is_context_and_never_gold(tmp_path):
    from igea_dgs.asistente.dataset_entrenamiento import (
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
    from igea_dgs.asistente.dataset_entrenamiento import (
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
    from igea_dgs.asistente.dataset_entrenamiento import importar_normativa

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
    from igea_dgs.asistente.dataset_entrenamiento import descubrir_alimentadores_inventarios

    ruta = tmp_path / 'w' / 'runs' / 'r' / 'salida'
    ruta.mkdir(parents=True)
    feeders = [{'network_id': f'NET_2030_{i}_AA{i:03d}'} for i in range(101)]
    (ruta / 'dataset_inventory.json').write_text(
        json.dumps({'feeders': feeders}), encoding='utf-8')
    codigos = descubrir_alimentadores_inventarios(tmp_path)
    assert set(codigos) == {f['network_id'] for f in feeders}


def test_identidad_explicita_prevalece_sobre_nombre_de_red(tmp_path):
    """043:RF-2 043:RF-3 — pertenencia explícita y códigos universales, sin regex de empresa."""
    from igea_dgs.asistente.dataset_entrenamiento import descubrir_alimentadores_inventarios
    (tmp_path / 'dataset_inventory.json').write_text(json.dumps({'feeders': [
        {'network_id': 'NET_2030_1_AA001', 'feeder': 'Ramal rural/Sur'},
        {'network_id': 'Identificador-no-convencional'},
    ]}), encoding='utf-8')
    assert set(descubrir_alimentadores_inventarios(tmp_path)) == {
        'Ramal rural/Sur', 'Identificador-no-convencional'}
