"""086:RF-127 (T101): una referencia de soporte por petición, que viaja al trabajo, al motor y al informe.

- La API devuelve en ``X-CSG-Traza`` la referencia de cada petición: la del cliente si es válida, si no una nueva.
- Lo que la petición encola hereda esa referencia; el trabajo la publica, la guarda en su diario y la tiene en curso.
- Un guion del motor la recibe en ``CSG_TRAZA``; la orden de DIgSILENT la apunta en el registro del servidor.
- El informe Word la lleva en sus metadatos y su JSON par en ``traza``.
- La web deja copiar la referencia, sin citas internas.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apoyo import cargar_herramienta

RAIZ = Path(__file__).resolve().parents[1]
ESPERA_S = 10.0
REFERENCIA = 'a1b2c3d4e5f60718293a4b5c6d7e8f90'


def _en_traza(referencia: str):
    """Fija la referencia; sin la pieza no fija nada y la aserción dice qué falta, en vez de un ImportError."""
    try:
        from convertersmartgrid.dominio import traza
    except ImportError:
        return contextlib.nullcontext()
    return traza.en_traza(referencia)


def _actual() -> str | None:
    try:
        from convertersmartgrid.dominio import traza
    except ImportError:
        return None
    return traza.actual()


@pytest.fixture(autouse=True)
def _entorno(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv('CSG_WEB_DATA', str(tmp_path / 'web'))
    monkeypatch.delenv('CSG_TRAZA', raising=False)
    # Sin la interfaz compilada: su ruta comodín se queda con las rutas de prueba que se añaden después.
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    yield


def _esperar(condicion, timeout_s: float = ESPERA_S) -> None:
    fin = threading.Event()
    limite = threading.Timer(timeout_s, fin.set)
    limite.start()
    try:
        while not condicion() and not fin.is_set():
            fin.wait(0.01)
    finally:
        limite.cancel()
    assert condicion(), 'no se cumplió a tiempo'


def test_cada_peticion_lleva_su_referencia_y_su_trabajo_la_hereda(tmp_path):
    """086:RF-127 — la respuesta trae la referencia; la ruta y el trabajo que encola ven la misma."""
    from convertersmartgrid.presentacion.web.app import create_app

    app = create_app(tmp_path / 'web', host='127.0.0.1')
    vista: dict = {}

    def encolar():
        vista['ruta'] = _actual()
        job = app.state.jobs.submit('W', 'prueba', 'Prueba', lambda _ctx: vista.update(trabajo=_actual()))
        return job.public()

    app.add_api_route('/api/_prueba_traza', encolar, methods=['GET'])
    with TestClient(app) as cliente:
        uno = cliente.get('/api/health').headers.get('x-csg-traza')
        dos = cliente.get('/api/health').headers.get('x-csg-traza')
        assert uno and re.fullmatch(r'[0-9a-f]{32}', uno) and dos and uno != dos
        respuesta = cliente.get('/api/_prueba_traza', headers={'X-CSG-Traza': REFERENCIA})
        assert respuesta.headers.get('x-csg-traza') == REFERENCIA
        assert respuesta.json().get('traza') == REFERENCIA and vista['ruta'] == REFERENCIA
        _esperar(lambda: 'trabajo' in vista)
        assert vista['trabajo'] == REFERENCIA
        # Lo que no cumple el formato no entra: se sustituye por una nueva.
        rara = cliente.get('/api/health', headers={'X-CSG-Traza': 'x<script>'}).headers.get('x-csg-traza')
        assert rara and rara != 'x<script>' and re.fullmatch(r'[0-9a-f]{32}', rara)


def test_el_trabajo_guarda_la_referencia_en_su_diario_y_la_recupera(tmp_path):
    """086:RF-127 — sin petición también tiene la suya; el diario la conserva tras un reinicio."""
    from convertersmartgrid.presentacion.web.jobs import DiarioTrabajos, JobManager

    jobs = JobManager(lambda *_a: None, diario=tmp_path / 'diario')
    soltar = threading.Event()
    with _en_traza(REFERENCIA):
        heredado = jobs.submit('W', 'prueba', 'Con petición', lambda _ctx: soltar.wait(ESPERA_S))
    suelto = jobs.submit('W', 'prueba', 'Sin petición', lambda _ctx: None, lane='control')
    try:
        assert heredado.public().get('traza') == REFERENCIA
        assert re.fullmatch(r'[0-9a-f]{32}', suelto.public().get('traza') or '')
        guardado = json.loads((tmp_path / 'diario' / f'{heredado.id}.json').read_text(encoding='utf-8'))
        assert guardado.get('traza') == REFERENCIA
        # Tras un reinicio: el diario de un servidor que ya no vive (otro proceso), no el de este, que sigue en marcha.
        previo = tmp_path / 'diario_previo'
        previo.mkdir()
        (previo / f'{heredado.id}.json').write_text(
            json.dumps({**guardado, 'pid': -1, 'inicio_proceso': None}), encoding='utf-8')
        recuperados = {j.id: j for j in DiarioTrabajos(previo).recuperar()}
        assert getattr(recuperados[heredado.id], 'traza', None) == REFERENCIA
    finally:
        soltar.set()


def test_el_guion_del_motor_recibe_la_referencia(tmp_path):
    """086:RF-127 — el proceso del motor la recibe en ``CSG_TRAZA`` y la escribe en el Registro del trabajo."""
    from convertersmartgrid.presentacion.web.jobs import FINISHED, JobManager

    eventos: list[dict] = []
    jobs = JobManager(lambda _w, tipo, datos: eventos.append(datos) if tipo == 'log' else None)
    orden = [sys.executable, '-c', 'import os; print("motor", os.environ.get("CSG_TRAZA"))']
    with _en_traza(REFERENCIA):
        # Sin ``PF_PYTHON``: un guion cualquiera, nunca el camino de DIgSILENT.
        entorno = {k: v for k, v in os.environ.items() if k != 'PF_PYTHON'}
        job = jobs.submit('W', 'guion', 'Guion', lambda ctx: ctx.run_process(orden, env=entorno))
    _esperar(lambda: job.status in FINISHED)
    assert any(e.get('text', '').strip() == f'motor {REFERENCIA}' for e in eventos), eventos


def _ocupado_con_traza(*, progreso, log, cancelado):
    return _actual()


def test_el_proceso_aparte_del_motor_tiene_la_referencia(tmp_path):
    """086:RF-127 — el oráculo y la lectura de libros corren en otro proceso: llevan la misma referencia."""
    from convertersmartgrid.presentacion.web.jobs import FINISHED, JobManager

    jobs = JobManager(lambda *_a: None)
    with _en_traza(REFERENCIA):
        job = jobs.submit('W', 'motor', 'Motor', lambda ctx: ctx.en_proceso(_ocupado_con_traza))
    _esperar(lambda: job.status in FINISHED, 60.0)
    assert job.result == REFERENCIA, job.error


def test_la_orden_de_digsilent_apunta_la_referencia_en_el_registro_del_servidor(tmp_path, monkeypatch, capsys):
    """086:RF-127 — el cliente la deja en la orden y el servidor la dice en su línea de ``servidor.log``."""
    from convertersmartgrid.adaptadores import pf_arnes

    monkeypatch.setenv(pf_arnes.VARIABLE_TURNO, str(tmp_path / 'turno'))
    monkeypatch.setenv(pf_arnes.VARIABLE_COLA, str(tmp_path / 'cola'))
    monkeypatch.setenv('CSG_TRAZA', REFERENCIA)
    cola = tmp_path / 'cola'
    cola.mkdir()
    servidor = cargar_herramienta('pf_servidor.py', 'pf_servidor_traza', tools_en_path=True)
    cliente = cargar_herramienta('pf_cliente.py', 'pf_cliente_traza', tools_en_path=True)
    monkeypatch.setattr(pf_arnes, 'servidor_vivo', lambda ruta=None: {'pid': 1})
    monkeypatch.setattr(servidor, '_cargar', lambda guion: SimpleNamespace(main=lambda argv: 0))
    hilo = threading.Thread(target=servidor.servir, args=(1.5,), daemon=True)
    hilo.start()
    assert cliente.enviar('verificar_pf.py', [], cola) == 0
    hilo.join(timeout=ESPERA_S)
    assert f'referencia {REFERENCIA}' in capsys.readouterr().out
    fila = json.loads((cola / 'ordenes.jsonl').read_text(encoding='utf-8').splitlines()[-1])
    assert fila.get('traza') == REFERENCIA


def test_el_informe_lleva_la_referencia_en_sus_metadatos(tmp_path):
    """086:RF-127 — Word con la referencia en sus propiedades y el JSON par con ``traza``; sin ella, como antes."""
    import docx

    from convertersmartgrid.adaptadores import informe_docx

    destino = tmp_path / 'informe' / 'estudio.docx'
    with _en_traza(REFERENCIA):
        informe_docx.guardar_informe(docx.Document(), destino, {'tipo': 'estudio'})
    assert docx.Document(str(destino)).core_properties.identifier == REFERENCIA
    assert json.loads(destino.with_suffix('.json').read_text(encoding='utf-8')).get('traza') == REFERENCIA
    otro = tmp_path / 'informe' / 'sin.docx'
    informe_docx.guardar_informe(docx.Document(), otro, {'tipo': 'estudio'})
    assert 'traza' not in json.loads(otro.with_suffix('.json').read_text(encoding='utf-8'))


def test_la_web_deja_copiar_la_referencia_sin_citas_internas():
    """086:RF-127 — el aviso del trabajo y su resumen ofrecen copiar la referencia, con texto de operador."""
    from convertersmartgrid.aplicacion.asistente.tareas import sin_citas

    fuente = (RAIZ / 'frontend/src/shared/AvisosTrabajo.tsx').read_text(encoding='utf-8')
    app = (RAIZ / 'frontend/src/app/App.tsx').read_text(encoding='utf-8')
    assert 'export function ReferenciaSoporte' in fuente
    assert re.search(r'navigator\.clipboard\??\.writeText\(traza\)', fuente)
    assert '<ReferenciaSoporte' in fuente and '<ReferenciaSoporte' in app
    textos = re.findall(r'>([^<>{}]*Referencia[^<>{}]*)<', fuente) + [t for t in re.findall(r'title="([^"]*)"', fuente) if 'referencia' in t]
    assert textos and all(sin_citas(t) == t and 'RF-' not in t for t in textos), textos
