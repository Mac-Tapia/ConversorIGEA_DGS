"""Spec 074: el entorno multiagente de obras, su máscara, sus penalidades y sus controles."""
from __future__ import annotations

import copy
import itertools

import numpy as np
import pytest

from convertersmartgrid.digital_twin.oraculo import ModeloRadial, muestra
from convertersmartgrid.madrl_obras import (
    NINGUNA,
    EntornoError,
    EntornoObras,
    EntornoPlano,
    Lagrange,
    ParametrosObras,
    candidatos_de,
    cargas_de_rama,
    comparar_controles,
    control_escalera,
    control_nsga2,
    evaluar_grafo,
    fidelidad,
    puerta_del_aprendizaje,
    zonas_por_fuente,
)

P = ParametrosObras(tension_min_pu=0.95, tension_max_pu=1.05, cargabilidad_max_pct=100.0, banco_mvar=0.3, costo_banco=10.0,
                    costo_terna_km=50.0, candidatos=4, max_bancos=2, max_pasos=6)


def _linea(prefijo: str, n: int, p_mw: float, r: float = 0.6, inom: float = 1.0, km: float | None = 1.0) -> tuple[dict, list]:
    nodos = {f'{prefijo}{i}': {'kv': 10.0, 'p_mw': p_mw, 'q_mvar': p_mw * 0.5} for i in range(1, n)}
    nodos[f'{prefijo}0'] = {'kv': 10.0, 'fuente': True, 'v_pu': 1.0}
    ramas = [{'id': f'{prefijo}L{i}', 'clase': 'ElmLne', 'desde': f'{prefijo}{i}', 'hasta': f'{prefijo}{i + 1}', 'r_ohm': r,
              'x_ohm': r / 2, 'inom_ka': inom, 'cerrada': True, **({'km': km} if km else {})} for i in range(n - 1)]
    return nodos, ramas


def _red(cargado=True, km=1.0):
    n1, r1 = _linea('A', 8, 0.4 if cargado else 0.01, km=km)
    n2, r2 = _linea('B', 6, 0.01, km=km)
    return {'nodos': {**n1, **n2}, 'ramas': r1 + r2}, {'A': [f'A{i}' for i in range(8)], 'B': [f'B{i}' for i in range(6)]}


def test_la_fisica_mide_y_una_isla_no_es_subtension():
    """074:RF-1 — la red cargada viola; la ligera, no; una barra sin fuente no cuenta como subtensión."""
    g, _z = _red()
    e = evaluar_grafo(g, P)
    assert not e.en_norma and e.subtension > 0 and e.vm_min < 0.95
    assert evaluar_grafo(_red(cargado=False)[0], P).en_norma
    g2, _z = _red(cargado=False)
    g2['nodos']['ISLA'] = {'kv': 10.0, 'p_mw': 1.0}
    assert evaluar_grafo(g2, P).en_norma
    # Una rama pequeña se sobrecarga sin que caiga la tensión.
    n, r = _linea('C', 3, 2.0, r=0.01, inom=0.05)
    assert evaluar_grafo({'nodos': n, 'ramas': r}, P).sobrecarga > 0


def test_la_carga_no_depende_de_la_impedancia_de_un_tramo_corto():
    """074:RF-1 — el oráculo sube la z de los tramos cortos; la corriente sale de la suma aguas abajo."""
    n, r = _linea('C', 3, 1.0, r=1e-7, inom=0.1)
    m = muestra({'nodos': n, 'ramas': r})
    o = ModeloRadial().predecir({'nodos': n, 'ramas': r})
    cargas = cargas_de_rama(m, np.asarray(o['v']), np.asarray(o['theta']))
    # 2 MW + 1 Mvar en 10 kV pasan por el primer tramo: |S| / (√3·10 kV) = 129 A sobre 100 A.
    assert cargas['CL0'] == pytest.approx(100 * np.hypot(2, 1) / (3 ** 0.5 * 10) / 0.1, rel=0.01)
    assert cargas['CL1'] == pytest.approx(cargas['CL0'] / 2, rel=0.01)


