"""Spec 017 (RF-109, RF-111, RF-112, RF-124): el mapa de las cargas nuevas y su punto de diseño leído en DIgSILENT.

Usuario, 2026-11-13: «en la web se debe ver la ubicación en Google Maps o similar de dónde se conectó y la ubicación
de la carga nueva o de los bloques, y eso debe ir en el informe»; «debe haber un botón para actualizar la imagen de la
ubicación y el punto de fijación de diseño cuando el usuario verificó en DIgSILENT, corrigió o asignó otro punto».
"""
from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest
from PIL import Image

import fake_pf  # noqa: F401 - lo usan los dobles importados
from apoyo import cargar_herramienta
from test_cargas_pf_guion import _nueva, _plan
from test_cargas_pf_guion_007 import _app, _barra

LAT, LON0 = -14.0, -75.7                     # F1 en el doble: barras F1_Bi en LON0 + 0,001·i


@pytest.fixture(scope='module')
def cargas_pf():
    return cargar_herramienta('cargas_pf.py', 'cargas_pf_mapa', tools_en_path=True)


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ubicacion_cargas_pf.py', 'ubicacion_cargas_guion', tools_en_path=True)


def _aplicada(cargas_pf, sed='N1', dlat=0.0005):
    """Una carga nueva aplicada por ``cargas_pf.py`` frente al centro de F1_L2, con su enlace si está a más de 25 m."""
    app = _app(alimentadores=('F1',))
    plan = _plan(['F1'], nuevas=[_nueva(sed, alimentador='F1', lat=LAT + dlat, lon=LON0 + 0.0015)])
    informe, rc = cargas_pf.ejecutar(app, plan, simular=False)
    assert rc == 0 and not informe['no_creadas'], informe
    (creada,) = informe['feeders'][0]['creadas']
    return app, creada


def _plan_lectura(creada, **extra):
    return {'project': 'P', 'feeders': ['F1'],
            'cargas': [{'sed': creada['sed'], 'alimentador': 'F1', 'variacion': creada['variacion']}], **extra}


# --------------------------------------------------------------------------- guion de solo lectura
def test_el_guion_lee_el_nodo_y_el_enlace_sin_escribir(cargas_pf, guion):
    """017:RF-124 — en «Con proyecto», el nodo de media al que llega la línea de enlace, con su GPS, y el punto de la
    carga; no escribe, no crea ni borra nada y deja activo el caso que lo estaba."""
    app, creada = _aplicada(cargas_pf)
    antes = (len(app.escrituras), len(app.creados), len(app.borrados), app.caso.loc_name)
    informe, rc = guion.ejecutar(app, _plan_lectura(creada))
    assert rc == 0 and informe['caso'] == 'Con proyecto' and informe['solo_lectura'] is True
    (fila,) = informe['cargas']
    assert fila['nodo']['nombre'] == creada['barra'] == 'NODE_T_N1'
    assert fila['nodo']['gps'] == pytest.approx([LAT, LON0 + 0.0015])
    assert fila['enlace']['nombre'] == 'LNE_N1' and fila['enlace']['km'] == pytest.approx(creada['distancia_m'] / 1000)
    assert fila['punto'] == pytest.approx([LAT + 0.0005, LON0 + 0.0015]) and fila['kw'] == pytest.approx(80.0)
    assert (len(app.escrituras), len(app.creados), len(app.borrados), app.caso.loc_name) == antes


def test_el_cambio_del_operador_se_lee_y_no_se_deshace(cargas_pf, guion):
    """017:RF-124 — el operador lleva en DIgSILENT el enlace a otro nodo: la lectura da ese nodo, y lo que él hizo
    sigue como estaba."""
    app, creada = _aplicada(cargas_pf)
    con = next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == 'Con proyecto')
    inicial = app.caso
    con.Activate()
    nodo = _barra(app, 'NODE_T_N1')
    cub = next(c for c in nodo.GetContents('*.StaCubic') if c.loc_name == 'Cub1_LNE_N1')
    _barra(app, 'F1_B3').Move(cub)                       # el operador: el enlace pasa a F1_B3
    inicial.Activate()
    informe, rc = guion.ejecutar(app, _plan_lectura(creada))
    assert rc == 0
    (fila,) = informe['cargas']
    assert fila['nodo']['nombre'] == 'F1_B3' and fila['enlace']['nombre'] == 'LNE_N1'
    con.Activate()
    assert cub.GetParent() is _barra(app, 'F1_B3')


