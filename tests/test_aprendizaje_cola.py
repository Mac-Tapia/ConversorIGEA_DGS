"""050:RF-4/8/10: plan explícito y cola común; contratos CPU, sin entrenamiento."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from convertersmartgrid import aprendizaje_continuo as ac
from convertersmartgrid.web import app
from convertersmartgrid.web.jobs import JobManager


def _plan(tmp_path):
    ruta = tmp_path / 'plan.json'
    plan = {'schema': ac.ESQUEMA_PLAN, 'workspace_id': 'espacio-operador',
        'raiz': str(tmp_path / 'aprendizaje'), 'contexto': 'a' * 64,
        'fuentes': {'dataset': str(tmp_path / 'dataset')},
        'familias': ['transformer'], 'politica_hash': 'b' * 64,
        'tiempo_s': 21600, 'memoria_gib': 12, 'usa_gpu': True,
        'parametros': {'semillas': '11,23,37,53,71'}}
    ruta.write_text(json.dumps(plan), encoding='utf-8')
    return ruta


def test_plan_no_infiere_recursos_ni_acepta_comandos(tmp_path):
    """050:RF-4/8 — el plan conserva presupuesto y solo admite entradas declarativas."""
    ruta = _plan(tmp_path)
    plan = ac.cargar_plan_ciclo(ruta)
    assert plan['memoria_gib'] == 12 and plan['tiempo_s'] == 21600
    original = json.loads(ruta.read_text(encoding='utf-8'))
    ruta.write_text(json.dumps({**original, 'comando': 'entrenar_suelto.py'}), encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado, match='campos'):
        ac.cargar_plan_ciclo(ruta)
    ruta.write_text(json.dumps({k: v for k, v in original.items() if k != 'memoria_gib'}), encoding='utf-8')
    with pytest.raises(ac.CicloBloqueado, match='campos'):
        ac.cargar_plan_ciclo(ruta)


def test_vigilancia_comun_activa_por_defecto_y_sin_plan_bloquea(tmp_path, monkeypatch):
    """050:RF-4/8, 071:RF-6 — sin ninguna variable la vigilancia ve los datos nuevos y pide el ciclo (usuario,
    2026-11-13: el reentreno automático va siempre). Sin plan del ciclo en el equipo, el bloqueo queda a la vista
    y no se encola nada: faltar el plan es un dato que falta (RF-8), no un permiso."""
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.asistente.vigilancia import Vigilante
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.delenv('CSG_AUTOENTRENAMIENTO', raising=False)
    monkeypatch.delenv('CSG_APRENDIZAJE_PLAN', raising=False)
    monkeypatch.setattr(Vigilante, 'arrancar', lambda _v: None)
    monkeypatch.setattr(app.services, 'asistente_nuevos', lambda: (30, 40))
    jobs = JobManager(lambda *_args: None)
    try:
        vigilante = app.arrancar_vigilancia(jobs)
        assert vigilante.ciclo is not None
        assert vigilante.contar_nuevos() == (30, 40)
        assert vigilante.ciclo(['datos nuevos']) is False
        assert jobs.list() == []
        bloqueos = ac.estado_aprendizaje(almacen.raiz() / 'aprendizaje')['bloqueos']
        assert 'plan' in bloqueos[-1]['motivos'][0].casefold()
    finally:
        jobs.shutdown(timeout_s=1)


def _con_carril_ocupado(jobs):
    """Otro ciclo en marcha: el nuevo queda en cola y no ejecuta nada en la prueba."""
    ocupado, liberar = threading.Event(), threading.Event()

    def mantener(_ctx):
        ocupado.set()
        assert liberar.wait(5)

    jobs.submit('operador', 'aprendizaje:otra_solicitud', 'otro ciclo en engine', mantener)
    assert ocupado.wait(2)
    return liberar


def test_sin_ninguna_variable_el_ciclo_arranca_con_el_plan_del_equipo(tmp_path, monkeypatch):
    """050:RF-4; 071:RF-6 — ni CSG_AUTOENTRENAMIENTO ni CSG_APRENDIZAJE_PLAN: con el plan guardado en los datos del
    asistente, el ciclo se encola en el carril de fondo. Antes devolvía None sin la variable a «1»."""
    from convertersmartgrid.asistente import almacen
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.delenv('CSG_AUTOENTRENAMIENTO', raising=False)
    monkeypatch.delenv('CSG_APRENDIZAJE_PLAN', raising=False)
    destino = almacen.raiz() / 'aprendizaje' / 'plan.json'
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(_plan(tmp_path).read_text(encoding='utf-8'), encoding='utf-8')
    jobs = JobManager(lambda *_args: None)
    liberar = _con_carril_ocupado(jobs)
    try:
        trabajo = app.encolar_ciclo_aprendizaje(jobs, ['episodios nuevos'])
        assert trabajo not in (None, False) and trabajo.kind.startswith('aprendizaje:') and trabajo.lane == 'engine'
        jobs.cancel(trabajo.id)
    finally:
        liberar.set()
        jobs.shutdown(timeout_s=2)


def test_con_la_orden_de_parar_no_arranca(tmp_path, monkeypatch):
    """050:RF-4; 071:RF-6 — el operador lo para con una orden explícita, ``CSG_AUTOENTRENAMIENTO=0``, como la captura
    del gemelo con ``CSG_TWIN_CAPTURA=0``: ni se encola ni la vigilancia cuenta datos nuevos."""
    from convertersmartgrid.asistente.vigilancia import Vigilante
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_AUTOENTRENAMIENTO', '0')
    monkeypatch.setenv('CSG_APRENDIZAJE_PLAN', str(_plan(tmp_path)))
    monkeypatch.setattr(Vigilante, 'arrancar', lambda _v: None)
    monkeypatch.setattr(app.services, 'asistente_nuevos', lambda: (30, 40))
    jobs = JobManager(lambda *_args: None)
    try:
        assert app.encolar_ciclo_aprendizaje(jobs, ['datos nuevos']) is None
        assert app.arrancar_vigilancia(jobs).contar_nuevos() == (0, 0)
        assert jobs.list() == []
    finally:
        jobs.shutdown(timeout_s=1)


def test_cola_deduplica_plan_vivo_y_admite_cancelacion_publica(tmp_path, monkeypatch):
    """050:RF-4 — dos disparos usan un trabajo real de engine y se cancelan por JobManager."""
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_AUTOENTRENAMIENTO', '1')
    ruta = _plan(tmp_path)
    monkeypatch.setenv('CSG_APRENDIZAJE_PLAN', str(ruta))
    jobs = JobManager(lambda *_args: None)
    ocupado, liberar = threading.Event(), threading.Event()
    def mantener(_ctx):
        ocupado.set()
        assert liberar.wait(5)
    primero = jobs.submit('operador', 'aprendizaje:otra_solicitud', 'otro ciclo en engine', mantener)
    assert ocupado.wait(2)
    try:
        uno = app.encolar_ciclo_aprendizaje(jobs, ['episodios nuevos'])
        dos = app.encolar_ciclo_aprendizaje(jobs, ['órdenes nuevas'])
        assert uno.id == dos.id and uno.id != primero.id
        assert uno.lane == 'engine' and uno.workspace_id == 'espacio-operador'
        assert len(jobs.list()) == 2
        cancelado = jobs.cancel(uno.id)
        assert cancelado.cancel.is_set()
    finally:
        liberar.set()
        jobs.shutdown(timeout_s=2)


def test_cancelacion_de_cola_impide_primera_etapa(tmp_path):
    """050:RF-4 — cancelar antes de comenzar conserva diario y nunca ejecuta una etapa."""
    from test_aprendizaje_continuo import _instantanea, CTX
    from convertersmartgrid.model_registry import RegistroModelo
    from convertersmartgrid.training_coordinator import TrainingStage
    inst = _instantanea(tmp_path)
    llamadas = []
    resultado = ac.ejecutar_ciclo(tmp_path / 'ap', inst,
        [TrainingStage('evolutivos', lambda: llamadas.append(1), uses_gpu=False)],
        politica_hash=CTX, presupuesto=ac.Presupuesto(5, 1, False),
        registro=RegistroModelo(tmp_path / 'registro'), cancelado=lambda: True)
    assert resultado['estado'] == 'cancelado' and llamadas == []
    assert ac.estado_aprendizaje(tmp_path / 'ap')['ultimo_ciclo']['estado'] == 'cancelado'


def test_vigilancia_no_anuncia_entrenamiento_y_reintenta_solicitud_no_admitida(tmp_path, monkeypatch):
    """050:RF-4/8/10 — faltar un plan no sella como entrenados ni atendidos los datos nuevos."""
    from datetime import datetime
    from convertersmartgrid.asistente.vigilancia import Vigilante, revisar_modelos
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path))
    avisos = revisar_modelos(episodios_nuevos=20, ordenes_nuevas=30)
    assert all('se reentrena' not in aviso.texto for aviso in avisos)
    solicitudes = []
    def rechazar(motivos):
        solicitudes.append(motivos)
        return False
    v = Vigilante(listar_trabajos=lambda: [], reintentar=lambda _i: None,
        entrenar_gemelo=lambda: pytest.fail('entrenamiento individual'),
        entrenar_asistente=lambda: pytest.fail('entrenamiento individual'),
        contar_nuevos=lambda: (20, 30), repo=tmp_path, ciclo=rechazar)
    v.tic(fecha=datetime(2026, 11, 8, 9))
    v.tic(fecha=datetime(2026, 11, 8, 9))
    assert len(solicitudes) == 2


def test_trabajo_real_mantiene_bloqueo_de_fuentes_sin_lanzar_modelos(tmp_path, monkeypatch):
    """050:RF-4/8/10 — cola y proceso CLI reales conservan un bloqueo anterior a entrenamiento."""
    import time
    from convertersmartgrid.web.jobs import FINISHED
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setenv('CSG_AUTOENTRENAMIENTO', '1')
    monkeypatch.setenv('CSG_APRENDIZAJE_PLAN', str(_plan(tmp_path)))
    jobs = JobManager(lambda *_args: None)
    try:
        job = app.encolar_ciclo_aprendizaje(jobs, ['fuentes nuevas'])
        limite = time.monotonic() + 10
        while job.status not in FINISHED and time.monotonic() < limite:
            job.cancel.wait(.05)
        assert job.status == 'failed' and 'bloqueado' in job.error
        estado = ac.estado_aprendizaje(tmp_path / 'aprendizaje')
        assert estado['ultimo_ciclo'] is None and estado['conjunto_activo'] is None
        assert any('dataset' in m for b in estado['bloqueos'] for m in b['motivos'])
    finally:
        jobs.shutdown(timeout_s=2)


def test_operador_en_otro_carril_pospone_admision_de_aprendizaje(tmp_path, monkeypatch):
    """050:RF-4 — PowerFactory del operador tiene prioridad antes de admitir el ciclo CPU/GPU."""
    monkeypatch.setenv('CSG_AUTOENTRENAMIENTO', '1')
    monkeypatch.setenv('CSG_APRENDIZAJE_PLAN', str(_plan(tmp_path)))
    ocupado, liberar = threading.Event(), threading.Event()
    jobs = JobManager(lambda *_args: None)
    def mantener(_ctx):
        ocupado.set()
        assert liberar.wait(5)
    jobs.submit('operador', 'pf_projects', 'trabajo de contrato sin motor', mantener, lane='powerfactory')
    assert ocupado.wait(2)
    try:
        assert app.encolar_ciclo_aprendizaje(jobs, ['datos nuevos']) is False
        assert len(jobs.list()) == 1
    finally:
        liberar.set()
        jobs.shutdown(timeout_s=2)
