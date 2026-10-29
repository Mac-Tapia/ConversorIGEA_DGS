"""Spec 028: escaneo del alimentador antes de recalibrar, reglas y guion con ``fake_pf``."""
from __future__ import annotations

import random
import string

import fake_pf
import pytest
from apoyo import cargar_herramienta

from igea_dgs import escaneo as esc

SEMILLA = random.randrange(1 << 30)


def _nombre(rnd: random.Random) -> str:
    return ''.join(rnd.choice(string.ascii_uppercase + string.digits) for _ in range(rnd.randint(3, 9)))


def test_reglas_origen_por_los_prefijos_del_conversor():
    """028:RF-3 / 028:RF-4 / 028:RF-5 / 028:RF-7 — lo propio por sus prefijos; cualquier otro
    nombre, sorteado, es del operador."""
    rnd = random.Random(SEMILLA)
    for prefijo, _que in esc.PREFIJOS_PROPIOS:
        assert esc.origen_de(prefijo + _nombre(rnd))['origen'] == 'conversor'
        assert esc.origen_de(_nombre(rnd).lower(), prefijo + 'x')['origen'] == 'conversor'
    for _ in range(50):
        n = _nombre(rnd).lower()
        assert esc.origen_de(n, None)['origen'] == 'operador', (SEMILLA, n)


def test_reglas_barra_de_la_central_y_resumen():
    """028:RF-11 / 028:RF-12 — la barra del generador del operador antes que la del conversor;
    con dos barras del mismo origen no se elige."""
    g = lambda barra, origen, servicio=True: {'barra': barra, 'origen': origen, 'en_servicio': servicio}
    escaneo = {'alimentadores': {
        'A': {'generadores': [g('B9', 'conversor'), g('B4', 'operador')], 'bancos': [
            {'banco': 'BC_CAL_A_1', 'origen': 'conversor'}, {'banco': 'X', 'origen': 'operador'}]},
        'B': {'generadores': [g('B1', 'conversor')]},
        'C': {'generadores': [g('B1', 'operador'), g('B2', 'operador')]},
        'D': {'generadores': [g('B1', 'operador', servicio=False)]}}}
    assert esc.nodo_de_central(escaneo, 'A') == 'B4'
    assert esc.nodo_de_central(escaneo, 'B') == 'B1'
    assert esc.nodo_de_central(escaneo, 'C') is None
    assert esc.nodo_de_central(escaneo, 'D') is None
    assert esc.nodo_de_central(None, 'A') is None
    r = esc.resumen(escaneo)['A']
    assert r == {'generadores': 2, 'generadores_del_operador': 1, 'bancos': 2,
                 'bancos_del_operador': 1, 'bancos_de_calibracion': 1, 'cargas_cambiadas': 0,
                 'tramos_nuevos': 0, 'tramos_cambiados': 0}


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('escanear_alimentador_pf.py', 'escanear_guion', tools_en_path=True)


def _con(app, alim: str, clase: str, nombre: str, barra: str):
    """Un objeto del operador conectado a ``barra`` del alimentador ``alim``."""
    red = app.proyecto.GetContents('*.ElmNet', 1)[0]
    elm = next(f for f in app.proyecto.GetContents('*.ElmFeeder', 1) if f.loc_name == alim)
    term = next(b for b in elm.GetObjs('ElmTerm') if b.loc_name == barra)
    obj = red.CreateObject(clase, nombre)
    cub = term.CreateObject('StaCubic', f'Cub_{nombre}')
    cub.obj_id, cub.obj_bus = obj, 0
    obj.bus1 = cub
    elm._objs.append(obj)
    return obj