def test_el_entorno_debe_reproducir_lo_medido():
    """074:RF-7 — con lo que da la propia física vale; con otra medida, o sin ella, no."""
    n, r = _linea('C', 4, 0.1)
    g = {'nodos': n, 'ramas': r}
    m = muestra(g)
    o = ModeloRadial().predecir(g)
    v, th = np.asarray(o['v']), np.asarray(o['theta'])
    propias = cargas_de_rama(m, v, th)
    tensiones = {x: float(v[i]) for i, x in enumerate(m.ids)}
    assert fidelidad(g, tensiones, propias)['vale'] is True
    assert fidelidad(g, {x: u - 0.05 for x, u in tensiones.items()}, propias)['vale'] is False
    assert fidelidad(g, tensiones, {x: c + 50 for x, c in propias.items()})['vale'] is False
    # Una sola rama muy errada, con la media baja: esa rama es la que decidiría una obra.
    una = {x: c + (30 if x == 'CL0' else 0) for x, c in propias.items()}
    assert fidelidad(g, tensiones, una, max_error_carga_pct=100)['vale'] is False
    sin = fidelidad(g, {}, {})
    assert sin['vale'] is False and 'medidas' in sin['motivo']


def test_una_zona_por_cada_fuente():
    """074:RF-1 — sale de la red, sin tabla de alimentadores; una barra sin fuente no entra en ninguna."""
    n1, r1 = _linea('A', 3, 0.1)
    n2, r2 = _linea('B', 2, 0.1)
    z = zonas_por_fuente({'nodos': {**n1, **n2, 'ISLA': {'kv': 10.0}}, 'ramas': r1 + r2})
    assert z == {'A0': ['A0', 'A1', 'A2'], 'B0': ['B0', 'B1']}
    r1[0]['cerrada'] = False
    assert zonas_por_fuente({'nodos': n1, 'ramas': r1})['A0'] == ['A0']


def test_el_entorno_no_toca_el_grafo_de_entrada():
    """074:RF-1 — el mismo grafo sirve de nuevo: la red real no cambia por entrenar."""
    g, z = _red()
    antes = copy.deepcopy(g)
    e = EntornoObras(g, z, P)
    control_escalera(e)
    assert g == antes and e.costo > 0
    with pytest.raises(EntornoError):
        EntornoObras(g, {}, P)


def test_obras_solo_si_hay_problemas():
    """074:RF-2 — un alimentador en norma solo puede no hacer nada, aunque otro tenga problemas."""
    g, z = _red()
    e = EntornoObras(g, z, P)
    assert e.mascara('B').tolist() == [True] + [False] * len(e.acciones['B'])
    assert e.mascara('A').sum() > 1
    limpia = EntornoObras(*_red(cargado=False), P)
    assert limpia.mascara('A').sum() == 1
    r = control_escalera(limpia)
    assert r['costo'] == 0 and r['obras'] == [] and r['en_norma']


def test_la_escalera_pone_los_bancos_antes_que_la_terna():
    """074:RF-2 — mientras quepan bancos no se ofrece terna; agotados, sí."""
    e = EntornoObras(*_red(), P)
    tipos = [a.tipo for a in e.acciones['A']]
    assert 'banco' in tipos and 'terna' in tipos

    def permitidos():
        return {tipos[i - 1] for i in np.flatnonzero(e.mascara('A')) if i != NINGUNA}

    assert permitidos() == {'banco'}
    for _ in range(P.max_bancos):
        if e.estado.en_norma:
            break
        e.paso({'A': int(np.flatnonzero(e.mascara('A'))[1]), 'B': NINGUNA})
    assert not e.estado.en_norma, 'la red de prueba necesita más de sus bancos para que se vea la terna'
    assert permitidos() == {'terna'}
    with pytest.raises(EntornoError, match='máscara'):
        EntornoObras(*_red(), P).paso({'B': 1})


