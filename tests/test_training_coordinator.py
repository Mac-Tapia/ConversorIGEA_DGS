"""043:RF-6 043:RF-7 — Coordinador reanudable y exclusión mutua real de GPU."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def lock_de_ensayo_aislado(tmp_path, monkeypatch):
    # Los callbacks de estas pruebas no entrenan: su exclusión OS debe poder
    # verificarse mientras otra sesión sí ocupa la GPU real.
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'ensayo-gpu.lock'))


def test_lock_rechaza_pid_vivo_y_recupera_pid_muerto(tmp_path):
    from convertersmartgrid.training_coordinator import BloqueoGPU

    ruta = tmp_path / 'gpu.lock'
    ruta.write_text(json.dumps({'pid': os.getpid(), 'model': 'otro'}), encoding='utf-8')
    with pytest.raises(RuntimeError, match='ocupada'):
        with BloqueoGPU(ruta, 'nuevo'):
            pass
    ruta.write_text(json.dumps({'pid': 99999999, 'model': 'muerto'}), encoding='utf-8')
    with BloqueoGPU(ruta, 'nuevo'):
        assert json.loads(ruta.read_text())['pid'] == os.getpid()
    assert not ruta.exists()


def test_dos_procesos_reales_no_adquieren_el_mismo_lock(tmp_path):
    from convertersmartgrid.training_coordinator import BloqueoGPU

    lock = tmp_path / 'gpu.lock'
    script = ('import sys,time; sys.path.insert(0,sys.argv[2]); '
              'from convertersmartgrid.training_coordinator import BloqueoGPU; '
              'b=BloqueoGPU(sys.argv[1],"p1"); b.__enter__(); print("LOCKED",flush=True); '
              'time.sleep(2); b.__exit__(None,None,None)')
    src = Path(__file__).resolve().parents[1] / 'src'
    proc = subprocess.Popen([sys.executable, '-c', script, str(lock), str(src)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == 'LOCKED'
        with pytest.raises(RuntimeError, match='ocupada'):
            with BloqueoGPU(lock, 'p2'):
                pass
    finally:
        proc.wait(timeout=5)
    assert proc.returncode == 0 and not lock.exists()


def test_orden_reanudacion_y_liberacion_entre_fases(tmp_path):
    from convertersmartgrid.training_coordinator import ORDEN_MODELOS, TrainingCoordinator, TrainingStage

    llamadas = []
    etapas = [TrainingStage(nombre, lambda n=nombre: llamadas.append(n) or {
        'status': 'PROMOVIDO', 'model': n}, uses_gpu=nombre != 'evolutivos') for nombre in ORDEN_MODELOS]
    coordinador = TrainingCoordinator(etapas, tmp_path / 'run',
                                      liberar_ollama=lambda: llamadas.append('liberar_ollama'),
                                      liberar_cuda=lambda: llamadas.append('liberar_cuda'))
    informe = coordinador.run(resume=True)
    assert [x['model'] for x in informe['stages']] == list(ORDEN_MODELOS)
    antes = list(llamadas)
    assert coordinador.run(resume=True) == informe and llamadas == antes
    posiciones = [llamadas.index(n) for n in ORDEN_MODELOS]
    assert posiciones == sorted(posiciones)


@pytest.mark.parametrize('contenido', ['{roto', '{}', '{"pid": null}', '[]'])
def test_lock_ilegible_bloquea(tmp_path, contenido):
    """043:RF-6 — un lock sin propietario válido no se borra en silencio."""
    from convertersmartgrid.training_coordinator import BloqueoGPU
    ruta = tmp_path / 'gpu.lock'
    ruta.write_text(contenido, encoding='utf-8')
    with pytest.raises(RuntimeError, match='lock'):
        with BloqueoGPU(ruta, 'gru'):
            pytest.fail('entró con lock ilegible')
    assert ruta.read_text(encoding='utf-8') == contenido


def test_dos_ejecuciones_comparten_bloqueo(tmp_path, monkeypatch):
    """043:RF-6 — directorios de ejecución distintos no habilitan dos etapas CUDA."""
    from convertersmartgrid.training_coordinator import TrainingCoordinator, TrainingStage
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'global.lock'))
    llamadas = []
    def segunda():
        return TrainingCoordinator([TrainingStage('gru', lambda: llamadas.append('segunda') or {
            'status': 'RECHAZADO'})], tmp_path / 'segunda').run()
    informe = TrainingCoordinator([TrainingStage('pinn', lambda: {
        'status': 'RECHAZADO', 'segunda': segunda()})], tmp_path / 'primera').run()
    assert llamadas == []
    assert informe['stages'][0]['segunda']['stages'][0]['status'] == 'ERROR_ENTORNO'


def test_guardia_no_recupera_metadatos_obsoletos_mientras_hay_propietario(tmp_path):
    """043:RF-6 — la exclusión no depende de releer un PID antes de un unlink."""
    from convertersmartgrid.training_coordinator import BloqueoGPU
    ruta = tmp_path / 'gpu.lock'
    with BloqueoGPU(ruta, 'propietario'):
        ruta.write_text(json.dumps({'pid': 99999999, 'model': 'obsoleto'}), encoding='utf-8')
        with pytest.raises(RuntimeError, match='GPU ocupada'):
            with BloqueoGPU(ruta, 'segundo'):
                pytest.fail('dos propietarios simultáneos')


def test_corrida_sin_gpu_no_libera_recursos_del_propietario(tmp_path, monkeypatch):
    """043:RF-6 — fallar al adquirir GPU no autoriza descargar recursos de otra etapa."""
    from convertersmartgrid.training_coordinator import BloqueoGPU, TrainingCoordinator, TrainingStage
    ruta = tmp_path / 'global.lock'
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(ruta))
    llamadas = []
    with BloqueoGPU(ruta, 'propietario'):
        resultado = TrainingCoordinator([TrainingStage('gru', lambda: {'status': 'RECHAZADO'})],
            tmp_path / 'run', liberar_ollama=lambda: llamadas.append('ollama'),
            liberar_cuda=lambda: llamadas.append('cuda')).run()
    assert llamadas == []
    assert resultado['stages'][0]['status'] == 'ERROR_ENTORNO'


@pytest.mark.parametrize('fisica,commit,minimo,permitido', [
    (1.32, 9.13, 6., True),
    (0.1, 12., 6., False),
    (7., 2., 6., False),
    (2., None, 3., False),
    (7., None, 6., True),
])
def test_memoria_windows_distingue_ram_y_compromiso(monkeypatch, fisica, commit, minimo, permitido):
    """043:RF-12: memoria comprometible suficiente no es igual a RAM fisica libre."""
    import convertersmartgrid.training_coordinator as m
    assert callable(getattr(m, 'exigir_memoria_ml', None)), 'Falta el control de memoria comprometible'
    monkeypatch.setattr(m, '_memoria_sistema', lambda: {'fisica_gib': fisica, 'commit_gib': commit})
    if permitido:
        assert m.exigir_memoria_ml(minimo, minimo_commit_gib=8.)['fisica_gib'] == fisica
    else:
        with pytest.raises(ValueError, match='Memoria insuficiente'):
            m.exigir_memoria_ml(minimo, minimo_commit_gib=8.)


def test_token_inventado_no_hereda_la_guardia(tmp_path, monkeypatch):
    """043:RF-6 — un hijo real solo entra con el token del dueño vivo que es su ancestro: no basta una variable."""
    from convertersmartgrid.training_coordinator import BloqueoGPU
    from convertersmartgrid.trabajadores_ml import entorno_hijo_gpu
    lock = tmp_path / 'gpu.lock'
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(lock))
    src = Path(__file__).resolve().parents[1] / 'src'
    script = ('import sys; sys.path.insert(0, sys.argv[1]); '
              'from convertersmartgrid.trabajadores_ml import turno_gpu\n'
              'with turno_gpu("hijo"):\n    print("ENTRO")')

    def hijo(env):
        return subprocess.run([sys.executable, '-c', script, str(src)], env=env, capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=120)
    with BloqueoGPU(lock, 'padre'):
        legitimo = hijo(entorno_hijo_gpu())
        assert legitimo.returncode == 0 and 'ENTRO' in legitimo.stdout, legitimo.stderr
        sin_token = {k: v for k, v in entorno_hijo_gpu().items() if k != 'CSG_GPU_PARENT_TOKEN'}
        ocupado = hijo(sin_token)
        assert ocupado.returncode != 0 and 'ocupada' in ocupado.stderr and 'ENTRO' not in ocupado.stdout
        falso = hijo({**sin_token, 'CSG_GPU_PARENT_TOKEN': 'inventado'})
        assert falso.returncode != 0 and 'no corresponde' in falso.stderr and 'ENTRO' not in falso.stdout


#: Lo que entrena de verdad: una llamada a cualquiera de ellos fuera del turno pelea por la misma GPU.
_ENTRENAN = {'entrenar_y_promover', 'entrenar_gobernado', 'entrenar_destilacion', 'entrenar_recuperador', 'entrenar_temporal',
             'comparar_pronosticos', 'entrenar_epoca', 'entrenar_ppo', 'entrenar_si_toca', 'learn', 'entrenar_miembro'}
_GUARDIAS = {'turno_gpu', 'BloqueoGPU'}


def _nombre(llamada):
    import ast
    f = llamada.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None


def _entrena(llamada):
    import ast
    if _nombre(llamada) in _ENTRENAN:
        return True
    # ``oraculo.entrenar``, ``modulo.entrenar``: no el cierre ``entrenar()`` de un guion, que se sigue por sus llamadas.
    return isinstance(llamada.func, ast.Attribute) and llamada.func.attr == 'entrenar'


def _llamadas_sin_turno(ruta):
    """Las llamadas que entrenan sin ``with`` de la guardia; un cierre vale si alguien lo llama con ella."""
    import ast
    arbol = ast.parse(ruta.read_text(encoding='utf-8'))
    padres = {hijo: nodo for nodo in ast.walk(arbol) for hijo in ast.iter_child_nodes(nodo)}

    def bajo_guardia(nodo, vistos=()):
        while nodo in padres:
            nodo = padres[nodo]
            if isinstance(nodo, ast.With) and any(
                    isinstance(n, ast.Name) and n.id in _GUARDIAS for i in nodo.items for n in ast.walk(i.context_expr)):
                return True
            if isinstance(nodo, (ast.FunctionDef, ast.Lambda)) and isinstance(nodo, ast.FunctionDef) \
                    and not isinstance(padres.get(nodo), ast.Module) and nodo.name not in vistos:
                return any(bajo_guardia(c, (*vistos, nodo.name)) for c in ast.walk(arbol)
                           if isinstance(c, ast.Call) and _nombre(c) == nodo.name)
        return False
    llamadas = [n for n in ast.walk(arbol) if isinstance(n, ast.Call) and _entrena(n)]
    return llamadas, [n.lineno for n in llamadas if not bajo_guardia(n)]


def test_todo_lanzador_de_entrenamiento_toma_la_guardia():
    """043:RF-6 — cada guion y cada vía a la GPU que entrena lo hace dentro del turno común, sin excepciones."""
    raiz = Path(__file__).resolve().parents[1]
    rutas = [*sorted((raiz / 'tools').glob('*.py')), raiz / 'src/convertersmartgrid/asistente/entrenamiento_dataset.py']
    entrenan, sin_turno = [], {}
    for ruta in rutas:
        llamadas, malas = _llamadas_sin_turno(ruta)
        if llamadas:
            entrenan.append(ruta.name)
        if malas:
            sin_turno[ruta.name] = malas
    assert not sin_turno, f'entrenan fuera del turno de GPU: {sin_turno}'
    # La comprobación tiene que estar viendo los lanzadores: si cambia su forma, no pasa en vacío.
    assert {'digital_twin_entrenar.py', 'digital_twin_temporal_entrenar.py', 'asistente_entrenar.py', 'asistente_destilar.py',
            'asistente_embeddings.py', 'asistente_qlora.py', 'llm_destilar.py', 'madrl_entrenar.py',
            'entrenamiento_dataset.py'} <= set(entrenan), entrenan


def test_la_comprobacion_de_lanzadores_detecta_uno_sin_turno(tmp_path):
    """043:RF-6 — el detector marca una llamada desnuda y la de un cierre llamado sin guardia."""
    ruta = tmp_path / 'lanzador.py'
    ruta.write_text('def main():\n    def correr():\n        return oraculo.entrenar(1)\n    correr()\n'
                    '    entrenar_epoca(2)\n    with turno_gpu("x"):\n        entrenar_epoca(3)\n', encoding='utf-8')
    llamadas, malas = _llamadas_sin_turno(ruta)
    assert len(llamadas) == 3 and sorted(malas) == [3, 5]