def test_guion_lee_generadores_bancos_y_alimentador_que_falta(guion):
    """028:RF-1 / 028:RF-2 / 028:RF-4 / 028:RF-6 / 028:RF-8 — generador y banco del operador y
    de la calibración con su barra; un alimentador que no está se dice y los demás siguen; no
    escribe nada."""
    rnd = random.Random(SEMILLA)
    feeders = tuple(f'F{i}' for i in range(1, rnd.randint(2, 5)))
    app = fake_pf.proyecto(alimentadores=feeders, cargas_por_alim=4, bt=True, flujo=True)
    gen = _con(app, 'F1', 'ElmGenstat', 'GEN_OPERADOR', 'F1_B3')
    gen.pgini, gen.qgini, gen.outserv = 2.5, -0.3, 0
    for nombre in ('BC_CAL_F1_1', 'BANCO_OPERADOR'):
        b = _con(app, 'F1', 'ElmShnt', nombre, 'F1_B2')
        b.qcapn, b.ncapa, b.ncapx, b.outserv = 0.3, 1, 1, 0
    antes = len(app.creados)
    informe, rc = guion.ejecutar(app, {'project': 'P', 'feeders': [*feeders, 'NO_ESTA']})
    assert rc == 0, informe
    assert 'no está' in informe['alimentadores']['NO_ESTA']['error']
    f1 = informe['alimentadores']['F1']
    [g] = f1['generadores']
    assert (g['generador'], g['barra'], g['origen']) == ('GEN_OPERADOR', 'F1_B3', 'operador')
    assert g['p_kw'] == pytest.approx(2500.0) and g['en_servicio']
    assert {b['banco']: b['origen'] for b in f1['bancos']} == {'BC_CAL_F1_1': 'conversor',
                                                            'BANCO_OPERADOR': 'operador'}
    assert f1['cargas_cambiadas'] == []
    assert all(not informe['alimentadores'][f].get('error') for f in feeders)
    assert len(app.creados) == antes, 'el escaneo no crea nada (RF-1)'
    assert esc.nodo_de_central(informe, 'F1') == 'F1_B3'


def test_ruta_de_la_web_guarda_el_escaneo_y_la_central_toma_su_barra(tmp_path, monkeypatch):
    """028:RF-9 / 028:RF-10 / 028:RF-12 — la ruta encola el escaneo en el carril de DIgSILENT,
    lo guarda en el espacio y la central declarada sin barra toma la del generador."""
    from apoyo import esperar_trabajo
    from fastapi.testclient import TestClient

    from igea_dgs.web import services
    from igea_dgs.web.app import create_app

    informe = {'project': 'P', 'caso': 'Sin proyecto', 'avisos': [], 'variaciones': [],
               'alimentadores': {'A1': {'generadores': [{'generador': 'G', 'barra': 'N7', 'en_servicio': True,
                                                         'origen': 'operador'}],
                                        'bancos': [], 'cargas_cambiadas': []}}}
    pedidos = []
    monkeypatch.setattr(services, '_guion_pf', lambda ws, ctx, script, plan, **kw: (
        pedidos.append((script, plan)) or (0, dict(informe), tmp_path / 'r.json')))
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'carpeta')
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        wid = c.post('/api/workspaces').json()['id']
        assert c.post(f'/api/workspaces/{wid}/powerfactory/escanear', json={'project': 'P', 'feeders': []}).status_code == 422
        job = c.post(f'/api/workspaces/{wid}/powerfactory/escanear', json={'project': 'P', 'feeders': ['A1']}).json()
        assert job['lane'] == 'powerfactory'
        estado = esperar_trabajo(c, job)
        assert estado['status'] == 'done', estado
        assert estado['result']['resumen']['A1']['generadores_del_operador'] == 1
        assert c.get(f'/api/workspaces/{wid}/powerfactory/escaneo').json()['escaneo']['P']['caso'] == 'Sin proyecto'
        ws = c.app.state.store.get(wid)
    [(script, plan)] = pedidos
    assert script == 'escanear_alimentador_pf.py' and plan['feeders'] == ['A1']
    monkeypatch.setattr(services, 'demanda_central', lambda *a, **k: {'error': None, 'fecha': 'x'})
    avisos: list[str] = []
    central = services._central_del_plan(ws, 'J', 'A1', 'M', {'generacion': 'G1', 'llegada': 'G2',
                                                              'salida': 'G3', 'nodo': ''}, avisos, '')
    assert central['nodo'] == 'N7' and any('028:RF-12' in x for x in avisos)


