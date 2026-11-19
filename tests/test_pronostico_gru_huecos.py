"""Spec 089, RF-115 (C10 del diagnóstico del 18-11, H17): la GRU de pronóstico no cuenta un objetivo ausente como un
dato. Antes, la serie entera pasaba por ``nan_to_num`` y un hueco entraba en la pérdida como un cero medido.

Solo la preparación del lote, en CPU con numpy: ni GPU, ni torch, ni entrenamiento.
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

from convertersmartgrid.adaptadores import pronostico_demanda as pd

RAIZ = Path(__file__).resolve().parents[1]


def test_el_lote_pone_a_cero_los_huecos_solo_en_la_entrada_y_los_enmascara_en_el_objetivo():
    """089:RF-115 — con una serie cuyo tramo final está ausente, el objetivo de ese tramo queda fuera de la máscara y
    la entrada no lleva NaN."""
    assert hasattr(pd, '_lote_gru'), 'la GRU no separa la preparación del lote de su entrenamiento'
    serie = np.arange(40, dtype=float)
    serie[30:] = np.nan                                   # el tramo que la máscara debe dejar fuera
    covariables = np.zeros((40, 2))
    x, y, mascara = pd._lote_gru([(serie, covariables)], np.random.default_rng(0), contexto=10, horizonte=5, lote=64)
    assert x.shape == (64, 10, 3) and y.shape == (64, 5) and mascara.shape == (64, 5)
    assert not np.isnan(x).any() and not np.isnan(y).any()
    # Donde el objetivo es un hueco, la máscara lo deja fuera; donde es un dato, lo cuenta con su valor.
    for k in range(64):
        assert all(mascara[k, j] == (y[k, j] != 0 or not np.isnan(y[k, j])) or not mascara[k, j] for j in range(5))
    assert (~mascara).any() and mascara.any(), 'el sorteo no tocó el tramo ausente o no tocó ninguno medido'
    medidos = y[mascara]
    assert (medidos >= 10).all() and (medidos < 30).all(), 'un objetivo ausente entró como dato'


def test_la_perdida_de_la_gru_usa_la_mascara_y_no_convierte_el_objetivo_en_cero():
    """089:RF-115 — en el ajuste de la GRU la serie no pasa entera por ``nan_to_num`` y la pérdida va ponderada por la
    máscara del lote (lectura del código: el ajuste necesita GPU)."""
    arbol = ast.parse((RAIZ / 'src' / 'convertersmartgrid' / 'adaptadores' / 'pronostico_demanda.py').read_text(encoding='utf-8'))
    gru = next(n for n in ast.walk(arbol) if isinstance(n, ast.ClassDef) and n.name == 'ModeloGRU')
    ajustar = next(n for n in gru.body if isinstance(n, ast.FunctionDef) and n.name == 'ajustar')
    codigo = ast.unparse(ajustar)
    assert 'nan_to_num(d[1])' not in codigo, 'la serie entera se convierte en cero antes de sacar los objetivos'
    assert '_lote_gru(' in codigo and 'mascara' in codigo, 'la pérdida no usa la máscara de los objetivos medidos'
