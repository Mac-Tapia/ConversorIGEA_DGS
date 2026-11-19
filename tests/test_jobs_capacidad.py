"""086:RF-114 (T84): la cola de trabajos y los terminados en memoria tienen tope (auditoría del 18-11, H05).

- Con la cola de un espacio y carril llena, el siguiente se rechaza antes de anotar su recibo, publicarlo o encolarlo;
  otro carril u otro espacio siguen admitiendo.
- Al terminar trabajos, los terminados de un espacio se depuran hasta el tope, los más antiguos primero, sin perder un
  interrumpido, una cadena de relanzados, el último de cada tipo ni una descarga cuyo fichero sigue en disco.
"""
from __future__ import annotations

import threading

import pytest

from convertersmartgrid.presentacion.web.jobs import (
    DONE, FINISHED, INTERRUMPIDO, QUEUED, Job, JobManager, TrabajoRechazado,
)

ESPERA_S = 5.0


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


def _gestor_con_carril_tapado(tmp_path, monkeypatch, tope: int):
    """Un gestor con diario y el carril «engine» ocupado por un trabajo que espera a ``soltar``."""
    monkeypatch.setenv('CSG_TRABAJOS_EN_COLA_MAX', str(tope))
    eventos: list[tuple[str, str, dict]] = []
    jobs = JobManager(lambda w, k, d: eventos.append((w, k, dict(d))), diario=tmp_path / 'diario')
    soltar = threading.Event()
    corriendo = jobs.submit('W', 'tapon', 'tapón', lambda _ctx: soltar.wait(ESPERA_S), lane='engine')
    _esperar(lambda: corriendo.status != QUEUED)
    return jobs, eventos, soltar


def test_cola_llena_rechaza_sin_efectos(tmp_path, monkeypatch):
    jobs, eventos, soltar = _gestor_con_carril_tapado(tmp_path, monkeypatch, tope=2)
    try:
        ejecutado = threading.Event()
        en_espera = [jobs.submit('W', 'calc', f'c{i}', lambda _ctx: ejecutado.set(), lane='engine') for i in range(2)]
        assert all(j.status == QUEUED for j in en_espera)
        antes_jobs = {j.id for j in jobs.list()}
        antes_eventos = len(eventos)
        antes_recibos = sorted(p.name for p in (tmp_path / 'diario').glob('*.json'))

        with pytest.raises(TrabajoRechazado) as rechazo:
            jobs.submit('W', 'calc', 'uno de más', lambda _ctx: ejecutado.set(), lane='engine')

        assert 'esperando' in str(rechazo.value)
        assert 'RF-' not in str(rechazo.value), 'el operador no lee requisitos'
        assert {j.id for j in jobs.list()} == antes_jobs, 'el rechazado no entra en la lista'
        assert len(eventos) == antes_eventos, 'el rechazado no se publica'
        assert sorted(p.name for p in (tmp_path / 'diario').glob('*.json')) == antes_recibos, 'ni deja recibo'
    finally:
        soltar.set()


def test_cola_llena_no_tapa_otro_carril_ni_otro_espacio(tmp_path, monkeypatch):
    jobs, _eventos, soltar = _gestor_con_carril_tapado(tmp_path, monkeypatch, tope=1)
    try:
        jobs.submit('W', 'calc', 'espera', lambda _ctx: None, lane='engine')
        with pytest.raises(TrabajoRechazado):
            jobs.submit('W', 'calc', 'de más', lambda _ctx: None, lane='engine')
        otro_carril = jobs.submit('W', 'correo', 'correo', lambda _ctx: None, lane='correo')
        otro_espacio = jobs.submit('OTRO', 'calc', 'del otro', lambda _ctx: None, lane='engine')
        assert otro_carril.status in (QUEUED, *FINISHED, 'running')
        assert otro_espacio.status == QUEUED
    finally:
        soltar.set()


def test_al_avanzar_la_cola_vuelve_a_admitir(tmp_path, monkeypatch):
    jobs, _eventos, soltar = _gestor_con_carril_tapado(tmp_path, monkeypatch, tope=1)
    espera = jobs.submit('W', 'calc', 'espera', lambda _ctx: None, lane='engine')
    with pytest.raises(TrabajoRechazado):
        jobs.submit('W', 'calc', 'de más', lambda _ctx: None, lane='engine')
    soltar.set()
    _esperar(lambda: espera.status in FINISHED)
    assert jobs.submit('W', 'calc', 'ahora sí', lambda _ctx: None, lane='engine').id


