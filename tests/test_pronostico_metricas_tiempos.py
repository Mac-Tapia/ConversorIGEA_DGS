"""089:RF-120, RF-121 — la evaluación de cada modelo da todas sus medidas de precisión y cuánto tarda en aprender y en
pronosticar ya entrenado.

El operador lo pidió el 2026-11-23: saber, además del WAPE y del error en la máxima que deciden la puerta, si el
pronóstico es verdadero con todas las medidas, y en cuánto tiempo pronostica un modelo ya entrenado. Sin GPU: la
competición usa el modelo falso de ``test_pronostico_demanda``.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

from convertersmartgrid.adaptadores import pronostico_demanda as pd_

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pronostico_demanda import _Falso, _objetivos_ml  # noqa: E402

def _metricas(*a, **k):
    assert hasattr(pd_, 'metricas_completas'), 'la evaluación no da todas las medidas de precisión (RF-120)'
    return pd_.metricas_completas(*a, **k)


CLAVES = {'n', 'mae', 'rmse', 'wape', 'smape', 'rmse_relativo', 'sesgo', 'sesgo_pct', 'r2', 'error_maxima_mediana',
          'desfase_maxima_h_mediana', 'mejora_sobre_referencia'}


def test_089_rf120_las_medidas_con_cifras_conocidas():
    real = np.array([100.0, 200.0, 300.0, 400.0])
    pron = real + np.array([10.0, -10.0, 10.0, 30.0])
    ref = real + 40.0
    m = _metricas([(real, pron)], q05=-20.0, q95=20.0, referencia=[(real, ref)])
    assert m['n'] == 4
    assert m['mae'] == pytest.approx(15.0)
    assert m['rmse'] == pytest.approx(np.sqrt((100 + 100 + 100 + 900) / 4))
    assert m['wape'] == pytest.approx(60 / 1000)
    assert m['sesgo'] == pytest.approx(10.0) and m['sesgo_pct'] == pytest.approx(40 / 1000)
    assert m['mejora_sobre_referencia'] == pytest.approx(1 - 15 / 40)
    assert m['error_maxima_mediana'] == pytest.approx(30 / 400) and m['desfase_maxima_h_mediana'] == 0
    assert m['cobertura'] == pytest.approx(3 / 4), 'el error de 30 cae fuera de la banda de ±20'
    assert m['ancho_banda_relativo'] == pytest.approx(40 / 250)
    assert m['r2'] == pytest.approx(1 - 1200 / 50000)
    assert m['pinball_q05'] > 0 and m['pinball_q95'] > 0


def test_089_rf120_lo_no_observado_no_cuenta():
    real = np.array([100.0, np.nan, 300.0])
    m = _metricas([(real, np.array([110.0, 9e9, 300.0]))])
    assert m['n'] == 2 and m['mae'] == pytest.approx(5.0)
    assert _metricas([(np.array([np.nan]), np.array([1.0]))]) == {'n': 0}


def test_089_rf120_rf121_la_competicion_informa_medidas_y_tiempos():
    r = pd_.backtest_modelos(_objetivos_ml(), ['bueno'], horizonte_dias=7, origenes=3, fabrica=lambda n, **k: _Falso(1.0))
    bueno = r['modelos']['bueno']
    assert 'metricas' in bueno and 'tiempos' in bueno, 'la competición no informa medidas ni tiempos (RF-120, RF-121)'
    assert set(bueno['metricas']) == {'1d', '7d'}
    assert CLAVES | {'cobertura', 'ancho_banda_relativo', 'pinball_q05', 'pinball_q95'} <= set(bueno['metricas']['7d'])
    t = bueno['tiempos']
    assert len(t['ajuste_s_por_origen']) == len(t['prediccion_s_por_origen']) == len(r['origenes'])
    assert t['prediccion_s_mediana'] is not None and t['prediccion_s_por_objetivo'] is not None
    assert t['objetivos_por_origen'] and all(n > 0 for n in t['objetivos_por_origen'])
    for perfil in r['perfiles'].values():
        assert CLAVES <= set(perfil['metricas']['7d'])
        assert perfil['tiempos']['prediccion_s_mediana'] is not None
    # La puerta no cambia (089:RF-63): las medidas nuevas se informan, no deciden.
    assert set(bueno['puerta']) == {'wape', 'maxima', 'cobertura'}
