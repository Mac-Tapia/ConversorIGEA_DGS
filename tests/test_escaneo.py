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
                 'bancos_del_operador': 1, 'bancos_de_calibracion': 1, 'cargas_cambiadas': 0}


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

