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
                espacios=[], perfil=None, declarado_por='', proyecto_series=None, proyecto_casos=[],
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
    ruta.write_text(json.dumps({'schema': pc.ESQUEMA_COMPLEMENTO, 'declarado_por': 'prueba', 'proyectos': proyectos or {}, 'series': series or {}}),
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
    inicio = datetime(2026, 1, 1)
    curva = [(inicio + timedelta(minutes=15 * i), 100. + i % 96) for i in range(84 * 96)]
    objetivo = Objetivo('cabecera', 'L-A1', 'kW', 'kW', curva)
    instantes = [(t + timedelta(hours=0)).replace(tzinfo=timezone.utc).isoformat() for t, _ in curva]
    monkeypatch.setattr(te, 'cargar_cabeceras', lambda ruta, **_: ({'L-A1': [v for _, v in curva]},
        {'instantes': instantes, 'motivos_omitidas': {'L-A9': 'L-A9: fila 2: potencia ausente/inválida'},
         'ambos_sentidos': ['L-A8'], 'hojas_omitidas': ['L-A9', 'L-A8']}))
    monkeypatch.setattr(te, 'objetivos_de_cabecera', lambda rutas, pares=None, **_: ([objetivo], list(apartados)))


def _libro(tmp_path):
    libro = tmp_path / 'libro.xls'
    libro.write_text('libro de contrato', encoding='utf-8')
    return libro


GRU = dict(zona_horaria='UTC', cadencia_min=15, horizontes='1,4,96')


def test_sin_series_pedidas_lo_apartado_consta_y_el_ciclo_sigue(tmp_path, monkeypatch):
    """050:RF-19/22 — el motivo textual de cargar_cabeceras consta y la serie válida prepara."""
    _objetivos_falsos(monkeypatch)
    twin, _ = _bufer(tmp_path, _que_ensena(caso='caso_base', clase='accepted', contexto_fisico=_fisico('caso_base')))
    resumen = pc.preparar(_args(tmp_path / 'salida', twin=twin, cabeceras=_libro(tmp_path),
        complemento=_complemento(tmp_path, {'P': COMPLETO}), **GRU))
    apartados = resumen['informe']['cabeceras']['apartados']
    assert {'objetivo': 'cabecera:L-A9', 'motivo': 'L-A9: fila 2: potencia ausente/inválida'} in apartados
    assert any(a['objetivo'] == 'cabecera:L-A8' for a in apartados)
    inst = _congelar(resumen, tmp_path / 'ac')
    r = ac.preparar_fuentes(inst, ['gru'], parametros=GRU, productores=ProductoresReales())
    assert set(r['vistas']['gru']) == {'entrenamiento', 'seleccion', 'calibracion', 'prueba'} and not r['cuarentena']


def test_con_series_pedidas_la_guarda_sigue_dura(tmp_path, monkeypatch):
    """050:RF-19 — lo pedido que falta bloquea: no se rebaja la guarda."""
    from convertersmartgrid.digital_twin import temporal_entrenamiento as te
    _objetivos_falsos(monkeypatch, [{'objetivo': 'cabecera:L-A9', 'motivo': 'L-A9: sin curva'}])
    inst = ac.congelar_instantanea({'cabeceras': _libro(tmp_path)}, tmp_path / 'ac', contexto='a' * 64, versiones={'codigo': 'x'})
    with pytest.raises(ac.CicloBloqueado, match='objetivos apartados'):
        te.muestras_aprendizaje(inst, {}, pares=[('L-A9', 'L-A9')], **GRU)


def test_criterio_comun_recorta_al_tramo_y_aparta_con_huecos(tmp_path, monkeypatch):
    """050:RF-22 — fuera del tramo común no se usa, y un kVAR con huecos dentro de él se aparta con su cifra."""
    from convertersmartgrid.digital_twin import temporal_entrenamiento as te
    from convertersmartgrid.digital_twin.pronostico import Objetivo
    inicio = datetime(2026, 1, 1)
    curva = [(inicio + timedelta(minutes=15 * i), 10.) for i in range(200)]
    comunes = [(t.replace(tzinfo=timezone.utc)).isoformat() for t, _ in curva[50:150]]
    monkeypatch.setattr(te, 'cargar_cabeceras', lambda ruta, **_: ({'S': []}, {'instantes': comunes, 'motivos_omitidas': {},
        'ambos_sentidos': [], 'hojas_omitidas': []}))
    monkeypatch.setattr(te, 'objetivos_de_cabecera', lambda rutas, pares=None, **_: ([Objetivo('cabecera', 'S', 'kW', 'kW', curva),
        Objetivo('cabecera', 'S', 'kVAR', 'kVAR', curva[:100])], []))
    objetivos, apartados = te.objetivos_del_ciclo(tmp_path / 'x', zona_horaria='UTC', cadencia_min=15)
    assert [(o.nombre, len(o.curva)) for o in objetivos] == [('cabecera:S:kW', 100)]
    assert apartados == [{'objetivo': 'cabecera:S:kVAR', 'motivo': '50 huecos en el tramo común; no se imputan objetivos'}]
    with pytest.raises(ValueError, match='15 minutos'):
        te.objetivos_del_ciclo(tmp_path / 'x', zona_horaria='UTC', cadencia_min=60)


def test_trabajador_del_ciclo_recibe_el_mismo_criterio():
    """050:RF-22 — la orden GRU del ciclo pide el tramo común con que se prepararon sus muestras."""
    import inspect
    from tools import reentrenar_modelos as rm
    assert "'--tramo-comun'" in inspect.getsource(rm)


def _fisico(rol):
    return {'case_role': rol, 'case_id': f'IntCase:Estudios\\{rol}', 'topology_hash': 'a' * 64,
            'controls_hash': 'a' * 64, 'scenario_hash': 'a' * 64}


def test_serie_con_caso_base_unico_recibe_referencias_que_el_productor_acepta(tmp_path, monkeypatch):
    """050:RF-11/20 — cada ventana lleva la identidad 043 del caso base de su alimentador."""
    _objetivos_falsos(monkeypatch)
    twin, _ = _bufer(tmp_path, _que_ensena(caso='caso_base', clase='accepted', contexto_fisico=_fisico('caso_base')))
    resumen = pc.preparar(_args(tmp_path / 'salida', twin=twin, cabeceras=_libro(tmp_path),
        complemento=_complemento(tmp_path, {'P': COMPLETO}), **GRU))
    assert resumen['informe']['cabeceras']['ventanas_con_referencia'] > 0
    assert resumen['informe']['cabeceras']['por_objetivo']['instantes'] == 84 * 96


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


def test_proyecto_de_las_series_usa_su_ultimo_caso_base(tmp_path, monkeypatch):
    """050:RF-27 — las series del libro toman el caso base más reciente del proyecto declarado."""
    _objetivos_falsos(monkeypatch)
    viejo = _que_ensena(caso='caso_base', clase='accepted', contexto_fisico=_fisico('caso_base'))
    nuevo = _que_ensena(caso='caso_base', clase='accepted', creado='2026-11-01T10:00:00+00:00',
        contexto_fisico={**_fisico('caso_base'), 'scenario_hash': 'b' * 64})
    twin, (_, e) = _bufer(tmp_path, viejo, nuevo)
    resumen = pc.preparar(_args(tmp_path / 'salida', twin=twin, cabeceras=_libro(tmp_path), proyecto_series='P',
        complemento=_complemento(tmp_path, {'P': COMPLETO}), **GRU))
    declaradas = resumen['informe']['series_declaradas']
    guardado = json.loads((tmp_path / 'salida' / 'complemento.json').read_text(encoding='utf-8'))
    assert guardado['series'] == {'L-A1': declaradas['contexto']} and guardado['declarado_por'] == 'prueba'
    contexto, _ = pc.contexto_de_episodio(e, guardado)
    assert clave_contexto(contexto) == declaradas['contexto']
    assert resumen['fuentes']['complemento'].endswith('complemento.json')


def test_complemento_sin_responsable_se_rechaza(tmp_path):
    """050:RF-25 — lo declarado tiene quien responda."""
    ruta = tmp_path / 'c.json'
    ruta.write_text(json.dumps({'schema': pc.ESQUEMA_COMPLEMENTO, 'proyectos': {}, 'series': {}}), encoding='utf-8')
    assert pc.main(['--salida', str(tmp_path / 's'), '--complemento', str(ruta)]) == 1


def test_complemento_generado_lee_la_ultima_calibracion_y_el_perfil(tmp_path):
    """050:RF-25 — mes y criterio del informe más reciente; sin informe, se dice; la huella se anota como declarada."""
    import os
    salida = tmp_path / 'web' / 'esp' / 'runs' / 'r1' / 'salida'
    salida.mkdir(parents=True)
    for i, (mes, criterio) in enumerate((('2026-02-01 10:00:00', 'maximo_mes'), ('2026-07-01 10:00:00', 'coincidente'))):
        ruta = salida / f'ajuste_cabecera_aplicacion_{i}.json'
        ruta.write_text(json.dumps({'project': 'P', 'criterio_fijas': criterio, 'objetivo': {'fecha': mes}}), encoding='utf-8')
        os.utime(ruta, (1000 + i, 1000 + i))
    perfil = tmp_path / 'perfil.json'
    perfil.write_text('{"empresa": "X"}', encoding='utf-8')
    dato, sin = pc.generar_complemento({'P', 'Q'}, [tmp_path / 'web'], perfil, 'integrador')
    assert dato['declarado_por'] == 'integrador' and 'declarada al preparar' in dato['profile_hash_nota']
    assert dato['proyectos']['P']['period'] == '2026-07' and dato['proyectos']['P']['criterio_fijas'] == 'coincidente'
    assert list(sin) == ['Q'] and 'Q' not in dato['proyectos']


def test_plantilla_referenciada_por_su_parte_sigue_siendo_maestro(tmp_path):
    """050:RF-26 — una plantilla no se coteja con observaciones y su etiqueta no sube."""
    from dataclasses import replace
    humano = normalizar_orden({'texto': 'convierte la red', 'tarea': 'convertir', 'datos': [], 'origen': 'confirmado', 'fecha': FECHA})
    plantilla = replace(_orden('informe de plantilla sobre factibilidad'), record_id='plantilla1', group_id='g1',
        tipo='informe', quality='silver_deterministic', verification='deterministic_template', resultado={'tipo_informe': 'estudio', 'subtipo': 'PIDE'})
    dataset = _dataset(tmp_path, humano, plantilla)
    resumen = pc.preparar(_args(tmp_path / 'salida', dataset=dataset, observaciones=[_observaciones(tmp_path, ('convierte la red', FECHA))]))
    assert resumen['informe']['dataset']['generados_con_referencia'] == 1
    inst = _congelar(resumen, tmp_path / 'ac')
    r = ac.preparar_fuentes(inst, ['clasificador'], productores=ProductoresReales())
    m = r['vistas']['clasificador']['entrenamiento'][0]
    assert (m.etiqueta, m.origen) == ('maestro', 'redactado')


def test_unir_datasets_conserva_particiones_y_bloquea_si_mueve(tmp_path, monkeypatch):
    """050:RF-24 — la unión no mueve reservas; si moviera alguna, no escribe nada."""
    spec = importlib.util.spec_from_file_location('unir_t7', Path(__file__).resolve().parents[1] / 'tools' / 'unir_dataset_lenguaje.py')
    un = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(un)
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir(), b.mkdir()
    from convertersmartgrid.asistente.dataset_entrenamiento import particionar_dataset
    filas = [_orden(f'orden numero {i}') for i in range(40)]
    escribir_particiones(particionar_dataset(tuple(filas[:20])), a)
    escribir_particiones(particionar_dataset(tuple(filas[20:])), b)
    informe = un.unir([a, b], tmp_path / 'u')
    assert informe['particiones_conservadas'] is True
    assert sum(sum(v.values()) for v in informe['particiones'].values()) == 40
    from convertersmartgrid.asistente import dataset_entrenamiento as de
    real = de.particionar_dataset
    monkeypatch.setattr(de, 'particionar_dataset', lambda r: {'train': tuple(r), 'validation': (), 'test': ()} if real(r)['test'] or real(r)['validation'] else real(r))
    with pytest.raises(ValueError, match='movería'):
        un.unir([a, b], tmp_path / 'u2')
    assert not (tmp_path / 'u2').exists()


def test_episodio_capturado_guarda_su_identidad_sin_complemento(tmp_path):
    """050:RF-23 — con el plan completo, el episodio nuevo basta para la huella 043."""
    from convertersmartgrid.digital_twin.contratos_fisicos import contexto_fisico
    from convertersmartgrid.digital_twin.integration import plan_de_lectura
    from convertersmartgrid.digital_twin.episode import Caso
    plan = {'project': 'P', 'feeders': ['A1', 'A2'], 'periodo': '2026-07', 'criterio_fijas': 'coincidente', 'profile_hash': 'b' * 64}
    assert plan_de_lectura(plan, Caso.SIN_PROYECTO, {})['profile_hash'] == 'b' * 64
    grafo = _grafo()
    lectura = {'topologia': {'grafo': grafo}, 'caso_nativo': {'id': 'IntCase:x', 'rol': 'sin_proyecto'},
               'contexto': {'period': '2026-07', 'criterio_fijas': 'coincidente', 'profile_hash': 'b' * 64}}
    fisico = contexto_fisico(lectura)
    assert (fisico['period'], fisico['criterio_fijas'], fisico['profile_hash']) == ('2026-07', 'coincidente', 'b' * 64)
    twin, (e,) = _bufer(tmp_path, _que_ensena(contexto_fisico={k: fisico[k] for k in
        ('case_role', 'case_id', 'topology_hash', 'controls_hash', 'scenario_hash', 'period', 'criterio_fijas', 'profile_hash')} ))
    contexto, motivo = pc.contexto_de_episodio(e, {'proyectos': {}, 'series': {}})
    assert motivo is None and contexto.profile_hash == 'b' * 64


def test_lectura_de_escenarios_recibe_la_identidad_del_plan():
    """050:RF-23 — los escenarios leen con otro guion, sin contexto: el episodio toma la del plan."""
    from test_digital_twin_capture import _construir, _lectura, _plan
    from convertersmartgrid.digital_twin.episode import Caso
    plan = {**_plan(), 'periodo': '2026-07', 'criterio_fijas': 'coincidente', 'profile_hash': 'b' * 64}
    e = _construir(plan=plan, caso=Caso.SIN_PROYECTO, referencia=None)
    assert (e.contexto_fisico['period'], e.contexto_fisico['criterio_fijas'], e.contexto_fisico['profile_hash']) == (
        '2026-07', 'coincidente', 'b' * 64)
    # Lo que la lectura ya trae no se sobrescribe.
    propia = _lectura(contexto={'period': '2025-01', 'criterio_fijas': 'maximo_mes', 'profile_hash': 'c' * 64})
    e = _construir(plan=plan, caso=Caso.SIN_PROYECTO, lectura=propia, referencia=None)
    assert e.contexto_fisico['period'] == '2025-01'


def test_identidad_de_captura_da_lo_que_consta(monkeypatch):
    """050:RF-23 — periodo y criterio de la calibración en disco y huella del perfil; lo que no consta, no va."""
    from convertersmartgrid.web import services as sv
    from convertersmartgrid.evaluacion_modelos import huella
    monkeypatch.setattr(sv, 'ajuste_aplicado_en_disco', lambda ws, project: {'informes': [
        {'objetivo': {'fecha': '2026-07-13 10:45:00'}, 'criterio_fijas': 'coincidente'}]})
    ws = SimpleNamespace(criterio_cabecera={})
    assert sv.identidad_de_captura(ws, 'P', {'a': 1}) == {'periodo': '2026-07', 'criterio_fijas': 'coincidente', 'profile_hash': huella({'a': 1})}
    monkeypatch.setattr(sv, 'ajuste_aplicado_en_disco', lambda ws, project: None)
    assert sv.identidad_de_captura(ws, 'P', {'a': 1}) == {'profile_hash': huella({'a': 1})}


def test_consultas_del_maestro_se_cuentan_aparte(tmp_path):
    """050:RF-29 — en la evaluación el maestro y el operador no se suman."""
    from convertersmartgrid.asistente.embeddings import origenes_consultas_reservadas
    (tmp_path / 'retrieval_test.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in (
        {'pregunta': 'a', 'origen': 'maestro', 'verification': 'teacher_redacted'},
        {'pregunta': 'b', 'origen': 'maestro', 'verification': 'teacher_redacted'},
        {'pregunta': 'c', 'verification': 'operator_confirmed'})), encoding='utf-8')
    assert origenes_consultas_reservadas(tmp_path) == {'maestro': 2, 'humano': 1}


def test_politica_del_ciclo_es_la_de_044_y_cambia_con_sus_valores():
    """050:RF-30 — ni ceros ni texto: depende de las semillas y de las políticas reales."""
    a = pc.politica_del_ciclo('11,23,37')
    assert a == pc.politica_del_ciclo('11,23,37') and a['huella'] != '0' * 64
    assert a['huella'] != pc.politica_del_ciclo('11,23')['huella'] and set(a['miembros']) == {'agente', 'temporal'}


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
    orden = [{'<s>': '60', '<GiB>': '1'}.get(v, v) for v in resumen['ordenes']['ciclo_solo_preparar']]
    orden[orden.index('--familias') + 1] = 'transformer'
    assert cli.main(['--raiz', str(raiz), *orden]) == 0
    assert len(list((raiz / 'instantaneas').iterdir())) == 1