def test_front_con_el_boton_y_la_tabla():
    """028:RF-9 / 028:RF-10 / 028:RF-11 — el botón llama a la ruta, la tabla muestra lo hallado
    y un generador declara la central con su barra."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1] / 'frontend' / 'src'
    demanda = (raiz / 'components' / 'DemandaMedida.tsx').read_text(encoding='utf-8')
    api = (raiz / 'api.ts').read_text(encoding='utf-8')
    assert 'Escanear en DIgSILENT</button>' in demanda and 'api.pfEscanear(ws.id, project, feeders' in demanda
    assert '/powerfactory/escanear' in api
    assert 'function EscaneoTabla' in demanda and 'Generadores (centrales)' in demanda
    assert "n[f] = { ...CENTRAL_VACIA, nodo: elegidas[0] }" in demanda


@pytest.fixture(scope='module')
def ajuste():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_escaneo_guion', tools_en_path=True)


def test_la_central_es_el_generador_del_operador(ajuste):
    """028:RF-13 — con un generador del operador en la barra de la central no se crea otro:
    lleva la P y Q medidas en el instante y el informe lo dice."""
    from test_ajuste_central_guion import _app, _plan

    app = _app()
    gen = _con(app, 'F1', 'ElmGenstat', 'CT_A_MANO', 'F1_B3')
    gen.pgini, gen.qgini, gen.outserv = 0.1, 0.0, 0
    informe, rc = ajuste.ejecutar(app, _plan())
    assert rc == 0, informe
    assert not [o for o in app.creados if o._clase == 'ElmGenstat' and o.loc_name.startswith('Central_')]
    c = informe['central']
    assert c['del_operador'] and c['generador'] == 'CT_A_MANO' and not c['creado']
    assert (gen.pgini, gen.qgini) == (pytest.approx(0.6), pytest.approx(-0.04))
    assert '028:RF-13' in c['aviso']



def test_tramos_nuevos_frente_al_dgs(guion, tmp_path):
    """028:RF-17 — un tramo que no venía en el DGS aceptado sale como nuevo con sus barras."""
    dgs = tmp_path / 'red.dgs'
    dgs.write_text('$$General;ID(a:40);Descr(a:40);Val(a:40)\n  1;Version;6.0\n'
                   '$$ElmLne;FID(a:40);OP(a:1);loc_name(a:40);fold_id(p)\n'
                   '  10;C;F1_L1;4\n  11;C;F1_L2;4\n  12;C;F1_L3;4\n$$ElmTerm;FID(a:40);OP(a:1);loc_name(a:40)\n'
                   '  20;C;F1_L4;4\n', encoding='cp1252')
    assert esc.tramos_del_dgs(dgs) == {'F1_L1', 'F1_L2', 'F1_L3'}
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=4, bt=True, flujo=True)
    informe, rc = guion.ejecutar(app, {'project': 'P', 'feeders': ['F1'], 'tramos_dgs': sorted(esc.tramos_del_dgs(dgs))})
    assert rc == 0
    [nuevo] = informe['alimentadores']['F1']['tramos_nuevos']
    assert nuevo['tramo'] == 'F1_L4' and nuevo['desde'] == 'F1_B3' and nuevo['hasta'] == 'F1_B4'
    assert esc.resumen(informe)['F1']['tramos_nuevos'] == 1


def test_tramos_cambiados_a_mano_en_una_variacion_del_operador(guion):
    """028:RF-26 — un tramo del DGS aceptado que graba una variación del operador sale como
    cambiado a mano, con su variación y su longitud de ahora; el de una variación del
    conversor («Fichas_») no. Usuario, 2026-10-28: «todas esas modificaciones manuales debe
    reconocerlas al momento de recalibrar»."""
    rnd = random.Random(SEMILLA)
    app = fake_pf.proyecto(alimentadores=('F1',), cargas_por_alim=4, bt=True, flujo=True)
    lineas = {ln.loc_name: ln for ln in app.proyecto.GetContents('*.ElmLne', 1)}
    suyo, del_conversor = rnd.sample(sorted(n for n in lineas if n.startswith('F1_L')), 2)
    nombre = f'Terna_{_nombre(rnd)}'
    var = app.carpetas['scheme'].CreateObject('IntScheme', nombre)
    var.NewStage('Etapa', 1_760_000_000, 1)
    km = round(rnd.uniform(0.1, 3.0), 3)
    lineas[suyo].dline = km
    fichas = app.carpetas['scheme'].CreateObject('IntScheme', 'Fichas_P')
    fichas.NewStage('Etapa', 1_760_000_100, 1)
    lineas[del_conversor].dline = 9.0

    informe, rc = guion.ejecutar(app, {'project': 'P', 'feeders': ['F1'],
                                       'tramos_dgs': sorted(lineas)})

    assert rc == 0, informe
    [fila] = informe['alimentadores']['F1']['tramos_cambiados']
    assert fila['tramo'] == suyo and fila['variacion'] == nombre and fila['km'] == pytest.approx(km)
    assert esc.resumen(informe)['F1']['tramos_cambiados'] == 1


def test_recalibrar_sin_bloqueos(tmp_path, monkeypatch):
    """028:RF-16 / 028:RF-19 / 028:RF-20 — la calibración escanea antes sin que se pida y, si el
    escaneo falla, calibra igual; una central sin barra ni generador no detiene el plan."""
    from threading import Event
    from types import SimpleNamespace

    from igea_dgs.web import services

    ws = SimpleNamespace(escaneo={}, pf_project_bindings={}, root=tmp_path, calibraciones={})
    avisos: list[str] = []
    monkeypatch.setattr(services, 'demanda_central', lambda *a, **k: {'error': None})
    assert services._central_del_plan(ws, 'J', 'A1', 'M', {'generacion': 'G', 'llegada': 'L', 'salida': 'S',
                                                           'nodo': ''}, avisos, '') is None
    assert any('028:RF-19' in a for a in avisos)
    logs = []
    ctx = SimpleNamespace(log=logs.append, cancel=Event())
    monkeypatch.setattr(services, 'escanear_alimentadores',
                        lambda *a, **k: (_ for _ in ()).throw(services.UserError('DIgSILENT ocupado')))
    assert services._escanear_sin_bloquear(ws, ctx, 'P', ['A1'], None) is None
    assert any('se calibra igual' in x for x in logs)
    assert services._tramos_del_dgs_aceptado(ws, 'P') == set()


def test_generador_del_operador_sin_central(ajuste):
    """028:RF-18 — sin central declarada, el generador del operador se queda en la red y el
    informe lo dice; no se crea ninguno."""
    from test_ajuste_central_guion import _app, _plan

    app = _app()
    gen = _con(app, 'F1', 'ElmGenstat', 'GD_A_MANO', 'F1_B3')
    gen.pgini, gen.qgini, gen.outserv = 0.2, 0.0, 0
    plan = _plan()
    plan.pop('central')
    informe, _rc = ajuste.ejecutar(app, plan)
    assert informe['generadores_del_operador'] == [{'generador': 'GD_A_MANO', 'p_kw': 200.0}]
    assert any('028:RF-18' in a for a in informe['avisos'])
    assert not [o for o in app.creados if o._clase == 'ElmGenstat' and o.loc_name.startswith('Central_')]


def test_boton_recalibrar_y_su_ruta(tmp_path, monkeypatch):
    """028:RF-21 / 028:RF-22 / 028:RF-23 / 028:RF-24 — la ruta saca el sistema del proyecto y la carpeta de
    los libros, corre ``sistema_web.py`` sin reconvertir en el carril del asistente y rechaza un
    proyecto que no es de un sistema; el front tiene su botón aparte."""
    from pathlib import Path

    from apoyo import esperar_trabajo
    from fastapi.testclient import TestClient

    from igea_dgs.web import jobs, services
    from igea_dgs.web.app import create_app

    ordenes = []
    monkeypatch.setattr(jobs.JobContext, 'run_process', lambda self, cmd, **kw: ordenes.append(cmd) or 0)
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    libros = tmp_path / 'referencia'
    (libros / '1.-medidores').mkdir(parents=True)
    (libros / '2.-cabecera').mkdir()
    with TestClient(create_app(tmp_path / 'web')) as c:
        wid = c.post('/api/workspaces').json()['id']
        ws = c.app.state.store.get(wid)
        ws.demanda = {'medidores': {'path': str(libros / '1.-medidores' / 'm.xlsx')},
                      'cabecera': {'path': str(libros / '2.-cabecera')}}
        d = c.get(f'/api/workspaces/{wid}/demanda/recalibrar', params={'project': '20261028_IGEA_SISTEMA_CHINCHA'}).json()
        assert d == {'zonal': 'Chincha', 'demanda_dir': str(libros)}
        assert c.post(f'/api/workspaces/{wid}/demanda/recalibrar',
                      json={'project': 'P_CA101', 'periodo': '2026-07'}).status_code == 400
        assert c.post(f'/api/workspaces/{wid}/demanda/recalibrar',
                      json={'project': 'X_SISTEMA_CHINCHA', 'periodo': 'julio'}).status_code == 422
        job = c.post(f'/api/workspaces/{wid}/demanda/recalibrar',
                     json={'project': '20261028_IGEA_SISTEMA_CHINCHA', 'periodo': '2026-07'}).json()
        assert job['lane'] == 'asistente'
        fin = esperar_trabajo(c, job)
        assert fin['status'] == 'done' and fin['result']['texto'] == 'recalibrado y válido'
        # 028:RF-24: el proyecto de dos alimentadores unidos, por su grupo y sin barra.
        ws.pf_projects = {'IN111_TA225': '20261028_IGEA_IN111_TA225', 'CA101': '20261028_IGEA_CA101'}
        ws.groups = {'IN111_TA225': {'tipo': 'unida', 'feeders': ['IN111', 'TA225']}}
        d = c.get(f'/api/workspaces/{wid}/demanda/recalibrar', params={'project': '20261028_IGEA_IN111_TA225'}).json()
        assert d['grupo'] == 'IN111_TA225' and d['alimentadores'] == ['IN111', 'TA225'] and d['zonal'] == ''
        assert c.get(f'/api/workspaces/{wid}/demanda/recalibrar',
                     params={'project': '20261028_IGEA_CA101'}).json()['alimentadores'] == ['CA101']
        fin = esperar_trabajo(c, c.post(f'/api/workspaces/{wid}/demanda/recalibrar',
                                        json={'project': '20261028_IGEA_IN111_TA225', 'periodo': '2026-07'}).json())
        assert fin['status'] == 'done'
    cmd, cmd2 = ordenes
    assert Path(cmd[1]).name == 'sistema_web.py' and '--reconvertir' not in cmd
    assert cmd[cmd.index('--zonal') + 1] == 'Chincha' and cmd[cmd.index('--periodo') + 1] == '2026-07'
    assert '--zonal' not in cmd2 and cmd2[cmd2.index('--red') + 1:cmd2.index('--grupo')] == ['IN111', 'TA225']
    assert cmd2[cmd2.index('--grupo') + 1] == 'IN111_TA225'
    demanda = (Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'components' / 'DemandaMedida.tsx').read_text(encoding='utf-8')
    assert 'Recalibrar «Sin proyecto»' in demanda and 'api.recalibrar(ws.id' in demanda


@pytest.mark.parametrize('grupo,feeders,project', [
    ('CA101', None, 'P_CA101'),
    ('RED', ['CA101', 'CA102'], 'P_RED'),
    ('SISTEMA_PISCO', ['CA101', 'CA102'], 'P_SISTEMA_PISCO'),
])
def test_recalibrar_alimentadores_usa_la_seleccion_guardada(tmp_path, monkeypatch, grupo, feeders, project):
    """RF-24: la pertenencia del espacio manda incluso si una red unida se llama SISTEMA_*."""
    from apoyo import esperar_trabajo
    from fastapi.testclient import TestClient
    from igea_dgs.web import jobs
    from igea_dgs.web.app import create_app

    ordenes = []
    monkeypatch.setattr(jobs.JobContext, 'run_process', lambda self, cmd, **kw: ordenes.append(cmd) or 0)
    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        wid = c.post('/api/workspaces').json()['id']
        ws = c.app.state.store.get(wid)
        ws.pf_projects[grupo] = project
        ws.demanda = {'medidores': {'path': str(tmp_path / 'm.xlsx')}}
        if feeders:
            ws.groups[grupo] = {'tipo': 'unida', 'feeders': feeders}
        esperado = feeders or [grupo]
        ruta = f'/api/workspaces/{wid}/demanda'
        d = c.get(ruta + '/recalibrar', params={'project': project}).json()
        assert d['zonal'] == '' and d['grupo'] == grupo and d['alimentadores'] == esperado
        assert c.get(ruta + '/sistema', params={'project': project}).json()['sistema'] is None
        sistema = c.get(ruta + '/sistema', params={'project': project, 'todos': True}).json()['sistema']
        assert sistema['alimentadores'] == esperado
        job = c.post(ruta + '/recalibrar', json={
            'project': project, 'periodo': '2026-07', 'zonal': 'Pisco'}).json()
        assert esperar_trabajo(c, job)['status'] == 'done'
    [cmd] = ordenes
    assert '--zonal' not in cmd and '--reconvertir' not in cmd
    assert cmd[cmd.index('--red') + 1:cmd.index('--grupo')] == esperado
    assert cmd[cmd.index('--grupo') + 1] == grupo


def test_las_variaciones_del_catalogo_son_del_conversor():
    """032:RF-27 — ``Fichas_`` y ``SED_NTP_`` son del conversor para el escaneo (028)."""
    from igea_dgs import escaneo as esc

    for nombre in ('Fichas_CA101', 'SED_NTP_Chincha'):
        assert esc.origen_de('', nombre)['origen'] == 'conversor'
        assert nombre.startswith(esc.PREFIJOS_CATALOGO)
