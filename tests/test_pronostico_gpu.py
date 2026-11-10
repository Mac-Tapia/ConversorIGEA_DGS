"""046:RF-13 / 046:RF-14 / 046:RF-15 — modelos neuronales reales en CUDA con series de contrato.

No es una medición ni un resultado eléctrico: comprueba que el adaptador entrena, predice con
la forma del contrato y reabre. Exige GPU: solo se lanza en el turno de GPU del integrador.
"""
from __future__ import annotations

import numpy as np
import pytest
from pronostico_sintetico import CADENCIA, PUNTOS_DIA, objetivos

from convertersmartgrid.digital_twin import pronostico as pr

H = 8


def _datos():
    c = pr.construir_conjunto(objetivos(1, 40), cadencia_min=CADENCIA, zona_horaria='UTC')
    em = np.array([35 * PUNTOS_DIA, 36 * PUNTOS_DIA])
    return c, c.lote(c.nombres * 2, em, contexto=32, horizonte=H)


def test_tramo_comun_sin_rellenar_huecos():
    """046:RF-26 — sin GPU: el multivariante entrena con el tramo en que todas las series tienen dato."""
    from types import SimpleNamespace

    from convertersmartgrid.digital_twin.adaptador_neuralforecast import tramo_comun

    a = np.arange(20, dtype=float)
    b = a.copy()
    b[5] = np.nan                        # un hueco parte el tramo común en [0, 5) y [6, 20)
    c = SimpleNamespace(nombres=['a', 'b'], valores={'a': a, 'b': b})
    assert tramo_comun(c, 20, minimo=10) == (6, 20)
    assert tramo_comun(c, 12, minimo=5) == (6, 12)
    with pytest.raises(ValueError, match='todas las series'):
        tramo_comun(c, 20, minimo=15)


def test_el_multivariante_no_predice_una_emision_con_hueco():
    """046:RF-26, 046:RF-1 — sin GPU: si a una serie le falta un dato en esa emisión, lo dice y no rellena."""
    from convertersmartgrid.digital_twin.adaptador_neuralforecast import AdaptadorNeuralForecast

    c, _lote = _datos()
    nombre = c.nombres[0]
    m = AdaptadorNeuralForecast.__new__(AdaptadorNeuralForecast)
    m.algoritmo, m.contexto_pasos, m.series, m.nf = 'itransformer', 32, [nombre], object()
    c.valores[nombre] = c.valores[nombre].copy()
    e = 35 * PUNTOS_DIA
    lote = c.lote([nombre], np.array([e]), contexto=32, horizonte=H)
    c.valores[nombre][e - 3] = np.nan     # el lote ya se copió; la rejilla que ve el multivariante, no
    with pytest.raises(ValueError, match='hueco'):
        m.predecir(lote)
    m.series = ['otro']
    with pytest.raises(ValueError, match='no se entrenó con'):
        m.predecir(lote)


@pytest.mark.parametrize('algoritmo', pr.NEURONALES)
def test_adaptador_real_entrena_predice_y_reabre(tmp_path, algoritmo):
    """046:RF-13 — todos los de ``NEURONALES`` cargan de verdad, en CUDA, con la misma salida y reapertura."""
    d = pr.disponibilidad(algoritmo)
    if d.get('sin_gpu'):
        from convertersmartgrid.training_coordinator import SinGPU

        raise SinGPU(d['motivo'])       # en GitHub, omitida (102:RF-17); aquí, un fallo
    assert d['disponible'], d
    c, lote = _datos()
    m = pr.fabrica(algoritmo, horizonte=H, cadencia_min=CADENCIA, contexto_pasos=32, pasos=5, lote=8, semilla=3)
    assert m.requiere_gpu is True
    m.ajustar(c, 30 * PUNTOS_DIA, H, 3)
    p = m.predecir(lote)
    assert p.shape == (2, H, 3) and np.isfinite(p).all()
    m.guardar(tmp_path / 'm')
    otra = pr.reabrir_modelo(algoritmo, tmp_path / 'm')
    assert np.allclose(otra.predecir(lote), p, atol=1e-3)
