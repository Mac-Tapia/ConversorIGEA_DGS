"""Spec 045, RF-15 y RF-16: la red del híbrido sin entrenar, construida en la CPU solo para comprobar fórmulas.

Como el gradiente de la T2, es una fórmula y no un modelo: la salida inicial, el estado sin corrección y la guarda de la
predicción. El entrenamiento y la ablación con datos reales son de la GPU (045 T6).
"""
from __future__ import annotations

import random

import numpy as np
import pytest

torch = pytest.importorskip('torch')

from test_benchmark_pinn import _red as red_radial

from convertersmartgrid.adaptadores.digital_twin import oraculo as orc

CPU = torch.device('cpu')
TOPE = orc.Puertas().residuo_max


def _muestra(semilla: int = 3, n: int = 12) -> orc.Muestra:
    g = red_radial(random.Random(semilla), n, semilla)
    p = orc.ModeloMallado().predecir(g)
    return orc.muestra(g, dict(zip(p['ids'], map(float, p['v']), strict=True)))


def _base(m: orc.Muestra, x) -> tuple[np.ndarray, np.ndarray]:
    """Lo que da la red con la corrección nula: la consigna en la fuente y la física en el resto."""
    es_fuente = x[:, 3] > 0.5
    return torch.where(es_fuente, x[:, 4], x[:, 5]).numpy(), x[:, 6].numpy()


def test_la_correccion_empieza_en_cero():
    """045:RF-15 — sin entrenar, el híbrido da exactamente la física: la capa final empieza a cero."""
    torch.manual_seed(0)
    m = _muestra()
    red = orc._red(16, 3)
    x, ar, e = orc._tensores(m, CPU)
    with torch.no_grad():
        v, th = red(x, ar, e)
    v_base, th_base = _base(m, x)
    assert np.array_equal(v.numpy(), v_base), 'la corrección inicial no es nula: el híbrido arranca fuera de la física'
    assert np.array_equal(th.numpy(), th_base)


def test_el_estado_sin_correccion_da_la_fisica():
    """045:RF-15 — con pesos ya aprendidos, el estado de partida que hay que mejorar es la física exacta."""
    fn = getattr(orc, '_estado_sin_correccion', None)
    assert fn is not None, 'no hay estado sin corrección con que comparar las épocas'
    torch.manual_seed(1)
    m = _muestra(4)
    red = orc._red(16, 3)
    with torch.no_grad():
        for p in red.salida[-1].parameters():
            p.normal_(0.0, 1.0)
    x, ar, e = orc._tensores(m, CPU)
    with torch.no_grad():
        assert not np.array_equal(red(x, ar, e)[0].numpy(), _base(m, x)[0])
        red.load_state_dict(fn(red))
        assert np.array_equal(red(x, ar, e)[0].numpy(), _base(m, x)[0])
    sin_salida = torch.nn.Linear(2, 2)
    assert fn(sin_salida) is None


def _oraculo_con_correccion(m: orc.Muestra, sesgo: float) -> orc.OraculoPINN:
    torch.manual_seed(2)
    cfg = orc.Entrenamiento(ocultas=16, pasos=3)
    red = orc._red(cfg.ocultas, cfg.pasos)
    with torch.no_grad():
        red.salida[-1].weight.zero_()
        red.salida[-1].bias.copy_(torch.tensor([sesgo, 0.0]))
    x = m.x
    dominio = {'x_min': x.min(axis=0).tolist(), 'x_max': x.max(axis=0).tolist(), 'nodos': [len(m.ids), len(m.ids)],
               'redes': [orc.red_de(m)], 'version_grafo': m.version}
    return orc.OraculoPINN([red.state_dict()] * 3, cfg, dominio)


def test_la_prediccion_no_deja_el_residuo_sobre_el_tope(monkeypatch):
    """045:RF-16 — una corrección que rompe el balance se recorta hacia la física hasta quedar en el tope, y se dice."""
    monkeypatch.setattr(orc, 'dispositivo', lambda *_a, **_k: CPU)
    m = _muestra(5)
    grafo = orc._grafo_de_muestra(m)
    fisica = orc.ModeloMallado().predecir(grafo)
    p = _oraculo_con_correccion(m, 3.0).predecir(grafo)        # +0,0995 p.u. en cada barra libre
    assert float(np.mean(p['residuo'])) <= TOPE, f"residuo {np.mean(p['residuo']):.3g} sobre el tope {TOPE}"
    assert p.get('escala_correccion', 1.0) < 1.0
    assert np.mean(np.abs(p['v'] - fisica['v'])) < 0.0995
    limpio = _oraculo_con_correccion(m, 0.0).predecir(grafo)
    assert limpio.get('escala_correccion') == 1.0
    assert np.allclose(limpio['v'], fisica['v'], atol=1e-6)


def test_la_guarda_no_esconde_el_desacuerdo_de_los_miembros(monkeypatch):
    """045:RF-16 — la incertidumbre es la dispersión de los miembros antes de la guarda: recortar la corrección no la
    reduce. Multiplicarla por la fracción usada la dejaba en 0 con la carga alta (MEJ30, T6 en la GPU, 2026-11-21)."""
    monkeypatch.setattr(orc, 'dispositivo', lambda *_a, **_k: CPU)
    m = _muestra(5)
    grafo = orc._grafo_de_muestra(m)
    base = _oraculo_con_correccion(m, 3.0)
    estados = []
    for sesgo in (2.0, 3.0, 4.0):
        estado = {k: w.clone() for k, w in base.estados[0].items()}
        estado['salida.2.bias'] = torch.tensor([sesgo, 0.0])
        estados.append(estado)
    oraculo = orc.OraculoPINN(estados, base.cfg, base.dominio)
    p = oraculo.predecir(grafo)
    assert p['escala_correccion'] < 1.0
    cruda = float(np.std([0.1 * np.tanh(s) for s in (2.0, 3.0, 4.0)]))
    libres = ~m.fuente
    assert np.allclose(p['incertidumbre'][libres], cruda, rtol=1e-4), (p['incertidumbre'][libres][:3], cruda)


def test_fuera_de_su_dominio_el_oraculo_da_la_fisica(monkeypatch):
    """045:RF-9, 045:RF-16 — fuera de lo validado decide la física también en lo que devuelve el oráculo, no solo en la
    marca: en la T6 la prueba entera estaba fuera del dominio y se medía la corrección que nadie usaría (5,07·10⁻⁴ p.u.
    frente a 2,07·10⁻⁴). Con ``respaldo_fisico=False`` se ve la predicción cruda."""
    monkeypatch.setattr(orc, 'dispositivo', lambda *_a, **_k: CPU)
    m = _muestra(5)
    grafo = orc._grafo_de_muestra(m)
    fisica = orc.ModeloMallado().predecir(grafo)
    oraculo = _oraculo_con_correccion(m, 0.5)
    oraculo.dominio = {**oraculo.dominio, 'redes': ['otra']}
    p = oraculo.predecir(grafo)
    assert p['fuera_de_dominio'] and p['motivos']
    assert np.allclose(p['v'], fisica['v'], atol=1e-6), 'fuera de dominio el oráculo devuelve su corrección'
    crudo = oraculo.predecir(grafo, respaldo_fisico=False)
    assert not np.allclose(crudo['v'], fisica['v'], atol=1e-6)

