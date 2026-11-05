"""087:RF-14 a RF-16 — cuándo construir cada obra, con casos resueltos a mano."""
from __future__ import annotations

import math

import pytest

from convertersmartgrid import planeamiento_etapas as pe

UNA = [{'nombre': 'media', 'tasa': 0.05, 'probabilidad': 1.0}]


def test_el_anio_limite():
    """087:RF-14 — 0 si ya no cumple; el primer año en que la demanda pasa del margen; ninguno si no crece."""
    assert pe.anio_limite(0.0, 0.05) == 0 and pe.anio_limite(None, 0.05) == 0
    margen = 1.05 ** 2 + 0.01 - 1
    assert pe.anio_limite(margen, 0.05) == 3
    assert pe.anio_limite(0.2, 0.0) is None


def test_el_arbol_sin_margen_construye_ahora():
    """087:RF-14 — la que ya no cumple no se difiere, aunque esperar saliera más barato."""
    r = pe.arbol_de_decision('O', 100.0, 0.0, pe.escenarios_de_demanda(0.04), 10, 0.1)
    assert r['decision'] == 'construir_ahora' and r['ahorro_esperado'] == 0


def test_el_arbol_con_margen_difiere_y_da_el_valor_esperado():
    """087:RF-14 — a mano: tres años de margen a tasa fija, costo 100, descuento 10 %, horizonte 5: años 3 y 4."""
    margen = 1.05 ** 2 + 0.01 - 1
    r = pe.arbol_de_decision('O', 100.0, margen, UNA, 5, 0.1)
    esperado = 100.0 / 1.1 ** 3 + 100.0 / 1.1 ** 4
    assert r['decision'] == 'diferir' and r['valor_esperado_diferir'] == pytest.approx(esperado, abs=0.01)
    assert r['valor_ahora'] == pytest.approx(sum(100.0 / 1.1 ** t for t in range(5)), abs=0.01)
    assert r['ramas'][0]['anio_de_construccion'] == 3


def test_los_escenarios_suman_uno_y_alta_llega_antes():
    """087:RF-14, 087:RF-16 — baja, media y alta; el resultado dice cada rama y su tasa."""
    esc = pe.escenarios_de_demanda(0.04)
    assert [e['nombre'] for e in esc] == ['baja', 'media', 'alta'] and sum(e['probabilidad'] for e in esc) == pytest.approx(1.0)
    r = pe.arbol_de_decision('O', 100.0, 0.1, esc, 20, 0.1)
    anios = {x['escenario']: x['anio_de_construccion'] for x in r['ramas']}
    assert anios['alta'] < anios['media'] < anios['baja'] and all(x['tasa'] > 0 for x in r['ramas'])


def test_el_proceso_coincide_con_el_caso_a_mano():
    """087:RF-15 — con un solo escenario, sin azar: construye justo el año en que se pasa del margen, con su valor."""
    margen = 1.05 ** 2 + 0.01 - 1
    r = pe.proceso_de_decision('O', 100.0, margen, UNA, 5, 0.1)
    assert r['anio_esperado'] == pytest.approx(3.0) and r['probabilidad_por_anio'][3] == 1.0 and r['probabilidad_sin_construir'] == 0
    assert r['valor'] == pytest.approx(100.0 / 1.1 ** 3 + 100.0 / 1.1 ** 4, abs=0.01)


def test_el_proceso_sin_margen_y_sin_crecer():
    """087:RF-15 — sin margen, el año 0; sin crecimiento dentro del horizonte, no se construye."""
    assert pe.proceso_de_decision('O', 100.0, 0.0, UNA, 5, 0.1)['anio_esperado'] == 0
    r = pe.proceso_de_decision('O', 100.0, 0.5, [{'nombre': 'plana', 'tasa': 0.0, 'probabilidad': 1.0}], 5, 0.1)
    assert r['anio_esperado'] is None and r['probabilidad_sin_construir'] == 1.0 and r['valor'] == 0


def test_el_proceso_dice_su_cadena_y_reparte_la_probabilidad():
    """087:RF-15, 087:RF-16 — la matriz suma 1 por fila; el régimen alto adelanta la obra; es reproducible."""
    esc = pe.escenarios_de_demanda(0.04)
    r = pe.proceso_de_decision('O', 100.0, 0.1, esc, 20, 0.1)
    assert all(sum(f) == pytest.approx(1.0) for f in r['transicion']) and r['escenarios'] == esc
    assert sum(r['probabilidad_por_anio']) + r['probabilidad_sin_construir'] == pytest.approx(1.0, abs=1e-3)
    assert 0 < r['anio_esperado'] < 20 and r == pe.proceso_de_decision('O', 100.0, 0.1, esc, 20, 0.1)
    assert math.isclose(r['persistencia'], pe.PERSISTENCIA)


def test_el_plan_por_etapas_de_varias_obras():
    """087:RF-14, 087:RF-15 — el árbol y el proceso de cada obra; la que no tiene costo no entra."""
    plan = pe.plan_por_etapas([{'alimentador': 'F1', 'nombre': 'a', 'costo_anual': 10.0, 'margen': 0.0},
                               {'alimentador': 'F2', 'nombre': 'b', 'costo_anual': None, 'margen': 0.2}], 0.04, 10, 0.1)
    assert [x['alimentador'] for x in plan] == ['F1'] and plan[0]['arbol']['decision'] == 'construir_ahora'
    assert plan[0]['proceso']['anio_esperado'] == 0
