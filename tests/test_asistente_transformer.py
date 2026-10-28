"""Spec 026, T3: el Transformer propio que entiende las órdenes."""
from __future__ import annotations

import os

import pytest

torch = pytest.importorskip('torch')

from igea_dgs.asistente import almacen
from igea_dgs.asistente import transformer as tr
from igea_dgs.asistente.sinteticos import generar

VOCAB = {'alimentadores': ['IN111', 'TA225', 'PA217', 'CA101', 'NA203'],
         'proyecto': ['20261015-170359_IGEA_IN111_TA225', 'CA101 13'], 'sistema': ['Pisco', 'Ica', 'Nasca']}
#: La de verdad: con 70 frases y 14 épocas la tarea se acierta pero los datos no (F1 0,49).
CFG = tr.Configuracion()
#: Para el candidato que debe rechazarse: basta con que exista.
CFG_RAPIDO = tr.Configuracion(epocas=2, por_tarea=20)


@pytest.fixture(scope='module')
def entrenado(tmp_path_factory):
    raiz = tmp_path_factory.mktemp('asistente')
    os.environ['IGEA_ASISTENTE_DATA'] = str(raiz)
    try:
        r = tr.entrenar_y_promover(VOCAB, cfg=CFG, puertas=tr.Puertas(acierto_tarea=0.9, f1_datos=0.8,
                                                                       acierto_real=0.0, f1_real=0.0))
        yield raiz, r
    finally:
        os.environ.pop('IGEA_ASISTENTE_DATA', None)


def test_aprende_la_tarea_y_los_datos(entrenado, monkeypatch):
    """026:RF-2 — en frases que no vio, reconoce la tarea y marca sus datos (alimentadores,
    proyecto, sistema, periodo), también con erratas."""
    raiz, r = entrenado
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(raiz))
    assert r['promovido'] and r['acierto_tarea'] >= 0.9 and r['f1_datos'] >= 0.8, r
    m = tr.cargar()
    p = m.predecir('complata la conversion de IN111 y TA225')
    assert p['tarea'] == 'convertir'
    assert 'IN111' in p['datos']['alimentadores'][0]['valor']
    p = m.predecir('calibra el sistema pisco con julio de 2026')
    assert p['tarea'] == 'sistema_completo' and p['datos']['sistema'][0]['valor'].lower() == 'pisco'


def test_reentrena_con_ordenes_reales_y_prueba_fija(entrenado, monkeypatch):
    """026:RF-19 / 026:RF-20 — las órdenes confirmadas o corregidas entran al entrenamiento
    (una de cada cinco a la prueba fija); el candidato se registra y solo sustituye al modelo
    en uso si pasa las puertas, y se puede volver al anterior."""
    raiz, r = entrenado
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(raiz))
    for i in range(10):
        almacen.anotar('ejemplos', {'texto': f'genera el dgs de PA217 vez {i}', 'tarea': 'convertir',
                                    'datos': [[15, 20, 'alimentadores']], 'origen': 'corregido'})
    ent, prueba = tr.ejemplos_reales()
    assert len(ent) == 8 and len(prueba) == 2
    r2 = tr.entrenar_y_promover(VOCAB, cfg=CFG_RAPIDO, puertas=tr.Puertas(acierto_tarea=1.01, acierto_real=0.0, f1_real=0.0))
    assert not r2['promovido'] and r2['fallos'] and tr.version_promovida() == r['version']
    tr.promover(r2['version'], 'prueba')
    assert tr.volver_al_anterior() == r['version'] and tr.version_promovida() == r['version']
    historial = (raiz / 'modelos' / 'ordenes' / 'historial.jsonl').read_text(encoding='utf-8')
    assert historial.count('\n') >= 3


def test_evaluar_en_la_prueba_fija(entrenado, monkeypatch):
    """026:RF-20 — la prueba fija se genera con su semilla y es la misma para todos."""
    raiz, _r = entrenado
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(raiz))
    prueba = generar(VOCAB, por_tarea=8, semilla=tr.SEMILLA_PRUEBA)
    assert [e.texto for e in prueba] == [e.texto for e in generar(VOCAB, por_tarea=8, semilla=tr.SEMILLA_PRUEBA)]
    m = tr.evaluar(tr.cargar(), prueba)
    assert 0 <= m['f1_datos'] <= 1 and m['acierto_tarea'] >= 0.8


def test_puertas_de_las_ordenes_reales(entrenado, monkeypatch):
    """027:RF-18 — con órdenes reales en la prueba fija, el candidato se promueve solo con
    acierto ≥ 0,98 y F1 ≥ 0,95 en ellas, medidas aparte."""
    raiz, _r = entrenado
    monkeypatch.setenv('IGEA_ASISTENTE_DATA', str(raiz))
    r = tr.entrenar_y_promover(VOCAB, cfg=CFG_RAPIDO, puertas=tr.Puertas(acierto_tarea=0.0, f1_datos=0.0,
                                                                        acierto_real=1.01))
    assert r['reales'] is not None and r['reales']['ejemplos'] >= 1
    assert not r['promovido'] and any('órdenes reales' in f for f in r['fallos'])
