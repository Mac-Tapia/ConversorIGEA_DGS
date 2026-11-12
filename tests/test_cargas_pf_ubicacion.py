"""Spec 004, RF-72 a RF-80: la ubicación de una carga nueva se comprueba antes de conectarla.

Caso real (PA217, 2026-11-12): SE0001 se escribió con Y = 476 517, un dígito de menos; su GPS quedó cerca del Polo Sur,
se conectó con una línea de miles de km, el flujo de «Cargas nuevas» no convergió y, al corregirla, se habría
reutilizado la mal puesta. Las redes de estas pruebas son sintéticas y sorteadas; la fila real se comprobó aparte, en
solo lectura, con la geografía de PA217 del espacio del usuario (sus cifras no van a git).
"""
from __future__ import annotations

import json
import math
import os
import random

import pytest

import fake_pf
from apoyo import cargar_herramienta
from convertersmartgrid.cargas_pf import (
    FRACCION_LINEA_LARGA, a_wgs84, distancia_gps_m, leer_hoja_nuevas, nodos_de_la_geografia, numero_es,
    verificar_ubicacion, verificar_ubicaciones, zona_del_alimentador,
)
from test_cargas_pf_guion import _nueva, _plan

pytest.importorskip('pyproj')

SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))
#: El CRS del caso de prueba: aquí es un dato de la prueba, no un valor por defecto del programa (P13).
CRS = 'EPSG:32718'
STAMP = '20261008_120000'


def a_gps(puntos):
    return a_wgs84(puntos, CRS)


def _red(rng):
    """Un alimentador sorteado en UTM: una cadena de 20 a 200 nodos con tramos de 50 a 400 m."""
    x, y = rng.uniform(300_000, 700_000), rng.uniform(8_200_000, 8_900_000)
    rumbo = rng.uniform(0, 2 * math.pi)
    xy = []
    for _ in range(rng.randint(20, 200)):
        xy.append((round(x, 1), round(y, 1)))
        rumbo += rng.uniform(-0.6, 0.6)
        paso = rng.uniform(50, 400)
        x, y = x + paso * math.cos(rumbo), y + paso * math.sin(rumbo)
    gps = a_gps(xy)
    nodos = [(f'N{i}', la, lo) for i, (la, lo) in enumerate(gps)]
    return xy, nodos


def _fila(**celdas):
    cabecera = ['nombre', 'SED', 'alimentador', 'Kw', 'FP', *celdas]
    filas, errores = leer_hoja_nuevas(cabecera, [['Cliente', 'SE0001', 'F1', '1500', '0.98', *celdas.values()]],
                                      'formulario', source_crs=CRS, avisos=[])
    assert errores == [] and len(filas) == 1, errores
    return filas[0].para_pf()


@pytest.fixture()
def red():
    rng = random.Random(SEMILLA)
    xy, nodos = _red(rng)
    return rng, xy, zona_del_alimentador('F1', nodos)


def test_un_digito_de_menos_en_y_se_rechaza_y_se_propone(red):
    """004:RF-72 / 004:RF-73 / 004:RF-74 — el caso de SE0001: Y sin su primer dígito queda a miles de km del
    alimentador; la fila se rechaza con la distancia y propone la Y entera, que quedaría junto a su nodo."""
    rng, xy, zona = red
    x, y = xy[rng.randrange(len(xy))]
    y_real = round(y + 20.0)
    escrita = float(str(int(y_real))[1:])
    fila = _fila(CoordX=str(x), CoordY=str(escrita))
    u = verificar_ubicacion(fila, zona, a_gps)
    assert u['fuera'] and u['distancia_m'] > 1_000_000, (SEMILLA, u)
    mejor = u['propuestas'][0]
    assert mejor['cambios'] == {'CoordY': float(y_real)} and mejor['campo'] == 'CoordY', (SEMILLA, u['propuestas'])
    assert mejor['distancia_m'] <= 25.0 and zona.dentro(mejor['distancia_m'])
    assert f'¿quiso decir Y = {numero_es(float(y_real))}?' in u['mensaje']
    assert f'del nodo {mejor["nodo"]}' in u['mensaje'] and 'km de F1' in u['mensaje']
    assert 'no se cambia solo' in u['mensaje']
    # Nunca se aplica: la fila sigue con lo que escribió el operador.
    assert fila['coord_y'] == escrita


