"""Spec 049, T3: coordinación, sensibilidad, poder de corte y reporte sobre los tiempos de DIgSILENT.

Los resultados imitan el informe de ``tools/protecciones_pf.py``; tiempos, corrientes y criterios
sorteados con semilla, sin valores de una empresa.
"""

from __future__ import annotations

import random

import pytest

from convertersmartgrid import protecciones as pr

SEMILLAS = [random.randrange(10**6) for _ in range(4)]


def _caso(rng, *, cti=None):
    """Un relé que respalda a N fusibles y una falla por fusible en que todo coordina."""
    criterios = {'cti_s': cti or round(rng.uniform(0.2, 0.4), 2), 'factor_sensibilidad': round(rng.uniform(1.5, 2.5), 2),
                 'margen_poder_corte': round(rng.uniform(1.0, 1.3), 2)}
    n = rng.randint(1, 6)
    fusibles = [f'FU{i}' for i in range(n)]
    dispositivos = [{'id': 'R1', 'clase': 'rele', 'arranque': 100.0, 'unidad_arranque': 'A', 'poder_corte_ka': 25.0,
                     'respalda_a': fusibles}]
    dispositivos += [{'id': f, 'clase': 'fusible', 'arranque': 10.0, 'unidad_arranque': 'A', 'poder_corte_ka': 10.0}
                     for f in fusibles]
    resultados = []
    for f in fusibles:
        i = rng.uniform(1000, 5000)                   # bien por encima de los arranques
        tp = round(rng.uniform(0.01, 0.2), 3)
        tr = round(tp + criterios['cti_s'] + rng.uniform(0.01, 0.5), 3)
        resultados.append({'id': f'falla_{f}', 'tipo': 'trifasica', 'ubicacion': f'B_{f}', 'estado': 'evaluada',
                           'protegen': [f], 'dispositivos': [
                               {'id': f, 'tiempo_s': tp, 'corriente_a': i, 'estado': 'disparo'},
                               {'id': 'R1', 'tiempo_s': tr, 'corriente_a': i, 'estado': 'arranco'}]})
    return {'dispositivos': dispositivos}, resultados, {'protecciones': criterios}


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_todo_coordinado_cumple(semilla):
    """049:RF-5, 049:RF-6, 049:RF-7 — con cada falla evaluada, márgenes sobre el CTI, sensibilidad
    y poder de corte suficientes, el estudio cumple y lista tiempos y márgenes."""
    rng = random.Random(semilla)
    inventario, resultados, perfil = _caso(rng)
    e = pr.evaluar_coordinacion(resultados, inventario, perfil)
    assert e['estado'] == pr.CUMPLE, e
    assert e['violaciones'] == [] and e['no_evaluados'] == []
    assert len(e['margenes']) == len(resultados)
    assert all(m['margen_s'] >= perfil['protecciones']['cti_s'] for m in e['margenes'])
    assert e['cobertura'] == {'fallas': len(resultados), 'evaluadas': len(resultados)}
    assert pr.AVISO_SELECTIVIDAD == e['aviso']


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_cti_incumplido_rechaza(semilla):
    """049:RF-5 — un respaldo que llega antes del CTI no pasa, aunque el flujo converja y las
    demás fallas coordinen."""
    rng = random.Random(semilla)
    inventario, resultados, perfil = _caso(rng)
    victima = rng.choice(resultados)
    tp = victima['dispositivos'][0]['tiempo_s']
    victima['dispositivos'][1]['tiempo_s'] = round(tp + perfil['protecciones']['cti_s'] * rng.uniform(0.1, 0.9), 4)
    e = pr.evaluar_coordinacion(resultados, inventario, perfil)
    assert e['estado'] == pr.NO_CUMPLE
    malas = [v for v in e['violaciones'] if v['tipo'] == 'cti']
    assert [v['falla'] for v in malas] == [victima['id']]
    assert malas[0]['valor'] < malas[0]['limite'] == perfil['protecciones']['cti_s']
    # Un respaldo que no arranca tampoco respalda.
    victima['dispositivos'][1]['tiempo_s'] = None
    e = pr.evaluar_coordinacion(resultados, inventario, perfil)
    assert any(v['tipo'] == 'sin_respaldo' and v['falla'] == victima['id'] for v in e['violaciones'])


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_falla_no_evaluada_no_aprueba(semilla):
    """049:RF-7 — una falla que DIgSILENT no evaluó deja el estudio parcial, nunca «cumple»; sin
    ninguna evaluada, bloqueado. Se distinguen evaluadas, no cubiertas e incumplidas."""
    rng = random.Random(semilla)
    inventario, resultados, perfil = _caso(rng)
    resultados.append({'id': 'falla_sin', 'tipo': 'monofasica', 'ubicacion': 'B_X', 'estado': 'no_evaluada',
                       'motivo': 'la barra B_X no está en la red del caso'})
    e = pr.evaluar_coordinacion(resultados, inventario, perfil)
    assert e['estado'] == pr.PARCIAL
    assert any(n['que'] == 'falla falla_sin' and 'B_X' in n['razon'] for n in e['no_evaluados'])
    assert e['cobertura'] == {'fallas': len(resultados), 'evaluadas': len(resultados) - 1}
    solo = pr.evaluar_coordinacion(resultados[-1:], inventario, perfil)
    assert solo['estado'] == pr.BLOQUEADO
    # Sin CTI en el perfil: la coordinación no se juzga y se dice, nunca se aprueba.
    del perfil['protecciones']['cti_s']
    e = pr.evaluar_coordinacion(resultados[:-1], inventario, perfil)
    assert e['estado'] == pr.PARCIAL and any('protecciones.cti_s' in n['razon'] for n in e['no_evaluados'])


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_poder_corte_insuficiente_rechaza(semilla):
    """049:RF-6 — un dispositivo cuya mayor corriente vista, por el margen del perfil, supera su
    poder de corte se rechaza; uno sin corriente dada por DIgSILENT queda no evaluado."""
    rng = random.Random(semilla)
    inventario, resultados, perfil = _caso(rng)
    fusible = rng.choice(inventario['dispositivos'][1:])
    i_max = max(d['corriente_a'] for r in resultados for d in r['dispositivos'] if d['id'] == fusible['id'])
    fusible['poder_corte_ka'] = round(i_max / 1000 * rng.uniform(0.3, 0.95), 3)
    e = pr.evaluar_coordinacion(resultados, inventario, perfil)
    assert e['estado'] == pr.NO_CUMPLE
    assert [v['dispositivo'] for v in e['violaciones'] if v['tipo'] == 'poder_corte'] == [fusible['id']]
    for r in resultados:
        for d in r['dispositivos']:
            d['corriente_a'] = None
    e = pr.evaluar_coordinacion(resultados, inventario, perfil)
    assert e['estado'] == pr.PARCIAL
    assert any(n['que'] == f"poder de corte de {fusible['id']}" for n in e['no_evaluados'])


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_sensibilidad_con_la_relacion_del_tc(semilla):
    """049:RF-6 — la sensibilidad compara la corriente vista con el arranque en amperios
    primarios: un arranque en secundarios se lleva con la relación del TC."""
    rng = random.Random(semilla)
    inventario, resultados, perfil = _caso(rng)
    rele = inventario['dispositivos'][0]
    prim, sec = rng.choice([200, 400, 600]), rng.choice([1, 5])
    rele.update(unidad_arranque='A sec', arranque=2.0, ct_primario_a=prim, ct_secundario_a=sec)
    assert pr.arranque_primario_a(rele) == pytest.approx(2.0 * prim / sec)
    r = resultados[0]
    r['protegen'] = ['R1']
    fs = perfil['protecciones']['factor_sensibilidad']
    r['dispositivos'][1]['corriente_a'] = pr.arranque_primario_a(rele) * fs * rng.uniform(0.3, 0.9)
    e = pr.evaluar_coordinacion(resultados, inventario, perfil)
    assert any(v['tipo'] == 'sensibilidad' and v['dispositivo'] == 'R1' for v in e['violaciones'])
    r['dispositivos'][1]['corriente_a'] = pr.arranque_primario_a(rele) * fs * rng.uniform(1.1, 3)
    e = pr.evaluar_coordinacion(resultados, inventario, perfil)
    assert not any(v['tipo'] == 'sensibilidad' for v in e['violaciones'])


