"""Spec 027, T0 — auditoría del dataset de cada modelo antes de entrenar.

Las muestras se generan aquí, sorteadas con su semilla, con cada defecto que la auditoría
tiene que encontrar: valores no finitos, tensiones fuera de rango, ramas en el tope de
acoplador y una sola red repetida.
"""
from __future__ import annotations

import os
import random

import numpy as np
import pytest

from igea_dgs.digital_twin import auditoria as au
from igea_dgs.digital_twin.oraculo import Z_ACOPLADOR_PU, muestra

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED') or random.randrange(1_000_000))


def _grafo(rng: random.Random, n: int, acopladores: int = 0) -> dict:
    nodos = {f'N{i}': {'kv': 10.0, 'p_mw': rng.uniform(0, 0.2), 'q_mvar': rng.uniform(0, 0.05),
                       'fuente': i == 0, 'v_pu': 1.0 if i == 0 else None} for i in range(n)}
    ramas = [{'id': f'R{i}', 'desde': f'N{i}', 'hasta': f'N{i + 1}',
              'r_ohm': 0.0 if i < acopladores else rng.uniform(0.05, 0.5),
              'x_ohm': 0.0 if i < acopladores else rng.uniform(0.05, 0.5), 'inom_ka': 0.2}
             for i in range(n - 1)]
    return {'nodos': nodos, 'ramas': ramas, 'version': 2}


def _muestras(rng, redes: int, por_red: int, *, baja=None, nan=False, acopladores=0):
    out, ids = [], []
    for r in range(redes):
        n = rng.randint(6, 15) + r * 20               # cada red con su tamaño
        g = _grafo(rng, n, acopladores)
        for k in range(por_red):
            v = {f'N{i}': rng.uniform(0.95, 1.02) for i in range(n)}
            if baja is not None and k == 0:
                v['N1'] = baja
            m = muestra(g, v, f'fam{r}')
            if nan and r == 0 and k == 0:
                m.x[0, 1] = np.nan
            out.append(m)
            ids.append(f'e{r}-{k}')
    return out, ids


def test_informe_de_un_dataset_sano():
    """027:RF-29, 027:RF-33 — el informe dice muestras, redes distintas, nodos, columnas,
    fracción etiquetada, rangos y parámetros frente a etiquetas, y es apto."""
    rng = random.Random(SEMILLA)
    redes, por_red = rng.randint(2, 4), rng.randint(2, 5)
    ms, ids = _muestras(rng, redes, por_red)
    inf = au.auditar_muestras(ms, ids, parametros=1000)
    assert inf['apto'], SEMILLA
    assert inf['muestras'] == redes * por_red and inf['redes'] == redes
    assert inf['columnas_x'] == 5 and inf['fraccion_etiquetada']['min'] == 1.0
    assert inf['parametros'] == 1000 and inf['etiquetas'] == sum(len(m.ids) for m in ms)
    assert inf['no_finitos'] == [] and inf['tensiones_fuera_de_rango'] == []
    assert not any('una sola red' in a for a in inf['avisos'])


def test_no_finitos_impiden_entrenar_y_se_nombran():
    """027:RF-30 — un valor no finito hace el dataset no apto y nombra el episodio."""
    rng = random.Random(SEMILLA)
    ms, ids = _muestras(rng, 2, 2, nan=True)
    inf = au.auditar_muestras(ms, ids)
    assert not inf['apto'] and inf['no_finitos'] == [{'episodio': 'e0-0', 'campo': 'x'}]


def test_tope_de_acoplador_y_tensiones_fuera_de_rango_se_dicen_sin_excluir():
    """027:RF-31, 027:RF-32 — las ramas en el tope de acoplador y su relación máx/mín se
    dicen; la tensión de 0,61 p.u. se marca con su episodio y sigue en la máscara."""
    rng = random.Random(SEMILLA)
    acop = rng.randint(1, 3)
    ms, ids = _muestras(rng, 2, 2, baja=0.61, acopladores=acop)
    inf = au.auditar_muestras(ms, ids)
    assert inf['apto']
    assert inf['ramas_en_tope']['por_muestra_max'] == 2 * acop     # las dos direcciones
    assert inf['ramas_en_tope']['tope_pu'] == Z_ACOPLADOR_PU and inf['relacion_z'] > 1e4
    marcadas = {x['episodio'] for x in inf['tensiones_fuera_de_rango']}
    assert marcadas == {'e0-0', 'e1-0'}
    assert all(m.mascara[1] for m in ms), 'no se excluye: la calculó DIgSILENT'


def test_una_sola_red_y_pocas_ordenes_reales_se_avisan():
    """027:RF-33, 027:RF-34 — una sola red se avisa; el asistente con menos de 200 órdenes
    reales, también, y sus métricas no valen como puertas si se midieron con sintéticas."""
    rng = random.Random(SEMILLA)
    ms, ids = _muestras(rng, 1, 3)
    inf = au.auditar_muestras(ms, ids, parametros=928_518)
    assert inf['redes'] == 1 and any('una sola red' in a for a in inf['avisos'])
    # La misma red con una maniobra más cerrada sigue siendo una sola red.
    g = _grafo(rng, 8)
    abierta = muestra(g, {f'N{i}': 1.0 for i in range(8)})
    g['ramas'].append({'id': 'S1', 'desde': 'N0', 'hasta': 'N7', 'r_ohm': 0.1, 'x_ohm': 0.1})
    cerrada = muestra(g, {f'N{i}': 1.0 for i in range(8)})
    assert au.auditar_muestras([abierta, cerrada], ['a', 'b'])['redes'] == 1
    ordenes = au.auditar_ordenes(reales=1, sinteticas=4054, prueba_real=0, parametros=567_088)
    assert any('200' in a for a in ordenes['avisos'])
    assert not ordenes['puertas_con_reales']
    assert au.auditar_ordenes(reales=250, sinteticas=4000, prueba_real=50,
                              parametros=567_088)['puertas_con_reales']


def test_entrenar_no_arranca_con_un_dataset_no_apto(monkeypatch, tmp_path):
    """027:RF-29, 027:RF-30 — `entrenar` audita antes: con no finitos no entrena y lo dice."""
    from igea_dgs.digital_twin import oraculo
    from igea_dgs.digital_twin.buffer import BuferEpisodios

    rng = random.Random(SEMILLA)
    ms, ids = _muestras(rng, 2, 2, nan=True)
    monkeypatch.setattr(oraculo, '_muestras', lambda *_a, **_k: (ms, ids))
    r = oraculo.entrenar(BuferEpisodios(tmp_path))
    assert r['entrenado'] is False and 'no finitos' in r['motivo'] and r['auditoria']['no_finitos']


@pytest.mark.parametrize('n', [0])
def test_sin_muestras_el_informe_lo_dice(n):
    """027:RF-29 — sin muestras, no apto y dicho."""
    inf = au.auditar_muestras([], [])
    assert not inf['apto'] and inf['muestras'] == n
