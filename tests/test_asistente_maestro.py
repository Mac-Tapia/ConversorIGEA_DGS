"""Spec 070 — el asistente opera el conversor de punta a punta.

Rutas y cola reales con ``TestClient``. Solo se sustituyen, y se dice en cada prueba, los motores que tocan
DIgSILENT o la GPU: lo que hagan de verdad allí queda en las tareas ``[DIgSILENT]`` de la spec.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.asistente import almacen
from convertersmartgrid.web import asistente_operacion as operacion
from convertersmartgrid.web import services
from convertersmartgrid.web.app import create_app

RAIZ = Path(__file__).resolve().parents[1]
#: Fijada antes de entrenar ningún candidato (070:RF-70): no se actualiza para que pase una prueba.
HUELLA_PRUEBA_SELLADA = 'df5e1db88595d378'
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


# ------------------------------------------------------------------ T2, tareas nuevas
def test_tareas_tipos_nuevos_al_final_para_los_modelos_heredados():
    """070:RF-17 / 070:RF-18 — la etiqueta de un modelo heredado es su posición: no se mueve ninguna."""
    from convertersmartgrid.asistente.datos_por_palabra import ETIQUETAS
    from convertersmartgrid.asistente.tareas import TIPOS_DATO

    previos = ('proyecto', 'alimentadores', 'sistema', 'periodo', 'caso', 'numero', 'ruta', 'sed', 'subtipo', 'texto')
    assert TIPOS_DATO[:len(previos)] == previos and {'set', 'estudio', 'alcance', 'anio'} <= set(TIPOS_DATO)
    assert ETIQUETAS[:1 + 2 * len(previos)] == ('O',) + tuple(f'{p}-{t}' for t in previos for p in ('B', 'I'))


@pytest.mark.parametrize('tarea, datos, extras, metodo, ruta, parte', [
    ('convertir_set', {'set': 'SETA'}, {}, 'POST', '/convert/sistema', {'sets': ['SETA']}),
    ('buscar_maxima', {}, {'maxima': {'medidores': [{'alimentador': 'F1', 'medidor': 'M1'}]}}, 'POST',
     '/demanda/cabecera/buscar', {'medidores': [{'alimentador': 'F1', 'medidor': 'M1'}]}),
    ('cruzar_clientes', {'alimentadores': ['F1'], 'periodo': '2026-07'}, {}, 'POST', '/demanda/clientes/cruzar',
     {'alimentadores': ['F1'], 'periodo': '2026-07'}),
    ('escanear', {'proyecto': 'P1', 'alimentadores': ['F1']}, {}, 'POST', '/powerfactory/escanear', {'feeders': ['F1']}),
    ('verificar_convergencia', {'proyecto': 'P1'}, {}, 'POST', '/powerfactory/verificar', {'project': 'P1'}),
    ('descargar_resultados', {'alimentadores': ['F1']}, {}, 'POST', '/outputs/archive', {'feeders': ['F1']}),
    ('pronostico', {'ruta': 'D:/m'}, {'pronostico': {'clase': 'cabecera'}}, 'POST', '/digital-twin/temporal',
     {'clase': 'cabecera', 'modo': 'pronostico'}),
])
def test_tareas_cada_una_por_su_ruta(tarea, datos, extras, metodo, ruta, parte):
    """070:RF-19 / 070:RF-22 / 070:RF-23 / 070:RF-27 / 070:RF-28 / 070:RF-35 / 070:RF-36 — la ruta del operador."""
    from convertersmartgrid.asistente.ejecutor import pasos

    p = pasos(tarea, datos, extras)[-1]
    assert (p.metodo, p.ruta) == (metodo, ruta)
    assert parte.items() <= p.cuerpo.items()


@pytest.mark.parametrize('tarea, ultimo', [('calibrar', 'aplicar'), ('simular_calibracion', 'simular')])
def test_tareas_calibrar_y_simular_usan_la_maxima_buscada(tarea, ultimo):
    """070:RF-24 / 070:RF-25 — relee proyectos, prepara el plan con la máxima y sin las centrales, y ejecuta."""
    from convertersmartgrid.asistente.ejecutor import pasos

    maxima = {'id': 'j1', 'result': {'resultados': [
        {'alimentador': 'F1', 'medidor': 'M1'}, {'alimentador': 'F2', 'medidor': 'M2', 'error': 'sin dato'},
        {'alimentador': 'Central F1', 'medidor': 'CT'}]}}
    lista = pasos(tarea, {'proyecto': 'P1'}, {'ultima_maxima': maxima})
    assert [p.ruta for p in lista[:2]] == ['/powerfactory/projects', '/demanda/ajuste/plan']
    assert lista[1].cuerpo['job_id'] == 'j1' and lista[1].cuerpo['medidores'] == ['M1']
    assert lista[2].ruta([{'token': 'tk'}]) == f'/demanda/ajuste/tk/{ultimo}'


@pytest.mark.parametrize('tarea', ['calibrar', 'simular_calibracion'])
def test_tareas_calibrar_sin_maxima_pide_buscarla(api, monkeypatch, tarea):
    """070:RF-24 — la máxima vive en memoria: tras un reinicio se dice que se vuelva a buscar."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    plan = proponer(cliente, wid, monkeypatch, Modelo(tarea, proyecto='P1'))['plan']
    assert not plan['listo'] and any('máxima' in f and 'busc' in f for f in plan['faltan'])


@pytest.mark.parametrize('alcance, datos, por_barra, de_60', [
    ('alimentadores', {'alimentadores': ['F1', 'F2']}, False, False),
    ('set', {'set': 'SETA'}, True, False),
    ('sistema', {'sistema': 'S1'}, True, True)])
def test_tareas_maxima_por_alcance(api, monkeypatch, alcance, datos, por_barra, de_60):
    """070:RF-22 — cada alcance con su criterio; no se mezclan (028:RF-27)."""
    cliente, app = api
    wid, ws = espacio(cliente, app)
    monkeypatch.setattr(services, 'estructura_resumen', lambda _ws: {'zonales': [
        {'nombre': 'S1', 'alimentadores': ['F1', 'F2'], 'sets_detalle': [{'codigo': 'SETA', 'alimentadores': ['F1', 'F2']}]}]})
    monkeypatch.setattr(services, 'medidores_por_alimentador', lambda _ws, a: {x: [f'M-{x}'] for x in a})
    pedidos = []
    monkeypatch.setattr(services, 'demanda_cabecera', lambda ws, ctx, pares, **kw: pedidos.append((pares, kw)) or {'resultados': []})
    r = proponer(cliente, wid, monkeypatch, Modelo('buscar_maxima', **datos), 'busca la máxima')
    assert r['plan']['listo'], r['plan']['faltan']
    assert esperar(cliente, r['trabajo']['id'])['status'] == 'done'
    pares, kw = pedidos[0]
    assert pares == [('F1', 'M-F1'), ('F2', 'M-F2')]
    assert (kw['por_barra'], kw['sistema_60kv'], kw['coincidente']) == (por_barra, de_60, alcance == 'alimentadores')


def test_tareas_maxima_sin_medidores_lo_dice(api, monkeypatch):
    """070:RF-22 — sin libro de medidores no se inventa ninguno."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    monkeypatch.setattr(services, 'medidores_por_alimentador', lambda _ws, a: {x: [] for x in a})
    plan = proponer(cliente, wid, monkeypatch, Modelo('buscar_maxima', alimentadores='F1'), 'busca la máxima')['plan']
    assert not plan['listo'] and any('medidor' in f for f in plan['faltan'])


def test_tareas_cruzar_con_la_fecha_de_la_maxima(api, monkeypatch):
    """070:RF-23 — el cruce lleva la fecha de la máxima de cada uno, como el front (035:RF-1)."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    vistos = []
    monkeypatch.setattr(services, 'demanda_clientes', lambda ws, a=None, periodo=None, maximas=None, criterio=None: (
        vistos.append((a, periodo, maximas)) or {'cruzados': []}))
    trabajo = {'id': 'j1', 'kind': 'demanda_cabecera', 'status': 'done', 'title': 'máxima', 'result': {'resultados': [
        {'alimentador': 'F1', 'medidor': 'M1', 'fecha': '2026-07-21 18:45', 'kw': 10.0, 'kvar': 1.0, 'fp': .99}]}}
    extras = operacion_extras_de(monkeypatch, trabajo)
    from convertersmartgrid.asistente.ejecutor import pasos

    plan = _plan('cruzar_clientes', {'alimentadores': ['F1'], 'periodo': '2026-07'})
    operacion.requisitos(services, app.state.store.get(wid), plan, extras)
    cuerpo = pasos('cruzar_clientes', plan.datos, extras)[0].cuerpo
    assert cuerpo['maximas']['F1']['fecha'] == '2026-07-21 18:45'


def _plan(tarea, datos, texto='orden'):
    from convertersmartgrid.asistente.plan import Plan
    from convertersmartgrid.asistente.tareas import TAREAS

    return Plan('a' * 12, texto, tarea, TAREAS[tarea].escribe, TAREAS[tarea].modo, datos=dict(datos))


def operacion_extras_de(_monkeypatch, *trabajos):
    return {'ultima_maxima': trabajos[-1], '_trabajos': list(trabajos)}


@pytest.mark.parametrize('texto, kw, fp', [
    ('conecta S9 de 800 kW en F1 de P1, fp 0,95, x 500100 y 8400200', 800.0, .95),
    ('conecta S9 de 1,5 MW en F1 x=500100 y=8400200', 1500.0, .98)])
def test_tareas_carga_sola_lee_la_orden(api, monkeypatch, texto, kw, fp):
    """070:RF-29 — con el mismo formulario de 3.2; el FP que no se dice es el que propone (y el plan lo avisa)."""
    con_calibracion(monkeypatch)
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    r = proponer(cliente, wid, monkeypatch, Modelo('carga_nueva_sola', proyecto='P1', alimentadores='F1', sed='S9'), texto)
    assert r['plan']['listo'], r['plan']['faltan']
    guardado = services.asistente_plan(app.state.store.get(wid), r['plan']['id'])
    nueva = guardado['extras']['nueva']
    assert (nueva['Kw'], nueva['FP'], nueva['alimentador'], nueva['CoordX'], nueva['CoordY']) == (kw, fp, 'F1', 500100.0, 8400200.0)
    if fp == .98:
        assert any('0,98' in x for x in r['plan']['razonamiento'])
    from convertersmartgrid.asistente.ejecutor import pasos

    cuerpo = pasos('carga_nueva_sola', guardado['plan'].datos, guardado['extras'])[1].cuerpo([{'ajuste': {'id': 'disco:t'}}])
    assert cuerpo['ajuste_job_id'] == 'disco:t' and '"Kw"' in cuerpo['nueva']


