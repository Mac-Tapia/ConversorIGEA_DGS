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


def _hasta(condicion, segundos=15):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return
        time.sleep(0.02)
    raise AssertionError('el proceso propio no alcanzó el punto esperado')


def _json(ruta, segundos=15):
    """El JSON que escribe el proceso hijo, ya completo: lo crea y lo escribe después, y leerlo en medio daba
    ``JSONDecodeError`` una vez de cada pocas (puerta de calidad, 2026-11-10)."""
    limite = time.monotonic() + segundos
    while True:
        try:
            return json.loads(ruta.read_text())
        except (OSError, ValueError):
            if time.monotonic() >= limite:
                raise
            time.sleep(0.02)


def _servidor_con_hijo(tmp_path, *, cancelar=False, motor=False, antes_anotar=False):
    """Diario producido por JobManager real; el servidor cae sin cerrar al trabajador."""
    guion = tmp_path / 'servidor_con_hijo.py'
    guion.write_text(textwrap.dedent(f'''
        import json, os, time
        from pathlib import Path
        from convertersmartgrid.web.jobs import JobManager, JobContext
        raiz = Path({str(tmp_path)!r})
        if {antes_anotar!r}:
            def sin_confirmar(self, pid):
                (raiz / 'antes_anotar').touch()
                time.sleep(60)
            JobContext.anotar_proceso = sin_confirmar
        def trabajador(*, progreso, log, cancelado):
            (raiz / 'hijo.json').write_text(json.dumps({{'pid': os.getpid()}}))
            time.sleep(60)
        if __name__ == '__main__':
            j = JobManager(lambda *a: None, diario=raiz / '_trabajos')
            def f(ctx):
                if {motor!r}:
                    return ctx.en_proceso(trabajador)
                return ctx.run_process([{sys.executable!r}, '-c',
                    'import json,os,time;from pathlib import Path;'
                    + 'Path(' + repr(str(raiz / 'hijo.json')) + ').write_text(json.dumps({{"pid":os.getpid()}}));'
                    + 'print("trabajador listo",flush=True);time.sleep(60)'])
            job = j.submit({WID!r}, 'recalibrar', 'Recalibrar propio', f,
                           reanudar={{'tipo': 'recalibrar', 'datos': {{'project': 'propio', 'periodo': '2026'}}}},
                           relanzado_de='origen_propio')
            while not (raiz / 'hijo.json').exists(): time.sleep(0.01)
            if {cancelar!r}: j.cancel(job.id)
            (raiz / 'servidor.json').write_text(json.dumps({{'id': job.id, 'pid': os.getpid()}}))
            time.sleep(60)
    '''), encoding='utf-8')
    entorno = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src'),
               'CSG_RUNTIME_HOME': str(tmp_path / 'runtime'), 'CSG_CACHE_HOME': str(tmp_path / 'cache')}
    # Este ensayo no pide el motor ni inspecciona procesos PowerFactory del usuario.
    entorno.pop('PF_PYTHON', None)
    proceso = subprocess.Popen([sys.executable, str(guion)], env=entorno,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return proceso


def test_identidad_incompleta_de_un_pid_real_muerto_no_bloquea():
    """096:RF-6 — primero comprobar muerte: la ausencia de fecha no mantiene vivo un PID que ya no existe."""
    import psutil
    from convertersmartgrid.web.jobs import proceso_pendiente

    proceso = subprocess.Popen([sys.executable, '-c', 'pass'])
    proceso.wait(10)
    assert not psutil.pid_exists(proceso.pid)
    assert not proceso_pendiente({'pid': proceso.pid, 'inicio': None})


@pytest.mark.parametrize('motor', [False, True], ids=['guion', 'motor'])
def test_reserva_anterior_al_spawn_se_retira_si_creacion_falla(tmp_path, monkeypatch, motor):
    """096:RF-6 — la reserva existe antes de crear el hijo y un error de creación no la deja bloqueando."""
    import multiprocessing.process
    from convertersmartgrid.web.jobs import DiarioTrabajos, Job, JobContext

    diario = DiarioTrabajos(tmp_path / '_trabajos')
    job = Job('k', 't', WID, 'engine', lambda ctx: None)
    diario.anotar(job)
    ctx = JobContext(job, lambda *a: None, diario)
    def fallar(*args, **kwargs):
        datos = _json(tmp_path / '_trabajos' / f'{job.id}.json')
        assert (datos.get('proceso') or {}).get('estado') == 'lanzando'
        raise OSError('creación propia denegada')
    if motor:
        monkeypatch.setattr(multiprocessing.process.BaseProcess, 'start', fallar)
    else:
        monkeypatch.setattr(subprocess, 'Popen', fallar)
    with pytest.raises(OSError, match='creación propia denegada'):
        if motor:
            ctx.en_proceso(lambda **kw: None)
        else:
            ctx.run_process(['solo-ensayo'], env={})
    assert job.proceso is None
    assert _json(tmp_path / '_trabajos' / f'{job.id}.json')['proceso'] is None


def test_no_crear_hijo_si_no_se_puede_persistir_reserva(tmp_path, monkeypatch):
    """096:RF-6 / 086:RF-9 — un diario no durable no permite crear un trabajador sin recibo previo."""
    from convertersmartgrid.web.jobs import DiarioTrabajos, Job, JobContext

    diario = DiarioTrabajos(tmp_path / '_trabajos')
    job = Job('k', 't', WID, 'engine', lambda ctx: None)
    diario.anotar(job)
    ctx = JobContext(job, lambda *a: None, diario)
    def sin_disco(*a, **k):
        raise OSError('sin disco propio')
    monkeypatch.setattr('convertersmartgrid.util.write_json_atomic', sin_disco)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('se creó un hijo sin reserva durable'))
    with pytest.raises(OSError, match='reserva'):
        ctx.run_process(['solo-ensayo'], env={})


