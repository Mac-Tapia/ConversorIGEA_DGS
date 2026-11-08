"""096:RF-4/5/6: intercalaciones del diario, retención causal y cierre, sin motor nativo."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import threading

import pytest

from convertersmartgrid.web import jobs as modulo


@pytest.mark.parametrize('etapa', ['avance', 'proceso'])
def test_cancelacion_no_retrocede_tras_escritura_en_vuelo_y_caida_real(tmp_path, etapa):
    """096:RF-4, 086:RF-9 — cancelar sigue durable tras una escritura anterior y muerte propia real."""
    guion = tmp_path / 'servidor_intercalado.py'
    guion.write_text(textwrap.dedent(f'''
        import json,os,threading
        from pathlib import Path
        from convertersmartgrid import util
        from convertersmartgrid.web.jobs import JobManager
        raiz=Path({str(tmp_path)!r})
        real=util.write_json_atomic
        pendiente,continuar,escrito=threading.Event(),threading.Event(),threading.Event()
        cancelada=threading.Event()
        def escribir(path,payload,**kw):
            objetivo=(payload.get('progress') is not None if {etapa!r}=='avance'
                      else payload.get('proceso') is not None)
            atrasada=objetivo and payload.get('cancel_requested') is False
            if atrasada:
                pendiente.set()
                assert continuar.wait(10)
            real(path,payload,**kw)
            if atrasada: escrito.set()
        util.write_json_atomic=escribir
        jobs=JobManager(lambda *_:None,diario=raiz/'diario')
        no_terminar=threading.Event()
        def f(ctx):
            if {etapa!r}=='avance': ctx.progress(1,2,'antes del corte')
            else: ctx.anotar_proceso(os.getpid())
            no_terminar.wait(30)
        job=jobs.submit('W','recalibrar','CPU propia',f,
            reanudar={{'tipo':'recalibrar','datos':{{}}}})
        assert pendiente.wait(10)
        def cancelar():
            jobs.cancel(job.id)
            cancelada.set()
        hilo=threading.Thread(target=cancelar)
        hilo.start()
        assert job.cancel.wait(10)
        # En la versión defectuosa la cancelación completa antes de liberar la escritura vieja.
        cancelada.wait(.3)
        continuar.set()
        assert escrito.wait(10) and cancelada.wait(10)
        hilo.join(10)
        (raiz/'corte.json').write_text(json.dumps({{'id':job.id,
            'cancel_durable':json.loads((raiz/'diario'/(job.id+'.json')).read_text())['cancel_requested']}}))
        os._exit(0)
    '''), encoding='utf-8')
    entorno = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src'),
               'CSG_RUNTIME_HOME': str(tmp_path / 'runtime'), 'CSG_CACHE_HOME': str(tmp_path / 'cache')}
    entorno.pop('CSG_REGISTRO_TRABAJOS', None)
    proceso = subprocess.run([sys.executable, '-B', str(guion)], env=entorno,
        capture_output=True, text=True, timeout=20)
    assert proceso.returncode == 0, proceso.stderr
    corte = json.loads((tmp_path / 'corte.json').read_text())
    assert corte['cancel_durable'] is True
    recuperado = modulo.JobManager(lambda *_: None, diario=tmp_path / 'diario')
    assert recuperado.get(corte['id']).cancel.is_set()
    assert recuperado.reanudables() == []


@pytest.mark.parametrize('sucesor', [False, True])
def test_estado_terminal_no_retrocede_por_una_anotacion_previa(tmp_path, monkeypatch, sucesor):
    """096:RF-6 — un recibo terminal no vuelve a running por publicarse después un avance anterior."""
    from convertersmartgrid import util
    diario = modulo.DiarioTrabajos(tmp_path / 'diario')
    job = modulo.Job('k', 't', 'W', 'engine', lambda _: None,
        status=modulo.RUNNING, relanzado_de='ancestro' if sucesor else None)
    real = util.write_json_atomic
    pendiente, continuar, finalizado = threading.Event(), threading.Event(), threading.Event()
    def escribir(path, payload, **kw):
        if payload.get('status') == modulo.RUNNING:
            pendiente.set()
            assert continuar.wait(5)
        real(path, payload, **kw)
    monkeypatch.setattr(util, 'write_json_atomic', escribir)
    anterior = threading.Thread(target=lambda: diario.anotar(job))
    anterior.start()
    assert pendiente.wait(5)
    job.status, job.result = modulo.DONE, {'ok': True}
    def terminar():
        diario.terminar(job)
        finalizado.set()
    ultimo = threading.Thread(target=terminar)
    ultimo.start()
    finalizado.wait(.3)
    continuar.set()
    anterior.join(5); ultimo.join(5)
    assert not anterior.is_alive() and not ultimo.is_alive()
    ruta = diario.carpeta / f'{job.id}.json'
    if sucesor:
        dato = json.loads(ruta.read_text())
        assert dato['status'] == modulo.DONE and dato['result'] == {'ok': True}
    else:
        assert not ruta.exists(), 'un avance viejo resucitó el diario que acababa de retirarse'


def _recibo(diario, identidad, *, fecha, espacio='W', proceso=None, padre=None,
             estado=modulo.INTERRUMPIDO):
    job = modulo.Job('recalibrar', 'Recibo controlado', espacio, 'asistente', lambda _: None,
        id=identidad, status=estado, created_at=fecha, proceso=proceso, relanzado_de=padre,
        reanudar={'tipo': 'recalibrar', 'datos': {}})
    assert diario.anotar(job)
    diario.linea(identidad, 'evidencia que no debe perderse si el trabajo está protegido')
    return job


@pytest.mark.parametrize('identidad', ['viva', 'ambigua'])
def test_retencion_no_olvida_identidad_protegida_antes_de_calcular_reanudables(tmp_path, identidad):
    """096:RF-6, 086:RF-9 — con el límite real, una identidad viva/incierta preserva recibo, log y bloqueo."""
    import psutil
    hijo = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)']) if identidad == 'viva' else None
    try:
        proceso = {'pid': hijo.pid, 'inicio': psutil.Process(hijo.pid).create_time()} if hijo else {'estado': 'lanzando'}
        diario = modulo.DiarioTrabajos(tmp_path / 'diario')
        _recibo(diario, 'viejo_protegido', fecha=1., proceso=proceso)
        for i in range(modulo.MAX_INTERRUMPIDOS - 1):
            _recibo(diario, f'otro{i}', fecha=float(i + 2), espacio=f'otro{i}')
        _recibo(diario, 'nuevo_del_mismo_espacio', fecha=1000.)
        jobs = modulo.JobManager(lambda *_: None, diario=diario.carpeta)
        assert jobs.get('viejo_protegido') is not None
        assert (diario.carpeta / 'viejo_protegido.json').exists()
        assert (diario.carpeta / 'viejo_protegido.log').exists()
        assert not [j for j in jobs.reanudables() if j.workspace_id == 'W']
        diario._cerrar_registro('viejo_protegido')
        for i in range(modulo.MAX_INTERRUMPIDOS - 1):
            diario._cerrar_registro(f'otro{i}')
        diario._cerrar_registro('nuevo_del_mismo_espacio')
    finally:
        if hijo is not None:
            hijo.terminate()
            hijo.wait(10)


def test_retencion_conserva_cadena_aunque_el_reloj_del_sucesor_retroceda(tmp_path):
    """096:RF-5, 096:RF-6 — fecha de pared antigua no permite perder el sucesor que excluye al ancestro."""
    diario = modulo.DiarioTrabajos(tmp_path / 'diario')
    _recibo(diario, 'ancestro', fecha=1000.)
    _recibo(diario, 'sucesor', fecha=.5, padre='ancestro', estado=modulo.DONE)
    _recibo(diario, 'nieto', fecha=.1, padre='sucesor', estado=modulo.FAILED)
    for i in range(modulo.MAX_INTERRUMPIDOS - 1):
        _recibo(diario, f'otro{i}', fecha=float(i + 2), espacio=f'otro{i}')
    jobs = modulo.JobManager(lambda *_: None, diario=diario.carpeta)
    assert jobs.get('ancestro') and jobs.get('sucesor') and jobs.get('nieto')
    assert not [j for j in jobs.reanudables() if j.workspace_id == 'W']
    for job in [*jobs.list()]:
        diario._cerrar_registro(job.id)


def test_sucesor_de_servidor_vivo_excluye_ancestro_sin_adjudicarse_su_trabajo(tmp_path):
    """096:RF-6 — omitir el trabajo del servidor vivo no permite repetir su ancestro ya enlazado."""
    diario = modulo.DiarioTrabajos(tmp_path / 'diario')
    _recibo(diario, 'ancestro', fecha=1.)
    _recibo(diario, 'sucesor', fecha=2., padre='ancestro', estado=modulo.RUNNING)
    for identidad in ('ancestro', 'sucesor'):
        diario._cerrar_registro(identidad)
    antes = {p.name: p.read_bytes() for p in diario.carpeta.iterdir()}
    jobs = modulo.JobManager(lambda *_: None, diario=diario.carpeta)
    assert jobs.get('sucesor') is None, 'no adjudicarse un trabajo cuyo servidor sigue vivo'
    assert jobs.reanudables() == []
    assert {p.name: p.read_bytes() for p in diario.carpeta.iterdir()} == antes


def test_shutdown_espera_admision_anterior_y_no_deja_jobs_detras_del_sentinel(tmp_path, monkeypatch):
    """096:RF-6 — una admisión en vuelo se completa antes del cierre o se rechaza; nunca queda sin worker."""
    original = modulo.Job
    pendiente, continuar, cerrado = threading.Event(), threading.Event(), threading.Event()
    resultado, errores = [], []
    def construir(*a, **kw):
        pendiente.set()
        assert continuar.wait(5)
        return original(*a, **kw)
    monkeypatch.setattr(modulo, 'Job', construir)
    jobs = modulo.JobManager(lambda *_: None, diario=tmp_path / 'diario')
    def admitir():
        try:
            resultado.append(jobs.submit('W', 'k', 'CPU', lambda ctx: ctx.check_cancel()))
        except RuntimeError as exc:
            errores.append(str(exc))
    entrada = threading.Thread(target=admitir)
    entrada.start(); assert pendiente.wait(5)
    def cerrar():
        jobs.shutdown(timeout_s=2)
        cerrado.set()
    salida = threading.Thread(target=cerrar)
    salida.start()
    cerrado.wait(.3)
    continuar.set(); entrada.join(5); salida.join(5)
    assert not entrada.is_alive() and not salida.is_alive()
    assert cerrado.is_set()
    assert errores or resultado[0].status in modulo.FINISHED
    assert not any(h.is_alive() for h in jobs._threads.values())


def test_fallo_del_recibo_no_anuncia_relanzamiento_durable(tmp_path, monkeypatch):
    """096:RF-5, 096:RF-6 — un fallo de escritura no sella en memoria una recuperación no persistida."""
    from convertersmartgrid import util
    diario = modulo.DiarioTrabajos(tmp_path / 'diario')
    job = _recibo(diario, 'ancestro', fecha=1.)
    diario._cerrar_registro(job.id)
    jobs = modulo.JobManager(lambda *_: None, diario=diario.carpeta)
    recuperado = jobs.get(job.id)
    def sin_disco(*a, **kw):
        raise OSError('disco de contrato sin espacio')
    monkeypatch.setattr(util, 'write_json_atomic', sin_disco)
    with pytest.raises(OSError, match='relanzado|durable'):
        jobs.marcar_relanzado(recuperado)
    assert recuperado.relanzado is False
    assert json.loads((diario.carpeta / 'ancestro.json').read_text())['relanzado'] is False


def test_no_admitir_sucesor_sin_su_recibo_durable(tmp_path, monkeypatch):
    """096:RF-5, 096:RF-6 — un sucesor sin persistir no se acepta ni ejecuta efectos directos sin spawn."""
    from convertersmartgrid import util
    jobs = modulo.JobManager(lambda *_: None, diario=tmp_path / 'diario')
    efectos = []
    def sin_disco(*a, **kw):
        raise OSError('disco de contrato sin espacio')
    monkeypatch.setattr(util, 'write_json_atomic', sin_disco)
    try:
        with pytest.raises(OSError, match='sucesor|durable'):
            jobs.submit('W', 'k', 'sucesor', lambda ctx: efectos.append('no ejecutar'),
                relanzado_de='ancestro')
        assert efectos == [] and jobs.list() == []
    finally:
        jobs.shutdown(timeout_s=2)


def test_cancelacion_avisa_si_no_puede_persistirse(tmp_path, monkeypatch):
    """096:RF-4, 086:RF-9 — la cancelación cooperativa sigue pedida, pero un disco fallido no se confirma."""
    from convertersmartgrid import util
    jobs = modulo.JobManager(lambda *_: None, diario=tmp_path / 'diario')
    ocupado, liberar = threading.Event(), threading.Event()
    def f(ctx):
        ocupado.set()
        liberar.wait(5)
    job = jobs.submit('W', 'k', 'CPU', f)
    assert ocupado.wait(5)
    real = util.write_json_atomic
    def sin_disco(*a, **kw):
        raise OSError('disco de contrato sin espacio')
    monkeypatch.setattr(util, 'write_json_atomic', sin_disco)
    try:
        with pytest.raises(OSError, match='cancelación.*durable'):
            jobs.cancel(job.id)
        assert job.cancel.is_set()
        assert json.loads((tmp_path / 'diario' / f'{job.id}.json').read_text())['cancel_requested'] is False
    finally:
        monkeypatch.setattr(util, 'write_json_atomic', real)
        liberar.set()
        jobs.shutdown(timeout_s=2)


def test_shutdown_cierra_workers_aunque_falle_emitir_cancelacion(tmp_path):
    """096:RF-4/6 — notificación fallida no evita centinelas/joins; el cierre comunica el fallo después."""
    ocupado, liberar = threading.Event(), threading.Event()
    def emitir(_w, _k, dato):
        if dato.get('status') == modulo.RUNNING and dato.get('cancel_requested'):
            liberar.set()
            raise OSError('notificación de contrato fallida')
    jobs = modulo.JobManager(emitir, diario=tmp_path / 'diario')
    def f(ctx):
        ocupado.set()
        assert ctx.cancel.wait(5)
        assert liberar.wait(5)
    jobs.submit('W', 'k', 'CPU', f)
    assert ocupado.wait(5)
    try:
        with pytest.raises(OSError, match='notificación|cierre'):
            jobs.shutdown(timeout_s=2)
        assert not any(h.is_alive() for h in jobs._threads.values())
    finally:
        jobs.shutdown(timeout_s=2)


def test_shutdown_no_espera_workers_bajo_el_turno_de_admision(tmp_path):
    """096:RF-6 — un worker puede comprobar rechazo de un paso nuevo antes de que su join termine."""
    ocupado, rechazo = threading.Event(), threading.Event()
    jobs = modulo.JobManager(lambda *_: None, diario=tmp_path / 'diario')
    def f(ctx):
        ocupado.set()
        assert ctx.cancel.wait(5)
        with pytest.raises(RuntimeError, match='cerrando'):
            jobs.submit('W', 'k', 'paso posterior', lambda _: None)
        rechazo.set()
    jobs.submit('W', 'k', 'CPU', f)
    assert ocupado.wait(5)
    jobs.shutdown(timeout_s=2)
    assert rechazo.is_set()
    assert not any(h.is_alive() for h in jobs._threads.values())


def test_recibo_grande_conserva_resultado_origen_y_exclusion_del_ancestro(tmp_path):
    """096:RF-6 — ocho MiB no truncan el recibo ni convierten su ancestro en reanudable."""
    diario = modulo.DiarioTrabajos(tmp_path / 'diario')
    _recibo(diario, 'ancestro', fecha=1.)
    diario._cerrar_registro('ancestro')
    sucesor = modulo.Job('k', 't', 'W', 'engine', lambda _: None, id='sucesor',
        status=modulo.DONE, created_at=2., relanzado_de='ancestro', result={'dato': 'x' * (8 * 2**20)})
    diario.terminar(sucesor)
    eventos = []
    jobs = modulo.JobManager(lambda *e: eventos.append(e), diario=diario.carpeta)
    assert jobs.get('sucesor').result == sucesor.result
    assert jobs.get('sucesor').relanzado_de == 'ancestro'
    assert jobs.reanudables() == []
    assert not [e for e in eventos if e[2]['status'] in (modulo.DONE, modulo.FAILED)]