def test_tareas_carga_sola_entra_por_el_formulario_real(api, monkeypatch):
    """070:RF-29 — llega a la ruta real como formulario y se marca sola por venir de él."""
    con_calibracion(monkeypatch)
    llamadas = []

    def plan_real(ws, project, feeders, upd, cre, una, eco, ajuste, minima_m=None):
        llamadas.append((project, feeders, una, ajuste['id']))
        ws.cargas_planes['tk'] = {'project': project, 'feeders': feeders}
        return {'token': 'tk'}

    monkeypatch.setattr(services, 'cargas_plan', plan_real)
    monkeypatch.setattr(services, 'cargas_plan_de', lambda ws, t: ws.cargas_planes[t])
    monkeypatch.setattr(services, 'cargas_ejecutar', lambda ws, ctx, t, simular=False: {'ok': t})
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    r = proponer(cliente, wid, monkeypatch, Modelo('carga_nueva_sola', proyecto='P1', alimentadores='F1', sed='S9'),
                 'conecta S9 de 800 kW en F1 barra B7')
    fin = confirmar(cliente, wid, r['plan'])
    assert fin['status'] == 'done', fin['error']
    assert llamadas[0][:2] == ('P1', ['F1']) and llamadas[0][2]['barra'] == 'B7' and llamadas[0][3] == 'disco:t1'


@pytest.mark.parametrize('texto, falta', [('conecta S9 en F1 x 1 y 2', 'potencia'), ('conecta S9 de 800 kW en F1', 'ubicación')])
def test_tareas_carga_sola_sin_potencia_o_ubicacion(api, monkeypatch, texto, falta):
    """070:RF-30 — lo que no se dijo no se deduce."""
    con_calibracion(monkeypatch)
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    plan = proponer(cliente, wid, monkeypatch, Modelo('carga_nueva_sola', proyecto='P1', alimentadores='F1', sed='S9'), texto)['plan']
    assert not plan['listo'] and any(falta in f for f in plan['faltan'])


def test_tareas_proyecto_entero_con_su_lista(api, monkeypatch, tmp_path):
    """070:RF-31 / 070:RF-38 — el plan enseña las etapas, espera confirmación y al confirmar va por el agente."""
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.dataset = object()
    (tmp_path / 'libros').mkdir()
    ws.demanda['medidores'] = {'path': str(tmp_path / 'libros' / 'm.xlsx')}
    llamadas = []
    monkeypatch.setattr(services, 'agente_proyecto', lambda ws, ctx, datos, base, http=None, reiniciar=False: (
        llamadas.append(datos) or {'completo': True, 'etapas': {}}))
    plan = proponer(cliente, wid, monkeypatch, Modelo('proyecto_entero', sistema='S1', periodo='2026-07'))['plan']
    assert plan['listo'] and plan['escribe'] and plan['modo'] == 'etapas', plan['faltan']
    assert any('estudios' in p for p in plan['pasos']) and not llamadas
    fin = confirmar(cliente, wid, plan)
    assert fin['status'] == 'done', fin['error']
    assert llamadas[0]['sistema'] == 'S1' and llamadas[0]['ruta'] == str(tmp_path / 'libros')


def test_tareas_cancelar_nombra_y_llega_con_el_carril_ocupado(api, monkeypatch):
    """070:RF-32 / 070:RF-33 — con un trabajo del asistente corriendo, la orden entra y lo cancela."""
    import threading

    cliente, app = api
    wid, ws = espacio(cliente, app)
    empezo, seguir = threading.Event(), threading.Event()

    def largo(ctx):
        empezo.set()
        while not ctx.cancel.is_set() and not seguir.is_set():
            time.sleep(.01)
        ctx.check_cancel()
        return {}

    corriendo = app.state.jobs.submit(wid, 'recalibrar', 'Recalibrar · P1', largo, lane='asistente')
    assert empezo.wait(5)
    try:
        r = proponer(cliente, wid, monkeypatch, Modelo('estado'), 'cancela lo que está corriendo')
        plan = r['plan']
        assert plan['tarea'] == 'cancelar_trabajo' and plan['listo'], plan['faltan']
        assert any('Recalibrar' in p for p in plan['pasos'])
        fin = confirmar(cliente, wid, plan)
        assert fin['status'] == 'done', fin['error']
        assert esperar(cliente, corriendo.id)['status'] == 'cancelled'
    finally:
        seguir.set()


def test_tareas_cancelar_sin_nada_en_curso(api, monkeypatch):
    """070:RF-32 — sin nada que cancelar se dice."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    plan = proponer(cliente, wid, monkeypatch, Modelo('estado'), 'cancela lo que está corriendo')['plan']
    assert plan['tarea'] == 'cancelar_trabajo' and not plan['listo']


def test_tareas_leer_solicitud_de_una_carpeta(api, monkeypatch, tmp_path):
    """070:RF-34 — los PDF de la carpeta llegan a la ruta real, en su trabajo."""
    carpeta = tmp_path / 'sol'
    carpeta.mkdir()
    (carpeta / 'carta.pdf').write_bytes(b'%PDF-1.4 x')
    (carpeta / 'nota.txt').write_text('no', encoding='utf-8')
    vistos = []
    monkeypatch.setattr(services, 'informe_documentos', lambda ws, ctx, tipo, rutas: (
        vistos.append((tipo, [p.name for p in rutas])) or {'tipo': tipo, 'documentos': [], 'propuesta': {}}))
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    plan = proponer(cliente, wid, monkeypatch, Modelo('leer_solicitud', ruta=str(carpeta)), 'lee los pdf')['plan']
    assert plan['listo'] and plan['escribe'], plan['faltan']
    fin = confirmar(cliente, wid, plan)
    assert fin['status'] == 'done', fin['error']
    assert vistos == [('factibilidad', ['carta.pdf'])]


def test_tareas_leer_solicitud_sin_pdf(api, monkeypatch, tmp_path):
    """070:RF-34 — una carpeta sin PDF se dice en el plan."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    plan = proponer(cliente, wid, monkeypatch, Modelo('leer_solicitud', ruta=str(tmp_path)), 'lee los pdf')['plan']
    assert not plan['listo'] and any('PDF' in f for f in plan['faltan'])


def test_tareas_descarga_da_su_enlace(api, monkeypatch):
    """070:RF-35 — el ZIP en su trabajo y el enlace para bajarlo."""
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    (ws.out_dir / 'F1.dgs').write_text('x', encoding='utf-8')
    r = proponer(cliente, wid, monkeypatch, Modelo('descargar_resultados'), 'pásame los resultados en zip')
    fin = esperar(cliente, r['trabajo']['id'])
    assert fin['status'] == 'done', fin['error']
    assert f'/api/workspaces/{wid}/outputs.zip?job=' in fin['result']['enlace']


@pytest.mark.parametrize('texto, falta', [
    ('pronostica la cabecera con D:/m zona UTC', 'cadencia'), ('pronostica la cabecera con D:/m cada 15 min', 'zona'),
    ('pronostica con D:/m zona UTC cada 15 min', 'clase')])
def test_tareas_pronostico_sin_suponer(api, monkeypatch, tmp_path, texto, falta):
    """070:RF-36 — clase, zona y cadencia no se suponen (046)."""
    libro = tmp_path / 'm.xlsx'
    libro.write_bytes(b'x')
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    plan = proponer(cliente, wid, monkeypatch, Modelo('pronostico', ruta=str(libro)), texto.replace('D:/m', str(libro)))['plan']
    assert not plan['listo'] and any(falta in f for f in plan['faltan'])


def test_tareas_pronostico_con_todo_llega_a_su_ruta_y_dice_quien_gano(api, monkeypatch, tmp_path):
    """070:RF-36 / 070:RF-37 — el resultado dice ganador, motivo, referencia, y que no es una medición."""
    libro = tmp_path / 'm.xlsx'
    libro.write_bytes(b'x')
    pedidos = []
    monkeypatch.setattr(services, 'gemelo_pronostico', lambda ws, ctx, pedido: pedidos.append(pedido) or {
        'status': 'RECHAZADO', 'marca': 'pronostico', 'promovido': False,
        'ganadores': {'F1': {'ganador': 'estacional_semanal', 'es_referencia': True, 'motivo': 'ningún neuronal la supera'}}})
    monkeypatch.setattr(services, 'medidores_por_alimentador', lambda _ws, a: {x: [f'M-{x}'] for x in a})
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    plan = proponer(cliente, wid, monkeypatch, Modelo('pronostico', ruta=str(libro), alimentadores='F1'),
                    f'pronostica la cabecera de F1 con {libro} zona America/Lima cada 15 min horizontes 1, 4')['plan']
    assert plan['listo'] and plan['escribe'], plan['faltan']
    fin = confirmar(cliente, wid, plan)
    assert fin['status'] == 'done', fin['error']
    p = pedidos[0]
    assert (p['clase'], p['libros'], p['zona_horaria'], p['cadencia_min'], p['pares'], p['horizontes']) == (
        'cabecera', [str(libro)], 'America/Lima', 15, {'F1': 'M-F1'}, [1, 4])
    texto = fin['result']['texto']
    assert 'estacional_semanal' in texto and 'ningún neuronal la supera' in texto and 'referencia' in texto
    assert 'nunca una medición' in texto


def test_tareas_recalibrar_con_su_carril_ocupado_por_el_propio_trabajo(api, monkeypatch, tmp_path):
    """070:RF-26 — por la ruta daba 409: el trabajo del asistente ocupa el carril en el que ella se encola."""
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.pf_projects['P1'] = 'P1'
    ws.demanda['medidores'] = {'path': str(tmp_path / 'm.xlsx')}
    llamadas = []
    monkeypatch.setattr(services, 'recalibrar_sistema', lambda ws, ctx, p, per, demanda_dir=None, **k: (
        llamadas.append((p, per, demanda_dir)) or {'project': p, 'codigo': 0}))
    plan = proponer(cliente, wid, monkeypatch, Modelo('recalibrar', proyecto='P1', periodo='2026-07'), 'recalibra')['plan']
    assert plan['listo'], plan['faltan']
    fin = confirmar(cliente, wid, plan)
    assert fin['status'] == 'done', fin['error']
    assert llamadas == [('P1', '2026-07', None)]