def test_un_digito_de_mas_en_x_se_propone(red):
    """004:RF-74 — lo mismo con un dígito de más, en la X."""
    rng, xy, zona = red
    x, y = xy[rng.randrange(len(xy))]
    x_real = round(x + 15.0)
    escrita = float(str(rng.randint(1, 9)) + str(int(x_real)))
    u = verificar_ubicacion(_fila(CoordX=str(escrita), CoordY=str(y)), zona, a_gps)
    assert u['fuera'] and u['propuestas'][0]['cambios'] == {'CoordX': float(x_real)}, (SEMILLA, u)
    assert f'¿quiso decir X = {numero_es(float(x_real))}?' in u['mensaje']


def test_x_e_y_intercambiadas_se_proponen(red):
    """004:RF-73 / 004:RF-74 — X e Y escritas al revés: se rechaza y propone intercambiarlas."""
    rng, xy, zona = red
    x, y = xy[rng.randrange(len(xy))]
    u = verificar_ubicacion(_fila(CoordX=str(y), CoordY=str(x)), zona, a_gps)
    assert u['fuera'], (SEMILLA, u)
    assert u['propuestas'][0]['campo'] == 'CoordX/CoordY'
    assert u['propuestas'][0]['cambios'] == {'CoordX': x, 'CoordY': y}
    assert 'X e Y intercambiadas' in u['mensaje']


def test_lat_y_lon_intercambiadas_se_proponen(red):
    """004:RF-73 / 004:RF-74 — Lat y Lon al revés: se rechaza y propone intercambiarlas."""
    rng, _xy, zona = red
    _n, la, lo = zona.nodos[rng.randrange(len(zona.nodos))]
    fila = _fila(Lat=str(lo), Lon=str(la))
    u = verificar_ubicacion(fila, zona, a_gps)
    assert u['fuera'], (SEMILLA, u)
    (p,) = u['propuestas']
    assert p['campo'] == 'Lat/Lon' and p['cambios'] == {'Lat': la, 'Lon': lo} and p['distancia_m'] < 1.0
    assert 'Lat y Lon intercambiadas' in u['mensaje']


def test_un_punto_bueno_sigue_con_su_distancia_al_nodo(red):
    """004:RF-72 — un punto junto a la red pasa, con su nodo más cercano y su distancia «a N m del nodo X»."""
    rng, xy, zona = red
    x, y = xy[rng.randrange(len(xy))]
    fila = _fila(CoordX=str(x + 30.0), CoordY=str(y))
    siguen, rechazadas = verificar_ubicaciones([fila], {'F1': zona}, a_gps)
    assert rechazadas == []
    (u,) = [f['ubicacion'] for f in siguen]
    assert not u['fuera'] and u['distancia_m'] <= 30.5 and u['radio_m'] == pytest.approx(zona.radio_m, abs=0.1)
    assert u['mensaje'] == f"SE0001: a {round(u['distancia_m'])} m del nodo {u['nodo']} de F1 (004:RF-72)."


def test_el_tope_del_perfil_manda_sobre_el_radio(red):
    """004:RF-73 — con el tope del perfil, ese es el límite y no el radio del alimentador, en los dos sentidos."""
    rng, _xy, zona = red
    nodos = zona.nodos
    # Un punto a unos 55 m de un nodo y a más de 10 m de todos (la cadena sorteada puede volver sobre sí misma).
    for _n, la, lo in rng.sample(nodos, len(nodos)):
        cerca = {'sed': 'C', 'lat': la + 0.0005, 'lon': lo}
        if zona.cercano((cerca['lat'], cerca['lon']))[1] > 10.0:
            break
    assert zona.tope_m == pytest.approx(2 * zona.radio_m)       # sin perfil: el radio más un radio de margen
    estrecha = zona_del_alimentador('F1', nodos, tope_perfil_m=10.0)
    u = verificar_ubicacion(cerca, estrecha)
    assert u['fuera'] and u['tope_del_perfil'] and 'tope del perfil, 10 m' in u['mensaje']
    lejos = {'sed': 'L', 'lat': la + 1.0, 'lon': lo}            # ~111 km
    if 111_000 > zona.tope_m:
        assert verificar_ubicacion(lejos, zona)['fuera']
    assert not verificar_ubicacion(lejos, zona_del_alimentador('F1', nodos, tope_perfil_m=500_000.0))['fuera']


