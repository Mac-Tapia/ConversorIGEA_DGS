"""Spec 045, T2: física representada, fronteras y pérdida por términos.

Ninguna prueba entrena ni usa la GPU. Las dos que tocan PyTorch comprueban una fórmula (el gradiente del
residuo) y las fronteras de la red con pesos al azar: la regla de «solo en CUDA» es la de entrenar y predecir
con un modelo, y sigue siendo de ``dispositivo()``.
"""
from __future__ import annotations

import random

import numpy as np
import pytest
from apoyo import contrato_fisico

# Antes que PyTorch: importarlo después reventó con un «access violation» en una de cada cuatro
# pasadas (Windows, 2026-11-03), dentro de la carga de módulos de pandapower.
pp = pytest.importorskip('pandapower')

from convertersmartgrid.digital_twin import oraculo as orc
from convertersmartgrid.digital_twin.contratos_fisicos import VERSION_GRAFO, validar_alcance_fisico
from convertersmartgrid.digital_twin.flujo import Z_ACOPLADOR


def _grafo(nodos, ramas, **extra) -> dict:
    return {'version': VERSION_GRAFO, **contrato_fisico(), 'nodos': nodos, 'ramas': ramas, **extra}


def _nodo(p=0.0, q=0.0, kv=10.0, **extra) -> dict:
    return {'kv': kv, 'p_mw': p, 'q_mvar': q, 'fuente': False, **extra}


def _fuente(v=1.02, kv=10.0, **extra) -> dict:
    return {'kv': kv, 'p_mw': 0.0, 'q_mvar': 0.0, 'fuente': True, 'v_pu': v, **extra}


def _linea(i, a, b, r=0.4, x=0.3, cerrada=True) -> dict:
    return {'id': i, 'clase': 'ElmLne', 'desde': a, 'hasta': b, 'cerrada': cerrada, 'r_ohm': r, 'x_ohm': x, 'inom_ka': 0.2}


def _acoplador(i, a, b) -> dict:
    return {'id': i, 'clase': 'ElmCoup', 'desde': a, 'hasta': b, 'cerrada': True, 'r_ohm': 0.0, 'x_ohm': 0.0, 'inom_ka': 0.0}


def _radial_y_mallada_con_acoplador_e_isla() -> dict:
    """Dos componentes con su fuente (una mallada, con acoplador en la fuente) y una isla sin fuente."""
    return _grafo(
        {'S1': _fuente(1.02), 'S1b': _nodo(), 'A': _nodo(0.2, 0.05), 'B': _nodo(0.1, 0.03), 'C': _nodo(0.15, 0.04),
         'S2': _fuente(0.98), 'D': _nodo(0.1, 0.02), 'I1': _nodo(0.1, 0.02), 'I2': _nodo(0.1, 0.02)},
        [_acoplador('K', 'S1', 'S1b'), _linea('L1', 'S1b', 'A'), _linea('L2', 'A', 'B'), _linea('L3', 'B', 'C'),
         _linea('L4', 'C', 'S1b', 0.6, 0.4), _linea('L5', 'S2', 'D'), _linea('L6', 'I1', 'I2')])


def test_referencia_por_componente():
    """045:RF-5 — la física fija la magnitud exacta y el ángulo 0 en cada componente, también tras un acoplador."""
    g = _radial_y_mallada_con_acoplador_e_isla()
    m = orc.muestra(g)
    p = orc.ModeloMallado().predecir_muestra(m)
    pos = {n: i for i, n in enumerate(p['ids'])}
    assert p['convergio']
    assert p['v'][pos['S1']] == 1.02 and p['v'][pos['S2']] == 0.98
    assert p['theta'][pos['S1']] == 0.0 and p['theta'][pos['S2']] == 0.0
    assert p['v'][pos['S1b']] == 1.02 and p['theta'][pos['S1b']] == 0.0
    assert p['v'][pos['I1']] == 0.0 and p['theta'][pos['I1']] == 0.0
    assert p['v'][pos['A']] > 0 and p['theta'][pos['A']] != 0.0


def test_imponer_fronteras_devuelve_el_dato_exacto():
    """045:RF-5 — lo que predice un modelo se corrige con lo que es dato: fuente, acoplador e isla sin fuente."""
    m = orc.muestra(_radial_y_mallada_con_acoplador_e_isla())
    pos = {n: i for i, n in enumerate(m.ids)}
    v, th = orc.imponer_fronteras(m, np.full(len(m.ids), 0.9), np.full(len(m.ids), 0.1))
    assert (v[pos['S1']], v[pos['S1b']], v[pos['S2']]) == (1.02, 1.02, 0.98)
    assert (th[pos['S1']], th[pos['S1b']], th[pos['S2']]) == (0.0, 0.0, 0.0)
    assert (v[pos['I1']], th[pos['I2']]) == (0.0, 0.0)
    assert v[pos['A']] == 0.9 and th[pos['A']] == 0.1


