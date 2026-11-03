"""Spec 070 — el asistente opera el conversor de punta a punta.

Rutas y cola reales con ``TestClient``. Solo se sustituyen, y se dice en cada prueba, los motores que tocan
DIgSILENT o la GPU: lo que hagan de verdad allí queda en las tareas ``[DIgSILENT]`` de la spec.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.web import asistente_operacion as operacion
from convertersmartgrid.web import services
from convertersmartgrid.web.app import create_app

RAIZ = Path(__file__).resolve().parents[1]
VOCAB = {'alimentadores': ['F1', 'F2', 'F3', 'F4'], 'proyecto': ['P1'], 'sistema': ['S1'], 'set': ['SETA'],
         'subtipo': ['refuerzo de red']}


class Modelo:
    """Doble del modelo de órdenes: dice la tarea y los datos que se le piden."""

    tareas = ('estado',)

    def __init__(self, tarea='estado', **datos):
        self.tarea, self.datos = tarea, {k: [{'valor': v} for v in (vs if isinstance(vs, list) else [vs])]
                                         for k, vs in datos.items()}

    def predecir(self, texto):
        return {'tarea': self.tarea, 'confianza': 1.0, 'datos': self.datos}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / 'gemelo'))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'gpu.lock'))
    monkeypatch.setattr(services, 'asistente_vocabulario', lambda ws: dict(VOCAB))
    services._ASISTENTE_PLANES.clear()
    yield tmp_path
    services._ASISTENTE_PLANES.clear()


@pytest.fixture
def api(entorno):
    app = create_app(entorno / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        yield cliente, app


def esperar(cliente, id_trabajo):
    limite = time.monotonic() + 20
    while time.monotonic() < limite:
        r = cliente.get(f'/api/jobs/{id_trabajo}').json()
        if r['status'] in ('done', 'failed', 'cancelled'):
            return r
        time.sleep(0.02)
    pytest.fail('la cola no terminó')


def espacio(cliente, app):
    wid = cliente.post('/api/workspaces', json={'name': 'maestro'}).json()['id']
    return wid, app.state.store.get(wid)


def proponer(cliente, wid, monkeypatch, modelo, texto='haz la orden'):
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (modelo, None))
    r = cliente.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': texto})
    assert r.status_code == 202, r.text
    fin = esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin['error']
    return fin['result']


def confirmar(cliente, wid, plan):
    r = cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar")
    assert r.status_code == 202, r.text
    return esperar(cliente, r.json()['id'])


def con_calibracion(monkeypatch, token='t1'):
    """La calibración en disco, sustituida: el informe real lo deja ``ajuste_cabecera_pf.py`` en DIgSILENT."""
    fila = {'id': f'disco:{token}', 'project': 'P1', 'feeders': ['F1'], 'informes': []}
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda ws, project, token=None: dict(fila))
    return fila


# ------------------------------------------------------------------ T1, huecos del ejecutor
def test_huecos_estudios_sin_calibracion_lo_dice_en_el_plan(api, monkeypatch):
    """070:RF-2 — sin calibración no se ofrece confirmar: antes fallaba después de confirmar."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    plan = proponer(cliente, wid, monkeypatch, Modelo('estudios', proyecto='P1', alimentadores='F1'))['plan']
    assert not plan['listo'] and any('calibración' in f for f in plan['faltan'])


