"""Spec 086, RF-9: un trabajo a medias se ve tras reiniciar la web, con su registro."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

WID = 'ab' * 8


def _matar_de_golpe(proceso: subprocess.Popen) -> None:
    """Con sus hijos, y hasta que no quede ninguno: el Python de un venv en Windows es un lanzador,
    y matarlo solo deja vivo un momento al proceso real, que seguiría escribiendo."""
    import psutil

    arbol = psutil.Process(proceso.pid).children(recursive=True)
    proceso.kill()
    proceso.wait()
    for hijo in arbol:
        try:
            hijo.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(arbol, timeout=10)


def _esperar(jobs, *trabajos, segundos: float = 10.0) -> None:
    """Hasta que terminen: ``shutdown`` cancela lo que siga corriendo, y esa no es la prueba."""
    from convertersmartgrid.web.jobs import FINISHED

    limite = time.monotonic() + segundos
    while time.monotonic() < limite and any(j.status not in FINISHED for j in trabajos):
        time.sleep(0.01)
    assert all(j.status in FINISHED for j in trabajos)


def _matar_a_media_corrida(tmp_path, diario: Path) -> tuple[str, str]:
    """Un servidor de verdad, otro proceso, que muere sin avisar con un trabajo corriendo y otro en cola."""
    guion = tmp_path / 'servidor.py'
    guion.write_text(textwrap.dedent(f'''
        import time
        from pathlib import Path
        from convertersmartgrid.web.jobs import JobManager
        j = JobManager(lambda *a: None, diario=Path({str(diario)!r}))
        listo = []
        def f(ctx):
            ctx.log('primera línea del guion')
            ctx.progress(3, 10, 'alimentador tres')
            ctx.log('segunda línea del guion')
            time.sleep(0.05)
            print(job.id, flush=True)
            time.sleep(60)
        job = j.submit({WID!r}, 'calibrar', 'Calibrar el proyecto', f, lane='powerfactory')
        cola = j.submit({WID!r}, 'estudio', 'Estudio en cola', lambda c: None, lane='powerfactory')
        print(cola.id, flush=True)
        time.sleep(60)
    '''), encoding='utf-8')
    entorno = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src'),
               'CSG_RUNTIME_HOME': str(tmp_path / 'runtime'), 'CSG_CACHE_HOME': str(tmp_path / 'cache')}
    proceso = subprocess.Popen([sys.executable, str(guion)], stdout=subprocess.PIPE, text=True, env=entorno)
    try:
        cola = proceso.stdout.readline().strip()
        corriendo = proceso.stdout.readline().strip()
    finally:
        _matar_de_golpe(proceso)
    assert cola and corriendo
    return corriendo, cola


def test_matar_el_proceso_deja_el_trabajo_interrumpido_con_su_registro(tmp_path):
    """086:RF-9 — el proceso muere de golpe: al arrancar otro, se ve interrumpido, con avance y registro."""
    from convertersmartgrid.web.jobs import FINISHED, INTERRUMPIDO, JobManager

    diario = tmp_path / '_trabajos'
    corriendo, cola = _matar_a_media_corrida(tmp_path, diario)
    vistos = []
    jobs = JobManager(lambda *a: vistos.append(a), diario=diario)
    trabajo = jobs.get(corriendo)
    assert trabajo is not None and trabajo.status == INTERRUMPIDO and trabajo.status in FINISHED
    assert trabajo.title == 'Calibrar el proyecto' and trabajo.workspace_id == WID
    assert trabajo.progress == {'index': 3, 'total': 10, 'label': 'alimentador tres'}
    assert 'se detuvo' in trabajo.error and trabajo.finished_at
    assert jobs.registro(corriendo) == ['primera línea del guion', 'segunda línea del guion']
    # El que estaba en cola tampoco terminó, y no se relanza solo.
    assert jobs.get(cola).status == INTERRUMPIDO
    assert not jobs.active(WID) and jobs.en_curso() == 0
    assert {a[2]['id'] for a in vistos} == {corriendo, cola}
    # El siguiente reinicio lo sigue viendo igual, sin cambiar la hora.
    hora = trabajo.finished_at
    otra = JobManager(lambda *a: None, diario=diario)
    assert otra.get(corriendo).status == INTERRUMPIDO and otra.get(corriendo).finished_at == hora


def test_la_api_lo_muestra_tras_reiniciar(tmp_path):
    """086:RF-9 — por la web: el espacio lo lista, el trabajo se abre y su registro se lee."""
    from convertersmartgrid.web.app import create_app
    from convertersmartgrid.web.workspace import WorkspaceStore

    ws = WorkspaceStore(tmp_path / 'web').create()
    diario = tmp_path / 'web' / '_trabajos'
    global WID
    anterior, WID = WID, ws.id
    try:
        corriendo, _ = _matar_a_media_corrida(tmp_path, diario)
    finally:
        WID = anterior
    with TestClient(create_app(tmp_path / 'web', host='127.0.0.1')) as cliente:
        publico = cliente.get(f'/api/workspaces/{ws.id}').json()
        assert {j['id']: j['status'] for j in publico['jobs']}[corriendo] == 'interrumpido'
        assert cliente.get(f'/api/jobs/{corriendo}').json()['status'] == 'interrumpido'
        assert cliente.get(f'/api/jobs/{corriendo}/registro').json()['lineas'] == [
            'primera línea del guion', 'segunda línea del guion']
        assert cliente.get('/api/jobs/noexiste/registro').status_code == 404
        # Cancelarlo no hace nada, y el carril queda libre para trabajar.
        assert cliente.post(f'/api/jobs/{corriendo}/cancel').json()['status'] == 'interrumpido'
        assert cliente.get('/api/health').json()['servidor']['trabajos_en_curso'] == 0
        # Y se ve en lo que observa el asistente, sin romperlo.
        assert cliente.get(f'/api/workspaces/{ws.id}/asistente/monitor').status_code == 200
        assert cliente.get(f'/api/workspaces/{ws.id}/events').json()


def test_terminar_con_normalidad_retira_su_diario(tmp_path):
    """086:RF-9 — el diario solo guarda lo que quedó a medias: lo terminado no se acumula."""
    from convertersmartgrid.web.jobs import JobManager

    diario = tmp_path / '_trabajos'
    jobs = JobManager(lambda *a: None, diario=diario)
    hecho = threading.Event()

    def bien(ctx):
        ctx.log('una línea')
        assert jobs.registro(ctx.job.id) == ['una línea']
        return 1

    def mal(ctx):
        ctx.log('otra')
        raise ValueError('falla')

    uno = jobs.submit(WID, 'k', 't', bien)
    dos = jobs.submit(WID, 'k', 't', mal)
    assert (diario / f'{uno.id}.json').exists() or uno.status != 'queued'
    tres = jobs.submit(WID, 'k', 't', lambda c: hecho.wait(5))
    cancelado = jobs.submit(WID, 'k', 't', lambda c: None)
    jobs.cancel(cancelado.id)
    hecho.set()
    _esperar(jobs, uno, dos, tres, cancelado)
    jobs.shutdown(10)
    assert (uno.status, dos.status, tres.status, cancelado.status) == ('done', 'failed', 'done', 'cancelled')
    assert list(diario.iterdir()) == []
    assert JobManager(lambda *a: None, diario=diario).list() == []


def test_el_trabajo_de_un_servidor_vivo_no_se_marca_interrumpido(tmp_path):
    """086:RF-9 — otro gestor sobre la misma carpeta no le da por muerto lo que sigue corriendo."""
    from convertersmartgrid.web.jobs import JobManager

    diario = tmp_path / '_trabajos'
    jobs = JobManager(lambda *a: None, diario=diario)
    seguir, empezado = threading.Event(), threading.Event()
    job = jobs.submit(WID, 'k', 't', lambda c: (empezado.set(), seguir.wait(10)))
    assert empezado.wait(5)
    try:
        assert JobManager(lambda *a: None, diario=diario).list() == []
        estado = json.loads((diario / f'{job.id}.json').read_text(encoding='utf-8'))['status']
        assert estado == 'running'
    finally:
        seguir.set()
        jobs.shutdown(10)


def test_pid_reutilizado_no_finge_un_trabajo_vivo(tmp_path):
    """086:RF-9 — Windows reutiliza pid: el mismo número con otra hora de arranque es otro proceso."""
    from convertersmartgrid.web import jobs as modulo

    diario = tmp_path / '_trabajos'
    diario.mkdir()
    (diario / 'aaa.json').write_text(json.dumps({
        'id': 'aaa', 'kind': 'k', 'title': 't', 'workspace_id': WID, 'lane': 'engine', 'status': 'running',
        'created_at': 1.0, 'pid': os.getppid(), 'inicio_proceso': 1.0}), encoding='utf-8')
    assert modulo.JobManager(lambda *a: None, diario=diario).get('aaa').status == modulo.INTERRUMPIDO


def test_diario_ilegible_o_que_falla_no_impide_arrancar_ni_trabajar(tmp_path, monkeypatch):
    """086:RF-9 — un corte a media escritura o un disco lleno no paran la web ni el trabajo."""
    from convertersmartgrid.util import write_json_atomic  # noqa: F401 - se sustituye abajo
    from convertersmartgrid.web import jobs as modulo

    diario = tmp_path / '_trabajos'
    diario.mkdir()
    (diario / 'roto.json').write_text('{roto', encoding='utf-8')
    (diario / 'ajeno.json').write_text(json.dumps({'id': 'x'}), encoding='utf-8')
    jobs = modulo.JobManager(lambda *a: None, diario=diario)
    assert jobs.list() == []
    assert (diario / 'roto.json').exists()

    def sin_disco(*_a, **_k):
        raise OSError('disco lleno')

    monkeypatch.setattr('convertersmartgrid.util.write_json_atomic', sin_disco)
    job = jobs.submit(WID, 'k', 't', lambda c: 7)
    _esperar(jobs, job)
    jobs.shutdown(10)
    assert job.status == 'done' and job.result == 7


def test_el_espacio_ausente_no_impide_arrancar(tmp_path):
    """086:RF-9 — el emisor falla con un trabajo interrumpido de un espacio que ya no está: se arranca igual."""
    from convertersmartgrid.web.jobs import INTERRUMPIDO, JobManager

    diario = tmp_path / '_trabajos'
    diario.mkdir()
    (diario / 'aaa.json').write_text(json.dumps({
        'id': 'aaa', 'kind': 'k', 'title': 't', 'workspace_id': WID, 'lane': 'otro', 'status': 'queued',
        'created_at': 1.0, 'pid': -1}), encoding='utf-8')

    def falla(*_a):
        raise OSError('sin espacio')

    job = JobManager(falla, diario=diario).get('aaa')
    assert job.status == INTERRUMPIDO and job.lane == 'engine'


def test_los_interrumpidos_antiguos_no_se_acumulan(tmp_path, monkeypatch):
    """086:RF-9 — quedan los últimos: cada uno lleva su registro, y un servidor que cae mucho llenaría el disco."""
    from convertersmartgrid.web import jobs as modulo

    monkeypatch.setattr(modulo, 'MAX_INTERRUMPIDOS', 2)
    diario = tmp_path / '_trabajos'
    diario.mkdir()
    for n in range(4):
        (diario / f'j{n}.json').write_text(json.dumps({
            'id': f'j{n}', 'kind': 'k', 'title': 't', 'workspace_id': WID, 'lane': 'engine',
            'status': 'interrumpido', 'created_at': float(n)}), encoding='utf-8')
        (diario / f'j{n}.log').write_text('x\n', encoding='utf-8')
    jobs = modulo.JobManager(lambda *a: None, diario=diario)
    assert [j.id for j in jobs.list()] == ['j2', 'j3']
    assert sorted(p.name for p in diario.iterdir()) == ['j2.json', 'j2.log', 'j3.json', 'j3.log']


def test_el_registro_no_crece_sin_limite(tmp_path, monkeypatch):
    """086:RF-9 — un guion que escribe sin parar no llena el disco con su registro."""
    from convertersmartgrid.web import jobs as modulo

    monkeypatch.setattr(modulo, 'LIMITE_REGISTRO_BYTES', 10)
    diario = modulo.DiarioTrabajos(tmp_path / '_trabajos')
    for _ in range(5):
        diario.linea('j', 'una línea larga')
    assert diario.registro('j') == ['una línea larga']
    diario.olvidar('j')
    assert diario.registro('j') is None


@pytest.mark.parametrize('estado', ['interrumpido'])
def test_el_contrato_de_la_api_admite_el_estado(estado):
    """086:RF-9 — la respuesta del trabajo lo admite: sin esto, la API daría un 500."""
    from convertersmartgrid.web import api_contract
    from convertersmartgrid.web.jobs import Job

    job = Job('k', 't', WID, 'engine', lambda c: None, status=estado)
    assert api_contract.JobRespuesta.model_validate(job.public()).status == estado
