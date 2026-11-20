"""026:RF-42 (T16) — el asistente carga las entradas del espacio por las rutas de la web: asigna a una casilla un fichero
de la máquina (por su subida, que lo valida antes de tocar la entrada vigente, 086:RF-3) y sube un libro de las fuentes
de la empresa a su carpeta y a su año (109:RF-25), con la confirmación del operador. De la nube, el fichero lo elige el
operador en el selector (070:RF-81): el plan lo dice y no se ofrece.

Datos sintéticos, de ninguna empresa (P13).
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.aplicacion.asistente import ejecutor, tareas
from convertersmartgrid.aplicacion.asistente.interprete import _por_frase_literal
from convertersmartgrid.presentacion.web import services

ORDENES = ('asignar_entrada', 'subir_fuente_empresa')
_RED_TXT = '[NODE]\nFORMAT_NODE=NodeID,X,Y\nN1,0,0\n[SECTION]\nFORMAT_SECTION=SectionID\n'
_BASE_ACCESS = b'\x00\x01\x00\x00Standard Jet DB\x00' + b'\x00' * 64


def test_026_rf42_las_ordenes_de_las_entradas_escriben_y_se_reconocen():
    """026:RF-42 — asignar una casilla y subir un libro de la empresa están en el catálogo, escriben (esperan la
    confirmación) y se reconocen por su frase mientras el modelo en uso no las conozca."""
    faltan = [t for t in ORDENES if t not in tareas.TAREAS]
    assert faltan == [], f'órdenes de las entradas que el asistente aún no tiene: {faltan}'
    for t in ORDENES:
        assert tareas.EFECTOS[t] == (tareas.ESCRIBE,) and tareas.TAREAS[t].escribe, t
    assert set(ORDENES) | {'repetir_trabajo'} == set(getattr(tareas, 'TAREAS_026_CONTROL', ()))
    assert _por_frase_literal('asigna "D:/datos/red.txt" a la casilla de la red', None) == 'asignar_entrada'
    assert _por_frase_literal('pon D:/datos/c.txt en la entrada de las cargas', None) == 'asignar_entrada'
    assert _por_frase_literal('sube el sicodi D:/libros/s.xlsx del 2025 a las fuentes de la empresa',
                              None) == 'subir_fuente_empresa'
    assert _por_frase_literal('registra el libro de demanda D:/libros/d.xlsx del 2024', None) == 'subir_fuente_empresa'


def test_026_rf42_sus_pasos_van_a_las_rutas_de_la_web(tmp_path):
    """026:RF-42 — la casilla, por su subida (``/inputs/{casilla}``); el libro, por ``/fuentes`` con su clase y su año."""
    assert hasattr(ejecutor, '_pasos_026_rf42'), 'el ejecutor no sabe los pasos de las entradas'
    red = tmp_path / 'red.txt'
    red.write_bytes(_RED_TXT.encode())
    (paso,) = ejecutor.pasos('asignar_entrada', {}, {'entrada': {'casilla': 'red', 'ruta': str(red), 'etiqueta': 'RED'}})
    assert (paso.metodo, paso.ruta) == ('POST', '/inputs/red') and paso.archivos is not None, paso
    assert paso.archivos([])['file'][:2] == ('red.txt', _RED_TXT.encode())
    libro = tmp_path / 'sicodi.xlsx'
    libro.write_bytes(b'libro sintetico')
    (paso,) = ejecutor.pasos('subir_fuente_empresa', {},
                             {'fuente': {'clase': 'sicodi', 'periodo': '2025', 'ruta': str(libro)}})
    assert (paso.metodo, paso.ruta, paso.cuerpo) == ('POST', '/fuentes', {'clase': 'sicodi', 'periodo': '2025'}), paso
    assert paso.archivos([])['file'][0] == 'sicodi.xlsx'


@pytest.fixture
def web(tmp_path, monkeypatch):
    from convertersmartgrid.presentacion.web.app import create_app

    for nombre, valor in (('CSG_ASISTENTE_DATA', tmp_path / 'asistente'), ('CSG_TWIN_DATA', tmp_path / 'gemelo'),
                          ('CSG_WEB_FRONTEND', tmp_path / 'sin_front'), ('CSG_ML_GPU_LOCK', tmp_path / 'gpu.lock')):
        monkeypatch.setenv(nombre, str(valor))
    monkeypatch.setattr(services, '_asistente_modelos', lambda: (None, None))
    services._ASISTENTE_PLANES.clear()
    app = create_app(tmp_path / 'web')
    with TestClient(app) as cliente:
        app.state.asistente_http = cliente
        yield cliente, app
    services._ASISTENTE_PLANES.clear()


def _esperar(cliente, trabajo: dict) -> dict:
    limite = time.monotonic() + 120
    while time.monotonic() < limite:
        r = cliente.get(f"/api/jobs/{trabajo['id']}").json()
        if r['status'] in ('done', 'failed', 'cancelled', 'parcial'):
            return r
        time.sleep(0.05)
    pytest.fail('la cola no terminó')


def _orden(cliente, wid: str, texto: str) -> dict:
    r = cliente.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': texto})
    assert r.status_code == 202, r.text
    fin = _esperar(cliente, r.json())
    assert fin['status'] == 'done', fin.get('error')
    return fin['result']['plan']


def _confirmar(cliente, wid: str, plan: dict) -> dict:
    r = cliente.post(f"/api/workspaces/{wid}/asistente/{plan['id']}/confirmar")
    assert r.status_code == 202, r.text
    return _esperar(cliente, r.json())


def test_026_rf42_asigna_un_fichero_de_la_maquina_a_su_casilla_por_la_web(web, tmp_path):
    """026:RF-42 — «asigna "…/red.txt" a la casilla de la red» espera la confirmación, entra por la subida de la web y
    queda en la casilla; una base Access en esa casilla la rechaza la web y la entrada vigente se queda."""
    cliente, _app = web
    wid = cliente.post('/api/workspaces').json()['id']
    red = tmp_path / 'red sintetica.txt'
    red.write_bytes(_RED_TXT.encode())
    plan = _orden(cliente, wid, f'asigna "{red}" a la casilla de la red')
    assert plan['tarea'] == 'asignar_entrada', plan
    assert plan['listo'] and plan['espera_confirmacion'], plan['faltan']
    fin = _confirmar(cliente, wid, plan)
    assert fin['status'] == 'done', fin.get('error')
    assert 'entró en la casilla' in fin['result']['texto'], fin['result']
    vigente = cliente.get(f'/api/workspaces/{wid}').json()['inputs']['red']['path']
    base = tmp_path / 'base.mdb'
    base.write_bytes(_BASE_ACCESS)
    plan = _orden(cliente, wid, f'asigna "{base}" a la casilla de la red')
    assert plan['tarea'] == 'asignar_entrada' and plan['listo'], plan['faltan']
    fin = _confirmar(cliente, wid, plan)
    assert fin['status'] == 'failed' and 'base Access' in (fin.get('error') or ''), fin
    assert cliente.get(f'/api/workspaces/{wid}').json()['inputs']['red']['path'] == vigente


def test_026_rf42_sin_casilla_sin_fichero_o_de_la_nube_lo_dice_el_plan(web, tmp_path):
    """026:RF-42 — sin la casilla o con un fichero que no está, el plan dice qué falta; de la nube lo elige el operador."""
    cliente, _app = web
    wid = cliente.post('/api/workspaces').json()['id']
    suelto = tmp_path / 'suelto.txt'
    suelto.write_text('x', encoding='utf-8')
    plan = _orden(cliente, wid, f'asigna el fichero "{suelto}" al espacio')
    assert plan['tarea'] == 'asignar_entrada' and not plan['listo'], plan
    assert any('la casilla' in f for f in plan['faltan']), plan['faltan']
    plan = _orden(cliente, wid, f'asigna "{tmp_path / "no_esta.txt"}" a la casilla de las cargas')
    assert not plan['listo'] and any('no está' in f for f in plan['faltan']), plan['faltan']
    plan = _orden(cliente, wid, 'asigna desde google drive el libro a la casilla de la red')
    assert plan['tarea'] == 'asignar_entrada' and not plan['listo'], plan
    assert any('selector' in f for f in plan['faltan']), plan['faltan']


def test_026_rf42_sube_un_libro_de_la_empresa_a_su_carpeta_y_su_anio(web, tmp_path):
    """026:RF-42 — «sube el sicodi "…" del 2025 a las fuentes de la empresa» lo registra en su clase y su año, vigente;
    sin el año, el plan lo pregunta."""
    cliente, _app = web
    wid = cliente.post('/api/workspaces').json()['id']
    libro = tmp_path / 'sicodi sintetico.xlsx'
    libro.write_bytes(b'libro sintetico de prueba')
    plan = _orden(cliente, wid, f'sube el sicodi "{libro}" a las fuentes de la empresa')
    assert plan['tarea'] == 'subir_fuente_empresa' and not plan['listo'], plan
    assert any('el año' in f for f in plan['faltan']), plan['faltan']
    plan = _orden(cliente, wid, f'sube el sicodi "{libro}" del 2025 a las fuentes de la empresa')
    assert plan['tarea'] == 'subir_fuente_empresa' and plan['listo'] and plan['espera_confirmacion'], plan['faltan']
    fin = _confirmar(cliente, wid, plan)
    assert fin['status'] == 'done', fin.get('error')
    (fuente,) = cliente.get(f'/api/workspaces/{wid}/fuentes', params={'clase': 'sicodi'}).json()['fuentes']
    assert (fuente['periodo'], fuente['vigente'], fuente['nombre']) == ('2025', True, libro.name), fuente
    assert 'el SICODI del 2025' in fin['result']['texto'], fin['result']
