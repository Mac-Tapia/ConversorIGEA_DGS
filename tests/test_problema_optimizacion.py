"""Spec 048, T1: problema mixto declarado, evaluación con la demanda atendida y caché con contexto.

El optimizador solo puede comparar soluciones que la red admite: un banco de 1,4 módulos o un
equipo que no está en el catálogo no existen, y una maniobra que deja carga sin fuente «pierde
menos» solo porque ya no la alimenta. Las redes son sintéticas y su tamaño se sortea.
"""
from __future__ import annotations

import random
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip('scipy')

from apoyo import contrato_fisico

from convertersmartgrid.digital_twin import evolutivo as ev
from convertersmartgrid.digital_twin import oraculo as orc
from convertersmartgrid.digital_twin import problema_optimizacion as po
from convertersmartgrid.experimentos import ContextoExperimento

POLITICA = 'f' * 64
NORMA = {'tension_min_pu': 0.95, 'tension_max_pu': 1.05}


def contexto_de(**cambios) -> ContextoExperimento:
    base = {'source_run_id': 'r1', 'source_mode': 'txt', 'source_fingerprint': 'a' * 64, 'project': 'P',
            'feeders': ('A1',), 'case_id': 'caso-con', 'case_role': 'con_proyecto', 'year': 2026,
            'period': '2026-07', 'criterio_fijas': 'coincidente', 'profile_hash': 'b' * 64,
            'topology_hash': 'c' * 64, 'controls_hash': 'd' * 64, 'scenario_hash': 'e' * 64}
    return ContextoExperimento(**{**base, **cambios})


def evaluador_lineal(vector):
    """Un evaluador de juguete: pérdidas que bajan con los módulos, demanda siempre atendida."""
    k = vector['bancos']
    return {'convergio': True, 'objetivos': {'perdidas_kw': 10.0 - k}, 'violaciones': {'tension_pu': 0.0},
            'demanda_referencia_kw': 100.0, 'demanda_atendida_kw': 100.0}


def problema_de(evaluador=evaluador_lineal, contexto=None, modelo_id='oraculo@1', coste=40.0, **cambios):
    variables = (
        po.Variable('bancos', 'entera', 'módulos de 300 kvar', inferior=0, superior=3,
                    origen='perfil: bancos fijos por tensión', coste=coste,
                    origen_coste='libro CAPEX del perfil' if coste is not None else None),
        po.Variable('conductor', 'categorica', 'tipo de línea', catalogo=('AAAC70', 'AAAC120'),
                    origen='catálogo de fichas del proyecto',
                    coste={'AAAC70': 0.0, 'AAAC120': 25.0} if coste is not None else None,
                    origen_coste='libro CAPEX del perfil' if coste is not None else None),
        # Una consigna no es una obra: su coste cero se declara con su motivo, no se supone.
        po.Variable('consigna', 'continua', 'p.u.', inferior=0.95, superior=1.05, origen='perfil: banda de cabecera',
                    coste=0.0, origen_coste='consigna de operación, sin inversión'),
    )
    base = dict(nombre='prueba', variables=variables,
                restricciones=(po.Restriccion('tension_pu', 'p.u.', 'banda de tensión de la norma'),),
                objetivos=(po.Objetivo('inversion', 'coste del perfil', origen='coste'),
                           po.Objetivo('perdidas_kw', 'kW')),
                contexto=contexto or contexto_de(), modelo_id=modelo_id, evaluador=evaluador)
    return po.ProblemaOptimizacion(**{**base, **cambios})


VECTOR = {'bancos': 2, 'conductor': 'AAAC70', 'consigna': 1.0}