def test_sin_enlace_el_nodo_es_el_del_seccionador(cargas_pf, guion):
    """017:RF-124 — a menos de 25 m la SED cuelga del nodo sin cable (016:RF-88): no hay enlace que leer."""
    app, creada = _aplicada(cargas_pf, dlat=0.0001)
    informe, _rc = guion.ejecutar(app, _plan_lectura(creada))
    (fila,) = informe['cargas']
    assert fila['nodo']['nombre'] == 'NODE_T_N1' and fila['enlace'] is None


def test_una_carga_nueva_que_la_web_no_tiene_tambien_se_lee(cargas_pf, guion):
    """017:RF-124 — una variación ``Carga_…`` activa en «Con proyecto» que no está en lo guardado sale como «solo en
    DIgSILENT»; una guardada que ya no está, con su motivo."""
    app, creada = _aplicada(cargas_pf)
    plan = {'project': 'P', 'feeders': ['F1'],
            'cargas': [{'sed': 'OTRA', 'alimentador': 'F1', 'variacion': 'Carga_OTRA_F1_1'}]}
    informe, rc = guion.ejecutar(app, plan)
    assert rc == 0
    filas = {f['sed']: f for f in informe['cargas']}
    assert 'no está en la red' in filas['OTRA']['error'] and 'no está activa' in filas['OTRA']['error']
    assert filas['N1']['solo_en_digsilent'] is True and filas['N1']['alimentador'] == 'F1'
    assert filas['N1']['variacion'] == creada['variacion'] and filas['N1']['nodo']['nombre'] == 'NODE_T_N1'


def test_la_carga_con_el_nombre_repetido_de_digsilent_se_encuentra(cargas_pf, guion):
    """017:RF-124 — CA101, 2026-11-13: DIgSILENT llamó «SECA0001(1)» a la carga porque su SED ya tiene una barra
    «SECA0001»; se encuentra por su SED, y la variación que la web no tiene da la SED, no el «(n)»."""
    app, creada = _aplicada(cargas_pf)
    con = next(c for c in app.carpetas['study'].GetContents('*.IntCase') if c.loc_name == 'Con proyecto')
    inicial = app.caso
    con.Activate()
    carga = next(o for o in app.proyecto.GetContents('*.ElmLod', 1) if o.loc_name == 'N1')
    carga.loc_name = 'N1(1)'
    inicial.Activate()
    informe, _rc = guion.ejecutar(app, _plan_lectura(creada))
    (fila,) = informe['cargas']
    assert fila['nodo']['nombre'] == 'NODE_T_N1' and fila['kw'] == pytest.approx(80.0)
    informe, _rc = guion.ejecutar(app, {'project': 'P', 'feeders': ['F1'], 'cargas': []})
    (fila,) = informe['cargas']
    assert fila['sed'] == 'N1' and fila['solo_en_digsilent'] and fila['nodo']['nombre'] == 'NODE_T_N1'
    assert guion.sin_copia('SECA0001(2)') == 'SECA0001' and guion.sin_copia('SE(1)A') == 'SE(1)A'


def test_el_guion_responde_a_help_sin_digsilent(guion, capsys):
    """017:RF-124; 009:RF-6 — la herramienta dice para qué sirve sin conectar con DIgSILENT."""
    with pytest.raises(SystemExit) as fin:
        guion.main(['--help'])
    assert fin.value.code == 0 and 'sin escribir' in capsys.readouterr().out


# --------------------------------------------------------------------------- diferencias y puntos de diseño
GUARDADA = {'sed': 'SE1', 'alimentador': 'AL1', 'barra': 'N1', 'lat': -13.5, 'lon': -76.0, 'distancia_m': 120.0,
            'kw': 500.0, 'sola': True, 'variacion': 'Carga_SE1_AL1_1'}
LEIDA = {'sed': 'SE1', 'alimentador': 'AL1', 'variacion': 'Carga_SE1_AL1_1', 'punto': [-13.5, -76.0], 'kw': 500.0,
         'nodo': {'nombre': 'N1', 'gps': [-13.501, -76.0]},
         'enlace': {'nombre': 'LNE_SE1', 'km': 0.12, 'gps': [[-13.501, -76.0], [-13.5, -76.0]]}}