def test_sin_metrado_ni_costo_no_hay_terna():
    """074:RF-3 — sin largo o sin costo declarado no se supone: la terna no se ofrece."""
    g, z = _red(km=None)
    assert {a.tipo for a in candidatos_de(g, set(z['A']), P)} == {'banco'}
    g, z = _red()
    sin_costo = ParametrosObras(0.95, 1.05, 100.0, 0.3, 10.0)
    assert {a.tipo for a in candidatos_de(g, set(z['A']), sin_costo)} == {'banco'}
    assert any(a.costo == 50.0 for a in candidatos_de(g, set(z['A']), P) if a.tipo == 'terna')


def test_las_penalidades_se_aprenden_y_la_recompensa_paga_el_costo():
    """074:RF-4 — el multiplicador sube al incumplir y baja al cumplir; la obra cuesta y violar cuesta más."""
    g, z = _red()
    violacion = evaluar_grafo(g, P)
    lag = Lagrange()
    antes = lag.multiplicadores['subtension']
    lag.actualizar(violacion)
    assert lag.multiplicadores['subtension'] > antes
    en_norma = evaluar_grafo(_red(cargado=False)[0], P)
    for _ in range(10000):
        lag.actualizar(en_norma)
    assert lag.multiplicadores['subtension'] == 0.0, 'nunca negativo'
    assert EntornoObras(g, z, P).paso({'A': NINGUNA, 'B': NINGUNA})[0] < 0, 'violar y no hacer nada se paga'
    assert EntornoObras(*_red(cargado=False), P).paso({'A': NINGUNA, 'B': NINGUNA})[0] == 0.0
    con_obra = EntornoObras(g, z, P, Lagrange(multiplicadores={}))
    assert con_obra.paso({'A': int(np.flatnonzero(con_obra.mascara('A'))[1]), 'B': NINGUNA})[0] == -1.0, 'sin penalidad, el costo'


def _red_con_arreglo():
    """Una red fuera de norma que cinco bancos dejan en norma."""
    n = {f'A{i}': {'kv': 10.0, 'p_mw': 0.35, 'q_mvar': 0.3} for i in range(1, 7)}
    n['A0'] = {'kv': 10.0, 'fuente': True, 'v_pu': 1.0}
    r = [{'id': f'AL{i}', 'clase': 'ElmLne', 'desde': f'A{i}', 'hasta': f'A{i + 1}', 'r_ohm': 0.6, 'x_ohm': 0.5, 'inom_ka': 1.0,
          'cerrada': True} for i in range(6)]
    return {'nodos': n, 'ramas': r}, {'A': list(n)}, ParametrosObras(0.95, 1.05, 100.0, 0.3, 10.0, candidatos=5, max_bancos=5)


def test_rendirse_no_sale_mas_barato_que_arreglar():
    """074:RF-4 — la violación se cobra al final y pesa más que las obras, con los multiplicadores iniciales."""
    g, z, p = _red_con_arreglo()
    rendirse = EntornoObras(g, z, p).paso({'A': NINGUNA})[0]
    e = EntornoObras(g, z, p)
    assert not e.estado.en_norma
    total, fin = 0.0, False
    while not fin:
        r_paso, fin = e.paso({'A': int(np.flatnonzero(e.mascara('A'))[1])})
        total += r_paso
        if not fin:
            assert r_paso == -1.0, 'a medio camino solo se paga la obra'
    assert e.estado.en_norma and total > rendirse


def test_un_paso_sin_obras_termina_el_episodio():
    """074:RF-1 — sin gasto no hay nada más que esperar: un agente no se queda dando vueltas."""
    assert EntornoObras(*_red(), P).paso({'A': NINGUNA, 'B': NINGUNA})[1] is True


def test_los_agentes_cooperan_en_la_misma_red():
    """074:RF-1 — pasos simultáneos: los dos gastan en un mismo paso y la recompensa es común."""
    n1, r1 = _linea('A', 8, 0.4)
    n2, r2 = _linea('B', 8, 0.4)
    e = EntornoObras({'nodos': {**n1, **n2}, 'ramas': r1 + r2}, {'A': list(n1), 'B': list(n2)}, P)
    e.paso({'A': int(np.flatnonzero(e.mascara('A'))[1]), 'B': int(np.flatnonzero(e.mascara('B'))[1])})
    assert e.costo == 2 * P.costo_banco and len(e.obras()) == 2


