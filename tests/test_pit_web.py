"""Spec 107 T13 — rutas propias del PIT, con el diagnóstico como trabajo en cola (107:RF-1, RF-3, RF-5, RF-10).

La app de la prueba registra solo este router (``web/app.py`` no se toca en la T13). La cola es un doble que ejecuta
el trabajo al momento con su progreso y su cancelación."""
from __future__ import annotations

import json
import threading

import openpyxl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from datos_pit import perfil_a, perfil_b

from convertersmartgrid.web.rutas_pit import crear_router


class _Ctx:
    def __init__(self):
        self.cancel, self.avance = threading.Event(), []

    def progress(self, i, n, texto=''):
        self.avance.append((i, n, texto))


class _Cola:
    def __init__(self):
        self.trabajos = []

    def submit(self, ws, kind, title, fn, *, lane='engine'):
        ctx = _Ctx()
        self.trabajos.append({'kind': kind, 'lane': lane, 'resultado': fn(ctx), 'ctx': ctx})
        return type('Job', (), {'id': f'j{len(self.trabajos)}'})()


def _cliente(tmp_path, caso, normativa=None, fuentes=None):
    claves = sorted({k for e in caso['elementos'] for k in e})
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Red'
    ws.append(claves)
    for e in caso['elementos']:
        ws.append([', '.join(e[k]) if isinstance(e.get(k), list) else e.get(k) for k in claves])
    espacio = tmp_path / 'ws1'
    espacio.mkdir()
    wb.save(espacio / 'red.xlsx')
    (espacio / 'proyeccion.json').write_text(json.dumps(caso['proyeccion']), encoding='utf-8')
    perfil = {**caso['perfil']}
    perfil['pit'] = {**perfil['pit'], 'libro_red': {'hoja': 'Red', 'columnas': {k: k for k in claves}},
                     'limites': {'tension_min_pu': 0.9, 'tension_max_pu': 1.1, 'cargabilidad_max_pct': 100}}
    if normativa is None:
        normativa = tmp_path / 'normativa'
        normativa.mkdir()
        (normativa / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': []}),
                                          encoding='utf-8')
    cola = _Cola()
    app = FastAPI()
    app.include_router(crear_router(cola, lambda ws: tmp_path / ws, lambda: perfil, normativa,
                                    fuentes=lambda: fuentes))
    return TestClient(app), cola


def test_diagnostico_en_cola_con_progreso(tmp_path):
    """107:RF-3 — el diagnóstico es un trabajo del carril engine, con progreso por año y su salida en el PIT."""
    caso = perfil_b(15)
    cliente, cola = _cliente(tmp_path, caso)
    r = cliente.post('/api/pit/diagnostico', json={'workspace_id': 'ws1', 'area': caso['area'],
                                                   'anios': caso['anios'], 'libro_red': 'red.xlsx',
                                                   'proyeccion': 'proyeccion.json'})
    assert r.status_code == 200 and r.json()['job'] == 'j1'
    t = cola.trabajos[0]
    assert t['lane'] == 'engine' and len(t['ctx'].avance) == len(caso['anios'])
    assert 'expedientes_pit' in t['resultado']['salida'] and t['resultado']['completo'] is False


def test_rutas_propias_capacidades_y_areas(tmp_path):
    """107:RF-1, 107:RF-5 — /api/pit da las áreas del perfil y la matriz de motores sin licencia."""
    caso = perfil_b(15)
    cliente, _ = _cliente(tmp_path, caso)
    assert caso['area'] in [a['codigo'] for a in cliente.get('/api/pit/areas').json()['areas']]
    matriz = cliente.get('/api/pit/capacidades').json()
    assert matriz['licencia'] is False
    cc = next(m for m in matriz['matriz'] if m['motor'] == 'abierto' and m['estudio'] == 'cortocircuito')
    assert cc['alcance'] == 'no_disponible'
    r = cliente.post('/api/pit/diagnostico', json={'workspace_id': 'ws1', 'area': caso['area'], 'anios': [1],
                                                   'libro_red': 'red.xlsx', 'proyeccion': 'proyeccion.json',
                                                   'motor': 'digsilent'})
    assert r.status_code == 422 and 'licencia' in r.json()['detail']