def test_la_red_fija_magnitud_y_angulo_en_la_fuente():
    """045:RF-5 — con pesos al azar, la red da en la fuente su consigna y su ángulo: antes el ángulo flotaba."""
    torch = pytest.importorskip('torch')
    torch.manual_seed(5)
    m = orc.muestra(_radial_y_mallada_con_acoplador_e_isla())
    disp = torch.device('cpu')                     # sin entrenar: solo la salida de la red, sin ocupar la GPU
    red = orc._red(8, 2)
    x, ar, e = orc._tensores(m, disp)
    with torch.no_grad():
        v, th = red(x, ar, e)
    fuente = torch.tensor(m.fuente)
    assert torch.equal(v[fuente], x[fuente, 4]) and torch.equal(th[fuente], x[fuente, 6])
    assert torch.all(th[fuente] == 0)


def test_isla_desenergizada_no_recibe_gold_cero():
    """045:RF-5 — una barra sin fuente no enseña «0 p.u.», ni una tensión que el grafo no puede explicar."""
    g = _radial_y_mallada_con_acoplador_e_isla()
    tensiones = {'A': 0.99, 'B': 0.0, 'I1': 0.0, 'I2': 0.97}
    m = orc.muestra(g, tensiones)
    pos = {n: i for i, n in enumerate(m.ids)}
    assert m.mascara[pos['A']]
    assert not m.mascara[pos['B']], 'a 0 p.u. no es una medida'
    assert not m.mascara[pos['I1']] and not m.mascara[pos['I2']]
    assert m.etiquetas_sin_fuente == 1, 'I2 tiene tensión medida y el grafo la deja sin fuente: se cuenta'


@pytest.mark.parametrize('red', ['radial', 'mallada', 'acopladores', 'transformador_y_banco'])
def test_gradiente_residuo_diferencias_finitas(red):
    """045:RF-7 — el gradiente del residuo contrastado con diferencias finitas: float64, red pequeña."""
    torch = pytest.importorskip('torch')
    disp = torch.device('cpu')                     # una fórmula, en float64: no es entrenar ni predecir
    nodos = {'S': _fuente(1.0), 'A': _nodo(0.3, 0.1), 'B': _nodo(0.2, 0.05), 'C': _nodo(0.1, 0.02)}
    ramas = [_linea('L1', 'S', 'A'), _linea('L2', 'A', 'B'), _linea('L3', 'B', 'C')]
    if red == 'mallada':
        ramas.append(_linea('L4', 'C', 'A', 0.5, 0.35))
    if red == 'acopladores':
        nodos['A2'] = _nodo(0.1, 0.02)
        ramas[1] = _linea('L2', 'A2', 'B')
        ramas.append(_acoplador('K', 'A', 'A2'))
    if red == 'transformador_y_banco':
        nodos['B'] = _nodo(0.2, 0.05, kv=0.4, banco_q_mvar=0.08)
        nodos['C'] = _nodo(0.1, 0.02, kv=0.4)
        ramas[1] = {'id': 'T', 'clase': 'ElmTr2', 'desde': 'A', 'hasta': 'B', 'cerrada': True, 'r_ohm': 0.9, 'x_ohm': 4.0,
                    'inom_ka': 0.03, 'u_desde_kv': 10.5, 'u_hasta_kv': 0.42,
                    'toma': {'posicion': 2.0, 'neutra': 0.0, 'paso_pct': 2.5, 'lado': 0.0, 'automatica': False}}
    m = orc.muestra(_grafo(nodos, ramas))
    f = orc._fisica(m, disp, 0.0, dtype=torch.float64)
    n = len(m.ids)
    rng = np.random.default_rng(7)
    v0 = np.where(m.fuente, 1.0, 0.97 + 0.02 * rng.random(n))        # lejos de |V| = 0, la singularidad
    th0 = np.where(m.fuente, 0.0, -0.02 * rng.random(n))

    def valor(vec: torch.Tensor) -> torch.Tensor:
        return orc._residuo_torch(f, vec[:n], vec[n:]).sum()

    x0 = torch.tensor(np.concatenate([v0, th0]), dtype=torch.float64, requires_grad=True)
    valor(x0).backward()
    analitico = x0.grad.detach().numpy()
    h = 1e-6
    numerico = np.zeros_like(analitico)
    base = x0.detach().clone()
    for i in range(len(base)):
        mas, menos = base.clone(), base.clone()
        mas[i] += h
        menos[i] -= h
        numerico[i] = float((valor(mas) - valor(menos)) / (2 * h))
    assert np.isclose(analitico, numerico, rtol=1e-4, atol=1e-6).all(), (analitico, numerico)
    # Y las dos versiones del residuo, la de la pérdida y la de la evaluación, son la misma cuenta.
    con_torch = np.sqrt(orc._residuo_torch(f, torch.tensor(v0), torch.tensor(th0)).detach().numpy())
    grupo, _real, exigir, _n = orc.barras_electricas(m)
    primero = np.unique(grupo, return_index=True)[1]
    assert np.allclose(con_torch, orc.residuo(m, v0, th0)[primero][exigir], rtol=1e-9)