# ------------------------------------------------------------------ RF-1: dominio declarado
def test_cada_variable_declara_dominio_unidad_y_origen():
    """048:RF-1 — una variable sin unidad, sin origen o con un tipo desconocido no se acepta."""
    p = problema_de()
    declaracion = p.declaracion()
    assert [v['nombre'] for v in declaracion['variables']] == ['bancos', 'conductor', 'consigna']
    assert all(v['unidad'] and v['origen'] for v in declaracion['variables'])
    assert declaracion['variables'][0] | {'tipo': 'entera', 'inferior': 0, 'superior': 3} == declaracion['variables'][0]
    assert declaracion['restricciones'] == [{'nombre': 'tension_pu', 'unidad': 'p.u.',
                                             'descripcion': 'banda de tensión de la norma'}]
    with pytest.raises(ValueError, match='unidad'):
        po.Variable('x', 'entera', '', inferior=0, superior=1, origen='perfil')
    with pytest.raises(ValueError, match='origen'):
        po.Variable('x', 'entera', 'módulos', inferior=0, superior=1, origen='')
    with pytest.raises(ValueError, match='tipo'):
        po.Variable('x', 'decimal', 'módulos', inferior=0, superior=1, origen='perfil')
    with pytest.raises(ValueError, match='entera'):
        po.Variable('x', 'entera', 'módulos', inferior=0, superior=2.5, origen='perfil')
    with pytest.raises(ValueError, match='catálogo'):
        po.Variable('x', 'categorica', 'tipo', catalogo=(), origen='perfil')
    with pytest.raises(ValueError, match='repetid'):
        problema_de(variables=(problema_de().variables[0],) * 2)


# ------------------------------------------------------------------ RF-2: discreción
@pytest.mark.parametrize('cambio,motivo', [
    ({'bancos': 1.4}, 'bancos'), ({'bancos': 4}, 'bancos'), ({'bancos': -1}, 'bancos'),
    ({'bancos': True}, 'bancos'), ({'bancos': float('nan')}, 'bancos'),
    ({'conductor': 'AAAC95'}, 'conductor'), ({'consigna': 1.2}, 'consigna'),
    ({'consigna': float('inf')}, 'consigna'),
])
def test_variables_discretas_no_fraccionan(cambio, motivo):
    """048:RF-2 — un banco de 1,4 módulos o un equipo que no está en el catálogo se rechazan, no se redondean."""
    llamadas = []

    def evaluador(v):
        llamadas.append(v)
        return evaluador_lineal(v)

    with pytest.raises(ValueError, match=motivo):
        po.evaluar_vector(problema_de(evaluador), {**VECTOR, **cambio})
    assert llamadas == []
    with pytest.raises(ValueError, match='falta'):
        po.evaluar_vector(problema_de(), {'bancos': 1, 'conductor': 'AAAC70'})
    with pytest.raises(ValueError, match='desconocida'):
        po.evaluar_vector(problema_de(), {**VECTOR, 'otra': 1})
    # Un entero escrito como 2.0 es el mismo entero: no es una fracción.
    assert po.evaluar_vector(problema_de(), {**VECTOR, 'bancos': 2.0})['vector']['bancos'] == 2


def test_reparar_es_el_mismo_criterio_para_todos():
    """048:RF-2 — los genes de un algoritmo pasan a un vector admisible por una sola regla."""
    p = problema_de()
    inferior, superior = po.cotas_geneticas(p)
    assert inferior.tolist() == [0, 0, 0.95] and superior.tolist() == [3, 1, 1.05]
    v = po.reparar(p, np.array([1.4, 0.6, 1.2]))
    assert v == {'bancos': 1, 'conductor': 'AAAC120', 'consigna': 1.05}
    assert po.reparar(p, np.array([2.5, -3, 0.9]))['bancos'] == 3     # medio entero, hacia arriba
    assert po.reparar(p, np.array([2.5, -3, 0.9]))['conductor'] == 'AAAC70'
    po.evaluar_vector(p, po.reparar(p, np.array([9.9, 9.9, 9.9])))     # siempre admisible


