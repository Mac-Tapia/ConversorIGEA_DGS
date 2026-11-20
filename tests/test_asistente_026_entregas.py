"""026:RF-45 (T19) — el asistente entrega los entregables de cada módulo (PIDE, PIT, VAD, VNR e informes) por las rutas que
ya tiene la web: los baja (el ZIP de la salida con la selección del módulo, o los ficheros del PIT y del VAD, que están
en su carpeta del espacio, uno por uno), deja lista la tarjeta para publicarlos en la nube y prepara el correo de un
informe; publicar y enviar siguen siendo el clic del operador (070:RF-81). Lo que la web no hace con un módulo, el plan
lo dice y no se ofrece: el correo solo lleva un informe cerrado (110:RF-3) y la nube solo publica la salida (109:RF-24).

Datos sintéticos, de ninguna empresa (P13).
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from convertersmartgrid.aplicacion.asistente import ejecutor
from convertersmartgrid.aplicacion.asistente.interprete import _por_frase_literal
from convertersmartgrid.presentacion.web import services


@pytest.fixture
def web(tmp_path, monkeypatch):
    import convertersmartgrid.dominio.perfil_empresa as perfil_empresa
    from convertersmartgrid.presentacion.web.app import create_app

    monkeypatch.setattr(perfil_empresa, 'cargar_perfil',
                        lambda *a, **k: perfil_empresa.PerfilEmpresa(nombre='Distribuidora Sintética Norte'))
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


def _esperar(cliente, trabajo_id: str) -> dict:
    limite = time.monotonic() + 120
    while time.monotonic() < limite:
        r = cliente.get(f'/api/jobs/{trabajo_id}').json()
        if r['status'] in ('done', 'failed', 'cancelled', 'parcial'):
            return r
        time.sleep(0.05)
    pytest.fail('la cola no terminó')


def _orden(cliente, wid: str, texto: str) -> dict:
    r = cliente.post(f'/api/workspaces/{wid}/asistente/orden', json={'texto': texto})
    assert r.status_code == 202, r.text
    fin = _esperar(cliente, r.json()['id'])
    assert fin['status'] == 'done', fin.get('error')
    return fin['result']


def _lo_que_hizo(cliente, respuesta: dict) -> dict:
    """La orden que solo lee se lanza sola: su trabajo, terminado."""
    assert respuesta.get('trabajo'), respuesta['plan']
    fin = _esperar(cliente, respuesta['trabajo']['id'])
    assert fin['status'] == 'done', fin.get('error')
    return fin['result']


def _salida(app, wid: str):
    ws = app.state.store.get(wid)
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    (ws.out_dir / 'pide_t1.xlsx').write_bytes(b'formatos del pide')
    (ws.out_dir / 'vnr').mkdir()
    (ws.out_dir / 'vnr' / 'resultado.json').write_text('{}', encoding='utf-8')
    (ws.out_dir / 'Informe_QX511.docx').write_bytes(b'informe')
    (ws.out_dir / 'Informe_QX511.json').write_text(json.dumps({'tipo': 'estudio'}), encoding='utf-8')
    (ws.out_dir / 'Informe_QX511.pdf').write_bytes(b'pdf')
    (ws.out_dir / 'QX511.dgs').write_text('red', encoding='utf-8')
    return ws


def _zip(cliente, enlace: str) -> list[str]:
    r = cliente.get(enlace)
    assert r.status_code == 200, r.text
    return sorted(zipfile.ZipFile(io.BytesIO(r.content)).namelist())


def test_026_rf45_descargar_un_modulo_se_reconoce_y_no_rearma_su_expediente():
    """026:RF-45 — «descarga el expediente del PIT» baja lo que hay (no vuelve a armarlo); igual el PIDE, el VAD, el VNR
    y los informes. Publicar y enviar un módulo siguen en sus tareas de la nube y del correo."""
    for orden in ('descarga el expediente del PIT', 'descarga el PIDE', 'bájame los entregables del VAD',
                  'descarga el VNR', 'descarga los informes'):
        assert _por_frase_literal(orden, None) == 'descargar_resultados', orden
    assert _por_frase_literal('publica el PIDE en google drive', None) == 'publicar_nube'
    assert _por_frase_literal('envía el PIDE por correo a revisor@otra.test', None) == 'enviar_informe'


def test_026_rf45_los_pasos_de_cada_modulo_van_a_su_ruta():
    """026:RF-45 — el ZIP de la salida con la selección del módulo; el PIT, de su trabajo; el VAD, de su estudio."""
    assert hasattr(ejecutor, '_pasos_026_rf45'), 'el ejecutor no sabe bajar los entregables de un módulo'
    (zip_,) = ejecutor.pasos('descargar_resultados', {}, {'entrega': {'modulo': 'pide', 'seleccion': ['pide_t1.xlsx']}})
    assert (zip_.metodo, zip_.ruta, zip_.cuerpo) == ('POST', '/outputs/archive', {'feeders': ['pide_t1.xlsx']})
    (pit,) = ejecutor.pasos('descargar_resultados', {}, {'entrega': {'modulo': 'pit', 'trabajo': 'j1'}})
    assert (pit.metodo, pit.ruta, pit.espera) == ('GET', '/api/jobs/j1', False)
    (vad,) = ejecutor.pasos('descargar_resultados', {}, {'entrega': {'modulo': 'vad', 'estudio': 'e1'}})
    assert (vad.metodo, vad.ruta) == ('GET', '/vad/e1')
    (todo,) = ejecutor.pasos('descargar_resultados', {'alimentadores': ['F1']}, {})
    assert (todo.ruta, todo.cuerpo) == ('/outputs/archive', {'feeders': ['F1']})


def test_026_rf45_descarga_el_pide_el_vnr_y_los_informes_solo_con_lo_suyo(web):
    """026:RF-45 — cada ZIP lleva solo lo del módulo: nada del DGS ni de los otros módulos."""
    cliente, app = web
    wid = cliente.post('/api/workspaces').json()['id']
    _salida(app, wid)
    esperado = {'descarga el PIDE': ['pide_t1.xlsx'], 'descarga el VNR': ['vnr/resultado.json'],
                'descarga los informes': ['Informe_QX511.docx', 'Informe_QX511.pdf']}
    for orden, ficheros in esperado.items():
        r = _orden(cliente, wid, orden)
        assert r['plan']['tarea'] == 'descargar_resultados' and r['plan']['listo'], (orden, r['plan']['faltan'])
        hecho = _lo_que_hizo(cliente, r)
        assert f'/api/workspaces/{wid}/outputs.zip?job=' in (hecho.get('enlace') or ''), (orden, hecho)
        assert _zip(cliente, hecho['enlace']) == ficheros, orden


def test_026_rf45_descarga_el_pit_y_el_vad_desde_su_carpeta_uno_por_uno(web):
    """026:RF-45 — el PIT, con las salidas de su último expediente terminado; el VAD, con las de su estudio. Cada uno
    queda como entregable que el panel enlaza, y la web lo sirve."""
    cliente, app = web
    wid = cliente.post('/api/workspaces').json()['id']
    ws = app.state.store.get(wid)
    r = _orden(cliente, wid, 'descarga el expediente del PIT')
    assert r['plan']['tarea'] == 'descargar_resultados' and not r['plan']['listo'], r['plan']
    assert any('expediente' in f for f in r['plan']['faltan']), r['plan']['faltan']
    carpeta = Path(ws.root) / 'expedientes_pit' / 'AX1'
    carpeta.mkdir(parents=True)
    (carpeta / 'formato_f1.xlsx').write_bytes(b'formato')
    (carpeta / 'informe.json').write_text('{}', encoding='utf-8')
    rel = {'formato': 'expedientes_pit/AX1/formato_f1.xlsx', 'informe': 'expedientes_pit/AX1/informe.json'}
    trabajo = app.state.jobs.submit(wid, 'pit_expediente', 'Expediente PIT AX1', lambda ctx: {'salidas_relativas': rel})
    assert _esperar(cliente, trabajo.id)['status'] == 'done'
    r = _orden(cliente, wid, 'descarga el expediente del PIT')
    assert r['plan']['tarea'] == 'descargar_resultados' and r['plan']['listo'], r['plan']['faltan']
    hecho = _lo_que_hizo(cliente, r)
    assert sorted(hecho['entregables']) == sorted(rel.values()), hecho
    for ruta in hecho['entregables']:
        assert cliente.get(f'/api/workspaces/{wid}/files/{ruta}', params={'download': True}).status_code == 200, ruta
    crea = _orden(cliente, wid, 'crea el estudio del VAD del grupo 1 para 2041-2045')['plan']
    assert crea['listo'], crea['faltan']
    assert _esperar(cliente, cliente.post(f"/api/workspaces/{wid}/asistente/{crea['id']}/confirmar").json()['id'])[
        'status'] == 'done'
    (estudio,) = [p.parent for p in (Path(ws.root) / 'vad').glob('*/estudio.json')]
    (estudio / 'anexo2.xlsx').write_bytes(b'anexo')
    hecho = _lo_que_hizo(cliente, _orden(cliente, wid, 'bájame los entregables del VAD'))
    assert f'vad/{estudio.name}/anexo2.xlsx' in hecho['entregables'], hecho


def test_026_rf45_publicar_un_modulo_deja_la_tarjeta_con_su_seleccion(web):
    """026:RF-45, 109:RF-24 — «publica el PIDE en google drive» deja la tarjeta con lo del PIDE; el PIT no se ofrece:
    está fuera de la salida, que es lo único que la web publica."""
    cliente, app = web
    wid = cliente.post('/api/workspaces').json()['id']
    _salida(app, wid)
    for orden, seleccion in (('publica el PIDE en google drive', 'pide'), ('sube el VNR a onedrive', 'vnr'),
                             ('publica el informe Informe_QX511 en google drive', 'Informe_QX511.docx')):
        r = _orden(cliente, wid, orden)
        assert r['plan']['tarea'] == 'publicar_nube' and r['plan']['listo'], (orden, r['plan']['faltan'])
        assert _lo_que_hizo(cliente, r)['tarjeta']['salida'] == seleccion, orden
    plan = _orden(cliente, wid, 'publica el expediente del PIT en google drive')['plan']
    assert plan['tarea'] == 'publicar_nube' and not plan['listo'], plan
    assert any('fuera de la salida' in f for f in plan['faltan']), plan['faltan']


def test_026_rf45_el_correo_lleva_un_informe_nunca_otro_libro(web):
    """026:RF-45, 110:RF-3 — «envía el PIDE por correo» no adjunta el último informe en su lugar: el plan dice cómo
    entregarlo; el informe sigue saliendo por su borrador."""
    cliente, app = web
    wid = cliente.post('/api/workspaces').json()['id']
    _salida(app, wid)
    plan = _orden(cliente, wid, 'envía el PIDE por correo a revisor@otra.test')['plan']
    assert plan['tarea'] == 'enviar_informe' and not plan['listo'], plan
    assert any('solo lleva un informe cerrado' in f for f in plan['faltan']), plan['faltan']
    plan = _orden(cliente, wid, 'envía el informe por correo a revisor@otra.test')['plan']
    assert plan['tarea'] == 'enviar_informe' and plan['listo'], plan['faltan']
