"""Spec 022, T5: el oráculo sobre la red unida por SET."""
from __future__ import annotations

from dataclasses import replace

import pytest

from igea_dgs import oraculo
from igea_dgs.combine import combine_models, estructurar
from igea_dgs.enlaces import abrir_caminos_cerrados
from igea_dgs.estructura import estructura_de_dict
from test_combine import _alimentador

pytest.importorskip('pandapower')

E = estructura_de_dict({'zonales': [
    {'nombre': 'Norte', 'sets': [{'codigo': 'SET 1', 'nombre': 'Uno', 'alimentadores': ['A', 'B']}]},
    {'nombre': 'Sur', 'sets': [{'codigo': 'SET 2', 'nombre': 'Dos', 'alimentadores': ['C']}]}]})


def _red(kw_c=50.0):
    a = _alimentador('A', 10.0, ['A_H', 'A_1', 'A_2'], con_carga='A_2')
    b = _alimentador('B', 22.9, ['B_H', 'B_1'], con_carga='B_1')
    c = _alimentador('C', 10.0, ['C_H', 'C_1', 'C_2'], con_carga='C_2')
    c.loads[0] = replace(c.loads[0], p_mw=kw_c / 1000.0, q_mvar=kw_c / 5000.0)
    red, _ = combine_models([a, b, c])
    estructurar(red, E)
    abrir_caminos_cerrados(red)
    return red


def test_la_red_unida_converge_con_su_veredicto_por_set_y_zonal():
    """022:RF-28, 022:RF-32 — el flujo de la red unida entera, una isla por barra de SET y
    tensión, con su P y su tensión mínima, y el resumen por zonal."""
    r = oraculo.validar_unida(_red(), consigna_pu=1.05)
    assert r.convergio and not r.general.errores
    assert sorted(i.fuente for i in r.islas) == ['SET 1', 'SET 1', 'SET 2']
    assert all(i.convergio and i.p_mw > 0 and i.v_min_pu <= 1.05 for i in r.islas)
    z = r.por_zonal()
    assert z['Norte']['fuentes'] == 2 and z['Sur']['fuentes'] == 1
    assert r.general.v_max_pu == pytest.approx(1.05, abs=1e-3)


def test_la_isla_que_no_converge_se_nombra_con_su_barra_y_su_transformador():
    """022:RF-33 — una SED de 100 kVA con 2 MW: la isla de SET 2 no converge y se dice, con
    la fracción de su carga con que converge, su barra más débil y su transformador; la de
    SET 1 sí converge."""
    r = oraculo.validar_unida(_red(kw_c=2000.0))
    assert not r.convergio
    sur = next(i for i in r.islas if i.fuente == 'SET 2')
    assert not sur.convergio and 0 < sur.escala_converge < 1
    assert sur.trafo_mas_cargado == 'TR_SE_C' and sur.barra_v_min
    assert all(i.convergio for i in r.islas if i.fuente == 'SET 1')
    [h] = [h for h in r.general.errores if h.codigo == 'isla_no_converge']
    assert 'SET 2' in h.texto and 'TR_SE_C' in h.texto and '022:RF-33' in h.texto
    assert r.por_zonal()['Sur']['no_convergen'] == ['SET 2']