@pytest.mark.parametrize('motor', [False, True], ids=['guion', 'motor'])
def test_caida_entre_crear_hijo_y_confirmar_identidad_no_autoriza_otro(tmp_path, motor):
    """096:RF-6 — una reserva durable anterior al spawn evita repetir si el servidor muere antes del recibo."""
    import psutil
    from convertersmartgrid.web.jobs import JobManager

    proceso = _servidor_con_hijo(tmp_path, motor=motor, antes_anotar=True)
    hijo = None
    try:
        _hasta(lambda: (tmp_path / 'servidor.json').exists() and (tmp_path / 'antes_anotar').exists())
        servidor = _json(tmp_path / 'servidor.json')
        hijo = psutil.Process(_json(tmp_path / 'hijo.json')['pid'])
        psutil.Process(servidor['pid']).kill()
        proceso.wait(10)
        assert hijo.is_running()
        jobs = JobManager(lambda *a: None, diario=tmp_path / '_trabajos')
        assert jobs.get(servidor['id']).status == 'interrumpido'
        assert jobs.reanudables() == [], 'el hijo existe pero aún no se confirmó su identidad'
        hijo.kill()
        hijo.wait(10)
        # Sin recibo no se puede identificar qué proceso terminó: queda para revisión explícita.
        assert JobManager(lambda *a: None, diario=tmp_path / '_trabajos').reanudables() == []
    finally:
        if hijo is not None and hijo.is_running():
            hijo.kill()
            hijo.wait(10)
        if proceso.poll() is None:
            _matar_de_golpe(proceso)


def test_trabajo_terminado_no_bloquea_otra_recuperacion(tmp_path):
    """096:RF-6 — una identidad residual de un trabajo ya terminado no bloquea otro interrumpido."""
    from convertersmartgrid.web.jobs import JobManager

    proceso = _servidor_con_hijo(tmp_path, motor=True)
    try:
        _hasta(lambda: (tmp_path / 'servidor.json').exists())
        servidor = _json(tmp_path / 'servidor.json')
    finally:
        _matar_de_golpe(proceso)
    jobs = JobManager(lambda *a: None, diario=tmp_path / '_trabajos')
    otro = jobs.submit(WID, 'k', 't', lambda ctx: ctx.anotar_proceso(os.getpid()))
    _esperar(jobs, otro)
    assert otro.status == 'done'
    assert [j.id for j in jobs.reanudables()] == [servidor['id']]
    jobs.shutdown(5)


