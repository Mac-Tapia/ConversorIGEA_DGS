"""043:RF-12: pesos completos y revisiones fijas, sin activacion automatica."""
import hashlib
import importlib.util
from pathlib import Path

import pytest
import io
import json
from types import SimpleNamespace
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _modulo():
    spec = importlib.util.spec_from_file_location('preparar_modelos', Path(__file__).parents[1] / 'tools/preparar_modelos_ia.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_archivo_completo_y_hash(tmp_path):
    """043:RF-12: existir no implica estar completo ni integro."""
    m = _modulo()
    p = tmp_path / 'pesos'; p.write_bytes(b'abc')
    f = {'size': 3, 'sha256': hashlib.sha256(b'abc').hexdigest()}
    assert m.verificar_archivo(p, f)
    assert not m.verificar_archivo(p, {**f, 'size': 4})
    assert not m.verificar_archivo(p, {**f, 'sha256': '0' * 64})
    assert not m.verificar_archivo(p, {'size': 3, 'sha256': None, 'git_blob_sha1': '0'*40})


@pytest.mark.parametrize('revision', ['main', '', '../fuera'])
def test_no_acepta_ramas_mutables(revision):
    """043:RF-12: una descarga reproducible fija el commit."""
    with pytest.raises(ValueError):
        _modulo().validar_catalogo({'schema_version': 1, 'modelos': [
            {'backend': 'huggingface', 'id': 'autor/modelo', 'revision': revision, 'licencia': 'mit',
             'files': [{'path': 'model.safetensors', 'size': 3, 'sha256': '0'*64}]}]})


@pytest.mark.parametrize('ruta', ['C:/fuera/model.safetensors', 'C:model.safetensors', '.'])
def test_catalogo_rechaza_rutas_windows_fuera_del_cache(ruta):
    """043:RF-12: una ruta de entrada no debe escapar del destino de modelos."""
    with pytest.raises(ValueError):
        _modulo().validar_catalogo({'schema_version': 1, 'modelos': [
            {'backend': 'huggingface', 'id': 'autor/modelo', 'revision': 'a'*40, 'licencia': 'mit',
             'files': [{'path': ruta, 'size': 3, 'sha256': '0'*64}]}]})


@pytest.mark.parametrize('sha', ['../fuera', 'x'*64, ''])
def test_hash_de_configuracion_tambien_se_valida(sha):
    """043:RF-12: la identidad del blob se valida antes de construir rutas o descargar."""
    with pytest.raises(ValueError):
        _modulo().validar_catalogo({'schema_version': 1, 'modelos': [
            {'backend': 'huggingface', 'id': 'autor/modelo', 'revision': 'a'*40, 'licencia': 'mit',
             'files': [{'path': 'config.json', 'size': 3, 'sha256': sha}]}]})


@pytest.mark.parametrize('digest', ['a' * 64, 'b' * 64])
def test_descarga_no_reemplaza_etiqueta_existente(monkeypatch, digest):
    """043:RF-12: un modelo instalado nunca se repunta al descargar un candidato."""
    m = _modulo()
    llamadas = []
    class Abrir:
        def open(self, url, timeout):
            return io.BytesIO(json.dumps({'models': [{'name': 'qwen3:8b', 'digest': digest}]}).encode())
    monkeypatch.setattr(m.urllib.request, 'build_opener', lambda *a: Abrir())
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **k: llamadas.append(a) or SimpleNamespace(returncode=0))
    r = m.preparar_ollama({'id': 'qwen3:8b', 'revision': 'a' * 64}, True)
    assert not llamadas
    assert r['ok'] == (digest == 'a' * 64)


@pytest.mark.parametrize('fallo_transitorio', [False, True])
def test_transferencia_por_partes_y_hash_con_http_real(tmp_path, fallo_transitorio):
    """043:RF-12: completar rangos reales y verificar el artefacto antes de publicarlo."""
    m = _modulo()
    contenido = b'0123456789' * 20
    class Servidor(BaseHTTPRequestHandler):
        def do_GET(self):
            if fallo_transitorio and not getattr(self.server, 'reintentado', False):
                self.server.reintentado = True
                self.send_response(503); self.end_headers(); return
            inicio, fin = map(int, self.headers['Range'].removeprefix('bytes=').split('-'))
            datos = contenido[inicio:fin+1]
            self.send_response(206)
            self.send_header('Content-Length', str(len(datos)))
            self.send_header('Content-Range', f'bytes {inicio}-{fin}/{len(contenido)}')
            self.end_headers()
            self.wfile.write(datos)
        def log_message(self, *args):
            pass
    servidor = ThreadingHTTPServer(('127.0.0.1', 0), Servidor)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True); hilo.start()
    try:
        destino = tmp_path / 'pesos'
        ficha = {'size': len(contenido), 'sha256': hashlib.sha256(contenido).hexdigest()}
        assert m.descargar_por_partes(f'http://127.0.0.1:{servidor.server_port}/modelo', destino, ficha, tamano_parte=32)
        assert destino.read_bytes() == contenido
    finally:
        servidor.shutdown(); servidor.server_close(); hilo.join()
