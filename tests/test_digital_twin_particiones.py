"""Spec 027, T2 — particiones «un sistema fuera» y mínimo de episodios de prueba.

Con la partición por familia de escenario, las variantes de IN111–TA225 caían en
entrenamiento y en prueba y el error de prueba medía la misma red (revisión del 2026-10-28).
"""
from __future__ import annotations

import os
import random

from igea_dgs.digital_twin import oraculo
from igea_dgs.digital_twin.oraculo import muestra

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED') or random.randrange(1_000_000))


def _red(rng: random.Random, n: int, prefijo: str) -> dict:
    nodos = {f'{prefijo}{i}': {'kv': 10.0, 'p_mw': 0.1, 'q_mvar': 0.02, 'fuente': i == 0} for i in range(n)}
    ramas = [{'id': f'{prefijo}R{i}', 'desde': f'{prefijo}{i}', 'hasta': f'{prefijo}{i + 1}',
              'r_ohm': rng.uniform(0.1, 0.4), 'x_ohm': rng.uniform(0.1, 0.4)} for i in range(n - 1)]
    return {'nodos': nodos, 'ramas': ramas, 'version': 2}


def _muestras(rng: random.Random, redes: int, por_red: int):
    out = []
    for r in range(redes):
        g = _red(rng, rng.randint(5, 12), f'S{r}N')
        for k in range(por_red):
            out.append(muestra(g, {n: rng.uniform(0.95, 1.02) for n in g['nodos']}, f'fam{r}-{k}'))
    return out


def test_ninguna_red_en_entrenamiento_y_prueba_a_la_vez():
    """027:RF-2 — cada red cae entera del lado de prueba o del de entrenamiento y validación;
    con dos o más redes siempre hay una de prueba."""
    rng = random.Random(SEMILLA)
    ms = _muestras(rng, rng.randint(2, 6), rng.randint(3, 12))
    grupos = oraculo.particionar(ms)
    prueba = {oraculo.red_de(m) for m in grupos['prueba']}
    resto = {oraculo.red_de(m) for m in grupos['entrenamiento'] + grupos['validacion']}
    assert prueba and not prueba & resto, SEMILLA
    assert sum(len(v) for v in grupos.values()) == len(ms)


def test_una_sola_red_no_tiene_prueba_y_no_se_promueve():
    """027:RF-2, 027:RF-3 — con una sola red no hay red de prueba: no se promueve y se dice."""
    rng = random.Random(SEMILLA)
    grupos = oraculo.particionar(_muestras(rng, 1, 20))
    assert grupos['prueba'] == []
    assert any('027:RF-3' in f for f in oraculo.fallos_de_particion(grupos))


def test_menos_de_diez_de_prueba_no_promueve():
    """027:RF-3 — una red de prueba con menos de 10 episodios no basta para promover."""
    rng = random.Random(SEMILLA)
    pocos = rng.randint(1, 9)
    grupos = oraculo.particionar(_muestras(rng, 2, pocos))
    assert len(grupos['prueba']) == pocos
    assert any('10' in f and '027:RF-3' in f for f in oraculo.fallos_de_particion(grupos))
    bastantes = oraculo.particionar(_muestras(rng, 2, 10))
    assert oraculo.fallos_de_particion(bastantes) == []