def test_sin_geografia_la_fila_sigue_sin_medir():
    """004:RF-75 — un alimentador sin geografía de la red convertida no se mide en la web: lo hace el guion."""
    fila = {'sed': 'S', 'alimentador': 'F9', 'lat': -85.6, 'lon': -89.9}
    siguen, rechazadas = verificar_ubicaciones([fila], {'F9': None})
    assert siguen == [fila] and rechazadas == []
    assert zona_del_alimentador('F9', [('a', None, None), ('b', 'x', 1)]) is None


def test_la_geografia_de_la_conversion_da_los_nodos(tmp_path):
    """004:RF-72 — los nodos salen del ``<alimentador>_geography.json`` de la conversión, con el nombre de su barra."""
    ruta = tmp_path / 'F1_geography.json'
    ruta.write_text(json.dumps({'nodes': {'18680': {'lat': -13.8, 'lon': -76.2, 'x': 1, 'y': 2}}}), encoding='utf-8')
    assert nodos_de_la_geografia(ruta) == [('18680', -13.8, -76.2)]


# =========================================================================== web
def _geografia(tmp_path, nombre, nodos):
    ruta = tmp_path / f'{nombre}_geography.json'
    ruta.write_text(json.dumps({'nodes': {n: {'lat': la, 'lon': lo} for n, la, lo in nodos}}), encoding='utf-8')
    return ruta


def test_web_rechaza_la_fila_con_su_propuesta(tmp_path, monkeypatch):
    """004:RF-72 / 004:RF-73 / 004:RF-74 / 004:RF-80 — el plan de la web: la fila fuera de su alimentador no va a
    DIgSILENT; su error, con la propuesta, va en ``row_errors`` y en ``ubicaciones_rechazadas``; la buena sigue con su
    ubicación, y el tope del perfil llega al guion."""
    pytest.importorskip('fastapi')
    pytest.importorskip('httpx2')
    from fastapi.testclient import TestClient

    from apoyo import vincular_proyecto
    from convertersmartgrid.web import services
    from convertersmartgrid.web.app import create_app

    rng = random.Random(SEMILLA)
    xy, nodos = _red(rng)
    salida = tmp_path / 'run' / 'salida'
    salida.mkdir(parents=True)
    _geografia(salida, 'F1', nodos)
    monkeypatch.setattr(services, '_dgs_aceptados', lambda _ws, _p: [salida / 'F1.dgs'])
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    x, y = xy[len(xy) // 2]
    with TestClient(create_app(tmp_path / 'web')) as client:
        wid = client.post('/api/workspaces').json()['id']
        assert client.put(f'/api/workspaces/{wid}/options', json={'source_crs': CRS}).status_code == 200
        vincular_proyecto(client, wid, 'P', ['F1'])
        mala = {'nombre': 'Italica', 'SED': 'SE0001', 'alimentador': 'F1', 'Kw': '1500', 'FP': '0.98',
                'CoordX': str(x), 'CoordY': str(float(str(int(y))[1:]))}
        r = client.post(f'/api/workspaces/{wid}/lote/plan', data={'project': 'P', 'feeders': ['F1'],
                                                                   'nueva': json.dumps(mala)})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['applicable'] is False and body['nuevas'] == []
        (rechazo,) = body['ubicaciones_rechazadas']
        assert rechazo['sed'] == 'SE0001' and rechazo['propuestas'][0]['cambios'] == {'CoordY': float(int(y))}
        assert rechazo['mensaje'] in body['row_errors'] and '¿quiso decir Y =' in rechazo['mensaje']
        buena = {**mala, 'CoordY': str(y)}
        body = client.post(f'/api/workspaces/{wid}/lote/plan', data={'project': 'P', 'feeders': ['F1'],
                                                                      'nueva': json.dumps(buena)}).json()
        assert body['applicable'] is True and body['ubicaciones_rechazadas'] == []
        (n,) = body['nuevas']
        assert n['ubicacion']['distancia_m'] < 1.0 and n['ubicacion']['fuente'] == 'red convertida de F1'
        plan = json.loads(next((tmp_path / 'web').rglob(f"cargas_pf_{body['token']}.json")).read_text(encoding='utf-8'))
        assert 'distancia_max_al_nodo_m' in plan and plan['nuevas'][0]['coord_y'] == y


def test_web_red_unida_usa_la_geografia_de_la_red(tmp_path, monkeypatch):
    """004:RF-72 — en una red unida sin la geografía propia del alimentador, la de la red entera, y se dice."""
    from convertersmartgrid.web import services

    _geografia(tmp_path, 'Grupo', [('n', -14.0, -75.7)])
    monkeypatch.setattr(services, '_dgs_aceptados', lambda _ws, _p: [tmp_path / 'Grupo.dgs'])
    (ruta, fuente), = services._geografias_del_proyecto(None, 'P', ['F1']).values()
    assert ruta.name == 'Grupo_geography.json' and 'sin la geografía propia de F1' in fuente
    monkeypatch.setattr(services, '_dgs_aceptados', lambda _ws, _p: [])
    assert services._geografias_del_proyecto(None, 'P', ['F1']) == {}


# =========================================================================== guion
@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('cargas_pf.py', 'cargas_pf_guion_ubicacion', tools_en_path=True)


def _app():
    return fake_pf.proyecto(alimentadores=('F1', 'F2'), cargas_por_alim=4, bt=True, flujo=True)


def _barra(app, nombre):
    return next(b for b in app.proyecto.GetContents('*.ElmTerm', 1) if b.loc_name == nombre)


def _variaciones(app):
    return {v.loc_name: v for v in app.carpetas['scheme'].GetContents('*.IntScheme')}


def _caso(app, nombre):
    return next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == nombre)