def test_fuera_del_espacio_y_observaciones(tmp_path):
    """107:RF-10 — las observaciones se registran por la web; una ruta fuera del espacio se rechaza."""
    caso = perfil_b(15)
    cliente, _ = _cliente(tmp_path, caso)
    r = cliente.post('/api/pit/diagnostico', json={'workspace_id': 'ws1', 'area': caso['area'], 'anios': [1],
                                                   'libro_red': '../../fuera.xlsx', 'proyeccion': 'proyeccion.json'})
    assert r.status_code == 400
    elem = caso['pistas']['compartida']
    r = cliente.post('/api/pit/observaciones', json={
        'workspace_id': 'ws1', 'expediente': 'expedientes_pit/x',
        'observaciones': [{'numero': '1', 'fecha': '2031-01-01', 'texto': 'Asigne el compartido', 'afecta': 'elemento',
                           'referencia': elem, 'respuesta': 'Hecho'}],
        'referencias': {'elemento': {elem: {}}}})
    assert r.status_code == 200 and r.json()['observaciones'] == 1


# --- Expediente por la web (107-P10c) ---------------------------------------------------------------------------------

def _pedido(caso, **cambios):
    return {'workspace_id': 'ws1', 'area': caso['area'], 'periodo': '2025-2029', 'anios': caso['anios'][:2],
            'libro_red': 'red.xlsx', 'proyeccion': 'proyeccion.json', **cambios}


def test_expediente_en_cola_de_punta_a_punta(tmp_path):
    """107:RF-1, RF-9 y RF-14 (P10c) — POST /api/pit/expediente encola el armado en el carril engine, con progreso
    por pasos, y deja el expediente en el espacio; sin alternativas sale «DE DIAGNÓSTICO, no presentable a
    Osinergmin» con su pendiente, y sin carpeta de fuentes dice por qué no hay libro F-000."""
    from test_pit_formatos import NORMATIVA
    caso = perfil_a(27)
    cliente, cola = _cliente(tmp_path, caso, normativa=NORMATIVA)
    r = cliente.post('/api/pit/expediente', json=_pedido(caso))
    assert r.status_code == 200, r.text
    assert r.json()['job'] == 'j1'
    t = cola.trabajos[0]
    assert t['kind'] == 'pit_expediente' and t['lane'] == 'engine' and len(t['ctx'].avance) == 6
    resultado = t['resultado']
    assert resultado['tipo'] == 'DE DIAGNÓSTICO, no presentable a Osinergmin' and resultado['estado'] == 'incompleto'
    assert 'sin alternativas: no hay comparación ni programa' in {p['causa'] for p in resultado['pendientes']}
    assert 'CSG_FUENTES_NORMATIVAS' in resultado['libro_f000']['motivo']
    assert (tmp_path / 'ws1' / 'expedientes_pit' / caso['area'] / '2025-2029' / 'resumen.json').is_file()


def test_expediente_rechaza_antes_de_encolar(tmp_path):
    """Aclaración de 107:RF-5 (P10c) — lo que se puede comprobar antes no se encola: un JSON de alternativas mal
    formado da 422 con el campo, una alternativa elegida que no está da 422, un fichero que falta da 422 y una ruta
    fuera del espacio da 400."""
    from test_pit_formatos import NORMATIVA
    caso = perfil_a(27)
    cliente, cola = _cliente(tmp_path, caso, normativa=NORMATIVA)
    (tmp_path / 'ws1' / 'alternativas.json').write_text(json.dumps({'alternativas': [
        {'nombre': 'x', 'cambios': [{'accion': 'baja', 'elemento': 'L-1', 'anio': 'dos mil', 'titular': 't',
                                     'instalacion': 'i', 'descripcion': 'd'}]}]}), encoding='utf-8')
    r = cliente.post('/api/pit/expediente', json=_pedido(caso, alternativas='alternativas.json',
                                                         alternativa_elegida='x'))
    assert r.status_code == 422 and 'alternativas[0].cambios[0].anio' in r.json()['detail']
    (tmp_path / 'ws1' / 'alternativas.json').write_text(json.dumps({'alternativas': [
        {'nombre': 'x', 'cambios': [{'accion': 'baja', 'elemento': 'L-1', 'anio': 2030, 'titular': 't',
                                     'instalacion': 'i', 'descripcion': 'd'}]}]}), encoding='utf-8')
    r = cliente.post('/api/pit/expediente', json=_pedido(caso, alternativas='alternativas.json',
                                                         alternativa_elegida='otra'))
    assert r.status_code == 422 and 'alternativa_elegida' in r.json()['detail']
    r = cliente.post('/api/pit/expediente', json=_pedido(caso, proyeccion='no_esta.json'))
    assert r.status_code == 422 and 'proyeccion' in r.json()['detail']
    r = cliente.post('/api/pit/expediente', json=_pedido(caso, libro_red='../../fuera.xlsx'))
    assert r.status_code == 400
    assert cola.trabajos == []


