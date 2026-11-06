"""Spec 048, T3: tramo continuo con un solucionador PNL real y elección con la verificación de la 044.

Un solucionador continuo (Ipopt, o HiGHS en un problema cuadrático) da un punto local de las
variables continuas con las discretas fijas: no es el óptimo global del problema mixto. Se
prueba con un caso diminuto de óptimo conocido, enumerando sus discretas, y nada se elige sin la
medición nativa completa que exige ``verificar_top_k``.
"""
from __future__ import annotations

import builtins
from dataclasses import replace

import pytest

pytest.importorskip('pyomo')
pytest.importorskip('highspy')

from test_verificacion_top_k_completa import LIMITES, contexto_de, medida_nativa

from convertersmartgrid.digital_twin import adaptador_pnl as pnl
from convertersmartgrid.digital_twin import problema_optimizacion as po

C_MODULO = 0.001
LIMITE_SUMA = 1.9
CONTEXTO = po.ContextoSintetico('benchmark_analitico_no_red_electrica', 'caso mixto diminuto de la 048')


def a_de(k: int) -> float:
    return 0.95 + 0.05 * k


def problema_conocido(modelo_pnl='defecto') -> po.ProblemaOptimizacion:
    """min (u − a_k)² + (w − 1)² + c·k con u + w ≤ 1,9: para cada k el óptimo es la proyección."""
    def evaluador(v):
        u, w, k = v['u'], v['w'], v['k']
        return {'convergio': True, 'objetivos': {'f': (u - a_de(k)) ** 2 + (w - 1) ** 2 + C_MODULO * k},
                'violaciones': {'suma': max(u + w - LIMITE_SUMA, 0.0)},
                'demanda_referencia_kw': 100.0, 'demanda_atendida_kw': 100.0}

    def modelo(m, x, discretas):
        k = discretas['k']
        return {'objetivo': (x['u'] - a_de(k)) ** 2 + (x['w'] - 1) ** 2 + C_MODULO * k,
                'restricciones': [x['u'] + x['w'] <= LIMITE_SUMA]}

    return po.ProblemaOptimizacion(
        nombre='mixto_diminuto',
        variables=(po.Variable('k', 'entera', 'módulos', inferior=0, superior=2, origen='prueba'),
                   po.Variable('u', 'continua', 'p.u.', inferior=0.9, superior=1.1, origen='prueba'),
                   po.Variable('w', 'continua', 'p.u.', inferior=0.0, superior=2.0, origen='prueba')),
        restricciones=(po.Restriccion('suma', 'p.u.', 'u + w no pasa de 1,9'),),
        objetivos=(po.Objetivo('f', 'p.u.²'),), contexto=CONTEXTO, modelo_id='analitico@1', evaluador=evaluador,
        modelo_pnl=modelo if modelo_pnl == 'defecto' else modelo_pnl)


def analitico(k: int) -> tuple[float, float, float]:
    d = max(a_de(k) + 1 - LIMITE_SUMA, 0.0) / 2
    return a_de(k) - d, 1 - d, 2 * d * d + C_MODULO * k


HIGHS = {'solver': 'highs'}


# ------------------------------------------------------------------ RF-4
def test_pnl_no_declara_optimo_global():
    """048:RF-4 — con un solucionador real, el resultado es un punto local continuo, nunca un óptimo global."""
    r = pnl.resolver_continuo(problema_conocido(), discretas_fijas={'k': 1}, opciones_solver=HIGHS)
    u, w, f = analitico(1)
    assert r['estado'] == 'LOCAL_CONVERGIDO', r
    assert r['alcance'] == 'local_continuo' and r['optimo_global'] is False
    assert r['continuas']['u'] == pytest.approx(u, abs=1e-5) and r['continuas']['w'] == pytest.approx(w, abs=1e-5)
    assert r['objetivo_pnl'] == pytest.approx(f, abs=1e-7)
    assert r['solver'] == 'highs' and r['terminacion']
    assert r['residuos']['restricciones_max'] <= r['tolerancias']['residuo_max']
    assert r['residuos']['cotas_max'] <= r['tolerancias']['residuo_max']
    assert set(r['iniciales']) == {'u', 'w'}
    assert r['evaluacion']['factible'] and r['requiere_verificacion_nativa'] is True


