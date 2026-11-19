"""070:RF-89 — CSG_ASISTENTE_OLLAMA=0 (18-11, pedido de c2 tras la e2e de 111-T16): con la variable a «0» el cliente de Ollama no abre
ninguna conexión y la orden sigue por la vía «Compatible», como con Ollama apagado; sin la variable, nada cambia. Las dos
configuraciones de las pruebas de navegador la ponen cuando corren sin modelo (CSG_E2E_SIN_MODELO=1): la web de prueba
cargaba el modelo de Ollama en la máquina (0,7 GB) en medio de una e2e.

El «Ollama» de la prueba es un servidor HTTP de mentira en un puerto libre de esta máquina: cuenta lo que recibe.
"""
from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path

import pytest

from convertersmartgrid.aplicacion.asistente import ollama
from convertersmartgrid.aplicacion.asistente.interprete import interpretar

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def ollama_de_mentira():
    recibidas = []

    class Manejador(http.server.BaseHTTPRequestHandler):
        def _responder(self):
            recibidas.append(self.path)
            cuerpo = json.dumps({'models': [{'name': 'qwen2.5:3b'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        do_GET = do_POST = _responder

        def log_message(self, *a):
            pass

    servidor = http.server.HTTPServer(('127.0.0.1', 0), Manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f'http://127.0.0.1:{servidor.server_port}', recibidas
    finally:
        servidor.shutdown()


def test_con_la_variable_a_cero_el_cliente_no_abre_ninguna_conexion(ollama_de_mentira, monkeypatch):
    """Con CSG_ASISTENTE_OLLAMA=0, ni la lista de modelos ni la interpretación llegan al servidor, y responden como un
    Ollama apagado (``None``)."""
    assert getattr(ollama, 'VARIABLE_APAGADO', None) == 'CSG_ASISTENTE_OLLAMA', 'el cliente de Ollama no se puede apagar'
    url, recibidas = ollama_de_mentira
    monkeypatch.setenv('CSG_ASISTENTE_OLLAMA', '0')
    cliente = ollama.ClienteOllama(url=url, tiempo_max_s=2)
    assert cliente.modelos() is None and cliente.interpretar('calibra P1 F1') is None
    assert recibidas == [], f'el cliente apagado habló con Ollama: {recibidas}'


def test_sin_la_variable_nada_cambia(ollama_de_mentira, monkeypatch):
    """Sin la variable (o con otro valor), el cliente pregunta a Ollama como siempre."""
    url, recibidas = ollama_de_mentira
    monkeypatch.delenv('CSG_ASISTENTE_OLLAMA', raising=False)
    assert ollama.ClienteOllama(url=url, tiempo_max_s=2).modelos() == ['qwen2.5:3b'] and recibidas == ['/api/tags']
    monkeypatch.setenv('CSG_ASISTENTE_OLLAMA', '1')
    assert ollama.ClienteOllama(url=url, tiempo_max_s=2).modelos() == ['qwen2.5:3b']


def test_con_ollama_apagado_la_orden_sigue_por_la_via_compatible(ollama_de_mentira, monkeypatch):
    """Una orden con su frase literal se entiende sin Ollama, y el servidor de mentira no recibe nada."""
    assert getattr(ollama, 'VARIABLE_APAGADO', None) == 'CSG_ASISTENTE_OLLAMA', 'el cliente de Ollama no se puede apagar'
    url, recibidas = ollama_de_mentira
    monkeypatch.setenv('CSG_ASISTENTE_OLLAMA', '0')
    i = interpretar('haz la escalera de obras en P1 F1', ollama=ollama.ClienteOllama(url=url, tiempo_max_s=2))
    assert i.tarea == 'obras_escalera', i
    assert recibidas == []


def test_las_pruebas_de_navegador_sin_modelo_apagan_ollama_en_el_servidor():
    """Las dos configuraciones de e2e ponen CSG_ASISTENTE_OLLAMA=0 cuando corren con CSG_E2E_SIN_MODELO=1."""
    config = (RAIZ / 'frontend' / 'test' / 'e2e' / 'playwright.config.mjs').read_text(encoding='utf-8')
    assert "process.env.CSG_E2E_SIN_MODELO === '1' ? { CSG_ASISTENTE_OLLAMA: '0' }" in config
    web = (RAIZ / 'frontend' / 'e2e' / 'web_de_prueba.py').read_text(encoding='utf-8')
    assert 'os.environ["CSG_ASISTENTE_OLLAMA"] = "0"' in web and 'CSG_E2E_SIN_MODELO' in web
