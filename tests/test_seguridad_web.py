"""086:RF-17 a RF-22 — la web solo atiende a esta máquina, con su token, y no sale a la red por su cuenta.

La revisión de la spec 086 reprodujo en la revisión af5d1357 que una página cualquiera del navegador
llegaba a la API de 127.0.0.1: Host ajeno 200, POST con Origin ajeno 201, sin token 200 y WebSocket con
Origin ajeno aceptado. Cada puerta tiene aquí su prueba negativa, también en el WebSocket.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import base64
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from convertersmartgrid.dominio import sesion_web
from convertersmartgrid.dominio.edicion import VARIABLE_EDICION, es_edicion_producto
from convertersmartgrid.dominio.salidas_red import (SALIDAS, SalidaApagada, contraer, exigir_salida, motivo_apagada,
                                            preparar_entorno_sin_red, salida_permitida)
from convertersmartgrid.presentacion.web import __main__ as lanzador
from convertersmartgrid.presentacion.web import seguridad
from convertersmartgrid.presentacion.web.app import create_app
from convertersmartgrid.presentacion.web.jobs import EventLog

RAIZ = Path(__file__).resolve().parents[1]
PUERTO = 8791
BASE = f'http://127.0.0.1:{PUERTO}'


def _latido_corto(monkeypatch) -> None:
    """El WebSocket espera 15 s entre latidos, y cerrar la prueba esperaría a que acabe esa espera."""
    original = EventLog.wait
    monkeypatch.setattr(EventLog, 'wait', lambda self, seq, _espera: original(self, seq, 0.05))


@pytest.fixture
def puerta(tmp_path, monkeypatch):
    """La aplicación con su puerta encendida y la sesión de un arranque de verdad."""
    monkeypatch.setattr(sesion_web, 'EXIGIR_SEGURIDAD', True)
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 'sesiones'))
    monkeypatch.setenv(sesion_web.VARIABLE_PUERTO, str(PUERTO))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    _latido_corto(monkeypatch)
    sesion = sesion_web.crear_sesion(PUERTO)
    app = create_app(tmp_path / 'web', host='127.0.0.1')
    return types.SimpleNamespace(app=app, sesion=sesion, token=sesion.token,
                                 con_token={sesion_web.CABECERA_TOKEN: sesion.token, 'Origin': BASE})


def _cliente(app, base=BASE, peer='127.0.0.1') -> TestClient:
    return TestClient(app, base_url=base, client=(peer, 50000), follow_redirects=False)


def _espacio(puerta) -> str:
    with _cliente(puerta.app) as c:
        return c.post('/api/workspaces', headers=puerta.con_token).json()['id']


def _codigo_ws(cliente, ruta: str, cabeceras: dict) -> int | None:
    """El código con que se rechaza el WebSocket, o None si lo acepta."""
    try:
        # El cliente de pruebas no usa su base_url en el WebSocket: la dirección entera, o llega como «testserver».
        destino = ruta if ruta.startswith('ws:') else f'ws://127.0.0.1:{PUERTO}{ruta}'
        with cliente.websocket_connect(destino, headers=cabeceras) as w:
            w.receive_json()
            return None
    except WebSocketDisconnect as exc:
        return exc.code


# ------------------------------------------------------------ RF-17, Host
@pytest.mark.parametrize('host', ['evil.example', '127.0.0.1.evil.example', 'evil.example:8791',
                                  '127.0.0.1@evil.example', '127.0.0.1:8791; script-src *', '192.168.1.20:8791', ''])
def test_host_ajeno_se_rechaza(puerta, host):
    """086:RF-17 — DNS rebinding: la página de un dominio ajeno que resuelve a 127.0.0.1."""
    with _cliente(puerta.app) as c:
        for ruta in ('/api/health', '/', '/assets/x.js'):
            r = c.get(ruta, headers={**puerta.con_token, 'Origin': f'http://{host}', 'Host': host})
            assert r.status_code == 403, (ruta, host)
            assert 'Host no permitido' in r.json()['detail']


@pytest.mark.parametrize('base', [BASE, f'http://localhost:{PUERTO}', f'http://[::1]:{PUERTO}'])
def test_host_propio_se_admite(puerta, base):
    """086:RF-17 — las tres formas de nombrar esta máquina."""
    with _cliente(puerta.app, base) as c:
        assert c.get('/api/health', headers={sesion_web.CABECERA_TOKEN: puerta.token}).status_code == 200


def test_host_ajeno_tambien_en_el_websocket(puerta):
    """086:RF-17 — el WebSocket pasa por la misma puerta."""
    wid = _espacio(puerta)
    with _cliente(puerta.app, 'http://evil.example') as c:
        r = _codigo_ws(c, f'ws://evil.example/api/workspaces/{wid}/ws',
                       {'Origin': 'http://evil.example', sesion_web.CABECERA_TOKEN: puerta.token})
        assert r == 4403


def test_lista_de_hosts_ampliable_solo_de_forma_explicita(tmp_path, monkeypatch):
    """086:RF-17 — un nombre más solo si se declara al arrancar."""
    monkeypatch.setattr(sesion_web, 'EXIGIR_SEGURIDAD', True)
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 's'))
    monkeypatch.setenv(sesion_web.VARIABLE_PUERTO, str(PUERTO))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.setenv(seguridad.VARIABLE_HOSTS, 'puesto.local')
    token = sesion_web.crear_sesion(PUERTO).token
    with _cliente(create_app(tmp_path / 'web', host='127.0.0.1'), f'http://puesto.local:{PUERTO}') as c:
        assert c.get('/api/health', headers={sesion_web.CABECERA_TOKEN: token}).status_code == 200


# ------------------------------------------------------------ RF-18, Origin
@pytest.mark.parametrize('origen', [None, 'http://evil.example', 'null', 'http://127.0.0.1:9000',
                                    f'https://127.0.0.1:{PUERTO}', 'http://localhost:5174'])
def test_lo_que_cambia_algo_exige_origin_propio(puerta, origen):
    """086:RF-18 — CSRF: aun con token, un POST sin Origin propio no entra."""
    cabeceras = {sesion_web.CABECERA_TOKEN: puerta.token, **({'Origin': origen} if origen else {})}
    with _cliente(puerta.app) as c:
        for metodo, ruta in (('POST', '/api/workspaces'), ('DELETE', '/api/workspaces/x'),
                             ('PUT', '/api/workspaces/x/options')):
            r = c.request(metodo, ruta, headers=cabeceras)
            assert r.status_code == 403, (metodo, origen)
            assert 'Origin' in r.json()['detail']
        assert c.get('/api/workspaces').status_code == 401


def test_origin_propio_pasa_y_get_sin_origin_tambien(puerta):
    """086:RF-18 — el navegador no manda Origin en un GET propio; y uno ajeno en GET tampoco pasa."""
    with _cliente(puerta.app) as c:
        assert c.post('/api/workspaces', headers=puerta.con_token).status_code == 201
        assert c.get('/api/workspaces', headers={sesion_web.CABECERA_TOKEN: puerta.token}).status_code == 200
        assert c.get('/api/workspaces', headers={sesion_web.CABECERA_TOKEN: puerta.token,
                                                 'Origin': 'http://evil.example'}).status_code == 403


@pytest.mark.parametrize('origen', [None, 'http://evil.example', 'null', 'http://127.0.0.1:9000'])
def test_websocket_exige_origin_propio(puerta, origen):
    """086:RF-18 — el navegador deja abrir un WebSocket entre orígenes; la puerta es el servidor."""
    wid = _espacio(puerta)
    cabeceras = {sesion_web.CABECERA_TOKEN: puerta.token, **({'Origin': origen} if origen else {})}
    with _cliente(puerta.app) as c:
        assert _codigo_ws(c, f'/api/workspaces/{wid}/ws', cabeceras) == 4403


def test_origen_de_vite_en_desarrollo_y_no_en_producto(tmp_path, monkeypatch):
    """086:RF-18 — el servidor de Vite solo en la edición de desarrollo."""
    monkeypatch.setattr(sesion_web, 'EXIGIR_SEGURIDAD', True)
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 's'))
    monkeypatch.setenv(sesion_web.VARIABLE_PUERTO, str(PUERTO))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    monkeypatch.delenv('CSG_WEB_DEV_ORIGINS', raising=False)
    token = sesion_web.crear_sesion(PUERTO).token
    cabeceras = {sesion_web.CABECERA_TOKEN: token, 'Origin': 'http://127.0.0.1:5173'}
    with _cliente(create_app(tmp_path / 'a', host='127.0.0.1')) as c:
        assert c.post('/api/workspaces', headers=cabeceras).status_code == 201
    monkeypatch.setenv(VARIABLE_EDICION, 'producto')
    with _cliente(create_app(tmp_path / 'b', host='127.0.0.1')) as c:
        assert c.post('/api/workspaces', headers=cabeceras).status_code == 403


# ------------------------------------------------------------ RF-19, token
def _rutas_api(app):
    # Del esquema: ``app.routes`` no entra en los routers incluidos, como el de VNR-GIS.
    for ruta, metodos in app.openapi()['paths'].items():
        for metodo in metodos:
            yield metodo.upper(), re.sub(r'\{[^}]+\}', 'x', ruta)


def test_toda_la_api_exige_el_token(puerta):
    """086:RF-19 — una por una, para que una ruta nueva nazca cerrada; también el cierre del lanzador."""
    rutas = sorted(set(_rutas_api(puerta.app)))
    assert len(rutas) > 100
    assert ('POST', '/api/sistema/cerrar') in rutas
    with _cliente(puerta.app) as c:
        for metodo, ruta in rutas:
            for cabeceras in ({'Origin': BASE}, {'Origin': BASE, sesion_web.CABECERA_TOKEN: 'falso'},
                              {'Origin': BASE, 'Authorization': 'Bearer falso'},
                              {'Origin': BASE, 'Cookie': f'{seguridad.nombre_cookie(PUERTO)}=falso'}):
                r = c.request(metodo, ruta, headers=cabeceras)
                assert r.status_code == 401, (metodo, ruta, cabeceras)
                assert 'sesión' in r.json()['detail']
        assert c.get('/openapi.json').status_code == 401


def test_no_hay_rutas_fuera_de_la_api_salvo_la_pagina(puerta):
    """086:RF-19 — lo público es la página; sin /docs, que además sale a un CDN (086:RF-22)."""
    fuera = [r for r in puerta.app.openapi()['paths'] if not r.startswith('/api/')]
    assert not fuera, fuera
    with _cliente(puerta.app) as c:
        assert c.get('/docs').status_code == 404
        assert c.get('/redoc').status_code == 404


def test_websocket_exige_el_token(puerta):
    """086:RF-19 — sin token ni con uno falso."""
    wid = _espacio(puerta)
    with _cliente(puerta.app) as c:
        for extra in ({}, {sesion_web.CABECERA_TOKEN: 'falso'}):
            assert _codigo_ws(c, f'/api/workspaces/{wid}/ws', {'Origin': BASE, **extra}) == 4401
        assert _codigo_ws(c, f'/api/workspaces/{wid}/ws', puerta.con_token) is None


def test_el_cierre_del_lanzador_sigue_funcionando_con_token(puerta):
    """086:RF-19 — token, Origin y su cabecera: pasa la puerta y responde la ruta (503: sin servidor a mano)."""
    with _cliente(puerta.app) as c:
        r = c.post('/api/sistema/cerrar', headers={**puerta.con_token, 'X-CSG-Lanzador': '1',
                                                   'X-CSG-Motivo': 'prueba'})
        assert r.status_code == 503
        assert c.post('/api/sistema/cerrar', headers=puerta.con_token).status_code == 403


def test_un_enlace_viejo_ve_una_pagina_y_la_api_su_json(puerta):
    """086:RF-19 — con el enlace de un arranque anterior, la persona lee qué hacer; un programa sigue con su JSON."""
    with _cliente(puerta.app) as c:
        r = c.get(f'/?{sesion_web.PARAMETRO_ACCESO}=viejo', headers={'Accept': 'text/html,*/*'})
        assert r.status_code == 401 and r.headers['content-type'].startswith('text/html')
        assert 'acceso directo' in r.text and '"detail"' not in r.text
        api = c.get('/api/workspaces', headers={'Accept': 'application/json'})
        assert api.status_code == 401 and api.json()['detail']


def test_la_direccion_del_lanzador_se_cambia_por_una_cookie(puerta):
    """086:RF-19 — HttpOnly y SameSite=Strict, sin el token en la barra de direcciones."""
    with _cliente(puerta.app) as c:
        r = c.get(f'/?panel=x&{sesion_web.PARAMETRO_ACCESO}={puerta.token}')
        assert r.status_code == 303
        assert r.headers['location'] == '/?panel=x'
        cookie = r.headers['set-cookie']
        assert cookie.startswith(f'{seguridad.nombre_cookie(PUERTO)}={puerta.token}')
        assert 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
        assert r.headers['referrer-policy'] == 'no-referrer'
        # Ya con la cookie, el navegador pasa por la API y por el WebSocket sin hacer nada más.
        assert c.get('/api/health').status_code == 200
        wid = c.post('/api/workspaces', headers={'Origin': BASE}).json()['id']
        assert _codigo_ws(c, f'/api/workspaces/{wid}/ws', {'Origin': BASE}) is None
    with _cliente(puerta.app) as otro:
        r = otro.get(f'/?{sesion_web.PARAMETRO_ACCESO}=falso')
        assert r.status_code == 401 and 'set-cookie' not in r.headers


def test_la_cookie_es_de_su_puerto(puerta):
    """086:RF-19 — las cookies no distinguen puertos: la de otra web de la máquina no vale aquí."""
    with _cliente(puerta.app) as c:
        r = c.get('/api/health', headers={'Cookie': f'{seguridad.nombre_cookie(9000)}={puerta.token}'})
        assert r.status_code == 401
        # Una cookie rara de otro programa de 127.0.0.1 no le quita la suya.
        r = c.get('/api/health', headers={'Cookie': f'x={{"a":1}}; {seguridad.nombre_cookie(PUERTO)}={puerta.token}'})
        assert r.status_code == 200


def test_cada_arranque_tiene_token_nuevo_y_el_anterior_solo_releva(tmp_path, monkeypatch):
    """086:RF-19 — la pestaña abierta se reconecta y sale con el token nuevo (001:RF-35); después, no vale."""
    monkeypatch.setattr(sesion_web, 'EXIGIR_SEGURIDAD', True)
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 's'))
    monkeypatch.setenv(sesion_web.VARIABLE_PUERTO, str(PUERTO))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    _latido_corto(monkeypatch)
    viejo = sesion_web.crear_sesion(PUERTO).token
    nueva = sesion_web.crear_sesion(PUERTO)
    assert nueva.token != viejo and nueva.anterior == viejo
    app = create_app(tmp_path / 'web', host='127.0.0.1')
    cookie = {'Cookie': f'{seguridad.nombre_cookie(PUERTO)}={viejo}'}
    with _cliente(app) as c:
        r = c.get('/api/health', headers=cookie)
        assert r.status_code == 200
        assert f'{seguridad.nombre_cookie(PUERTO)}={nueva.token}' in r.headers['set-cookie']
        wid = c.post('/api/workspaces', headers={**cookie, 'Origin': BASE}).json()['id']
        with c.websocket_connect(f'ws://127.0.0.1:{PUERTO}/api/workspaces/{wid}/ws',
                                 headers={**cookie, 'Origin': BASE}) as w:
            assert any(k.lower() == b'set-cookie' and nueva.token.encode() in v for k, v in w.extra_headers or ())
            w.receive_json()
        ahora = time.monotonic()
        monkeypatch.setattr(seguridad.time, 'monotonic', lambda: ahora + seguridad.RELEVO_S + 1)
        assert c.get('/api/health', headers=cookie).status_code == 401


def test_sin_lanzador_la_api_queda_cerrada(tmp_path, monkeypatch, capsys):
    """086:RF-19 — ``uvicorn`` a mano no abre la web por no conocer el token: la cierra y lo dice."""
    monkeypatch.setattr(sesion_web, 'EXIGIR_SEGURIDAD', True)
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 's'))
    monkeypatch.delenv(sesion_web.VARIABLE_PUERTO, raising=False)
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with _cliente(create_app(tmp_path / 'web')) as c:
        assert c.get('/api/health').status_code == 401
    assert 'la API queda cerrada' in capsys.readouterr().err


def test_el_fichero_del_token_es_solo_del_usuario(tmp_path, monkeypatch):
    """086:RF-19 — lo lee quien ya es este usuario en esta máquina."""
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 's'))
    sesion_web.crear_sesion(PUERTO)
    ruta = sesion_web.ruta_sesion(PUERTO)
    if os.name == 'nt':
        acl = subprocess.run(['icacls', str(ruta)], capture_output=True, text=True, check=True).stdout
        assert os.environ['USERNAME'].lower() in acl.lower()
        for ajeno in ('BUILTIN\\Users', 'Authenticated Users', 'Everyone', 'BUILTIN\\Usuarios', 'Todos'):
            assert ajeno.lower() not in acl.lower(), acl
    else:
        assert (ruta.stat().st_mode & 0o777) == 0o600
    assert not list(ruta.parent.glob('.sesion-*'))


def test_el_token_solo_va_a_esta_maquina(tmp_path, monkeypatch):
    """086:RF-19 — un cliente con otra dirección no lo manda, aunque el puerto coincida."""
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 's'))
    token = sesion_web.crear_sesion(PUERTO).token
    assert sesion_web.cabeceras_locales(f'http://servidor.example:{PUERTO}') == {}
    assert sesion_web.cabeceras_locales('http://testserver') == {}
    assert sesion_web.cabeceras_locales(BASE) == {sesion_web.CABECERA_TOKEN: token, 'Origin': BASE}
    assert sesion_web.url_de_entrada(f'{BASE}/') == f'{BASE}/?{sesion_web.PARAMETRO_ACCESO}={token}'
    assert sesion_web.url_de_entrada(f'http://servidor.example:{PUERTO}/') == f'http://servidor.example:{PUERTO}/'
    assert sesion_web.cabeceras_locales('http://127.0.0.1:9000') == {'Origin': 'http://127.0.0.1:9000'}


def test_arranque_que_pierde_el_puerto_devuelve_el_fichero(tmp_path, monkeypatch):
    """086:RF-19 — el fichero vuelve a ser del servidor que sí escucha: si no, todos sus clientes darían 401."""
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 's'))
    bueno = sesion_web.crear_sesion(PUERTO).token
    perdedor = sesion_web.crear_sesion(PUERTO)
    assert sesion_web.leer_sesion(PUERTO).token == perdedor.token
    sesion_web.devolver_sesion(perdedor)
    assert sesion_web.leer_sesion(PUERTO).token == bueno


def test_el_registro_de_accesos_no_guarda_el_token():
    """086:RF-19 — uvicorn escribe la URL entera, y en la edición de producto irá a ficheros (RF-41)."""
    filtro = seguridad._SinTokenEnElRegistro()
    registro = logging.LogRecord('uvicorn.access', logging.INFO, '', 0, '%s %s', ('GET', '/?panel=x&acceso=secreto'), None)
    assert filtro.filter(registro) is True
    assert 'secreto' not in registro.getMessage() and 'panel=x' in registro.getMessage()


def test_ningun_registro_guarda_secretos_en_el_mensaje():
    """086:RF-19 — el filtro iba solo en ``uvicorn.access`` y solo miraba ``args``: el asistente escribía el token."""
    import io

    flujo = io.StringIO()
    manejador = logging.StreamHandler(flujo)
    programa = logging.getLogger('convertersmartgrid')
    programa.addHandler(manejador)
    nivel = programa.level
    programa.setLevel(logging.INFO)
    try:
        seguridad._instalar_filtro_registro()
        registro = logging.getLogger('convertersmartgrid.aplicacion.asistente')
        registro.info('orden «%s» con acceso=secreto1 y Authorization: Bearer secreto2abc', 'convierte AL101')
        registro.info('token=secreto3&x=1 contraseña: secreto4 "password": "secreto5"')
        registro.info('cabecera %s: %s', 'X-CSG-Token', 'secreto6')
    finally:
        programa.removeHandler(manejador)
        programa.setLevel(nivel)
    texto = flujo.getvalue()
    assert 'convierte AL101' in texto and 'x=1' in texto
    assert not re.search(r'secreto\d', texto), texto


# ------------------------------------------------------------ clientes locales
@pytest.fixture
def servidor_real(tmp_path, monkeypatch):
    """Un uvicorn de verdad, en un puerto libre: la puerta con los clientes tal como son."""
    import uvicorn

    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        puerto = s.getsockname()[1]
    monkeypatch.setattr(sesion_web, 'EXIGIR_SEGURIDAD', True)
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 's'))
    monkeypatch.setenv(sesion_web.VARIABLE_PUERTO, str(puerto))
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    _latido_corto(monkeypatch)
    sesion = sesion_web.crear_sesion(puerto)
    app = create_app(tmp_path / 'web', host='127.0.0.1')
    servidor = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=puerto, log_level='warning', proxy_headers=False))
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()
    limite = time.monotonic() + 30
    while not servidor.started and time.monotonic() < limite:
        time.sleep(0.05)
    assert servidor.started
    yield types.SimpleNamespace(url=f'http://127.0.0.1:{puerto}', puerto=puerto, token=sesion.token, servidor=servidor)
    servidor.should_exit = True
    hilo.join(30)


def test_el_lanzador_sigue_viendo_y_cerrando_la_web(servidor_real, monkeypatch):
    """086:RF-19 — sin token, ``conversor_en`` no veía nada y terminaba el proceso por colgado."""
    url = servidor_real.url + '/'
    salud = lanzador.conversor_en(url)
    assert salud and salud['version'] and salud['servidor']['pid'] == os.getpid()
    assert lanzador.trabajos_en_curso(url, {}) == 0
    assert lanzador.es_web_de_otra_sesion(url) is False
    cierres = []
    from convertersmartgrid.presentacion.web import app as app_mod
    monkeypatch.setattr(app_mod, '_cierre', [lambda: cierres.append(1)])
    monkeypatch.setattr(app_mod, '_motivo_cierre', [])
    assert lanzador.pedir_cierre(url, 'prueba') is True
    limite = time.monotonic() + 5
    while not cierres and time.monotonic() < limite:
        time.sleep(0.05)
    assert cierres


def test_el_lanzador_no_toca_la_web_de_otra_sesion(servidor_real, tmp_path, monkeypatch):
    """086:RF-19 — con otro token responde 401: no está colgada, y antes se terminaba (081:RF-44)."""
    url = servidor_real.url + '/'
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 'otra'))
    assert lanzador.conversor_en(url) is None
    assert lanzador.es_web_de_otra_sesion(url) is True
    monkeypatch.setattr(lanzador, '_terminar', lambda _p: pytest.fail('terminó una web que funciona'))
    monkeypatch.setattr(lanzador, 'quien_escucha', lambda _p: pytest.fail('no hay que buscarle el proceso'))
    accion, valor = lanzador.resolver_puerto('127.0.0.1', servidor_real.puerto, abrir=False)
    assert accion == 'arrancar' and valor != servidor_real.puerto


def test_sistema_web_y_cliente_del_asistente_con_token(servidor_real):
    """086:RF-19 — las herramientas de ``tools/`` y el asistente, que se llama a sí mismo por la API."""
    import requests

    sys.path.insert(0, str(RAIZ / 'tools'))
    from sistema_web import Web

    from convertersmartgrid.aplicacion.asistente.ejecutor import ClienteWeb

    with urllib.request.urlopen(urllib.request.Request(
            servidor_real.url + '/api/workspaces', data=b'', method='POST',
            headers=sesion_web.cabeceras_locales(servidor_real.url))) as r:
        wid = __import__('json').load(r)['id']
    web = Web(servidor_real.url, wid, reintentos=1)
    assert web.get('')['id'] == wid
    cliente = ClienteWeb(requests.Session(), servidor_real.url, wid)
    assert cliente.pedir('GET', '')['id'] == wid
    assert cliente.pedir('PUT', '/options', json={'strict': True})['id'] == wid


def test_websocket_real_se_abre_con_cookie_y_no_entre_origenes(servidor_real):
    """086:RF-18, 086:RF-19 — con un cliente WebSocket de verdad, sobre uvicorn."""
    from websockets.exceptions import InvalidStatus
    from websockets.sync.client import connect

    cab = sesion_web.cabeceras_locales(servidor_real.url)
    pedido = urllib.request.Request(servidor_real.url + '/api/workspaces', data=b'', method='POST', headers=cab)
    with urllib.request.urlopen(pedido) as r:
        wid = __import__('json').load(r)['id']
    ws = f'ws://127.0.0.1:{servidor_real.puerto}/api/workspaces/{wid}/ws'
    cookie = f'{seguridad.nombre_cookie(servidor_real.puerto)}={servidor_real.token}'
    with connect(ws, origin=servidor_real.url, additional_headers={'Cookie': cookie}, open_timeout=10):
        pass
    for origen, extra, en_texto in (('http://evil.example', {'Cookie': cookie}, 'origen ajeno'),
                                    (servidor_real.url, {}, 'sin token')):
        with pytest.raises(InvalidStatus) as exc:
            connect(ws, origin=origen, additional_headers=extra, open_timeout=10).close()
        assert exc.value.response.status_code == 403, en_texto


# ------------------------------------------------------------ RF-20, escucha
@pytest.mark.parametrize('host', ['0.0.0.0', '::', '::1', '192.168.1.20', 'puesto.empresa.local'])
def test_fuera_de_esta_maquina_se_niega_y_dice_por_que(host, monkeypatch, capsys):
    """086:RF-20 — no llega a arrancar nada."""
    monkeypatch.setitem(sys.modules, 'uvicorn', types.SimpleNamespace(
        Config=lambda *a, **k: pytest.fail('llegó a configurar el servidor'),
        Server=lambda *a, **k: pytest.fail('llegó a crear el servidor')))
    assert lanzador.main(['--host', host, '--no-browser']) == 1
    error = capsys.readouterr().err
    assert host in error and 'usuarios' in error and 'TLS' in error


def test_la_orden_de_la_cli_tambien_se_niega(monkeypatch, capsys):
    """086:RF-20 — ``convertersmartgrid web --host`` va por el mismo lanzador."""
    from convertersmartgrid.presentacion.cli import main as cli

    assert cli(['web', '--host', '0.0.0.0', '--no-browser']) == 1
    assert 'TLS' in capsys.readouterr().err


def test_arrancado_a_mano_en_la_red_no_atiende_a_otra_maquina(puerta):
    """086:RF-20 — con ``uvicorn --host 0.0.0.0`` no pasa por el lanzador; la puerta mira quién conecta."""
    for peer in ('192.168.1.50', '10.0.0.5'):
        with _cliente(puerta.app, peer=peer) as c:
            r = c.get('/api/health', headers=puerta.con_token)
            assert r.status_code == 403 and 'TLS' in r.json()['detail']
            assert c.get('/').status_code == 403


def test_el_lanzador_crea_la_sesion_tras_decidir_el_puerto(tmp_path, monkeypatch):
    """086:RF-19, 086:RF-20 — el servidor lee el token por su puerto, y sin proxy_headers."""
    configuraciones = []

    class Servidor:
        def __init__(self, config):
            self.should_exit = False
            configuraciones.append(config)

        def run(self):
            self.started = True

    monkeypatch.setitem(sys.modules, 'uvicorn', types.SimpleNamespace(Config=lambda *a, **k: k, Server=Servidor))
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 's'))
    monkeypatch.delenv(sesion_web.VARIABLE_PUERTO, raising=False)
    monkeypatch.delenv('CSG_WEB_HOST', raising=False)
    monkeypatch.setattr(lanzador, 'puerto_ocupado', lambda *_a: False)
    assert lanzador.main(['--port', str(PUERTO), '--no-browser']) == 0
    assert os.environ[sesion_web.VARIABLE_PUERTO] == str(PUERTO)
    assert sesion_web.leer_sesion(PUERTO) is not None
    assert configuraciones[0]['proxy_headers'] is False
    os.environ.pop(sesion_web.VARIABLE_PUERTO, None)


def test_el_navegador_se_abre_con_la_sesion(tmp_path, monkeypatch):
    """086:RF-19 — el lanzador lo entrega al frente: con ella, la página entra sin que el operador haga nada."""
    monkeypatch.setenv(sesion_web.VARIABLE_CARPETA, str(tmp_path / 's'))
    token = sesion_web.crear_sesion(PUERTO).token
    abiertos = []
    monkeypatch.setattr(lanzador.webbrowser, 'open', abiertos.append)
    assert lanzador.mostrar_en_navegador(f'{BASE}/') is True
    assert abiertos == [f'{BASE}/?{sesion_web.PARAMETRO_ACCESO}={token}']


# ------------------------------------------------------------ RF-21, Leaflet y política
@pytest.mark.parametrize('nombre', ['leaflet.js', 'leaflet.css'])
def test_leaflet_propio_con_su_huella_y_licencia(nombre):
    """086:RF-21 — la misma copia que publica Leaflet, sin nada que se haya cambiado en el camino."""
    from convertersmartgrid.adaptadores.preview import CARPETA_LEAFLET, HUELLAS_LEAFLET

    huella = base64.b64encode(hashlib.sha256((CARPETA_LEAFLET / nombre).read_bytes()).digest()).decode()
    assert f'sha256-{huella}' == HUELLAS_LEAFLET[nombre]
    assert 'BSD' in (CARPETA_LEAFLET / 'LICENSE').read_text(encoding='utf-8') or 'Redistribution' in (CARPETA_LEAFLET / 'LICENSE').read_text(encoding='utf-8')


def _modelo_de_vista_previa():
    sys.path.insert(0, str(RAIZ / 'tests'))
    from test_preview import _mini_geo, _mini_model

    return _mini_model(), _mini_geo()


def test_la_vista_previa_no_pide_nada_de_fuera(tmp_path, monkeypatch):
    """086:RF-21 — ni script ni estilo de un CDN; con la salida apagada, tampoco teselas, y lo dice."""
    from convertersmartgrid.adaptadores.preview import write_preview_html

    monkeypatch.setenv(VARIABLE_EDICION, 'producto')
    monkeypatch.delenv(SALIDAS['teselas'].variable, raising=False)
    modelo, geo = _modelo_de_vista_previa()
    texto = write_preview_html(modelo, geo, tmp_path / 'a.html', backend='auto').read_text(encoding='utf-8')
    assert 'unpkg.com' not in texto and 'cdn' not in texto.lower().split('</head>')[0].split('leaflet')[0]
    assert not re.search(r'<(script|link)[^>]+(src|href)=', texto)
    assert 'openstreetmap.org/{z}' not in texto.replace('\\', '')
    assert 'L.tileLayer(' not in texto
    assert 'Sin fondo de mapa' in texto and SALIDAS['teselas'].variable in texto
    assert 'Content-Security-Policy' in texto
    assert 'L.map' in texto            # Leaflet va dentro: el mapa abre igual


def test_vista_previa_no_ejecuta_nombres_de_la_entrega(tmp_path):
    """086:RF-21 — un nombre con «</script>» cerraba el guion y lo que siguiera se ejecutaba."""
    from convertersmartgrid.adaptadores.preview import write_preview_html

    modelo, geo = _modelo_de_vista_previa()
    modelo.network_name = 'A</script><img src=x onerror=alert(1)>'
    modelo.feeder = modelo.network_name
    texto = write_preview_html(modelo, geo, tmp_path / 'a.html', backend='leaflet').read_text(encoding='utf-8')
    cuerpo = texto.split('</head>')[1]
    assert '<img src=x' not in cuerpo


def test_con_teselas_encendidas_abre_y_dice_si_no_llega(tmp_path, monkeypatch):
    """086:RF-22 — encendidas de forma explícita en producto: la capa, su política y el aviso sin red."""
    from convertersmartgrid.adaptadores.preview import ORIGEN_TESELAS, politica_pagina_generada, write_preview_html

    monkeypatch.setenv(VARIABLE_EDICION, 'producto')
    monkeypatch.setenv(SALIDAS['teselas'].variable, '1')
    modelo, geo = _modelo_de_vista_previa()
    texto = write_preview_html(modelo, geo, tmp_path / 'a.html', backend='leaflet').read_text(encoding='utf-8')
    assert 'L.tileLayer(' in texto and "'tileerror'" in texto and 'no se pudo llegar' in texto
    assert ORIGEN_TESELAS in politica_pagina_generada()
    monkeypatch.setenv(SALIDAS['teselas'].variable, '0')
    assert ORIGEN_TESELAS not in politica_pagina_generada()


# ------------------------------------------------------------ RF-63 a RF-66, fondo de calles y satélite
_TESELAS_EN_HTML = re.compile(r'tile\.openstreetmap\.org|arcgisonline\.com|World_Imagery|L\.tileLayer\(')


def test_086_rf63_calles_y_satelite_con_su_selector(tmp_path, monkeypatch):
    """086:RF-63 — dos fondos con su atribución, el selector de capas y calles al abrir; Leaflet sigue dentro (RF-65)."""
    from convertersmartgrid.adaptadores.preview import (ORIGEN_SATELITE, ORIGEN_TESELAS, URL_SATELITE, URL_TESELAS,
                                            politica_pagina_generada, write_preview_html)

    monkeypatch.setenv(VARIABLE_EDICION, 'producto')
    monkeypatch.setenv(SALIDAS['teselas'].variable, '1')
    modelo, geo = _modelo_de_vista_previa()
    texto = write_preview_html(modelo, geo, tmp_path / 'a.html', backend='leaflet').read_text(encoding='utf-8')
    assert URL_TESELAS in texto and URL_SATELITE in texto
    assert URL_SATELITE == 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    assert '&copy; OpenStreetMap' in texto
    assert 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community' in texto
    assert 'L.control.layers(fondos' in texto
    assert texto.index('"nombre": "Calles"') < texto.index('"nombre": "Satélite"')
    assert 'if (i === 0) capa.addTo(map);' in texto           # calles por defecto: el primero
    # La red se añade después y va en su propio panel, por encima de las teselas.
    assert texto.index('L.control.layers(') < texto.index('L.geoJSON(data')
    assert not re.search(r'<(script|link)[^>]+(src|href)=', texto)
    politica = politica_pagina_generada()
    assert ORIGEN_TESELAS in politica and ORIGEN_SATELITE in politica
    assert SALIDAS['teselas'].destino == 'OpenStreetMap y Esri World Imagery'


def test_086_rf64_el_aviso_va_por_capa(tmp_path, monkeypatch):
    """086:RF-64 — cada fondo avisa una vez con su nombre si no llega; la red se dibuja igual."""
    from convertersmartgrid.adaptadores.preview import write_preview_html

    monkeypatch.setenv(SALIDAS['teselas'].variable, '1')
    modelo, geo = _modelo_de_vista_previa()
    texto = write_preview_html(modelo, geo, tmp_path / 'a.html', backend='leaflet').read_text(encoding='utf-8')
    assert "capa.once('tileerror'" in texto and 'sinFondo.push(f.aviso)' in texto
    assert 'OpenStreetMap (calles)' in texto and 'Esri World Imagery (satélite)' in texto
    assert 'La red se dibuja igual.' in texto


def test_086_rf65_sin_la_salida_ni_una_direccion_de_teselas(tmp_path, monkeypatch):
    """086:RF-65 — apagada por la edición, por la variable o por lo guardado: ninguna tesela en el HTML."""
    from convertersmartgrid.adaptadores.preview import politica_pagina_generada, write_preview_html
    from convertersmartgrid.dominio.salidas_red import guardar_salida

    modelo, geo = _modelo_de_vista_previa()
    monkeypatch.delenv(SALIDAS['teselas'].variable, raising=False)
    casos = []
    monkeypatch.setenv(VARIABLE_EDICION, 'producto')
    casos.append(write_preview_html(modelo, geo, tmp_path / 'edicion.html', backend='leaflet'))
    monkeypatch.delenv(VARIABLE_EDICION)
    guardar_salida('teselas', False)
    casos.append(write_preview_html(modelo, geo, tmp_path / 'equipo.html', backend='leaflet'))
    guardar_salida('teselas', True)
    monkeypatch.setenv(SALIDAS['teselas'].variable, '0')
    casos.append(write_preview_html(modelo, geo, tmp_path / 'variable.html', backend='leaflet'))
    for ruta in casos:
        texto = ruta.read_text(encoding='utf-8')
        assert not _TESELAS_EN_HTML.search(texto), ruta.name
        assert 'L.control.layers' not in texto and 'Sin fondo de mapa' in texto
        assert 'L.map' in texto                                    # Leaflet dentro, el mapa abre igual
    assert 'arcgisonline' not in politica_pagina_generada()


def test_086_rf66_la_variable_manda_luego_el_equipo_luego_la_edicion(tmp_path, monkeypatch):
    """086:RF-66 — precedencia de la salida: variable, lo guardado en el equipo y, sin nada, la edición."""
    from convertersmartgrid.dominio.salidas_red import (VARIABLE_RUTA_GUARDADAS, estado_salida, guardar_salida,
                                                ruta_guardadas, salidas_guardadas)

    variable = SALIDAS['teselas'].variable
    monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv(VARIABLE_RUTA_GUARDADAS, str(tmp_path / 'config' / 'salidas.json'))
    monkeypatch.setenv(VARIABLE_EDICION, 'producto')
    assert estado_salida('teselas') == (False, 'edicion')
    monkeypatch.delenv(VARIABLE_EDICION)
    assert estado_salida('teselas') == (True, 'edicion')
    monkeypatch.setenv(VARIABLE_EDICION, 'producto')
    guardar_salida('teselas', True)
    assert json.loads(ruta_guardadas().read_text(encoding='utf-8')) == {'teselas': True}
    assert estado_salida('teselas') == (True, 'equipo') and salida_permitida('teselas') is True
    monkeypatch.setenv(variable, '0')
    assert estado_salida('teselas') == (False, 'variable') and salida_permitida('teselas') is False
    guardar_salida('teselas', False)
    monkeypatch.setenv(variable, '1')
    assert estado_salida('teselas') == (True, 'variable')
    monkeypatch.delenv(variable)
    assert estado_salida('teselas') == (False, 'equipo')
    # Lo guardado solo vale para las que se cambian desde la web; un fichero roto es nada guardado.
    ruta_guardadas().write_text('{"internet": true, "teselas": "si"}', encoding='utf-8')
    assert salidas_guardadas() == {} and estado_salida('internet') == (False, 'edicion')
    ruta_guardadas().write_text('{roto', encoding='utf-8')
    assert estado_salida('teselas') == (False, 'edicion')
    with pytest.raises(ValueError):
        guardar_salida('internet', True)


def test_086_rf67_lo_guardado_va_en_la_carpeta_local_fuera_de_git(tmp_path, monkeypatch):
    """086:RF-67 — junto a ``config/powerfactory.json``, en la carpeta local, y ``.gitignore`` lo deja fuera."""
    from convertersmartgrid.dominio import runtime_paths
    from convertersmartgrid.dominio.salidas_red import VARIABLE_RUTA_GUARDADAS, ruta_guardadas

    monkeypatch.delenv(VARIABLE_RUTA_GUARDADAS)
    monkeypatch.setattr(runtime_paths, 'raiz_local', lambda programa=None, environ=None: tmp_path / 'datos')
    assert ruta_guardadas() == tmp_path / 'datos' / 'config' / 'salidas.json'
    ignorados = (RAIZ / '.gitignore').read_text(encoding='utf-8').splitlines()
    assert 'config/salidas.json' in ignorados and 'config/powerfactory.json' in ignorados


def test_la_web_sirve_sus_paginas_con_politica(tmp_path, puerta):
    """086:RF-21 — la de la interfaz en todo, y la aislada en una página generada."""
    wid = _espacio(puerta)
    store = puerta.app.state.store
    salida = store.get(wid).out_dir
    salida.mkdir(parents=True, exist_ok=True)
    (salida / 'mapa.html').write_text('<html>mapa</html>', encoding='utf-8')
    with _cliente(puerta.app) as c:
        r = c.get('/api/health', headers=puerta.con_token)
        politica = r.headers['content-security-policy']
        assert "script-src 'self'" in politica and "frame-ancestors 'none'" in politica
        assert 'unsafe-inline' not in politica and 'http' not in politica.replace(f'ws://127.0.0.1:{PUERTO}', '')
        assert f'ws://127.0.0.1:{PUERTO}' in politica
        assert r.headers['x-content-type-options'] == 'nosniff'
        r = c.get(f'/api/workspaces/{wid}/files/mapa.html', headers=puerta.con_token)
        assert r.status_code == 200 and r.headers['content-type'].startswith('text/html')
        politica = r.headers['content-security-policy']
        assert politica.startswith('sandbox allow-scripts') and "default-src 'none'" in politica
        assert 'connect-src' not in politica      # con default-src 'none': ni a la API ni a fuera


def _como_iframe_propio(puerta) -> dict:
    """Lo que manda Chrome al cargar el ``src`` de un iframe de la propia web: la cookie de la sesión (SameSite=Strict
    la envía, porque el marco y su página son del mismo sitio), ni Origin ni token en cabecera, y ``Sec-Fetch-Dest``."""
    return {'Cookie': f'{seguridad.nombre_cookie(PUERTO)}={puerta.token}', 'Accept': 'text/html,application/xhtml+xml',
            'Sec-Fetch-Dest': 'iframe', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'same-origin'}


def _directivas_de_marco(politica: str) -> list[str]:
    return [d.strip() for d in politica.split(';') if d.strip().lower().startswith('frame-ancestors')]


def _marco(r) -> tuple[str | None, list[str]]:
    """``X-Frame-Options`` (una sola) y los ``frame-ancestors`` de todas las políticas de la respuesta."""
    opciones = r.headers.get_list('x-frame-options')
    politicas = r.headers.get_list('content-security-policy')
    return (opciones[0] if len(opciones) == 1 else repr(opciones)), [d for p in politicas for d in _directivas_de_marco(p)]


def _se_deja_enmarcar_solo_por_la_web(r) -> None:
    assert r.status_code == 200, r.text[:200]
    assert 'location' not in r.headers                      # ni redirección a «/» ni a ningún sitio
    assert _marco(r) == ('SAMEORIGIN', ["frame-ancestors 'self'"]), _marco(r)   # una sola de cada, la de la puerta
    politica = r.headers['content-security-policy']
    assert "frame-ancestors 'self'" in politica and "frame-ancestors 'none'" not in politica
    # Sigue aislada (086:RF-21): sin origen propio ni alcance a la API.
    assert politica.startswith('sandbox allow-scripts') and "default-src 'none'" in politica
    assert 'connect-src' not in politica


def test_086_rf21_el_mapa_de_cargas_se_ve_en_su_marco(puerta):
    """086:RF-21 — el mapa de las cargas nuevas (MapaCargas.tsx) va en un iframe de la propia web. La revisión en pantalla
    del 2026-11-14 lo vio en blanco: «Refused to display … in a frame because it set 'X-Frame-Options' to 'deny'». La
    ruta ponía su propia política sin ``frame-ancestors``, pero la puerta le añadía ``X-Frame-Options: DENY``."""
    wid = _espacio(puerta)
    with _cliente(puerta.app) as c:
        r = c.get(f'/api/workspaces/{wid}/mapa-cargas/pagina', params={'project': 'PRY'},
                  headers=_como_iframe_propio(puerta))
    _se_deja_enmarcar_solo_por_la_web(r)
    assert 'L.map(' in r.text


@pytest.mark.parametrize('fichero', ['mapa.html', 'sub/Vista.HTML'])
def test_086_rf21_la_vista_previa_se_ve_en_su_marco(puerta, fichero):
    """086:RF-21 — la vista previa de un alimentador (Modules.tsx) va en el mismo tipo de marco que el mapa."""
    wid = _espacio(puerta)
    destino = puerta.app.state.store.get(wid).out_dir / fichero
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text('<html>mapa</html>', encoding='utf-8')
    with _cliente(puerta.app) as c:
        r = c.get(f'/api/workspaces/{wid}/files/{fichero}', headers=_como_iframe_propio(puerta))
    _se_deja_enmarcar_solo_por_la_web(r)


def test_086_rf21_lo_demas_no_se_deja_enmarcar(puerta):
    """086:RF-21 — solo las dos páginas que la web incrusta se dejan enmarcar, y solo por ella. La interfaz, la API, una
    descarga, un fichero que no es HTML, una ruta que solo se parece y el rechazo sin sesión siguen con DENY y 'none'."""
    wid = _espacio(puerta)
    salida = puerta.app.state.store.get(wid).out_dir
    salida.mkdir(parents=True, exist_ok=True)
    (salida / 'mapa.html').write_text('<html>mapa</html>', encoding='utf-8')
    (salida / 'datos.json').write_text('{}', encoding='utf-8')
    iframe = _como_iframe_propio(puerta)
    with _cliente(puerta.app) as c:
        respuestas = {
            'interfaz': c.get('/', headers=iframe),
            'salud': c.get('/api/health', headers=iframe),
            'datos del mapa': c.get(f'/api/workspaces/{wid}/mapa-cargas', params={'project': 'PRY'}, headers=iframe),
            'json': c.get(f'/api/workspaces/{wid}/files/datos.json', headers=iframe),
            'descarga': c.get(f'/api/workspaces/{wid}/files/mapa.html', params={'download': 'true'}, headers=iframe),
            'descarga 1': c.get(f'/api/workspaces/{wid}/files/mapa.html', params={'download': '1'}, headers=iframe),
            'parecida': c.get(f'/api/workspaces/{wid}/mapa-cargas/pagina/otra', params={'project': 'PRY'},
                              headers=iframe),
        }
        sin_sesion = c.get(f'/api/workspaces/{wid}/mapa-cargas/pagina', params={'project': 'PRY'},
                           headers={**iframe, 'Cookie': f'{seguridad.nombre_cookie(PUERTO)}=caducada'})
    for nombre, r in respuestas.items():
        assert r.headers.get('x-frame-options') == 'DENY', nombre
        politica = r.headers.get('content-security-policy', '')
        assert "frame-ancestors 'self'" not in politica, nombre
        if not politica.startswith('sandbox'):
            assert "frame-ancestors 'none'" in politica, nombre
    # Sin sesión, la página que lo dice tampoco se deja enmarcar por nadie.
    assert sin_sesion.status_code == 401
    assert sin_sesion.headers.get('x-frame-options') == 'DENY'
    assert "frame-ancestors 'none'" in sin_sesion.headers.get('content-security-policy', '')


def _puerta_sobre(rutas: dict[str, str | None]) -> tuple[TestClient, dict]:
    """La puerta, sola, delante de unas rutas de prueba con la política que cada una ponga (``None``: ninguna)."""
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse
    from starlette.routing import Route

    def pagina(politica):
        return lambda _peticion: HTMLResponse('<html>x</html>',
                                              headers={'Content-Security-Policy': politica} if politica else None)

    interior = Starlette(routes=[Route(ruta, pagina(p)) for ruta, p in rutas.items()])
    sesion = sesion_web.Sesion('token-de-prueba')
    app = seguridad.SeguridadWeb(interior, sesion=sesion)
    cookie = {'Cookie': f'{seguridad.nombre_cookie(PUERTO)}={sesion.token}', 'Accept': 'text/html',
              'Sec-Fetch-Dest': 'iframe', 'Sec-Fetch-Site': 'same-origin'}
    return _cliente(app), cookie


def test_086_rf21_una_incrustable_sin_sandbox_no_se_deja_enmarcar():
    """086:RF-21 — falla cerrado (condición del auditor ca): el aislamiento lo pone la ruta con «sandbox» en su política.
    Si una ruta que casa con las incrustables llega sin él (un cambio en app.py:1767 o en mapa_cargas_api.py:154), la
    puerta no la deja enmarcar: DENY y frame-ancestors 'none', como cualquier otra."""
    sin_sandbox = "default-src 'none'; script-src 'unsafe-inline'"
    cliente, cookie = _puerta_sobre({'/api/workspaces/w1/mapa-cargas/pagina': sin_sandbox,
                                     '/api/workspaces/w1/files/vista.html': None,
                                     '/api/workspaces/w1/files/otra.html': f"{sin_sandbox}; img-src data: sandbox.example"})
    with cliente as c:
        for ruta in ('/api/workspaces/w1/mapa-cargas/pagina', '/api/workspaces/w1/files/vista.html',
                     '/api/workspaces/w1/files/otra.html'):
            r = c.get(ruta, headers=cookie)
            assert r.status_code == 200, ruta
            assert r.headers['x-frame-options'] == 'DENY', ruta
            politica = r.headers['content-security-policy']
            assert "frame-ancestors 'self'" not in politica, ruta
            assert "frame-ancestors 'none'" in politica, ruta


def test_086_rf21_una_incrustable_con_sandbox_se_deja_enmarcar_por_la_web():
    """086:RF-21 — la que sí pone «sandbox» como directiva sigue con SAMEORIGIN y frame-ancestors 'self', y aislada."""
    from convertersmartgrid.adaptadores.preview import politica_pagina_generada

    cliente, cookie = _puerta_sobre({'/api/workspaces/w1/mapa-cargas/pagina': politica_pagina_generada(),
                                     '/api/workspaces/w1/files/vista.html': 'SANDBOX allow-scripts; default-src \'none\''})
    with cliente as c:
        for ruta in ('/api/workspaces/w1/mapa-cargas/pagina', '/api/workspaces/w1/files/vista.html'):
            r = c.get(ruta, headers=cookie)
            assert r.status_code == 200, ruta
            assert r.headers['x-frame-options'] == 'SAMEORIGIN', ruta
            politica = r.headers['content-security-policy']
            assert "frame-ancestors 'self'" in politica and "frame-ancestors 'none'" not in politica, ruta
            assert politica.lower().startswith('sandbox allow-scripts'), ruta


# ------------------------------------------------------------ RF-21, la puerta decide los marcos de toda respuesta
#: Las tres pantallas que enmarcan una página de la propia web (MapaCargas.tsx, Modules.tsx y PlanoRed.tsx), por su
#: plantilla. La del plano faltaba (111:RF-14): su marco salía en blanco en el navegador («frame-ancestors 'none'»),
#: lo encontró la medición en navegador real de 111 T2.
_ENMARCADAS = {'/api/workspaces/{wid}/mapa-cargas/pagina', '/api/workspaces/{wid}/files/{rel:path}',
               '/api/workspaces/{wid}/plano/pagina'}
_DATOS_MAPA = {'project': 'PRY', 'alimentadores': {'AL1': {'tramos': [['L1', [[-13.49, -76.01], [-13.5, -76.0]]]],
                                                           'cabecera': None}},
               'cargas': [{'sed': 'SE1', 'alimentador': 'AL1', 'kw': 5, 'sola': True,
                           'punto': {'lat': -13.5, 'lon': -76.0, 'utm': None},
                           'nodo': {'nombre': 'N1', 'lat': -13.5, 'lon': -76.0, 'utm': None}, 'enlace': None,
                           'corregida': False}], 'avisos': [], 'repetir_flujos': []}
_AISLADA = b"sandbox allow-scripts; default-src 'none'"


def _plantillas(app) -> list:
    """Cada ruta de la aplicación, también las del enrutador incluido (VNR-GIS), con su plantilla entera."""
    salida = []

    def recorrer(rutas, prefijo=''):
        for ruta in rutas:
            incluido = getattr(ruta, 'original_router', None)
            if incluido is not None:
                contexto = getattr(ruta, 'include_context', None)
                recorrer(incluido.routes, prefijo + (getattr(contexto, 'prefix', '') or ''))
            elif hasattr(ruta, 'path'):
                salida.append((prefijo + ruta.path, ruta))
    recorrer(app.routes)
    return salida


def _ruta_concreta(plantilla: str) -> str:
    return re.sub(r'\{([^}:]+)(?::([^}]+))?\}',
                  lambda m: {'path': 'carpeta/pagina.html', 'int': '1', 'float': '1.0'}.get(m.group(2) or '', 'x1'),
                  plantilla)


def _puerta_que_responde(cabeceras: list, cuerpo: bytes = b'<html>x</html>', estado: int = 200) -> TestClient:
    """La puerta delante de una aplicación que responde siempre lo mismo a todo: decide la puerta, no la ruta.

    Sin ``with``: es una aplicación ASGI mínima, sin ``lifespan``."""
    async def app(scope, receive, send):
        await send({'type': 'http.response.start', 'status': estado,
                    'headers': [*cabeceras, (b'content-length', str(len(cuerpo)).encode())]})
        await send({'type': 'http.response.body', 'body': cuerpo})
    return _cliente(seguridad.SeguridadWeb(app, sesion=sesion_web.Sesion('t' * 32)))


_CON_TOKEN_DE_PRUEBA = {sesion_web.CABECERA_TOKEN: 't' * 32, 'Origin': BASE}


def test_086_rf21_toda_otra_ruta_sigue_sin_dejarse_enmarcar(puerta):
    """086:RF-21 — recorre las rutas de la aplicación (``app.routes``, con el enrutador incluido, y cotejado con el
    contrato OpenAPI): solo las dos de la lista se dejan enmarcar, solo por GET y solo por el mismo origen. Las demás,
    también si responden una página HTML aislada que pide dejarse enmarcar por cualquiera (``frame-ancestors *`` y
    ``SAMEORIGIN``), salen con una sola ``DENY`` y ``frame-ancestors 'none'``: la cabecera de la ruta no cuenta."""
    rutas = _plantillas(puerta.app)
    plantillas = {p for p, _r in rutas}
    assert _ENMARCADAS <= plantillas, _ENMARCADAS - plantillas        # las tres son rutas que existen
    sin_conversor = {re.sub(r':[^}]+\}', '}', p) for p in plantillas}
    assert set(puerta.app.openapi()['paths']) <= sin_conversor
    pagina_que_pide_marco = [(b'content-type', b'text/html; charset=utf-8'),
                             (b'content-security-policy', _AISLADA + b'; frame-ancestors *'),
                             (b'x-frame-options', b'SAMEORIGIN')]
    clientes = {'html': _puerta_que_responde(pagina_que_pide_marco),
                'json': _puerta_que_responde([(b'content-type', b'application/json')], b'{}')}
    vistas, malas = 0, []
    for plantilla, ruta in rutas:
        metodos = sorted((getattr(ruta, 'methods', None) or set()) - {'HEAD'})
        if not metodos:              # el WebSocket: no tiene respuesta HTTP que enmarcar
            continue
        concreta = _ruta_concreta(plantilla)
        for metodo in metodos:
            for nombre, cliente in clientes.items():
                r = cliente.request(metodo, concreta, headers=_CON_TOKEN_DE_PRUEBA)
                propia = plantilla in _ENMARCADAS and nombre == 'html' and metodo == 'GET'
                esperado = ('SAMEORIGIN', ["frame-ancestors 'self'"]) if propia else ('DENY', ["frame-ancestors 'none'"])
                vistas += 1
                if r.status_code != 200 or _marco(r) != esperado:
                    malas.append((metodo, plantilla, nombre, r.status_code, _marco(r)))
    assert vistas > 300 and not malas, (vistas, len(malas), malas[:10])
    # La lista va en el código con su nombre, y son esas dos: una tercera se añade a propósito, aquí y en la spec.
    assert set(getattr(seguridad, 'RUTAS_ENMARCABLES', ())) == _ENMARCADAS


def test_086_rf21_un_error_o_una_descarga_de_las_enmarcables_no_se_enmarca(puerta, monkeypatch):
    """086:RF-21 — en las dos rutas de la lista solo se enmarca una página HTML aislada que se abre en el sitio. Un error
    JSON (aunque traiga la política aislada) o la misma página servida como descarga (``attachment``) llevan ``DENY``."""
    from convertersmartgrid.presentacion.web import mapa_cargas_api

    vista = '/api/workspaces/w1/files/carpeta/vista.html'
    casos = {
        'error json': ([(b'content-type', b'application/json'), (b'content-security-policy', _AISLADA)], 404, False),
        'descarga': ([(b'content-type', b'text/html; charset=utf-8'), (b'content-security-policy', _AISLADA),
                      (b'content-disposition', b'attachment; filename="vista.html"')], 200, False),
        'en el sitio': ([(b'content-type', b'text/html; charset=utf-8'), (b'content-security-policy', _AISLADA),
                         (b'content-disposition', b'inline')], 200, True),
    }
    for nombre, (cabeceras, estado, se_enmarca) in casos.items():
        for ruta in (vista, '/api/workspaces/w1/mapa-cargas/pagina'):
            r = _puerta_que_responde(cabeceras, estado=estado).get(ruta, headers=_CON_TOKEN_DE_PRUEBA)
            esperado = ('SAMEORIGIN', ["frame-ancestors 'self'"]) if se_enmarca else ('DENY', ["frame-ancestors 'none'"])
            assert r.status_code == estado and _marco(r) == esperado, (nombre, ruta, _marco(r))
    # Por la web de verdad: un fichero que no existe y el mapa sin su proyecto son errores JSON de esas rutas.
    monkeypatch.setattr(mapa_cargas_api, 'datos_para_la_web', lambda _ws, _p, _a: _DATOS_MAPA)
    wid = _espacio(puerta)
    with _cliente(puerta.app) as c:
        for ruta in (f'/api/workspaces/{wid}/files/no_esta.html', f'/api/workspaces/{wid}/mapa-cargas/pagina'):
            r = c.get(ruta, headers=puerta.con_token)
            assert r.status_code >= 400 and _marco(r) == ('DENY', ["frame-ancestors 'none'"]), (ruta, r.status_code,
                                                                                               _marco(r))


def test_086_rf21_lo_que_rechaza_la_puerta_tampoco_se_deja_enmarcar(puerta):
    """086:RF-21 — la página de «sin sesión» (401), el rechazo por Host u Origin (403) y la entrada con el enlace del
    lanzador (303) no las genera ninguna ruta: las cabeceras de marco las pone la puerta."""
    with _cliente(puerta.app) as c:
        respuestas = {
            '401': (c.get('/api/health', headers={'Accept': 'text/html'}), 401),
            '403 host': (c.get('/api/health', headers={**puerta.con_token, 'Host': 'evil.example'}), 403),
            '403 origin': (c.post('/api/workspaces', headers={**puerta.con_token, 'Origin': 'http://evil.example'}), 403),
            '303': (c.get(f'/?{sesion_web.PARAMETRO_ACCESO}={puerta.token}'), 303),
        }
    for nombre, (r, estado) in respuestas.items():
        assert r.status_code == estado and _marco(r) == ('DENY', ["frame-ancestors 'none'"]), (nombre, r.status_code,
                                                                                               _marco(r))


def test_086_rf21_las_teselas_por_sus_servidores_exactos(tmp_path, monkeypatch):
    """086:RF-21 — las páginas enmarcadas no piden nada de fuera salvo las teselas, y la política nombra cada servidor
    sin comodín: los que salen de la dirección de cada fondo con los subdominios de Leaflet. Comprobado en el HTML
    generado de las dos páginas, no en las constantes."""
    from convertersmartgrid.adaptadores import mapa_cargas as mc
    from convertersmartgrid.adaptadores.preview import (CARPETA_LEAFLET, FONDOS_MAPA, politica_pagina_generada, recurso_leaflet,
                                            write_preview_html)

    monkeypatch.setenv('CSG_SALIDA_TESELAS', '1')
    (subdominios,) = re.findall(r'subdomains:"([a-z]+)"', (CARPETA_LEAFLET / 'leaflet.js').read_text(encoding='utf-8'))
    servidores = set()
    for _n, url, *_resto in FONDOS_MAPA:
        origen = re.match(r'https://[^/]+', url).group(0)
        servidores |= {origen.replace('{s}', s) for s in subdominios} if '{s}' in origen else {origen}
    politica = politica_pagina_generada()
    (imagenes,) = [d for d in politica.split(';') if d.strip().startswith('img-src')]
    assert set(imagenes.split()[1:]) == {'data:', *servidores}, imagenes
    assert '*' not in politica
    pagina_mapa = mc.pagina_del_mapa(_DATOS_MAPA)
    vista = write_preview_html(*_modelo_de_vista_previa(), tmp_path / 'v.html', backend='leaflet').read_text(encoding='utf-8')
    for html_generado in (pagina_mapa, vista):
        for propio in ('leaflet.js', 'leaflet.css'):       # su huella la comprueba test_leaflet_propio_con_su_huella
            assert recurso_leaflet(propio) in html_generado
            html_generado = html_generado.replace(recurso_leaflet(propio), '')
        assert not re.search(r'<(script|link|iframe|img)[^>]+(src|href)=["\']?https?:', html_generado)
        pedidos = {re.match(r'https://[^/]+', u).group(0) for u in re.findall(r'https://[^\s"\'\\;]+', html_generado)}
        pedidos = {p for p in pedidos if '{s}' not in p} | {p.replace('{s}', s) for p in pedidos if '{s}' in p
                                                            for s in subdominios}
        assert pedidos <= servidores, pedidos - servidores


def test_086_rf21_la_hoja_de_seguridad_dice_que_se_enmarca_y_que_sale():
    """086:RF-21 — el responsable de sistemas lee en la hoja qué páginas se enmarcan y a qué servidores piden teselas."""
    from convertersmartgrid.adaptadores.preview import ORIGEN_SATELITE, ORIGEN_TESELAS

    hoja = (RAIZ / 'docs/SEGURIDAD_Y_PRIVACIDAD.md').read_text(encoding='utf-8')
    for texto in ('SAMEORIGIN', "frame-ancestors 'self'", "frame-ancestors 'none'", 'DENY',
                  'Ubicación de las cargas nuevas', 'vista previa del alimentador', *ORIGEN_TESELAS.split(),
                  ORIGEN_SATELITE):
        assert texto in hoja, texto


def test_el_frente_no_pide_nada_de_fuera():
    """086:RF-21 — ni guiones ni estilos de terceros en la interfaz."""
    index = (RAIZ / 'frontend' / 'index.html').read_text(encoding='utf-8')
    assert not re.search(r'<(script|link)[^>]+(src|href)=["\']https?:', index)
    estilos = (RAIZ / 'frontend' / 'src' / 'shared' / 'styles.css').read_text(encoding='utf-8')
    assert not re.search(r'@import|url\(["\']?https?:', estilos)


# ------------------------------------------------------------ RF-22, salidas
_PRIMITIVAS_RED = re.compile(
    r'urllib\.request\.(urlopen|build_opener)|requests\.(get|post|put|Session|request)\(|httpx\.'
    r'|hf_hub_download\(|snapshot_download\(|socket\.create_connection|shutil\.which\(.codex.\)')
#: Lo que abre una conexión, pero no sale de la máquina o no se entrega.
_SIN_SALIDA = {
    'src/convertersmartgrid/presentacion/web/__main__.py': 'el lanzador, a su propia web de 127.0.0.1',
    'src/convertersmartgrid/aplicacion/asistente/ejecutor.py': 'la API de la web, solo local (asistente/equipo.py)',
    'src/convertersmartgrid/presentacion/web/services.py': 'el cliente del asistente, a la propia web',
    'src/convertersmartgrid/aplicacion/asistente/ollama.py': 'Ollama en esta máquina (LOCALES)',
    'src/convertersmartgrid/aplicacion/asistente/embeddings.py': 'local_files_only: lee la caché de modelos',
    'tools/sistema_web.py': 'a la propia web',
    'tools/validar_totalidad_vnr.py': 'a la propia web',
    'tools/verify_architecture_links.py': 'herramienta de desarrollo, no se entrega (T19)',
    'tools/verify_interactive_architecture.mjs': 'herramienta de desarrollo, no se entrega (T19)',
}


def test_toda_salida_a_la_red_esta_declarada():
    """086:RF-22 — recorre el código: quien abra la red sin estar en la lista hace fallar esta prueba."""
    declaradas = {m for s in SALIDAS.values() for m in s.modulos}
    encontradas = set()
    for carpeta in ('src', 'tools'):
        for fichero in (RAIZ / carpeta).rglob('*.py'):
            rel = fichero.relative_to(RAIZ).as_posix()
            if rel in ('src/convertersmartgrid/dominio/salidas_red.py',):
                continue
            if _PRIMITIVAS_RED.search(fichero.read_text(encoding='utf-8', errors='replace')):
                encontradas.add(rel)
    sin_declarar = encontradas - declaradas - set(_SIN_SALIDA)
    assert not sin_declarar, f'Abren la red sin declararlo en salidas_red.SALIDAS: {sorted(sin_declarar)}'
    for salida in SALIDAS.values():
        for modulo in salida.modulos:
            assert (RAIZ / modulo).is_file(), modulo
            assert 'salida_permitida' in (RAIZ / modulo).read_text(encoding='utf-8'), f'{modulo} no comprueba su salida'


def test_edicion_y_salidas_por_defecto(monkeypatch):
    """086:RF-22 — en desarrollo como hasta ahora; en producto, apagadas; la variable manda en las dos."""
    for s in SALIDAS.values():
        monkeypatch.delenv(s.variable, raising=False)
    monkeypatch.delenv(VARIABLE_EDICION, raising=False)
    assert es_edicion_producto() is False
    assert all(salida_permitida(n) for n in SALIDAS)
    monkeypatch.setenv(VARIABLE_EDICION, 'producto')
    assert es_edicion_producto() is True
    for nombre, salida in SALIDAS.items():
        assert salida_permitida(nombre) is False
        with pytest.raises(SalidaApagada, match=salida.variable):
            exigir_salida(nombre)
        monkeypatch.setenv(salida.variable, '1')
        assert salida_permitida(nombre) is True
        monkeypatch.delenv(salida.variable)
    monkeypatch.delenv(VARIABLE_EDICION)
    monkeypatch.setenv(SALIDAS['vias'].variable, '0')
    assert salida_permitida('vias') is False


@pytest.fixture
def producto(monkeypatch, tmp_path):
    for s in SALIDAS.values():
        monkeypatch.delenv(s.variable, raising=False)
    monkeypatch.setenv(VARIABLE_EDICION, 'producto')
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))


def _no_debe_salir(*_a, **_k):
    pytest.fail('Salió a la red con la salida apagada')


def test_internet_apagado_no_consulta(producto):
    """086:RF-22 — búsquedas del asistente: ni GitHub, ni PyPI, ni arXiv."""
    from convertersmartgrid.aplicacion.asistente.internet import Buscador

    r = Buscador(abrir=_no_debe_salir)._consultar('github', 'pandas', 'prueba', _no_debe_salir)
    assert r['resultados'] == [] and SALIDAS['internet'].variable in r['bloqueada']


def test_vias_apagado_va_en_recta_y_lo_dice(producto):
    """086:RF-22 — OSRM: el enlace sale en recta, con el aviso de cómo se activa."""
    from convertersmartgrid.aplicacion.vias import ruta_por_vias

    ruta = ruta_por_vias((-14.0, -75.7), (-14.1, -75.8), {'servicio': 'osrm', 'url': 'http://osrm.example'},
                         pedir=_no_debe_salir)
    assert ruta.por_via is False and SALIDAS['vias'].variable in ruta.avisos[0]


def test_vias_encendido_de_forma_explicita(producto, monkeypatch):
    """086:RF-22 — con su variable, en producto, sí consulta."""
    from convertersmartgrid.aplicacion.vias import ruta_por_vias

    monkeypatch.setenv(SALIDAS['vias'].variable, '1')
    llamadas = []

    def pedir(url, _t):
        llamadas.append(url)
        raise OSError('sin red')

    assert ruta_por_vias((-14.0, -75.7), (-14.1, -75.8), {'servicio': 'osrm', 'url': 'http://osrm.example'},
                         pedir=pedir).por_via is False
    assert llamadas


def test_codex_apagado_no_lo_lanza(producto, monkeypatch):
    """086:RF-22 — el maestro de destilación, ni anotando una consulta que no sale."""
    import shutil
    from convertersmartgrid.aplicacion.asistente import destilacion

    monkeypatch.setattr(shutil, 'which', _no_debe_salir)
    monkeypatch.setattr(destilacion.almacen, 'anotar', _no_debe_salir)
    assert destilacion.MaestroCodex(vocab={}).interpretar('una orden') is None


def test_portal_vnr_apagado_no_conecta(producto, monkeypatch, tmp_path):
    """086:RF-22 — buscar y bajar paquetes de Osinergmin; un paquete ya en disco se sigue usando."""
    import requests

    from convertersmartgrid.adaptadores.entrada.vnr.discovery import download, official

    monkeypatch.setattr(requests, 'get', _no_debe_salir)
    with pytest.raises(official.OfficialDiscoveryError, match=SALIDAS['vnr_oficial'].variable):
        official._fetch_html(official.PORTAL_VNR)
    descargador = next(v for k, v in vars(download).items()
                       if isinstance(v, type) and hasattr(v, 'download') and v.__module__ == download.__name__)
    url = 'https://www.osinergmin.gob.pe/x.zip'
    with pytest.raises(download.DownloadError, match=SALIDAS['vnr_oficial'].variable):
        descargador(tmp_path / 'cache').download(url, tmp_path / 'x.zip')


def test_arcgis_apagado_no_conecta(producto, monkeypatch):
    """086:RF-22 — un servidor ArcGIS, aunque lo indique el usuario."""
    import requests

    from convertersmartgrid.adaptadores.entrada.vnr.connectors.arcgis import ArcGISError, ArcGISLayer

    monkeypatch.setattr(requests, 'get', _no_debe_salir)
    with pytest.raises(ArcGISError, match=SALIDAS['arcgis'].variable):
        ArcGISLayer('https://arcgis.example/capa').metadata()


def _resuelve_a(monkeypatch, ip):
    """El DNS de las pruebas: cualquier nombre resuelve a ``ip``; ninguna prueba consulta un DNS real."""
    def getaddrinfo(host, port, *_a, **_k):
        familia = socket.AF_INET6 if ':' in ip else socket.AF_INET
        return [(familia, socket.SOCK_STREAM, 6, '', (ip, port or 0))]
    monkeypatch.setattr(socket, 'getaddrinfo', getaddrinfo)


#: Destinos que el usuario no debe poder dar: la propia máquina, los metadatos de la nube, ficheros y otros protocolos.
_DESTINOS_VEDADOS = ('http://127.0.0.1/arcgis/rest/services/Red/MapServer', 'http://169.254.169.254/latest/meta-data',
                     'file:///etc/passwd', 'ftp://servidor.example/capa', 'http://[::1]/capa', 'http://0.0.0.0/capa',
                     'https:///sin-host')


@pytest.mark.parametrize('url', _DESTINOS_VEDADOS)
def test_arcgis_rechaza_destinos_locales_y_otros_protocolos(url, monkeypatch):
    """086:RF-22 — la URL del usuario llegaba tal cual a ``requests.get``: SSRF hacia la máquina o la nube."""
    import requests

    from convertersmartgrid.adaptadores.entrada.vnr.connectors.arcgis import ArcGISError, ArcGISLayer

    monkeypatch.setenv(SALIDAS['arcgis'].variable, '1')
    _resuelve_a(monkeypatch, '93.184.216.34')
    monkeypatch.setattr(requests, 'get', _no_debe_salir)
    with pytest.raises(ArcGISError):
        ArcGISLayer(url)


def test_arcgis_rechaza_un_nombre_que_resuelve_a_la_red_privada(monkeypatch):
    """086:RF-22 — el nombre se resuelve y se mira cada IP: un DNS que apunta a 10.0.0.5 no se consulta."""
    import requests

    from convertersmartgrid.adaptadores.entrada.vnr.connectors.arcgis import ArcGISError, ArcGISLayer

    monkeypatch.setenv(SALIDAS['arcgis'].variable, '1')
    _resuelve_a(monkeypatch, '10.0.0.5')
    monkeypatch.setattr(requests, 'get', _no_debe_salir)
    with pytest.raises(ArcGISError, match='10.0.0.5'):
        ArcGISLayer('https://capas.example/arcgis/rest/services/Red/MapServer/0')


def _servidor_falso(monkeypatch, *respuestas):
    """La red de las pruebas, por debajo de requests: cada petición la contesta el pool de urllib3 con la siguiente
    de ``respuestas`` (código, cuerpo, cabeceras) y se anota a qué IP iba el pool y con qué nombre de TLS y Host."""
    import io

    import urllib3

    cola, pedidas = list(respuestas), []

    def urlopen(pool, method, url, body=None, headers=None, **_k):
        pedidas.append({'ip': pool.host, 'host': (headers or {}).get('Host'), 'url': url,
                        'sni': pool.conn_kw.get('server_hostname'), 'certificado': getattr(pool, 'assert_hostname', None)})
        codigo, cuerpo, cabeceras = cola.pop(0)
        return urllib3.HTTPResponse(body=io.BytesIO(cuerpo), headers=cabeceras, status=codigo, preload_content=False,
                                    decode_content=False)

    monkeypatch.setattr(urllib3.connectionpool.HTTPConnectionPool, 'urlopen', urlopen)
    return pedidas


def _dns_que_cambia(monkeypatch, *, al_validar, al_conectar):
    """DNS rebinding: responde ``al_validar`` al programa y ``al_conectar`` a quien abre el socket (urllib3 o
    ``socket.create_connection``), y una IP escrita se devuelve tal cual. Anota cada ``connect`` y no deja salir."""
    conectadas = []

    def getaddrinfo(host, port, *_a, **_k):
        try:
            ip = str(ipaddress.ip_address(host))
        except ValueError:
            quien = sys._getframe(1).f_globals.get('__name__', '')
            ip = al_conectar if quien.startswith(('urllib3', 'socket', 'http')) else al_validar
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port or 0))]

    def connect(_sock, direccion):
        conectadas.append(direccion[0])
        raise ConnectionRefusedError('red de prueba: no se conecta a nada')

    monkeypatch.setattr(socket, 'getaddrinfo', getaddrinfo)
    monkeypatch.setattr(socket.socket, 'connect', connect)
    return conectadas


def test_arcgis_conecta_a_la_ip_validada_aunque_el_dns_cambie(monkeypatch):
    """086:RF-22 (b4, rebinding) — se validaba el nombre y requests lo volvía a resolver al conectar: un DNS que da una
    IP pública a la validación y 127.0.0.1 a la conexión llevaba la consulta a esta máquina. Ahora va a la validada."""
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import arcgis

    monkeypatch.setenv(SALIDAS['arcgis'].variable, '1')
    conectadas = _dns_que_cambia(monkeypatch, al_validar='93.184.216.34', al_conectar='127.0.0.1')
    with pytest.raises(OSError):
        arcgis.ArcGISLayer('https://capas.example/MapServer/0').count()
    assert conectadas and '127.0.0.1' not in conectadas, conectadas
    assert set(conectadas) == {'93.184.216.34'}


def test_vias_conecta_a_la_ip_validada_aunque_el_dns_cambie(monkeypatch):
    """086:RF-22 (b4, rebinding) — OSRM por la misma función: la conexión no va a la IP que el DNS da al conectar."""
    from convertersmartgrid.aplicacion import vias

    conectadas = _dns_que_cambia(monkeypatch, al_validar='93.184.216.34', al_conectar='127.0.0.1')
    with pytest.raises(OSError):
        vias._pedir('http://osrm.example/route/v1/driving/x', 1.0)
    assert conectadas and set(conectadas) == {'93.184.216.34'}, conectadas


def test_arcgis_no_sigue_redirecciones(monkeypatch):
    """086:RF-22 — un 302 hacia una IP privada es un error con su motivo, y no se reintenta ni se sigue."""
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import arcgis

    monkeypatch.setenv(SALIDAS['arcgis'].variable, '1')
    _resuelve_a(monkeypatch, '93.184.216.34')
    pedidas = _servidor_falso(monkeypatch, (302, b'', {'Location': 'http://10.0.0.5/arcgis/rest/services'}))
    monkeypatch.setattr(arcgis.time, 'sleep', lambda _s: None)
    with pytest.raises(arcgis.ArcGISDestinoError, match='10.0.0.5'):
        arcgis.ArcGISLayer('https://capas.example/MapServer/0').metadata()
    assert len(pedidas) == 1 and pedidas[0]['ip'] == '93.184.216.34'


def test_arcgis_un_destino_publico_si_se_consulta(monkeypatch):
    """086:RF-22 — lo legítimo responde como antes, por la IP validada, y TLS y Host siguen con el nombre pedido."""
    from convertersmartgrid.adaptadores.entrada.vnr.connectors import arcgis

    monkeypatch.setenv(SALIDAS['arcgis'].variable, '1')
    _resuelve_a(monkeypatch, '93.184.216.34')
    pedidas = _servidor_falso(monkeypatch, (200, b'{"maxRecordCount": 7}', {'Content-Type': 'application/json'}))
    assert arcgis.ArcGISLayer('https://capas.example/MapServer/0').max_record_count() == 7
    assert pedidas == [{'ip': '93.184.216.34', 'host': 'capas.example', 'url': '/MapServer/0?f=json',
                        'sni': 'capas.example', 'certificado': 'capas.example'}]


@pytest.mark.parametrize('url', ['http://127.0.0.1:9/route/v1/driving/x', 'http://169.254.169.254/route',
                                 'file:///etc/passwd', 'ftp://osrm.example/route'])
def test_vias_rechaza_destinos_locales_y_otros_protocolos(url, monkeypatch):
    """086:RF-22 — OSRM tenía el mismo defecto: la URL del perfil iba tal cual a ``urlopen``."""
    import urllib3

    from convertersmartgrid.aplicacion import vias
    from convertersmartgrid.dominio.salidas_red import DestinoNoPermitido

    _resuelve_a(monkeypatch, '93.184.216.34')
    monkeypatch.setattr(urllib3.connectionpool.HTTPConnectionPool, 'urlopen', _no_debe_salir)
    with pytest.raises(DestinoNoPermitido):
        vias._pedir(url, 1.0)


def test_vias_con_destino_vedado_va_en_recta_y_dice_por_que(monkeypatch):
    """086:RF-22 y 016:RF-85 — el enlace no se bloquea: va en recta, con el motivo del destino."""
    import urllib3

    from convertersmartgrid.aplicacion.vias import ruta_por_vias

    monkeypatch.setenv(SALIDAS['vias'].variable, '1')
    _resuelve_a(monkeypatch, '10.0.0.5')
    monkeypatch.setattr(urllib3.connectionpool.HTTPConnectionPool, 'urlopen', _no_debe_salir)
    ruta = ruta_por_vias((-14.0, -75.7), (-14.1, -75.8), {'servicio': 'osrm', 'url': 'https://osrm.example'})
    assert ruta.por_via is False and '10.0.0.5' in ruta.avisos[0]


def test_vias_no_sigue_redirecciones(monkeypatch):
    """086:RF-22 — un 302 del enrutador hacia una IP privada corta la consulta en vez de seguirla."""
    from convertersmartgrid.aplicacion import vias
    from convertersmartgrid.dominio.salidas_red import DestinoNoPermitido

    _resuelve_a(monkeypatch, '93.184.216.34')
    pedidas = _servidor_falso(monkeypatch, (302, b'', {'Location': 'http://10.0.0.5/route'}))
    with pytest.raises(DestinoNoPermitido, match='10.0.0.5'):
        vias._pedir('https://osrm.example/route/v1/driving/x', 1.0)
    assert len(pedidas) == 1


def test_sin_requests_osrm_va_en_recta(monkeypatch):
    """103:RF-2 y 016:RF-85 — el Python 3.9 de DIgSILENT 2021 puede no tener requests: el enlace va en recta, no cae."""
    from convertersmartgrid.aplicacion import vias

    monkeypatch.setenv(SALIDAS['vias'].variable, '1')
    _resuelve_a(monkeypatch, '93.184.216.34')
    monkeypatch.setitem(sys.modules, 'requests', None)
    ruta = vias.ruta_por_vias((-14.0, -75.7), (-14.1, -75.8), {'servicio': 'osrm', 'url': 'https://osrm.example'})
    assert ruta.por_via is False and 'requests' in ruta.avisos[0]


def _guarda_de_red_activa() -> None:
    """La guarda de ``conftest._sin_red_real`` está puesta; si no, la prueba para antes de intentar nada."""
    puestas = {n: getattr(f, '_red_real_prohibida', False) for n, f in (
        ('connect', socket.socket.connect), ('connect_ex', socket.socket.connect_ex),
        ('create_connection', socket.create_connection), ('getaddrinfo', socket.getaddrinfo),
        ('gethostbyname', socket.gethostbyname))}
    assert all(puestas.values()), f'la guarda de red de las pruebas no está activa: {puestas}'


def test_la_guarda_de_las_pruebas_para_cualquier_conexion_real():
    """086:RF-22 (H8H5 v3) — en las pruebas de red, una conexión real no sale: la guarda la para y dice adónde iba.

    Es de la base de pruebas, no del programa: pasa también en el rojo, con el esqueleto que no conecta."""
    _guarda_de_red_activa()
    with pytest.raises(AssertionError, match='red real prohibida.*192.0.2.1:9'):
        socket.create_connection(('192.0.2.1', 9), timeout=0.1)
    with pytest.raises(AssertionError, match='red real prohibida.*osrm.example:443'):
        socket.getaddrinfo('osrm.example', 443)
    with pytest.raises(AssertionError, match='red real prohibida.*osrm.example'):
        socket.gethostbyname('osrm.example')
    with socket.socket() as s:
        with pytest.raises(AssertionError, match='red real prohibida.*127.0.0.1:9'):
            s.connect(('127.0.0.1', 9))
        with pytest.raises(AssertionError, match='red real prohibida.*169.254.169.254:80'):
            s.connect_ex(('169.254.169.254', 80))
    # Lo que la prueba simula sigue funcionando: la simulación sustituye a la guarda.
    _resuelve_a_en_esta_prueba = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(socket, 'getaddrinfo', lambda *_a, **_k: _resuelve_a_en_esta_prueba)
        assert socket.getaddrinfo('osrm.example', 443) == _resuelve_a_en_esta_prueba
    finally:
        mp.undo()
    _guarda_de_red_activa()


def test_la_via_de_red_sin_simular_la_para_la_guarda(monkeypatch):
    """086:RF-22 (H8H5 v3) — OSRM y ArcGIS sin red simulada: resolver el servidor para validarlo ya es salir a la red, y
    la guarda lo para antes de cualquier conexión. Si el código no resolviera ni validara, no habría nada que parar."""
    from convertersmartgrid.aplicacion import vias
    from convertersmartgrid.adaptadores.entrada.vnr.connectors.arcgis import ArcGISLayer

    _guarda_de_red_activa()
    with pytest.raises(AssertionError, match='red real prohibida.*osrm.example'):
        vias._pedir('https://osrm.example/route/v1/driving/x', 1.0)
    monkeypatch.setenv(SALIDAS['arcgis'].variable, '1')
    with pytest.raises(AssertionError, match='red real prohibida.*capas.example'):
        ArcGISLayer('https://capas.example/arcgis/rest/services/Red/MapServer/0')


def test_la_red_privada_solo_con_permiso_expreso(monkeypatch):
    """086:RF-22 — el permiso de intranet abre 10/8, 172.16/12 y 192.168/16; nunca la máquina ni los metadatos."""
    from convertersmartgrid.dominio.salidas_red import DestinoNoPermitido, validar_destino

    _resuelve_a(monkeypatch, '10.0.0.5')
    with pytest.raises(DestinoNoPermitido):
        validar_destino('https://sig.intranet/arcgis')
    validar_destino('https://sig.intranet/arcgis', permitir_intranet=True)
    for vedado in ('http://127.0.0.1/x', 'http://169.254.169.254/x', 'http://224.0.0.1/x'):
        with pytest.raises(DestinoNoPermitido):
            validar_destino(vedado, permitir_intranet=True)


def test_hugging_face_apagado_desde_el_arranque(producto):
    """086:RF-22 — ``huggingface_hub`` lee la variable al importarse: se decide antes de importarlo."""
    entorno = {VARIABLE_EDICION: 'producto'}
    preparar_entorno_sin_red(entorno)
    assert entorno['HF_HUB_OFFLINE'] == '1' and entorno['TRANSFORMERS_OFFLINE'] == '1'
    entorno = {VARIABLE_EDICION: 'producto', SALIDAS['hugging_face'].variable: '1'}
    preparar_entorno_sin_red(entorno)
    assert 'HF_HUB_OFFLINE' not in entorno


def test_politica_sin_red_prevalece_sobre_las_variables_heredadas(producto):
    """086:RF-22 — heredar HF_HUB_OFFLINE=0 no debe reabrir una salida desactivada por la política."""
    entorno = {SALIDAS['hugging_face'].variable: '0', 'HF_HUB_OFFLINE': '0', 'TRANSFORMERS_OFFLINE': '0'}
    preparar_entorno_sin_red(entorno)
    assert entorno['HF_HUB_OFFLINE'] == '1' and entorno['TRANSFORMERS_OFFLINE'] == '1'


def test_conversion_y_reapertura_en_proceso_sin_sockets_externos(tmp_path):
    """086:RF-22 / 086:RF-46 — denegación de red en el hijo y sus hijos; conversión real con TXT propios."""
    aislamiento = tmp_path / 'aislamiento'
    aislamiento.mkdir()
    # sitecustomize se carga antes del producto y también en los trabajadores spawn.
    (aislamiento / 'sitecustomize.py').write_text(
        'import sys,os,json\n'
        'def sin_red(evento,args):\n'
        '    if evento not in ("socket.connect","socket.getaddrinfo"): return\n'
        '    direccion=args[1] if evento=="socket.connect" else args[0]\n'
        '    host=direccion[0] if isinstance(direccion,tuple) else direccion\n'
        '    if host in ("127.0.0.1","::1","localhost",None): return\n'
        '    with open(os.environ["P21_BLOQUEOS"],"a") as f: f.write(json.dumps({"pid":os.getpid(),"evento":evento})+"\\n")\n'
        '    raise PermissionError("red externa denegada al proceso propio")\n'
        'sys.addaudithook(sin_red)\n', encoding='utf-8')
    guion = tmp_path / 'sin_red.py'
    guion.write_text(
        'import os,json,socket,hashlib\nfrom pathlib import Path\n'
        'from fastapi.testclient import TestClient\n'
        'from convertersmartgrid.dominio.salidas_red import SALIDAS,exigir_salida,SalidaApagada,preparar_entorno_sin_red\n'
        'from convertersmartgrid.dominio import sesion_web\n'
        'from convertersmartgrid.presentacion.web.app import create_app\n'
        'from convertersmartgrid.presentacion.web.workspace import WorkspaceStore\n'
        'from test_web_api import _loaded\n'
        'from apoyo import esperar_trabajo\n'
        'from synthetic_export import ExportSpec,write_export\n'
        'if __name__=="__main__":\n'
        '    try: socket.create_connection(("192.0.2.1",9),timeout=.1)\n'
        '    except PermissionError: pass\n'
        '    else: raise AssertionError("aislamiento inactivo")\n'
        '    preparar_entorno_sin_red()\n'
        '    avisos=[]\n'
        '    for nombre in SALIDAS:\n'
        '        try: exigir_salida(nombre)\n'
        '        except SalidaApagada as e: avisos.append(str(e))\n'
        '        else: raise AssertionError(nombre)\n'
        f'    raiz=Path({str(tmp_path)!r})\n'
        '    sesion_web.EXIGIR_SEGURIDAD=False\n'
        '    entradas=write_export(ExportSpec(feeders=2,sections_per_feeder=3,seed=21),raiz/"entradas")\n'
        '    with TestClient(create_app(raiz/"web")) as c:\n'
        '        wid=_loaded(c,entradas)\n'
        '        trabajo=c.post(f"/api/workspaces/{wid}/convert",json={"all":True}).json()\n'
        '        final=esperar_trabajo(c,trabajo)\n'
        '        assert final["status"]=="done",final\n'
        '    ws=WorkspaceStore(raiz/"web").get(wid)\n'
        '    archivos=list(ws.out_dir.rglob("*.dgs"))\n'
        '    assert len(archivos)==2 and len(ws.conversions)==2\n'
        '    hashes={str(p.relative_to(ws.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in archivos}\n'
        '    with TestClient(create_app(raiz/"web")) as c:\n'
        '        assert c.get(f"/api/workspaces/{wid}").status_code==200\n'
        '    assert hashes=={str(p.relative_to(ws.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in archivos}\n'
        '    (raiz/"resultado.json").write_text(json.dumps({"hashes":hashes,"avisos":avisos,"espacio":wid}))\n',
        encoding='utf-8')
    bloqueos = tmp_path / 'bloqueos.jsonl'
    entorno = {**os.environ, **{s.variable: '0' for s in SALIDAS.values()},
               'PYTHONPATH': os.pathsep.join(map(str, (aislamiento, RAIZ / 'src', RAIZ / 'tests'))),
               'P21_BLOQUEOS': str(bloqueos), 'CSG_WEB_DATA': str(tmp_path / 'web'),
               'CSG_RUNTIME_HOME': str(tmp_path / 'runtime'), 'CSG_CACHE_HOME': str(tmp_path / 'cache'),
               'CSG_ASISTENTE_DATA': str(tmp_path / 'asistente'), 'CSG_TWIN_DATA': str(tmp_path / 'twin'),
               'CSG_WEB_RELANZAR': '0', 'CSG_ASISTENTE_VIGILANCIA': '0', 'OPENBLAS_NUM_THREADS': '1'}
    entorno.pop('PF_PYTHON', None)
    resultado = subprocess.run([sys.executable, '-B', str(guion)], env=entorno, capture_output=True,
                               text=True, encoding='utf-8', errors='replace', timeout=60, check=False)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    datos = json.loads((tmp_path / 'resultado.json').read_text())
    assert len(datos['hashes']) == 2 and len(datos['avisos']) == len(SALIDAS)
    # Solo la sonda deliberada intentó una conexión; el flujo no necesitó ninguna salida externa.
    assert len(bloqueos.read_text().splitlines()) == 1


def test_preparar_modelos_no_descarga_con_la_salida_apagada(producto, tmp_path, capsys):
    """086:RF-22 — la herramienta que baja modelos, con la misma salida."""
    from apoyo import cargar_herramienta

    herramienta = cargar_herramienta('preparar_modelos_ia.py')
    assert herramienta.main(['--descargar', '--output-json', str(tmp_path / 'x.json')]) == 1
    assert SALIDAS['hugging_face'].variable in capsys.readouterr().err


def test_el_motivo_dice_como_activarla():
    """086:RF-22 — el operador tiene que poder encenderla sin leer el código."""
    for nombre, salida in SALIDAS.items():
        assert salida.variable in motivo_apagada(nombre)
    assert '«Opciones de conversión»' in motivo_apagada('teselas')                  # 086:RF-67
    assert 'Opciones de conversión' not in motivo_apagada('internet')


def test_086_rf61_el_aviso_dice_al_y_del():
    """086:RF-61 — «La salida al portal de Osinergmin», nunca «a el portal» (rc5, 2026-11-12, en la web)."""
    assert motivo_apagada('vnr_oficial').startswith('La salida al portal de Osinergmin está apagada')
    for nombre in SALIDAS:
        texto = motivo_apagada(nombre)
        assert not re.search(r'\b[Aa] el\b|\b[Dd]e el\b', texto), texto


@pytest.mark.parametrize('texto, sale', [
    ('La salida a el portal', 'La salida al portal'),
    ('A el servidor', 'Al servidor'),
    ('la copia de el servicio', 'la copia del servicio'),
    ('De el enrutador', 'Del enrutador'),
    ('para el portal', 'para el portal'),
    ('a ellos y de ella', 'a ellos y de ella'),
    ('la SET de El Carmen', 'la SET de El Carmen'),
])
def test_086_rf61_contraer(texto, sale):
    """086:RF-61 — solo «a el» y «de el» con el artículo; un nombre propio con «El» no se contrae (RAE)."""
    assert contraer(texto) == sale


def test_el_filtro_de_secretos_falla_cerrado_si_la_depuracion_falla(monkeypatch):
    """086:RF-19 — si depurar falla, el registro no sale crudo: se sustituye por un texto fijo y el fallo se cuenta
    (pre-auditoría de 7e, 2026-11-14: el ``except`` devolvía el registro sin depurar)."""
    from convertersmartgrid.dominio import sesion_web

    def depurar_roto(_texto):
        raise RuntimeError('fallo dentro de la depuración')

    filtro = sesion_web.FiltroSecretos()
    monkeypatch.setattr(sesion_web, 'depurar_secretos', depurar_roto)
    registro = logging.LogRecord('convertersmartgrid', logging.INFO, '', 0, 'token=secreto8 en %s', ('AL101',), None)
    assert filtro.filter(registro) is True
    texto = registro.getMessage()
    assert 'secreto8' not in texto and 'no se pudo depurar' in texto
    assert filtro.fallos == 1


def test_un_registro_mal_formado_sale_depurado_y_sin_romper():
    """086:RF-19 — un mensaje que no casa con sus argumentos ya no llega crudo a ``handleError``, que lo imprimía
    entero en stderr con el secreto."""
    from convertersmartgrid.dominio import sesion_web

    filtro = sesion_web.FiltroSecretos()
    registro = logging.LogRecord('convertersmartgrid', logging.INFO, '', 0, 'token=secreto9 %s %s', ('solo',), None)
    assert filtro.filter(registro) is True
    texto = registro.getMessage()
    assert 'secreto9' not in texto and 'argumentos' in texto
