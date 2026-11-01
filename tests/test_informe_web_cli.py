"""017:RF-105 — un informe de la web se repite desde la línea de órdenes con su plan."""
from __future__ import annotations

import json
import time
from pathlib import Path

import docx
import pytest

pytest.importorskip('fastapi')

from fastapi.testclient import TestClient  # noqa: E402

from apoyo import cargar_herramienta, esperar_trabajo  # noqa: E402
from convertersmartgrid.web.app import create_app  # noqa: E402


def _medida(vmin):
    return {'converge': True, 'barras': [['CAB', 1.0], ['N1', vmin]], 'elementos': [['L1', 'ElmLne', 60.0]],
            'vm_min': vmin, 'vm_min_barra': 'N1', 'vm_max': 1.0, 'vm_max_barra': 'CAB', 'mas_cargado': 'L1',
            'cargabilidad_max': 60.0, 'cabecera_kw': 6000.0, 'cabecera_kvar': 3000.0, 'perdidas_kw': 300.0,
            'perdidas_kvar': 55.0}


FORMULARIO = {'project': 'P1', 'alimentador': 'AL01', 'fecha': '2026-10-15', 'lugar': 'Ica',
              'numero': 'GT-300-PR', 'asunto': 'CAÍDA DE TENSIÓN DEL CLIENTE X', 'destinatario': 'ING. Z',
              'antecedentes': ['El cliente X reclama baja tensión.'],
              'limites': {'tension_min_pu': 0.95, 'tension_max_pu': 1.05, 'cargabilidad_max_pct': 100}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    modelo = docx.Document()
    modelo.add_paragraph('Texto del modelo.')
    modelo.save(tmp_path / 'modelo.docx')
    perfil = tmp_path / 'perfil_empresa.json'
    perfil.write_text(json.dumps({'informes': {
        'modelo_estudio': str(tmp_path / 'modelo.docx'), 'modelo_factibilidad': str(tmp_path / 'modelo.docx'),
        'bandas_tension_pct': [95, 105], 'bandas_cargabilidad_pct': [80, 100],
        'cabecera': {'numero': 'INFORME TECNICO'}, 'norma': 'NTCSE'}}), encoding='utf-8')
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(perfil))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


@pytest.fixture(scope='module')
def herramienta():
    return cargar_herramienta('informe_web.py', 'informe_web_prueba', tools_en_path=True)


class WebDePrueba:
    """La interfaz de ``WebConDescarga`` sobre el ``TestClient``: la misma API, sin red."""

    def __init__(self, client, wid):
        self.client, self.wid = client, wid

    def post(self, ruta, **kw):
        r = self.client.post(f'/api/workspaces/{self.wid}{ruta}', **kw)
        assert r.status_code < 300, r.text
        return r.json()

    def esperar(self, trabajo):
        return esperar_trabajo(self.client, trabajo)

    def descargar(self, nombre):
        r = self.client.get(f'/api/workspaces/{self.wid}/files/{nombre}?download=1')
        assert r.status_code == 200, r.text
        return r.content


def _espacio(client, tmp_path) -> tuple[str, Path]:
    wid = client.post('/api/workspaces').json()['id']
    salida = tmp_path / 'web' / wid / 'salida'
    salida.mkdir(parents=True, exist_ok=True)
    (salida / 'estudio_sin_flujo_desequilibrado_a.json').write_text(
        json.dumps({'medidas': {'AL01': _medida(0.90)}}), encoding='utf-8')
    time.sleep(0.01)
    return wid, salida


def test_la_web_guarda_el_plan_y_la_linea_de_ordenes_lo_repite(client, tmp_path, herramienta):
    """017:RF-105 — el informe de la web deja su plan (tipo y formulario tal como llegó) junto al
    Word, y ``tools/informe_web.py`` lo envía a la misma API y descarga un Word igual de armado."""
    wid, salida = _espacio(client, tmp_path)
    fin = esperar_trabajo(client, client.post(f'/api/workspaces/{wid}/informes/estudio', json=FORMULARIO).json())
    assert fin['status'] == 'done', fin
    plan = salida / fin['result']['plan']
    assert plan.name == Path(fin['result']['informe']).stem + '.plan.json'
    guardado = json.loads(plan.read_text(encoding='utf-8'))
    assert guardado['tipo'] == 'estudio'
    assert {k: guardado['formulario'][k] for k in FORMULARIO} == FORMULARIO

    tipo, formulario = herramienta.leer_plan(plan)
    destino = tmp_path / 'cli'
    resultado = herramienta.generar(WebDePrueba(client, wid), tipo, formulario, destino)
    assert resultado['informe'] != fin['result']['informe']
    texto = '\n'.join(p.text for p in docx.Document(destino / resultado['informe']).paragraphs)
    assert 'CAÍDA DE TENSIÓN DEL CLIENTE X' in texto and 'El cliente X reclama baja tensión.' in texto
    assert (destino / resultado['plan']).is_file()


def test_plan_sin_tipo_o_sin_proyecto_se_rechaza(tmp_path, herramienta):
    """017:RF-105 — un formulario suelto pide ``--tipo``; sin proyecto no se envía nada."""
    suelto = tmp_path / 'formulario.json'
    suelto.write_text(json.dumps(FORMULARIO), encoding='utf-8')
    with pytest.raises(ValueError, match='--tipo'):
        herramienta.leer_plan(suelto)
    assert herramienta.leer_plan(suelto, 'estudio') == ('estudio', FORMULARIO)
    sin_proyecto = tmp_path / 'sin.json'
    sin_proyecto.write_text(json.dumps({'tipo': 'estudio', 'formulario': {'alimentador': 'AL01'}}),
                            encoding='utf-8')
    with pytest.raises(ValueError, match='proyecto'):
        herramienta.leer_plan(sin_proyecto)


def test_un_trabajo_fallido_es_un_error_con_su_motivo(tmp_path, herramienta):
    """017:RF-105 — si la web no genera el informe, la herramienta lo dice y no descarga nada."""
    class WebFallida:
        def post(self, ruta, **kw):
            return {'id': 'x'}

        def esperar(self, trabajo):
            return {'status': 'failed', 'error': 'No hay un flujo de «Sin proyecto» de AL01'}

        def descargar(self, nombre):
            raise AssertionError('no debía descargar')

    with pytest.raises(RuntimeError, match='Sin proyecto'):
        herramienta.generar(WebFallida(), 'estudio', FORMULARIO, tmp_path / 'cli')