def test_tareas_pronostico_con_clientes_nombrados(entorno, monkeypatch, tmp_path):
    """070:RF-36 — los clientes son opcionales; si se nombran, van al pedido."""
    from convertersmartgrid.web.workspace import WorkspaceStore

    libro = tmp_path / 'm.xlsx'
    libro.write_bytes(b'x')
    plan, extras = _plan('pronostico', {'ruta': str(libro)}, f'pronostica clientes con {libro} zona UTC cada 15 min clientes: C1, C2'), {}
    operacion.requisitos(services, WorkspaceStore(entorno / 'w').create(), plan, extras)
    assert not plan.faltan and extras['pronostico']['clase'] == 'cliente' and extras['pronostico']['clientes'] == ['C1', 'C2']


def test_tareas_nuevas_que_escriben_esperan_confirmacion(api, monkeypatch):
    """070:RF-38 — el plan que escribe no se ejecuta solo y al reiniciar no se reanuda (067:RF-14)."""
    from convertersmartgrid.asistente.tareas import TAREAS

    for nombre in ('convertir_set', 'set_completo', 'alimentadores_completo', 'calibrar', 'simular_calibracion',
                   'recalibrar', 'carga_nueva_sola', 'proyecto_entero', 'cancelar_trabajo', 'leer_solicitud', 'pronostico'):
        assert TAREAS[nombre].escribe, nombre
    con_calibracion(monkeypatch)
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    r = proponer(cliente, wid, monkeypatch, Modelo('recalibrar', proyecto='P1', periodo='2026-07'), 'recalibra')
    assert 'trabajo' not in r


@pytest.mark.parametrize('texto, tarea', [
    ('conviérteme solo la set SETA', 'convertir_set'),
    ('dgs de la set SETA', 'convertir_set'),
    ('calibra la set SETA con 2026-07', 'set_completo'),
    ('calibra F1 de punta a punta con 2026-07', 'alimentadores_completo'),
    ('búscame la máxima coincidente de F1', 'buscar_maxima'),
    ('¿cuál es la máxima de la barra de SETA?', 'buscar_maxima'),
    ('crúzame los clientes de F1', 'cruzar_clientes'),
    ('aplica la calibración de P1', 'calibrar'),
    ('simula la calibración de P1', 'simular_calibracion'),
    ('recalibra P1 con 2026-07', 'recalibrar'),
    ('escanea F1 de P1', 'escanear'),
    ('¿converge P1?', 'verificar_convergencia'),
    ('conecta S9 de 800 kW en F1', 'carga_nueva_sola'),
    ('hazme todo el proyecto de S1 con 2026-07', 'proyecto_entero'),
    ('cancela lo que está corriendo', 'cancelar_trabajo'),
    ('lee los pdf del solicitante', 'leer_solicitud'),
    ('pásame los resultados en zip', 'descargar_resultados'),
    ('pronostica la cabecera de F1', 'pronostico')])
def test_tareas_frase_literal_con_modelo_que_no_las_conoce(texto, tarea):
    """070:RF-39 — hasta que un candidato pase las puertas, la frase las reconoce."""
    from convertersmartgrid.asistente.interprete import interpretar

    assert interpretar(texto, transformer=Modelo('estado')).tarea == tarea


@pytest.mark.parametrize('texto', [
    '¿qué hace el escaneo?', 'por qué no converge el flujo', 'calibra Valle con 2026-07', 'recalibra el sistema Valle con 2026-07',
    'verifica si converge el caso base de P1', 'set nueva para las cargas que no caben en P1', 'carga nuevas de D:/a.xlsx en P1'])
def test_tareas_frase_literal_no_captura_lo_que_ya_tenia_dueno(texto):
    """070:RF-39 — una pregunta o una orden de otra tarea sigue siendo del modelo."""
    from convertersmartgrid.asistente.interprete import interpretar

    assert interpretar(texto, transformer=Modelo('estado')).tarea == 'estado'


@pytest.mark.parametrize('tarea, datos, esperado', [
    ('alimentadores_completo', {'alimentadores': ['F1', 'F2'], 'periodo': '2026-07'}, ['--red', 'F1', 'F2']),
    ('set_completo', {'set': 'SETA', 'periodo': '2026-07'}, ['--zonal', 'S1', '--set', 'SETA']),
    ('sistema_completo', {'sistema': 'S1', 'periodo': '2026-07'}, ['--zonal', 'S1'])])
def test_tareas_de_punta_a_punta_por_sistema_web(entorno, monkeypatch, tarea, datos, esperado):
    """070:RF-20 / 070:RF-21 — la herramienta de siempre, con el alcance de la orden y los libros."""
    from types import SimpleNamespace

    class E:
        sets = {'SETA': SimpleNamespace(zonal='S1')}

    monkeypatch.setattr(services, 'estructura_del_espacio', lambda _ws: E)
    comandos = []
    ctx = SimpleNamespace(run_process=lambda cmd, **kw: comandos.append(cmd) or 0, job=SimpleNamespace(id='j'))
    plan = _plan(tarea, {**datos, 'ruta': 'D:/libros'})
    r = services._asistente_proceso(SimpleNamespace(id='w'), ctx, plan)
    assert r['codigo'] == 0
    cmd = comandos[0]
    assert cmd[cmd.index('--espacio') + 2:cmd.index('--espacio') + 2 + len(esperado)] == esperado
    assert cmd[cmd.index('--demanda-dir') + 1] == 'D:/libros'


def test_tareas_sistema_web_de_una_set(monkeypatch):
    """070:RF-21 / 070:RF-60 — convierte la SET sola, por barra y sin el instante común de 60 kV."""
    import sys

    sys.path.insert(0, str(RAIZ / 'tests'))
    from apoyo import cargar_herramienta

    h = cargar_herramienta('sistema_web.py', 'sistema_web_set')
    assert h.grupo_de_set('Valle', ' seta ') == 'SISTEMA_VALLE_SETA'
    enviados = {}

    class Web:
        def __init__(self):
            self.proyectos = {}

        def get(self, ruta, **kw):
            if ruta == '':
                return {'loaded': True, 'jobs': [], 'pf_projects': self.proyectos}
            if ruta == '/demanda/sistema':
                return {'sistema': {'grupo': 'SISTEMA_VALLE_SETA', 'alimentadores': ['F1'], 'medidores': {'F1': ['M1']}}}
            return {'centrales': []}

        def post(self, ruta, **kw):
            enviados[ruta] = kw.get('json')
            if ruta == '/powerfactory/flow':
                self.proyectos['SISTEMA_VALLE_SETA'] = 'P_SET'
            if ruta == '/demanda/ajuste/plan':
                return {'token': 't'}
            return {'id': ruta, 'title': ruta}

        def esperar(self, trabajo):
            r = {'id': trabajo['id'], 'status': 'done', 'result': {}}
            if trabajo['id'] == '/convert/sistema':
                r['result'] = {'status': 'ok', 'group': 'SISTEMA_VALLE_SETA'}
            if trabajo['id'] == '/demanda/cabecera/buscar':
                r['result'] = {'resultados': [{'medidor': 'M1', 'alimentador': 'F1', 'kw': 1.0}], 'barras': []}
            if trabajo['id'].endswith('/aplicar'):
                r['result'] = {'informes': [{'feeder': 'F1', 'cuadrado': True, 'status': 'ok', 'flujos': 1,
                                             'validacion_posterior_nativa': {'status': 'VALIDO'}}]}
            return r

    codigo = h.correr(Web(), 'Valle', demanda_dir=Path('libros'), periodo='2026-07', reconvertir=False, transformadores=False,
                      tension_pu=None, bancos=True, libros={'medidores': Path('m'), 'cabecera': Path('c')}, set_electrica='SETA')
    assert codigo == 0
    assert enviados['/convert/sistema'] == {'zonales': [], 'sets': ['SETA']}
    assert enviados['/demanda/cabecera/buscar']['por_barra'] is True
    assert enviados['/demanda/cabecera/buscar']['sistema_60kv'] is False

# ------------------------------------------------------------------ T3, consulta de datos
def consultar(cliente, wid, monkeypatch, texto, **datos):
    r = proponer(cliente, wid, monkeypatch, Modelo('consultar_datos', **datos), texto)
    assert r['plan']['tarea'] == 'consultar_datos' and r['plan']['listo'], r['plan']
    return r['respuesta']


def test_consulta_no_escribe_ni_abre_digsilent(api, monkeypatch):
    """070:RF-40 — se responde en la misma orden; ningún trabajo del carril de DIgSILENT."""
    from convertersmartgrid.asistente.tareas import TAREAS

    assert not TAREAS['consultar_datos'].escribe and TAREAS['consultar_datos'].modo == 'consulta'
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    r = consultar(cliente, wid, monkeypatch, '¿qué proyectos tengo?')
    assert not r['encontrado']
    assert not [j for j in app.state.jobs.list(wid) if j.lane == 'powerfactory']


@pytest.mark.parametrize('texto, dato', [
    ('¿qué alimentadores hay?', 'alimentadores'), ('¿qué SED tiene F1?', 'sed'), ('dame los medidores de F1', 'medidores'),
    ('¿qué clientes son fijos en F1?', 'clientes'), ('dame las máximas ya buscadas', 'maximas'),
    ('¿qué años de medición tengo?', 'anios'), ('muestra el catálogo', 'catalogo'), ('¿qué variaciones tiene P1?', 'variaciones'),
    ('lista de proyectos', 'proyectos'), ('¿cuál fue la última calibración de P1?', 'calibracion')])