def test_huecos_estudios_llegan_a_la_ruta_con_su_base_y_su_catalogo(api, monkeypatch):
    """070:RF-1 / 070:RF-3 — la ruta real recibe la última calibración, y el catálogo es el del proyecto."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    fila = con_calibracion(monkeypatch)
    pedidos, catalogos = [], []
    original = services.estudios_catalogo

    def catalogo(ws=None, project=''):
        catalogos.append(project)
        return original(ws, project)

    monkeypatch.setattr(services, 'estudios_catalogo', catalogo)
    monkeypatch.setattr(services, 'estudios_plan', lambda ws, project, feeders, estudios, ajuste, *a: (
        pedidos.append((project, estudios, ajuste)) or {'token': 'tk'}))
    monkeypatch.setattr(services, 'estudios_ejecutar', lambda ws, ctx, token: {'ok': token})
    wid_ws = app.state.store.get(wid)
    wid_ws.cargas_planes['tk'] = {'kind': 'estudios', 'project': 'P1', 'feeders': ['F1']}
    plan = proponer(cliente, wid, monkeypatch, Modelo('estudios', proyecto='P1', alimentadores='F1'))['plan']
    assert plan['listo'], plan['faltan']
    fin = confirmar(cliente, wid, plan)
    assert fin['status'] == 'done', fin['error']
    assert pedidos[0][0] == 'P1' and pedidos[0][2]['id'] == fila['id'] and pedidos[0][1]
    assert 'P1' in catalogos


def test_huecos_estudio_nombrado_corre_solo_ese(api, monkeypatch):
    """070:RF-4 — con un estudio nombrado, solo ese."""
    from convertersmartgrid.asistente.ejecutor import pasos

    lista = pasos('estudios', {'proyecto': 'P1', 'alimentadores': ['F1'], 'estudio': 'flujo'})
    resultados = [{'ajuste': {'id': 'disco:t'}}, {'ofrecidos': [{'clave': 'flujo'}, {'clave': 'troncal'}]}]
    assert lista[2].cuerpo(resultados)['estudios'] == ['flujo']


def test_huecos_estudio_no_ofrecido_dice_su_motivo(api, monkeypatch):
    """070:RF-5 — el motivo es el del catálogo, no una suposición."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    con_calibracion(monkeypatch)
    monkeypatch.setattr(services, 'estudios_catalogo', lambda ws=None, project='': {
        'ofrecidos': [], 'no_ofrecidos': [{'clave': 'fiabilidad', 'nombre': 'Confiabilidad', 'motivo': 'faltan datos: tasas'}]})
    plan = proponer(cliente, wid, monkeypatch, Modelo('estudios', proyecto='P1', alimentadores='F1', estudio='fiabilidad'))['plan']
    assert not plan['listo'] and any('faltan datos: tasas' in f for f in plan['faltan'])


def test_huecos_sistema_usa_la_carpeta_de_los_libros_del_espacio(api, monkeypatch, tmp_path):
    """070:RF-6 — sin carpeta en la orden, la de los libros asignados en la web."""
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.dataset = object()
    (tmp_path / 'libros').mkdir()
    ws.demanda['medidores'] = {'path': str(tmp_path / 'libros' / 'medidores.xlsx')}
    plan = proponer(cliente, wid, monkeypatch, Modelo('sistema_completo', sistema='S1', periodo='2026-07'))['plan']
    assert plan['listo'], plan['faltan']
    assert plan['datos']['ruta'] == str(tmp_path / 'libros')


def test_huecos_sistema_sin_libros_lo_dice(api, monkeypatch):
    """070:RF-7 — sin carpeta ni libros, el plan lo dice: antes moría el proceso por una opción obligatoria."""
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.dataset = object()
    plan = proponer(cliente, wid, monkeypatch, Modelo('sistema_completo', sistema='S1', periodo='2026-07'))['plan']
    assert not plan['listo'] and any('libros' in f for f in plan['faltan'])


def test_huecos_proyecto_para_antes_de_la_primera_etapa(tmp_path):
    """070:RF-8 — sin los libros no se empieza por cargar la fuente para caer en la etapa siguiente."""
    from convertersmartgrid.asistente.ejecutor import ClienteWeb
    from convertersmartgrid.asistente.orquestador import PuntoDeControl, ejecutar_proyecto

    class SinRed:
        def request(self, *_a, **_k):
            pytest.fail('no debía llamar a la web')

    with pytest.raises(ValueError, match='ruta'):
        ejecutar_proyecto({'sistema': 'S1', 'periodo': '2026-07'}, cliente=ClienteWeb(SinRed(), 'http://x', 'w'),
                          control=PuntoDeControl.abrir(tmp_path / 'c.json'), proceso=lambda *_a: pytest.fail('no'))


