"""046:RF-6 y RF-18 — métricas por horizonte, cobertura y puertas predeclaradas."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from convertersmartgrid.digital_twin.evaluacion_temporal import (
    POLITICA_TEMPORAL,
    error_de_maxima,
    evaluar_pronosticos,
    familias_de,
    verificar_ventanas_identicas,
)

RAIZ = Path(__file__).resolve().parents[1]


def _datos(dias=20, h=(1, 4), sesgo=0.0, ancho=20.0, semilla=7, objetivo='cabecera:X:kW', cuantiles=('q05', 'q50', 'q95')):
    rng = np.random.default_rng(semilla)
    real, pred = [], []
    inicio = datetime(2026, 3, 1)
    for i in range(dias * 24):
        e = inicio + timedelta(hours=i)
        for paso in h:
            t = e + timedelta(minutes=15 * paso)
            v = 100 + 10 * rng.standard_normal()
            real.append({'target': objetivo, 'forecast_time': t.isoformat(), 'valor': v})
            fila = {'target': objetivo, 'emission_time': e.isoformat(), 'forecast_time': t.isoformat(),
                    'horizon_steps': paso, cuantiles[0]: 100 + sesgo - ancho, cuantiles[1]: 100 + sesgo,
                    cuantiles[2]: 100 + sesgo + ancho}
            pred.append(fila)
    # Los valores reales se repiten por objetivo e instante: el último manda, como en la serie.
    unicos = {(r['target'], r['forecast_time']): r for r in real}
    return list(unicos.values()), pred


def test_cuantiles_y_cobertura_coherentes():
    """046:RF-6 — pinball y cobertura por horizonte con su n; un q10/q90 no pasa por 90 %."""
    real, pred = _datos()
    ev = evaluar_pronosticos(real, pred, politica=POLITICA_TEMPORAL)
    fila = ev['contextos']['cabecera:X:kW'][4]
    assert fila['n'] == 20 * 24 and fila['grupos'] == 20
    assert 0 <= fila['cobertura'] <= 1 and fila['pinball'] > 0 and fila['mae'] > 0 and fila['rmse'] >= fila['mae']
    assert ev['cobertura_nominal'] == pytest.approx(.9)
    with pytest.raises(ValueError, match='cuantil'):
        evaluar_pronosticos(*_datos(cuantiles=('q10', 'q50', 'q90')), politica=POLITICA_TEMPORAL)
    real, pred = _datos()
    pred[0]['q05'], pred[0]['q95'] = pred[0]['q95'], pred[0]['q05']
    with pytest.raises(ValueError, match='ordenados'):
        evaluar_pronosticos(real, pred, politica=POLITICA_TEMPORAL)


def test_pinball_conocido():
    """046:RF-6 — la pérdida es la de los tres cuantiles, comprobada a mano."""
    real = [{'target': 'o', 'forecast_time': '2026-03-01T00:15:00', 'valor': 10.0}]
    pred = [{'target': 'o', 'emission_time': '2026-03-01T00:00:00', 'forecast_time': '2026-03-01T00:15:00',
             'horizon_steps': 1, 'q05': 8.0, 'q50': 9.0, 'q95': 12.0}]
    fila = evaluar_pronosticos(real, pred, politica=POLITICA_TEMPORAL)['contextos']['o'][1]
    esperado = (.05 * 2 + .5 * 1 + .05 * 2) / 3
    assert fila['pinball'] == pytest.approx(esperado)
    assert fila['mae'] == pytest.approx(1.0) and fila['cobertura'] == 1.0


def test_sin_dato_real_no_se_inventa():
    """046:RF-6 — un instante previsto sin medición es un error, no un cero."""
    real, pred = _datos(dias=1)
    with pytest.raises(ValueError, match='sin medición'):
        evaluar_pronosticos(real[:-1], pred, politica=POLITICA_TEMPORAL)


def test_error_de_maxima_y_de_su_instante():
    """046:RF-18 — la máxima de cada trayectoria y a cuántos minutos cae su instante."""
    real = np.array([[1., 5., 2., 1.], [3., 1., 1., 9.]])
    q50 = np.array([[1., 2., 7., 1.], [3., 1., 1., 9.]])
    e = error_de_maxima(real, q50, cadencia_min=15, puntos_trayectoria=4)
    assert e['error_maxima'] == pytest.approx(1.0)            # (|7-5| + 0) / 2
    assert e['error_instante_min'] == pytest.approx(7.5)      # (15 + 0) / 2
    # Solo el primer día de la trayectoria: la máxima de después no cuenta.
    assert error_de_maxima(real, q50, cadencia_min=15, puntos_trayectoria=2)['error_maxima'] == pytest.approx((3 + 0) / 2)


def test_sesgo_de_maxima_se_calibra_y_se_aplica():
    """046:RF-18 — una mediana lisa no pierde la puerta solo por serlo: el sesgo sale de calibración."""
    from convertersmartgrid.digital_twin.evaluacion_temporal import sesgo_de_maxima
    real = np.array([[1., 9., 2.], [2., 11., 1.], [1., 10., 3.]])
    lisa = np.array([[1., 7., 2.], [2., 7., 1.], [1., 7., 3.]])
    sesgo = sesgo_de_maxima(real, lisa, puntos_trayectoria=3)
    assert sesgo == pytest.approx(3.0)
    con = error_de_maxima(real, lisa, cadencia_min=15, puntos_trayectoria=3, sesgo=sesgo)['error_maxima']
    assert con < error_de_maxima(real, lisa, cadencia_min=15, puntos_trayectoria=3)['error_maxima']


def _metricas(pinball, mae=1.0, emax=1.0, einst=15.0, cobertura=.9, sesgo_dia=0.0):
    dias = {f'2026-03-{d:02d}': pinball + sesgo_dia * ((d % 2) - .5) for d in range(1, 21)}
    return {'pinball': pinball, 'mae': mae, 'rmse': mae, 'cobertura': cobertura, 'n': 480, 'grupos': 20, 'por_dia': dias,
            'error_maxima': emax, 'error_instante_min': einst,
            'por_dia_maxima': {d: emax for d in dias}, 'por_dia_instante': {d: einst for d in dias}}


def test_error_por_horizonte_no_se_oculta():
    """046:RF-8 — una media buena no tapa un horizonte fuera de puerta."""
    ref = {1: _metricas(1.0), 96: _metricas(1.0)}
    cand = {1: _metricas(.5), 96: _metricas(1.05)}
    fam = familias_de('o', cand, ref, politica=POLITICA_TEMPORAL)
    from convertersmartgrid.evaluacion_modelos import verificar_familias
    fallos = verificar_familias(fam, None, POLITICA_TEMPORAL, esperadas=['o|h1', 'o|h96'])
    assert any(f.startswith('o|h96: habilidad_pinball') for f in fallos)
    assert not any(f.startswith('o|h1:') for f in fallos)


def test_pico_y_su_instante_son_puertas():
    """046:RF-18 — mejorar el pinball empeorando la máxima o su instante no pasa."""
    from convertersmartgrid.evaluacion_modelos import verificar_familias
    ref = {4: _metricas(1.0)}
    for cand, puerta in (({4: _metricas(.5, emax=1.2)}, 'maxima_no_peor'),
                         ({4: _metricas(.5, einst=30.0)}, 'instante_no_peor')):
        fallos = verificar_familias(familias_de('o', cand, ref, politica=POLITICA_TEMPORAL), None, POLITICA_TEMPORAL,
                                    esperadas=['o|h4'])
        assert any(puerta in f for f in fallos), puerta
    assert not verificar_familias(familias_de('o', {4: _metricas(.5)}, ref, politica=POLITICA_TEMPORAL), None,
                                  POLITICA_TEMPORAL, esperadas=['o|h4'])


def test_cobertura_fuera_de_banda_no_pasa():
    """046:RF-6 — un intervalo muy ancho o muy estrecho no pasa aunque mejore el error."""
    from convertersmartgrid.evaluacion_modelos import verificar_familias
    ref = {4: _metricas(1.0)}
    for c in (.99, .7):
        fallos = verificar_familias(familias_de('o', {4: _metricas(.5, cobertura=c)}, ref, politica=POLITICA_TEMPORAL),
                                    None, POLITICA_TEMPORAL, esperadas=['o|h4'])
        assert any('cobertura_en_banda' in f for f in fallos)


def test_pico_con_azar_no_rechaza_si_no_es_peor_de_verdad():
    """046:RF-18 — una diferencia de pico dentro del azar de los días no cuenta como peor."""
    ref = {4: _metricas(1.0)}
    cand = {4: _metricas(.5)}
    cand[4]['por_dia_maxima'] = {d: 1.0 + (3 if i % 2 else -2.9) for i, d in enumerate(cand[4]['por_dia'])}
    assert familias_de('o', cand, ref, politica=POLITICA_TEMPORAL)['o|h4']['maxima_no_peor'] == 1.0


def test_mejora_se_agrupa_por_dia():
    """046:RF-6 — los días, no las ventanas solapadas, son la muestra de la mejora."""
    ref = {4: _metricas(1.0)}
    claro = familias_de('o', {4: _metricas(.9)}, ref, politica=POLITICA_TEMPORAL)['o|h4']
    assert claro['mejora_significativa'] == 1.0 and claro['ejemplos'] == 20
    # Media un 10 % mejor, pero la mitad de los días es mucho peor: no es significativa.
    ruidoso = familias_de('o', {4: _metricas(.9, sesgo_dia=8.0)}, ref, politica=POLITICA_TEMPORAL)['o|h4']
    assert ruidoso['mejora_significativa'] == 0.0


def test_ventanas_distintas_se_rechazan():
    """046:RF-5 — no se compara un modelo con otro en ventanas distintas."""
    _r, a = _datos(dias=1)
    verificar_ventanas_identicas({'m1': a, 'm2': list(a)})
    with pytest.raises(ValueError, match='ventanas'):
        verificar_ventanas_identicas({'m1': a, 'm2': a[:-1]})


def test_puertas_predeclaradas_dicen_lo_mismo_que_la_spec():
    """046:RF-8 — la tabla de la spec y la política son la misma, antes de medir."""
    spec = next((RAIZ / 'specs').glob('046-*/spec.md')).read_text(encoding='utf-8')
    tabla = dict(re.findall(r'^\| (\w+) \| (\d+\.\d+) \| .*$', spec, re.M))
    tabla_puertas = {k: float(v) for k, v in tabla.items() if k.startswith(('habilidad', 'cobertura', 'mejora', 'maxima', 'instante'))}
    assert tabla_puertas == dict(POLITICA_TEMPORAL.puertas_por_familia)
    dias = re.findall(r'^\| (entrenamiento|seleccion|calibracion|prueba) \| (\d+\.\d+) \| (\d+) \|$', spec, re.M)
    assert tuple(int(d[2]) for d in dias) == POLITICA_TEMPORAL.minimos
    from convertersmartgrid.digital_twin.series_causales import FRACCIONES_DIAS
    assert tuple(float(d[1]) for d in dias) == FRACCIONES_DIAS
    assert POLITICA_TEMPORAL.cobertura_objetivo == .9