def test_consulta_entiende_que_dato_se_pide_y_si_no_esta_lo_dice(api, monkeypatch, texto, dato):
    """070:RF-41 / 070:RF-43 — en un espacio vacío, «no lo encuentro» y qué hacer, nunca un valor."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    r = consultar(cliente, wid, monkeypatch, texto, alimentadores='F1', proyecto='P1')
    assert r['dato'] == dato
    assert not r['encontrado'] and r['filas'] == [] and r['fuente'] is None
    assert r['texto'].startswith('No lo encuentro') and r['que_hacer']


def test_consulta_con_datos_da_su_fuente(api, monkeypatch):
    """070:RF-42 — cada respuesta dice de dónde sale."""
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.demanda['medidores'] = {'path': 'x.xlsx', 'name': 'medidores.xlsx'}
    ws.demanda['cabecera'] = {'path': 'c', 'name': 'cabecera', 'anios': [2025, 2026]}
    ws.escaneo['P1'] = {'resumen': {'F1': {'generadores': 1, 'bancos': 2}}}
    monkeypatch.setattr(services, 'medidores_por_alimentador', lambda _ws, a: {x: ['M1'] for x in a})
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *_a, **_k: {
        'report': 'ajuste_cabecera_aplicacion_t.json', 'informes': [{'feeder': 'F1', 'status': 'ok', 'cuadrado': True}]})
    casos = {'dame los medidores de F1': 'medidores.xlsx', '¿qué años de medición tengo?': 'cabecera',
             '¿qué variaciones tiene P1?': 'escaneo de P1', '¿cuál fue la última calibración de P1?': 'ajuste_cabecera_aplicacion_t.json'}
    for texto, fuente in casos.items():
        r = consultar(cliente, wid, monkeypatch, texto, alimentadores='F1', proyecto='P1')
        assert r['encontrado'] and fuente in r['fuente'] and fuente in r['texto'], texto


def test_consulta_maximas_tras_reiniciar_pide_volver_a_buscar(api, monkeypatch):
    """070:RF-44 — lo que vivía en memoria no se da por inexistente."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    r = consultar(cliente, wid, monkeypatch, 'dame las máximas ya buscadas')
    assert 'Vuelva a buscarla' in r['que_hacer']


def test_consulta_maxima_viva_con_sus_cifras(api, monkeypatch):
    """070:RF-41 / 070:RF-42 — con la búsqueda viva, las cifras que dio ese trabajo y su nombre."""
    monkeypatch.setattr(services, 'demanda_cabecera', lambda *_a, **_k: {'resultados': [
        {'alimentador': 'F1', 'medidor': 'M1', 'fecha': '2026-07-21 18:45', 'kw': 123.4}]})
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    t = cliente.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={'medidores': [{'alimentador': 'F1', 'medidor': 'M1'}]})
    assert esperar(cliente, t.json()['id'])['status'] == 'done'
    r = consultar(cliente, wid, monkeypatch, 'dame las máximas ya buscadas')
    assert r['filas'][0]['kw'] == 123.4 and 'Máxima de cabecera' in r['fuente']


def test_consulta_sed_por_el_modelo_sin_recorrer_tablas(tmp_path):
    """070:RF-45 — la ruta usa el modelo del alimentador; con las tablas envenenadas funciona igual (P2)."""
    import sys

    sys.path.insert(0, str(RAIZ / 'tests'))
    from synthetic_export import ExportSpec, load_export
    from test_flexibility_and_scale import _NoFullScan

    from convertersmartgrid.web.workspace import WorkspaceStore

    ds = load_export(ExportSpec(feeders=3, sections_per_feeder=6, loads_per_feeder=4, seed=70), tmp_path / 'src')
    ds.customer_loads_by_feeder, ds.switching_by_feeder, ds.intermediate_by_section
    for nombre in ('customer_loads', 'switch_settings', 'sectionalizer_settings', 'intermediate_nodes'):
        object.__setattr__(ds, nombre, _NoFullScan(nombre, getattr(ds, nombre)))
    ws = WorkspaceStore(tmp_path / 'w').create()
    ws.dataset = ds
    from convertersmartgrid.naming import feeder_short_name

    for network_id in ds.feeder_ids():
        r = services.sed_de_alimentador(ws, feeder_short_name(network_id))
        assert r['seds'] and all(s['codigo'] for s in r['seds'])


def test_consulta_sed_ruta_web(api, monkeypatch):
    """070:RF-45 — la ruta dice el motivo con 400, sin fuente cargada."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    assert cliente.get(f'/api/workspaces/{wid}/feeders/F1/sed').status_code == 400
    monkeypatch.setattr(services, 'sed_de_alimentador', lambda ws, a: {'alimentador': a, 'seds': [{'codigo': 'S1', 'kva': 50.0}]})
    assert cliente.get(f'/api/workspaces/{wid}/feeders/F1/sed').json()['seds'][0]['codigo'] == 'S1'


def test_consulta_lo_devuelto_no_sale_a_internet(api, monkeypatch):
    """070:RF-46 — un código que devolvió la consulta queda vetado en la búsqueda (P9), aunque no tenga forma de código."""
    monkeypatch.setattr(services, 'sed_de_alimentador', lambda ws, a: {'alimentador': a, 'seds': [{'codigo': 'Quebrada Honda', 'kva': 50.0}]})
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.dataset = object()
    r = consultar(cliente, wid, monkeypatch, '¿qué SED tiene F1?', alimentadores='F1')
    assert r['encontrado']
    salida = services.asistente_buscar(ws, 'caida de tension en quebrada honda')
    assert salida['bloqueada'] and 'No se buscó' in salida['texto']


@pytest.mark.parametrize('texto', ['¿qué SED tiene F1?', 'dame los medidores de F1', '¿qué clientes son fijos en F1?',
                                   '¿qué años de medición tengo?', '¿qué variaciones tiene P1?', 'dame las máximas ya buscadas'])
def test_consulta_por_frase_literal_aunque_sea_pregunta(texto):
    """070:RF-39 / 070:RF-41 — tiene forma de pregunta y es una orden de esta tarea."""
    from convertersmartgrid.asistente.interprete import interpretar

    assert interpretar(texto, transformer=Modelo('estado')).tarea == 'consultar_datos'

# ------------------------------------------------------------------ T4, no disponible
@pytest.mark.parametrize('texto, clave', [
    ('¿me sacas el cortocircuito de F1?', 'cortocircuito'), ('corrientes de falla de SETA', 'cortocircuito'),
    ('corre el flujo óptimo de P1', 'flujo_optimo'), ('quiero armónicos de F1', 'armonicos'),
    ('revisa la coordinación de protecciones de F1', 'protecciones'), ('¿coordinan los relés de SETA?', 'protecciones')])
def test_nodisponible_del_catalogo_con_su_motivo(api, monkeypatch, texto, clave):
    """070:RF-47 / 070:RF-48 — el motivo es el de ``estudios_no_ofrecidos``, no uno escrito aquí."""
    from convertersmartgrid.estudios_pf import estudios_no_ofrecidos

    fila = next(e for e in estudios_no_ofrecidos() if clave in e['clave'])
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    r = proponer(cliente, wid, monkeypatch, Modelo('estado'), texto)
    assert r['plan']['tarea'] == 'no_disponible' and not r['plan']['escribe']
    assert r['respuesta']['disponible'] is False and r['respuesta']['motivo'] == fila['motivo']
    assert fila['motivo'] in r['respuesta']['texto']


@pytest.mark.parametrize('texto, spec', [('corre la optimización no lineal de P1', '048'), ('corre el pnl de P1', '048')])
def test_nodisponible_lo_que_solo_esta_especificado(api, monkeypatch, texto, spec):
    """070:RF-47 / 070:RF-49 — se dice que está especificado y no hecho; ninguna cifra ni trabajo."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    r = proponer(cliente, wid, monkeypatch, Modelo('estado'), texto)
    assert r['plan']['tarea'] == 'no_disponible' and spec in r['respuesta']['motivo']
    assert 'trabajo' not in r and not re.search(r'\d+[.,]\d+', r['respuesta']['texto'])
    assert not [j for j in app.state.jobs.list(wid) if j.kind not in ('asistente_interpretar',)]


@pytest.mark.parametrize('texto', ['¿qué es el cortocircuito?', 'cómo funciona la coordinación de protecciones'])
def test_nodisponible_una_pregunta_de_concepto_sigue_siendo_pregunta(texto):
    """070:RF-47 — explicar el concepto no es pedir el estudio."""
    from convertersmartgrid.asistente.interprete import interpretar

    assert interpretar(texto, transformer=Modelo('estado')).tarea == 'estado'

# ------------------------------------------------------------------ T5, evaluar una carga nueva
class WebDeCarga:
    """La API de la web, sustituida: cada POST es un trabajo que termina como pida la prueba."""

    def __init__(self, *, calibrado=True, factible=True, verificar_rc=0, cortar_en=None):
        self.calibrado, self.factible, self.verificar_rc, self.cortar_en = calibrado, factible, verificar_rc, cortar_en
        self.llamadas, self.resultados, self.informes = [], {}, 0

    def request(self, metodo, url, **kw):
        ruta = url.split('/api/workspaces/w', 1)[-1] if '/api/workspaces/w' in url else url.split('/api', 1)[-1]
        self.llamadas.append((metodo, ruta, kw.get('json') or kw.get('data')))

        class R:
            def __init__(s, codigo, datos):
                s.status_code, s._d, s.content, s.text = codigo, datos, b'x', str(datos)

            def json(s):
                return s._d

        if ruta.startswith('/jobs/'):
            return R(200, {'id': ruta[6:], 'status': 'done', 'result': self.resultados.get(ruta[6:], {})})
        if self.cortar_en and ruta.startswith(self.cortar_en):
            self.cortar_en = None
            return R(409, {'detail': 'DIgSILENT ocupado'})
        if ruta.startswith('/demanda/ajuste/ultimo'):
            return R(200, {'ajuste': {'id': 'disco:t'} if self.calibrado else None})
        if ruta == '/lote/plan':
            return R(200, {'token': 'tk'})
        marca = ruta.strip('/').replace('/', '_') + f'-{len(self.llamadas)}'
        if ruta == '/powerfactory/verificar':
            self.resultados[marca] = {'returncode': self.verificar_rc, 'report': 'v.json'}
        if ruta == '/informes/factibilidad':
            self.informes += 1
            self.resultados[marca] = {'factible': self.factible or self.informes > 1, 'informe': f'informe{self.informes}.docx',
                                      'libro_xlsx': None, 'sin_libro': 'el perfil no lo declara'}
        return R(202, {'id': marca, 'status': 'queued'})


