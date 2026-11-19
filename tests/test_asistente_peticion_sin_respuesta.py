"""070:RF-88 — una petición del asistente que no recibe respuesta a tiempo es un paso fallido con su motivo, nunca una
excepción cruda de la biblioteca de red; las rutas síncronas largas llevan su plazo; y la espera de un trabajo sigue
contando esos fallos como pasajeros (070:RF-87). Con la revisión de ASISTENTE-A de 1d (18-11): los textos sin «(s)»
(086:RF-110), las redirecciones de una lectura revalidadas (026:RF-50) y una regeneración a medias que no queda
preparada (026:RF-46).
"""
from __future__ import annotations

import http.server
import threading
from types import SimpleNamespace

import pytest
import requests

from convertersmartgrid.aplicacion.asistente import ejecutor
from convertersmartgrid.aplicacion.asistente import internet


def _nuevo(nombre):
    assert hasattr(ejecutor, nombre), f'070:RF-88: el ejecutor no tiene {nombre}'
    return getattr(ejecutor, nombre)


class _Http:
    """Una sesión de prueba: responde lo que se le dé y apunta el ``timeout`` de cada petición."""

    def __init__(self, respuestas):
        self.respuestas, self.plazos = list(respuestas), []

    def request(self, metodo, url, **kw):
        self.plazos.append((url, kw.get('timeout')))
        r = self.respuestas.pop(0)
        if isinstance(r, BaseException):
            raise r
        return r


def _ok(datos):
    return SimpleNamespace(status_code=200, content=b'x', json=lambda: datos, text='')


def _cliente(http):
    return ejecutor.ClienteWeb(http=http, base='http://127.0.0.1:1', espacio='e', intervalo_s=0)


def test_070_rf88_una_peticion_sin_respuesta_es_un_paso_fallido_con_su_motivo():
    """070:RF-88: un ReadTimeout de requests sale como PeticionSinRespuesta (un PasoFallido), en español."""
    sin_respuesta = _nuevo('PeticionSinRespuesta')
    c = _cliente(_Http([requests.ReadTimeout('lento')]))
    with pytest.raises(ejecutor.PasoFallido) as e:
        c.pedir('POST', '/api/normativa/regenerar', json={})
    assert isinstance(e.value, sin_respuesta) and 'la web no respondió en 300 s (ReadTimeout)' in str(e.value)


def test_070_rf88_las_rutas_sincronas_largas_llevan_su_plazo():
    """070:RF-88: regenerar una norma, cargar la fuente y preparar los planes esperan hasta PLAZO_SINCRONO_S."""
    plazo = _nuevo('PLAZO_SINCRONO_S')
    assert plazo >= 1900
    http = _Http([_ok({'token': 'abc'}), _ok({'ok': True})])
    pasos = ejecutor.pasos('normativa_regenerar', {}, {'normativa': {'generador': 'coes'}})
    ejecutor._ejecutar(pasos, _cliente(http), lambda _m: None)
    assert http.plazos[0] == ('http://127.0.0.1:1/api/normativa/regenerar', plazo)
    assert http.plazos[1][1] == ejecutor.TIEMPO_PETICION_S
    assert {'/load', '/lote/plan', '/pf/estudios/plan'} <= set(_nuevo('RUTAS_SINCRONAS_LARGAS'))


def test_070_rf88_el_doble_que_tarda_mas_que_el_plazo_da_paso_fallido_y_no_excepcion_cruda():
    """070:RF-88: el ejecutor entero: la orden falla con PasoFallido (lo que captura la web), no con ReadTimeout."""
    _nuevo('PeticionSinRespuesta')
    http = _Http([requests.ReadTimeout('el servidor sigue con el subproceso')])
    pasos = ejecutor.pasos('normativa_regenerar', {}, {'normativa': {'generador': 'coes'}})
    with pytest.raises(ejecutor.PasoFallido):
        ejecutor._ejecutar(pasos, _cliente(http), lambda _m: None)


