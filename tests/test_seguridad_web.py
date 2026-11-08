"""086:RF-17 a RF-22 — la web solo atiende a esta máquina, con su token, y no sale a la red por su cuenta.

La revisión de la spec 086 reprodujo en la revisión af5d1357 que una página cualquiera del navegador
llegaba a la API de 127.0.0.1: Host ajeno 200, POST con Origin ajeno 201, sin token 200 y WebSocket con
Origin ajeno aceptado. Cada puerta tiene aquí su prueba negativa, también en el WebSocket.
"""
from __future__ import annotations

import hashlib
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

from convertersmartgrid import sesion_web
from convertersmartgrid.edicion import VARIABLE_EDICION, es_edicion_producto
from convertersmartgrid.salidas_red import (SALIDAS, SalidaApagada, exigir_salida, motivo_apagada,
                                            preparar_entorno_sin_red, salida_permitida)
from convertersmartgrid.web import __main__ as lanzador
from convertersmartgrid.web import seguridad
from convertersmartgrid.web.app import create_app
from convertersmartgrid.web.jobs import EventLog

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
    from convertersmartgrid.web import app as app_mod
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

    from convertersmartgrid.asistente.ejecutor import ClienteWeb

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
    from convertersmartgrid.cli import main as cli

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
    from convertersmartgrid.preview import CARPETA_LEAFLET, HUELLAS_LEAFLET

    huella = base64.b64encode(hashlib.sha256((CARPETA_LEAFLET / nombre).read_bytes()).digest()).decode()
    assert f'sha256-{huella}' == HUELLAS_LEAFLET[nombre]
    assert 'BSD' in (CARPETA_LEAFLET / 'LICENSE').read_text(encoding='utf-8') or 'Redistribution' in (CARPETA_LEAFLET / 'LICENSE').read_text(encoding='utf-8')


def _modelo_de_vista_previa():
    sys.path.insert(0, str(RAIZ / 'tests'))
    from test_preview import _mini_geo, _mini_model

    return _mini_model(), _mini_geo()


def test_la_vista_previa_no_pide_nada_de_fuera(tmp_path, monkeypatch):
    """086:RF-21 — ni script ni estilo de un CDN; con la salida apagada, tampoco teselas, y lo dice."""
    from convertersmartgrid.preview import write_preview_html

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
    from convertersmartgrid.preview import write_preview_html

    modelo, geo = _modelo_de_vista_previa()
    modelo.network_name = 'A</script><img src=x onerror=alert(1)>'
    modelo.feeder = modelo.network_name
    texto = write_preview_html(modelo, geo, tmp_path / 'a.html', backend='leaflet').read_text(encoding='utf-8')
    cuerpo = texto.split('</head>')[1]
    assert '<img src=x' not in cuerpo


def test_con_teselas_encendidas_abre_y_dice_si_no_llega(tmp_path, monkeypatch):
    """086:RF-22 — encendidas de forma explícita en producto: la capa, su política y el aviso sin red."""
    from convertersmartgrid.preview import ORIGEN_TESELAS, politica_pagina_generada, write_preview_html

    monkeypatch.setenv(VARIABLE_EDICION, 'producto')
    monkeypatch.setenv(SALIDAS['teselas'].variable, '1')
    modelo, geo = _modelo_de_vista_previa()
    texto = write_preview_html(modelo, geo, tmp_path / 'a.html', backend='leaflet').read_text(encoding='utf-8')
    assert 'L.tileLayer(' in texto and "'tileerror'" in texto and 'no se pudo llegar' in texto
    assert ORIGEN_TESELAS in politica_pagina_generada()
    monkeypatch.setenv(SALIDAS['teselas'].variable, '0')
    assert ORIGEN_TESELAS not in politica_pagina_generada()


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
    'src/convertersmartgrid/web/__main__.py': 'el lanzador, a su propia web de 127.0.0.1',
    'src/convertersmartgrid/asistente/ejecutor.py': 'la API de la web, solo local (asistente/equipo.py)',
    'src/convertersmartgrid/web/services.py': 'el cliente del asistente, a la propia web',
    'src/convertersmartgrid/asistente/ollama.py': 'Ollama en esta máquina (LOCALES)',
    'src/convertersmartgrid/asistente/embeddings.py': 'local_files_only: lee la caché de modelos',
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
            if rel in ('src/convertersmartgrid/salidas_red.py',):
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
    from convertersmartgrid.asistente.internet import Buscador

    r = Buscador(abrir=_no_debe_salir)._consultar('github', 'pandas', 'prueba', _no_debe_salir)
    assert r['resultados'] == [] and SALIDAS['internet'].variable in r['bloqueada']


def test_vias_apagado_va_en_recta_y_lo_dice(producto):
    """086:RF-22 — OSRM: el enlace sale en recta, con el aviso de cómo se activa."""
    from convertersmartgrid.vias import ruta_por_vias

    ruta = ruta_por_vias((-14.0, -75.7), (-14.1, -75.8), {'servicio': 'osrm', 'url': 'http://osrm.example'},
                         pedir=_no_debe_salir)
    assert ruta.por_via is False and SALIDAS['vias'].variable in ruta.avisos[0]


def test_vias_encendido_de_forma_explicita(producto, monkeypatch):
    """086:RF-22 — con su variable, en producto, sí consulta."""
    from convertersmartgrid.vias import ruta_por_vias

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
    from convertersmartgrid.asistente import destilacion

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
        'from convertersmartgrid.salidas_red import SALIDAS,exigir_salida,SalidaApagada,preparar_entorno_sin_red\n'
        'from convertersmartgrid import sesion_web\n'
        'from convertersmartgrid.web.app import create_app\n'
        'from convertersmartgrid.web.workspace import WorkspaceStore\n'
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