def test_enumerar_discretas_del_caso_diminuto_da_su_optimo_conocido():
    """048:RF-4 — enumerar el caso diminuto y resolver su tramo continuo encuentra el óptimo analítico."""
    resultados = {k: pnl.resolver_continuo(problema_conocido(), discretas_fijas={'k': k}, opciones_solver=HIGHS)
                  for k in range(3)}
    assert all(r['estado'] == 'LOCAL_CONVERGIDO' for r in resultados.values())
    mejor = min(resultados, key=lambda k: resultados[k]['objetivo_pnl'])
    esperado = min(range(3), key=lambda k: analitico(k)[2])
    assert mejor == esperado == 0
    for k, r in resultados.items():
        assert r['evaluacion']['objetivos']['f'] == pytest.approx(analitico(k)[2], abs=1e-7)


def test_iniciales_y_tolerancias_se_informan():
    """048:RF-4 — el punto inicial y las tolerancias declaradas viajan con el resultado."""
    r = pnl.resolver_continuo(problema_conocido(), discretas_fijas={'k': 2},
                              opciones_solver={**HIGHS, 'iniciales': {'u': 1.0, 'w': 0.5}, 'residuo_max': 1e-7})
    assert r['iniciales'] == {'u': 1.0, 'w': 0.5}
    assert r['tolerancias']['residuo_max'] == 1e-7
    with pytest.raises(ValueError, match='inicial'):
        pnl.resolver_continuo(problema_conocido(), discretas_fijas={'k': 2},
                              opciones_solver={**HIGHS, 'iniciales': {'u': 3.0, 'w': 0.5}})


@pytest.mark.parametrize('fijas,motivo', [
    ({}, 'falta'), ({'k': 1.5}, 'k'), ({'k': 3}, 'k'), ({'k': 1, 'u': 1.0}, 'continua'), ({'k': None}, 'k'),
])
def test_discretas_se_fijan(fijas, motivo):
    """048:RF-4 — las discretas se fijan enteras y del dominio; el solucionador nunca las relaja."""
    with pytest.raises(ValueError, match=motivo):
        pnl.resolver_continuo(problema_conocido(), discretas_fijas=fijas, opciones_solver=HIGHS)
    r = pnl.resolver_continuo(problema_conocido(), discretas_fijas={'k': 2}, opciones_solver=HIGHS)
    assert r['variables_pnl'] == ['u', 'w']             # el modelo solo tiene las continuas
    assert r['discretas'] == {'k': 2} and r['vector']['k'] == 2


def test_solver_ausente_no_rompe_algoritmos(monkeypatch):
    """048:RF-4 — sin el solucionador o sin Pyomo, ERROR_ENTORNO solo para el candidato PNL."""
    r = pnl.resolver_continuo(problema_conocido(), discretas_fijas={'k': 0},
                              opciones_solver={'solver': 'solucionador_inexistente_csg'})
    assert r['estado'] == 'ERROR_ENTORNO' and r['alcance'] == 'local_continuo' and r['optimo_global'] is False
    assert r['continuas'] is None and 'solucionador_inexistente_csg' in r['motivo']
    original = builtins.__import__

    def sin_pyomo(nombre, *a, **kw):
        if nombre.startswith('pyomo'):
            raise ImportError('pyomo no instalado (prueba)')
        return original(nombre, *a, **kw)

    monkeypatch.setattr(builtins, '__import__', sin_pyomo)
    r = pnl.resolver_continuo(problema_conocido(), discretas_fijas={'k': 0}, opciones_solver=HIGHS)
    assert r['estado'] == 'ERROR_ENTORNO' and 'pyomo' in r['motivo'].lower()
    monkeypatch.setattr(builtins, '__import__', original)
    # Los algoritmos evolutivos siguen: el benchmark no depende del PNL.
    from convertersmartgrid.digital_twin import benchmark_optimizacion as bo
    prob = replace(problema_conocido(), normalizacion={'f': (0.0, 1.0)})
    b = bo.comparar_optimizadores([prob], semillas=tuple(range(20)), presupuesto=10, cancelado=lambda: False,
                                  algoritmos=('nsga2', 'evolucion_diferencial'))
    assert b['estado'] == 'completo'


