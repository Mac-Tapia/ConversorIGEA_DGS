"""Spec 074: la política con atención respeta la máscara, aprende en una red pequeña y vale en una red que no vio."""
from __future__ import annotations

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from convertersmartgrid.madrl_obras import (
    EntornoObras,
    EntornoPlano,
    ParametrosObras,
)
from convertersmartgrid.madrl_politica import (
    RASGOS,
    Entrenamiento,
    crear_politica,
    entrenar_ppo,
    evaluar_en,
    observacion_grafo,
)

P = ParametrosObras(0.95, 1.05, 100.0, 0.3, 10.0, candidatos=5, max_bancos=5)


def _red(n: int, p_mw: float, prefijo='A'):
    nodos = {f'{prefijo}{i}': {'kv': 10.0, 'p_mw': p_mw, 'q_mvar': p_mw * 0.85} for i in range(1, n)}
    nodos[f'{prefijo}0'] = {'kv': 10.0, 'fuente': True, 'v_pu': 1.0}
    ramas = [{'id': f'{prefijo}L{i}', 'clase': 'ElmLne', 'desde': f'{prefijo}{i}', 'hasta': f'{prefijo}{i + 1}', 'r_ohm': 0.6,
              'x_ohm': 0.5, 'inom_ka': 1.0, 'cerrada': True} for i in range(n - 1)]
    return EntornoPlano(EntornoObras({'nodos': nodos, 'ramas': ramas}, {prefijo: list(nodos)}, P))


def test_la_observacion_es_la_red_y_sus_obras():
    """074:RF-1 — rasgos por barra, la barra de cada obra y la máscara del entorno."""
    plano = _red(7, 0.35)
    o = observacion_grafo(plano)
    assert o['x'].shape == (7, RASGOS) and len(o['sitio']) == len(plano.todas)
    assert (o['mascara'] == plano.mascara()).all()


def test_la_politica_nunca_elige_fuera_de_la_mascara():
    """074:RF-2 — lo prohibido queda con probabilidad nula, en redes de distinto tamaño."""
    torch.manual_seed(0)
    politica = crear_politica()
    for plano in (_red(7, 0.35), _red(12, 0.2)):
        plano.reiniciar()
        o = observacion_grafo(plano)
        logits, valor = politica(o)
        prob = torch.softmax(logits, 0)
        assert float(prob[torch.as_tensor(~o['mascara'])].sum()) < 1e-6 and valor.shape == ()


def test_aprende_y_se_mide_en_redes_que_no_vio():
    """074:RF-6 / 074:RF-9 — en CPU y con pocas iteraciones: la curva mejora y se evalúa en redes no vistas."""
    entrenada = _red(7, 0.35)
    _politica, curva = entrenar_ppo(entrenada, Entrenamiento(iteraciones=12, episodios_por_iteracion=6, epocas=3))
    assert max(curva[-3:]) > curva[0], curva
    nuevas = [_red(7, 0.33, 'B'), _red(8, 0.3, 'C')]
    aprendido = evaluar_en(nuevas, _politica)
    assert len(aprendido) == 2 and all(a['control'] == 'gatv2' for a in aprendido)