def test_comparar_dice_que_cambio_en_digsilent():
    """017:RF-124 — igual, nodo distinto, enlace más largo, punto movido, solo en DIgSILENT y no leída."""
    from convertersmartgrid.mapa_cargas import comparar

    (igual,) = comparar([GUARDADA], [LEIDA])
    assert igual['estado'] == 'igual' and igual['cambios'] == []
    movida = {**LEIDA, 'punto': [-13.5009, -76.0], 'nodo': {'nombre': 'N7', 'gps': [-13.502, -76.0]},
              'enlace': {**LEIDA['enlace'], 'km': 0.3}}
    (cambio,) = comparar([GUARDADA], [movida])
    assert cambio['estado'] == 'cambiada'
    assert cambio['cambios'][0] == 'nodo de conexión N1 → N7'
    assert 'enlace de 0.120 km → 0.300 km' in cambio['cambios'] and any('movido 100 m' in c for c in cambio['cambios'])
    filas = {f['sed']: f for f in comparar([GUARDADA], [{**LEIDA, 'sed': 'SE9'}])}
    assert filas['SE9']['estado'] == 'solo_en_digsilent' and filas['SE1']['estado'] == 'no_leida'
    (sin_enlace,) = comparar([GUARDADA], [{**LEIDA, 'enlace': None}])
    assert sin_enlace['cambios'] == ['sin línea de enlace']


def test_el_punto_confirmado_lo_usan_las_cargas_aplicadas(tmp_path):
    """017:RF-124 — guardado en el espacio, la barra pasa a ser el nodo leído y la de la aplicación queda aparte;
    aplicarlo dos veces no cambia nada."""
    from convertersmartgrid.mapa_cargas import aplicar_puntos, guardar_puntos, leer_puntos, ruta_puntos

    movida = {**LEIDA, 'nodo': {'nombre': 'N7', 'gps': [-13.502, -76.0]}, 'punto': [-13.4999, -76.0]}
    (guardado,) = guardar_puntos(tmp_path, 'PRY', [movida], lectura='ubicacion_cargas_0123456789ab.json')
    assert guardado['barra'] == 'N7' and ruta_puntos(tmp_path, 'PRY').is_file()
    assert set(leer_puntos(tmp_path, 'PRY')) == {'al1|se1'}
    (una,) = aplicar_puntos(tmp_path, 'PRY', [GUARDADA])
    assert una['barra'] == 'N7' and una['barra_aplicada'] == 'N1' and una['nodo_gps'] == [-13.502, -76.0]
    assert (una['lat'], una['lon']) == (-13.4999, -76.0) and una['distancia_m'] == pytest.approx(120.0)
    assert aplicar_puntos(tmp_path, 'PRY', [una]) == [una]
    assert aplicar_puntos(tmp_path, 'OTRO', [GUARDADA]) == [GUARDADA]
    ruta_puntos(tmp_path, 'PRY').write_text('{roto', encoding='utf-8')
    assert aplicar_puntos(tmp_path, 'PRY', [GUARDADA]) == [GUARDADA]


GEO = {'cabecera': 'CAB', 'barras': [['CAB', -13.49, -76.01, 1.0, 10.0], ['N1', -13.501, -76.0, 0.98, 10.0]],
       'tramos': [['L1', [[-13.49, -76.01], [-13.501, -76.0]], 40.0, 'CAB', 'N1', 'AAAC', 1.5],
                  ['LNE_SE1', [[-13.501, -76.0], [-13.5, -76.0]], 5.0, 'N1', 'NODE_SE1', 'AAAC', 0.12]]}


