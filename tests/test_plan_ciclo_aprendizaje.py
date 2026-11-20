"""050:RF-32 a RF-35: plan del ciclo validado, preparado desde el almacén con su matriz por familia, sin entrenar."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from apoyo import cargar_herramienta
from convertersmartgrid.aplicacion import aprendizaje_continuo as ac

from test_preparar_ciclo_aprendizaje import FECHA, _dataset, _observaciones, _orden, pc

SIETE = ('transformer', 'clasificador', 'gru', 'pinn', 'evolutivos', 'embeddings', 'qlora')


def _almacen(tmp_path, *, dataset=True):
    """Un almacén sintético del asistente: dataset v2 con una orden y su observación original."""
    almacen = tmp_path / 'web' / '_asistente'
    almacen.mkdir(parents=True)
    if dataset:
        _dataset(almacen, _orden())
    _observaciones(almacen, ('convierte la red', FECHA))
    return almacen


def _foto(carpeta: Path) -> dict[str, bytes]:
    return {p.relative_to(carpeta).as_posix(): p.read_bytes() for p in sorted(carpeta.rglob('*')) if p.is_file()}


def _preparar_plan(tmp_path, almacen, *extra):
    """La orden real de la herramienta: código de salida e informe JSON (None si no lo dio)."""
    argv = ['--solo-preparar', '--almacen', str(almacen), '--salida', str(tmp_path / 'preparacion'),
            '--plan-salida', str(tmp_path / 'plan' / 'plan.json'), *extra]
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(io.StringIO()):
        try:
            rc = pc.main(argv)
        except SystemExit as exc:
            rc = exc.code
    try:
        return rc, json.loads(salida.getvalue())
    except ValueError:
        return rc, None


COMPLETO = ('--workspace-id', 'espacio-prueba', '--familias', 'transformer', '--tiempo-s', '60', '--memoria-gib', '1')


def test_solo_preparar_escribe_el_plan_valido_solo_en_su_ruta(tmp_path):
    """050:RF-32 y 050:RF-35 — desde el almacén sale un plan cargable y validado; el almacén queda intacto y
    no se congela ninguna instantánea ni se entrena nada."""
    almacen = _almacen(tmp_path)
    antes = _foto(almacen)
    rc, informe = _preparar_plan(tmp_path, almacen, *COMPLETO)
    assert rc == 0, informe
    assert informe['faltan'] == [] and informe['entrenamiento_ejecutado'] is False
    ruta = tmp_path / 'plan' / 'plan.json'
    assert informe['plan_escrito'] == str(ruta) and ruta.is_file()
    assert _foto(almacen) == antes
    assert not (almacen / 'aprendizaje').exists(), 'el preflight del plan no congela ni crea ciclos'
    assert sorted(p.name for p in ruta.parent.iterdir()) == ['plan.json']
    plan = ac.cargar_plan_ciclo(ruta)
    assert ac.validar_plan_ciclo(plan) == []
    assert plan['familias'] == ['transformer'] and plan['workspace_id'] == 'espacio-prueba'
    assert Path(plan['fuentes']['dataset']) == (almacen / 'dataset').resolve()
    assert plan['datasets']['dataset'] == ac.huella_fuente(almacen / 'dataset')
    assert plan['raiz'] == str((almacen / 'aprendizaje').resolve())


def test_la_matriz_del_plan_tiene_las_siete_familias_con_su_motivo(tmp_path):
    """050:RF-34 — la matriz declara por familia estado, huella, contexto, recursos y por qué se bloquea."""
    almacen = _almacen(tmp_path)
    rc, informe = _preparar_plan(tmp_path, almacen, *COMPLETO)
    assert rc == 0, informe
    plan = json.loads((tmp_path / 'plan' / 'plan.json').read_text(encoding='utf-8'))
    matriz = plan['matriz']
    assert set(matriz) == set(SIETE)
    fila = matriz['transformer']
    assert fila['estado'] == 'listo_para_preflight' and fila['en_plan'] is True and fila['motivos'] == []
    assert fila['fuentes']['dataset'] == plan['datasets']['dataset']['huella']
    assert fila['referencias'] >= 1 and fila['contexto_hash'] and fila['recursos'] == {
        'tiempo_s': 60.0, 'memoria_gib': 1.0, 'usa_gpu': True}
    assert matriz['pinn']['estado'] == 'bloqueado_por_datos' and matriz['pinn']['en_plan'] is False
    assert any('twin' in m for m in matriz['pinn']['motivos'])
    assert any('informe' in m for m in matriz['clasificador']['motivos'])
    assert plan['puertas'] == {'transformer': ['preflight', 'retencion_por_contexto', 'reapertura',
                                               'evaluacion_conjunta']}


def test_sin_espacio_ni_presupuesto_no_hay_plan_y_se_dice_que_falta(tmp_path):
    """050:RF-33 — lo que el operador no declaró se nombra con su opción, y no se escribe ningún plan."""
    almacen = _almacen(tmp_path)
    rc, informe = _preparar_plan(tmp_path, almacen, '--familias', 'transformer')
    assert rc == 2 and informe is not None
    assert informe['plan_escrito'] is None and not (tmp_path / 'plan' / 'plan.json').exists()
    texto = ' '.join(informe['faltan'])
    for opcion in ('--workspace-id', '--tiempo-s', '--memoria-gib'):
        assert opcion in texto


def test_familia_pedida_sin_su_fuente_bloquea_el_plan_con_su_motivo(tmp_path):
    """050:RF-33, RF-34 — pedir la PINN sin búfer del gemelo no da un plan; se dice la familia y la fuente."""
    almacen = _almacen(tmp_path)
    rc, informe = _preparar_plan(tmp_path, almacen, '--workspace-id', 'e', '--familias', 'transformer,pinn',
                                 '--tiempo-s', '60', '--memoria-gib', '1')
    assert rc == 2 and informe is not None and not (tmp_path / 'plan' / 'plan.json').exists()
    motivos = [m for m in informe['faltan'] if m.startswith('pinn:')]
    assert motivos and any('twin' in m for m in motivos)
    assert not any(m.startswith('transformer:') for m in informe['faltan'])


def test_dataset_v1_del_almacen_se_explica_y_no_se_elige_otro(tmp_path):
    """050:RF-32, RF-33 (D02) — el dataset por defecto de otro esquema bloquea sus familias; la versión v2
    que haya al lado se nombra, pero no entra sin declararla."""
    almacen = _almacen(tmp_path, dataset=False)
    v1 = almacen / 'dataset'
    v1.mkdir()
    (v1 / 'manifest.json').write_text(json.dumps({'schema': 'igea-dgs-training-dataset-v1'}), encoding='utf-8')  # legado-058: el esquema con el nombre anterior se rechaza
    _dataset(almacen / 'otra', _orden())
    (almacen / 'otra' / 'dataset').rename(almacen / 'dataset_v5')
    rc, informe = _preparar_plan(tmp_path, almacen, *COMPLETO)
    assert rc == 2 and informe is not None and not (tmp_path / 'plan' / 'plan.json').exists()
    motivos = ' '.join(informe['matriz']['transformer']['motivos'])
    assert 'igea-dgs-training-dataset-v1' in motivos and 'dataset_v5' in motivos  # legado-058: el esquema con el nombre anterior se rechaza
    assert 'dataset' not in informe['plan']['fuentes']


def test_validador_detecta_dataset_cambiado_puerta_quitada_y_familia_bloqueada(tmp_path):
    """050:RF-33 — el validador da la lista entera: huella que ya no coincide, puerta quitada y familia
    bloqueada en la matriz."""
    almacen = _almacen(tmp_path)
    rc, _ = _preparar_plan(tmp_path, almacen, *COMPLETO)
    assert rc == 0
    ruta = tmp_path / 'plan' / 'plan.json'
    plan = json.loads(ruta.read_text(encoding='utf-8'))
    plan['puertas']['transformer'].remove('reapertura')
    plan['familias'].append('pinn')
    with (almacen / 'dataset' / 'train.jsonl').open('a', encoding='utf-8') as f:
        f.write('\n')
    faltan = ac.validar_plan_ciclo(plan, base=ruta.parent)
    texto = ' '.join(faltan)
    assert 'cambió' in texto and 'reapertura' in texto
    assert any(m.startswith('pinn:') and 'bloqueada' in m for m in faltan)
    assert len(faltan) >= 3


def test_cargar_plan_admite_la_matriz_y_sigue_rechazando_ordenes(tmp_path):
    """050:RF-4, RF-32 — el cargador de la cola acepta los tres campos de la matriz juntos, con su forma, y sigue
    rechazando un comando, un campo suelto de la matriz o una matriz mal formada."""
    from test_aprendizaje_cola import _plan
    ruta = _plan(tmp_path)
    base = json.loads(ruta.read_text(encoding='utf-8'))
    extension = {'datasets': {'dataset': {'huella': 'c' * 64, 'ficheros': 1}},
                 'puertas': {'transformer': ['preflight', 'retencion_por_contexto', 'reapertura',
                                             'evaluacion_conjunta']},
                 'matriz': {'transformer': {'estado': 'listo_para_preflight', 'motivos': []}}}
    ruta.write_text(json.dumps({**base, **extension}), encoding='utf-8')
    try:
        cargado = ac.cargar_plan_ciclo(ruta)
    except ac.CicloBloqueado as exc:
        cargado = {'rechazado': str(exc)}
    assert (cargado.get('matriz') or {}).get('transformer', {}).get('estado') == 'listo_para_preflight', cargado
    for malo in ({**base, **extension, 'comando': 'entrenar.py'}, {**base, 'matriz': extension['matriz']},
                 {**base, **extension, 'matriz': {'transformer': {'estado': 'preparado', 'motivos': []}}}):
        ruta.write_text(json.dumps(malo), encoding='utf-8')
        with pytest.raises(ac.CicloBloqueado):
            ac.cargar_plan_ciclo(ruta)


def test_la_cola_no_congela_un_plan_cuyo_dataset_cambio(tmp_path, monkeypatch):
    """050:RF-33, RF-8 — la entrada ``plan`` de la vigilancia revalida las huellas: un dataset tocado después
    de preparar el plan queda bloqueado con su motivo y no llega a congelarse."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente_cola'))
    almacen = _almacen(tmp_path)
    rc, _ = _preparar_plan(tmp_path, almacen, *COMPLETO)
    assert rc == 0
    ruta = tmp_path / 'plan' / 'plan.json'
    cli = cargar_herramienta('aprendizaje_continuo.py')
    congeladas = []
    monkeypatch.setattr(ac, 'congelar_instantanea', lambda *a, **kw: congeladas.append(a) or {})
    with (almacen / 'dataset' / 'train.jsonl').open('a', encoding='utf-8') as f:
        f.write('\n')
    plan_hash = ac.cargar_plan_ciclo(ruta)['plan_hash']
    with contextlib.redirect_stdout(io.StringIO()):
        assert cli.main(['plan', '--archivo', str(ruta), '--plan-hash', plan_hash, '--solo-preparar']) == 2
    assert congeladas == []
    bloqueos = ac.estado_aprendizaje(tmp_path / 'asistente_cola' / 'aprendizaje')['bloqueos']
    assert 'cambió' in bloqueos[-1]['motivos'][0]
