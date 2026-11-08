"""065:RF-18 / 065:RF-19: transporte HTTP real con cancelación y cuota incremental."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    state = {'solicitudes': 0, 'contenido': b'x' * 65}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state['solicitudes'] += 1
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(len(state['contenido'])))
            self.end_headers()
            try:
                self.wfile.write(state['contenido'])
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f'http://127.0.0.1:{http.server_port}/datos.bin'
    finally:
        http.shutdown()
        http.server_close()
        thread.join(2)


def test_cuota_no_reintenta_ni_reemplaza_original(servidor, tmp_path):
    """065:RF-19 — la cabecera y bytes reales se controlan antes de publicar."""
    from convertersmartgrid.adaptadores.entrada.vnr.discovery.download import DownloadManager
    state, url = servidor
    destination = tmp_path / 'archivo.bin'
    destination.write_bytes(b'anterior')
    manager = DownloadManager(tmp_path / 'cache', max_file_size_bytes=64, verify_archive=False)
    with pytest.raises(RuntimeError, match='máximo|cuota'):
        manager.download(url, destination, force=True)
    assert state['solicitudes'] == 1
    assert destination.read_bytes() == b'anterior'
    assert not list((tmp_path / 'runtime').rglob('owner.json'))


def test_cancelacion_previa_no_abre_red(servidor, tmp_path):
    """065:RF-18 — cancelar antes de admitir impide incluso la solicitud remota."""
    from convertersmartgrid.adaptadores.entrada.vnr.discovery.download import DownloadManager
    state, url = servidor
    manager = DownloadManager(tmp_path / 'cache', verify_archive=False)
    with pytest.raises(RuntimeError, match='cancelada'):
        manager.download(url, tmp_path / 'archivo.bin', cancelled=lambda: True)
    assert state['solicitudes'] == 0


def test_cancelacion_durante_descarga_no_reintenta(servidor, tmp_path):
    """065:RF-18 / 065:RF-12 — un corte cooperativo limpia solamente su staging."""
    from convertersmartgrid.adaptadores.entrada.vnr.discovery.download import DownloadManager
    state, url = servidor
    state['contenido'] = b'x' * (2 * 1024 ** 2)
    cancel = threading.Event()
    manager = DownloadManager(tmp_path / 'cache', verify_archive=False)
    with pytest.raises(RuntimeError, match='cancelada'):
        manager.download(url, tmp_path / 'archivo.bin', cancelled=cancel.is_set,
                         on_progress=lambda n, total: cancel.set() if n else None)
    assert state['solicitudes'] == 1
    assert not (tmp_path / 'archivo.bin').exists()
    assert not list((tmp_path / 'runtime').rglob('owner.json'))
