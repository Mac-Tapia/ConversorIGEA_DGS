"""086:RF-113 (T83): la cota de una subida se impone mientras llega el cuerpo, no después de que el parser lo haya
consumido entero (auditoría del 18-11, H04).

Con una app pequeña y aislada se cuenta lo que el servidor ASGI entrega (``receive``): un cuerpo que pasa la cota se
corta con 413 en cuanto la pasa, con o sin Content-Length y aunque mienta; en el límite exacto se admite; el endpoint no
llega a correr; y la cota tampoco pasa del espacio libre de la carpeta temporal menos su reserva.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI, File, UploadFile

from convertersmartgrid.presentacion.web import seguridad

FRONTERA = b'csgprueba'
TROZO = 512


def _presupuesto():
    assert hasattr(seguridad, 'PresupuestoIngreso'), 'falta seguridad.PresupuestoIngreso (086:RF-113)'
    return seguridad.PresupuestoIngreso


def _multipart(n_bytes: int) -> bytes:
    return (b'--' + FRONTERA + b'\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n'
            b'Content-Type: text/plain\r\n\r\n' + b'a' * n_bytes + b'\r\n--' + FRONTERA + b'--\r\n')


def _app(llamadas: list):
    app = FastAPI()

    @app.post('/subir')
    def subir(file: UploadFile = File(...)) -> dict:
        llamadas.append(file.filename)
        return {'ok': True}

    app.add_middleware(_presupuesto())
    return app


def _pedir(app, cuerpo: bytes, *, longitud: int | None) -> tuple[int, dict, int]:
    """Llama a la app ASGI con el cuerpo en trozos; devuelve el estado, el JSON y los bytes que llegó a pedir."""
    cabeceras = [(b'content-type', b'multipart/form-data; boundary=' + FRONTERA), (b'host', b'127.0.0.1')]
    if longitud is not None:
        cabeceras.append((b'content-length', str(longitud).encode()))
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
             'path': '/subir', 'raw_path': b'/subir', 'query_string': b'', 'root_path': '', 'headers': cabeceras,
             'client': ('127.0.0.1', 50000), 'server': ('127.0.0.1', 8000)}
    trozos = [cuerpo[i:i + TROZO] for i in range(0, len(cuerpo), TROZO)] or [b'']
    entregados = {'bytes': 0, 'i': 0}
    respuesta = {'estado': None, 'cuerpo': b''}

    async def receive():
        i = entregados['i']
        if i >= len(trozos):
            await asyncio.sleep(3600)  # nunca se pide más allá del cuerpo
        entregados['i'] = i + 1
        entregados['bytes'] += len(trozos[i])
        return {'type': 'http.request', 'body': trozos[i], 'more_body': i + 1 < len(trozos)}

    async def send(mensaje):
        if mensaje['type'] == 'http.response.start':
            respuesta['estado'] = mensaje['status']
        elif mensaje['type'] == 'http.response.body':
            respuesta['cuerpo'] += mensaje.get('body', b'')

    asyncio.run(asyncio.wait_for(app(scope, receive, send), timeout=10))
    datos = json.loads(respuesta['cuerpo'] or b'{}')
    return respuesta['estado'], datos, entregados['bytes']


@pytest.fixture
def cota(monkeypatch):
    def fijar(n: int) -> int:
        monkeypatch.setenv('CSG_UPLOAD_MAX_REQUEST_BYTES', str(n))
        return n
    return fijar


def test_longitud_declarada_mayor_que_la_cota_no_lee_el_cuerpo(cota):
    limite = cota(2048)
    llamadas: list = []
    cuerpo = _multipart(8192)
    estado, datos, leidos = _pedir(_app(llamadas), cuerpo, longitud=len(cuerpo))
    assert estado == 413 and 'cuota' in datos.get('detail', '').lower()
    assert leidos == 0, f'leyó {leidos} B de un cuerpo que ya se sabía mayor que {limite} B'
    assert llamadas == []


@pytest.mark.parametrize('longitud', [None, 100], ids=['sin_longitud', 'longitud_mentida'])
def test_sin_longitud_o_mentida_se_corta_al_pasar_la_cota(cota, longitud):
    limite = cota(2048)
    llamadas: list = []
    cuerpo = _multipart(64 * 1024)
    estado, datos, leidos = _pedir(_app(llamadas), cuerpo, longitud=longitud)
    assert estado == 413, f'estado {estado}: el cuerpo se consumió entero ({leidos} de {len(cuerpo)} B)'
    assert leidos <= limite + TROZO, f'leyó {leidos} B con una cota de {limite} B'
    assert llamadas == [], 'el endpoint corrió con un cuerpo fuera de cuota'


def test_en_el_limite_exacto_se_admite_y_un_byte_mas_no(cota):
    llamadas: list = []
    cuerpo = _multipart(1000)
    cota(len(cuerpo))
    estado, _datos, _leidos = _pedir(_app(llamadas), cuerpo, longitud=len(cuerpo))
    assert estado == 200 and llamadas == ['a.txt']
    cota(len(cuerpo) - 1)
    estado, _datos, _leidos = _pedir(_app(llamadas), cuerpo, longitud=None)
    assert estado == 413 and llamadas == ['a.txt']


def test_la_cota_no_pasa_del_espacio_libre_menos_la_reserva(cota, monkeypatch):
    cota(10 * 1024 ** 3)
    libre = seguridad.RESERVA_INGRESO_BYTES + 2048 if hasattr(seguridad, 'RESERVA_INGRESO_BYTES') else 2048
    monkeypatch.setattr(seguridad.shutil, 'disk_usage', lambda _ruta: type('U', (), {'free': libre})())
    llamadas: list = []
    estado, datos, leidos = _pedir(_app(llamadas), _multipart(16 * 1024), longitud=None)
    assert estado == 413 and 'espacio' in datos.get('detail', '').lower()
    assert leidos <= 2048 + TROZO and llamadas == []


def test_una_peticion_segura_no_se_cuenta(cota):
    cota(1)
    app = FastAPI()

    @app.get('/estado')
    def estado() -> dict:
        return {'ok': True}

    app.add_middleware(_presupuesto())
    respuesta: dict = {}

    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    async def send(m):
        if m['type'] == 'http.response.start':
            respuesta['estado'] = m['status']

    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': 'GET', 'scheme': 'http',
             'path': '/estado', 'raw_path': b'/estado', 'query_string': b'', 'root_path': '', 'headers': [],
             'client': ('127.0.0.1', 1), 'server': ('127.0.0.1', 8000)}
    asyncio.run(app(scope, receive, send))
    assert respuesta['estado'] == 200


def test_la_web_del_conversor_instala_la_cota_de_ingreso():
    """La app real pone la cota, también sin la puerta de seguridad (una prueba o ``uvicorn`` a mano)."""
    clase = _presupuesto()
    from convertersmartgrid.presentacion.web import app as modulo

    fuente = modulo.__loader__.get_source(modulo.__name__)
    assert 'add_middleware(PresupuestoIngreso)' in fuente, 'create_app no instala la cota de ingreso'
    assert clase.__module__ == seguridad.__name__