def test_la_solucion_de_la_fisica_anula_el_residuo():
    """045:RF-7 — con relaciones y bancos, la solución del flujo cumple el balance que evalúa el residuo."""
    g = _grafo({'S': _fuente(1.0, kv=60.0), 'A': _nodo(0.0, 0.0, kv=10.0, banco_q_mvar=0.3),
                'B': _nodo(0.9, 0.3 - 0.3, kv=10.0, banco_q_mvar=0.3)},
               [{'id': 'T', 'clase': 'ElmTr2', 'desde': 'S', 'hasta': 'A', 'cerrada': True, 'r_ohm': 4.0, 'x_ohm': 30.0,
                 'inom_ka': 0.1, 'u_desde_kv': 60.0, 'u_hasta_kv': 10.5,
                 'toma': {'posicion': -2.0, 'neutra': 0.0, 'paso_pct': 1.25, 'lado': 0.0, 'automatica': False}},
                _linea('L', 'A', 'B')])
    p = orc.ModeloMallado().predecir(g)
    assert p['convergio'] and not p['fuera_de_dominio'], p['motivos']
    assert np.max(p['residuo']) < 1e-8


def test_transformador_y_banco_coinciden_con_pandapower():
    """045:RF-4 — una relación fuera de la nominal, una toma y un banco, contrastados con pandapower.

    La física de referencia con pandapower es la de la spec 082: aquí contrasta la de la PINN, sin duplicarla.
    """
    net = pp.create_empty_network(sn_mva=10.0)
    s = pp.create_bus(net, 60.0)
    a = pp.create_bus(net, 10.0)
    b = pp.create_bus(net, 10.0)
    pp.create_ext_grid(net, s, vm_pu=1.02)
    sn, vk, vkr, paso, posicion = 10.0, 8.0, 0.6, 1.25, 3
    pp.create_transformer_from_parameters(net, s, a, sn_mva=sn, vn_hv_kv=60.0, vn_lv_kv=10.5, vkr_percent=vkr, vk_percent=vk,
                                          pfe_kw=0.0, i0_percent=0.0, shift_degree=0.0, tap_side='hv', tap_neutral=0,
                                          tap_min=-8, tap_max=8, tap_step_percent=paso, tap_pos=posicion,
                                          tap_changer_type='Ratio')
    r_ohm, x_total = 0.8, 0.5
    pp.create_line_from_parameters(net, a, b, length_km=1.0, r_ohm_per_km=r_ohm, x_ohm_per_km=x_total, c_nf_per_km=0.0, max_i_ka=1.0)
    pp.create_load(net, b, p_mw=2.5, q_mvar=1.0)
    pp.create_shunt(net, b, q_mvar=0.6)              # positivo consume en pandapower; abajo, -0.6 de banco
    net.shunt.loc[0, 'q_mvar'] = -0.6
    pp.runpp(net, trafo_model='pi', calculate_voltage_angles=False, tolerance_mva=1e-10)
    z_base = 60.0 ** 2 / sn
    rama = {'id': 'T', 'clase': 'ElmTr2', 'desde': 'S', 'hasta': 'A', 'cerrada': True, 'r_ohm': vkr / 100 * z_base,
            'x_ohm': (vk ** 2 - vkr ** 2) ** 0.5 / 100 * z_base, 'inom_ka': 0.1, 'u_desde_kv': 60.0, 'u_hasta_kv': 10.5,
            'toma': {'posicion': float(posicion), 'neutra': 0.0, 'paso_pct': paso, 'lado': 0.0, 'automatica': False}}
    g = _grafo({'S': _fuente(1.02, kv=60.0), 'A': _nodo(kv=10.0),
                'B': _nodo(2.5, 1.0 - 0.6, kv=10.0, banco_q_mvar=0.6)}, [rama, _linea('L', 'A', 'B', r_ohm, x_total)])
    p = orc.ModeloMallado().predecir(g)
    pos = {n: i for i, n in enumerate(p['ids'])}
    assert p['convergio']
    assert p['v'][pos['A']] == pytest.approx(net.res_bus.vm_pu[a], abs=1e-5)
    assert p['v'][pos['B']] == pytest.approx(net.res_bus.vm_pu[b], abs=1e-5)
    # En un árbol, el barrido dice lo mismo: nadie queda con la física de antes.
    radial = orc.ModeloRadial().predecir(g)
    assert radial['v'][pos['B']] == pytest.approx(p['v'][pos['B']], abs=1e-6)


