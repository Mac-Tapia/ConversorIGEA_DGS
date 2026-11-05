"""087:RF-7 a RF-9 — cuándo dejar de sortear una variante, con su probabilidad bayesiana."""
from __future__ import annotations

import math

import pytest

from convertersmartgrid.seleccion_bayesiana import CERTEZA, MINIMO_SORTEOS, Seguimiento, probabilidad_de_alcanzar


def test_la_posterior_da_el_valor_conocido():
    """087:RF-7 — sin datos, la previa uniforme: P(p ≥ 0,95) = 0,05; sin fallos, 1 − 0,95^(n+1)."""
    assert probabilidad_de_alcanzar(0, 0, 0.95) == pytest.approx(0.05)
    assert probabilidad_de_alcanzar(50, 0, 0.95) == pytest.approx(1 - 0.95 ** 51)


def _hasta_parar(seg, resultados):
    for bien in resultados:
        if seg.anota(bien):
            return True
    return False


def test_para_a_favor_cuando_ya_esta_claro():
    """087:RF-8 — sin fallos se para antes de los 200: el primer n con 1 − 0,95^(n+1) > 0,99."""
    seg = Seguimiento(200, 0.95, bayesiana=True)
    assert _hasta_parar(seg, [True] * 200)
    esperado = next(n for n in range(1, 201) if 1 - 0.95 ** (n + 1) > CERTEZA)
    assert seg.medidos == esperado and seg.medidos < 200 and seg.parada == 'cumple'
    assert seg.fraccion() >= 0.95


def test_para_en_contra_sin_esperar_a_agotar_los_fallos_admitidos():
    """087:RF-8 — una variante mala se descarta mucho antes que con la regla de los 10 fallos."""
    seg = Seguimiento(200, 0.95, bayesiana=True)
    assert _hasta_parar(seg, [False] * 200)
    assert seg.medidos == MINIMO_SORTEOS and seg.parada == 'no_cumple' and seg.fraccion() < 0.95


def test_no_para_con_pocos_sorteos_ni_si_no_esta_claro():
    """087:RF-8 — antes del mínimo no se decide; 94,5 % en 200 no se distingue del 95 %."""
    seg = Seguimiento(200, 0.95, bayesiana=True)
    assert not _hasta_parar(seg, [False] * (MINIMO_SORTEOS - 1))
    prob = probabilidad_de_alcanzar(189, 11, 0.95)
    assert 1 - CERTEZA < prob < CERTEZA


def test_el_resumen_dice_la_certeza():
    """087:RF-9 — sorteos usados, fracción y probabilidad de alcanzar el objetivo."""
    seg = Seguimiento(200, 0.95, bayesiana=True)
    _hasta_parar(seg, [True] * 200)
    r = seg.resumen()
    assert r['sorteos_usados'] == seg.medidos and r['sorteos_total'] == 200 and r['fraccion'] == 1.0
    assert r['probabilidad'] > CERTEZA and r['parada'] == 'cumple' and math.isclose(r['objetivo'], 0.95)


def test_sin_la_marca_sigue_la_regla_de_siempre():
    """087:RF-8 — sin ``bayesiana``, la corrida de referencia mide igual: para al pasar de los fallos admitidos."""
    seg = Seguimiento(200, 0.95)
    assert not _hasta_parar(seg, [False] * 10)
    assert seg.anota(False) and seg.fraccion() == pytest.approx(189 / 200)
    assert not _hasta_parar(Seguimiento(200, 0.95), [True] * 200)