@pytest.mark.parametrize('sin_respuesta, termina', [(4, True), (5, False)])
def test_070_rf88_la_espera_sigue_contando_los_fallos_pasajeros(sin_respuesta, termina):
    """070:RF-87 y RF-88: 4 consultas sin respuesta y luego una buena acaban bien; 5 seguidas, se rinde."""
    _nuevo('PeticionSinRespuesta')
    http = _Http([requests.ConnectionError('caída')] * sin_respuesta + [_ok({'id': 't', 'status': 'done'})])
    c = _cliente(http)
    if termina:
        assert c.esperar({'id': 't'})['status'] == 'done'
    else:
        with pytest.raises(ejecutor.PasoFallido, match='5 veces seguidas'):
            c.esperar({'id': 't'})


def test_086_rf110_los_textos_de_la_biblioteca_y_de_regenerar_no_usan_s_entre_parentesis():
    """086:RF-110: «norma(s)», «alterada(s)» y «fichero(s)» pasan a su singular o plural reales."""
    import inspect

    from convertersmartgrid.presentacion.web import asistente_operacion, services

    assert hasattr(services, '_asistente_normativa_fuentes') and hasattr(asistente_operacion, '_texto_normativa'), \
        '026:RF-46: no están los textos de la biblioteca normativa'
    fuentes = inspect.getsource(services._asistente_normativa_fuentes) + inspect.getsource(
        asistente_operacion._texto_normativa)
    assert '(s)' not in fuentes


class _Redirige(http.server.BaseHTTPRequestHandler):
    destino = ''

    def do_GET(self):  # noqa: N802
        self.send_response(302)
        self.send_header('Location', self.destino)
        self.end_headers()

    def log_message(self, *a):
        pass


def test_026_rf50_una_redireccion_fuera_de_la_lista_no_se_sigue():
    """026:RF-50: cada redirección se revalida antes de pedirla; fuera de la lista, no se pide."""
    assert hasattr(internet, 'abridor_que_revalida'), '026:RF-50: las redirecciones de una lectura no se revalidan'
    pedidas = []

    class _Fuera(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            pedidas.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    fuera = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Fuera)
    _Redirige.destino = f'http://127.0.0.1:{fuera.server_port}/otra'
    origen = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Redirige)
    for s in (fuera, origen):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        abrir = internet.abridor_que_revalida(
            lambda url: 'dominio fuera de la lista' if str(fuera.server_port) in url else None)
        import urllib.request
        with pytest.raises(internet.RedireccionFueraDeLista, match='no seguida'):
            abrir(urllib.request.Request(f'http://127.0.0.1:{origen.server_port}/'), 5)
        assert pedidas == []
    finally:
        for s in (fuera, origen):
            s.shutdown()


def test_026_rf46_una_regeneracion_a_medias_no_queda_preparada(tmp_path, monkeypatch):
    """026:RF-46: si la copia de la biblioteca falla, el destino se borra y la ruta dice el motivo."""
    import inspect

    from convertersmartgrid.aplicacion import biblioteca_normativa as bn
    from convertersmartgrid.presentacion.web import normativa_api

    assert 'carpeta_fuentes' in inspect.signature(normativa_api.registrar_rutas_normativa).parameters, \
        '026:RF-46: la API de la biblioteca no sabe regenerar un registro'
    from test_asistente_026_normativa import _armar, _generador

    cliente, _capa, _fuentes, programa = _armar(normativa_api.registrar_rutas_normativa, tmp_path, monkeypatch)
    _generador(programa, 'generar_coes.py', 'pass\n')
    (programa / 'config' / 'normativa').mkdir(parents=True)

    def falla(*_a, **_k):
        raise OSError('disco lleno')

    monkeypatch.setattr(normativa_api.shutil, 'copytree', falla)
    try:
        r = cliente.post('/api/normativa/regenerar', json={'generador': 'coes'})
    except OSError as exc:
        raise AssertionError(f'026:RF-46: la copia a medias sale como una excepción cruda: {exc}') from exc
    assert r.status_code == 500 and 'disco lleno' in r.text
    preparadas = bn.ruta_capa_usuario().parent / 'normativa_regenerada'
    assert not preparadas.exists() or not any(preparadas.iterdir())