def test_sin_relaciones_el_flujo_no_cambia():
    """045:RF-4 — una red sin transformadores ni bancos da exactamente lo mismo que antes de las relaciones."""
    rnd = random.Random(21)
    nodos = {'S': _fuente(1.0), **{f'N{i}': _nodo(rnd.uniform(0.05, 0.2), rnd.uniform(0.01, 0.05)) for i in range(8)}}
    ramas = [_linea(f'L{i}', 'S' if i == 0 else f'N{i - 1}', f'N{i}', rnd.uniform(0.2, 0.6), rnd.uniform(0.2, 0.5)) for i in range(8)]
    m = orc.muestra(_grafo(nodos, ramas))
    assert (m.ru == 1.0).all() and (m.rw == 1.0).all() and (m.s_shunt == 0).all()
    from convertersmartgrid.digital_twin.flujo import SistemaMallado

    sin = SistemaMallado(m.aristas, m.z, m.fuente, m.x[:, 4], m.alimentado).resolver(m.s_carga)
    con = orc.sistema_de(m).resolver(m.s_carga)
    assert np.array_equal(sin.v, con.v) and np.array_equal(sin.theta, con.theta)


def _trafo(**cambios) -> dict:
    return {'id': 'T', 'clase': 'ElmTr2', 'desde': 'S', 'hasta': 'A', 'cerrada': True, 'r_ohm': 1.0, 'x_ohm': 4.0, 'inom_ka': 0.1,
            'toma': {'posicion': 0.0, 'neutra': 0.0, 'paso_pct': 1.0, 'lado': 0.0, 'automatica': False}, **cambios}


def _base(**extra) -> dict:
    return _grafo({'S': _fuente(1.0), 'A': _nodo(0.1, 0.01)}, [_trafo()], **extra)


@pytest.mark.parametrize('cambio,texto', [
    (lambda g: g['alcance_fisico']['no_representados'].update(ElmVoltreg=['R1']), 'ElmVoltreg'),
    (lambda g: g['alcance_fisico']['no_representados'].update(ElmTr3=['T3']), 'ElmTr3'),
    (lambda g: g.pop('alcance_fisico'), 'alcance'),
    (lambda g: g['controles'].pop('comldf'), 'ComLdf'),
    (lambda g: g['controles']['comldf'].pop('iopt_at'), 'iopt_at'),
    (lambda g: g['controles']['comldf'].update(iopt_net=1), 'desequilibrado'),
    (lambda g: (g['controles']['comldf'].update(iopt_at=1), g['ramas'][0]['toma'].update(automatica=True)), 'automática'),
    (lambda g: (g['controles']['comldf'].update(iopt_asht=1), g.update(bancos=[{'id': 'B', 'en_servicio': True}])), 'iopt_asht'),
    (lambda g: g['nodos']['S'].update(v_pu=None), 'consigna'),
    (lambda g: g['nodos'].pop('S') and g['nodos']['A'].update(fuente=False), 'ninguna fuente'),
    (lambda g: g['ramas'][0].update(faltan=['nntap']), 'nntap'),
    (lambda g: g.update(generadores=[{'id': 'G', 'en_servicio': True, 'control': 'constv'}]), 'control'),
    (lambda g: g.update(version=2), 'versión 2'),
])
def test_fisica_incompleta_bloquea(cambio, texto):
    """045:RF-4 — un equipo o control que la física no representa se rechaza con su motivo, no se aproxima."""
    assert validar_alcance_fisico(_base()) == ()
    g = _base()
    cambio(g)
    motivos = validar_alcance_fisico(g)
    assert any(texto in m for m in motivos), motivos
    if 'S' in g['nodos']:
        p = orc.ModeloMallado().predecir(g)
        assert p['fuera_de_dominio'] and p['motivos'], 'la física tampoco lo da por bueno'
        assert orc.ModeloRadial().predecir(g)['fuera_de_dominio']


