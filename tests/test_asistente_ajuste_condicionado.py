"""047:RF-8 / 047:RF-9 — ajustar el LLM exige el incumplimiento medido con órdenes reales independientes."""
from __future__ import annotations

import pytest

from convertersmartgrid.asistente.ajuste_condicionado import decidir_ajuste, evaluar_puertas_reales


def metricas(acierto=.99, f1=.97, ejemplos=200, **extra):
    return {'acierto_tarea': acierto, 'f1_datos': f1, 'ejemplos': ejemplos, **extra}


def manifiesto(reales=200, **extra):
    return {'calidades': {'gold_human': reales}, 'ordenes_reales_distintas': reales, 'sin_fuga': True,
            'dataset_hash': 'a' * 64, **extra}


def test_qlora_sin_gold_real_bloquea():
    """047:RF-8 — el caso límite de la spec: 200 sintéticos no habilitan decidir la suficiencia real."""
    d = decidir_ajuste(metricas(acierto=.5, f1=.5),
                       {'calidades': {'silver_teacher_verified': 200}, 'ordenes_reales_distintas': 200,
                        'sin_fuga': True, 'dataset_hash': 'a' * 64})
    assert d['decision'] == 'bloqueada'
    assert any('silver_teacher_verified' in m for m in d['motivos'])
    assert d['entrenado'] is False and d['promovido'] is False


def test_baseline_cumple_no_entrena():
    """047:RF-8 — evidencia suficiente y puertas cumplidas: no_necesaria, sin fingir un entrenamiento."""
    d = decidir_ajuste(metricas(), manifiesto())
    assert d['decision'] == 'no_necesaria' and d['evidencia']['aprobada'] and d['entrenado'] is False


@pytest.mark.parametrize('acierto,f1,causa', [(.97, .97, 'acierto'), (.99, .94, 'F1'), (.5, .5, 'acierto')])
def test_incumplimiento_medido_lo_hace_necesario(acierto, f1, causa):
    """047:RF-8 — solo aquí se justifica ajustar, y se dice qué puerta no se cumplió."""
    d = decidir_ajuste(metricas(acierto=acierto, f1=f1), manifiesto())
    assert d['decision'] == 'necesaria' and any(causa in m for m in d['motivos'])
    assert d['entrenado'] is False


@pytest.mark.parametrize('m,manif,frase', [
    (metricas(ejemplos=199), manifiesto(reales=199), '199 órdenes reales'),
    (metricas(ejemplos=3), manifiesto(reales=3), '3 órdenes reales'),
    (metricas(), manifiesto(sin_fuga=False), 'fuera del entrenamiento'),
    (metricas(), manifiesto(sin_fuga=None), 'fuera del entrenamiento'),
    (metricas(), manifiesto(dataset_hash=None), 'huella'),
    (metricas(ejemplos=150), manifiesto(), 'no se midieron'),
    (metricas(acierto=float('nan')), manifiesto(), 'no válidas'),
    (metricas(f1=True), manifiesto(), 'no válidas'),
    (metricas(acierto=1.2), manifiesto(), 'no válidas'),
    ({}, {}, 'órdenes reales'),
])
def test_sin_evidencia_suficiente_se_bloquea_aunque_las_cifras_digan_otra_cosa(m, manif, frase):
    """047:RF-9 — 027:RF-34: sin independencia o sin 200 no hay veredicto, ni bueno ni malo."""
    d = decidir_ajuste(m, manif)
    assert d['decision'] == 'bloqueada' and any(frase in x for x in d['motivos'])
    assert d['evidencia']['aprobada'] is False


def test_mezclar_propuestas_con_reales_no_las_vuelve_reales():
    """047:RF-9 — 201 ejemplos con 200 de oro y uno del maestro: se mide solo con las reales o no vale."""
    p = evaluar_puertas_reales(metricas(ejemplos=201), manifiesto(calidades={'gold_human': 200, 'silver_teacher_verified': 1}))
    assert not p['suficiente'] and not p['aprobada']


def test_las_puertas_son_las_de_027_y_no_se_copian():
    """047:RF-9 — 027:RF-18 en un solo sitio: si alguien las cambia, aquí se ven; y siguen en 0,98 y 0,95."""
    from convertersmartgrid.asistente.transformer import Puertas
    from convertersmartgrid.digital_twin.auditoria import Umbrales
    p = evaluar_puertas_reales(metricas(), manifiesto())
    assert p['puertas'] == {'acierto_tarea': Puertas().acierto_real, 'f1_datos': Puertas().f1_real}
    assert (Puertas().acierto_real, Puertas().f1_real) == (.98, .95)
    assert p['minimo'] == Umbrales().min_ordenes_reales == 200


def _propuestas():
    """Un informe de las 200 que aprueba todas sus puertas: lo real se decide aparte."""
    from convertersmartgrid.asistente.tareas import TAREAS
    nombres = sorted(TAREAS)
    casos = [{'record_id': f'{i:064x}', 'esperado': nombres[i % len(nombres)], 'obtenido': nombres[i % len(nombres)],
              'correcto': True, 'confirmacion': True, 'vp': 1, 'fp': 0, 'fn': 0} for i in range(200)]
    familias = {t: {'ejemplos': sum(c['esperado'] == t for c in casos), 'acierto_tarea': 1., 'f1_datos': 1.} for t in nombres}
    return {'ejemplos': 200, 'unicos': 200, 'tareas': len(nombres), 'acierto_tarea': 1., 'f1_datos': 1., 'familias': familias,
            'casos': casos, 'confirmaciones_conservadas': True, 'sin_fuga': True}


def test_la_aceptacion_publica_las_puertas_reales_y_no_presta_las_propuestas():
    """047:RF-9 / 047:RF-17 — las 200 aprueban la asistida y, con pocas humanas, lo real sigue bloqueado."""
    from convertersmartgrid.asistente.aceptacion import decidir_aceptacion
    r = decidir_aceptacion(_propuestas(), {'ejemplos': 3, 'unicos': 3, 'acierto_tarea': 1., 'f1_datos': 1.})
    assert r['asistida']['aprobada'] is True
    assert r['puertas_reales']['aprobada'] is False and r['puertas_reales']['ordenes_reales'] == 3
    assert r['ajuste']['decision'] == 'bloqueada'
    assert r['integral'] is False and r['autonoma']['aprobada'] is False


def test_con_200_humanas_independientes_decide_el_incumplimiento():
    """047:RF-8 / 047:RF-9 — el informe humano real, sellado y sin fuga, llega a una decisión por sus cifras."""
    from convertersmartgrid.asistente.aceptacion import decidir_aceptacion
    humanas = {'ejemplos': 200, 'unicos': 200, 'acierto_tarea': .9, 'f1_datos': .97, 'sin_fuga': True, 'dataset_hash': 'b' * 64}
    r = decidir_aceptacion(_propuestas(), humanas)
    assert r['ajuste']['decision'] == 'necesaria' and r['puertas_reales']['suficiente']
    assert r['integral'] is False
