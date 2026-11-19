"""Spec 026, RF-44 (T18): el asistente hace los módulos que le faltaban, el Estudio VNR por la Guía 232 (spec 108) y la
Evolución de clientes fijos (spec 105), por las mismas rutas de la web (usuario, 2026-11-18: «el asistente debe controlar
el SmartConverter de punta a punta»).

Las dos escriben su resultado en el espacio, así que esperan la confirmación del operador. El VNR toma por defecto la red
que dejó la carga y el SICODI de las fuentes del espacio, como la pestaña; de la orden solo salen sus datos.
"""
from __future__ import annotations

from convertersmartgrid.aplicacion.asistente import ejecutor, tareas
from convertersmartgrid.aplicacion.asistente.interprete import _por_frase_literal

from test_asistente_107_112 import _orden, web_vad  # noqa: F401  (el mismo arnés de la web que el VAD)

MODULOS = ('vnr_estudio', 'clientes_fijos_evolucion')


def test_026_rf44_vnr_y_clientes_fijos_son_ordenes_que_escriben_y_se_reconocen():
    """026:RF-44 — las dos órdenes están en el catálogo, escriben (esperan la confirmación) y se reconocen por su frase
    mientras el modelo en uso no las conozca (067:RF-36)."""
    faltan = [t for t in MODULOS if t not in tareas.TAREAS]
    assert faltan == [], f'órdenes que el asistente aún no tiene: {faltan}'
    for tarea in MODULOS:
        assert tareas.EFECTOS.get(tarea) == (tareas.ESCRIBE,) and tareas.TAREAS[tarea].escribe, tarea
    assert _por_frase_literal('haz el estudio VNR de la red con el SICODI', None) == 'vnr_estudio'
    assert _por_frase_literal('calcula el valor nuevo de reemplazo de la red', None) == 'vnr_estudio'
    assert _por_frase_literal('evolución de los clientes fijos de AL101 de 2025-01 a 2025-06', None) == \
        'clientes_fijos_evolucion'


def test_026_rf44_sus_pasos_van_a_las_rutas_de_la_web():
    """026:RF-44 — el VNR va por POST /vnr/estudio como formulario (sector, SICODI, resolución, año y moneda; la red y el
    SICODI, los del espacio) y la evolución por POST /clientes-fijos/evolucion con sus alimentadores y su rango."""
    assert hasattr(ejecutor, '_pasos_026_rf44'), 'el ejecutor no sabe los pasos de los módulos 105 y 108'
    vnr = {'sector': 'urbano_rural', 'sector_sicodi': '3', 'resolucion': '158-2023-OS/CD', 'anio': 2025, 'moneda': 'PEN'}
    (paso,) = ejecutor.pasos('vnr_estudio', {}, {'vnr': vnr})
    assert (paso.metodo, paso.ruta, paso.formulario) == ('POST', '/vnr/estudio', True), paso
    assert paso.cuerpo == vnr and paso.archivos is None, paso.cuerpo
    fijos = {'desde': '2025-01', 'hasta': '2025-06', 'con_cabecera': False}
    (paso,) = ejecutor.pasos('clientes_fijos_evolucion', {'alimentadores': ['AL101', 'AL102']}, {'clientes_fijos': fijos})
    assert (paso.metodo, paso.ruta, paso.formulario) == ('POST', '/clientes-fijos/evolucion', False), paso
    assert paso.cuerpo == {'alimentadores': ['AL101', 'AL102'], 'desde': '2025-01', 'hasta': '2025-06',
                           'con_cabecera': False}, paso.cuerpo


def test_026_rf44_por_la_web_la_orden_completa_espera_confirmacion_y_sin_datos_dice_que_falta(web_vad):
    """026:RF-44 — por la web real, «haz el estudio VNR … sector SICODI 3, resolución …, 2025» queda lista esperando la
    confirmación del operador, con la resolución entera y el año de la valorización (no el de la resolución); sin sus
    datos, el plan dice cuáles faltan y no se ofrece."""
    cliente, _app = web_vad
    wid = cliente.post('/api/workspaces').json()['id']
    plan = _orden(cliente, wid, 'haz el estudio VNR del sector urbano rural con sector SICODI 3, resolución '
                                '158-2023-OS/CD, para 2025 en soles')
    assert plan['tarea'] == 'vnr_estudio' and plan['listo'] and plan['espera_confirmacion'], plan.get('faltan')
    plan = _orden(cliente, wid, 'haz el estudio VNR de la red')
    assert plan['tarea'] == 'vnr_estudio' and not plan['listo'], plan
    assert any('SICODI' in f for f in plan['faltan']) and any('resolución' in f for f in plan['faltan']), plan['faltan']
    plan = _orden(cliente, wid, 'histórico de los clientes fijos')
    assert plan['tarea'] == 'clientes_fijos_evolucion' and not plan['listo'], plan
    assert any('meses' in f for f in plan['faltan']), plan['faltan']
