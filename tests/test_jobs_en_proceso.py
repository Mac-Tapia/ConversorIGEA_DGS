"""Spec 027, T13: trabajos del motor en un proceso aparte, con límite de memoria."""
from __future__ import annotations

import time

import pytest

from igea_dgs.web import jobs


def ocupado(segundos, *, progreso, log, cancelado):
    """CPU pura durante ``segundos`` (como leer un libro de cabecera), con su Registro."""
    log('empieza')
    fin = time.monotonic() + segundos
    n = 0
    while time.monotonic() < fin and not cancelado():
        n += sum(i * i for i in range(20000))
    progreso(1, 1, 'hecho')
    return {'cancelado': cancelado(), 'n': n > 0}


def glotona(mb, *, progreso, log, cancelado):
    bloques = []
    for _ in range(mb // 50 + 4):
        bloques.append(bytearray(50 * 2**20))
        time.sleep(0.1)
    return len(bloques)


def falla(*, progreso, log, cancelado):
    raise ValueError('libro roto')


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from igea_dgs.web.app import create_app

    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        yield c


def _contexto(app):
    eventos = []
    job = jobs.Job(kind='prueba', title='prueba', workspace_id='w', lane='engine', fn=lambda c: None)
    return jobs.JobContext(job, lambda w, k, d: eventos.append((k, d))), eventos


def test_la_api_responde_mientras_el_motor_trabaja(cliente):
    """027:RF-25 / 027:RF-26 — con un trabajo de CPU en su proceso, ``/api/health`` responde en
    menos de 1 s; el Registro y el avance llegan del proceso."""
    import threading

    ctx, eventos = _contexto(cliente.app)
    resultado = {}
    hilo = threading.Thread(target=lambda: resultado.update(r=ctx.en_proceso(ocupado, 6.0)))
    hilo.start()
    time.sleep(2.5)
    peores = []
    for _ in range(5):
        t0 = time.monotonic()
        assert cliente.get('/api/health').status_code == 200
        peores.append(time.monotonic() - t0)
        time.sleep(0.3)
    hilo.join(30)
    assert max(peores) < 1.0, peores
    assert resultado['r'] == {'cancelado': False, 'n': True}
    assert any(k == 'log' and d['text'] == 'empieza' for k, d in eventos)
    assert any(k == 'job' for k, _d in eventos)


def test_cancelar_y_errores_del_proceso():
    """027:RF-25 — la cancelación del trabajo llega al proceso y su error vuelve al padre."""
    import threading

    ctx, _ev = _contexto(None)
    threading.Timer(1.5, ctx.cancel.set).start()
    t0 = time.monotonic()
    assert ctx.en_proceso(ocupado, 60.0)['cancelado'] is True
    assert time.monotonic() - t0 < 20
    ctx2, _ev = _contexto(None)
    with pytest.raises(ValueError, match='libro roto'):
        ctx2.en_proceso(falla)


def test_limite_de_memoria_detiene_el_trabajo():
    """027:RF-27 — un trabajo que pasa su límite se detiene con su motivo, sin tumbar al padre."""
    ctx, _ev = _contexto(None)
    with pytest.raises(jobs.MemoriaExcedida, match='027:RF-27'):
        ctx.en_proceso(glotona, 1200, limite_mb=400)
