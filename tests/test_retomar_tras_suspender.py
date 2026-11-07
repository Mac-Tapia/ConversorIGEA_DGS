"""Spec 096: tras suspender el equipo, la web vuelve sola al último trabajo pendiente."""
from __future__ import annotations

import json
import time

import pytest

from convertersmartgrid.web import jobs as J
from convertersmartgrid.web import suspension


def _esperar(manager, job_id, limite=10.0):
    fin = time.time() + limite
    while time.time() < fin:
        job = manager.get(job_id)
        if job.status in J.FINISHED:
            return job
        time.sleep(0.02)
    raise AssertionError('el trabajo no terminó')


@pytest.fixture()
def reloj(monkeypatch):
    """Segundos suspendidos que da Windows; las pruebas los avanzan como una suspensión."""
    estado = {'s': 1000.0, 'pedidos': []}
    monkeypatch.setattr(suspension, 'suspendido_s', lambda: estado['s'])
    monkeypatch.setattr(suspension, '_estado', lambda banderas: estado['pedidos'].append(banderas))
    return estado


def _fallar_tras_dormir(reloj, veces, dormir_s=600.0):
    llamadas = []

    def fn(ctx):
        llamadas.append(1)
        if len(llamadas) <= veces:
            reloj['s'] += dormir_s
            raise RuntimeError('DIgSILENT: licencia de red perdida')
        return {'ok': len(llamadas)}
    return fn, llamadas


def test_tras_una_suspension_el_trabajo_que_falla_se_repite_una_vez(reloj):
    """096:RF-1 / 096:RF-2 — el trabajo pide a Windows no suspender y lo suelta; si falla tras una suspensión, se
    repite solo y lo dice con el tiempo suspendido."""
    registro = []
    m = J.JobManager(lambda w, k, d: registro.append(d.get('text')) if k == 'log' else None)
    fn, llamadas = _fallar_tras_dormir(reloj, 1)
    job = _esperar(m, m.submit('w', 'recalibrar', 'Recalibrar', fn).id)
    assert job.status == J.DONE and job.result == {'ok': 2} and len(llamadas) == 2
    assert any('suspendido 10.0 min' in (t or '') and '096:RF-2' in t for t in registro)
    con = suspension.ES_CONTINUOUS | suspension.ES_SYSTEM_REQUIRED
    assert reloj['pedidos'][:2] == [con, suspension.ES_CONTINUOUS]


def test_el_repetido_que_vuelve_a_fallar_queda_fallido(reloj):
    """096:RF-3 — una sola repetición: el segundo fallo queda con su error."""
    m = J.JobManager(lambda *a: None)
    fn, llamadas = _fallar_tras_dormir(reloj, 5)
    job = _esperar(m, m.submit('w', 'recalibrar', 'Recalibrar', fn).id)
    assert job.status == J.FAILED and len(llamadas) == 2 and 'licencia' in job.error


def test_sin_suspension_o_cancelado_no_se_repite(reloj):
    """096:RF-4 — un fallo sin suspensión, o de un trabajo cancelado, no se repite."""
    m = J.JobManager(lambda *a: None)
    fn, llamadas = _fallar_tras_dormir(reloj, 5, dormir_s=1.0)
    job = _esperar(m, m.submit('w', 'k', 'sin dormir', fn).id)
    assert job.status == J.FAILED and len(llamadas) == 1

    intentos = []

    def cancelado(ctx):
        intentos.append(1)
        ctx.job.cancel.set()
        reloj['s'] += 600.0
        raise RuntimeError('cortado')
    job = _esperar(m, m.submit('w', 'k', 'cancelado', cancelado).id)
    assert job.status == J.FAILED and len(intentos) == 1


def test_al_arrancar_se_relanza_una_vez_el_ultimo_interrumpido(tmp_path, monkeypatch):
    """096:RF-5 / 096:RF-6 / 096:RF-7 — el «Recalibrar» que quedó a medias al caer la web se relanza solo con su
    petición, dice de dónde viene y no se relanza dos veces; uno sin petición guardada no se relanza."""
    from fastapi.testclient import TestClient

    from convertersmartgrid.web import services
    from convertersmartgrid.web.app import create_app

    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    raiz = tmp_path / 'web'
    with TestClient(create_app(raiz)) as c:
        wid = c.post('/api/workspaces').json()['id']
    diario = raiz / '_trabajos'
    datos = {'project': '20261103_CSG_SISTEMA_VALLE', 'periodo': '2026', 'solo': ['VA101']}

    def interrumpido(job_id, creado, reanudar):
        (diario / f'{job_id}.json').write_text(json.dumps({
            'id': job_id, 'kind': 'recalibrar', 'title': 'Recalibrar', 'workspace_id': wid, 'lane': 'asistente',
            'status': 'running', 'created_at': creado, 'pid': 999999, 'inicio_proceso': 1.0, 'reanudar': reanudar}),
            encoding='utf-8')
    diario.mkdir(parents=True, exist_ok=True)
    interrumpido('viejo1', 1.0, None)
    interrumpido('viejo2', 2.0, {'tipo': 'recalibrar', 'datos': datos})
    pedidos = []
    monkeypatch.setattr(services, 'recalibrar_datos', lambda ws, p: {'zonal': 'Valle', 'demanda_dir': 'x',
                                                                     'del_sistema': ['VA101']})
    monkeypatch.setattr(services, 'recalibrar_sistema', lambda ws, ctx, project, periodo, **kw: (
        pedidos.append((project, periodo, kw.get('solo'), ctx.job.relanzado_de)) or {'codigo': 0}))
    with TestClient(create_app(raiz)) as c:
        lanzados = c.app.state.relanzar_interrumpidos()
        assert [j['kind'] for j in lanzados] == ['recalibrar']
        fin = time.time() + 10
        while not pedidos and time.time() < fin:
            time.sleep(0.05)
        assert pedidos == [('20261103_CSG_SISTEMA_VALLE', '2026', ['VA101'], 'viejo2')]
        textos = [e['data'].get('text') or '' for e in c.app.state.store.get(wid).events.since(0) if e['type'] == 'log']
        assert any('viejo2' in x and 'RF-7' in x for x in textos), textos
        assert c.app.state.relanzar_interrumpidos() == []
    assert json.loads((diario / 'viejo2.json').read_text(encoding='utf-8'))['relanzado'] is True
    with TestClient(create_app(raiz)) as c:
        assert c.app.state.relanzar_interrumpidos() == []
