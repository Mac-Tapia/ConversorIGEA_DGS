"""Spec 049, T4: validación y persistencia de las protecciones en DIgSILENT (049:RF-9).

Ninguna fuente trae fichas de protecciones: sin dispositivos con curva y ajustes no hay ajustes que aplicar,
reabrir y releer. Lo que se prueba es que la evidencia nativa (``CSG_EVIDENCIA_NATIVA``, fuera de pytest por
084:RF-21) guarda la lista de bloqueo y no da la tarea por cerrada.
"""
from __future__ import annotations

import pytest
from apoyo import cargar_herramienta, evidencia_nativa


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('aceptacion_nativa.py', 'aceptacion_nativa_049', tools_en_path=True)


def test_sin_fichas_no_se_cierra(guion):
    """049:RF-9 — ni un ``ComShc`` que se ejecuta ni una disponibilidad bloqueada cierran la persistencia de los
    ajustes: el veredicto guarda lo que falta."""
    v = guion.veredicto_049({'informe': {'version': '24.0.2', 'clases': {'ElmRelay': {'cuantos': 0}},
                                         'comandos': {'ComShc': {'existe': True, 'ejecuta': True}}}},
                            {'disponibilidad': {'disponible': False, 'faltan': ['fichas'], 'bloqueos': []}})
    assert v['nativo'] and v['bloqueo'] == ['fichas'] and v['cerrable'] is False


def test_protecciones_nativas_bloqueadas_con_su_lista():
    """049:RF-9 — con DIgSILENT real: la versión conectada y sus órdenes quedan comprobadas, el proyecto no
    tiene dispositivos de protección, y la evidencia guarda la lista de bloqueo sin dar la T4 por cerrada."""
    _g, _c, _m, veredictos = evidencia_nativa('protecciones')
    v = veredictos['049']
    assert v['nativo'] and v['version']
    assert v['comandos']['ComShc']['existe'] and v['comandos']['ComShc']['ejecuta'] is not None
    if not v['disponible']:
        assert v['bloqueo'], v
    assert v['cerrable'] is False
