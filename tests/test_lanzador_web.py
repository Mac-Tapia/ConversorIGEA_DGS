"""001:RF-28 a RF-33 — el acceso directo no se queda parado con el puerto ocupado.

2026-10-15, fase comercial: con la web ya abierta, con un servidor de prueba arrancado con
``--no-browser`` o con uno colgado, el acceso directo se quedaba en «Presione una tecla».
Cada caso se prueba con un servidor falso en un puerto libre, nunca en el 8765.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from fastapi.testclient import TestClient  # noqa: E402

from igea_dgs.web import __main__ as lanzador  # noqa: E402
from igea_dgs.web import app as app_mod  # noqa: E402
from igea_dgs.web.runtime import huella_del_codigo  # noqa: E402


def _huella_actual() -> str:
    return huella_del_codigo(app_mod.frontend_dist())


class _Falso:
    """Un Conversor falso: responde ``/api/health`` y, si se acepta, se cierra al pedirlo."""

    def __init__(self, salud: dict | None, *, acepta_cierre: bool = False,
                 espacios: list | None = None) -> None:
        self.cierres = 0
        falso = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def _responder(self, codigo: int, datos) -> None:
                cuerpo = json.dumps(datos).encode()
                self.send_response(codigo)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def do_GET(self):
                if self.path == '/api/health' and salud is not None:
                    self._responder(200, salud)
                elif self.path == '/api/workspaces' and espacios is not None:
                    self._responder(200, espacios)
                else:
                    self._responder(500, {'detail': 'no'})

            def do_POST(self):
                if self.path == '/api/sistema/cerrar' and acepta_cierre \
                        and self.headers.get(app_mod.CABECERA_LANZADOR) == '1':
                    falso.cierres += 1
                    self._responder(202, {'cerrando': True})
                    threading.Thread(target=falso.cerrar, daemon=True).start()
                else:
                    self._responder(404, {'detail': 'no'})

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Manejador)
        self.port = self.httpd.server_address[1]
        self._hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._hilo.start()

    def cerrar(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _salud(**servidor) -> dict:
    datos = {'version': '9.9', 'slots': {}}
    if servidor:
        datos['servidor'] = servidor
    return datos


@pytest.fixture
def uvicorn_falso(monkeypatch, tmp_path):
    """Sustituye uvicorn: anota en qué puerto arrancaría el servidor, sin arrancarlo."""
    arranques: list[dict] = []
    monkeypatch.setenv('IGEA_REGISTRO_TRABAJOS', str(tmp_path / 'trabajos_web'))

    class Servidor:
        def __init__(self, config):
            self.config = config
            self.should_exit = False

        def run(self):
            arranques.append(self.config)

    monkeypatch.setitem(sys.modules, 'uvicorn', types.SimpleNamespace(
        Config=lambda *a, **k: k, Server=Servidor,
        run=lambda *a, **k: arranques.append(k)))
    monkeypatch.setattr(lanzador.webbrowser, 'open', lambda *_a, **_k: True)
    monkeypatch.delenv('IGEA_WEB_HOST', raising=False)
    return arranques


def test_mismo_codigo_abierto_se_reutiliza(uvicorn_falso):
    """001:RF-28 — con el mismo código en el puerto, se abre ese y se sale con 0, sin pausa."""
    falso = _Falso(_salud(pid=1, huella=_huella_actual(), trabajos_en_curso=2))
    try:
        assert lanzador.main(['--port', str(falso.port), '--no-browser']) == 0
    finally:
        falso.cerrar()
    assert uvicorn_falso == []
    assert falso.cierres == 0


def test_otra_version_sin_trabajos_se_reemplaza(uvicorn_falso):
    """001:RF-29 — otra versión sin trabajos: se le pide cerrar y el nuevo usa el mismo puerto."""
    falso = _Falso(_salud(pid=1, huella='otra', trabajos_en_curso=0), acepta_cierre=True)
    assert lanzador.main(['--port', str(falso.port), '--no-browser']) == 0
    assert falso.cierres == 1
    assert [a['port'] for a in uvicorn_falso] == [falso.port]


def test_otra_version_con_trabajos_no_se_cierra(uvicorn_falso, capsys):
    """001:RF-30 — con trabajos en curso, se abre la versión anterior y se sale con 3."""
    falso = _Falso(_salud(pid=1, huella='otra', trabajos_en_curso=1), acepta_cierre=True)
    try:
        assert lanzador.main(['--port', str(falso.port), '--no-browser']) == lanzador.SALIDA_OTRA_VERSION
    finally:
        falso.cerrar()
    assert falso.cierres == 0 and uvicorn_falso == []
    assert '1 trabajo(s) en curso' in capsys.readouterr().err


def test_version_antigua_sin_recuento_se_mira_por_espacios(uvicorn_falso):
    """001:RF-30 — un servidor sin ``servidor`` en health: si no se sabe, no se cierra."""
    falso = _Falso(_salud())
    try:
        assert lanzador.main(['--port', str(falso.port), '--no-browser']) == lanzador.SALIDA_OTRA_VERSION
    finally:
        falso.cerrar()
    assert uvicorn_falso == []
    assert lanzador.trabajos_en_curso('http://127.0.0.1:1/', _salud()) is None


def test_conversor_colgado_se_termina(uvicorn_falso, monkeypatch):
    """001:RF-31 — un Conversor que no responde se termina y el nuevo usa su puerto."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    s.listen(8)
    port = s.getsockname()[1]
    terminados = []
    monkeypatch.setattr(lanzador, 'conversor_en', lambda *_a, **_k: None)
    monkeypatch.setattr(lanzador, 'quien_escucha',
                        lambda _p: (999_999, 'python.exe -m igea_dgs.web --no-browser'))
    monkeypatch.setattr(lanzador, '_terminar', lambda pid: (terminados.append(pid), s.close()))
    assert lanzador.main(['--port', str(port), '--no-browser']) == 0
    assert terminados == [999_999]
    assert [a['port'] for a in uvicorn_falso] == [port]