DATOS_CARGA = {'proyecto': 'P1', 'alimentadores': ['F1'], 'sed': 'S9', 'nueva': {'Kw': 800.0, 'FP': .98, 'barra': 'B7', 'SED': 'S9', 'alimentador': 'F1', 'nombre': 'S9'},
               'formulario': {'solicitud': {'cliente': 'c'}}, 'periodo': '2026-07', 'ruta': 'D:/libros'}


def correr_carga(web, tmp_path):
    from convertersmartgrid.asistente.ejecutor import ClienteWeb
    from convertersmartgrid.asistente.orquestador import ETAPAS_CARGA, PuntoDeControl, ejecutar_proyecto

    def proceso(tarea, _d):
        assert tarea == 'recalibrar'
        web.llamadas.append(('POST', 'proceso:recalibrar', None))
        web.calibrado = True
        return {'codigo': 0}

    control = PuntoDeControl.abrir(tmp_path / 'carga.json')
    r = ejecutar_proyecto(DATOS_CARGA, cliente=ClienteWeb(web, 'http://x', 'w', intervalo_s=0), control=control,
                          proceso=proceso, etapas=ETAPAS_CARGA)
    return r, control


def test_cadena_sin_problemas_no_hace_obras_y_lo_dice(tmp_path):
    """070:RF-50 / 070:RF-53 / 070:RF-54 — con calibración y factible, sin calibrar ni obras, con el motivo."""
    web = WebDeCarga()
    r, _c = correr_carga(web, tmp_path)
    rutas = [x[1] for x in web.llamadas if x[0] == 'POST']
    assert rutas[0] == '/powerfactory/verificar' and 'proceso:recalibrar' not in rutas and '/pf/obras/con-proyecto' not in rutas
    assert rutas.count('/informes/factibilidad') == 1
    et = r['etapas']
    assert et['calibracion']['estado'] == 'omitida' and 'calibración' in et['calibracion']['resultado']['motivo']
    assert et['obras']['estado'] == 'omitida' and 'sin obras' in et['obras']['resultado']['motivo']
    assert et['informe']['estado'] == 'omitida'


def test_cadena_con_problemas_hace_obras_de_esa_carga_y_rehace_el_informe(tmp_path):
    """070:RF-50 — solo esa carga (063:RF-23), y el informe se rehace con las obras."""
    web = WebDeCarga(factible=False)
    r, _c = correr_carga(web, tmp_path)
    cuerpos = {x[1]: x[2] for x in web.llamadas}
    assert cuerpos['/pf/obras/con-proyecto']['cargas'] == ['S9']
    assert [x[1] for x in web.llamadas].count('/informes/factibilidad') == 2
    assert cuerpos['/informes/factibilidad']['preparar_casos'] is True
    assert r['etapas']['informe']['estado'] == 'hecha'


def test_cadena_sin_calibracion_recalibra_antes_de_la_carga(tmp_path):
    """070:RF-50 — la calibración hace falta y va antes de conectar."""
    web = WebDeCarga(calibrado=False)
    correr_carga(web, tmp_path)
    rutas = [x[1] for x in web.llamadas if x[0] == 'POST']
    assert rutas.index('proceso:recalibrar') < rutas.index('/lote/plan')


def test_cadena_no_sigue_si_no_converge(tmp_path):
    """070:RF-50 — no se conecta nada sobre una red que no converge; se para y se dice (no aceptar que no converge)."""
    web = WebDeCarga(verificar_rc=2)
    with pytest.raises(RuntimeError, match='no converge'):
        correr_carga(web, tmp_path)
    assert '/lote/plan' not in [x[1] for x in web.llamadas]


def test_cadena_cortada_retoma_sin_repetir(tmp_path):
    """070:RF-56 — lo hecho no se repite; retomar exige volver a llamarla, no ocurre solo."""
    from convertersmartgrid.asistente.ejecutor import PasoFallido

    web = WebDeCarga(cortar_en='/informes/factibilidad')
    with pytest.raises(PasoFallido):
        correr_carga(web, tmp_path)
    web2 = WebDeCarga()
    correr_carga(web2, tmp_path)
    assert '/lote/plan' not in [x[1] for x in web2.llamadas] and '/informes/factibilidad' in [x[1] for x in web2.llamadas]


def test_cadena_el_plan_ensena_las_etapas_y_confirma_una_vez(api, monkeypatch):
    """070:RF-51 — la lista va en el plan, y un solo clic va por el agente con esas etapas."""
    con_calibracion(monkeypatch)
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.informes['formularios']['P1'] = {'factibilidad': {'solicitud': {'cliente': 'c'}}}
    llamadas = []
    monkeypatch.setattr(services, 'agente_proyecto', lambda ws, ctx, datos, base, http=None, reiniciar=False, **kw: (
        llamadas.append((datos, kw)) or {'completo': True, 'etapas': {'evaluacion': {'estado': 'hecha', 'resultado': {
            'factible': True, 'informe': 'i.docx'}}}, 'datos': datos}))
    plan = proponer(cliente, wid, monkeypatch, Modelo('estado', proyecto='P1', alimentadores='F1', sed='S9'),
                    'evalúa la carga nueva S9 de 800 kW en F1 de P1 barra B7')['plan']
    assert plan['tarea'] == 'evaluar_carga_nueva' and plan['modo'] == 'etapas', plan
    assert plan['listo'] and plan['escribe'], plan['faltan']
    texto = ' '.join(plan['pasos'])
    assert 'calibracion' in texto and 'ya tiene' in texto and 'obras' in texto and 'solo si' in texto
    assert not llamadas
    fin = confirmar(cliente, wid, plan)
    assert fin['status'] == 'done', fin['error']
    assert len(llamadas) == 1 and llamadas[0][0]['nueva']['Kw'] == 800.0
    assert 'i.docx' in fin['result']['entregables'] and 'factible' in fin['result']['texto']


def test_cadena_que_cambio_no_se_ejecuta(api, monkeypatch):
    """070:RF-52 — si la calibración apareció o desapareció, la lista ya no es la que se confirmó."""
    con_calibracion(monkeypatch)
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.informes['formularios']['P1'] = {'factibilidad': {'solicitud': {'cliente': 'c'}}}
    monkeypatch.setattr(services, 'agente_proyecto', lambda *_a, **_k: pytest.fail('no debía ejecutarse'))
    plan = proponer(cliente, wid, monkeypatch, Modelo('estado', proyecto='P1', alimentadores='F1', sed='S9', periodo='2026-07'),
                    'evalúa la carga nueva S9 de 800 kW en F1 de P1 barra B7 con 2026-07')['plan']
    assert plan['listo'], plan['faltan']
    monkeypatch.setattr(services, 'ajuste_aplicado_en_disco', lambda *_a, **_k: None)
    fin = confirmar(cliente, wid, plan)
    assert fin['status'] == 'failed' and 'cambió' in fin['error']


@pytest.mark.parametrize('texto, falta', [
    ('evalúa la carga nueva S9 en F1 de P1 barra B7', 'potencia'),
    ('evalúa la carga nueva S9 de 800 kW en F1 de P1', 'ubicación')])
def test_cadena_dice_lo_que_falta_de_la_carga(api, monkeypatch, texto, falta):
    """070:RF-51 — lo mismo que la carga sola: no se deduce."""
    con_calibracion(monkeypatch)
    cliente, app = api
    wid, ws = espacio(cliente, app)
    ws.informes['formularios']['P1'] = {'factibilidad': {'solicitud': {'cliente': 'c'}}}
    plan = proponer(cliente, wid, monkeypatch, Modelo('estado', proyecto='P1', alimentadores='F1', sed='S9'), texto)['plan']
    assert not plan['listo'] and any(falta in f for f in plan['faltan'])


def test_cadena_la_carga_se_llama_por_su_nombre():
    """070:RF-29 — sin SED todavía, el nombre que da la orden; una palabra de unión no es un nombre."""
    from convertersmartgrid.asistente.interprete import Interpretacion
    from convertersmartgrid.asistente.plan import resolver

    def nombre(texto):
        return resolver(Interpretacion(texto, 'carga_nueva_sola', 1., 'x', {}), {}).datos.get('sed')

    assert nombre('conecta Quebrada de 800 kW') == 'QUEBRADA' and nombre('evalúa la carga nueva S9 de 800 kW') == 'S9'
    assert nombre('conecta en F1 de 800 kW') is None


def test_cadena_sin_formulario_ni_calibracion_lo_dice(api, monkeypatch):
    """070:RF-51 / 070:RF-53 — sin formulario del informe; sin calibración pide el periodo con que hacerla."""
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    plan = proponer(cliente, wid, monkeypatch, Modelo('estado', proyecto='P1', alimentadores='F1', sed='S9'),
                    'evalúa la carga nueva S9 de 800 kW en F1 de P1 barra B7')['plan']
    assert any('formulario' in f for f in plan['faltan']) and any('periodo' in f for f in plan['faltan'])


def test_cadena_el_libro_es_solo_del_perfil():
    """070:RF-55 — lo decide el informe, que ya lo escribe solo si el perfil lo declara (066:RF-1): aquí no se fuerza."""
    fuente = (RAIZ / 'src/convertersmartgrid/asistente/orquestador.py').read_text(encoding='utf-8')
    assert 'libro_informe' not in fuente and 'libro_xlsx' not in fuente
    fuente = (RAIZ / 'src/convertersmartgrid/web/services.py').read_text(encoding='utf-8')
    assert '_libro_del_informe(ctx, destino, imagenes)' in fuente

# ------------------------------------------------------------------ T6, reglas de dominio
def test_dominio_la_ruta_rechaza_mas_de_tres_coincidentes(api, monkeypatch):
    """070:RF-57 — también en el backend, y propone SET o sistema; por barra no hay tope."""
    monkeypatch.setattr(services, 'demanda_cabecera', lambda *_a, **_k: {'resultados': []})
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    medidores = [{'alimentador': f'F{i}', 'medidor': f'M{i}'} for i in range(1, 5)]
    r = cliente.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={'medidores': medidores, 'coincidente': True})
    assert r.status_code == 400 and 'SET' in r.json()['detail'] and 'sistema' in r.json()['detail']
    r = cliente.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={'medidores': medidores, 'por_barra': True})
    assert r.status_code == 202
    esperar(cliente, r.json()['id'])