def test_huecos_cargas_en_bloque_con_su_base(api, monkeypatch, tmp_path):
    """070:RF-9 — sin calibración lo dice; con ella, la base llega al plan de cargas."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    libro = tmp_path / 'cargas.xlsx'
    libro.write_bytes(b'x')
    modelo = Modelo('cargas_nuevas', proyecto='P1', alimentadores='F1', ruta=str(libro))
    plan = proponer(cliente, wid, monkeypatch, modelo)['plan']
    assert not plan['listo'] and any('calibración' in f for f in plan['faltan'])
    from convertersmartgrid.asistente.ejecutor import pasos

    lista = pasos('cargas_nuevas', {'proyecto': 'P1', 'alimentadores': ['F1'], 'ruta': str(libro)})
    assert lista[1].cuerpo([{'ajuste': {'id': 'disco:t'}}])['ajuste_job_id'] == 'disco:t'


def test_huecos_factibilidad_sin_solicitud(api, monkeypatch):
    """070:RF-10 — el formulario sin solicitud se dice antes: la ruta lo rechazaba después de confirmar."""
    monkeypatch.setattr(services, 'carga_del_informe', lambda *_a: {'sola': True})
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.informes['formularios']['P1'] = {'factibilidad': {'lugar': 'x'}}
    plan = proponer(cliente, wid, monkeypatch, Modelo('informe_factibilidad', proyecto='P1', alimentadores='F1', sed='S9'))['plan']
    assert not plan['listo'] and any('solicitud' in f for f in plan['faltan'])


def test_huecos_factibilidad_dice_como_conectarla(api, monkeypatch):
    """070:RF-11 — el operador sabe qué pedir: la carga sola."""
    def no_existe(*_a):
        raise services.UserError('S9 no es una carga nueva aplicada')

    monkeypatch.setattr(services, 'carga_del_informe', no_existe)
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.informes['formularios']['P1'] = {'factibilidad': {'solicitud': {'cliente': 'c'}}}
    plan = proponer(cliente, wid, monkeypatch, Modelo('informe_factibilidad', proyecto='P1', alimentadores='F1', sed='S9'))['plan']
    assert any('carga nueva sola' in f for f in plan['faltan'])


def test_huecos_informe_de_estudio_por_alimentador():
    """070:RF-12 — antes se perdían todos menos el primero."""
    from convertersmartgrid.asistente.ejecutor import pasos

    lista = pasos('informe_estudio', {'proyecto': 'P1', 'alimentadores': ['F1', 'F2']}, {'formulario': {'lugar': 'x'}})
    assert [p.cuerpo['alimentador'] for p in lista] == ['F1', 'F2']
    assert all(p.ruta == '/informes/estudio' for p in lista)


@pytest.mark.parametrize('tarea', ['obras_escalera', 'optimizar_con_proyecto'])
def test_huecos_obras_envian_capex_y_tipo_de_cambio(tarea):
    """070:RF-13 — el libro CAPEX y el tipo de cambio llegan a la ruta."""
    from convertersmartgrid.asistente.ejecutor import pasos

    cuerpo = pasos(tarea, {'proyecto': 'P1', 'alimentadores': ['F1'], 'ruta': 'D:/capex.xlsx'}, {'tipo_cambio': 3.75})[0].cuerpo
    assert cuerpo['capex'] == 'D:/capex.xlsx' and cuerpo['tipo_cambio'] == 3.75


def test_huecos_obras_sin_perfil_para_costear(api, monkeypatch):
    """070:RF-14 — el motivo es el de ``escalera_optima``: antes se veía tras confirmar."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *_a, **_k: {'id': 'disco:t'})
    plan = proponer(cliente, wid, monkeypatch, Modelo('obras_escalera', proyecto='P1', alimentadores='F1'))['plan']
    assert not plan['listo'] and any('perfil de empresa' in f for f in plan['faltan'])


def test_huecos_obras_tipo_de_cambio_de_la_orden(api, monkeypatch):
    """070:RF-14 — el tipo de cambio de la orden se usa para comprobar y queda para la ruta."""
    vistos = []
    monkeypatch.setattr(operacion, 'parametros_de_costeo', lambda tc: vistos.append(tc))
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *_a, **_k: {'id': 'disco:t'})
    plan = proponer(cliente, wid, monkeypatch, Modelo('obras_escalera', proyecto='P1', alimentadores='F1'),
                    'corre la escalera con tipo de cambio de 3,75')['plan']
    assert plan['listo'], plan['faltan']
    assert vistos == [3.75]


def test_huecos_set_nueva_directa_sin_capex(api, monkeypatch):
    """070:RF-15 — la SET nueva sale de los módulos del libro CAPEX: sin él, se dice antes."""
    monkeypatch.setattr(operacion, 'parametros_de_costeo', lambda tc: None)
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    plan = proponer(cliente, wid, monkeypatch, Modelo('optimizar_con_proyecto', proyecto='P1', alimentadores='F1'),
                    'manda las cargas directo a una set nueva')['plan']
    assert not plan['listo'] and any('CAPEX' in f for f in plan['faltan'])


def test_huecos_entregables_de_todos_los_pasos():
    """070:RF-16 — con un informe por alimentador se perdían todos los Word menos el último."""
    from convertersmartgrid.asistente.ejecutor import ClienteWeb, Paso, ejecutar

    class Web:
        def __init__(self):
            self.n = 0

        def request(self, metodo, url, **kw):
            self.n += 1

            class R:
                status_code, content = 200, b'x'
                json = staticmethod(lambda n=self.n: {'informe': f'informe{n}.docx'})

            return R()

    r = ejecutar([Paso('uno', 'POST', '/a', {}), Paso('dos', 'POST', '/b', {})], ClienteWeb(Web(), 'http://x', 'w'))
    assert r['entregables'] == ['informe1.docx', 'informe2.docx']

