"""Spec 107 T13 — rutas propias del PIT, con el diagnóstico como trabajo en cola (107:RF-1, RF-3, RF-5, RF-10).

La app de la prueba registra solo este router (``web/app.py`` no se toca en la T13). La cola es un doble que ejecuta
el trabajo al momento con su progreso y su cancelación."""
from __future__ import annotations

import json
import threading

import openpyxl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from datos_pit import perfil_b

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


def _cliente(tmp_path, caso):
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
    normativa = tmp_path / 'normativa'
    normativa.mkdir()
    (normativa / 'r.json').write_text(json.dumps({'esquema': 'registro_normativo_v1', 'normas': []}),
                                      encoding='utf-8')
    cola = _Cola()
    app = FastAPI()
    app.include_router(crear_router(cola, lambda ws: tmp_path / ws, lambda: perfil, normativa))
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
