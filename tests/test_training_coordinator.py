"""043:RF-6 043:RF-7 — Coordinador reanudable y exclusión mutua real de GPU."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_lock_rechaza_pid_vivo_y_recupera_pid_muerto(tmp_path):
    from igea_dgs.training_coordinator import BloqueoGPU

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
    from igea_dgs.training_coordinator import BloqueoGPU

    lock = tmp_path / 'gpu.lock'
    script = ('import sys,time; sys.path.insert(0,sys.argv[2]); '
              'from igea_dgs.training_coordinator import BloqueoGPU; '
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
    from igea_dgs.training_coordinator import ORDEN_MODELOS, TrainingCoordinator, TrainingStage

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
    from igea_dgs.training_coordinator import BloqueoGPU
    ruta = tmp_path / 'gpu.lock'
    ruta.write_text(contenido, encoding='utf-8')
    with pytest.raises(RuntimeError, match='lock'):
        with BloqueoGPU(ruta, 'gru'):
            pytest.fail('entró con lock ilegible')
    assert ruta.read_text(encoding='utf-8') == contenido


def test_dos_ejecuciones_comparten_bloqueo(tmp_path, monkeypatch):
    """043:RF-6 — directorios de ejecución distintos no habilitan dos etapas CUDA."""
    from igea_dgs.training_coordinator import TrainingCoordinator, TrainingStage
    monkeypatch.setenv('IGEA_ML_GPU_LOCK', str(tmp_path / 'global.lock'))
    llamadas = []
    def segunda():
        return TrainingCoordinator([TrainingStage('gru', lambda: llamadas.append('segunda') or {
            'status': 'RECHAZADO'})], tmp_path / 'segunda').run()
    informe = TrainingCoordinator([TrainingStage('pinn', lambda: {
        'status': 'RECHAZADO', 'segunda': segunda()})], tmp_path / 'primera').run()
    assert llamadas == []
    assert informe['stages'][0]['segunda']['stages'][0]['status'] == 'ERROR_ENTORNO'