def test_dominio_las_centrales_no_cuentan_como_alimentadores(api, monkeypatch):
    """070:RF-57 — los medidores de una central llevan su alimentador, y no son otro alimentador."""
    monkeypatch.setattr(services, 'demanda_cabecera', lambda *_a, **_k: {'resultados': []})
    cliente, app = api
    wid, _ws = espacio(cliente, app)
    medidores = [{'alimentador': f'F{i}', 'medidor': f'M{i}'} for i in range(1, 4)] + [
        {'alimentador': 'Central F1', 'medidor': m} for m in ('G', 'L', 'S')]
    r = cliente.post(f'/api/workspaces/{wid}/demanda/cabecera/buscar', json={'medidores': medidores, 'coincidente': True})
    assert r.status_code == 202
    esperar(cliente, r.json()['id'])


@pytest.mark.parametrize('tarea, datos', [
    ('buscar_maxima', {'alimentadores': ['F1', 'F2', 'F3', 'F4']}),
    ('alimentadores_completo', {'alimentadores': ['F1', 'F2', 'F3', 'F4'], 'periodo': '2026-07', 'ruta': 'D:/l'})])
def test_dominio_tareas_con_mas_de_tres_proponen_set_o_sistema(entorno, monkeypatch, tarea, datos):
    """070:RF-58 — se dice en el plan, con la alternativa: no se pregunta ni se trocea."""
    from convertersmartgrid.web.workspace import WorkspaceStore

    monkeypatch.setattr(services, 'medidores_por_alimentador', lambda _ws, a: {x: [f'M-{x}'] for x in a})
    plan = _plan(tarea, datos)
    operacion.requisitos(services, WorkspaceStore(entorno / 'w').create(), plan, {})
    assert any('SET' in f and 'sistema' in f for f in plan.faltan)


def test_dominio_sistema_web_rechaza_mas_de_tres(capsys):
    """070:RF-57 — la herramienta también: antes del primer paso."""
    import sys

    sys.path.insert(0, str(RAIZ / 'tests'))
    from apoyo import cargar_herramienta

    h = cargar_herramienta('sistema_web.py', 'sistema_web_tope')

    class SinWeb:
        def __getattr__(self, _n):
            pytest.fail('no debía llamar a la web')

    codigo = h.correr(SinWeb(), None, demanda_dir=Path('l'), periodo='2026-07', reconvertir=False, transformadores=False,
                      tension_pu=None, bancos=True, libros={'medidores': Path('m'), 'cabecera': Path('c')},
                      red=['F1', 'F2', 'F3', 'F4'])
    assert codigo == 2 and 'SET' in capsys.readouterr().out


def _estructura_de_prueba():
    from types import SimpleNamespace

    return SimpleNamespace(zonales=['Valle'], sets={'SET 1': SimpleNamespace(zonal='Valle', codigo='SET 1')})


def test_dominio_recalibrar_conserva_el_criterio_de_la_set(entorno, monkeypatch, tmp_path):
    """070:RF-59 — un proyecto de SET se calibraba como alimentadores sueltos: ``SISTEMA_<zonal>_<set>`` no casaba."""
    from types import SimpleNamespace

    from convertersmartgrid.web.workspace import WorkspaceStore

    ws = WorkspaceStore(entorno / 'w').create()
    grupo = 'SISTEMA_VALLE_SET_1'
    ws.pf_projects[grupo] = 'P_SET'
    ws.groups[grupo] = {'tipo': 'sistema', 'feeders': ['F1', 'F2']}
    ws.demanda['medidores'] = {'path': str(tmp_path / 'm.xlsx')}
    monkeypatch.setattr(services, 'estructura_del_espacio', lambda _ws: _estructura_de_prueba())
    datos = services.recalibrar_datos(ws, 'P_SET')
    assert (datos['zonal'], datos['set']) == ('Valle', 'SET 1') and 'alimentadores' not in datos
    comandos = []
    ctx = SimpleNamespace(run_process=lambda cmd, **kw: comandos.append(cmd) or 0, job=SimpleNamespace(id='j'), log=lambda _m: None)
    services.recalibrar_sistema(ws, ctx, 'P_SET', '2026-07')
    cmd = comandos[0]
    assert cmd[cmd.index('--zonal') + 1] == 'Valle' and cmd[cmd.index('--set') + 1] == 'SET 1' and '--red' not in cmd


def test_dominio_recalibrar_un_sistema_sigue_igual(entorno, monkeypatch, tmp_path):
    """070:RF-59 — los proyectos de sistema y de alimentadores no cambian (028:RF-24)."""
    from convertersmartgrid.web.workspace import WorkspaceStore

    ws = WorkspaceStore(entorno / 'w').create()
    ws.pf_projects['SISTEMA_VALLE'] = 'P_SIS'
    ws.groups['SISTEMA_VALLE'] = {'tipo': 'sistema', 'feeders': ['F1']}
    ws.pf_projects['F9'] = 'P_UNO'
    ws.demanda['medidores'] = {'path': str(tmp_path / 'm.xlsx')}
    monkeypatch.setattr(services, 'estructura_del_espacio', lambda _ws: _estructura_de_prueba())
    assert services.recalibrar_datos(ws, 'P_SIS')['zonal'] == 'Valle' and 'set' not in services.recalibrar_datos(ws, 'P_SIS')
    assert services.recalibrar_datos(ws, 'P_UNO')['alimentadores'] == ['F9']


def test_dominio_la_maxima_de_una_set_es_de_barra(api, monkeypatch):
    """070:RF-60 — por barra y sin el instante común de 60 kV (RF-22 lo mide en el plan)."""
    from convertersmartgrid.asistente.ejecutor import pasos

    monkeypatch.setattr(services, 'estructura_resumen', lambda _ws: {'zonales': [
        {'nombre': 'S1', 'alimentadores': ['F1'], 'sets_detalle': [{'codigo': 'SETA', 'alimentadores': ['F1']}]}]})
    monkeypatch.setattr(services, 'medidores_por_alimentador', lambda _ws, a: {x: ['M'] for x in a})
    cliente, app = api
    wid, ws = espacio(cliente, app)
    plan, extras = _plan('buscar_maxima', {'set': 'SETA'}), {}
    operacion.requisitos(services, ws, plan, extras)
    c = pasos('buscar_maxima', plan.datos, extras)[0].cuerpo
    assert c['por_barra'] is True and c['sistema_60kv'] is False


def test_dominio_transmision_no_se_calibra(api, monkeypatch):
    """070:RF-61 — ni por la ruta ni desde el asistente: sirve para la cargabilidad de la SET (017:RF-68)."""
    monkeypatch.setattr(services, 'es_proyecto_de_transmision', lambda p: p == 'P1')
    cliente, app = api
    wid, ws = espacio(cliente, app)
    with pytest.raises(services.UserError, match='transmisión'):
        services.ajuste_plan(ws, 'P1', [{'medidor': 'M1'}], '', .01)
    for tarea, datos in (('calibrar', {'proyecto': 'P1'}), ('recalibrar', {'proyecto': 'P1', 'periodo': '2026-07'})):
        plan = proponer(cliente, wid, monkeypatch, Modelo(tarea, **datos))['plan']
        assert not plan['listo'] and any('transmisión' in f for f in plan['faltan']), tarea


def test_dominio_transmision_sin_perfil_no_estorba(entorno):
    """070:RF-61 — sin perfil no se supone ninguno (P13)."""
    assert services.es_proyecto_de_transmision('P1') is False


def test_dominio_la_conclusion_de_conexion_manda_al_decidir_obras():
    """070:RF-54 — lo que decide es la conclusión de los tres casos (063:RF-8), no el resumen del Word."""
    from convertersmartgrid.asistente.orquestador import _resumen

    r = _resumen({'factible': True, 'informe': 'i.docx', 'conclusion_conexion': {'factible': False, 'clave': 'requiere_refuerzo'}})
    assert r['factible'] is False and r['conclusion'] == 'requiere_refuerzo' and r['informe'] == 'i.docx'