# ------------------------------------------------------------------ RF-2: conectividad
def cadena(n: int, p: float = 0.05, q: float = 0.02) -> dict:
    nodos = {f'N{i}': {'kv': 10.0, 'p_mw': 0.0 if i == 0 else p, 'q_mvar': 0.0 if i == 0 else q,
                       'fuente': i == 0, 'v_pu': 1.0 if i == 0 else None} for i in range(n)}
    ramas = [{'id': f'L{i}', 'desde': f'N{i - 1}', 'hasta': f'N{i}', 'cerrada': True,
              'r_ohm': 0.2, 'x_ohm': 0.2, 'inom_ka': 0.3} for i in range(1, n)]
    return {'version': orc.VERSION_GRAFO, **contrato_fisico(), 'nodos': nodos, 'ramas': ramas}


def test_isla_invalida_no_es_factible():
    """048:RF-2 — abrir una maniobra que deja cargas sin fuente pierde menos, pero no es factible."""
    rng = random.Random(4801)
    n = rng.randint(5, 14)
    corte = rng.randint(2, n - 1)
    grafo = cadena(n)
    p = ev.problema_maniobras(grafo, maniobras=[f'L{corte}'], contexto=contexto_de(), modelo_id='flujo@1', **NORMA)
    cerrada = po.evaluar_vector(p, {f'L{corte}': 1})
    abierta = po.evaluar_vector(p, {f'L{corte}': 0})
    assert cerrada['factible'], cerrada
    assert abierta['objetivos']['perdidas_kw'] < cerrada['objetivos']['perdidas_kw']
    assert not abierta['factible']
    deficit = abierta['violaciones']['demanda_no_atendida_kw']
    assert deficit == pytest.approx((n - corte) * 50.0, rel=1e-6)
    assert abierta['demanda']['referencia_kw'] == pytest.approx((n - 1) * 50.0)
    assert abierta['demanda']['atendida_kw'] == pytest.approx((corte - 1) * 50.0)


def test_evaluador_que_calla_la_demanda_no_es_factible():
    """048:RF-2 — sin la demanda atendida no se puede probar que nadie quedó sin servicio."""
    def mudo(v):
        r = evaluador_lineal(v)
        del r['demanda_atendida_kw']
        return r

    r = po.evaluar_vector(problema_de(mudo), VECTOR)
    assert not r['factible'] and 'demanda_atendida_kw' in ' '.join(r['avisos'])

    def sin_violacion(v):
        r = evaluador_lineal(v)
        r['violaciones'] = {}
        return r

    r = po.evaluar_vector(problema_de(sin_violacion), VECTOR)
    assert not r['factible'] and 'tension_pu' in ' '.join(r['avisos'])


def test_bancos_del_gemelo_son_un_problema_declarado():
    """048:RF-1, 048:RF-2 — los bancos del gemelo se formulan con su unidad, su norma y su demanda."""
    grafo = cadena(8, p=0.8, q=0.6)
    p = ev.problema_bancos(grafo, candidatos=['N7', 'N5', 'N0'], kvar_modulo=300.0, contexto=contexto_de(),
                           modelo_id='flujo@1', **NORMA)
    assert [v.nombre for v in p.variables] == ['N7', 'N5']        # la fuente no es candidata
    assert all(v.tipo == 'entera' and 'kvar' in v.unidad for v in p.variables)
    nada = po.evaluar_vector(p, {'N7': 0, 'N5': 0})
    con = po.evaluar_vector(p, {'N7': 3, 'N5': 0})
    assert not nada['factible'] and nada['violaciones']['tension_pu'] > con['violaciones']['tension_pu']
    assert con['demanda']['atendida_kw'] == pytest.approx(con['demanda']['referencia_kw'])