def test_datos_del_mapa_con_la_geografia_guardada(tmp_path, monkeypatch):
    """017:RF-109, 017:RF-124 — red del alimentador, carga en su punto, nodo con su GPS y el enlace de la geografía; sin
    CRS en el perfil, sin UTM (P13); un punto confirmado después del flujo pide repetir 4.2."""
    from convertersmartgrid import mapa_cargas as mc

    monkeypatch.setenv('CSG_SALIDA_TESELAS', '0')
    datos = mc.datos_del_mapa('PRY', [GUARDADA, {**GUARDADA, 'sed': 'SE2', 'sola': False}], {'AL1': GEO},
                              utm=lambda _p: None, flujo_epoca={'AL1': time.time()})
    assert set(datos['alimentadores']) == {'AL1'} and len(datos['alimentadores']['AL1']['tramos']) == 2
    uno = datos['cargas'][0]
    assert uno['nodo'] == {'nombre': 'N1', 'lat': -13.501, 'lon': -76.0, 'utm': None}
    assert uno['enlace']['nombre'] == 'LNE_SE1' and uno['enlace']['km'] == 0.12 and uno['corregida'] is False
    assert datos['cargas'][1]['sola'] is False and datos['repetir_flujos'] == []
    assert datos['fondo']['encendido'] is False and 'CSG_SALIDA_TESELAS' in datos['fondo']['motivo']
    mc.guardar_puntos(tmp_path, 'PRY', [{**LEIDA, 'nodo': {'nombre': 'N9', 'gps': [-13.6, -76.1]}}])
    con_punto = mc.aplicar_puntos(tmp_path, 'PRY', [GUARDADA])
    datos = mc.datos_del_mapa('PRY', con_punto, {'AL1': GEO}, utm=lambda p: [1.0, 2.0], flujo_epoca={'AL1': 0.0})
    (c,) = datos['cargas']
    assert c['corregida'] and c['nodo']['nombre'] == 'N9' and c['nodo']['lat'] == -13.6 and c['nodo']['utm'] == [1.0, 2.0]
    assert datos['repetir_flujos'] == ['AL1'] and any('repita los flujos de 4.2' in a for a in datos['avisos'])
    sin_geo = mc.datos_del_mapa('PRY', [GUARDADA], {}, utm=lambda _p: None)
    assert any('no hay un flujo' in a for a in sin_geo['avisos'])


def test_la_pagina_del_mapa_lleva_leaflet_dentro_y_los_fondos_solo_si_se_permiten(monkeypatch):
    """017:RF-124; 086:RF-63, 086:RF-65 — la página lleva Leaflet dentro; con la salida apagada no nombra ninguna
    tesela y lo dice; encendida, calles y satélite; un nombre con «</script>» no cierra el guion."""
    from convertersmartgrid import mapa_cargas as mc
    from convertersmartgrid.preview import ORIGEN_SATELITE

    datos = {'project': 'PRY', 'alimentadores': {'AL1': {'tramos': [['L1', [[-13.49, -76.01], [-13.5, -76.0]]]],
                                                         'cabecera': None}},
             'cargas': [{'sed': 'X</script><b>', 'alimentador': 'AL1', 'kw': 5, 'sola': True,
                         'punto': {'lat': -13.5, 'lon': -76.0, 'utm': None},
                         'nodo': {'nombre': 'N1', 'lat': -13.5, 'lon': -76.0, 'utm': None}, 'enlace': None,
                         'corregida': False}], 'avisos': [], 'repetir_flujos': []}
    monkeypatch.setenv('CSG_SALIDA_TESELAS', '0')
    apagada = mc.pagina_del_mapa(datos)
    assert 'L.map(' in apagada and 'tile.openstreetmap' not in apagada and 'Sin fondo de mapa' in apagada
    assert 'X</script>' not in apagada and 'X\\u003c/script>' in apagada
    monkeypatch.setenv('CSG_SALIDA_TESELAS', '1')
    encendida = mc.pagina_del_mapa(datos)
    assert 'tile.openstreetmap.org' in encendida and ORIGEN_SATELITE in encendida and 'L.control.layers' in encendida


# --------------------------------------------------------------------------- imagen del informe con fondo
def _png(color) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', (256, 256), color).save(buf, 'PNG')
    return buf.getvalue()


class _Fondo:
    nombre, atribucion, zoom_max = 'OpenStreetMap (calles)', '© OpenStreetMap', 19

    def __init__(self, datos):
        self.datos, self.pedidas = datos, []

    def tesela(self, z, x, y):
        self.pedidas.append((z, x, y))
        return self.datos