def test_alternativa_elegida_sin_alternativas_es_un_error(tmp_path):
    """Aclaración de 107:RF-5 (P10c) — una alternativa elegida sin el JSON de alternativas no se ignora en silencio:
    da 422 con el campo y el motivo, y no se encola nada."""
    from test_pit_formatos import NORMATIVA
    caso = perfil_a(27)
    cliente, cola = _cliente(tmp_path, caso, normativa=NORMATIVA)
    r = cliente.post('/api/pit/expediente', json=_pedido(caso, alternativa_elegida='refuerzo'))
    assert r.status_code == 422, r.text
    assert r.json()['detail'] == 'alternativa_elegida: hay alternativa elegida y no hay alternativas'
    assert cola.trabajos == []


# --- El panel del PIT en la web (107 T13, P10d) -----------------------------------------------------------------------

def test_107_t13_entradas_admite_los_cuatro_formatos_de_excel(tmp_path):
    """107 T13 (lector común) — el libro de la red sube en .xlsx, .xlsm, .xls y .xlsb: los cuatro que lee calamine."""
    caso = perfil_b(15)
    cliente, _ = _cliente(tmp_path, caso)
    for ext in ('.xlsx', '.xlsm', '.xls', '.xlsb'):
        r = cliente.post('/api/pit/entradas', data={'workspace_id': 'ws1'},
                         files=[('files', (f'red{ext}', b'PK', 'application/octet-stream'))])
        assert r.status_code == 200, (ext, r.text)
        assert r.json()['rutas'] == [f'entradas_pit/red{ext}']


def test_107_t13_los_resultados_traen_sus_rutas_dentro_del_espacio(tmp_path):
    """107 T13 (P10d) — el panel descarga lo que deja el trabajo y pide las observaciones de su expediente: el
    diagnóstico y el expediente devuelven sus rutas relativas al espacio, con «/»."""
    from test_pit_formatos import NORMATIVA
    caso = perfil_b(15)
    cliente, cola = _cliente(tmp_path, caso)
    cliente.post('/api/pit/diagnostico', json={'workspace_id': 'ws1', 'area': caso['area'], 'anios': caso['anios'],
                                               'libro_red': 'red.xlsx', 'proyeccion': 'proyeccion.json'})
    assert cola.trabajos[0]['resultado'].get('salida_relativa') == \
        f"expedientes_pit/{caso['area']}/diagnostico_de_trabajo.json"
    caso = perfil_a(27)
    otro = tmp_path / 'b'
    otro.mkdir()
    cliente, cola = _cliente(otro, caso, normativa=NORMATIVA)
    r = cliente.post('/api/pit/expediente', json=_pedido(caso))
    assert r.status_code == 200, r.text
    res = cola.trabajos[0]['resultado']
    assert res.get('carpeta_relativa') == f"expedientes_pit/{caso['area']}/2025-2029"
    assert res.get('salidas_relativas') and all(not v.startswith(('/', '.')) and '\\' not in v and ':' not in v
                                                for v in res['salidas_relativas'].values())
    assert set(res['salidas_relativas']) == set(res['salidas'])
