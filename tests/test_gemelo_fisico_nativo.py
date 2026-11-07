"""Spec 045, T4: contraste del gemelo físico con la red nativa de su mismo alcance (045:RF-11).

El gemelo físico es el flujo mallado de ``digital_twin.flujo`` (CPU); el contraste se hace con cada caso
releído en DIgSILENT tras reabrir, de la evidencia de ``CSG_EVIDENCIA_NATIVA`` (fuera de pytest, 084:RF-21).
"""
from __future__ import annotations

import pytest
from apoyo import cargar_herramienta, evidencia_nativa
from test_verificacion_top_k_nativa import lectura


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('aceptacion_nativa.py', 'aceptacion_nativa_045', tools_en_path=True)


def test_banco_no_declarado_rompe_el_inventario(guion):
    """045:RF-11 — bancos y centrales tienen que coincidir antes y después, salvo la obra declarada."""
    antes = {'sin_proyecto': lectura('sin_proyecto', bancos=[('BC1', 0.3)])}
    bien = {'sin_proyecto': lectura('sin_proyecto', bancos=[('BC1', 0.3)]),
            'con_proyecto': lectura('con_proyecto', bancos=[('BC1', 0.3), ('BC_OBRA', 0.3)], variaciones=['V'])}
    v = guion.veredicto_045(bien, antes, pedidos=[], bancos_declarados=['ElmShnt:BC_OBRA'], tolerancia_v_pu=0.01,
                            variacion='V')
    assert v['inventario_ok'], v['inventario']
    v = guion.veredicto_045(bien, antes, pedidos=[], bancos_declarados=[], tolerancia_v_pu=0.01, variacion='V')
    assert not v['inventario']['con_proyecto']['ok']


def test_contraste_nativo_cuatro_casos():
    """045:RF-11 — con DIgSILENT real: se piden los cuatro papeles de caso y cada uno se relee explícitamente
    tras reabrir; el que el proyecto no tiene queda declarado con lo que respondió DIgSILENT, no omitido, y
    cada releído lleva el contraste del gemelo físico con sus tensiones."""
    guion, _c, _m, veredictos = evidencia_nativa('obras')
    v = veredictos['045']
    assert set(v['roles']) == set(guion.ROLES)
    for rol, r in v['roles'].items():
        if r['releido']['ok']:
            c = r['contraste']
            assert c and c['barras_contrastadas'] > 0 and c['mae_v_pu'] is not None, (rol, c)
        else:
            assert r['releido']['motivos'], rol


def test_central_y_bancos_persisten():
    """045:RF-11 — con DIgSILENT real: bancos y centrales releídos coinciden con los de antes, y en «Con
    proyecto» solo se añade el banco de la obra declarada."""
    _g, _c, _m, veredictos = evidencia_nativa('obras')
    assert veredictos['045']['inventario_ok'], veredictos['045']['inventario']