def test_guion_sin_geografia_rechaza_con_las_barras_de_digsilent(guion):
    """004:RF-75 / 004:RF-73 / 004:RF-74 — sin ``ubicacion`` de la web, el guion mide el punto con las barras de media
    con GPS del alimentador: lejos, no se crea ni se conecta, con el motivo y la propuesta de Lat/Lon intercambiadas."""
    app = _app()
    b2 = _barra(app, 'F1_B2')
    filas = [_nueva('POLO', alimentador='F1', lat=-85.6, lon=-89.9),
             _nueva('REVES', alimentador='F1', lat=b2.GPSlon, lon=b2.GPSlat)]
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=filas), simular=True)
    assert rc == 0, informe
    motivos = {x['sed']: x['motivo'] for x in informe['no_creadas']}
    assert '004:RF-73' in motivos['POLO'] and 'km de F1' in motivos['POLO']
    assert 'Lat y Lon intercambiadas' in motivos['REVES'] and 'F1_B2' in motivos['REVES']
    assert [c for f in informe['feeders'] for c in f['crearian']] == []


def test_guion_da_la_longitud_de_la_linea_y_avisa_si_es_larga(guion):
    """004:RF-72 / 004:RF-78 / 004:RF-79 — al simular, cada carga dice su nodo más cercano y la longitud de su línea
    de conexión; la que pasa de la mitad del radio del alimentador se avisa."""
    app = _app()
    b2 = _barra(app, 'F1_B2')
    corta = _nueva('CORTA', alimentador='F1', lat=b2.GPSlat + 0.0003, lon=b2.GPSlon)    # ~33 m
    larga = _nueva('LARGA', alimentador='F1', lat=b2.GPSlat + 0.0015, lon=b2.GPSlon)    # ~167 m
    informe, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[corta, larga]), simular=True)
    assert rc == 0, informe
    crearian = {c['sed']: c for f in informe['feeders'] for c in f['crearian']}
    radio = crearian['CORTA']['radio_m']
    assert radio and 33.4 < FRACCION_LINEA_LARGA * radio < 166.8
    assert crearian['CORTA']['longitud_linea_m'] == pytest.approx(33.4, abs=1.0)
    assert crearian['LARGA']['longitud_linea_m'] == pytest.approx(166.8, abs=1.5)
    assert crearian['CORTA']['ubicacion']['nodo'] == 'F1_B2'
    largas = [a for a in informe['avisos'] if '004:RF-79' in a]
    assert len(largas) == 1 and 'LARGA' in largas[0]