@pytest.mark.parametrize('fallar', [False, True], ids=['done', 'failed'])
def test_caida_tras_finalizar_sucesor_antes_de_marcar_ancestro_no_lo_repite(tmp_path, fallar):
    """096:RF-5 / 096:RF-6 — la muerte entre admitir sucesor y marcar el viejo no repite su efecto ya registrado."""
    import psutil
    from convertersmartgrid.web.jobs import JobManager

    proceso = _servidor_con_hijo(tmp_path, motor=True)
    try:
        _hasta(lambda: (tmp_path / 'servidor.json').exists())
        anterior = _json(tmp_path / 'servidor.json')['id']
    finally:
        _matar_de_golpe(proceso)
    guion = tmp_path / 'sucesor.py'
    guion.write_text(textwrap.dedent(f'''
        import os,time,json,threading
        from pathlib import Path
        from convertersmartgrid.web.jobs import JobManager,FINISHED
        raiz=Path({str(tmp_path)!r})
        finalizado=threading.Event()
        def emitir(w,k,d):
            if k=='job' and d.get('status') in ('done','failed'): finalizado.set()
        jobs=JobManager(emitir,diario=raiz/'_trabajos')
        def efecto(ctx):
            (raiz/'efecto.txt').write_text('una escritura')
            if {fallar!r}: raise RuntimeError('fallo propio posterior al efecto')
            return {{'ok':True}}
        nuevo=jobs.submit({WID!r},'recalibrar','Sucesor propio',efecto,
                          reanudar={{'tipo':'recalibrar','datos':{{'project':'propio','periodo':'2026'}}}},
                          relanzado_de={anterior!r})
        assert finalizado.wait(10)
        # La llamada a marcar_relanzado del consumidor todavía no ha ocurrido.
        (raiz/'sucesor_listo.json').write_text(json.dumps({{'pid':os.getpid(),'id':nuevo.id}}))
        time.sleep(60)
    '''), encoding='utf-8')
    entorno = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
    segundo = subprocess.Popen([sys.executable, str(guion)], env=entorno,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        _hasta(lambda: (tmp_path / 'sucesor_listo.json').exists())
        listo = _json(tmp_path / 'sucesor_listo.json')
        psutil.Process(listo['pid']).kill()
        segundo.wait(10)
        observados = []
        jobs = JobManager(lambda w, k, d: observados.append(d), diario=tmp_path / '_trabajos')
        assert jobs.reanudables() == [], 'el ancestro reaparece aunque su sucesor ya terminó'
        recuperado = jobs.get(listo['id'])
        assert recuperado.status == ('failed' if fallar else 'done')
        if fallar:
            assert 'fallo propio posterior al efecto' in recuperado.error
        else:
            assert recuperado.result == {'ok': True}
        assert not any(d.get('status') in ('done', 'failed') for d in observados), 'releer no repite efectos del emisor'
        assert (tmp_path / 'efecto.txt').read_text() == 'una escritura'
    finally:
        if segundo.poll() is None:
            _matar_de_golpe(segundo)


@pytest.mark.parametrize('motor', [False, True], ids=['guion', 'motor'])
def test_caida_real_no_relanzar_encima_de_un_trabajador_vivo(tmp_path, motor):
    """096:RF-6 / 086:RF-9 — retirar la identidad del hijo permitiría duplicar una escritura en curso."""
    import psutil
    from convertersmartgrid.web.jobs import JobManager

    proceso = _servidor_con_hijo(tmp_path, motor=motor)
    hijo = None
    try:
        _hasta(lambda: (tmp_path / 'servidor.json').exists())
        servidor = _json(tmp_path / 'servidor.json')
        hijo = psutil.Process(_json(tmp_path / 'hijo.json')['pid'])
        # Matar solo el servidor real: en Windows el ejecutable venv puede ser un lanzador.
        psutil.Process(servidor['pid']).kill()
        proceso.wait(10)
        assert hijo.is_running()
        jobs = JobManager(lambda *a: None, diario=tmp_path / '_trabajos')
        job = jobs.get(servidor['id'])
        assert job.status == 'interrumpido'
        assert jobs.reanudables() == [], 'se iba a duplicar el trabajador que aún está vivo'
        assert job.relanzado_de == 'origen_propio'
        hijo.kill()
        hijo.wait(10)
        _hasta(lambda: bool(jobs.reanudables()))
        assert [j.id for j in jobs.reanudables()] == [job.id]
    finally:
        if hijo is not None and hijo.is_running():
            hijo.kill()
            hijo.wait(10)
        if proceso.poll() is None:
            _matar_de_golpe(proceso)


def test_cancelacion_persistida_impide_reanudar_tras_muerte_real(tmp_path):
    """096:RF-4 / 086:RF-9 — olvidar cancel_requested reactivaría la orden cancelada tras caer la web."""
    from convertersmartgrid.web.jobs import JobManager

    proceso = _servidor_con_hijo(tmp_path, cancelar=True, motor=True)
    try:
        _hasta(lambda: (tmp_path / 'servidor.json').exists())
        servidor = _json(tmp_path / 'servidor.json')
    finally:
        _matar_de_golpe(proceso)
    jobs = JobManager(lambda *a: None, diario=tmp_path / '_trabajos')
    job = jobs.get(servidor['id'])
    assert job is not None and job.cancel.is_set()
    assert jobs.reanudables() == []
    # Otro arranque conserva la decisión del operador.
    assert JobManager(lambda *a: None, diario=tmp_path / '_trabajos').get(job.id).cancel.is_set()


@pytest.mark.parametrize('concurrente', [False, True], ids=['rechazo-prevalidacion', 'dos-relanzadores'])
def test_relanzar_real_es_reintentable_y_exclusivo(tmp_path, monkeypatch, concurrente):
    """096:RF-5 / 096:RF-6 — consumir antes de admitir pierde la orden; dos relanzadores la duplican."""
    from convertersmartgrid.web import services
    from convertersmartgrid.web.app import create_app
    from convertersmartgrid.web.workspace import Workspace

    raiz = tmp_path / 'web'
    raiz.mkdir()
    Workspace(id=WID, root=raiz / WID).save()
    proceso = _servidor_con_hijo(raiz, motor=True)
    try:
        _hasta(lambda: (raiz / 'servidor.json').exists())
    finally:
        _matar_de_golpe(proceso)
    llamadas, ejecuciones = [], []

    def prevalidar(*_):
        llamadas.append(1)
        if not concurrente and len(llamadas) == 1:
            raise ValueError('ruta temporalmente no disponible')
        if concurrente:
            # Asegura que el segundo relanzador entra durante la prevalidación del primero.
            entrando.set()
            assert seguir.wait(5)
        return {'del_sistema': []}

    monkeypatch.setattr(services, 'recalibrar_datos', prevalidar)
    monkeypatch.setattr(services, 'recalibrar_sistema', lambda *a, **k: ejecuciones.append(1) or {'codigo': 0})
    app = create_app(raiz)
    if not concurrente:
        assert app.state.relanzar_interrumpidos() == []
        lanzados = app.state.relanzar_interrumpidos()
        assert len(lanzados) == 1, 'un rechazo previo a la admisión consumió la recuperación'
    else:
        entrando, seguir = threading.Event(), threading.Event()
        resultados = []
        primero = threading.Thread(target=lambda: resultados.append(app.state.relanzar_interrumpidos()))
        segundo = threading.Thread(target=lambda: resultados.append(app.state.relanzar_interrumpidos()))
        primero.start()
        assert entrando.wait(5)
        segundo.start()
        seguir.set()
        primero.join(10)
        segundo.join(10)
        assert not primero.is_alive() and not segundo.is_alive()
        assert sum(map(len, resultados)) == 1
    _hasta(lambda: bool(ejecuciones))
    assert ejecuciones == [1]
    assert app.state.relanzar_interrumpidos() == []


def test_identidad_ambigua_bloquea_y_pid_reutilizado_no_bloquea():
    """096:RF-6 — una fecha ilegible no autoriza repetir ni enviar señales a ese PID."""
    import psutil
    from convertersmartgrid.web.jobs import proceso_pendiente

    inicio = psutil.Process(os.getpid()).create_time()
    assert proceso_pendiente({'pid': os.getpid(), 'inicio': inicio})
    assert not proceso_pendiente({'pid': os.getpid(), 'inicio': inicio - 100})
    for identidad in ({'pid': os.getpid(), 'inicio': None}, {'pid': os.getpid(), 'inicio': 'ilegible'},
                      {'pid': os.getpid()}, {'pid': -1, 'inicio': inicio}):
        assert proceso_pendiente(identidad)


@pytest.mark.parametrize('rechazar', [False, True], ids=['esperar-hijo', 'sin-bucle-invalido'])
def test_lifecycle_retoma_despues_de_la_muerte_real_del_hijo_y_se_detiene(tmp_path, monkeypatch, rechazar):
    """096:RF-5 / 096:RF-6 — comprobar solo al arrancar abandonaría el trabajo cuyo hijo aún vive."""
    import psutil
    from convertersmartgrid.web import services
    from convertersmartgrid.web.app import create_app
    from convertersmartgrid.web.workspace import Workspace

    raiz = tmp_path / 'web'
    raiz.mkdir()
    Workspace(id=WID, root=raiz / WID).save()
    proceso = _servidor_con_hijo(raiz, motor=True)
    hijo = None
    try:
        _hasta(lambda: (raiz / 'servidor.json').exists())
        servidor = _json(raiz / 'servidor.json')
        hijo = psutil.Process(_json(raiz / 'hijo.json')['pid'])
        psutil.Process(servidor['pid']).kill()
        proceso.wait(10)
        ejecuciones, intentos = [], []
        def prevalidar(*_):
            intentos.append(1)
            if rechazar:
                raise ValueError('requiere revisar ruta')
            return {'del_sistema': []}
        monkeypatch.setattr(services, 'recalibrar_datos', prevalidar)
        monkeypatch.setattr(services, 'recalibrar_sistema', lambda *a, **k: ejecuciones.append(1) or {'codigo': 0})
        monkeypatch.setenv('CSG_WEB_RELANZAR', '1')
        app = create_app(raiz)
        with TestClient(app):
            assert intentos == [] and hijo.is_running()
            hijo.kill()
            hijo.wait(10)
            _hasta(lambda: bool(intentos), segundos=6)
            if rechazar:
                assert ejecuciones == []
                assert not app.state.jobs.get(servidor['id']).relanzado
                assert 'ruta' in app.state.recuperaciones_interrumpidas[servidor['id']]['motivo']
            else:
                _hasta(lambda: bool(ejecuciones))
                assert ejecuciones == [1]
            # Varias vueltas del monitor no repiten una admisión ni una prevalidación inválida.
            time.sleep(2.2)
            assert intentos == [1]
        assert app.state.tarea_reanudacion.done() and app.state.jobs._closing
    finally:
        if hijo is not None and hijo.is_running():
            hijo.kill()
            hijo.wait(10)
        if proceso.poll() is None:
            _matar_de_golpe(proceso)


def test_un_emit_roto_no_pierde_cancelacion_persistida(tmp_path):
    """096:RF-4 / 086:RF-9 — el fallo de notificación posterior a cancelar no borra la decisión."""
    from convertersmartgrid.web.jobs import JobManager

    iniciado, seguir = threading.Event(), threading.Event()
    def emitir(_wid, _tipo, datos):
        if datos.get('cancel_requested'):
            raise OSError('navegador desconectado')
    jobs = JobManager(emitir, diario=tmp_path / '_trabajos')
    job = jobs.submit(WID, 'k', 't', lambda ctx: (iniciado.set(), seguir.wait(10)))
    assert iniciado.wait(5)
    try:
        with pytest.raises(OSError, match='desconectado'):
            jobs.cancel(job.id)
        assert _json(tmp_path / '_trabajos' / f'{job.id}.json')['cancel_requested'] is True
    finally:
        seguir.set()
        # El emisor fallido no debe escapar de la limpieza de este ensayo.
        jobs._emit = lambda *a: None
        jobs.shutdown(10)


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