def test_reporte_determinista_y_comparacion_entre_casos(tmp_path):
    """049:RF-7 — el JSON y los CSV salen iguales para la misma evaluación; la comparación
    «Sin proyecto» / «Con proyecto» solo entre contextos compatibles."""
    rng = random.Random(17)
    inventario, resultados, perfil = _caso(rng)
    e = pr.evaluar_coordinacion(resultados, inventario, perfil)
    a = pr.escribir_reporte(e, tmp_path / 'a', 'protecciones')
    b = pr.escribir_reporte(e, tmp_path / 'b', 'protecciones')
    assert set(a) == {'json', 'tiempos', 'margenes', 'violaciones'}
    for k in a:
        assert open(a[k], 'rb').read() == open(b[k], 'rb').read()
    contexto = {'project': 'P', 'feeders': ['F1'], 'source_fingerprint': 'x', 'source_mode': 'txt', 'year': 2026,
                'period': '2026-07', 'profile_hash': 'h'}
    sin = {**e, 'contexto': {**contexto, 'case_role': 'sin_proyecto'}}
    victima = resultados[0]
    victima['dispositivos'][1]['tiempo_s'] = victima['dispositivos'][0]['tiempo_s']
    con = {**pr.evaluar_coordinacion(resultados, inventario, perfil), 'contexto': {**contexto, 'case_role': 'con_proyecto'}}
    d = pr.comparar_casos(sin, con)
    assert d['nuevas'] == [('cti', victima['id'], 'R1')] and d['resueltas'] == []
    with pytest.raises(pr.ProteccionesError, match='year'):
        pr.comparar_casos(sin, {**con, 'contexto': {**con['contexto'], 'year': 2025}})
    with pytest.raises(pr.ProteccionesError, match='Con proyecto'):
        pr.comparar_casos(sin, sin)
