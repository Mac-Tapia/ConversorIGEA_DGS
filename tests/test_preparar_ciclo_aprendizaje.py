"""050:RF-11 a RF-21: manifiestos reales de procedencia y contexto, sin entrenar ni escribir en origen."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from convertersmartgrid import aprendizaje_continuo as ac
from convertersmartgrid.asistente.dataset_entrenamiento import escribir_particiones, normalizar_orden
from convertersmartgrid.digital_twin.buffer import BuferEpisodios
from convertersmartgrid.digital_twin.episode import leer_episodio
from convertersmartgrid.digital_twin.productor_pinn import muestras_aprendizaje as muestras_pinn
from convertersmartgrid.experimentos import ContextoExperimento, clave_contexto
from convertersmartgrid.productores_aprendizaje import ProductoresReales

from test_digital_twin_episode import _payload
from test_gemelo_contratos_v2 import _grafo

_spec = importlib.util.spec_from_file_location('preparar_ciclo_prueba',
    Path(__file__).resolve().parents[1] / 'tools' / 'preparar_ciclo_aprendizaje.py')
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)

FECHA = '2026-11-08T10:00:00-05:00'


def _args(salida, **cambios):
    base = dict(salida=salida, dataset=None, observaciones=[], vocabulario=None, twin=None, cabeceras=None,
                llm_dataset=None, casos_evolutivos=None, referencia_pinn=None, complemento=None,
                zona_horaria=None, cadencia_min=None, horizontes=None, semillas=pc.SEMILLAS,
                embedding_model=pc.MODELO_EMBEDDINGS)
    return SimpleNamespace(**{**base, **cambios})


def _dataset(tmp_path, *filas):
    destino = tmp_path / 'dataset'
    escribir_particiones({'train': tuple(filas), 'validation': (), 'test': ()}, destino)
    return destino


def _orden(texto='convierte la red', fecha=FECHA):
    return normalizar_orden({'texto': texto, 'tarea': 'convertir', 'datos': [], 'origen': 'confirmado', 'fecha': fecha})


def _observaciones(tmp_path, *pares):
    ruta = tmp_path / 'ejemplos.jsonl'
    ruta.write_text(''.join(json.dumps({'texto': t, 'fecha': f, 'tarea': 'convertir', 'origen': 'confirmado'}) + '\n'
                            for t, f in pares), encoding='utf-8')
    return ruta


def _congelar(resumen, raiz):
    salida = Path(resumen['fuentes']['procedencia']).parent
    contexto = json.loads((salida / 'contexto_ciclo.json').read_text(encoding='utf-8'))
    return ac.congelar_instantanea({n: Path(r) for n, r in resumen['fuentes'].items()}, raiz,
                                   contexto=contexto, versiones={'codigo': 'prueba'})


def _bufer(tmp_path, *payloads):
    bufer = BuferEpisodios(tmp_path / 'twin')
    episodios = [leer_episodio(p) for p in payloads]
    for e in episodios:
        bufer.guardar(e)
    return tmp_path / 'twin', episodios


def _que_ensena(**cambios):
    return _payload(topologia={'grafo': _grafo()}, **cambios)


def _complemento(tmp_path, proyectos=None, series=None):
    ruta = tmp_path / 'complemento.json'
    ruta.write_text(json.dumps({'schema': pc.ESQUEMA_COMPLEMENTO, 'proyectos': proyectos or {}, 'series': series or {}}),
                    encoding='utf-8')
    return ruta


COMPLETO = {'period': '2026-07', 'criterio_fijas': 'coincidente', 'profile_hash': 'b' * 64}


def test_orden_real_recibe_referencia_y_prepara_al_transformer(tmp_path):
    """050:RF-11 — la orden se coteja con su observación y el productor real la acepta."""
    fila = _orden()
    dataset = _dataset(tmp_path, fila)
    resumen = pc.preparar(_args(tmp_path / 'salida', dataset=dataset,
                                observaciones=[_observaciones(tmp_path, ('convierte la red', FECHA))]))
    assert resumen['informe']['dataset']['con_referencia'] == 1
    inst = _congelar(resumen, tmp_path / 'ac')
    r = ac.preparar_fuentes(inst, ['transformer'], productores=ProductoresReales())
    assert r['resumen'] == {'transformer': {'entrenamiento': 1}} and r['cuarentena'] == []
    ids = {m.observacion_id for m in r['vistas']['transformer']['entrenamiento']}
    assert len(ids) == 1


def test_no_escribe_en_los_origenes(tmp_path):
    """050:RF-12 — las fuentes conservan sus bytes y la salida es la única carpeta nueva."""
    dataset = _dataset(tmp_path, _orden())
    obs = _observaciones(tmp_path, ('convierte la red', FECHA))
    twin, _ = _bufer(tmp_path, _que_ensena())
    antes = {'dataset': ac.huellas_de(dataset), 'obs': ac.huellas_de(obs), 'twin': ac.huellas_de(twin)}
    pc.preparar(_args(tmp_path / 'salida', dataset=dataset, observaciones=[obs], twin=twin,
                      complemento=_complemento(tmp_path, {'P': COMPLETO})))
    assert antes == {'dataset': ac.huellas_de(dataset), 'obs': ac.huellas_de(obs), 'twin': ac.huellas_de(twin)}


def test_rechaza_salida_con_contenido_o_dentro_de_una_fuente(tmp_path):
    """050:RF-11/12 — nada se mezcla con otro ensayo ni se escribe dentro de un almacén."""
    ocupada = tmp_path / 'ocupada'
    ocupada.mkdir()
    (ocupada / 'previo.json').write_text('{}', encoding='utf-8')
    assert pc.main(['--salida', str(ocupada)]) == 1
    twin, _ = _bufer(tmp_path, _que_ensena())
    assert pc.main(['--salida', str(twin / 'nueva'), '--twin', str(twin)]) == 1
    assert not (twin / 'nueva').exists()


def test_orden_sin_observacion_va_a_cuarentena_sin_referencia(tmp_path):
    """050:RF-15 — sin texto y fecha coincidentes no se fabrica la referencia; el ciclo bloquea."""
    fila = _orden()
    dataset = _dataset(tmp_path, fila)
    otra = _observaciones(tmp_path, ('otra orden', FECHA), ('convierte la red', '2026-01-01T00:00:00-05:00'))
    resumen = pc.preparar(_args(tmp_path / 'salida', dataset=dataset, observaciones=[otra]))
    cuarentena = json.loads((tmp_path / 'salida' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert [c['registro'] for c in cuarentena if c['registro'] == fila.record_id] == [fila.record_id]
    assert 'sin observación original' in next(c['motivo'] for c in cuarentena if c['registro'] == fila.record_id)
    assert resumen['informe']['dataset']['con_referencia'] == 0
    inst = _congelar(resumen, tmp_path / 'ac')
    with pytest.raises(ac.CicloBloqueado, match='falta referencia'):
        ac.preparar_fuentes(inst, ['transformer'], productores=ProductoresReales())


def test_episodio_sin_campos_043_no_entra_en_el_mapa(tmp_path):
    """050:RF-13/15 — sin profile_hash ni periodo no hay huella 043: cuarentena y vista sin él."""
    twin, (e,) = _bufer(tmp_path, _que_ensena())
    resumen = pc.preparar(_args(tmp_path / 'salida', twin=twin))
    cuarentena = json.loads((tmp_path / 'salida' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert cuarentena == [{'fuente': 'twin', 'registro': e.episode_id,
                           'motivo': 'identidad 043 incompleta: faltan period, criterio_fijas, profile_hash'}]
    assert resumen['proyectos_043'] == 0 and resumen['contexto_hash'] is None
    assert 'twin' not in resumen['fuentes'] and resumen['pendientes']['twin']['familias'] == ['pinn', 'evolutivos']
    assert not (tmp_path / 'salida' / 'vista_twin').exists()
    assert not (tmp_path / 'salida' / 'contexto_ciclo.json').exists()


def test_complemento_completa_la_identidad_y_la_pinn_la_acepta(tmp_path):
    """050:RF-13 — la huella es la de ContextoExperimento con los 14 campos, comprobada por el productor."""
    twin, (e,) = _bufer(tmp_path, _que_ensena())
    obs = _dataset(tmp_path, _orden())
    resumen = pc.preparar(_args(tmp_path / 'salida', twin=twin, dataset=obs,
        observaciones=[_observaciones(tmp_path, ('convierte la red', FECHA))],
        complemento=_complemento(tmp_path, {'P': COMPLETO})))
    esperado = ContextoExperimento('run-1', 'txt', e.fuente['source_fingerprint'], 'P', ('A1', 'A2'),
        e.contexto_fisico['case_id'], 'sin_proyecto', None, '2026-07', 'coincidente', 'b' * 64,
        e.contexto_fisico['topology_hash'], e.contexto_fisico['controls_hash'], e.contexto_fisico['scenario_hash'])
    contexto = json.loads((tmp_path / 'salida' / 'contexto_ciclo.json').read_text(encoding='utf-8'))
    assert list(contexto['proyectos'].values()) == [clave_contexto(esperado)]
    inst = _congelar(resumen, tmp_path / 'ac')
    procedencia = json.loads(ac.ruta_de(inst, 'procedencia').read_text(encoding='utf-8'))
    muestras = muestras_pinn(inst, procedencia['referencias'])
    assert [m.etiqueta for m in muestras] == ['motor_nativo'] and muestras[0].contexto == clave_contexto(esperado)


def test_complemento_que_contradice_al_episodio_va_a_cuarentena(tmp_path):
    """050:RF-14 — lo declarado no sustituye lo leído en el episodio."""
    fisico = {'case_role': 'sin_proyecto', 'case_id': 'IntCase:Estudios\\sin_proyecto', 'topology_hash': 'a' * 64,
              'controls_hash': 'a' * 64, 'scenario_hash': 'a' * 64, 'criterio_fijas': 'coincidente',
              'period': {'clientes': '2026-07', 'maxima': '2026-07', 'status': 'CLIENT_PERIOD_MATCH'}}
    twin, (e,) = _bufer(tmp_path, _que_ensena(contexto_fisico=fisico))
    pc.preparar(_args(tmp_path / 'salida', twin=twin,
        complemento=_complemento(tmp_path, {'P': {**COMPLETO, 'period': '2025-01'}})))
    cuarentena = json.loads((tmp_path / 'salida' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert 'contradice al episodio en period' in cuarentena[0]['motivo'] and cuarentena[0]['registro'] == e.episode_id


def test_complemento_con_campos_ajenos_se_rechaza(tmp_path):
    """050:RF-13 — el complemento no puede redefinir huellas de topología ni la fuente."""
    ruta = _complemento(tmp_path, {'P': {'topology_hash': 'c' * 64}})
    assert pc.main(['--salida', str(tmp_path / 's'), '--complemento', str(ruta)]) == 1


def test_vista_solo_con_episodios_que_ensenan_y_tienen_referencia(tmp_path):
    """050:RF-16 — lo que no enseña se cuenta con su motivo y no se copia."""
    ensena = _que_ensena()
    no_ensena = _payload(creado='2026-10-22T10:00:00+00:00')
    twin, (a, b) = _bufer(tmp_path, ensena, no_ensena)
    resumen = pc.preparar(_args(tmp_path / 'salida', twin=twin, complemento=_complemento(tmp_path, {'P': COMPLETO})))
    vista = Path(resumen['fuentes']['twin'])
    assert sorted(p.stem for p in vista.rglob('*.json')) == [a.episode_id]
    ac.validar_vista_twin(vista)
    assert resumen['informe']['twin']['no_ensenan'] == {'sin grafo o sin tensiones': 1}
    assert b.episode_id not in json.loads((tmp_path / 'salida' / 'procedencia.json').read_text(encoding='utf-8'))['referencias']['twin']


def test_consultas_documentales_llevan_la_fecha_de_sellado_y_lo_dicen(tmp_path):
    """050:RF-17 — un registro documental sin fecha toma la del manifiesto, y consta el origen."""
    from dataclasses import replace
    fragmento = replace(_orden('La fuente del estudio se conserva con una huella verificable.'),
        record_id='ctx1', group_id='grupo_ctx1', tipo='artefacto_contexto', quality='context')
    dataset = _dataset(tmp_path, _orden(), fragmento)
    resumen = pc.preparar(_args(tmp_path / 'salida', dataset=dataset,
                                observaciones=[_observaciones(tmp_path, ('convierte la red', FECHA))]))
    procedencia = json.loads((tmp_path / 'salida' / 'procedencia.json').read_text(encoding='utf-8'))
    consultas = [r for k, r in procedencia['referencias']['dataset'].items() if k.startswith('retrieval_train:')]
    sellado = resumen['informe']['dataset']['instante_consultas']
    assert len(consultas) == 1 and consultas[0]['instante'] == sellado['valor']
    assert datetime.fromisoformat(sellado['valor']).utcoffset() is not None and '050:RF-17' in sellado['origen']
    # Sin consultas reservadas, embeddings queda con su motivo textual.
    cuarentena = json.loads((tmp_path / 'salida' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert any('retrieval_test' in c['motivo'] for c in cuarentena)


def test_referencia_fisica_no_toma_la_fecha_de_sellado(tmp_path):
    """050:RF-18 — el instante de un episodio es el suyo, con su zona."""
    twin, (e,) = _bufer(tmp_path, _que_ensena())
    pc.preparar(_args(tmp_path / 'salida', twin=twin, complemento=_complemento(tmp_path, {'P': COMPLETO})))
    referencia = json.loads((tmp_path / 'salida' / 'procedencia.json').read_text(encoding='utf-8'))['referencias']['twin'][e.episode_id]
    assert referencia['instante'] == e.creado and referencia['registro_id'] == e.episode_id
    ruta = next((twin / 'objetos').rglob(f'{e.episode_id}.json'))
    assert referencia['fuente_hash'] == hashlib.sha256(ruta.read_bytes()).hexdigest()


def _objetivos_falsos(monkeypatch, apartados=()):
    from convertersmartgrid.digital_twin import temporal_entrenamiento as te
    from convertersmartgrid.digital_twin.pronostico import Objetivo
    inicio = datetime(2026, 1, 1, tzinfo=timezone.utc)
    curva = [(inicio + timedelta(hours=i), 100. + i % 24) for i in range(84 * 24)]
    objetivo = Objetivo('cabecera', 'L-A1', 'kW', 'kW', curva)
    monkeypatch.setattr(te, 'objetivos_de_cabecera', lambda rutas: ([objetivo], list(apartados)))


def _libro(tmp_path):
    libro = tmp_path / 'libro.xls'
    libro.write_text('libro de contrato', encoding='utf-8')
    return libro


GRU = dict(zona_horaria='UTC', cadencia_min=60, horizontes='24')


def test_serie_apartada_se_reporta_y_la_guarda_gru_sigue(tmp_path, monkeypatch):
    """050:RF-19 — el motivo textual consta y la familia sigue bloqueada: no se rebaja la guarda."""
    motivo = {'objetivo': 'cabecera:L-A9', 'motivo': 'L-A9: sin curva'}
    _objetivos_falsos(monkeypatch, [motivo])
    libro = _libro(tmp_path)
    twin, _ = _bufer(tmp_path, _que_ensena(caso='caso_base', clase='accepted'))
    resumen = pc.preparar(_args(tmp_path / 'salida', twin=twin, cabeceras=libro,
        complemento=_complemento(tmp_path, {'P': COMPLETO}), **GRU))
    assert resumen['informe']['cabeceras']['apartados'] == [motivo]
    cuarentena = json.loads((tmp_path / 'salida' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert {'fuente': 'cabeceras', 'registro': 'cabecera:L-A9', 'motivo': 'objetivo apartado: L-A9: sin curva'} in cuarentena
    inst = _congelar(resumen, tmp_path / 'ac')
    with pytest.raises(ac.CicloBloqueado, match='objetivos apartados'):
        ac.preparar_fuentes(inst, ['gru'], parametros=GRU, productores=ProductoresReales())


def test_serie_con_caso_base_unico_recibe_referencias_que_el_productor_acepta(tmp_path, monkeypatch):
    """050:RF-11/20 — sin apartados, cada ventana lleva la identidad 043 del caso base de su alimentador."""
    _objetivos_falsos(monkeypatch)
    twin, (e,) = _bufer(tmp_path, _que_ensena(caso='caso_base', clase='accepted'))
    resumen = pc.preparar(_args(tmp_path / 'salida', twin=twin, cabeceras=_libro(tmp_path),
        complemento=_complemento(tmp_path, {'P': COMPLETO}), **GRU))
    assert resumen['informe']['cabeceras']['ventanas_con_referencia'] > 0
    inst = _congelar(resumen, tmp_path / 'ac')
    r = ac.preparar_fuentes(inst, ['gru'], parametros=GRU, productores=ProductoresReales())
    assert set(r['vistas']['gru']) == {'entrenamiento', 'seleccion', 'calibracion', 'prueba'} and not r['cuarentena']


def test_serie_sin_identidad_unica_va_a_cuarentena(tmp_path, monkeypatch):
    """050:RF-20 — sin caso base del alimentador no se le atribuye otro contexto."""
    _objetivos_falsos(monkeypatch)
    twin, _ = _bufer(tmp_path, _que_ensena())  # «Sin proyecto»: es un estudio, no la red como está.
    resumen = pc.preparar(_args(tmp_path / 'salida', twin=twin, cabeceras=_libro(tmp_path),
        complemento=_complemento(tmp_path, {'P': COMPLETO}), **GRU))
    cuarentena = json.loads((tmp_path / 'salida' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert any(c['registro'] == 'cabecera:L-A1:kW' and '0 identidades 043' in c['motivo'] for c in cuarentena)
    assert resumen['informe']['cabeceras']['ventanas_con_referencia'] == 0


def test_serie_declarada_con_contexto_ajeno_se_rechaza(tmp_path, monkeypatch):
    """050:RF-20 — el complemento no introduce una huella que ningún episodio respalda."""
    _objetivos_falsos(monkeypatch)
    twin, _ = _bufer(tmp_path, _que_ensena())
    pc.preparar(_args(tmp_path / 'salida', twin=twin, cabeceras=_libro(tmp_path),
        complemento=_complemento(tmp_path, {'P': COMPLETO}, {'L-A1': 'f' * 64}), **GRU))
    cuarentena = json.loads((tmp_path / 'salida' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert any('no es de ningún episodio' in c['motivo'] for c in cuarentena)


def test_ruta_ausente_queda_pendiente_con_sus_familias(tmp_path):
    """050:RF-21 — lo que no se pasó se declara, con lo que deja sin preparar."""
    resumen = pc.preparar(_args(tmp_path / 'salida'))
    assert resumen['pendientes']['dataset']['familias'] == ['transformer', 'clasificador', 'embeddings']
    assert resumen['pendientes']['llm_dataset']['familias'] == ['qlora']
    assert resumen['pendientes']['evolutivos_casos']['familias'] == ['evolutivos']
    assert resumen['pendientes']['cabeceras']['familias'] == ['gru']
    assert resumen['entrenamiento_ejecutado'] is False


def test_corpus_con_parte_invalida_conserva_el_motivo(tmp_path, monkeypatch):
    """050:RF-15/17 — una parte que el lector sellado rechaza no recibe referencia; la válida, su sellado."""
    from convertersmartgrid.asistente import llm_destilacion as ld
    corpus = tmp_path / 'corpus'
    corpus.mkdir()
    (corpus / 'dataset_manifest.json').write_text('{}', encoding='utf-8')
    (corpus / 'entrenamiento.jsonl').write_text('{}\n', encoding='utf-8')

    def lector(dataset, parte, **_):
        if parte != 'entrenamiento':
            raise ValueError('particion ausente o invalida')
        return [{'record_id': 'r1', 'texto': 'x'}], {}
    monkeypatch.setattr(ld, 'leer_particion_real', lector)
    resumen = pc.preparar(_args(tmp_path / 'salida', llm_dataset=corpus))
    referencia = json.loads((tmp_path / 'salida' / 'procedencia.json').read_text(encoding='utf-8'))['referencias']['llm_dataset']['r1']
    assert referencia['instante'] == resumen['informe']['llm_dataset']['instante']['valor']
    assert referencia['contexto'] == hashlib.sha256((corpus / 'dataset_manifest.json').read_bytes()).hexdigest()
    cuarentena = json.loads((tmp_path / 'salida' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert {c['registro'] for c in cuarentena} == {'seleccion', 'calibracion', 'prueba'}


def _caso(e, contexto):
    return {'record_id': 'caso1', 'episode_id': e.episode_id, 'contexto_043': asdict(contexto), 'problema': 'maniobras',
            'particion': 'entrenamiento', 'parametros': {'maniobras': ['L1'], 'tension_min_pu': .9, 'tension_max_pu': 1.1},
            'normalizacion': {'perdidas_kw': [0, 100]}}


def test_caso_evolutivo_coherente_prepara_y_uno_ajeno_va_a_cuarentena(tmp_path):
    """050:RF-13/15 — el contexto del caso se contrasta con su episodio antes de referenciarlo."""
    from convertersmartgrid.digital_twin.evolutivo import casos_aprendizaje
    twin, (e,) = _bufer(tmp_path, _que_ensena())
    f = e.contexto_fisico
    bueno = ContextoExperimento('run-1', 'txt', e.fuente['source_fingerprint'], 'P', ('A1', 'A2'), f['case_id'],
        'sin_proyecto', None, 'no_aplica', 'no_aplica', 'a' * 64, f['topology_hash'], f['controls_hash'], f['scenario_hash'])
    casos = tmp_path / 'casos.json'
    malo = {**_caso(e, bueno), 'record_id': 'caso2', 'contexto_043': {**asdict(bueno), 'project': 'OTRO'}}
    casos.write_text(json.dumps({'schema': 'convertersmartgrid-optimization-learning-cases-v1',
                                 'casos': [_caso(e, bueno), malo]}), encoding='utf-8')
    resumen = pc.preparar(_args(tmp_path / 'salida', twin=twin, casos_evolutivos=casos))
    cuarentena = json.loads((tmp_path / 'salida' / 'cuarentena.json').read_text(encoding='utf-8'))
    assert any(c['registro'] == 'caso2' and 'project/feeders' in c['motivo'] for c in cuarentena)
    assert resumen['informe']['evolutivos_casos']['con_referencia'] == 1
    procedencia = json.loads((tmp_path / 'salida' / 'procedencia.json').read_text(encoding='utf-8'))
    assert list(procedencia['referencias']['evolutivos_casos']) == ['caso1']
    # El caso rechazado sigue en el manifiesto: el productor no acepta preparar hasta quitarlo.
    malos = tmp_path / 'solo_bueno.json'
    malos.write_text(json.dumps({'schema': 'convertersmartgrid-optimization-learning-cases-v1',
                                 'casos': [_caso(e, bueno)]}), encoding='utf-8')
    resumen = pc.preparar(_args(tmp_path / 'salida2', twin=twin, casos_evolutivos=malos))
    inst = _congelar(resumen, tmp_path / 'ac')
    assert [c['muestra'].record_id for c in casos_aprendizaje(inst)] == ['caso1']


def test_congelar_y_ciclo_comparten_una_sola_copia(tmp_path):
    """050:RF-1/11 — las dos órdenes generadas resuelven la misma instantánea, sin duplicar datos."""
    spec = importlib.util.spec_from_file_location('ciclo_t6', Path(__file__).resolve().parents[1] / 'tools' / 'aprendizaje_continuo.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    dataset = _dataset(tmp_path, _orden())
    resumen = pc.preparar(_args(tmp_path / 'salida', dataset=dataset, zona_horaria='UTC', cadencia_min=15, horizontes='1,4,96',
                                observaciones=[_observaciones(tmp_path, ('convierte la red', FECHA))]))
    raiz = tmp_path / 'ac'
    assert cli.main(['--raiz', str(raiz), *resumen['ordenes']['congelar']]) == 0
    orden = [{'<huella 044>': 'a' * 64, '<s>': '60', '<GiB>': '1'}.get(v, v) for v in resumen['ordenes']['ciclo_solo_preparar']]
    orden[orden.index('--familias') + 1] = 'transformer'
    assert cli.main(['--raiz', str(raiz), *orden]) == 0
    assert len(list((raiz / 'instantaneas').iterdir())) == 1
