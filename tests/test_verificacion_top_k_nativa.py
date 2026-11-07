"""Spec 044, T4: el diseño confirmado se relee en DIgSILENT tras una sesión nueva (044:RF-9).

Las de arriba prueban las comprobaciones de ``tools/aceptacion_nativa.py`` con lecturas mínimas; la última
relee la evidencia nativa de ``CSG_EVIDENCIA_NATIVA`` (DIgSILENT real, fuera de pytest por 084:RF-21) y vuelve
a decidir con ella. Ningún doble cierra la tarea.
"""
from __future__ import annotations

import pytest
from apoyo import cargar_herramienta, evidencia_nativa


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('aceptacion_nativa.py', 'aceptacion_nativa_044', tools_en_path=True)


def lectura(rol: str, *, bancos=(), variaciones=(), version='24.0.2', reabierta=True, u=1.0) -> dict:
    """Una lectura nativa mínima: dos barras, un tramo, sus bancos y el flujo."""
    barras = {'ElmTerm:B1': {'nombre': 'B1', 'kv': 10.0}, 'ElmTerm:B2': {'nombre': 'B2', 'kv': 10.0}}
    nodos = {k: {'kv': 10.0, 'carga_p_mw': 0.5 if k.endswith('2') else 0.0, 'fuente': k.endswith('1'), 'v_pu': 1.0}
             for k in barras}
    return {'pf_version': version, 'reopen_verified': reabierta,
            'caso_nativo': {'rol': rol, 'nombre': rol, 'id': f'IntCase:{rol}'},
            'topologia': {'variaciones_activas': list(variaciones), 'barras': barras, 'grafo': {
                'version': 3, 'nodos': nodos, 'generadores': [],
                'ramas': [{'id': 'ElmLne:L1', 'desde': 'ElmTerm:B1', 'hasta': 'ElmTerm:B2', 'cerrada': True,
                           'r_ohm': 0.5, 'x_ohm': 0.5}],
                'bancos': [{'id': f'ElmShnt:{n}', 'nodo': 'ElmTerm:B2', 'q_mvar': q, 'en_servicio': True,
                            'escalones': 1.0} for n, q in bancos]}},
            'flujo': {'tensiones': {'valores': {'ElmTerm:B1': 1.0, 'ElmTerm:B2': u}},
                      'balance': {'valores': {'cabeceras': {'F1': 500.0}}}}}


def test_la_relectura_exige_version_reapertura_caso_y_variacion(guion):
    """044:RF-9 — una lectura sin versión de DIgSILENT, sin reabrir, de otro caso o sin la variación de la obra
    no confirma nada."""
    assert guion.releida(lectura('con_proyecto', variaciones=['V1']), 'con_proyecto', ['V1'])['ok']
    for mala, motivo in ((lectura('con_proyecto', variaciones=['V1'], version=None), 'versión'),
                         (lectura('con_proyecto', variaciones=['V1'], reabierta=False), 'reapertura'),
                         (lectura('sin_proyecto', variaciones=['V1']), 'caso'),
                         (lectura('con_proyecto'), 'activas')):
        r = guion.releida(mala, 'con_proyecto', ['V1'])
        assert not r['ok'] and any(motivo in m for m in r['motivos']), r


def test_la_obra_que_no_esta_tras_reabrir_no_se_confirma(guion):
    """044:RF-9 — el banco de la obra tiene que estar tras reabrir, en su barra y con su potencia."""
    sin = lectura('sin_proyecto', bancos=[('BC1', 0.3)])
    con = lectura('con_proyecto', bancos=[('BC1', 0.3), ('BC_OBRA', 0.3)])
    assert guion.obra_presente(sin, con, 'B2', 300.0)['ok']
    assert not guion.obra_presente(sin, sin, 'B2', 300.0)['ok']
    assert not guion.obra_presente(sin, con, 'B2', 450.0)['ok']
    otro = lectura('con_proyecto', bancos=[('BC1', 0.45), ('BC_OBRA', 0.3)])
    assert any('existentes' in m for m in guion.obra_presente(sin, otro, 'B2', 300.0)['motivos'])


def test_top_k_nativo_reabre_y_relee():
    """044:RF-9 — con DIgSILENT real: tras una sesión nueva se releen los controles (la variación activa y el
    banco en su barra) y los resultados (tensión mínima y pérdidas no negativas), y la decisión de
    ``verificar_top_k`` sale de esa relectura: un caso que converge con violaciones se rechaza por la evaluación
    eléctrica, no por converger."""
    _g, _c, manifiesto, veredictos = evidencia_nativa('obras')
    v = veredictos['044']
    lecturas = manifiesto['obras']['lecturas']
    # Cada relectura es un proceso propio: una sesión nueva de DIgSILENT, no la que escribió.
    assert len({x['pid'] for x in lecturas.values()}) == len(lecturas)
    assert v['reabierto']['ok'], v['reabierto']
    assert v['obra_presente']['ok'], v['obra_presente']
    assert v['resultados']['ok'], v['resultados']
    assert v['aceptada'] or v['rechazo_electrico'], v
    if v['rechazo_electrico']:
        assert not v['top_k']['verificada'] and v['juicio']['violaciones']
    assert v['cerrable']