@pytest.mark.parametrize('valor', ['', 'cero', '0', '-3', '2.5'])
def test_tope_no_valido_deja_el_de_por_defecto(tmp_path, monkeypatch, valor):
    from convertersmartgrid.presentacion.web import jobs as modulo

    monkeypatch.setenv('CSG_TRABAJOS_EN_COLA_MAX', valor)
    monkeypatch.setenv('CSG_TRABAJOS_TERMINADOS_MAX', valor)
    tope = getattr(modulo, 'tope_de_entorno', None)
    assert callable(tope), 'los topes se leen del entorno con su valor por defecto'
    assert (getattr(modulo, 'COLA_MAX', None), getattr(modulo, 'TERMINADOS_MAX', None)) == (64, 200)
    assert tope('CSG_TRABAJOS_EN_COLA_MAX', 64) == 64
    assert tope('CSG_TRABAJOS_TERMINADOS_MAX', 200) == 200


def _terminado(jobs: JobManager, kind: str, creado: float, **extra) -> Job:
    job = Job(kind=kind, title=kind, workspace_id=extra.pop('workspace_id', 'W'), lane='engine',
              fn=lambda _ctx: None, status=extra.pop('status', DONE), created_at=creado, finished_at=creado, **extra)
    jobs._jobs[job.id] = job
    return job


def test_depuracion_no_pierde_resultado_referenciado(tmp_path, monkeypatch):
    monkeypatch.setenv('CSG_TRABAJOS_TERMINADOS_MAX', '3')
    jobs = JobManager(lambda *_a: None)
    zip_vivo = tmp_path / 'salida.zip'
    zip_vivo.write_bytes(b'PK')
    interrumpido = _terminado(jobs, 'recalibrar', 1, status=INTERRUMPIDO)
    ancestro = _terminado(jobs, 'recalibrar', 2, status='failed')
    sucesor = _terminado(jobs, 'recalibrar', 3, relanzado_de=ancestro.id)
    descarga = _terminado(jobs, 'archive', 4)
    descarga._archivo_zip = zip_vivo
    descarga_vieja = _terminado(jobs, 'archive', 5)
    descarga_vieja._archivo_zip = tmp_path / 'ya_no_esta.zip'
    viejos = [_terminado(jobs, 'calc', 10 + i) for i in range(5)]
    cabecera = _terminado(jobs, 'demanda_cabecera', 20)
    del_otro = [_terminado(jobs, 'calc', 30 + i, workspace_id='OTRO') for i in range(5)]
    ultimo_archive = _terminado(jobs, 'archive', 40)

    hecho = jobs.submit('W', 'calc', 'el que termina', lambda _ctx: None, lane='engine')
    _esperar(lambda: hecho.status in FINISHED)
    _esperar(lambda: jobs.get(viejos[0].id) is None)

    quedan = {j.id for j in jobs.list('W')}
    for protegido in (interrumpido, ancestro, sucesor, descarga, cabecera, ultimo_archive, hecho):
        assert protegido.id in quedan, f'{protegido.kind} protegido se perdió'
    assert all(j.id not in quedan for j in viejos), 'los calc antiguos sobran: el último calc es el que termina'
    assert descarga_vieja.id not in quedan, 'una descarga sin fichero no protege'
    assert {j.id for j in jobs.list('OTRO')} == {j.id for j in del_otro}, 'otro espacio no se depura por este'


def test_sin_pasar_el_tope_no_se_quita_nada(monkeypatch):
    monkeypatch.setenv('CSG_TRABAJOS_TERMINADOS_MAX', '50')
    jobs = JobManager(lambda *_a: None)
    previos = [_terminado(jobs, 'calc', i) for i in range(10)]
    hecho = jobs.submit('W', 'calc', 'otro', lambda _ctx: None)
    _esperar(lambda: hecho.status in FINISHED)
    assert {j.id for j in previos} <= {j.id for j in jobs.list('W')}
