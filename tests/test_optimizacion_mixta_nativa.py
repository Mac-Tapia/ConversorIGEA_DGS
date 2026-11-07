"""Spec 048, T4: las obras aplicadas persisten en DIgSILENT sin tocar el caso de referencia (048:RF-9).

Las comprobaciones de ``tools/aceptacion_nativa.py`` con lecturas mínimas, y la evidencia nativa de
``CSG_EVIDENCIA_NATIVA`` (DIgSILENT real, fuera de pytest por 084:RF-21) releída y vuelta a decidir.
"""
from __future__ import annotations

import pytest
from apoyo import cargar_herramienta, evidencia_nativa
from test_verificacion_top_k_nativa import lectura


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('aceptacion_nativa.py', 'aceptacion_nativa_048', tools_en_path=True)


def test_la_referencia_que_cambia_se_nota(guion):
    """048:RF-9 — dos lecturas del mismo caso en sesiones distintas tienen que dar la misma red: una tensión
    que se mueve más que la tolerancia declarada o un banco cambiado es otra referencia."""
    a = lectura('sin_proyecto', bancos=[('BC1', 0.3)])
    assert guion.comparar_lecturas(a, lectura('sin_proyecto', bancos=[('BC1', 0.3)]))['ok']
    movida = guion.comparar_lecturas(a, lectura('sin_proyecto', bancos=[('BC1', 0.3)], u=1.0 - 10 * guion.TOL_V_PU))
    assert not movida['ok'] and any('tensión' in m for m in movida['motivos'])
    otro_banco = guion.comparar_lecturas(a, lectura('sin_proyecto', bancos=[('BC1', 0.45)]))
    assert not otro_banco['ok'] and any('controls_hash' in m for m in otro_banco['motivos'])


def test_obras_persisten_sin_tocar_referencia():
    """048:RF-9 — con DIgSILENT real: la obra sigue en su variación y activa en «Con proyecto» tras reabrir en
    otra sesión, y el «Caso base» y «Sin proyecto» releídos son los de antes de aplicar (misma topología,
    controles, bancos, tensiones y cabeceras)."""
    _g, _c, _m, veredictos = evidencia_nativa('obras')
    checks = veredictos['048']['checks']
    for nombre in ('persistencia_del_guion', 'con_proyecto_releido', 'obra_presente', 'caso_base_intacto',
                   'sin_proyecto_intacto'):
        assert checks[nombre]['ok'], (nombre, checks[nombre])


def test_demanda_no_cae_artificialmente():
    """048:RF-9 — con DIgSILENT real: «Con proyecto» con la obra atiende la misma demanda que «Sin proyecto»
    y no deja barras sin tensión que antes tenían."""
    _g, _c, _m, veredictos = evidencia_nativa('obras')
    assert veredictos['048']['checks']['demanda_atendida']['ok'], veredictos['048']['checks']['demanda_atendida']
