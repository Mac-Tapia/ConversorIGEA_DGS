"""086:RF-112 (T82): un fallo de la observación o del diario nunca deja un trabajo «en curso» con su hilo muerto, ni
ejecuta un trabajo cuyo recibo durable no se pudo guardar (auditoría del 18-11, H01 y H02).

- Si publicar el inicio falla, el trabajo termina con error explícito sin ejecutarse y el carril sigue vivo.
- Si publicar el final falla, el resultado queda consultable y el siguiente trabajo del carril corre.
- Con diario, un trabajo nuevo sin su recibo durable no se admite ni se ejecuta; sin diario se admite como siempre.
"""
from __future__ import annotations

import threading

import pytest

from convertersmartgrid.presentacion.web.jobs import DONE, FAILED, FINISHED, RUNNING, JobManager

ESPERA_S = 5.0


@pytest.fixture(autouse=True)
def hilos_sin_morir(monkeypatch):
    """Ningún hilo del gestor puede morir con una excepción: el siguiente ``submit`` lo resucitaba y lo escondía."""
    muertes: list[str] = []
    monkeypatch.setattr(threading, 'excepthook', lambda args: muertes.append(f'{args.thread.name}: {args.exc_value!r}'))
    yield muertes
    assert muertes == [], f'hilos muertos por una excepción: {muertes}'


def _esperar_fin(job, timeout_s: float = ESPERA_S) -> None:
    fin = threading.Event()

    def mirar():
        while job.status not in FINISHED and not fin.is_set():
            fin.wait(0.01)
        fin.set()

    hilo = threading.Thread(target=mirar, daemon=True)
    hilo.start()
    hilo.join(timeout_s)
    fin.set()


class _Observador:
    """Falla al publicar el estado indicado las primeras ``veces`` veces."""

    def __init__(self, estado: str, veces: int = 1) -> None:
        self.estado, self.veces, self.fallos = estado, veces, 0
        self.publicados: list[dict] = []

    def __call__(self, _wid, tipo, datos):
        if tipo == 'job' and datos.get('status') == self.estado and self.fallos < self.veces:
            self.fallos += 1
            raise OSError('prueba: canal de eventos no disponible')
        self.publicados.append(datos)


def test_fallo_al_emitir_running_no_mata_el_carril(tmp_path):
    observador = _Observador(RUNNING)
    manager = JobManager(observador)
    corrio = {'primero': False, 'segundo': False}
    try:
        primero = manager.submit('esp', 'prueba', 'Primero', lambda _ctx: corrio.__setitem__('primero', True))
        _esperar_fin(primero)
        assert primero.status == FAILED, f'el trabajo quedó «{primero.status}» con el inicio sin publicar'
        assert primero.error and 'no se ejecutó' in primero.error
        assert corrio['primero'] is False, 'se ejecutó un trabajo cuyo inicio no se pudo observar'
        segundo = manager.submit('esp', 'prueba', 'Segundo', lambda _ctx: corrio.__setitem__('segundo', True))
        _esperar_fin(segundo)
        assert segundo.status == DONE and corrio['segundo'], 'el carril murió con el fallo del observador'
        assert manager._threads['engine'].is_alive()
    finally:
        manager.shutdown(timeout_s=2)


@pytest.mark.parametrize('estado_final', [DONE, FAILED])
def test_fallo_al_emitir_terminal_no_bloquea_el_siguiente(tmp_path, estado_final):
    observador = _Observador(estado_final)
    manager = JobManager(observador)

    def cuerpo(_ctx):
        if estado_final == FAILED:
            raise ValueError('prueba: el cuerpo falla')
        return {'ok': True}

    try:
        primero = manager.submit('esp', 'prueba', 'Primero', cuerpo)
        _esperar_fin(primero)
        assert primero.status == estado_final
        consultado = manager.get(primero.id)
        assert consultado is not None and consultado.status == estado_final, 'el resultado dejó de ser consultable'
        if estado_final == DONE:
            assert consultado.result == {'ok': True}
        siguiente = manager.submit('esp', 'prueba', 'Siguiente', lambda _ctx: 7)
        _esperar_fin(siguiente)
        assert siguiente.status == DONE and siguiente.result == 7, 'el carril se paró tras el fallo del final'
        assert manager._threads['engine'].is_alive()
    finally:
        manager.shutdown(timeout_s=2)


def test_diario_inaccesible_rechaza_antes_del_efecto(tmp_path):
    bloqueo = tmp_path / 'no_es_carpeta'
    bloqueo.write_text('fichero que ocupa el sitio de la carpeta', encoding='utf-8')
    manager = JobManager(lambda *_a: None, diario=bloqueo / 'diario')
    corrio = threading.Event()
    try:
        with pytest.raises(OSError, match='recibo durable'):
            manager.submit('esp', 'prueba', 'Sin recibo', lambda _ctx: corrio.set())
        assert not corrio.wait(0.3), 'se ejecutó un trabajo sin su recibo durable'
        assert manager.list() == [], 'quedó admitido un trabajo sin recibo'
        assert manager.en_curso() == 0
    finally:
        manager.shutdown(timeout_s=2)


def test_sin_diario_se_admite_como_siempre(tmp_path):
    manager = JobManager(lambda *_a: None)
    try:
        job = manager.submit('esp', 'prueba', 'Sin diario', lambda _ctx: 'hecho')
        _esperar_fin(job)
        assert job.status == DONE and job.result == 'hecho'
    finally:
        manager.shutdown(timeout_s=2)


def test_diario_que_falla_al_empezar_no_deja_el_trabajo_en_curso(tmp_path, monkeypatch):
    """El recibo se guardó al admitir, pero el diario falla al empezar: el trabajo termina, no queda colgado."""
    manager = JobManager(lambda *_a: None, diario=tmp_path / 'diario')
    corrio = threading.Event()
    original = manager._diario.anotar
    fallos = []

    def anotar(job):
        if job.status == RUNNING and not fallos:
            fallos.append(job.id)
            raise OSError('prueba: disco lleno al empezar')
        return original(job)

    monkeypatch.setattr(manager._diario, 'anotar', anotar)
    try:
        job = manager.submit('esp', 'prueba', 'Diario roto', lambda _ctx: corrio.set())
        _esperar_fin(job)
        assert job.status == FAILED and not corrio.is_set()
        siguiente = manager.submit('esp', 'prueba', 'Siguiente', lambda _ctx: 1)
        _esperar_fin(siguiente)
        assert siguiente.status == DONE
    finally:
        manager.shutdown(timeout_s=2)
