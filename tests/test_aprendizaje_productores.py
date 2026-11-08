"""050:RF-1/2/3/4/8: productores conectados, sin entrenar ni abrir motores nativos."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from convertersmartgrid import aprendizaje_continuo as ac
from convertersmartgrid.asistente.dataset_entrenamiento import (
    escribir_particiones, normalizar_orden,
)


def _hash(valor):
    return hashlib.sha256(json.dumps(valor, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _captura(tmp_path):
    fuente = tmp_path / 'ordenes_originales.jsonl'
    fuente.write_text('{"orden":"convertir"}\n', encoding='utf-8')
    sha = hashlib.sha256(fuente.read_bytes()).hexdigest()
    contexto = ac.crear_contexto_documental({'ordenes_confirmadas': sha})
    fila = normalizar_orden({'texto': 'convierte la red', 'tarea': 'convertir',
        'datos': [], 'origen': 'confirmado', 'fecha': '2026-11-08T10:00:00-05:00'})
    dataset = tmp_path / 'dataset'
    escribir_particiones({'train': (fila,), 'validation': (), 'test': ()}, dataset)
    referencia = {'contexto': contexto['contexto_hash'], 'fuente_hash': sha,
        'registro_id': 'orden_original_1', 'instante': '2026-11-08T10:00:00-05:00',
        'contenido_hash': _hash(asdict(fila))}
    procedencia = tmp_path / 'procedencia.json'
    procedencia.write_text(json.dumps({'schema': ac.ESQUEMA_PROCEDENCIA,
        'referencias': {'dataset': {fila.record_id: referencia}}}), encoding='utf-8')
    inst = ac.congelar_instantanea({'dataset': dataset, 'procedencia': procedencia,
        'ordenes_fuente': fuente}, tmp_path / 'aprendizaje', contexto=contexto,
        versiones={'codigo': 'prueba'})
    return inst, fila, referencia


def test_contexto_documental_se_conserva_sin_proyecto_fisico(tmp_path):
    """050:RF-1/3 — el corpus tiene identidad, sin inventar un proyecto nativo 043."""
    inst, _, _ = _captura(tmp_path)
    leida = ac.verificar_instantanea(inst['ruta'])
    assert leida['contextos'] == {}
    assert leida['contextos_documentales'] == {'documental': inst['contexto_hash']}
    assert leida['contexto_documental']['schema'] == ac.ESQUEMA_CONTEXTO_DOCUMENTAL
    leida['contexto_documental']['corpus']['ordenes_confirmadas'] = 'f' * 64
    ruta = Path(inst['ruta']) / 'manifiesto.json'
    ruta.write_text(json.dumps({k: v for k, v in leida.items()
        if k not in ('ruta', 'verificada')}), encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado, match='documental'):
        ac.verificar_instantanea(inst['ruta'])


def test_productor_dataset_conserva_partes_y_observacion_entre_familias(tmp_path):
    """050:RF-2 — el productor lee el dataset real; una segunda representación conserva identidad."""
    inst, fila, referencia = _captura(tmp_path)
    resultado = ac.preparar_fuentes(inst, ['transformer'])
    uno = resultado['vistas']['transformer']['entrenamiento'][0]
    otro = ac.muestra_de_registro(inst, {'dataset': {fila.record_id: referencia}},
        'dataset', fila.record_id, asdict(fila), familia='clasificador',
        particion='entrenamiento', origen='observado', etiqueta='operador')
    assert uno.observacion_id == otro.observacion_id == ac.crear_observacion_id(
        referencia['contexto'], referencia['fuente_hash'], referencia['registro_id'], referencia['instante'])
    assert uno.record_id == fila.record_id and uno.etiqueta == 'operador'
    assert resultado['resumen'] == {'transformer': {'entrenamiento': 1}}
    assert resultado['cuarentena'] == []


def test_productor_rechaza_referencia_que_no_corresponde_al_contenido(tmp_path):
    """050:RF-2/8 — copiar referencias a otros registros no acredita su procedencia."""
    inst, fila, referencia = _captura(tmp_path)
    referencias = {'dataset': {fila.record_id: {**referencia, 'contenido_hash': '0' * 64}}}
    with pytest.raises(ac.CicloBloqueado, match='contenido'):
        ac.muestra_de_registro(inst, referencias, 'dataset', fila.record_id,
            asdict(fila), familia='transformer', particion='entrenamiento',
            origen='observado', etiqueta='operador')


def test_contexto_documental_no_admite_etiqueta_fisica(tmp_path):
    """050:RF-3 — un manifiesto documental no acredita contexto eléctrico nativo."""
    inst, fila, referencia = _captura(tmp_path)
    with pytest.raises(ac.CicloBloqueado, match='físico'):
        ac.muestra_de_registro(inst, {'dataset': {fila.record_id: referencia}},
            'dataset', fila.record_id, asdict(fila), familia='pinn',
            particion='entrenamiento', origen='simulado_nativo', etiqueta='motor_nativo')


def test_productor_ausente_bloquea_antes_de_construir_etapas(tmp_path):
    """050:RF-8 — no construir trabajadores con vistas omitidas o sin productor."""
    inst, _, _ = _captura(tmp_path)
    with pytest.raises(ac.CicloBloqueado, match='evolutivos'):
        ac.preparar_fuentes(inst, ['evolutivos'])
    spec = importlib.util.spec_from_file_location('p19_cli',
        Path(__file__).resolve().parents[1] / 'tools' / 'aprendizaje_continuo.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    with pytest.raises(ac.CicloBloqueado, match='evolutivos'):
        cli._etapas(inst, ['evolutivos'], SimpleNamespace(), tmp_path / 'etapas')


def test_productor_buffer_lee_objetos_sin_tocar_indice_y_respeta_partes(tmp_path):
    """050:RF-2/3 — episodios validados, identidad fuente y particiones del oráculo, sin entrenar."""
    from test_digital_twin_episode import _payload
    from test_gemelo_contratos_v2 import _grafo
    from convertersmartgrid.digital_twin.buffer import BuferEpisodios, muestras_aprendizaje
    from convertersmartgrid.digital_twin.episode import leer_episodio, episodio_a_dict

    fuente = tmp_path / 'fuente.txt'
    fuente.write_text('fuente nativa custodiada', encoding='utf-8')
    sha = hashlib.sha256(fuente.read_bytes()).hexdigest()
    payload = _payload(topologia={'grafo': _grafo()})
    payload['fuente']['source_fingerprint'] = sha
    episodio = leer_episodio(payload)
    bufer = BuferEpisodios(tmp_path / 'twin')
    bufer.guardar(episodio)
    vista = tmp_path / 'vista_twin'
    shutil.copytree(bufer.raiz / 'objetos', vista / 'objetos')
    ctx = 'a' * 64
    inst = ac.congelar_instantanea({'twin': vista, 'fuente': fuente},
        tmp_path / 'ac', contexto=ac.crear_contexto_ciclo({'P': ctx}), versiones={'codigo': 'x'})
    referencia = {'contexto': ctx, 'fuente_hash': sha, 'registro_id': episodio.episode_id,
        'instante': episodio.creado, 'contenido_hash': _hash(episodio_a_dict(episodio))}
    antes = ac.huellas_de(ac.ruta_de(inst, 'twin'))
    muestras = muestras_aprendizaje(inst, {'twin': {episodio.episode_id: referencia}})
    assert len(muestras) == 1 and muestras[0].familia == 'pinn'
    assert muestras[0].etiqueta == 'motor_nativo'
    assert muestras[0].particion in ('entrenamiento', 'seleccion', 'calibracion', 'prueba')
    assert ac.huellas_de(ac.ruta_de(inst, 'twin')) == antes
    assert ac.verificar_instantanea(inst['ruta'])['verificada']
    with pytest.raises(ac.CicloBloqueado, match='observación fuente'):
        muestras_aprendizaje(inst, {'twin': {episodio.episode_id: {
            **referencia, 'registro_id': 'otro-episodio'}}})


def test_productor_temporal_conserva_las_ventanas_reales_sin_gpu(tmp_path):
    """050:RF-2/3 — partición por día y referencias por ventana que consumirá la GRU."""
    from datetime import datetime, timedelta, timezone
    from convertersmartgrid.digital_twin.pronostico import Objetivo, construir_conjunto
    from convertersmartgrid.digital_twin.evaluacion_temporal import POLITICA_TEMPORAL
    from convertersmartgrid.digital_twin.temporal_entrenamiento import muestras_de_ventanas

    fuente = tmp_path / 'medida.csv'
    fuente.write_text('medidas de contrato', encoding='utf-8')
    sha = hashlib.sha256(fuente.read_bytes()).hexdigest()
    inicio = datetime(2026, 1, 1, tzinfo=timezone.utc)
    curva = [(inicio + timedelta(hours=i), 100. + i % 24) for i in range(84 * 24)]
    objetivo = Objetivo('cabecera', 'A1', 'kW', 'kW', curva)
    conjunto = construir_conjunto([objetivo], cadencia_min=60, zona_horaria='UTC')
    ventanas = conjunto.ventanas_comunes(POLITICA_TEMPORAL, contexto_pasos=168,
        horizonte_max=24, paso=1)
    inst = ac.congelar_instantanea({'cabeceras': fuente}, tmp_path / 'ac',
        contexto=ac.crear_contexto_ciclo({'P': 'a' * 64}), versiones={'codigo': 'x'})
    referencias = {}
    for parte, objetivos in ventanas['partes'].items():
        for nombre, emisiones in objetivos.items():
            for emision in emisiones:
                instante = conjunto.instantes[int(emision)].isoformat()
                registro = f'{nombre}|{instante}'
                contenido = {'objetivo': nombre, 'instante': instante,
                    'contexto': conjunto.valores[nombre][emision - 167:emision + 1].tolist(),
                    'objetivos': conjunto.valores[nombre][emision + 1:emision + 25].tolist()}
                referencias[registro] = {'contexto': 'a' * 64, 'fuente_hash': sha,
                    'registro_id': registro, 'instante': instante, 'contenido_hash': _hash(contenido)}
    muestras = muestras_de_ventanas(inst, {'cabeceras': referencias}, conjunto,
        ventanas, contexto_pasos=168, horizonte_max=24)
    assert len(muestras) == sum(len(ms) for p in ventanas['partes'].values() for ms in p.values())
    preparadas = ac.preparar_vistas(inst, muestras)
    assert set(preparadas['vistas']['gru']) == {'entrenamiento', 'seleccion', 'calibracion', 'prueba'}
    assert not preparadas['cuarentena']


def test_productor_generativo_no_convierte_maestro_en_humano(tmp_path):
    """050:RF-2/3/8 — el lector sellado rechaza el corpus incompleto antes de entrenar."""
    from convertersmartgrid.asistente.llm_destilacion import muestras_aprendizaje
    corpus = tmp_path / 'corpus'
    corpus.mkdir()
    (corpus / 'dataset_manifest.json').write_text('{}', encoding='utf-8')
    inst = ac.congelar_instantanea({'llm_dataset': corpus}, tmp_path / 'ac',
        contexto=ac.crear_contexto_documental({'corpus': hashlib.sha256(
            (corpus / 'dataset_manifest.json').read_bytes()).hexdigest()}), versiones={'codigo': 'x'})
    with pytest.raises(ValueError, match='particion'):
        muestras_aprendizaje(inst, {})


def test_embeddings_emite_consultas_consumidas_con_reserva_independiente(tmp_path):
    """050:RF-2/3/6 — el productor usa consultas reales del lector compartido y sus partes."""
    from dataclasses import replace
    from convertersmartgrid.asistente.dataset_entrenamiento import muestras_aprendizaje
    inst, fila, _ = _captura(tmp_path)
    fragmento = replace(fila, record_id='contexto1', group_id='grupo_contexto1',
        tipo='artefacto_contexto', quality='context',
        texto='La fuente del estudio se conserva con una huella verificable.')
    dataset = tmp_path / 'retrieval'
    escribir_particiones({'train': (fragmento,), 'validation': (), 'test': ()}, dataset)
    train = {'pregunta': '¿Cómo se conserva la fuente?',
        'fuente': 'documento_local#contexto1', 'confirmada': True,
        'verification': 'extractive_deterministic', 'independent_evaluation': False}
    test = {'pregunta': '¿Qué evidencia identifica la fuente del estudio?',
        'fuente': 'documento_local#contexto1', 'confirmada': True,
        'verification': 'operator_confirmed', 'independent_evaluation': True}
    for nombre, registro in [('retrieval_train', train), ('retrieval_test', test)]:
        (dataset / f'{nombre}.jsonl').write_text(json.dumps(registro) + '\n', encoding='utf-8')
    contexto = ac.crear_contexto_documental({'corpus': hashlib.sha256(
        (dataset / 'manifest.json').read_bytes()).hexdigest()})
    nueva = ac.congelar_instantanea({'dataset': dataset}, tmp_path / 'retrieval_ac',
        contexto=contexto, versiones={'codigo': 'x'})
    refs = {}
    for nombre, r in [('retrieval_train', train), ('retrieval_test', test)]:
        refs[f'{nombre}:{_hash(r)}'] = {'contexto': contexto['contexto_hash'],
            'fuente_hash': hashlib.sha256((dataset / f'{nombre}.jsonl').read_bytes()).hexdigest(),
            'registro_id': nombre + ':1', 'instante': '2026-11-08T00:00:00Z',
            'contenido_hash': _hash(r)}
    muestras = muestras_aprendizaje(nueva, {'dataset': refs}, ['embeddings'])
    assert [(m.particion, m.origen, m.etiqueta) for m in muestras] == [
        ('entrenamiento', 'redactado', 'maestro'), ('prueba', 'observado', 'operador')]


def test_preflight_informa_todas_las_familias_sin_ocultar_faltantes(tmp_path):
    """050:RF-8/10 — cada familia expone su bloqueo; ninguna falta se interpreta como preparada."""
    inst, _, _ = _captura(tmp_path)
    r = ac.preflight_ciclo(inst, ['transformer', 'clasificador', 'gru', 'pinn', 'embeddings', 'qlora', 'evolutivos'])
    assert r['estado'] == 'bloqueado'
    assert r['por_familia']['transformer']['estado'] == 'preparado'
    assert len(r['por_familia']) == 7
    assert all(r['por_familia'][f]['motivos'] for f in r['por_familia'] if f != 'transformer')
    assert not list((tmp_path / 'aprendizaje').glob('ciclos/*/ciclo.json'))


def test_evolutivos_consume_caso_con_contexto_043_declarado(tmp_path):
    """050:RF-2/3/8, 048:RF-1 — el problema usa el episodio congelado; no anuncia aceptación nativa."""
    from test_digital_twin_episode import _payload
    from test_gemelo_contratos_v2 import _grafo
    from convertersmartgrid.digital_twin.buffer import BuferEpisodios
    from convertersmartgrid.digital_twin.episode import leer_episodio
    from convertersmartgrid.digital_twin.evolutivo import casos_aprendizaje
    from convertersmartgrid.digital_twin.problema_optimizacion import evaluar_vector
    from convertersmartgrid.experimentos import ContextoExperimento, clave_contexto

    fuente = tmp_path / 'fuente.txt'
    fuente.write_text('fuente del grafo de contrato', encoding='utf-8')
    sha = hashlib.sha256(fuente.read_bytes()).hexdigest()
    p = _payload(topologia={'grafo': _grafo()})
    p['fuente']['source_fingerprint'] = sha
    episodio = leer_episodio(p)
    bufer = BuferEpisodios(tmp_path / 'twin')
    bufer.guardar(episodio)
    vista = tmp_path / 'vista_twin'
    shutil.copytree(bufer.raiz / 'objetos', vista / 'objetos')
    contexto = ContextoExperimento('run-1', 'txt', sha, 'P', ('A1', 'A2'),
        'IntCase:Estudios\\sin_proyecto', 'sin_proyecto', None, 'no_aplica', 'no_aplica',
        'a' * 64, 'a' * 64, 'a' * 64, 'a' * 64)
    ctx = clave_contexto(contexto)
    caso = {'record_id': 'caso_maniobra1', 'episode_id': episodio.episode_id,
        'contexto_043': asdict(contexto), 'problema': 'maniobras', 'particion': 'entrenamiento',
        'parametros': {'maniobras': ['L1'], 'tension_min_pu': .9, 'tension_max_pu': 1.1},
        'normalizacion': {'perdidas_kw': [0, 100]}}
    casos = tmp_path / 'casos.json'
    casos.write_text(json.dumps({'schema': 'convertersmartgrid-optimization-learning-cases-v1',
        'casos': [caso]}), encoding='utf-8')
    ref = {'contexto': ctx, 'fuente_hash': sha, 'registro_id': episodio.episode_id,
        'instante': episodio.creado, 'contenido_hash': _hash(caso)}
    procedencia = tmp_path / 'procedencia.json'
    procedencia.write_text(json.dumps({'schema': ac.ESQUEMA_PROCEDENCIA,
        'referencias': {'evolutivos_casos': {'caso_maniobra1': ref}}}), encoding='utf-8')
    inst = ac.congelar_instantanea({'twin': vista, 'fuente': fuente,
        'evolutivos_casos': casos, 'procedencia': procedencia}, tmp_path / 'ac',
        contexto=ac.crear_contexto_ciclo({'P': ctx}), versiones={'codigo': 'contrato'})
    preparados = casos_aprendizaje(inst)
    problema = preparados[0]['problema']
    assert problema.contexto == contexto
    assert problema.modelo_id == 'flujo_mallado:contrato'
    assert preparados[0]['muestra'].etiqueta == 'motor_nativo'
    assert ac.preparar_fuentes(inst, ['evolutivos'])['resumen'] == {'evolutivos': {'entrenamiento': 1}}
    evaluacion = evaluar_vector(problema, {'L1': 1})
    assert evaluacion['convergio'] is True and 'perdidas_kw' in evaluacion['objetivos']
    assert ac.verificar_instantanea(inst['ruta'])['verificada']
    spec = importlib.util.spec_from_file_location('evolutivos_ciclo_p19',
        Path(__file__).resolve().parents[1] / 'tools' / 'evaluar_evolutivos.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    reporte, registro = tmp_path / 'evaluacion.json', tmp_path / 'registro'
    assert cli.main(['--instantanea', inst['ruta'], '--seeds', '30', '--presupuesto', '1',
        '--registro', str(registro), '--report', str(reporte)]) == 0
    resultado = json.loads(reporte.read_text(encoding='utf-8'))
    assert resultado['status'] == 'RECHAZADO' and resultado['evaluation_completed'] is True
    assert resultado['training_completed'] is False and resultado['promovido'] is False
    from convertersmartgrid.model_registry import RegistroModelo
    reg = RegistroModelo(registro)
    assert reg.detalle('evolutivos', resultado['candidate_id'])['decision']['status'] == 'RECHAZADO'
    assert reg.activo('evolutivos') is None


def test_contexto_documental_exige_custodia_del_digest_declarado(tmp_path):
    """050:RF-1/8 — declarar un hexadecimal ajeno al corpus no acredita su identidad."""
    fuente = tmp_path / 'texto.txt'
    fuente.write_text('corpus real', encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado, match='documental.*custodia'):
        ac.congelar_instantanea({'texto': fuente}, tmp_path / 'ac',
            contexto=ac.crear_contexto_documental({'corpus': 'a' * 64}), versiones={'codigo': 'x'})


def test_procedencia_malformada_deja_bloqueo_controlado(tmp_path):
    """050:RF-8 — listas o tipos ajenos en referencias no saltan el diagnóstico del ciclo."""
    inst, fila, _ = _captura(tmp_path)
    with pytest.raises(ac.CicloBloqueado, match='referencia'):
        ac.muestra_de_registro(inst, {'dataset': []}, 'dataset', fila.record_id,
            asdict(fila), familia='transformer', particion='entrenamiento',
            origen='observado', etiqueta='operador')


def test_congelar_rechaza_raiz_twin_viva_antes_de_copiar_pesos_o_sqlite(tmp_path):
    """050:RF-1/8 — pedir una vista de datos, sin copiar pesos ni SQLite/WAL en caliente."""
    from test_aprendizaje_continuo import _fuentes, CTX, VERSIONES
    fuentes = _fuentes(tmp_path)
    twin = fuentes['twin']
    (twin / 'modelos').mkdir()
    (twin / 'modelos' / 'fixture.pt').write_bytes(b'fixture, no pesos reales')
    (twin / 'episodios.sqlite3').write_bytes(b'base viva de contrato')
    (twin / 'episodios.sqlite3-wal').write_bytes(b'wal de contrato')
    antes = ac.huellas_de(twin)
    with pytest.raises(ac.CicloBloqueado, match='vista.*objetos'):
        ac.congelar_instantanea(fuentes, tmp_path / 'ac', contexto=CTX, versiones=VERSIONES)
    assert ac.huellas_de(twin) == antes
    assert not (tmp_path / 'ac' / 'instantaneas').exists()
    assert not list((tmp_path / 'ac').rglob('*.pt'))


def test_copia_de_trabajo_rechaza_snapshot_legacy_con_modelos_sin_duplicarlos(tmp_path):
    """050:RF-1/8 — un snapshot antiguo se puede verificar, pero no duplicar pesos para otro ciclo."""
    from tools.reentrenar_modelos import _twin_de_trabajo
    origen = tmp_path / 'twin_legacy'
    (origen / 'objetos').mkdir(parents=True)
    (origen / 'objetos' / 'episodio.json').write_text('{}', encoding='utf-8')
    (origen / 'modelos').mkdir()
    (origen / 'modelos' / 'fixture.pt').write_bytes(b'fixture, no pesos reales')
    with pytest.raises(ac.CicloBloqueado, match='vista.*objetos'):
        _twin_de_trabajo(origen, tmp_path / 'trabajo')
    assert not (tmp_path / 'trabajo').exists()


def test_verificar_snapshot_v1_previo_no_reinterpreta_sus_archivos(tmp_path):
    """050:RF-1 — conserva lectura e identidad de capturas previas aunque hoy no se duplique su raíz."""
    raiz = tmp_path / 'legacy'
    archivos = {'twin': {'objetos/ep.json': hashlib.sha256(b'{}').hexdigest(),
                         'modelos/fixture.pt': hashlib.sha256(b'fixture').hexdigest()}}
    identidad = {'schema': ac.ESQUEMA_INSTANTANEA, 'contexto_hash': 'a' * 64,
                 'versiones': {'codigo': 'legacy'}, 'archivos': archivos}
    sid = _hash(identidad)
    carpeta = raiz / sid
    for rel, contenido in [('objetos/ep.json', b'{}'), ('modelos/fixture.pt', b'fixture')]:
        f = carpeta / 'datos' / 'twin' / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(contenido)
    (carpeta / 'manifiesto.json').write_text(json.dumps({**identidad, 'snapshot_id': sid,
        'tipos': {'twin': 'carpeta'}}), encoding='utf-8')
    assert ac.verificar_instantanea(carpeta)['snapshot_id'] == sid


def test_referencia_pinn_ausente_no_se_convierte_en_mejora(tmp_path):
    """050:RF-6/7/8 — primer candidato posible, pero un previo individual no se pierde por usar vista."""
    from test_aprendizaje_continuo import _instantanea, _candidato
    from convertersmartgrid.model_registry import RegistroModelo
    inst = _instantanea(tmp_path)
    reg = RegistroModelo(tmp_path / 'registro')
    primera = ac.referencia_pinn_ciclo(inst, registro=reg)
    assert primera['estado'] == 'sin_modelo_previo' and primera['retencion_acreditada'] is False
    cid = _candidato(reg, 'pinn')
    reg.promover('pinn', cid)
    with pytest.raises(ac.CicloBloqueado, match='individual previo'):
        ac.referencia_pinn_ciclo(inst, registro=reg)


def test_referencia_pinn_declarada_exige_conjunto_e_identidad_exactos(tmp_path):
    """050:RF-6/7/8 — una referencia sellada ausente o distinta bloquea, sin modelo inicial implícito."""
    from test_aprendizaje_continuo import _ciclo_terminado, CTX
    from convertersmartgrid.model_registry import RegistroModelo
    reg = RegistroModelo(tmp_path / 'registro')
    ciclo = _ciclo_terminado(tmp_path, reg)
    publicado = ac.publicar_conjunto(tmp_path / 'aprendizaje', reg, ciclo,
        retencion={f: {'retiene': True} for f in ('pinn', 'transformer')},
        conjunta={'aprobado': True}, obligatorias=['pinn', 'transformer'])
    conjunto = publicado['conjunto']
    referencia = {'schema': 'convertersmartgrid-pinn-reference-v1',
        'conjunto_id': conjunto['conjunto_id'], 'candidate_id': conjunto['miembros']['pinn']}
    ruta = tmp_path / 'referencia.json'
    ruta.write_text(json.dumps(referencia), encoding='utf-8')
    inst = ac.congelar_instantanea({'referencia_pinn': ruta}, tmp_path / 'captura',
        contexto=CTX, versiones={'codigo': 'x'})
    assert ac.referencia_pinn_ciclo(inst, registro=reg)['candidate_id'] == referencia['candidate_id']
    ruta.write_text(json.dumps({**referencia, 'candidate_id': 'f' * 64}), encoding='utf-8')
    otra = ac.congelar_instantanea({'referencia_pinn': ruta}, tmp_path / 'captura',
        contexto=CTX, versiones={'codigo': 'x'})
    with pytest.raises(ac.CicloBloqueado, match='referencia.*distinta'):
        ac.referencia_pinn_ciclo(otra, registro=reg)
    with pytest.raises(ac.CicloBloqueado, match='referencia.*ausente'):
        ac.referencia_pinn_ciclo(inst, registro=RegistroModelo(tmp_path / 'sin_modelo' / 'registro'))
    with pytest.raises(ac.CicloBloqueado, match='integridad'):
        ac.referencia_pinn_ciclo(inst, registro=RegistroModelo(tmp_path / 'otro_registro'))