# ------------------------------------------------------------------ T7, la vía antigua
def herramienta_entrenar():
    import importlib.util

    spec = importlib.util.spec_from_file_location('asistente_entrenar_070', RAIZ / 'tools/asistente_entrenar.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_via_sin_opciones_toma_la_gobernada_y_nunca_la_antigua(entorno, monkeypatch):
    """070:RF-62 / 070:RF-63 — la vigilancia la lanza sin ``--integral``: nunca llega a ``entrenar_y_promover``."""
    from convertersmartgrid.asistente import clasificador, destilacion_integral as di, transformer

    monkeypatch.setattr(transformer, 'entrenar_y_promover', lambda *_a, **_k: pytest.fail('vía antigua de órdenes'))
    monkeypatch.setattr(clasificador, 'entrenar_y_promover', lambda *_a, **_k: pytest.fail('vía antigua de informes'))
    vistos = []
    monkeypatch.setattr(di, 'preparar_corpus', lambda vocab, *_a, **_k: vistos.append(vocab) or ([], {}))
    monkeypatch.setattr(di, 'guardar_corpus', lambda *_a, **_k: None)
    monkeypatch.setattr(di, 'entrenar_destilacion', lambda *_a, registro=None, **_k: {
        'status': 'RECHAZADO', 'promovido': False, 'registro': str(registro),
        'candidato': {'status': 'RECHAZADO', 'candidate_id': 'c'}})
    from convertersmartgrid.asistente import modelos_en_uso

    monkeypatch.setattr(modelos_en_uso, 'aplicar_decision', lambda familia, c: {'promovido': False, 'motivo': 'no pasa', 'en_uso': None})
    monkeypatch.setattr(clasificador, 'entrenar_gobernado', lambda *_a, **_k: {'status': 'BLOQUEADO_POR_DATOS'})
    almacen_vocab = {'alimentadores': ['F1']}
    from convertersmartgrid.asistente import almacen

    almacen.guardar_json('vocabulario', almacen_vocab)
    salida = entorno / 'informe.json'
    codigo = herramienta_entrenar().main(['--output-json', str(salida)])
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert codigo == 0 and informe['training_completed'] is True and 'model_registry' in informe['ordenes']['registro']
    assert vistos == [almacen_vocab], 'el vocabulario que guardó la web, como en la vía antigua'


@pytest.mark.parametrize('opciones, tocan_ordenes', [(['--solo', 'ordenes'], True), (['--destilar'], True), (['--solo', 'informes'], False)])
def test_via_pedida_expresamente_va_con_turno_y_registro(entorno, monkeypatch, opciones, tocan_ordenes):
    """070:RF-63 / 070:RF-64 — con turno de GPU, sin promover por su cuenta y con la decisión en el registro."""
    from convertersmartgrid import trabajadores_ml
    from convertersmartgrid.asistente import clasificador, destilacion, ollama, transformer
    from convertersmartgrid.model_registry import RegistroModelo

    turnos, kw_vistos = [], []

    class Turno:
        def __init__(self, nombre):
            turnos.append(nombre)

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(trabajadores_ml, 'turno_gpu', Turno)
    monkeypatch.setattr(transformer, '_dispositivo', lambda: 'cuda')
    import convertersmartgrid.digital_twin.oraculo as oraculo

    monkeypatch.setattr(oraculo, 'dispositivo', lambda: 'cuda')

    def antigua(vocab, **kw):
        kw_vistos.append(kw)
        return {'version': 'v1', 'promovido': False, 'fallos': [], 'acierto_tarea': .99, 'dataset': {'calidades': {'x': 1}}}

    monkeypatch.setattr(transformer, 'entrenar_y_promover', antigua)
    monkeypatch.setattr(clasificador, 'entrenar_gobernado', lambda *_a, **_k: {'status': 'BLOQUEADO_POR_DATOS', 'promovido': False})
    monkeypatch.setattr(destilacion, 'MaestroArchivo', lambda: object())
    salida = entorno / 'informe.json'
    codigo = herramienta_entrenar().main(['--output-json', str(salida), *opciones])
    informe = json.loads(salida.read_text(encoding='utf-8'))
    assert codigo == 0, informe
    assert turnos, 'sin turno de GPU'
    if tocan_ordenes:
        assert kw_vistos[0]['promover_directo'] is False and informe['ordenes']['promovido'] is False
        registro = RegistroModelo(almacen.raiz() / 'model_registry')
        assert registro.activo('transformer') is None
        assert registro.ultimo('transformer')['status'] == 'RECHAZADO'


def test_via_por_defecto_no_promueve_sin_registro(entorno, monkeypatch):
    """070:RF-63 — sin pedirlo expresamente, ``entrenar_y_promover`` no toca el puntero."""
    import inspect

    from convertersmartgrid.asistente import transformer

    assert inspect.signature(transformer.entrenar_y_promover).parameters['promover_directo'].default is False


def test_via_quita_de_entrenar_los_textos_de_la_prueba():
    """070:RF-65 — un texto de la prueba repetido en el entrenamiento no mide nada."""
    from convertersmartgrid.asistente import transformer
    from convertersmartgrid.asistente.sinteticos import Ejemplo

    e = lambda t: Ejemplo(t, 'estado', [])  # noqa: E731
    limpio, quitados = transformer.sin_textos_de_prueba([e('Uno  dos'), e('tres'), e('uno dos')], [e('uno dos')])
    assert [x.texto for x in limpio] == ['tres'] and quitados == 2


def test_via_clasificador_sin_fuga_y_con_calidad(entorno, monkeypatch):
    """070:RF-65 / 070:RF-66 — el clasificador gobernado tampoco entrena con su prueba, y su manifiesto dice la calidad."""
    from convertersmartgrid.asistente import clasificador as cl
    from convertersmartgrid.model_registry import RegistroModelo

    for i in range(5):
        cl.registrar(f'informe real {i}', 'estudio', 'refuerzo de red', 'generado')
    vistos = []

    class Candidato:
        red = None
        subtipos = ['refuerzo de red']
        version = ''

    def entrenar(datos, *_a, **_k):
        vistos.append(datos)
        return Candidato()

    def guardar(modelo, carpeta):
        carpeta.mkdir(parents=True)
        (carpeta / 'pesos.pt').write_bytes(b'p')
        (carpeta / 'modelo.json').write_text('{}', encoding='utf-8')

    monkeypatch.setattr(cl, 'entrenar', entrenar)
    monkeypatch.setattr(cl, 'evaluar', lambda *_a: {'acierto_tipo': 1., 'acierto_subtipo': .97, 'ejemplos': 9})
    monkeypatch.setattr(cl, 'cargar', lambda: None)
    monkeypatch.setattr(cl, 'guardar_candidato', guardar)
    monkeypatch.setattr(cl, 'generar', lambda s, **k: [('repetido', 'estudio', 'refuerzo de red')] if k.get('semilla') == cl.SEMILLA_PRUEBA
                        else [('repetido', 'estudio', 'refuerzo de red'), ('propio', 'estudio', 'refuerzo de red')])
    registro = RegistroModelo(almacen.raiz() / 'model_registry')
    r = cl.entrenar_gobernado(registro, entorno / 'cand', reabrir=lambda _c: {'ok': True})
    assert 'repetido' not in [x[0] for x in vistos[0]] and 'propio' in [x[0] for x in vistos[0]]
    manifiesto = registro.detalle('clasificador', r['candidato']['candidate_id'], verificar_artefactos=False)['dataset_manifest']
    assert manifiesto['calidades'] and manifiesto['textos_de_prueba_quitados'] == 1

# ------------------------------------------------------------------ T8, currículo y prueba
def test_curriculo_cinco_parafrasis_de_entrenar_por_tarea_con_origen():
    """070:RF-67 / 070:RF-68 — al menos cinco distintas por tarea, nuevas y antiguas, marcadas por su origen."""
    from convertersmartgrid.asistente.curriculo_maestro import ESTILO_REAL, MAESTRO_070, PARAFRASIS_070
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.asistente.tareas import TAREAS, TAREAS_HASTA_069

    assert MAESTRO_070['origen'] == 'sintetico_spec_070'
    assert set(PARAFRASIS_070) == set(TAREAS_HASTA_069) and all(len(set(v)) >= 5 for v in PARAFRASIS_070.values())
    assert all(len(set(ESTILO_REAL[t])) >= 5 for t in set(TAREAS) - set(TAREAS_HASTA_069))
    filas, meta = preparar_corpus({}, [], por_familia=2)
    nuevas = [r for r in filas if r.get('origen_curriculo') == 'parafrasis_070']
    assert nuevas and all(r['particion'] == 'entrenamiento' for r in nuevas)
    assert meta['parafrasis_070']['maestro'] == MAESTRO_070 and meta['parafrasis_070']['filas'] == len(nuevas)


def test_curriculo_sin_nombres_de_empresa_ni_numeros_fijos():
    """070:RF-67 — P2 y P13: nada de empresas, zonales ni códigos reales en lo que se añade."""
    from convertersmartgrid.asistente.curriculo_maestro import PARAFRASIS_070
    from convertersmartgrid.asistente.prueba_sellada import FRASES, VOCABULARIO

    texto = normalizar_todo(PARAFRASIS_070, FRASES, VOCABULARIO)
    for prohibida in ('dunas', 'pisco', 'chincha', 'nasca', 'copara', 'electro', 'na205', 'in111', '101 alimentadores'):
        assert prohibida not in texto, prohibida


def normalizar_todo(*dicts):
    from convertersmartgrid.asistente.sinteticos import normalizar

    return normalizar(' '.join(str(d) for d in dicts))


def test_curriculo_prueba_sellada_con_varias_parafrasis_y_su_declaracion():
    """070:RF-69 — varias frases por tarea de todo el catálogo, y el módulo dice cómo se generó."""
    from convertersmartgrid.asistente import prueba_sellada as ps
    from convertersmartgrid.asistente.tareas import TAREAS

    assert set(ps.FRASES) == set(TAREAS) and all(len(set(v)) >= 5 for v in ps.FRASES.values())
    filas = ps.selladas()
    por_grupo = {}
    for r in filas:
        por_grupo.setdefault(r['tarea'], set()).add(r['group_id'])
    assert all(len(g) >= 5 for g in por_grupo.values())
    assert all(p in ps.__doc__ for p in ('sin mirar ningún modelo', 'expandir', 'semilla', 'HUELLA'))
    assert all(r['quality'] != 'gold_human' for r in filas)


def test_curriculo_prueba_sellada_huella_fija_sin_depender_del_espacio():
    """070:RF-70 — la misma con cualquier vocabulario del espacio; si cambia, se rechaza."""
    from convertersmartgrid.asistente import prueba_sellada as ps
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus

    assert ps.HUELLA == HUELLA_PRUEBA_SELLADA and ps.huella_de(ps.filas()) == HUELLA_PRUEBA_SELLADA
    uno, m1 = preparar_corpus({}, [], por_familia=1)
    dos, m2 = preparar_corpus({'alimentadores': ['AB101'], 'proyecto': ['Otro'], 'sistema': ['Valle']}, [], por_familia=1)
    sellada = lambda filas: sorted(r['record_id'] for r in filas if r.get('conjunto') == ps.CONJUNTO)  # noqa: E731
    assert sellada(uno) == sellada(dos) and m1['prueba_sellada']['huella'] == m2['prueba_sellada']['huella'] == HUELLA_PRUEBA_SELLADA
    original = ps.FRASES['estado']
    try:
        ps.FRASES['estado'] = (*original[:-1], 'una frase cambiada')
        with pytest.raises(ValueError, match='huella'):
            ps.selladas()
    finally:
        ps.FRASES['estado'] = original


def test_curriculo_prueba_sellada_separada_por_familias():
    """070:RF-71 — ni un texto ni una familia en entrenamiento, selección o calibración, también con erratas."""
    from convertersmartgrid.asistente import prueba_sellada as ps
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.asistente.maestro_real import clave_texto, firma_familia

    filas, _ = preparar_corpus({'alimentadores': ['AB101', 'CD202'], 'proyecto': ['Proyecto X'], 'sistema': ['Valle']}, [], por_familia=6)
    sellada = [r for r in filas if r.get('conjunto') == ps.CONJUNTO]
    resto = [r for r in filas if r['particion'] != 'prueba']
    textos = {clave_texto(r['texto']) for r in sellada}
    familias = {firma_familia(r['texto'], r['datos']) for r in sellada}
    assert sellada and resto
    assert not [r for r in resto if clave_texto(r['texto']) in textos or firma_familia(r['texto'], r['datos']) in familias]
    assert not ({r['group_id'] for r in sellada} & {r['group_id'] for r in resto})


def test_curriculo_prueba_historica_intacta_y_sin_tareas_nuevas():
    """070:RF-72 — las filas de la anterior son las mismas y de las tareas de entonces."""
    from convertersmartgrid.asistente.destilacion_integral import es_historica, preparar_corpus
    from convertersmartgrid.asistente.tareas import TAREAS_HASTA_069
    from convertersmartgrid.evaluacion_modelos import huella

    filas, meta = preparar_corpus({}, [], por_familia=5)
    historicas = [r for r in filas if es_historica(r)]
    assert {r['tarea'] for r in historicas} == set(TAREAS_HASTA_069)
    assert meta['prueba_historica']['huella'] == huella(sorted(r['record_id'] for r in historicas))
    assert meta['prueba_historica']['filas'] == len(historicas)
    assert not [r for r in filas if es_historica(r) and r.get('conjunto')]


def test_curriculo_decide_la_sellada_y_la_historica_se_mide_sin_decidir(tmp_path, monkeypatch):
    """070:RF-69 / 070:RF-72 — el protocolo real con codificador falso: decisión con la nueva, medida con las dos."""
    import convertersmartgrid.model_registry as mr
    from test_interprete_codificador import CodificadorFalso

    from convertersmartgrid.asistente import codificador_ordenes as co, destilacion_integral as di, prueba_sellada as ps, transformer as tr

    monkeypatch.setattr(tr, 'liberar_gpu', lambda: None)
    import torch

    monkeypatch.setattr(tr, '_dispositivo', lambda: torch.device('cpu'))
    monkeypatch.setattr(co, 'FABRICA', CodificadorFalso)
    co._abiertos.clear()
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setattr(mr, 'reabrir_en_subproceso', lambda *_a, **_k: {'ok': True})
    vistas = {}
    original = di.decidir_promocion

    def espia(sinteticas, humanas, familias, referencia, rechazo=None):
        vistas['sinteticas'] = sinteticas
        return original(sinteticas, humanas, familias, referencia, rechazo)

    monkeypatch.setattr(di, 'decidir_promocion', espia)
    filas, meta = di.preparar_corpus({}, [{'texto': 'carga la fuente', 'tarea': 'cargar_fuente', 'datos': [], 'origen': 'confirmado'}], por_familia=1)
    di.guardar_corpus(tmp_path / 'corpus', filas, meta, [])
    cfg = co.Configuracion(epocas=1, lote_tarea=64, lote_etiquetas=64, oculta_tarea=8, oculta_etiquetas=8)
    r = di.entrenar_destilacion(tmp_path / 'corpus', tmp_path / 'run', cfg=cfg, semillas=(11,), registro=tmp_path / 'reg', log=lambda *_a, **_k: None)
    # 079:RF-45: decide la sellada nueva; la de la 070 se mide con su huella y sin decidir.
    n_sellada = sum(x.get('conjunto') == 'sellada_079' for x in filas)
    assert vistas['sinteticas']['ejemplos'] == n_sellada and r['sinteticas']['ejemplos'] == n_sellada
    assert r['prueba_sellada']['huella'] == HUELLA_PRUEBA_SELLADA and r['prueba_sellada']['decide'] is False
    assert r['prueba_historica']['decide'] is False and r['prueba_historica']['medida']['ejemplos'] > 0
    assert r['prueba_historica']['huella'] == meta['prueba_historica']['huella']


@pytest.mark.parametrize('cambio', [{'acierto_tarea': .9499}, {'f1_datos': .8499}])
def test_curriculo_puertas_de_familia_no_bajan(cambio):
    """070:RF-73 — 0,95 y 0,85 por familia, ni una décima menos."""
    from convertersmartgrid.asistente import destilacion_integral as di
    from convertersmartgrid.asistente.tareas import TAREAS

    perfecto = {'ejemplos': 3, 'acierto_tarea': 1., 'f1_datos': 1.}
    familias = {t: dict(perfecto) for t in TAREAS}
    rechazo = {'ejemplos': 200, 'rechazada': 1., 'se_cuela': 0.}
    assert di.decidir_promocion(perfecto, perfecto, familias, familias, rechazo)['status'] == 'PROMOVIDO'
    familias['estado'] = {**perfecto, **cambio}
    assert di.decidir_promocion(perfecto, perfecto, familias, None, rechazo)['status'] == 'RECHAZADO'


@pytest.mark.parametrize('humanas, rechazo', [
    ({'ejemplos': 3, 'acierto_tarea': .9799, 'f1_datos': 1.}, {'ejemplos': 200, 'rechazada': 1., 'se_cuela': 0.}),
    ({'ejemplos': 3, 'acierto_tarea': 1., 'f1_datos': .9499}, {'ejemplos': 200, 'rechazada': 1., 'se_cuela': 0.}),
    ({'ejemplos': 3, 'acierto_tarea': 1., 'f1_datos': 1.}, {'ejemplos': 200, 'rechazada': .8999, 'se_cuela': 0.}),
    ({'ejemplos': 3, 'acierto_tarea': 1., 'f1_datos': 1.}, {'ejemplos': 200, 'rechazada': 1., 'se_cuela': .0201})])
def test_curriculo_puertas_humanas_y_de_rechazo_no_bajan(humanas, rechazo):
    """070:RF-73 — 0,98 y 0,95 humanas; rechazo de al menos 0,90 y como mucho 0,02."""
    from convertersmartgrid.asistente import destilacion_integral as di
    from convertersmartgrid.asistente.tareas import TAREAS

    perfecto = {'ejemplos': 3, 'acierto_tarea': 1., 'f1_datos': 1.}
    familias = {t: dict(perfecto) for t in TAREAS}
    assert di.decidir_promocion(perfecto, humanas, familias, familias, rechazo)['status'] == 'RECHAZADO'


def test_curriculo_un_pronostico_no_es_reconstruccion():
    """070:RF-74 — «pronostica» estaba en ``gemelo_temporal``, que reconstruye a un paso."""
    from convertersmartgrid.asistente.curriculo_maestro import ESTILO_REAL, FAMILIAS, PARAFRASIS_070
    from convertersmartgrid.asistente.ordenes_fijas import FRASES
    from convertersmartgrid.asistente.prueba_sellada import FRASES as SELLADA
    from convertersmartgrid.asistente.tareas import TAREAS

    conjuntos = (FAMILIAS, ESTILO_REAL, PARAFRASIS_070, FRASES, SELLADA, {t: v.plantillas for t, v in TAREAS.items()})
    for c in conjuntos:
        assert not [f for f in c.get('gemelo_temporal', ()) if 'pronostic' in f]
    assert any('pronostic' in f for f in ESTILO_REAL['pronostico'])


def test_curriculo_fijas_con_su_huella_intacta():
    """070:RF-75 — con 48 tareas siguen siendo las 200 de siempre."""
    from convertersmartgrid.asistente import ordenes_fijas as of

    assert of.huella(of.generar({})) == '41f7ab110ac35c0b'


def test_curriculo_interpreta_lo_mismo_con_tipos_nuevos_en_un_heredado():
    """070:RF-18 — los modelos con menos etiquetas siguen leyéndose: sus índices no se movieron."""
    import numpy as np

    from convertersmartgrid.asistente.datos_por_palabra import ETIQUETAS, marcar_datos

    heredadas = 1 + 2 * 10
    p = np.zeros((10, heredadas), dtype='float32')
    p[:, 0] = 1.
    p[5:, ETIQUETAS.index('B-proyecto')] = 3.
    p[5:, 0] = 0.
    assert 'proyecto' in marcar_datos('hola AB101', p)

def _humana(texto, tarea, datos=()):
    return {'texto': texto, 'tarea': tarea, 'datos': list(datos), 'origen': 'confirmado'}


def test_curriculo_lo_confirmado_nunca_entrena_aunque_fuera_plata():
    """070:RF-76 — sin mayúsculas ni tildes es la misma frase: ni la plata, ni sus erratas, ni la plantilla que la repite."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus
    from convertersmartgrid.asistente.maestro_real import clave_texto

    # Frase de catálogo que se genera sin datos: «que hay cargado» sale de las plantillas de ``estado``.
    humana = 'Qué hay cargado'
    plata = {'texto': 'qué hay cargado', 'tarea': 'estado', 'confianza': .95, 'spans': [], 'maestro': 'claude'}
    filas, meta = preparar_corpus({}, [_humana(humana, 'estado')], por_familia=8, etiquetas_reales=[plata])
    gold = [r for r in filas if r['quality'] == 'gold_human']
    assert [r['particion'] for r in gold] == ['prueba'] and meta['ordenes_humanas_independientes'] == 1
    clave = clave_texto(humana)
    assert not [r for r in filas if r['particion'] != 'prueba' and clave_texto(r['texto']) == clave]
    assert meta['etiquetas_reales']['usadas'] == 0


def test_curriculo_una_humana_igual_a_la_sellada_no_para_el_corpus():
    """070:RF-76 / 070:RF-71 — las dos son prueba: no hay fuga, y la sellada no cambia por una orden del operador."""
    from convertersmartgrid.asistente import prueba_sellada as ps
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus

    filas, meta = preparar_corpus({}, [_humana('Aborta eso', 'cancelar_trabajo')], por_familia=1)
    assert meta['prueba_sellada']['huella'] == ps.HUELLA and meta['ordenes_humanas_independientes'] == 1
    assert sum(r['quality'] == 'gold_human' for r in filas) == 1


def test_curriculo_la_historica_sin_humanas_se_puede_comparar():
    """070:RF-72 — con más órdenes confirmadas la huella con humanas se mueve; la de sus sintéticas lo dice aparte."""
    from convertersmartgrid.asistente.destilacion_integral import preparar_corpus

    _, sin = preparar_corpus({}, [], por_familia=1)
    _, con = preparar_corpus({}, [_humana('una orden confirmada cualquiera', 'estado')], por_familia=1)
    assert sin['prueba_historica']['huella'] != con['prueba_historica']['huella']
    assert sin['prueba_historica']['huella_sinteticas'] == con['prueba_historica']['huella_sinteticas']
