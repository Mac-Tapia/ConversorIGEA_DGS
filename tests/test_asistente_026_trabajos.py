"""026:RF-43 — el asistente controla los trabajos: carril, avance y resultado de cada uno, y repetir el último que falló
con sus mismos datos (cancelar ya estaba: 070:RF-32). Repetir rehace el plan con el sello de ahora y su confirmación;
nunca relanza a ciegas el trabajo viejo.
"""
from __future__ import annotations

from types import SimpleNamespace

from convertersmartgrid.aplicacion.asistente.interprete import _por_frase_literal
from convertersmartgrid.aplicacion.asistente.plan import Plan
from convertersmartgrid.aplicacion.asistente.planes_guardados import PlanesGuardados
from convertersmartgrid.aplicacion.asistente.tareas import EFECTOS, TAREAS
from convertersmartgrid.presentacion.web import services

TRABAJOS = [
    {'id': 'a', 'kind': 'convert', 'title': 'Convertir la red de prueba', 'status': 'failed', 'lane': 'engine',
     'progress': 40, 'error': 'falta la carga'},
    {'id': 'b', 'kind': 'pf_flow', 'title': 'Flujo de prueba', 'status': 'running', 'lane': 'powerfactory',
     'progress': 25, 'error': None},
    {'id': 'c', 'kind': 'asistente_interpretar', 'title': 'Interpretar la orden', 'status': 'running', 'lane': 'asistente'},
]


def test_026_rf43_el_estado_dice_el_carril_el_avance_y_el_ultimo_que_fallo(tmp_path, monkeypatch):
    """026:RF-43: cada trabajo en curso con su carril y su avance; el último que falló con su motivo; sin «(s)»."""
    monkeypatch.setattr(services, 'feeder_rows', lambda ws: [{}, {}])
    ws = SimpleNamespace(dataset=None, out_dir=tmp_path / 'salida')
    r = services._asistente_respuesta(ws, SimpleNamespace(tarea='estado', datos={}), TRABAJOS)
    (en_curso,) = r['trabajos']
    assert en_curso == {'titulo': 'Flujo de prueba', 'estado': 'running', 'carril': 'powerfactory', 'avance': 25,
                        'error': None}
    assert r.get('ultimo_fallido', {}).get('titulo') == 'Convertir la red de prueba', '026:RF-43: no dice cuál falló'
    assert 'falta la carga' in r['texto'] and '(s)' not in r['texto'] and '1 trabajo en curso' in r['texto']


def test_026_rf43_repetir_es_una_orden_que_escribe_y_se_reconoce():
    """026:RF-43: «repite el último trabajo que falló» es su tarea, con efecto de escritura (espera la confirmación)."""
    assert 'repetir_trabajo' in TAREAS, '026:RF-43: el asistente no sabe repetir un trabajo que falló'
    assert TAREAS['repetir_trabajo'].escribe and 'escribe' in EFECTOS['repetir_trabajo']
    assert _por_frase_literal('repite el último trabajo que falló', None) == 'repetir_trabajo'
    assert _por_frase_literal('vuelve a lanzar lo que falló con los mismos datos', None) == 'repetir_trabajo'


def _guardar(raiz, plan_id, texto, tarea, datos, error):
    disco = PlanesGuardados(raiz)
    disco.guardar(Plan(plan_id, texto, tarea, True, 'trabajo', datos=datos), {}, SimpleNamespace(sello=lambda: 's'))
    disco.marcar(plan_id, 'pendiente', error=error)


def test_026_rf43_repetir_rehace_el_plan_del_ultimo_que_fallo_con_sus_datos(tmp_path, monkeypatch):
    """026:RF-43: el último plan que falló (no el cancelado) vuelve como plan nuevo con su tarea y sus datos."""
    assert hasattr(services, 'asistente_plan_repetido'), '026:RF-43: no se repite el último trabajo que falló'
    _guardar(tmp_path, 'a' * 12, 'convierte la red de prueba', 'convertir', {'alimentadores': ['A1']}, 'falta la carga')
    _guardar(tmp_path, 'b' * 12, 'para eso', 'cancelar_trabajo', {}, 'cancelado por el operador')
    llamadas = []

    def desde(ws, texto, tarea, datos, origen, motivo):
        llamadas.append((texto, tarea, datos, origen, motivo))
        return Plan('c' * 12, texto, tarea, True, 'trabajo', datos=dict(datos))

    monkeypatch.setattr(services, '_asistente_plan_desde', desde)
    orden = Plan('d' * 12, 'repite el último trabajo que falló', 'repetir_trabajo', True, 'trabajo')
    nuevo = services.asistente_plan_repetido(SimpleNamespace(root=tmp_path), orden)
    assert nuevo.tarea == 'convertir' and nuevo.datos == {'alimentadores': ['A1']} and nuevo.id != 'a' * 12
    ((texto, tarea, datos, origen, motivo),) = llamadas
    assert (texto, tarea, origen) == ('convierte la red de prueba', 'convertir', 'repeticion') and 'falta la carga' in motivo


def test_026_rf43_sin_ninguno_que_haya_fallado_lo_dice(tmp_path):
    """026:RF-43: sin un plan fallido (un cancelado no cuenta), la orden no queda lista y dice por qué."""
    assert hasattr(services, 'asistente_plan_repetido'), '026:RF-43: no se repite el último trabajo que falló'
    _guardar(tmp_path, 'b' * 12, 'para eso', 'cancelar_trabajo', {}, 'cancelado por el operador')
    orden = Plan('d' * 12, 'repite lo que falló', 'repetir_trabajo', True, 'trabajo')
    r = services.asistente_plan_repetido(SimpleNamespace(root=tmp_path), orden)
    assert r.tarea is None and any('ningún trabajo' in f for f in r.faltan)
