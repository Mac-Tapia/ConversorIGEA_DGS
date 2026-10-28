"""Spec 029: la tasa de crecimiento de cada alimentador desde la medición de cabecera."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest

from igea_dgs import crecimiento as cr


def _curva(anio: int, meses: range, base: float, rnd: random.Random):
    out = []
    for m in meses:
        t = datetime(anio, m, 1)
        for h in range(0, 24 * 28, 6):
            out.append((t + timedelta(hours=h), base * (0.6 + 0.4 * rnd.random()), None))
    return out


def test_tasa_con_los_meses_comunes():
    """029:RF-2 — se comparan las máximas de los meses que tienen los dos años: un año entero
    frente a medio año no da un crecimiento falso."""
    rnd = random.Random(7)
    a2025 = _curva(2025, range(1, 13), 1000, rnd) + [(datetime(2025, 12, 20), 5000.0, None)]
    a2026 = _curva(2026, range(1, 8), 1100, rnd)
    r = cr.tasa_entre(a2025, a2026, 1)
    assert r['meses'] == list(range(1, 8)) and r['max_anterior_kw'] < 1000.01
    assert r['tasa'] == pytest.approx(r['max_ultimo_kw'] / r['max_anterior_kw'] - 1)
    assert cr.tasa_entre(a2025, [], 1) is None


def test_tasas_por_alimentador_y_mediana():
    """029:RF-1 / 029:RF-3 / 029:RF-5 — tasa compuesta de los que tienen dos años; los demás,
    la mediana del sistema, dicho."""
    rnd = random.Random(3)
    curvas = {2024: {'A': [(datetime(2024, 3, 1), 100.0, None)]},
              2026: {'A': [(datetime(2026, 3, 1), 121.0, None)], 'B': [(datetime(2026, 3, 1), 50.0, None)]},
              2025: {'C': _curva(2025, range(1, 4), 200, rnd)}}
    curvas[2026]['C'] = [(f.replace(year=2026), kw * 1.05, q) for f, kw, q in curvas[2025]['C']]
    t = cr.tasas_por_alimentador(curvas, ['A', 'B', 'C'])
    assert t['A']['tasa'] == pytest.approx(0.10) and t['A']['anios'] == [2024, 2026] and t['A']['origen'] == 'medida'
    assert t['C']['tasa'] == pytest.approx(0.05)
    assert t['B']['origen'] == 'mediana del sistema' and t['B']['tasa'] == pytest.approx(0.075)
    assert cr.tasas_por_alimentador({}, ['X'])['X'] == {'tasa': None, 'origen': 'sin datos'}


def test_curvas_sumadas_en_registros_comunes():
    """029:RF-1 — un alimentador con dos medidores suma sus curvas donde los dos tienen registro."""
    t = datetime(2026, 1, 1)
    s = cr.sumar([[(t, 10.0, None), (t + timedelta(hours=1), 5.0, None)], [(t, 3.0, None)]])
    assert s == [(t, 13.0, None)]
    assert cr.maximas_mensuales([(t, 1.0, None), (t + timedelta(days=40), 2.0, None), ('mala', 9.0, None)]) == {1: 1.0, 2: 2.0}