def _colgado_con_trabajos(monkeypatch, tmp_path, respuesta):
    """Un puerto ocupado por un Conversor que no responde y que anotó un trabajo en curso."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    s.listen(8)
    registro = tmp_path / 'trabajos_web'
    registro.mkdir(exist_ok=True)
    (registro / '999999.json').write_text(json.dumps({'pid': 999_999, 'en_curso': 1, 'hora': 0}))
    terminados = []
    monkeypatch.setattr(lanzador, 'conversor_en', lambda *_a, **_k: None)
    monkeypatch.setattr(lanzador, 'esperar_respuesta', lambda url, segundos: respuesta)
    monkeypatch.setattr(lanzador, 'quien_escucha',
                        lambda _p: (999_999, 'python.exe -m igea_dgs.web'))
    monkeypatch.setattr(lanzador, '_terminar', lambda pid: (terminados.append(pid), s.close()))
    return s, terminados


def test_conversor_ocupado_con_trabajos_no_se_termina(uvicorn_falso, monkeypatch, tmp_path, capsys):
    """001:RF-34 — un Conversor que no responde pero anotó trabajos en curso no se termina: se
    espera y, si sigue sin responder, se muestra en el navegador y se sale con 3."""
    s, terminados = _colgado_con_trabajos(monkeypatch, tmp_path, None)
    try:
        assert lanzador.main(['--port', str(s.getsockname()[1]), '--no-browser']) == lanzador.SALIDA_OTRA_VERSION
    finally:
        s.close()
    assert terminados == [] and uvicorn_falso == []
    assert 'trabajos en curso' in capsys.readouterr().err


def test_conversor_ocupado_que_responde_al_esperar_se_reutiliza(uvicorn_falso, monkeypatch, tmp_path):
    """001:RF-34 — si al esperar responde y es el mismo código, se reutiliza como siempre."""
    s, terminados = _colgado_con_trabajos(
        monkeypatch, tmp_path, _salud(pid=999_999, huella=_huella_actual(), trabajos_en_curso=1))
    try:
        assert lanzador.main(['--port', str(s.getsockname()[1]), '--no-browser']) == 0
    finally:
        s.close()
    assert terminados == [] and uvicorn_falso == []


def test_el_servidor_anota_sus_trabajos_en_curso(tmp_path, monkeypatch):
    """001:RF-34 — el registro del proceso dice cuántos trabajos tiene sin terminar."""
    from igea_dgs.web import jobs

    monkeypatch.setenv(jobs.VARIABLE_REGISTRO, str(tmp_path))
    gestor = jobs.JobManager(lambda *_a: None)
    suelta = threading.Event()
    job = gestor.submit('w', 'k', 't', lambda ctx: suelta.wait(5))
    assert jobs.trabajos_anotados(os.getpid()) == 1
    suelta.set()
    for _ in range(100):
        if job.status in jobs.FINISHED:
            break
        time.sleep(0.05)
    assert jobs.trabajos_anotados(os.getpid()) == 0
    monkeypatch.delenv(jobs.VARIABLE_REGISTRO)
    assert jobs.trabajos_anotados(os.getpid()) is None


def test_otro_programa_en_el_puerto_se_usa_el_siguiente(uvicorn_falso, monkeypatch, capsys):
    """001:RF-31 — si el puerto lo tiene otro programa, no se toca y se arranca en otro."""
    monkeypatch.setattr(lanzador, 'conversor_en', lambda *_a, **_k: None)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(8)
        port = s.getsockname()[1]
        assert lanzador.main(['--port', str(port), '--no-browser']) == 0
    assert len(uvicorn_falso) == 1 and uvicorn_falso[0]['port'] != port
    # El que escucha es esta prueba: el aviso lo nombra y no lo termina.
    assert f'proceso {os.getpid()}' in capsys.readouterr().out


def test_solo_un_servidor_del_conversor_cuenta_como_tal():
    """001:RF-31 — la comprobación de entorno del .bat no es un servidor que terminar."""
    assert lanzador.es_conversor('"C:\\py\\python.exe" -m igea_dgs.web --no-browser')
    assert lanzador.es_conversor('C:\\venv\\Scripts\\igea-dgs-web.exe')
    assert not lanzador.es_conversor('python -m igea_dgs.web.runtime --front')
    assert not lanzador.es_conversor('python -m http.server 8765')


def test_navegador_cuando_responde_y_ctrl_c_sin_error(monkeypatch, uvicorn_falso):
    """001:RF-32 — el navegador se abre al responder el servidor, y Ctrl+C sale con 0."""
    abiertos = []
    monkeypatch.setattr(lanzador.webbrowser, 'open', lambda url: abiertos.append(url))
    falso = _Falso(_salud())
    url = f'http://127.0.0.1:{falso.port}/'
    try:
        lanzador.abrir_cuando_responda(url, segundos=10).join(10)
    finally:
        falso.cerrar()
    assert abiertos == [url]

    class Interrumpido:
        def __init__(self, _config):
            self.should_exit = False

        def run(self):
            raise KeyboardInterrupt

    sys.modules['uvicorn'].Server = Interrumpido
    monkeypatch.setattr(lanzador, 'puerto_ocupado', lambda *_a: False)
    assert lanzador.main(['--no-browser']) == 0


def test_health_publica_el_servidor(tmp_path):
    """001:RF-33 — health da el PID, la huella del código y los trabajos en curso."""
    client = TestClient(app_mod.create_app(tmp_path))
    servidor = client.get('/api/health').json()['servidor']
    assert servidor == {'pid': os.getpid(), 'huella': _huella_actual(), 'trabajos_en_curso': 0}


def test_cierre_solo_desde_el_lanzador_local(tmp_path, monkeypatch):
    """001:RF-33 — sin cabecera o desde fuera, 403; con trabajos, 409; si no, se cierra."""
    monkeypatch.setattr(app_mod, '_cierre', [])
    app = app_mod.create_app(tmp_path)
    cabecera = {app_mod.CABECERA_LANZADOR: '1'}
    local = TestClient(app, client=('127.0.0.1', 50000))
    assert local.post('/api/sistema/cerrar').status_code == 403
    assert TestClient(app, client=('10.0.0.5', 50000)).post(
        '/api/sistema/cerrar', headers=cabecera).status_code == 403
    # Sin el servidor a mano (p. ej. con --reload), el lanzador termina el proceso.
    assert local.post('/api/sistema/cerrar', headers=cabecera).status_code == 503

    cerrado = threading.Event()
    app_mod.al_pedir_cierre(cerrado.set)
    soltar = threading.Event()
    app.state.jobs.submit('ws', 'prueba', 'Trabajo largo', lambda _ctx: soltar.wait(10))
    try:
        r = local.post('/api/sistema/cerrar', headers=cabecera)
        assert r.status_code == 409 and '1 trabajo' in r.json()['detail']
    finally:
        soltar.set()
    limite = time.monotonic() + 10
    while app.state.jobs.en_curso() and time.monotonic() < limite:
        time.sleep(0.05)
    assert local.post('/api/sistema/cerrar', headers=cabecera).status_code == 202
    assert cerrado.wait(5)
