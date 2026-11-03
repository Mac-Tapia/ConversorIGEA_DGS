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
    ('recalibrar', {'proyecto': 'P1', 'periodo': '2026-07'}, {}, 'POST', '/demanda/recalibrar', {'project': 'P1'}),
    ('escanear', {'proyecto': 'P1', 'alimentadores': ['F1']}, {}, 'POST', '/powerfactory/escanear', {'feeders': ['F1']}),
    ('verificar_convergencia', {'proyecto': 'P1'}, {}, 'POST', '/powerfactory/verificar', {'project': 'P1'}),
    ('descargar_resultados', {'alimentadores': ['F1']}, {}, 'POST', '/outputs/archive', {'feeders': ['F1']}),
    ('pronostico', {'ruta': 'D:/m'}, {'pronostico': {'clase': 'cabecera'}}, 'POST', '/digital-twin/temporal',
     {'clase': 'cabecera', 'modo': 'pronostico'}),
])
def test_tareas_cada_una_por_su_ruta(tarea, datos, extras, metodo, ruta, parte):
    """070:RF-19 / 070:RF-22 / 070:RF-23 / 070:RF-26 / 070:RF-27 / 070:RF-28 / 070:RF-35 / 070:RF-36 — la ruta del operador."""
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