def test_la_imagen_de_ubicacion_con_fondo_de_calles(tmp_path):
    """017:RF-111, 017:RF-109 — con el fondo, las teselas quedan debajo de la red y el pie nombra el fondo y su
    atribución; con un nodo corregido que la geografía no tiene, se marca en su GPS."""
    from convertersmartgrid.mapa_informe import ubicacion_del_cliente

    fondo = _Fondo(_png((10, 200, 10)))
    ruta = ubicacion_del_cliente({'AL1': GEO}, 'AL1', 'N1', 'Carga-X-100 kW-Cod N1', tmp_path / 'u.png',
                                 titulo='Ubicación', fondo=fondo)
    with Image.open(ruta) as img:
        assert img.info['pie'] == 'Fondo de mapa: OpenStreetMap (calles) (© OpenStreetMap)'
        assert (10, 200, 10) in {c for _n, c in img.getcolors(1 << 20)}
    assert fondo.pedidas and 0 < len(fondo.pedidas) <= 64 and all(z <= 19 for z, _x, _y in fondo.pedidas)
    otra = ubicacion_del_cliente({'AL1': GEO}, 'AL1', 'N_NUEVO', 't', tmp_path / 'v.png', titulo='v',
                                 punto=(-13.6, -76.1))
    assert otra.is_file()


def test_sin_red_o_sin_salida_la_imagen_sale_sin_fondo_y_lo_dice(tmp_path):
    """017:RF-112, 017:RF-111 — si no llega ninguna tesela, sin fondo y el pie dice a cuál no se llegó; sin salida,
    el pie dice por qué; nunca un error."""
    from convertersmartgrid.mapa_informe import PIE_SIN_FONDO, ubicacion_del_cliente

    ruta = ubicacion_del_cliente({'AL1': GEO}, 'AL1', 'N1', 't', tmp_path / 'u.png', titulo='u', fondo=_Fondo(None))
    with Image.open(ruta) as img:
        assert img.info['pie'].startswith(PIE_SIN_FONDO) and 'No se pudo llegar a OpenStreetMap' in img.info['pie']
    ruta = ubicacion_del_cliente({'AL1': GEO}, 'AL1', 'N1', 't', tmp_path / 'w.png', titulo='w',
                                 sin_fondo='La salida está apagada.')
    with Image.open(ruta) as img:
        assert img.info['pie'] == f'{PIE_SIN_FONDO}. La salida está apagada.'


def test_proveedor_de_teselas_con_cache_y_sin_insistir_sin_red(tmp_path, monkeypatch):
    """017:RF-111, 017:RF-112; 086:RF-22 — trae del origen de la vista previa y guarda en el espacio; sin red, una sola
    petición y ``None``; con la salida apagada no pide nada."""
    from convertersmartgrid import mapa_cargas as mc

    monkeypatch.setenv('CSG_SALIDA_TESELAS', '1')
    pedidas = []

    def pedir(url, _t):
        pedidas.append(url)
        return b'png'

    fondo, motivo = mc.fondo_del_informe(tmp_path, 'calles', pedir=pedir)
    assert motivo == '' and fondo.tesela(15, 100, 200) == b'png' and fondo.tesela(15, 100, 200) == b'png'
    assert pedidas == ['https://a.tile.openstreetmap.org/15/100/200.png']
    assert (tmp_path / mc.CARPETA_TESELAS / 'calles' / '15' / '100' / '200.png').read_bytes() == b'png'
    sat, _m = mc.fondo_del_informe(tmp_path, 'satelite', pedir=pedir)
    sat.tesela(3, 1, 2)
    assert pedidas[-1].endswith('/World_Imagery/MapServer/tile/3/2/1') and sat.zoom_max == 18

    def sin_red(_url, _t):
        pedidas.append('fallo')
        raise OSError('sin red')

    caido, _m = mc.fondo_del_informe(None, 'calles', pedir=sin_red)
    assert caido.tesela(1, 0, 0) is None and caido.tesela(1, 1, 0) is None and pedidas.count('fallo') == 1
    assert caido.fallos == ['OSError: sin red']
    monkeypatch.setenv('CSG_SALIDA_TESELAS', '0')
    apagado, motivo = mc.fondo_del_informe(tmp_path, 'calles', pedir=sin_red)
    assert apagado is None and 'CSG_SALIDA_TESELAS' in motivo
    with pytest.raises(ValueError):
        mc.fondo_del_informe(tmp_path, 'google')


