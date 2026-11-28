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


# --- 050:RF-47 a RF-50: el ciclo no ocupa el carril de otro (2026-11-28) ---------------------------------------------
# 28-11, 11:31: al reiniciar la web, el ciclo se encoló con la GPU en manos de la suite, quedó «bloqueado: GPU ocupada»
# y siguió con el carril; la aceptación de la 100 esperó detrás («su carril lo tiene «Ciclo conjunto de aprendizaje»»)
# hasta que se canceló a mano. Además eligió como espacio uno de la aceptación, el del último trabajo de la web.

def _con_parametro(nombre):
    import inspect

    assert nombre in inspect.signature(app.encolar_ciclo_aprendizaje).parameters, \
        f'encolar_ciclo_aprendizaje no admite {nombre} (050 T10)'


def test_050_rf47_con_la_gpu_de_otro_el_ciclo_no_se_encola_y_se_anota_una_vez(tmp_path, monkeypatch):
    """050:RF-47 — con la GPU en manos de otro proceso vivo, la vigilancia no encola el ciclo (devuelve False, para
    pedirlo otra vez), anota quién la tiene una sola vez y lo encola en cuanto la GPU queda libre."""
    _con_parametro('gpu_de_otro')
    _web_, almacen = _web(tmp_path, monkeypatch)
    ocupada = lambda: 'PID 4242 (suite, desde 2041-01-01T11:31:00)'               # noqa: E731
    for _ in range(3):
        trabajos = _Trabajos()
        assert app.encolar_ciclo_aprendizaje(trabajos, ['45 órdenes nuevas'], gpu_de_otro=ocupada) is False
        assert trabajos.encolados == []
    filas = [json.loads(x) for x in (almacen / 'aprendizaje' / 'bloqueos.jsonl').read_text(encoding='utf-8')
             .splitlines()]
    assert [f['etapa'] for f in filas] == ['gpu'] and 'PID 4242' in filas[0]['motivos'][0]
    trabajos = _Trabajos()
    trabajo = app.encolar_ciclo_aprendizaje(trabajos, ['45 órdenes nuevas'], gpu_de_otro=lambda: None)
    assert trabajo not in (None, False) and trabajos.encolados == [trabajo]


def test_050_rf47_la_gpu_es_de_otro_solo_si_la_tiene_un_proceso_ajeno_vivo(tmp_path):
    """050:RF-47 — la guardia de la GPU es de otro si la tiene un proceso vivo que no es este, ni un antecesor ni un
    descendiente suyo (el entrenamiento que lanzó el propio ciclo); muerta o sin dueño válido, no."""
    import psutil

    from convertersmartgrid.aplicacion import trabajadores_ml as tm

    assert hasattr(tm, 'gpu_de_otro'), 'falta la consulta de la GPU sin tomarla (050 T10)'
    ruta = tmp_path / 'gpu.lock'
    assert tm.gpu_de_otro(ruta) is None                                         # sin guardia
    yo = psutil.Process()
    familia = {yo.pid, *(p.pid for p in yo.parents()), *(p.pid for p in yo.children(recursive=True))}
    ajeno = next(p for p in psutil.process_iter(['pid', 'create_time'])
                 if p.pid not in familia and p.pid > 4 and p.info['create_time'])

    def guardia(pid, creado):
        ruta.write_text(json.dumps({'pid': pid, 'creado': creado, 'model': 'suite', 'token': 't',
                                    'started_at': '2041-01-01T11:31:00'}), encoding='utf-8')
    guardia(ajeno.pid, ajeno.info['create_time'])
    assert f'PID {ajeno.pid}' in (tm.gpu_de_otro(ruta) or '')
    guardia(yo.pid, yo.create_time())
    assert tm.gpu_de_otro(ruta) is None                                         # la de este proceso
    padre = yo.parent()
    guardia(padre.pid, padre.create_time())
    assert tm.gpu_de_otro(ruta) is None                                         # la del que lo lanzó
    guardia(ajeno.pid, ajeno.info['create_time'] + 1000)                        # PID reutilizado: ya no vive
    assert tm.gpu_de_otro(ruta) is None


def test_050_rf48_rf50_el_ciclo_cede_el_carril_a_otro_trabajo_sin_gastar_sus_datos(tmp_path, monkeypatch):
    """050:RF-48, 050:RF-50 — si al empezar, o entre la preparación y el entrenamiento, hay otro trabajo de la web sin
    terminar (aquí, el de la aceptación), el ciclo no lanza nada: suelta el carril sin darse por fallido, lo dice en el
    Registro, avisa a la vigilancia para que lo pida otra vez y no da por usados los datos que lo dispararon."""
    from convertersmartgrid.aplicacion.asistente import almacen as alm
    _con_parametro('al_ceder')
    _web(tmp_path, monkeypatch)
    avisos = []
    trabajo = app.encolar_ciclo_aprendizaje(_Trabajos(), ['45 órdenes nuevas'], gpu_de_otro=lambda: None,
                                            al_ceder=lambda: avisos.append('pedir de nuevo'))
    assert trabajo not in (None, False)
    aceptacion = SimpleNamespace(kind='sistema_web', title='Calibrar el sistema', status='queued')
    ordenes, registro = [], []
    ctx = _ctx(ordenes)
    ctx.pendientes = lambda: [aceptacion]
    ctx.log = registro.append
    salida = trabajo.fn(ctx)
    assert salida['estado'] == 'cedido' and 'Calibrar el sistema' in salida['motivo']
    assert ordenes == [], 'con otro trabajo en cola el ciclo no debe lanzar nada'
    assert any('cede el carril' in r for r in registro) and avisos == ['pedir de nuevo']
    assert not (alm.leer_json('vigilancia') or {}).get('ordenes'), 'los datos no se dan por usados'


