"""087:RF-21 a RF-27 — cuánto mejora una versión: la fila de cada corrida, las normas y la comparación."""
from __future__ import annotations

import json

from apoyo import cargar_herramienta

from convertersmartgrid import medicion_obras as mo
from convertersmartgrid.web import services


def _resultado():
    tabla = [{'nombre': 'sección AA24003D_22_9kV_FICHA en 3 tramos hasta X (2.50 km) + terna hasta X (2.50 km)', 'u_min_mt': 0.97, 'carga_max_pct': 70.0,
              'inversion': 100.0, 'costo_anual': 20.0, 'perdidas_kw': 5.0, 'valle': True},
             {'nombre': 'otra', 'u_min_mt': 0.5}]
    bancos = {'nombre': 'bancos 1×450 kvar', 'u_min_mt': 0.93, 'carga_max_pct': 95.0, 'inversion': 8.0, 'costo_anual': 2.0, 'perdidas_kw': 1.0, 'valle': False}
    return {'escalera_por_cargas': {
        'por_alimentador': {'F1': {'cumple': True}, 'F2': {'cumple': True}, 'F3': {'cumple': False}},
        'escalera': {'alimentadores': [
            {'alimentador': 'F1', 'elegida': tabla[0]['nombre'], 'tabla': tabla, 'aplicada': ['Obra_seccion_F1', 'Obra_terna_F1'],
             'coordenadas': [{'elemento': 'L', 'puntos': [{'lat': -13.0}]}], 'instalaciones': [{'avisos': []}]},
            {'alimentador': 'F2', 'elegida': bancos['nombre'], 'tabla': [bancos], 'aplicada': ['Obra_condensador_F2']}]}},
        'set_nueva': {'zonas': [{'solucion': 'set_nueva', 'ubicacion_final': {'cumple': True}}, {'solucion': 'expreso'}],
                      'obras': [{'clase': 'set_nueva'}, {'clase': 'expreso'}]}}


def _fila(metodo='oraculo', tiempo=100.0, **k):
    ordenes = [{'segundos': 10.0, 'codigo': 0}, {'segundos': 5.0, 'codigo': 1}]
    return mo.fila_de_corrida(sistema='S', revision='abc', metodo=metodo, estado='done', resultado=_resultado(), tiempo_s=tiempo,
                              ordenes=ordenes, oraculo={'flujos': 500, 'oraculo_s': 3.0}, memoria_mb=120.0, carga_max=80.0,
                              secciones=('AA24003D', 'AA12003D'), **k)


def test_la_fila_dice_lo_que_costo():
    """087:RF-21 — sistema, revisión, método, tiempos, flujos, órdenes y memoria."""
    f = _fila()
    assert (f['sistema'], f['revision'], f['metodo']) == ('S', 'abc', 'oraculo')
    assert f['tiempo_s'] == 100.0 and f['oraculo_s'] == 3.0 and f['digsilent_s'] == 15.0
    assert f['flujos_oraculo'] == 500 and f['ordenes'] == 2 and f['ordenes_fallidas'] == 1 and f['memoria_mb'] == 120.0


def test_la_fila_dice_lo_que_dio():
    """087:RF-22 — resueltos, obras por clase, km, inversión, costo, pérdidas, tensión y carga."""
    f = _fila()
    assert f['resueltos'] == 2 and f['sin_resolver'] == 1
    assert f['obras_por_clase'] == {'seccion': 1, 'terna': 1, 'condensador': 1, 'set_nueva': 1, 'expreso': 1} and f['obras'] == 5
    assert f['km'] == 5.0 and f['inversion'] == 108.0 and f['costo_anual'] == 22.0 and f['perdidas_kw'] == 6.0
    assert f['u_min'] == 0.93 and f['carga_max_pct'] == 95.0
    json.dumps(f)


def test_las_normas_cuentan_lo_que_no_cumple_y_lo_que_no_se_midio():
    """087:RF-23, 087:RF-24 — cada norma con cumplen, no cumplen y sin dato: lo no medido no cuenta como cumplido."""
    n = _fila()['normas']
    assert n['tension'] == {'cumplen': 1, 'no_cumplen': 1, 'sin_dato': 0}
    assert n['carga'] == {'cumplen': 1, 'no_cumplen': 1, 'sin_dato': 0}
    assert n['seccion_normalizada']['cumplen'] == 1 and n['valle']['no_cumplen'] == 1
    assert n['ternas']['cumplen'] == 1 and n['set_area_libre']['cumplen'] == 1
    assert n['coordenadas'] == {'cumplen': 1, 'no_cumplen': 0, 'sin_dato': 1}
    otra = mo.comprobar_normas([{'nombre': 'sección CU02503D en 2 tramos', 'aplicada': []}], {}, tension_min=0.95, tension_max=1.05,
                               carga_max=80.0, secciones=('AA24003D',))
    assert otra['seccion_normalizada']['no_cumplen'] == 1 and otra['tension']['sin_dato'] == 1