def test_nsga2_y_escalera_sobre_las_mismas_obras():
    """074:RF-5 — los dos resuelven la misma red; NSGA-II no paga más que la óptima por fuerza bruta."""
    g, z, p = _red_con_arreglo()
    e = EntornoObras(g, z, p)
    assert not e.estado.en_norma, 'sin problemas, esta prueba se cumpliría con cero obras'
    nsga = control_nsga2(e, generaciones=25, poblacion=24)
    esc = control_escalera(EntornoObras(g, z, p))
    assert nsga['en_norma'] and esc['en_norma']
    bancos = e.acciones['A']
    mejor = None
    for k in range(len(bancos) + 1):
        for combo in itertools.combinations(bancos, k):
            copia = copy.deepcopy(g)
            for a in combo:
                copia['nodos'][a.elemento]['q_mvar'] -= p.banco_mvar
            if evaluar_grafo(copia, p).en_norma and (mejor is None or k * p.costo_banco < mejor):
                mejor = k * p.costo_banco
    assert mejor is not None and nsga['costo'] == mejor
    assert esc['costo'] >= mejor, 'la escalera nunca puede ganar a la óptima'


def test_el_entorno_plano_es_el_mismo_entorno():
    """074:RF-9 — una obra por paso, con la máscara del entorno, y las penalidades suben al terminar sin cumplir."""
    e = EntornoObras(*_red(), P)
    plano = EntornoPlano(e)
    obs = plano.reiniciar()
    assert obs.shape == (plano.tam_observacion,) and plano.n_acciones == 1 + sum(len(x) for x in e.acciones.values())
    m = plano.mascara()
    assert m[0] and m.sum() > 1 and not any(m[1 + i] for i, (a, _x) in enumerate(plano.todas) if a == 'B')
    elegida = int(np.flatnonzero(m)[1])
    obs2, r, fin = plano.paso(elegida)
    assert e.costo == P.costo_banco and r < 0 and not fin and obs2[4 + 2 * (elegida - 1)] == 1.0
    antes = e.lagrange.multiplicadores['subtension']
    _o, _r, fin = plano.paso(0)
    assert fin and e.lagrange.multiplicadores['subtension'] > antes
    assert plano.reiniciar()[4] == 0.0 and e.costo == 0.0


def test_comparar_deja_la_referencia():
    """074:RF-5 — el punto de partida y los dos controles, con sus evaluaciones."""
    g, z = _red()
    r = comparar_controles(g, z, P, medir_nsga2=lambda e: control_nsga2(e, generaciones=5, poblacion=10))
    assert r['inicio']['en_norma'] is False and r['acciones']['A'] > 0
    assert r['escalera']['control'] == 'escalera' and r['nsga2']['evaluaciones'] > 0


@pytest.mark.parametrize('aprendido, referencia, sigue, palabra', [
    ([{'en_norma': True, 'costo': 10}], [{'en_norma': True, 'costo': 10}], True, 'referencia'),
    ([{'en_norma': False, 'costo': 1}], [{'en_norma': True, 'costo': 10}], False, 'norma'),
    ([{'en_norma': True, 'costo': 11}], [{'en_norma': True, 'costo': 10}], False, 'cuesta'),
    ([], [], False, 'no vistos'),
    ([{'en_norma': True, 'costo': 1}], [], False, 'no vistos'),
])
def test_la_puerta_no_deja_seguir_sin_superar_al_control(aprendido, referencia, sigue, palabra):
    """074:RF-6 — 100 % en norma y costo no peor; barato y fuera de norma no pasa."""
    r = puerta_del_aprendizaje(aprendido, referencia)
    assert r['sigue'] is sigue and palabra in r['motivo']
