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


@pytest.mark.parametrize('algoritmo', ['gru', 'nhits', 'tft', 'patchtst'])
def test_adaptador_real_entrena_predice_y_reabre(tmp_path, algoritmo):
    """046:RF-13 — los cuatro cargan de verdad, en CUDA, con la misma salida y reapertura."""
    d = pr.disponibilidad(algoritmo)
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