def test_comparar_da_diferencias_y_no_declara_mejora_con_pocas_corridas():
    """087:RF-25, 087:RF-26 — con menos de 5 por grupo: diferencias observadas, sin contraste."""
    filas = [_fila('escalera', 400.0), _fila('oraculo', 100.0), {**_fila('oraculo', 50.0), 'estado': 'cancelled'}, {**_fila('oraculo'), 'sistema': 'otro'}]
    r = mo.comparar(filas, 'S', 'metodo', 'escalera', 'oraculo')
    assert r['corridas_a'] == 1 and r['corridas_b'] == 1
    assert r['medidas']['tiempo_s']['diferencia'] == -300.0 and r['medidas']['tiempo_s']['porcentaje'] == -75.0
    assert r['contraste'] is None and 'no una mejora demostrada' in r['motivo']
    assert r['normas']['tension']['a']['no_cumplen'] == 1


def test_comparar_con_corridas_contrasta():
    """087:RF-25 — con 5 o más por grupo, el contraste de 081:RF-73 sobre el tiempo y las órdenes fallidas."""
    filas = [_fila('escalera', 400.0 + i) for i in range(6)] + [_fila('oraculo', 100.0 + i) for i in range(6)]
    r = mo.comparar(filas, 'S', 'metodo', 'escalera', 'oraculo')
    assert r['contraste']['tiempo']['demostrado'] and not r['contraste']['ordenes_fallidas']['demostrado']


def test_las_pruebas_de_un_junit(tmp_path):
    """087:RF-27 — aprobadas, fallidas y omitidas."""
    ruta = tmp_path / 'j.xml'
    ruta.write_text('<testsuites><testsuite tests="10" failures="1" errors="1" skipped="2"/></testsuites>', encoding='utf-8')
    assert mo.pruebas_de_junit(ruta) == {'aprobadas': 6, 'fallidas': 2, 'omitidas': 2}
    assert _fila(pruebas=mo.pruebas_de_junit(ruta))['pruebas']['omitidas'] == 2


def test_el_fichero_y_la_herramienta(tmp_path, capsys):
    """087:RF-21, 087:RF-25 — la fila se añade y `tools/medir_mejora.py comparar` la lee."""
    ruta = tmp_path / 'c.jsonl'
    assert mo.leer(ruta) == []
    mo.anadir(ruta, _fila('escalera', 400.0))
    mo.anadir(ruta, _fila('oraculo', 100.0))
    herramienta = cargar_herramienta('medir_mejora.py', 'medir_mejora_prueba')
    assert herramienta.main(['--registro', str(ruta), 'comparar', '--sistema', 'S', '--a', 'escalera', '--b', 'oraculo']) == 0
    salida = capsys.readouterr().out
    assert 'tiempo_s' in salida and 'no una mejora demostrada' in salida


def test_registrar_un_trabajo_ya_terminado(tmp_path, capsys):
    """087:RF-21 — la referencia de un trabajo sin fila: del JSON de la API y de las órdenes de la cola."""
    trabajo = tmp_path / 't.json'
    trabajo.write_text(json.dumps({'status': 'done', 'started_at': 1000.0, 'finished_at': 1100.0, 'result': _resultado()}), encoding='utf-8')
    ruta = tmp_path / 'c.jsonl'
    herramienta = cargar_herramienta('medir_mejora.py', 'medir_mejora_prueba2')
    assert herramienta.main(['--registro', str(ruta), 'registrar', '--trabajo', str(trabajo), '--sistema', 'S', '--metodo', 'escalera',
                             '--revision', 'abc', '--cola', str(tmp_path)]) == 0
    capsys.readouterr()
    fila = mo.leer(ruta)[0]
    assert fila['tiempo_s'] == 100.0 and fila['metodo'] == 'escalera' and fila['resueltos'] == 2


def test_la_web_registra_la_corrida_y_medir_no_la_hace_fallar(monkeypatch, tmp_path):
    """087:RF-21 — cada «Con proyecto» deja su fila; si no se puede escribir, se dice y sigue."""
    monkeypatch.setattr(services, '_ruta_de_medicion', lambda nombre: tmp_path / nombre)

    class Ctx:
        def __init__(self):
            self.textos = []

        def log(self, texto='', *_a, **_k):
            self.textos.append(texto)

    r = _resultado()
    r['escalera_por_cargas'].update(metodo='oraculo', oraculo={'flujos': 9, 'oraculo_s': 1.0})
    services._registrar_corrida(Ctx(), 'P', r, 0.0, '2099-01-01T00:00:00')
    fila = mo.leer(tmp_path / mo.REGISTRO)[0]
    assert fila['metodo'] == 'oraculo' and fila['flujos_oraculo'] == 9 and fila['sistema'] == 'P'
    ctx = Ctx()
    services._registrar_corrida(ctx, 'P', {'escalera_por_cargas': 'roto'}, 0.0, '2099-01-01T00:00:00')
    assert any('087:RF-21' in t for t in ctx.textos)