def test_guion_reutiliza_si_no_cambia_y_reemplaza_si_cambia(guion):
    """004:RF-76 / 004:RF-77 — la misma fila otra vez reutiliza la variación (014:RF-24); con otra ubicación, la
    variación anterior se elimina, con su carga y su línea, y se crea de nuevo, y el informe lo dice."""
    app = _app()
    b2 = _barra(app, 'F1_B2')
    fila = _nueva('SE0001', alimentador='F1', lat=b2.GPSlat + 0.0003, lon=b2.GPSlon)
    primero, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[fila]), simular=False)
    assert rc == 0, primero
    (var,) = [n for n in _variaciones(app) if 'SE0001' in n]
    _caso(app, 'Caso base').Activate()

    igual, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[fila]), simular=False)
    assert rc == 0, igual
    assert [x['variacion'] for x in igual['reutilizadas']] == [var] and igual['cargas'] == []
    assert not any('004:RF-76' in a for a in igual['avisos'])
    _caso(app, 'Caso base').Activate()

    movida = {**fila, 'lat': b2.GPSlat - 0.0004}
    simulado, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[movida]), simular=True)
    assert rc == 0 and [x['variacion'] for x in simulado['eliminarian']] == [var], simulado
    assert simulado['reutilizadas'] == []
    _caso(app, 'Caso base').Activate()
    segundo, rc = guion.ejecutar(app, _plan(['F1'], nuevas=[movida]), simular=False)
    assert rc == 0, segundo
    assert any('SE0001: cambió su ubicación; se reemplaza la carga anterior' in a for a in segundo['avisos'])
    (eliminada,) = segundo['eliminadas']
    assert eliminada['variacion'] == var and eliminada['eliminada'] and '004:RF-76' in eliminada['motivo']
    (creada,) = segundo['cargas']
    assert creada['sed'] == 'SE0001' and creada['reemplaza']['cambios'] == ['su ubicación']
    nuevas = [n for n in _variaciones(app) if 'SE0001' in n]
    assert len(nuevas) == 1
    cargas = [c for v in _variaciones(app).values() for e in v.GetContents('*.IntSstage')
              for c in e.GetContents('*.ElmLod', 1) if c.loc_name == 'SE0001']
    assert len(cargas) == 1 and distancia_gps_m((cargas[0].GPSlat, cargas[0].GPSlon),
                                                (movida['lat'], movida['lon'])) < 1.0
    assert guion.huella_de(cargas[0])['lat'] == movida['lat']


def test_cambios_de_la_carga_con_y_sin_huella(guion):
    """004:RF-76 / 004:RF-77 — con huella se compara con la fila con que se creó (kW, kVAR, kVA, barra, ubicación);
    sin ella (las creadas antes del cambio), con el GPS y la potencia de la carga."""
    fila = _nueva('N1', alimentador='F1', lat=-14.0, lon=-75.7)
    con = type('Carga', (), {})()
    con.desc = [guion.HUELLA + json.dumps(guion.huella_de_la_fila(fila))]
    assert guion.cambios_de_la_carga(con, fila) == []
    otra = {**fila, 'kw': 90.0, 'kvar': 31.0, 'kva_instalado': 250.0, 'barra': 'F1_B3'}
    assert guion.cambios_de_la_carga(con, otra) == ['su kW', 'su kVAR', 'su kVA', 'su barra']
    sin = type('Carga', (), {})()
    sin.GPSlat, sin.GPSlon, sin.plini, sin.qlini = -85.6, -89.9, 0.08, 0.03
    assert guion.cambios_de_la_carga(sin, fila) == ['su ubicación']
    # Sin huella, la potencia leída (escenario, retoques del operador) no reemplaza: se avisa (014:RF-28).
    sin.GPSlat, sin.GPSlon, sin.plini = -14.0, -75.7, 0.095
    assert guion.cambios_de_la_carga(sin, fila) == []