def test_sin_modelo_pnl_o_sin_continuas_no_aplica():
    """048:RF-4 — un problema sin tramo continuo declarado no se resuelve con el PNL, se dice."""
    r = pnl.resolver_continuo(problema_conocido(modelo_pnl=None), discretas_fijas={'k': 0}, opciones_solver=HIGHS)
    assert r['estado'] == 'NO_APLICA' and 'modelo_pnl' in r['motivo']


# ------------------------------------------------------------------ RF-7
def candidato(nombre: str, **extra) -> dict:
    return {'id': nombre, 'v_min': 0.97, 'perdidas_kw': 10.0, 'vector': {'k': 0, 'u': 0.925, 'w': 0.975}, **extra}


def test_eleccion_exige_verificacion_completa_044():
    """048:RF-7 — se elige solo la que pasa la verificación completa de la 044, secuencial y entre las k primeras."""
    medidas = {'pnl_sin_solver': None, 'incompleta': {'converge': True}, 'completa': medida_nativa(0.971, 10.5)}
    medidos = []

    def medir(alt):
        medidos.append(alt['id'])
        return medidas[alt['id']]

    candidatos = [candidato('pnl_sin_solver', pnl={'estado': 'ERROR_ENTORNO'}), candidato('incompleta'),
                  candidato('completa')]
    r = pnl.verificar_candidatos(candidatos, medir, k=3, tolerancia_v_pu=0.01, contexto=contexto_de(),
                                 limites=LIMITES)
    assert r['verificada'] and r['elegida']['id'] == 'completa'
    assert medidos == ['incompleta', 'completa']         # el PNL sin solver ni se mide
    assert r['excluidas'][0]['alternativa']['id'] == 'pnl_sin_solver'
    assert r['descartadas'][0]['alternativa']['id'] == 'incompleta'
    assert r['evaluacion']['clase'] == 'accepted' and r['validacion']['valida']
    # Con k=1 solo se prueba la primera admisible: incompleta, y no se elige ninguna.
    r = pnl.verificar_candidatos(candidatos, medir, k=1, tolerancia_v_pu=0.01, contexto=contexto_de(),
                                 limites=LIMITES)
    assert r['verificada'] is False and r['elegida'] is None
    assert pnl.TOP_K == 3
    with pytest.raises(ValueError, match='k'):
        pnl.verificar_candidatos(candidatos, medir, k=0, tolerancia_v_pu=0.01, contexto=contexto_de(), limites=LIMITES)


def test_infactible_o_no_convergido_no_llega_a_digsilent():
    """048:RF-7 — lo que el gemelo ya da por infactible o el PNL no convergió no gasta una simulación."""
    medidos = []
    candidatos = [candidato('infactible', evaluacion={'factible': False}),
                  candidato('pnl_no_converge', pnl={'estado': 'NO_CONVERGIDO'}),
                  candidato('pnl_ok', pnl={'estado': 'LOCAL_CONVERGIDO'}, evaluacion={'factible': True})]
    r = pnl.verificar_candidatos(candidatos, lambda a: medidos.append(a['id']) or medida_nativa(0.971, 10.5),
                                 tolerancia_v_pu=0.01, contexto=contexto_de(), limites=LIMITES)
    assert medidos == ['pnl_ok'] and r['elegida']['id'] == 'pnl_ok'
    assert [e['alternativa']['id'] for e in r['excluidas']] == ['infactible', 'pnl_no_converge']
    assert all(e['motivo'] for e in r['excluidas'])

