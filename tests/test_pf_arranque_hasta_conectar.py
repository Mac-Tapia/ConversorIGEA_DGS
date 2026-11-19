"""086:RF-116 (T86): un guion de PowerFactory no puede quedarse callado más del límite de arranque hasta que conecta.

Prueba funcional del 19-11 (un alimentador de prueba): tras «Turno de DIgSILENT liberado: … ya no estaba vivo.» la importación se quedó
unos 30 min sin escribir ni gastar CPU, y la web no la cortó: esa línea de aviso desarmaba el límite de la primera
línea (005:RF-21), que se pensó para «DIgSILENT ya respondiendo». Hasta la marca «Conectado a DIgSILENT», cada línea
solo reinicia el plazo; una espera de turno con sus avisos periódicos (019:RF-2) sigue siendo válida.
"""
from __future__ import annotations

import os
import sys
import time


def _contexto_pf(monkeypatch, limite_s: float):
    import convertersmartgrid.adaptadores.powerfactory_env as pf_env
    from convertersmartgrid.presentacion.web import jobs
    from convertersmartgrid.presentacion.web.jobs import Job, JobContext

    monkeypatch.setattr(jobs, 'LIMITE_ARRANQUE_PF_S', limite_s)
    monkeypatch.setattr(pf_env, 'cerrar_guiones_pf_huerfanos', list)
    monkeypatch.setattr(pf_env, 'powerfactory_abierto', lambda lista=None: [])
    registro: list[str] = []
    job = Job(kind='pf_flujo', title='prueba', workspace_id='w', lane='powerfactory', fn=lambda _ctx: None)
    ctx = JobContext(job, lambda _w, tipo, datos: registro.append(datos.get('text', '')) if tipo == 'log' else None)
    return ctx, registro, {**os.environ, 'PF_PYTHON': 'x', 'CSG_PF_SERVIDOR': '0'}


def _corre(ctx, guion, **kw):
    """(código, excepción): la prueba asevera qué pasó en vez de esperar una excepción a ciegas."""
    try:
        return ctx.run_process(guion, **kw), None
    except Exception as exc:  # noqa: BLE001 - se asevera su tipo
        return None, exc


def _guion(*pasos: str) -> list[str]:
    return [sys.executable, '-c', 'import time\n' + '\n'.join(pasos)]


def test_aviso_de_turno_y_silencio_se_corta_antes_de_conectar(monkeypatch):
    from convertersmartgrid.presentacion.web.jobs import PowerFactorySinRespuesta

    ctx, registro, env = _contexto_pf(monkeypatch, 1)
    guion = _guion("print('Turno de DIgSILENT liberado: pf_servidor.py (proceso 1) ya no estaba vivo.', flush=True)",
                   'time.sleep(8)')
    inicio = time.monotonic()
    rc, exc = _corre(ctx, guion, env=env)
    assert isinstance(exc, PowerFactorySinRespuesta), f'no se cortó: rc={rc}, excepción={exc!r}'
    assert time.monotonic() - inicio < 7, 'el silencio tras el aviso de turno se corta al pasar el límite'
    assert any('sin haber conectado' in linea for linea in registro)
    assert any('Se reintenta una vez' in linea for linea in registro), 'sin conectar, repetirlo es seguro'


def test_espera_de_turno_con_avisos_y_despues_conecta_no_se_corta(monkeypatch):
    ctx, _registro, env = _contexto_pf(monkeypatch, 1)
    guion = _guion("for i in range(5):\n    print(f'DIgSILENT lo tiene otro proceso; espero ({i})', flush=True)\n"
                   '    time.sleep(0.5)',
                   "print('Conectado a DIgSILENT como prueba (3 s).', flush=True)")
    assert ctx.run_process(guion, env=env) == 0


def test_conectado_un_silencio_largo_no_se_corta(monkeypatch):
    ctx, _registro, env = _contexto_pf(monkeypatch, 1)
    guion = _guion("print('Conectado a DIgSILENT como prueba (1 s).', flush=True)", 'time.sleep(2.5)')
    assert ctx.run_process(guion, env=env) == 0


def test_cancelar_tras_un_aviso_sin_conectar_lo_termina(monkeypatch, tmp_path):
    """Con fichero de cancelación, un guion que avisó pero no conectó se termina al cancelar (no espera al alimentador)."""
    import threading

    from convertersmartgrid.presentacion.web.jobs import JobCancelled

    ctx, _registro, env = _contexto_pf(monkeypatch, 120)
    threading.Timer(1.0, ctx.cancel.set).start()
    guion = _guion("print('Turno de DIgSILENT liberado: x (proceso 1) ya no estaba vivo.', flush=True)", 'time.sleep(30)')
    inicio = time.monotonic()
    rc, exc = _corre(ctx, guion, env=env, cancel_file=tmp_path / 'cancelar.flag')
    assert isinstance(exc, JobCancelled), f'no se terminó al cancelar: rc={rc}, excepción={exc!r}'
    assert time.monotonic() - inicio < 15
