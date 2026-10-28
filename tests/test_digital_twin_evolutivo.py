"""Spec 024, T16: algoritmos genéticos y evolutivos del gemelo y su uso en las obras.

Los optimizadores se prueban con problemas de óptimo conocido (el genético con un objetivo
exacto, NSGA-II con el frente de Schaffer, jDE con Rosenbrock) y los problemas de la red
con alimentadores sintéticos cuyo diagnóstico se comprueba antes: cada prueba verifica que
la red de partida incumple y que la propuesta la arregla.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip('scipy')

from igea_dgs.digital_twin import evolutivo as ev
from igea_dgs.digital_twin import oraculo as orc
from igea_dgs.pide_economia import valor_kw_perdidas

NORMA = {'tension_min_pu': 0.95, 'tension_max_pu': 1.05}


def cadena(n: int = 20, p: float = 0.2, q: float = 0.12, r: float = 0.35, x: float = 0.4,
           v_fuente: float = 1.0) -> dict:
    """Alimentador en línea de 10 kV: la fuente en N0 y una carga en cada barra."""
    nodos = {f'N{i}': {'kv': 10.0, 'p_mw': 0.0 if i == 0 else p, 'q_mvar': 0.0 if i == 0 else q,
                       'fuente': i == 0, 'v_pu': v_fuente if i == 0 else None} for i in range(n)}
    ramas = [{'id': f'L{i}', 'desde': f'N{i - 1}', 'hasta': f'N{i}', 'cerrada': True,
              'r_ohm': r, 'x_ohm': x, 'inom_ka': 0.3} for i in range(1, n)]
    return {'version': orc.VERSION_GRAFO, 'nodos': nodos, 'ramas': ramas}


def _v_min(grafo: dict) -> float:
    p = orc.ModeloMallado().predecir(grafo)
    return float(np.min(p['v'][1:]))


# ------------------------------------------------------------------ optimizadores
def test_genetico_halla_el_optimo_y_es_determinista():
    """024:RF-67 — el algoritmo genético llega al óptimo exacto, con elitismo (la mejor
    aptitud nunca empeora), memoria de evaluaciones y el mismo resultado con la misma semilla."""
    objetivo = np.array([3, 0, 7, 2, 5, 1, 4, 6])

    def aptitud(g):
        return float(np.sum((g - objetivo) ** 2))

    a = ev.algoritmo_genetico(aptitud, [0] * 8, [7] * 8, poblacion=40, generaciones=200, semilla=3)
    b = ev.algoritmo_genetico(aptitud, [0] * 8, [7] * 8, poblacion=40, generaciones=200, semilla=3)
    assert a.aptitud == 0 and list(a.mejor) == list(objetivo)
    assert list(a.mejor) == list(b.mejor) and a.historia == b.historia
    assert all(x >= y for x, y in zip(a.historia, a.historia[1:]))
    assert a.evaluaciones < 40 * (a.generaciones + 1)


def test_nsga2_frente_de_schaffer_y_restriccion():
    """024:RF-67 / 024:RF-69 — NSGA-II da el frente de Pareto de Schaffer (x entre 0 y 2), sin
    soluciones dominadas; con la restricción x ≥ 1, solo la parte que la cumple."""
    def schaffer(x):
        return [float(x[0] ** 2), float((x[0] - 2) ** 2)], 0.0

    f = ev.nsga2(schaffer, [-5.0], [5.0], enteros=False, poblacion=40, generaciones=60, semilla=1)
    xs = np.array([s[0] for s in f.soluciones])
    assert len(xs) >= 10 and xs.min() > -0.05 and xs.max() < 2.05
    for i, a in enumerate(f.objetivos):
        assert not any(np.all(b <= a) and np.any(b < a) for j, b in enumerate(f.objetivos) if j != i)

    def restringido(x):
        return schaffer(x)[0], max(0.0, 1.0 - float(x[0]))

    r = ev.nsga2(restringido, [-5.0], [5.0], enteros=False, poblacion=40, generaciones=60, semilla=1)
    xr = np.array([s[0] for s in r.soluciones])
    assert np.all(r.violacion == 0) and xr.min() >= 1.0 - 1e-9 and xr.max() < 2.05


def test_evolucion_diferencial_autoadaptativa():
    """024:RF-67 / 024:RF-72 — jDE llega al mínimo de Rosenbrock en 4 dimensiones y es
    determinista con su semilla."""
    def rosenbrock(x):
        return float(np.sum(100 * (x[1:] - x[:-1] ** 2) ** 2 + (1 - x[:-1]) ** 2))

    a = ev.evolucion_diferencial(rosenbrock, [-2] * 4, [2] * 4, generaciones=600, paciencia=200, semilla=5)
    b = ev.evolucion_diferencial(rosenbrock, [-2] * 4, [2] * 4, generaciones=600, paciencia=200, semilla=5)
    assert a.aptitud < 1e-3 and np.allclose(a.mejor, 1.0, atol=0.05)
    assert a.aptitud == b.aptitud


# ------------------------------------------------------------------ bancos
@pytest.fixture(scope='module')
def bancos():
    g = cadena()
    assert _v_min(g) < 0.95, 'la red de partida tiene que incumplir'
    r = ev.optimizar_bancos(g, candidatos=[f'N{i}' for i in range(1, 20)], kvar_modulo=300,
                            costo_modulo=1000.0, valor_kw_perdidas=50.0, semilla=2, **NORMA)
    return g, r


def test_bancos_cumplen_la_norma_al_menor_coste(bancos):
    """024:RF-68 — los bancos elegidos cumplen la norma donde la red de partida no, en la
    mitad lejana del alimentador, y ninguna solución del frente que cumple cuesta menos."""
    _g, r = bancos
    assert r['factible'] and r['bancos'] and r['v_min'] >= 0.95 - 1e-9 and r['v_min_base'] < 0.95
    assert all(int(b['barra'][1:]) >= 7 for b in r['bancos'])
    assert all(b['q_kvar'] == 300 * b['modulos'] for b in r['bancos'])
    assert r['perdidas_kw'] < r['perdidas_kw_base'] and r['confirmar_en_pf']
    cumplen = [f for f in r['frente'] if f['cumple']]
    assert cumplen and min(f['inversion'] for f in cumplen) >= r['inversion'] - 1e-9


def test_frente_y_sobredimensionadas(bancos):
    """024:RF-69 — el frente inversión–pérdidas trae soluciones que cumplen con más inversión,
    y esas quedan marcadas como sobredimensionadas."""
    _g, r = bancos
    assert r['algoritmos']['nsga2']['soluciones'] == len(r['frente']) >= 2
    for f in r['frente']:
        assert f['sobredimensionada'] == (f['cumple'] and f['inversion'] > r['inversion'] + 1e-9)


def test_bancos_deterministas(bancos):
    """024:RF-67 — misma red, mismos parámetros y misma semilla: la misma propuesta."""
    g, r = bancos
    otra = ev.optimizar_bancos(g, candidatos=[f'N{i}' for i in range(1, 20)], kvar_modulo=300,
                               costo_modulo=1000.0, valor_kw_perdidas=50.0, semilla=2, **NORMA)
    assert otra['bancos'] == r['bancos'] and otra['coste_total'] == r['coste_total']


def test_sin_costos_la_menor_intervencion():
    """024:RF-70 — sin libro CAPEX ni precio de las pérdidas no se inventan: el coste es el
    número de módulos y las pérdidas solo desempatan."""
    g = cadena()
    r = ev.optimizar_bancos(g, candidatos=[f'N{i}' for i in range(1, 20)], kvar_modulo=300, semilla=2, **NORMA)
    assert r['factible'] and r['inversion'] == sum(b['modulos'] for b in r['bancos'])
    assert r['coste_total'] - r['inversion'] < 0.01


def test_bancos_que_no_alcanzan_lo_dicen():
    """024:RF-68 — si ningún banco del tamaño del perfil cumple la norma, no se da por bueno."""
    r = ev.optimizar_bancos(cadena(), candidatos=['N19'], kvar_modulo=1, modulos_max=1, semilla=2, **NORMA)
    assert not r['factible']
    assert ev.optimizar_bancos(cadena(), candidatos=['NO_EXISTE'], kvar_modulo=300, **NORMA)['motivo']


# ------------------------------------------------------------------ reconfiguración y consigna
def anillo(n: int = 12) -> dict:
    """Anillo desde la fuente N0, abierto junto a ella: todo cuelga de un solo extremo."""
    g = cadena(n, p=0.15, q=0.08)
    g['ramas'].append({'id': 'CIERRE', 'desde': f'N{n - 1}', 'hasta': 'N0', 'cerrada': False,
                       'r_ohm': 0.35, 'x_ohm': 0.4, 'inom_ka': 0.3})
    return g


def test_reconfiguracion_radial_con_menos_perdidas():
    """024:RF-71 — el algoritmo genético abre el anillo por el medio: menos pérdidas, sin
    lazos y sin cargas sin fuente; nada se escribe, se confirma en DIgSILENT."""
    g = anillo()
    maniobras = [r['id'] for r in g['ramas']]
    r = ev.reconfigurar(g, maniobras=maniobras, semilla=4, **NORMA)
    assert r['factible'] and r['mejora'] and r['confirmar_en_pf']
    assert r['despues']['perdidas_kw'] < 0.6 * r['antes']['perdidas_kw']
    assert r['cerrar'] == ['CIERRE'] and len(r['abrir']) == 1
    abierta = int(r['abrir'][0][1:])
    assert 4 <= abierta <= 8


def test_reconfiguracion_nunca_deja_lazos_ni_islas():
    """024:RF-71 — un estado con lazos o con cargas sin fuente nunca se propone, aunque los
    radiales también incumplan la tensión (entonces se elige el que menos se aparta)."""
    g = anillo()
    m = orc.muestra(ev._grafo_con_estados(g, {'CIERRE': True}))
    assert ev._lazos(m) == 1
    r = ev.reconfigurar(g, maniobras=['CIERRE', 'L1'], semilla=1, **NORMA)
    assert 'perdidas_kw' in r['despues'] and r['despues']['violacion_pu'] > 0 and not r['factible']
    cerradas = {'CIERRE': 'CIERRE' in r['cerrar'], 'L1': 'L1' not in r['abrir']}
    assert sum(cerradas.values()) == 1


def test_consigna_con_evolucion_diferencial():
    """024:RF-72 — jDE sube la consigna de la fuente lo justo para cumplir la norma, dentro
    de su banda, con un solo flujo por evaluación."""
    g = cadena(14, p=0.1, q=0.06)
    assert 0.92 < _v_min(g) < 0.95
    r = ev.optimizar_consigna(g, semilla=3, **NORMA)
    u = r['consignas']['N0']
    assert r['factible'] and 1.0 < u <= 1.05
    assert r['antes']['v_min'] < 0.95 <= r['despues']['v_min'] + 1e-9
    assert r['despues']['v_max'] <= 1.05 + 1e-9


# ------------------------------------------------------------------ obras del PIDE
def _obra(barra: str, anio: int = 0) -> dict:
    return {'codigo': 'AL01', 'anio': anio, 'alternativa': 'bancos', 'elemento': barra,
            'obra_011': {'clase': 'condensador', 'alimentador': 'A1', 'barra': barra, 'q_kvar': 300,
                         'escalones': 1, 'casos': ['Con proyecto']}}


def test_afinar_bancos_del_pide():
    """024:RF-73 — los bancos del PIDE pasan a la ubicación y el tamaño del optimizador, con
    su evidencia; la obra sigue siendo de la spec 011 y se confirma en DIgSILENT."""
    obras = [_obra('N12')]
    avisos = ev.afinar_bancos_pide(obras, cadena(), bancos_kvar={10.0: 300.0}, semilla=2, **NORMA)
    o = obras[0]
    assert not avisos and o['optimizacion']['aplicada'] and o['optimizacion']['factible']
    assert o['obra_011']['clase'] == 'condensador' and o['obra_011']['q_kvar'] % 300 == 0
    assert o['elemento'] == o['obra_011']['barra']
    g = cadena()
    for b in [o['obra_011'], *(o.get('obras_011_extra') or [])]:
        g['nodos'][b['barra']]['q_mvar'] -= b['q_kvar'] / 1000
    assert _v_min(g) >= 0.95 - 1e-9


def test_afinar_con_demanda_del_anio_y_barra_desconocida():
    """024:RF-73 — la demanda se escala al año de la obra; una barra que no está en la red del
    gemelo deja el banco del diagnóstico, con aviso."""
    sin_barra = [_obra('XYZ')]
    avisos = ev.afinar_bancos_pide(sin_barra, cadena(), bancos_kvar={10.0: 300.0}, **NORMA)
    assert avisos and sin_barra[0]['obra_011']['barra'] == 'XYZ' and 'optimizacion' not in sin_barra[0]
    hoy, futuro = [_obra('N12', 0)], [_obra('N12', 8)]
    ev.afinar_bancos_pide(hoy, cadena(), bancos_kvar={10.0: 300.0}, **NORMA)
    ev.afinar_bancos_pide(futuro, cadena(), bancos_kvar={10.0: 300.0}, tasa_demanda=0.03, **NORMA)

    def kvar(o):
        return sum(b['q_kvar'] for b in [o['obra_011'], *(o.get('obras_011_extra') or [])] if b)

    assert kvar(futuro[0]) > kvar(hoy[0])


def _episodio(grafo, factor=1.0, abiertos=()):
    return SimpleNamespace(topologia={'grafo': grafo},
                           accion={'escenario': {'factor_carga': factor, 'tramos_abiertos': list(abiertos)}})


def test_red_del_gemelo():
    """024:RF-73 — la red del gemelo es la del episodio más reciente sin perturbar; si solo
    hay escenarios, se devuelve con la demanda a su factor 1 y los tramos cerrados."""
    g1, g2 = cadena(5), cadena(6)
    assert ev.red_del_gemelo([_episodio(g1), _episodio(g2, 1.2)]) is g1
    assert ev.red_del_gemelo([]) is None
    perturbada = cadena(5, p=0.24)
    perturbada['ramas'][1]['cerrada'] = False
    r = ev.red_del_gemelo([_episodio(perturbada, 1.2, ['L2'])])
    assert r['nodos']['N1']['p_mw'] == pytest.approx(0.2) and r['ramas'][1]['cerrada']


def test_valor_de_las_perdidas():
    """024:RF-70 — el kW de pérdidas se valora con el factor de carga y el precio del perfil;
    sin ellos no hay valor."""
    plan = {'tasa_regulada': 0.12, 'vida_util_anios': 30}
    assert valor_kw_perdidas(plan, factor_carga=None, precio_compra_kwh=0.2) is None
    v = valor_kw_perdidas(plan, factor_carga=0.6, precio_compra_kwh=0.2)
    assert v == pytest.approx(8760 * (0.3 * 0.6 + 0.7 * 0.36) * 0.2 / 0.12414, rel=1e-3)


def test_la_web_optimiza_los_bancos_con_la_red_del_gemelo(tmp_path, monkeypatch):
    """024:RF-73 — el PIDE de la web toma la red del gemelo del proyecto y afina sus bancos;
    sin red del gemelo, lo dice y deja los del diagnóstico."""
    from test_digital_twin_episode import _payload

    from igea_dgs.digital_twin.buffer import BuferEpisodios
    from igea_dgs.digital_twin.episode import leer_episodio
    from igea_dgs.web import services

    monkeypatch.setenv('IGEA_TWIN_DATA', str(tmp_path / 'twin'))
    limites = SimpleNamespace(**NORMA)
    perfil = {'calibracion': {'bancos_kvar_por_tension': {'10': 300}}}
    plan = {'tasa_regulada': 0.12, 'vida_util_anios': 30}
    ctx = SimpleNamespace(log=lambda _m: None)
    obras = [_obra('N12')]
    avisos = services._pide_optimizar('P1', obras, limites, perfil, plan, {}, ctx)
    assert any('no tiene la red' in a for a in avisos) and 'optimizacion' not in obras[0]
    p = _payload()
    p['nativo']['project'] = 'P1'
    p['topologia'] = {'grafo': cadena()}
    BuferEpisodios().guardar(leer_episodio(p))
    avisos = services._pide_optimizar('P1', obras, limites, perfil, plan, {}, ctx)
    assert obras[0]['optimizacion']['aplicada'] and any('desempatan' in a for a in avisos)


def test_top_k_verificado_en_digsilent(bancos):
    """027:RF-14 / 027:RF-15 / 027:RF-16 — las k mejores que cumplen, distintas, en orden; la que
    DIgSILENT no confirma se descarta con su episodio y se prueba la siguiente; la elegida lleva
    la evaluación del gemelo y la de DIgSILENT."""
    _g, r = bancos
    alts = r['alternativas']
    assert 1 <= len(alts) <= 3 and alts[0]['bancos'] == r['bancos']
    assert len({tuple((b['barra'], b['modulos']) for b in a['bancos']) for a in alts}) == len(alts)
    guardados = []
    medidas = iter([{'converge': True, 'v_min': alts[0]['v_min'] - 0.05, 'perdidas_kw': alts[0]['perdidas_kw']}]
                   + [{'converge': True, 'v_min': a['v_min'] + 0.001, 'perdidas_kw': a['perdidas_kw'] * 1.05}
                      for a in alts[1:]])
    v = ev.verificar_top_k(alts, lambda _a: next(medidas), tolerancia_v_pu=0.01,
                           guardar=lambda a, m, motivo: guardados.append(motivo))
    if len(alts) > 1:
        assert v['verificada'] and v['elegida'] == alts[1] and len(v['descartadas']) == 1
        assert 'tensión mínima' in v['descartadas'][0]['motivo'] and guardados == [v['descartadas'][0]['motivo']]
        assert set(v['gemelo']) == {'v_min', 'perdidas_kw'} and v['digsilent']['converge']
    nada = ev.verificar_top_k(alts, lambda _a: {'converge': False}, tolerancia_v_pu=0.01)
    assert not nada['verificada'] and len(nada['descartadas']) == len(alts)