def test_toma_automatica_sin_iopt_at_esta_en_su_posicion():
    """045:RF-4 — sin el ajuste automático en el flujo, la toma está donde se escribió: eso sí se representa."""
    g = _base()
    g['ramas'][0]['toma']['automatica'] = True
    assert validar_alcance_fisico(g) == ()


def test_iopt_lev_bloquea_solo_si_cambio_el_consumo():
    """045:RF-4 — con la adaptación del modelo, el consumo medido decide: CA101 consumía el 73 % de lo escrito."""
    g = _base()
    g['controles']['comldf']['iopt_lev'] = 1
    g['nodos']['A'].update(carga_p_mw=0.1, carga_q_mvar=0.01, carga_p_efectiva_mw=0.1, carga_q_efectiva_mvar=0.01)
    assert validar_alcance_fisico(g) == ()
    g['nodos']['A']['carga_p_efectiva_mw'] = 0.073
    assert any('iopt_lev' in m for m in validar_alcance_fisico(g))
    g['nodos']['A']['carga_p_efectiva_mw'] = None
    assert any('no se midió' in m for m in validar_alcance_fisico(g))


def test_dos_fuentes_con_angulos_distintos_en_una_isla():
    """045:RF-5 — sin los desfases de grupo no se comparan dos ángulos de una misma isla; en islas separadas, sí vale."""
    g = _grafo({'S1': _fuente(1.0, angulo_deg=0.0), 'S2': _fuente(1.0, angulo_deg=30.0), 'A': _nodo(0.1, 0.0)},
               [_linea('L1', 'S1', 'A'), _linea('L2', 'A', 'S2')])
    assert any('ángulos' in m for m in validar_alcance_fisico(g))
    g['ramas'][1]['cerrada'] = False
    assert validar_alcance_fisico(g) == ()


def test_la_muestra_conserva_el_contrato_de_su_grafo():
    """045:RF-4 — el grafo que se rehace desde una muestra no olvida los motivos ni las relaciones de su original."""
    g = _base()
    g['alcance_fisico']['no_representados']['ElmTr3'] = ['T3']
    g['ramas'][0].update(u_desde_kv=10.5, u_hasta_kv=10.0)
    g['nodos']['A']['banco_q_mvar'] = 0.2
    m = orc.muestra(g)
    rehecho = orc._grafo_de_muestra(m)
    assert rehecho['version'] == VERSION_GRAFO
    assert validar_alcance_fisico(rehecho) == validar_alcance_fisico(g) != ()
    m2 = orc.muestra(rehecho)
    assert np.allclose(m2.z, m.z) and np.allclose(m2.ru, m.ru) and np.allclose(m2.s_shunt, m.s_shunt)
    assert np.allclose(m2.s_carga, m.s_carga)
    assert np.allclose(orc.ModeloMallado().predecir(rehecho)['v'], orc.ModeloMallado().predecir(g)['v'])


def test_escalar_la_demanda_no_escala_central_ni_banco():
    """045:RF-3 — al escalar la demanda solo cambia la carga: con la neta, la central también crecía."""
    d = _nodo(0.5 - 0.2, 0.1 - 0.05 - 0.2, carga_p_mw=0.5, carga_q_mvar=0.1, gen_p_mw=0.2, gen_q_mvar=0.05, banco_q_mvar=0.2)
    e = orc.escalar_nodo(d, 2.0)
    assert e['p_mw'] == pytest.approx(1.0 - 0.2) and e['q_mvar'] == pytest.approx(0.2 - 0.05 - 0.2)
    assert e['gen_p_mw'] == 0.2 and e['banco_q_mvar'] == 0.2 and e['carga_p_mw'] == 1.0
    assert orc.escalar_nodo(_nodo(0.1, 0.02), 3.0)['p_mw'] == pytest.approx(0.3), 'un grafo sin partes, como antes'
    grafo = _base()
    assert orc.perturbar(grafo, orc.Escenario(1.0, ()))['version'] == VERSION_GRAFO


