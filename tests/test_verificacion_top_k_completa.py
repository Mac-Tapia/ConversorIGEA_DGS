"""044:RF-6 — la ausencia de medidas nunca equivale a una verificación correcta."""
from __future__ import annotations

import pytest

from igea_dgs.digital_twin.evolutivo import verificar_top_k


def test_top_k_sin_metricas_rechaza():
    """044:RF-6 — reproduce la aceptación anterior con solo converge=True."""
    resultado = verificar_top_k([{'id': 'x'}], lambda _: {'converge': True},
                               tolerancia_v_pu=0.01)
    assert resultado['verificada'] is False
    assert resultado['elegida'] is None
    assert resultado['descartadas'][0]['motivo']


@pytest.mark.parametrize('lado', ['prediccion', 'medicion'])
@pytest.mark.parametrize('clave', ['v_min', 'perdidas_kw'])
@pytest.mark.parametrize('valor', [None, float('nan'), float('inf'), -float('inf'), 'invalido', True])
def test_top_k_metricas_invalidas_rechaza(lado, clave, valor):
    """044:RF-6 — validar ambos lados evita ceros ficticios y comparaciones con NaN."""
    alternativa = {'v_min': 0.97, 'perdidas_kw': 10.0}
    medicion = {'converge': True, **alternativa}
    (alternativa if lado == 'prediccion' else medicion)[clave] = valor
    resultado = verificar_top_k([alternativa], lambda _: medicion, tolerancia_v_pu=0.01)
    assert resultado['verificada'] is False
    assert clave in resultado['descartadas'][0]['motivo']


@pytest.mark.parametrize('lado', ['prediccion', 'medicion'])
def test_top_k_perdidas_negativas_rechaza(lado):
    """044:RF-6 — una pérdida negativa no es una medida física admisible."""
    alternativa = {'v_min': 0.97, 'perdidas_kw': 10.0}
    medicion = {'converge': True, **alternativa}
    (alternativa if lado == 'prediccion' else medicion)['perdidas_kw'] = -1.0
    assert not verificar_top_k([alternativa], lambda _: medicion,
                              tolerancia_v_pu=0.01)['verificada']


def test_top_k_descarta_y_continua_con_evidencia():
    """044:RF-6 — descartar no impide encontrar una alternativa completa posterior."""
    alternativas = [{'id': 'mala'}, {'id': 'valida', 'v_min': 0.97, 'perdidas_kw': 10.0}]
    guardados = []
    resultado = verificar_top_k(
        alternativas, lambda _: {'converge': True, 'v_min': 0.971, 'perdidas_kw': 10.5},
        tolerancia_v_pu=0.01, guardar=lambda *args: guardados.append(args))
    assert resultado['verificada']
    assert resultado['elegida']['id'] == 'valida'
    assert len(guardados) == len(resultado['descartadas']) == 1
