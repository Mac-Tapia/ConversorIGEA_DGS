"""Spec 024, T12: gemelo temporal con curvas sintéticas de 15 minutos."""
from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from igea_dgs.digital_twin import temporal as tp


def _curva(dias: int, base: float, semilla: int) -> np.ndarray:
    rnd = np.random.default_rng(semilla)
    t = np.arange(dias * tp.PUNTOS_DIA)
    forma = 0.6 + 0.4 * np.sin(2 * np.pi * (t % tp.PUNTOS_DIA) / tp.PUNTOS_DIA - 1.2) ** 2
    return base * forma * (1 + 0.02 * rnd.standard_normal(len(t)))


INSTANTES = [datetime(2026, 7, 1, tzinfo=UTC) + timedelta(minutes=15 * i) for i in range(7 * tp.PUNTOS_DIA)]


def test_el_estacional_cumple_el_contrato():
    """024:RF-20 / 024:RF-38 — sin PyTorch, el mismo instante del día anterior."""
    s = _curva(3, 1000, 1)
    r = tp.ModeloEstacional().reproducir(s)
    assert np.isnan(r[: tp.PUNTOS_DIA]).all() and r[tp.PUNTOS_DIA] == s[0]
    assert tp.metricas(s, r)['mape_pct'] < 10


def test_gru_reproduce_el_mes():
    """024:RF-20 / 024:RF-37 — la GRU aprende la forma diaria y reproduce la curva con poco
    error frente a lo medido."""
    pytest.importorskip('torch')
    s = _curva(7, 2000, 2)
    m = tp.GemeloGRU(epocas=40)
    m.entrenar(s[: 5 * tp.PUNTOS_DIA])
    r = m.reproducir(s)
    met = tp.metricas(s[5 * tp.PUNTOS_DIA:], r[5 * tp.PUNTOS_DIA:])
    assert met['puntos'] > 0 and met['mape_pct'] < 8, met


def test_desviaciones_con_su_alimentador():
    """024:RF-21 — el instante, el alimentador que más aporta y la contribución de cada uno."""
    a, b = _curva(7, 1000, 3), _curva(7, 500, 4)
    ra, rb = a.copy(), b.copy()
    ra[300] = a[300] * 0.5
    devs = tp.desviaciones({'A': a, 'B': b}, {'A': ra, 'B': rb}, INSTANTES, umbral_pct=5)
    assert [d['alimentador'] for d in devs] == ['A']
    assert devs[0]['instante'] == INSTANTES[300].isoformat() and devs[0]['confirmar_en_pf']
    assert devs[0]['contribucion_pct']['A'] == pytest.approx(100)


def test_pseudo_medidas_sin_medidor():
    """024:RF-22 — lo que falta en la barra se reparte por kVA, menos pérdidas y fijos, con
    intervalo y marcado como estimado; si lo medido supera a la barra, 0 y aviso."""
    medido = _curva(1, 600, 5)
    barra = medido + 400
    est = tp.pseudo_medidas(barra, {'M1': medido}, {'S1': 300, 'S2': 100}, perdidas_pct=0)
    assert all(e['estimada'] for e in est.values())
    assert np.allclose(np.array(est['S1']['kw']) + np.array(est['S2']['kw']), 400)
    assert np.allclose(np.array(est['S1']['kw']), 300)
    assert est['S1']['inferior'][0] < est['S1']['kw'][0] < est['S1']['superior'][0]
    corto = tp.pseudo_medidas(medido * 0.5, {'M1': medido}, {'S1': 1})
    assert corto['S1']['aviso'] and max(corto['S1']['kw']) == 0


def test_instante_critico_coincidente():
    """024:RF-37 — el instante de máxima coincidente, no la máxima de cada uno."""
    semilla = random.randrange(1 << 30)
    rnd = np.random.default_rng(semilla)
    a, b = rnd.uniform(1, 2, 20), rnd.uniform(1, 2, 20)
    a[5], b[7] = 10, 10
    a[12], b[12] = 8, 8
    c = tp.instante_critico({'A': a, 'B': b}, INSTANTES[:20])
    assert c['instante'] == INSTANTES[12].isoformat(), f'semilla {semilla}'
    assert c['total_kw'] == pytest.approx(16)


def test_gemelo_temporal_desde_la_web(tmp_path, monkeypatch):
    """024:RF-20 / 024:RF-21 / 024:RF-22 / 024:RF-37 — con las curvas de la última máxima
    buscada: reproducción por cabecera, desviaciones, instante crítico y pseudo-medidas."""
    from threading import Lock
    from types import SimpleNamespace

    from igea_dgs.web import services

    a, b = _curva(7, 1000, 6), _curva(7, 400, 7)
    barra = a + b + _curva(7, 300, 8)
    curva = lambda s: [(t, float(v), 0.0) for t, v in zip(INSTANTES, s, strict=True)]
    ws = SimpleNamespace(lock=Lock(), curvas_cabecera={'J1': {'MA': {'curva': curva(a)}, 'MB': {'curva': curva(b)},
                                                              'MS': {'curva': curva(barra)}}})
    ctx = SimpleNamespace(log=lambda _m: None)
    r = services.gemelo_temporal(ws, ctx, 'J1', {'A': 'MA', 'B': 'MB'}, barra='MS', sin_medidor={'C': 250})
    assert set(r['alimentadores']) == {'A', 'B'} and r['alimentadores']['A']['puntos'] > 0
    assert r['instante_critico']['total_kw'] > 0
    assert r['pseudo_medidas']['C']['estimada'] and r['pseudo_medidas']['C']['kw_max'] > 0
    with pytest.raises(services.UserError):
        services.gemelo_temporal(ws, ctx, 'J1', {'A': 'NO'})


def test_gru_valida_con_la_ultima_parte_y_para_a_tiempo():
    """027:RF-5 / 027:RF-6 / 027:RF-11 — la GRU valida con el final de la serie, para cuando
    no mejora y se usa solo si gana al estacional en esa parte."""
    pytest.importorskip('torch')
    s = _curva(7, 2000, 9)
    m = tp.GemeloGRU(epocas=200, paciencia=3)
    m.entrenar(s)
    v = m.validacion
    assert v['epocas'] < 200 and v['mejor_epoca'] < v['epocas']
    assert v['mae_kw'] > 0 and v['mae_estacional_kw'] > 0
    usado = tp.elegido(tp.GemeloGRU(epocas=200, paciencia=3), s)
    assert usado.nombre == ('gru' if v['supera_estacional'] else 'estacional')
    # Una serie que se repite día a día: el estacional es exacto y la GRU no puede ganarle.
    repetida = np.tile(s[:tp.PUNTOS_DIA], 7)
    assert tp.elegido(tp.GemeloGRU(epocas=2, paciencia=1), repetida).nombre == 'estacional'
