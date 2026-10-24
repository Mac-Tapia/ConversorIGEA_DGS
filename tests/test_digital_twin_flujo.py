"""Spec 024, T15: flujo físico mallado del gemelo (base de la PINN y de los evolutivos).

Se contrasta con el barrido radial en árboles y con pandapower en redes con lazos, que es
un cálculo independiente: si los tres coinciden, la física de la base está bien.
"""
from __future__ import annotations

import random

import numpy as np
import pytest

pytest.importorskip('scipy')

from test_digital_twin_oraculo import red_radial

from igea_dgs.digital_twin import oraculo as orc


def red_mallada(rnd: random.Random, n: int, lazos: int, kv: float = 10.0) -> dict:
    """Árbol de ``n`` barras con ``lazos`` ramas más que cierran lazos, a media carga: con
    40 barras a plena carga la red queda al borde del colapso y pandapower no converge."""
    g = red_radial(rnd, n, carga=0.5)
    for nodo in g['nodos'].values():
        nodo['kv'] = kv
    for k in range(lazos):
        a, b = rnd.sample(range(1, n), 2)
        g['ramas'].append({'id': f'LZ{k}', 'desde': f'N{a}', 'hasta': f'N{b}', 'cerrada': True,
                           'r_ohm': rnd.uniform(0.2, 0.8), 'x_ohm': rnd.uniform(0.2, 0.6), 'inom_ka': 0.2})
    return g


def _pandapower(g: dict) -> dict[str, float]:
    pp = pytest.importorskip('pandapower')
    net = pp.create_empty_network(sn_mva=orc.S_BASE)
    bus = {n: pp.create_bus(net, vn_kv=d['kv'], name=n) for n, d in g['nodos'].items()}
    for n, d in g['nodos'].items():
        if d.get('fuente'):
            pp.create_ext_grid(net, bus[n], vm_pu=d.get('v_pu') or 1.0)
        elif d['p_mw'] or d['q_mvar']:
            pp.create_load(net, bus[n], p_mw=d['p_mw'], q_mvar=d['q_mvar'])
    for r in g['ramas']:
        if r.get('cerrada', True):
            pp.create_line_from_parameters(net, bus[r['desde']], bus[r['hasta']], length_km=1.0,
                                           r_ohm_per_km=r['r_ohm'], x_ohm_per_km=r['x_ohm'], c_nf_per_km=0.0,
                                           max_i_ka=r['inom_ka'] or 1.0)
    pp.runpp(net, tolerance_mva=1e-10, max_iteration=50, numba=False)
    return {n: float(net.res_bus.vm_pu.at[i]) for n, i in bus.items()}


@pytest.mark.parametrize('semilla', [1, 2, 3])
def test_en_un_arbol_coincide_con_el_barrido(semilla):
    """024:RF-64 — sin lazos, el flujo mallado y el barrido radial dan lo mismo."""
    g = red_radial(random.Random(semilla), 25)
    mallado = orc.ModeloMallado().predecir(g)
    radial = orc.ModeloRadial().predecir(g)
    assert np.max(np.abs(mallado['v'] - radial['v'])) < 1e-7
    assert float(np.max(mallado['residuo'])) < 1e-8


@pytest.mark.parametrize('semilla', [4, 5, 6])
def test_con_lazos_coincide_con_pandapower(semilla):
    """024:RF-64 — con lazos, el flujo mallado coincide con pandapower; el barrido no puede."""
    rnd = random.Random(semilla)
    g = red_mallada(rnd, rnd.randint(15, 40), lazos=3)
    referencia = _pandapower(g)
    p = orc.ModeloMallado().predecir(g)
    v = dict(zip(p['ids'], p['v'], strict=True))
    assert max(abs(v[n] - referencia[n]) for n in referencia) < 1e-6
    assert p['convergio'] and p['perdidas_mw'] > 0


def test_acopladores_e_islas():
    """024:RF-65 — las barras de un acoplador cerrado tienen la misma tensión y una isla sin
    fuente queda a 0 p.u. sin romper el cálculo."""
    g = red_radial(random.Random(7), 10)
    g['nodos']['NA'] = {'kv': 10.0, 'p_mw': 0.1, 'q_mvar': 0.02, 'fuente': False}
    g['nodos']['ISLA'] = {'kv': 10.0, 'p_mw': 0.1, 'q_mvar': 0.0, 'fuente': False}
    g['ramas'].append({'id': 'ACOP', 'desde': 'N9', 'hasta': 'NA', 'cerrada': True,
                       'r_ohm': 0.0, 'x_ohm': 0.0, 'inom_ka': 0.0})
    p = orc.ModeloMallado().predecir(g)
    v = dict(zip(p['ids'], p['v'], strict=True))
    assert v['N9'] == pytest.approx(v['NA'], abs=1e-12) and v['N9'] < 1.0
    assert v['ISLA'] == 0.0 and p['convergio']


def test_perdidas_y_consigna_sin_refactorizar():
    """024:RF-64 — las pérdidas son lo que entra menos lo que consumen las cargas, y la
    consigna de la fuente cambia sin volver a factorizar la red."""
    g = red_mallada(random.Random(8), 20, lazos=2)
    m = orc.muestra(g)
    sis = orc.sistema_de(m)
    sol = sis.resolver(m.s_carga)
    entra = float(np.sum(sol.s_fuentes.real))
    assert sol.perdidas_pu == pytest.approx(entra - float(np.sum(m.s_carga.real)), rel=1e-6)
    alta = sis.resolver(m.s_carga, consigna=np.array([1.05]))
    assert alta.v[m.alimentado].min() > sol.v[m.alimentado].min()
    assert orc.sistema_de(m) is sis


def test_si_no_converge_lo_dice():
    """024:RF-66 — una demanda que la red no puede llevar no da tensiones como resultado."""
    g = red_radial(random.Random(9), 10, carga=400.0)
    p = orc.ModeloMallado().predecir(g)
    assert not p['convergio'] and p['fuera_de_dominio'] and p['motivos']


def test_elige_el_modelo_de_carga_con_la_fisica_mallada():
    """024:RF-66 — el modelo de carga se elige con la física mallada: con tensiones de
    impedancia constante, sale el exponente 2."""
    rnd = random.Random(10)
    muestras = []
    for _ in range(4):
        g = red_mallada(rnd, 20, lazos=2)
        g['version'] = orc.VERSION_GRAFO
        p = orc.ModeloMallado(exponente=2.0).predecir(g)
        muestras.append(orc.muestra(g, dict(zip(p['ids'], map(float, p['v']), strict=True))))
    assert orc.elegir_exponente(muestras) == 2.0


def test_residuo_por_barra_electrica():
    """024:RF-65 — el residuo físico se mide por barra eléctrica: dos barras unidas por un
    acoplador con tensiones apenas distintas no disparan el balance."""
    g = red_radial(random.Random(11), 8)
    g['nodos']['NA'] = {'kv': 10.0, 'p_mw': 0.0, 'q_mvar': 0.0, 'fuente': False}
    g['ramas'].append({'id': 'ACOP', 'desde': 'N7', 'hasta': 'NA', 'cerrada': True,
                       'r_ohm': 0.0, 'x_ohm': 0.0, 'inom_ka': 0.0})
    m = orc.muestra(g)
    p = orc.ModeloMallado().predecir_muestra(m)
    v = p['v'].copy()
    v[m.ids.index('NA')] += 1e-5
    assert float(np.max(orc.residuo(m, v, p['theta']))) < 1e-3
