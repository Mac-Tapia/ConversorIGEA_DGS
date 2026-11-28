"""050:RF-36 a RF-46: la vigilancia prepara sola el plan del ciclo cuando falta, omite las familias sin datos con su
motivo y anota cada bloqueo una sola vez.

El 27-11 la web veía «45 órdenes nuevas…» y cada minuto anotaba «Falta el plan del ciclo de aprendizaje»: 2,6 MB de
líneas iguales en ``bloqueos.jsonl`` y ningún entrenamiento. Las pruebas usan almacenes sintéticos en ``tmp_path`` y
nunca entrenan: la orden del ciclo se registra sin ejecutarla.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from apoyo import cargar_herramienta
from convertersmartgrid.aplicacion import aprendizaje_continuo as ac
from convertersmartgrid.dominio.contratos_aprendizaje import puertas_de_familia
from convertersmartgrid.presentacion.web import app

from test_preparar_ciclo_aprendizaje import FECHA, _observaciones, pc

SIETE = ('transformer', 'clasificador', 'gru', 'pinn', 'evolutivos', 'embeddings', 'qlora')


def _foto(carpeta: Path) -> dict[str, bytes]:
    return {p.relative_to(carpeta).as_posix(): p.read_bytes() for p in sorted(carpeta.rglob('*')) if p.is_file()}


def _web(tmp_path, monkeypatch, *, v1=True):
    """Una web sintética: almacén con órdenes confirmadas, un dataset v1 viejo y dos espacios guardados."""
    web = tmp_path / 'web'
    almacen = web / '_asistente'
    almacen.mkdir(parents=True)
    _observaciones(almacen, *[(f'convierte la red {i}', FECHA) for i in range(6)])
    if v1:
        (almacen / 'dataset').mkdir()
        (almacen / 'dataset' / 'manifest.json').write_text(
            json.dumps({'schema': 'convertersmartgrid-training-dataset-v1'}), encoding='utf-8')
    for nombre, instante in (('espacioviejo', 1_700_000_000), ('espacionuevo', 1_800_000_000)):
        (web / nombre).mkdir()
        ws = web / nombre / 'workspace.json'
        ws.write_text(json.dumps({'id': nombre}), encoding='utf-8')
        os.utime(ws, (instante, instante))
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(almacen))
    monkeypatch.setenv('CSG_TWIN_DATA', str(web / '_digital_twin'))
    monkeypatch.delenv('CSG_AUTOENTRENAMIENTO', raising=False)
    monkeypatch.delenv('CSG_APRENDIZAJE_PLAN', raising=False)
    return web, almacen


def _automatico(tmp_path, almacen, *extra):
    salida = tmp_path / 'preparacion'
    argv = ['--automatico', '--almacen', str(almacen), '--salida', str(salida),
            '--plan-salida', str(tmp_path / 'plan' / 'plan.json'), '--informe', str(tmp_path / 'informe.json'), *extra]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            rc = pc.main(argv)
        except SystemExit as exc:
            rc = exc.code
    informe = tmp_path / 'informe.json'
    return rc, (json.loads(informe.read_text(encoding='utf-8')) if informe.is_file() else None)


class _Trabajos:
    """Lo justo de JobManager: lo encolado se guarda y se ejecuta a mano."""

    def __init__(self, previos=()):
        self.previos = list(previos)
        self.encolados = []

    def list(self):
        return self.previos + self.encolados

    def submit(self, espacio, tipo, titulo, funcion, lane):
        trabajo = SimpleNamespace(workspace_id=espacio, kind=tipo, title=titulo, fn=funcion, lane=lane, status='queued')
        self.encolados.append(trabajo)
        return trabajo


def _ctx(ordenes):
    """La preparación corre de verdad, en otro proceso; la orden del ciclo solo se anota (no se entrena)."""
    def run_process(cmd, **_k):
        ordenes.append([str(c) for c in cmd])
        if 'preparar_ciclo_aprendizaje.py' in str(cmd[1]):
            return subprocess.run(cmd, env=dict(os.environ), capture_output=True, timeout=600).returncode
        return 0
    return SimpleNamespace(check_cancel=lambda: None, job=SimpleNamespace(id='j1'), log=lambda _m: None,
                           run_process=run_process)


def test_050_rf38_rf40_rf41_el_plan_automatico_reconstruye_el_dataset_y_omite_lo_que_falta(tmp_path, monkeypatch):
    """050:RF-38, 050:RF-40, 050:RF-41, 050:RF-45 — con el dataset v1 del almacén, la preparación automática
    reconstruye un v2 en una carpeta nueva, sin tocar el almacén; las familias sin fuente se omiten con lo que les
    falta y el plan sale con las demás, con el presupuesto por defecto y todas sus puertas."""
    _web_, almacen = _web(tmp_path, monkeypatch)
    antes = _foto(almacen)
    rc, informe = _automatico(tmp_path, almacen)
    assert rc == 0, informe
    assert _foto(almacen) == antes, 'el almacén solo se lee'
    plan = ac.cargar_plan_ciclo(tmp_path / 'plan' / 'plan.json')
    assert ac.validar_plan_ciclo(plan) == []
    dataset = Path(plan['fuentes']['dataset'])
    assert dataset.is_relative_to((tmp_path / 'preparacion').resolve()) and dataset != (almacen / 'dataset').resolve()
    assert json.loads((dataset / 'manifest.json').read_text(encoding='utf-8'))['schema'] == \
        'convertersmartgrid-training-dataset-v2'
    assert 'transformer' in plan['familias']
    omitidas = informe['omitidas']
    assert set(omitidas) == set(SIETE) - set(plan['familias'])
    assert {'pinn', 'gru', 'qlora', 'evolutivos'} <= set(omitidas)
    assert all(motivos for motivos in omitidas.values()), omitidas
    assert any('twin' in m for m in omitidas['pinn'])
    for familia in SIETE:
        assert plan['matriz'][familia]['en_plan'] is (familia in plan['familias'])
    assert {k: plan[k] for k in ac.PRESUPUESTO_AUTOMATICO} == ac.PRESUPUESTO_AUTOMATICO
    assert plan['puertas'] == {f: list(puertas_de_familia(f)) for f in plan['familias']}
    assert informe['espacio'] == {'id': 'espacionuevo', 'origen': 'espacio guardado más recientemente'}


def test_050_rf36_rf46_sin_plan_la_vigilancia_lo_prepara_encola_el_ciclo_y_da_por_usados_los_datos(
        tmp_path, monkeypatch):
    """050:RF-36, 050:RF-37, 050:RF-46 — sin plan, la vigilancia no anota bloqueo: encola un trabajo que prepara el
    plan en una carpeta nueva del almacén de aprendizaje, con el espacio de la última corrida por la web, lanza el
    ciclo con ese plan y, al terminar bien, da por usadas las órdenes que lo dispararon."""
    from convertersmartgrid.aplicacion.asistente import almacen as alm
    _web_, almacen = _web(tmp_path, monkeypatch)
    previo = SimpleNamespace(workspace_id='espacioviejo', kind='convertir', status='done', title='Convertir')
    trabajos = _Trabajos([previo])
    trabajo = app.encolar_ciclo_aprendizaje(trabajos, ['45 órdenes nuevas'])
    assert trabajo not in (None, False), 'sin plan la vigilancia debe prepararlo, no bloquearse'
    assert trabajo.workspace_id == 'espacioviejo' and trabajo.lane == 'engine'
    assert not (almacen / 'aprendizaje' / 'bloqueos.jsonl').exists()
    ordenes = []
    trabajo.fn(_ctx(ordenes))
    preparar = next(o for o in ordenes if 'preparar_ciclo_aprendizaje.py' in o[1])
    assert '--automatico' in preparar and preparar[preparar.index('--workspace-id') + 1] == 'espacioviejo'
    salida = Path(preparar[preparar.index('--salida') + 1])
    assert salida.parent == almacen / 'aprendizaje' / 'preparaciones'
    plan_ruta = almacen / 'aprendizaje' / 'plan.json'
    plan = ac.cargar_plan_ciclo(plan_ruta)
    assert plan['workspace_id'] == 'espacioviejo'
    ciclo = next(o for o in ordenes if o[1].endswith('aprendizaje_continuo.py'))
    assert ciclo[ciclo.index('--plan-hash') + 1] == plan['plan_hash']
    assert (alm.leer_json('vigilancia') or {}).get('ordenes') == 6


def test_050_rf43_el_mismo_bloqueo_se_anota_una_sola_vez(tmp_path, monkeypatch):
    """050:RF-43 — un plan del operador que no carga se anota la primera vez y cuando cambia su motivo, no en cada
    vuelta de la vigilancia (antes, una línea igual por minuto)."""
    _web_, almacen = _web(tmp_path, monkeypatch)
    plan = almacen / 'aprendizaje' / 'plan.json'
    plan.parent.mkdir(parents=True)
    plan.write_text('{"schema": "otro"}', encoding='utf-8')
    for _ in range(3):
        assert app.encolar_ciclo_aprendizaje(_Trabajos(), ['45 órdenes nuevas']) is False
    bloqueos = almacen / 'aprendizaje' / 'bloqueos.jsonl'
    assert len(bloqueos.read_text(encoding='utf-8').splitlines()) == 1
    plan.write_text('no es json', encoding='utf-8')
    assert app.encolar_ciclo_aprendizaje(_Trabajos(), ['46 órdenes nuevas']) is False
    assert len(bloqueos.read_text(encoding='utf-8').splitlines()) == 2


def test_050_rf44_el_plan_automatico_se_rehace_y_el_del_operador_no(tmp_path, monkeypatch):
    """050:RF-44 — con datos nuevos, un plan que preparó el sistema se prepara otra vez; el del operador se usa tal
    cual y nunca se sobrescribe."""
    _web_, almacen = _web(tmp_path, monkeypatch)
    trabajos = _Trabajos()
    ordenes = []
    trabajo = app.encolar_ciclo_aprendizaje(trabajos, ['órdenes nuevas'])
    assert trabajo not in (None, False), 'sin plan la vigilancia debe prepararlo'
    trabajo.fn(_ctx(ordenes))
    primero = ac.cargar_plan_ciclo(almacen / 'aprendizaje' / 'plan.json')['plan_hash']
    _observaciones(almacen, *[(f'convierte la red {i}', FECHA) for i in range(9)])
    ordenes.clear()
    app.encolar_ciclo_aprendizaje(_Trabajos(), ['más órdenes nuevas']).fn(_ctx(ordenes))
    assert any('preparar_ciclo_aprendizaje.py' in o[1] for o in ordenes), 'el plan automático se rehace'
    assert ac.cargar_plan_ciclo(almacen / 'aprendizaje' / 'plan.json')['plan_hash'] != primero
    # El del operador: el mismo contenido sin la marca de preparación automática.
    (almacen / 'aprendizaje' / ac.MARCA_PLAN_AUTOMATICO).unlink()
    del_operador = (almacen / 'aprendizaje' / 'plan.json').read_bytes()
    ordenes.clear()
    app.encolar_ciclo_aprendizaje(_Trabajos(), ['otras órdenes']).fn(_ctx(ordenes))
    assert not any('preparar_ciclo_aprendizaje.py' in o[1] for o in ordenes)
    assert (almacen / 'aprendizaje' / 'plan.json').read_bytes() == del_operador


def test_050_rf42_el_preflight_omite_la_familia_bloqueada_y_sigue_con_las_preparadas(tmp_path, monkeypatch):
    """050:RF-42 — si el preflight bloquea la PINN y deja preparado el Transformer, el ciclo no se bloquea entero:
    la PINN queda anotada como omitida con su motivo y el ciclo corre con el Transformer."""
    ciclo_cli = cargar_herramienta('aprendizaje_continuo.py')
    monkeypatch.setenv('CSG_ASISTENTE_DATA', str(tmp_path / 'asistente'))
    monkeypatch.setattr(ac, 'congelar_instantanea', lambda *_a, **_k: {'snapshot_id': 'c' * 64, 'ruta': str(tmp_path)})

    def preflight(_inst, familias, **_k):
        por = {f: ({'estado': 'bloqueado', 'motivos': [f'{f}: sin vista del gemelo']} if f == 'pinn'
                   else {'estado': 'preparado', 'motivos': []}) for f in familias}
        motivos = [m for r in por.values() for m in r['motivos']]
        return {'estado': 'bloqueado' if motivos else 'preparado', 'por_familia': por, 'motivos': motivos}
    monkeypatch.setattr(ac, 'preflight_ciclo', preflight)
    monkeypatch.setattr(ciclo_cli, '_etapas', lambda _i, familias, *_a: [SimpleNamespace(name=f) for f in familias])
    corridas = []
    monkeypatch.setattr(ac, 'ejecutar_ciclo', lambda _r, _i, etapas, **_k: corridas.append(
        [e.name for e in etapas]) or {'estado': 'terminado'})
    with contextlib.redirect_stdout(io.StringIO()):
        rc = ciclo_cli.main(['--raiz', str(tmp_path / 'ap'), 'ciclo', '--contexto', 'a' * 64,
                             '--familias', 'transformer,pinn', '--politica-hash', 'b' * 64,
                             '--tiempo-s', '60', '--memoria-gib', '1'])
    assert rc == 0 and corridas == [['transformer']]
    filas = [json.loads(x) for x in (tmp_path / 'ap' / 'bloqueos.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [f['etapa'] for f in filas] == ['omision'] and 'pinn' in filas[0]['motivos'][0]