# ------------------------------------------------------------------ coste trazable
def test_sin_coste_no_inventa_cero():
    """048:RF-1 — sin coste declarado la inversión queda sin valor y la solución no es comparable."""
    r = po.evaluar_vector(problema_de(coste=None), VECTOR)
    assert r['objetivos']['inversion'] is None
    assert r['comparable'] is False
    assert any('coste' in a for a in r['avisos'])
    # Cero módulos sí cuestan cero: no es un coste inventado. El conductor elegido, en cambio,
    # siempre es una obra, y sin su coste la inversión sigue sin valor.
    solo_bancos = problema_de(coste=None, variables=problema_de(coste=None).variables[:1])
    assert po.evaluar_vector(solo_bancos, {'bancos': 0})['objetivos']['inversion'] == 0
    assert po.evaluar_vector(problema_de(coste=None), {**VECTOR, 'bancos': 0})['objetivos']['inversion'] is None
    con = po.evaluar_vector(problema_de(), VECTOR)
    assert con['objetivos']['inversion'] == 80.0 and con['comparable'] is True
    with pytest.raises(ValueError, match='origen_coste'):
        po.Variable('x', 'entera', 'módulos', inferior=0, superior=1, origen='perfil', coste=10.0)


# ------------------------------------------------------------------ RF-5: caché con contexto
@pytest.mark.parametrize('cambio', [
    {'contexto': contexto_de(year=2025)}, {'contexto': contexto_de(criterio_fijas='maximo_mes')},
    {'contexto': contexto_de(case_id='otro')}, {'modelo_id': 'oraculo@2'},
])
def test_cache_incluye_contexto_y_modelo(cambio):
    """048:RF-5 — otro año, criterio, caso o modelo no reutiliza la evaluación guardada."""
    llamadas = []

    def evaluador(v):
        llamadas.append(dict(v))
        return evaluador_lineal(v)

    cache = po.CacheEvaluaciones()
    a, b = problema_de(evaluador), problema_de(evaluador, **cambio)
    assert po.clave_evaluacion(a, VECTOR, POLITICA) != po.clave_evaluacion(b, VECTOR, POLITICA)
    cache.evaluar(a, VECTOR, POLITICA)
    cache.evaluar(a, dict(VECTOR), POLITICA)
    assert len(llamadas) == 1 and cache.reales == 1 and cache.cacheadas == 1
    cache.evaluar(b, VECTOR, POLITICA)
    assert len(llamadas) == 2 and cache.reales == 2


def test_cache_incluye_politica_y_vector():
    """048:RF-5 — otra política o un vector distinto, aunque sea por una cifra, es otra evaluación."""
    p = problema_de()
    claves = {po.clave_evaluacion(p, VECTOR, POLITICA), po.clave_evaluacion(p, VECTOR, '0' * 64),
              po.clave_evaluacion(p, {**VECTOR, 'consigna': 1.0 + 1e-12}, POLITICA),
              po.clave_evaluacion(p, {**VECTOR, 'conductor': 'AAAC120'}, POLITICA)}
    assert len(claves) == 4
    # Mismo vector escrito de otra forma (orden, 2 frente a 2.0): misma clave.
    assert (po.clave_evaluacion(p, {'consigna': 1.0, 'conductor': 'AAAC70', 'bancos': 2.0}, POLITICA)
            == po.clave_evaluacion(p, VECTOR, POLITICA))
    with pytest.raises(ValueError, match='politica'):
        po.clave_evaluacion(p, VECTOR, 'sin-huella')
    # Otra declaración del problema con el mismo nombre tampoco comparte clave.
    otra = replace(p, restricciones=(*p.restricciones, po.Restriccion('cargabilidad', '%', 'líneas')))
    assert po.clave_evaluacion(otra, VECTOR, POLITICA) != po.clave_evaluacion(p, VECTOR, POLITICA)


def test_contexto_sintetico_se_dice_y_no_se_confunde():
    """048:RF-5 — un benchmark analítico lleva su propio contexto, que no pasa por una red real."""
    sintetico = po.ContextoSintetico('benchmark_analitico_no_red_electrica', 'esfera entera')
    p = problema_de(contexto=sintetico)
    assert p.declaracion()['contexto']['dominio'] == 'benchmark_analitico_no_red_electrica'
    assert po.clave_evaluacion(p, VECTOR, POLITICA) != po.clave_evaluacion(problema_de(), VECTOR, POLITICA)
    with pytest.raises(ValueError, match='contexto'):
        problema_de(contexto={'year': 2026})
    with pytest.raises(ValueError, match='modelo_id'):
        problema_de(modelo_id=' ')