# --------------------------------------------------------------------------- rutas de la web
@pytest.fixture()
def web(tmp_path, monkeypatch):
    """Las rutas del mapa en una aplicación con el almacén de espacios y una cola que corre en el acto."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from convertersmartgrid.web import services
    from convertersmartgrid.web.jobs import Job, JobContext
    from convertersmartgrid.web.mapa_cargas_api import registrar_rutas_mapa
    from convertersmartgrid.web.requisitos import UserError
    from convertersmartgrid.web.workspace import WorkspaceStore

    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(tmp_path / 'sin_perfil.json'))
    monkeypatch.setenv('CSG_SALIDA_TESELAS', '0')
    monkeypatch.setattr(services, 'carpeta_de', lambda _ws, _p=None: 'carpeta')
    store = WorkspaceStore(tmp_path / 'web')
    app = FastAPI()

    @app.exception_handler(UserError)
    async def _error(_r, exc):
        return JSONResponse(status_code=400, content={'detail': str(exc)})

    hechos = []

    def submit(ws, kind, title, fn, *, lane='engine'):
        job = Job(kind, title, ws.id, lane, fn)
        ctx = JobContext(job, lambda *_a: None)
        job.result, job.status = fn(ctx), 'done'
        hechos.append(job)
        return job.public()

    registrar_rutas_mapa(app, ws_or_404=store.get, submit=submit)
    with TestClient(app) as cliente:
        yield cliente, store, hechos


def _espacio_con_carga(store) -> object:
    """Lo que dejan el paso 3 y un flujo de «Con proyecto»: la carga aplicada, su plan y la geografía."""
    ws = store.create()
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    (ws.out_dir / 'estudio_con_flujo_b.json').write_text(json.dumps({
        'project': 'PRY', 'medidas': {'AL1': {'converge': True}}, 'geo': {'AL1': GEO}}), encoding='utf-8')
    (ws.out_dir / 'cargas_pf_aplicacion_tok1.json').write_text(json.dumps({
        'project': 'PRY', 'cargas': [{'sed': 'SE1', 'alimentador': 'AL1', 'barra': 'N1',
                                      'variacion': 'Carga_SE1_AL1_1', 'distancia_m': 120.0}]}), encoding='utf-8')
    ws.plans_dir.mkdir(parents=True, exist_ok=True)
    (ws.plans_dir / 'cargas_pf_tok1.json').write_text(json.dumps({'nuevas': [
        {'sed': 'SE1', 'hoja': 'formulario', 'alimentador': 'AL1', 'kw': 500.0, 'lat': -13.5, 'lon': -76.0}]}),
        encoding='utf-8')
    return ws


def test_rutas_del_mapa_actualizar_y_usar_el_punto(web, monkeypatch):
    """017:RF-109, 017:RF-124 — los datos y la página salen de lo guardado; «Actualizar desde DIgSILENT» es un
    trabajo del carril de DIgSILENT con las diferencias; «Usar este punto» lo guarda y desde entonces el mapa lo usa y
    pide repetir 4.2; una lectura que no es de ese proyecto, o un nombre de fichero cualquiera, no se acepta."""
    from convertersmartgrid.web import services

    cliente, store, hechos = web
    ws = _espacio_con_carga(store)
    base = f'/api/workspaces/{ws.id}/mapa-cargas'
    datos = cliente.get(base, params={'project': 'PRY'}).json()
    assert [c['nodo']['nombre'] for c in datos['cargas']] == ['N1'] and datos['cargas'][0]['sola'] is True
    pagina = cliente.get(f'{base}/pagina', params={'project': 'PRY'})
    assert pagina.status_code == 200 and 'sandbox' in pagina.headers['content-security-policy']
    assert 'L.map(' in pagina.text

    planes = []

    def guion_pf(ws_, _ctx, script, plan, *, nombre, cancelable=True, **_k):
        planes.append((script, plan, cancelable))
        report = ws_.out_dir / f'{nombre}_0123456789ab.json'
        informe = {'project': plan['project'], 'caso': 'Con proyecto', 'avisos': [],
                   'cargas': [{**LEIDA, 'nodo': {'nombre': 'N7', 'gps': [-13.502, -76.0]}}]}
        report.write_text(json.dumps(informe), encoding='utf-8')
        return 0, informe, report

    monkeypatch.setattr(services, '_guion_pf', guion_pf)
    job = cliente.post(f'{base}/digsilent', json={'project': 'PRY'})
    assert job.status_code == 202 and job.json()['lane'] == 'powerfactory'
    script, plan, cancelable = planes[0]
    assert script == 'ubicacion_cargas_pf.py' and plan['folder'] == 'carpeta' and plan['feeders'] == ['AL1']
    assert plan['cargas'] == [{'sed': 'SE1', 'alimentador': 'AL1', 'variacion': 'Carga_SE1_AL1_1'}]
    resultado = hechos[-1].result
    (dif,) = resultado['diferencias']
    assert dif['estado'] == 'cambiada' and dif['cambios'][0] == 'nodo de conexión N1 → N7'

    malo = cliente.post(f'{base}/confirmar', json={'project': 'PRY', 'lectura': '../workspace.json',
                                                    'cargas': [{'alimentador': 'AL1', 'sed': 'SE1'}]})
    assert malo.status_code == 400
    otro = cliente.post(f'{base}/confirmar', json={'project': 'OTRO', 'lectura': resultado['lectura'],
                                                    'cargas': [{'alimentador': 'AL1', 'sed': 'SE1'}]})
    assert otro.status_code == 400 and 'PRY' in otro.json()['detail']
    ok = cliente.post(f'{base}/confirmar', json={'project': 'PRY', 'lectura': resultado['lectura'],
                                                  'cargas': [{'alimentador': 'AL1', 'sed': 'SE1'}]})
    assert ok.status_code == 200 and ok.json()['repetir_flujos'] == ['AL1'] and '4.2' in ok.json()['aviso']
    despues = cliente.get(base, params={'project': 'PRY'}).json()
    (c,) = despues['cargas']
    assert c['corregida'] and c['nodo']['nombre'] == 'N7' and c['barra_aplicada'] == 'N1'
    assert despues['repetir_flujos'] == ['AL1']
    # Lo guardado es del espacio: nada de lo leído se escribe en otro sitio.
    assert Path(ws.root / 'puntos_de_diseno' / 'PRY.json').is_file()


def test_la_carga_que_solo_esta_en_digsilent_se_da_de_alta_como_sola(web):
    """017:RF-124 ampliada — SECA0001 (2026-11-13) estaba en DIgSILENT y no en la web: «Dar de alta» la deja como carga
    aplicada y sola, con su potencia, su punto, su nodo y su enlace, y el informe de factibilidad ya la encuentra. Una
    carga que la web ya tiene, o sin nodo, no se da de alta."""
    from convertersmartgrid.web import services

    cliente, store, _hechos = web
    ws = _espacio_con_carga(store)
    lectura = 'ubicacion_cargas_0123456789ab.json'
    (ws.out_dir / lectura).write_text(json.dumps({'project': 'PRY', 'cargas': [
        {'sed': 'SE2', 'alimentador': 'AL1', 'variacion': 'Carga_SE2_AL1_2', 'solo_en_digsilent': True,
         'punto': [-13.53, -76.03], 'kw': 1287.0, 'kvar': 261.3,
         'nodo': {'nombre': 'N9', 'gps': [-13.51, -76.05]}, 'enlace': {'nombre': 'LNE_SE2', 'km': 3.910834}},
        {'sed': 'SE1', 'alimentador': 'AL1', 'variacion': 'Carga_SE1_AL1_1', 'solo_en_digsilent': False,
         'nodo': {'nombre': 'N1'}, 'kw': 500.0},
        {'sed': 'SE3', 'alimentador': 'AL1', 'solo_en_digsilent': True, 'kw': 10.0}]}), encoding='utf-8')
    base = f'/api/workspaces/{ws.id}/mapa-cargas'
    for sed in ('SE1', 'SE3'):
        r = cliente.post(f'{base}/alta', json={'project': 'PRY', 'lectura': lectura,
                                               'cargas': [{'alimentador': 'AL1', 'sed': sed}]})
        assert r.status_code == 400, (sed, r.text)
    r = cliente.post(f'{base}/alta', json={'project': 'PRY', 'lectura': lectura,
                                           'cargas': [{'alimentador': 'AL1', 'sed': 'SE2'}]})
    assert r.status_code == 200, r.text and r.json()['altas'] == ['SE2']
    carga = services.carga_del_informe(ws, 'PRY', 'AL1', 'SE2')
    assert carga['sola'] is True and carga['barra'] == 'N9' and carga['kw'] == 1287.0
    assert carga['distancia_m'] == pytest.approx(3910.8) and (carga['lat'], carga['lon']) == (-13.53, -76.03)