def test_050_rf48_si_otro_llega_mientras_entrena_el_ciclo_suelta_el_carril(tmp_path, monkeypatch):
    """050:RF-48 — el entrenamiento ya lanzado se para cuando llega otro trabajo: ``run_process`` recibe con qué
    consultarlo, y su código de cesión termina el ciclo como cedido, no como fallido."""
    from convertersmartgrid.presentacion.web import jobs as jb
    _con_parametro('al_ceder')
    _web(tmp_path, monkeypatch)
    trabajo = app.encolar_ciclo_aprendizaje(_Trabajos(), ['45 órdenes nuevas'], gpu_de_otro=lambda: None)
    pendientes, consultas, ordenes = [], [], []
    base = _ctx(ordenes)

    def run_process(cmd, **k):
        if 'preparar_ciclo_aprendizaje.py' in str(cmd[1]):
            return base.run_process(cmd, **k)
        ordenes.append([str(c) for c in cmd])
        assert callable(k.get('ceder')), 'el entrenamiento se lanza sin poder ceder el carril'
        consultas.append(k['ceder']())                     # libre: sigue
        pendientes.append(SimpleNamespace(kind='convertir', title='Convertir', status='queued'))
        consultas.append(k['ceder']())                     # llegó el operador: cede
        return jb.CEDIDO
    ctx = SimpleNamespace(**{**vars(base), 'run_process': run_process, 'pendientes': lambda: list(pendientes)})
    salida = trabajo.fn(ctx)
    assert consultas[0] is None and 'Convertir' in consultas[1]
    assert salida['estado'] == 'cedido' and sum(o[1].endswith('aprendizaje_continuo.py') for o in ordenes) == 1


def test_050_rf48_run_process_para_el_guion_al_ceder(tmp_path):
    """050:RF-48 — con ``ceder``, ``run_process`` pide parar al guion por su fichero de cancelación y lo termina si no
    sale en la gracia; sin fichero, lo termina en seguida; en los dos casos devuelve el código de cesión."""
    import time

    from convertersmartgrid.presentacion.web import jobs as jb

    assert hasattr(jb, 'CEDIDO'), 'run_process no sabe ceder el carril (050 T10)'
    job = jb.Job(kind='aprendizaje:automatico', title='Ciclo', workspace_id='w', lane='engine', fn=lambda c: None)
    ctx = jb.JobContext(job, lambda *_a: None)
    cancelar = tmp_path / 'cancelar'
    obediente = ('import pathlib, sys, time\nprint("empieza", flush=True)\n'
                 f'while not pathlib.Path(r"{cancelar}").exists(): time.sleep(0.1)\nsys.exit(0)\n')
    inicio = time.monotonic()
    rc = ctx.run_process([sys.executable, '-c', obediente], cancel_file=cancelar, ceder=lambda: 'llegó otro')
    assert rc == jb.CEDIDO and cancelar.read_text(encoding='utf-8') == 'ceder\n'
    sordo = 'import time\nprint("empieza", flush=True)\ntime.sleep(120)\n'
    rc = ctx.run_process([sys.executable, '-c', sordo], cancel_file=tmp_path / 'otro', ceder=lambda: 'llegó otro',
                         gracia_ceder_s=1.0)
    assert rc == jb.CEDIDO
    rc = ctx.run_process([sys.executable, '-c', sordo], ceder=lambda: 'llegó otro')
    assert rc == jb.CEDIDO and time.monotonic() - inicio < 60
    assert ctx.run_process([sys.executable, '-c', 'print(1)'], ceder=lambda: None) == 0


def test_050_rf49_el_ciclo_no_elige_un_espacio_de_la_aceptacion(tmp_path, monkeypatch):
    """050:RF-49 — los espacios que anotó la aceptación (100:RF-24) no son del operador: el ciclo toma el último
    trabajo de otro espacio y, sin trabajos, el guardado más recientemente que no sea de la aceptación."""
    _web_, _almacen = _web(tmp_path, monkeypatch)
    sellos = tmp_path / 'aceptacion'
    sellos.mkdir()
    (sellos / 'espacios.json').write_text(json.dumps({'espacios': ['espacionuevo']}), encoding='utf-8')
    monkeypatch.setenv('CSG_ACEPTACION_DATA', str(sellos))
    previos = [SimpleNamespace(workspace_id='espacioviejo', kind='convertir', status='done', title='Convertir'),
               SimpleNamespace(workspace_id='espacionuevo', kind='sistema_web', status='done', title='Calibrar')]
    trabajo = app.encolar_ciclo_aprendizaje(_Trabajos(previos), ['45 órdenes nuevas'], **(
        {'gpu_de_otro': lambda: None} if _admite('gpu_de_otro') else {}))
    assert trabajo not in (None, False) and trabajo.workspace_id == 'espacioviejo', \
        'el ciclo eligió un espacio de la aceptación por el del operador'
    assert ac.espacio_mas_reciente(_web_) == 'espacionuevo'
    trabajo = app.encolar_ciclo_aprendizaje(_Trabajos(), ['46 órdenes nuevas'], **(
        {'gpu_de_otro': lambda: None} if _admite('gpu_de_otro') else {}))
    assert trabajo.workspace_id == 'espacioviejo', 'sin trabajos, eligió el espacio de la aceptación más reciente'


def _admite(nombre):
    import inspect

    return nombre in inspect.signature(app.encolar_ciclo_aprendizaje).parameters