def test_perdida_con_sus_terminos_por_separado():
    """045:RF-6 — datos, física y fronteras por separado, con sus unidades y sin un peso supuesto."""
    g = _radial_y_mallada_con_acoplador_e_isla()
    sol = orc.ModeloMallado().predecir(g)
    tensiones = {n: float(v) for n, v in zip(sol['ids'], sol['v'], strict=True) if v > 0}
    m = orc.muestra(g, tensiones)
    pesos = {'datos': 1.0, 'fisica': 1e-4, 'fronteras': 0.5}
    exacta = orc.perdidas_fisicas(sol, m, pesos=pesos)
    assert exacta['datos'] == pytest.approx(0.0, abs=1e-20) and exacta['fisica'] < 1e-16 and exacta['fronteras'] == 0.0
    assert exacta['unidades'] == {'datos': 'p.u.²', 'fisica': 'p.u.²', 'fronteras': 'p.u.²'}
    # Solo se mueve la tensión de datos: el error de un término no se reparte en los otros.
    pos = {n: i for i, n in enumerate(m.ids)}
    otra = {**sol, 'v': sol['v'].copy()}
    otra['v'][pos['A']] += 0.01
    t = orc.perdidas_fisicas(otra, m, pesos=pesos)
    assert t['datos'] > 0 and t['fisica'] > 0 and t['fronteras'] == 0.0
    assert t['total'] == pytest.approx(t['datos'] + 1e-4 * t['fisica'])
    # La fuente fuera de su consigna y la isla con tensión son error de fronteras.
    mala = {**sol, 'v': sol['v'].copy(), 'theta': sol['theta'].copy()}
    mala['v'][pos['S1']] += 0.02
    mala['theta'][pos['S2']] = 0.01
    mala['v'][pos['I1']] = 0.5
    t = orc.perdidas_fisicas(mala, m, pesos=pesos)
    assert t['fronteras'] > 0
    assert t['total'] == pytest.approx(t['datos'] + 1e-4 * t['fisica'] + 0.5 * t['fronteras'])
    with pytest.raises(ValueError, match='fronteras'):
        orc.perdidas_fisicas(sol, m, pesos={'datos': 1.0, 'fisica': 1.0})


def test_sin_medidas_los_datos_son_ausencia_no_cero():
    """045:RF-6 — sin barras medidas, el término de datos es ``None``: no aparenta un ajuste perfecto."""
    m = orc.muestra(_radial_y_mallada_con_acoplador_e_isla())
    sol = orc.ModeloMallado().predecir_muestra(m)
    t = orc.perdidas_fisicas(sol, m, pesos={'datos': 1.0, 'fisica': 1.0, 'fronteras': 1.0})
    assert t['datos'] is None and t['total'] == pytest.approx(t['fisica'] + t['fronteras'])


def test_los_terminos_de_la_red_y_de_la_evaluacion_son_la_misma_cuenta():
    """045:RF-6 — la pérdida de PyTorch da los mismos términos que ``perdidas_fisicas``."""
    torch = pytest.importorskip('torch')
    g = _radial_y_mallada_con_acoplador_e_isla()
    sol = orc.ModeloMallado().predecir(g)
    tensiones = {n: float(v) + 0.003 for n, v in zip(sol['ids'], sol['v'], strict=True) if v > 0}
    m = orc.muestra(g, tensiones)
    disp = torch.device('cpu')
    f = orc._fisica(m, disp, 0.0, dtype=torch.float64)
    v, th = sol['v'].copy(), sol['theta'].copy()
    v += 0.002
    th += 0.001
    t = orc._terminos_torch(f, torch.tensor(v), torch.tensor(th), torch.tensor(m.v), torch.tensor(m.mascara))
    n = orc.perdidas_fisicas({'v': v, 'theta': th}, m, pesos={'datos': 1.0, 'fisica': 1.0, 'fronteras': 1.0})
    for clave in ('datos', 'fisica', 'fronteras'):
        assert float(t[clave]) == pytest.approx(n[clave], rel=1e-9), clave


def test_acoplador_sigue_siendo_acoplador():
    """045:RF-5 — el tope de un acoplador no cambia: se une la barra y no se mete 10⁶ p.u. en la matriz."""
    m = orc.muestra(_radial_y_mallada_con_acoplador_e_isla())
    pos = {n: i for i, n in enumerate(m.ids)}
    assert m.sistema is None
    sis = orc.sistema_de(m)
    assert sis.indice[pos['S1']] == sis.indice[pos['S1b']]
    assert np.abs(m.z).min() < Z_ACOPLADOR
