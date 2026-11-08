"""043:RF-5 043:RF-7 — reanudación y verificación del contrato completo."""
import json
import sys
from pathlib import Path

import pytest


def test_resume_config_distinta_rechaza(tmp_path):
    """043:RF-7 — no reutilizar una ejecución de otras semillas/datos/configuración."""
    from convertersmartgrid.training_coordinator import TrainingCoordinator, TrainingStage
    etapas = [TrainingStage('gru', lambda: {'status': 'RECHAZADO'}, uses_gpu=False)]
    TrainingCoordinator(etapas, tmp_path, config_hash='a' * 64).run()
    with pytest.raises(ValueError, match='configuraci'):
        TrainingCoordinator(etapas, tmp_path, config_hash='b' * 64).run(resume=True)


def test_verify_rechaza_familias_duplicadas(tmp_path):
    """043:RF-7 — siete filas de una sola familia no son siete modelos entrenados."""
    from tools.reentrenar_modelos import verificar
    ruta = tmp_path / 'report.json'
    ruta.write_text(json.dumps({'complete': True, 'stages': [
        {'model': 'gru', 'status': 'PROMOVIDO'} for _ in range(7)]}), encoding='utf-8')
    assert verificar(ruta, fail_on_incomplete=True) != 0


def test_config_se_valida_sin_entrenar(tmp_path, capsys):
    """043:RF-2 043:RF-7 — inspección reproducible antes de ocupar GPU o motor nativo."""
    from dataclasses import asdict
    from test_experimentos import contexto
    from tools.reentrenar_modelos import main
    ruta = tmp_path / 'config.json'
    ruta.write_text(json.dumps({'schema_version': 1, 'contexto': asdict(contexto()),
        'algoritmo': 'gru', 'semillas': [11, 23], 'revision': 'revision-fijada',
        'politica': {'cobertura_objetivo': 0.9}}), encoding='utf-8')
    assert main(['run', '--config', str(ruta), '--validar-config']) == 0
    resultado = json.loads(capsys.readouterr().out)
    assert resultado['etapas'] == ['gru'] and len(resultado['config_hash']) == 64
    assert not (tmp_path / 'report.json').exists()


def test_subproceso_fallido_no_reutiliza_informe(tmp_path):
    """043:RF-5 — un reporte anterior no hace exitoso un proceso que acaba de fallar."""
    import sys
    from tools.reentrenar_modelos import _subproceso
    ruta = tmp_path / 'gru.json'
    ruta.write_text(json.dumps({'promovido': True, 'entrenado': True}), encoding='utf-8')
    resultado = _subproceso([sys.executable, '-c', 'raise SystemExit(3)'], ruta, 'gru')
    assert resultado['status'] == 'ERROR_ENTORNO'


def test_huella_twin_cambia_con_objetos(tmp_path):
    """043:RF-7 — el búfer real no tiene un manifest.json único de sus objetos."""
    from tools.reentrenar_modelos import huella_entrada
    objeto = tmp_path / 'objetos/aa/episodio.json'
    objeto.parent.mkdir(parents=True)
    objeto.write_text('{"valor": 1}', encoding='utf-8')
    antes = huella_entrada(tmp_path, tipo='twin')
    objeto.write_text('{"valor": 2}', encoding='utf-8')
    assert huella_entrada(tmp_path, tipo='twin') != antes


def test_verify_rechazo_sin_entrenamiento_no_cierra(tmp_path):
    """043:RF-7 — rechazar promoción no demuestra haber entrenado una familia."""
    from tools.reentrenar_modelos import verificar
    from convertersmartgrid.training_coordinator import ORDEN_MODELOS
    ruta = tmp_path / 'report.json'
    ruta.write_text(json.dumps({'complete': True, 'stages': [
        {'model': n, 'status': 'RECHAZADO'} for n in ORDEN_MODELOS]}), encoding='utf-8')
    assert verificar(ruta, fail_on_incomplete=True) != 0


RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def turno_de_ensayo(tmp_path, monkeypatch):
    """Estas pruebas nunca toman la guardia real: otra sesión puede estar entrenando en la GPU."""
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'ensayo-gpu.lock'))
    src = str(RAIZ / 'src')
    monkeypatch.setenv('PYTHONPATH', src)      # los hijos abren este código, también desde un worktree


def _payload(tmp_path, status='PROMOVIDO', contenido=b'pesos', smoke=None):
    artefacto = tmp_path / 'pesos.bin'
    artefacto.write_bytes(contenido)
    return dict(model_manifest={'algorithm': 'prueba'}, dataset_manifest={'sha256': 'd' * 64}, metrics={'mae': .1},
                decision={'status': status, 'gates': {'approved': status == 'PROMOVIDO'}},
                smoke_reload=smoke if smoke is not None else {'ok': status == 'PROMOVIDO'}, artifacts=[artefacto])


def _carpeta_ilegible(tmp_path):
    """Los ficheros de cualquier familia, truncados: se rompen al leerlos, antes de tocar pesos ni GPU."""
    carpeta = tmp_path / 'candidato'
    carpeta.mkdir()
    for nombre in ('modelo.json', 'readback.json', 'sonda.npz', 'pesos.pt', 'miembro_0.pt', 'estado.json'):
        (carpeta / nombre).write_bytes(b'{truncado')
    return carpeta


#: La orden real con que cada familia reabre un candidato en otro proceso.
REAPERTURAS = {
    'pinn': ('tools/digital_twin_entrenar.py', '--reabrir-candidato'),
    'gru': ('tools/digital_twin_temporal_entrenar.py', '--reabrir-candidato'),
    'transformer': ('tools/asistente_destilar.py', 'verificar', '--modelo'),
    'clasificador': ('tools/asistente_destilar.py', 'verificar', '--familia', 'clasificador', '--modelo'),
}


@pytest.mark.parametrize('familia', REAPERTURAS)
def test_smoke_fallido_no_promueve(tmp_path, familia):
    """043:RF-5 — el proceso real de la familia no reabre un artefacto ilegible, y el activo sigue siendo el anterior."""
    from convertersmartgrid.model_registry import RegistroModelo, reabrir_en_subproceso
    herramienta, *opciones = REAPERTURAS[familia]
    smoke = reabrir_en_subproceso([sys.executable, str(RAIZ / herramienta), *opciones, str(_carpeta_ilegible(tmp_path))],
                                  timeout_s=300.)
    assert smoke['ok'] is False and smoke['returncode'] not in (0, None), smoke
    registro = RegistroModelo(tmp_path / 'registro')
    anterior = registro.registrar_candidato(familia, **_payload(tmp_path))
    registro.promover(familia, anterior['candidate_id'])
    with pytest.raises(ValueError, match='reapertura'):
        registro.registrar_candidato(familia, **_payload(tmp_path, contenido=b'nuevo', smoke=smoke))
    registro.registrar_candidato(familia, **{**_payload(tmp_path, status='RECHAZADO', contenido=b'nuevo'), 'smoke_reload': smoke})
    assert registro.activo(familia)['candidate_id'] == anterior['candidate_id']
    assert registro.ultimo(familia)['status'] == 'RECHAZADO'


def test_reapertura_del_indice_en_otro_proceso(tmp_path):
    """043:RF-5 — la familia sin GPU, reabierta de verdad en otro proceso; alterada, deja de abrir."""
    from types import SimpleNamespace
    from convertersmartgrid.asistente.embeddings import guardar_indice_versionado
    from convertersmartgrid.model_registry import reabrir_en_subproceso
    frags = [SimpleNamespace(id='a', fuente='f', texto='texto del fragmento')]
    guardar_indice_versionado(frags, [[1.0, 0.0]], tmp_path / 'indice', modelo='base', segmentacion={'dataset': 'v2'})
    orden = [sys.executable, '-c',
             'import json,sys; from convertersmartgrid.asistente.embeddings import reabrir_indice_versionado as r; '
             'print(json.dumps({"ok": len(r(sys.argv[1]).buscar("texto", 1, [1.0, 0.0])) == 1}))', str(tmp_path / 'indice')]
    assert reabrir_en_subproceso(orden, timeout_s=300.)['ok'] is True
    (tmp_path / 'indice/vectores.json').write_text('[[0.0, 1.0]]', encoding='utf-8')
    assert reabrir_en_subproceso(orden, timeout_s=300.)['ok'] is False


def _candidato_pinn(tmp_path, contenido=b'{"miembros": 0}'):
    from convertersmartgrid.digital_twin.buffer import BuferEpisodios
    bufer = BuferEpisodios(tmp_path / 'bufer')
    carpeta = tmp_path / 'bufer/modelos/20261103-nuevo'
    carpeta.mkdir(parents=True)
    (carpeta / 'modelo.json').write_bytes(contenido)
    (carpeta / 'miembro_0.pt').write_bytes(b'pesos')
    return bufer, carpeta


def _puntero_pinn(bufer):
    from convertersmartgrid.digital_twin.oraculo import promover
    (bufer.raiz / 'modelos/anterior').mkdir(parents=True, exist_ok=True)
    promover(bufer, 'anterior', 'el modelo en uso')
    return json.loads((bufer.raiz / 'modelos/promovido.json').read_text(encoding='utf-8'))['version']


def test_pinn_no_reabierta_no_se_promueve(tmp_path):
    """043:RF-5 — la PINN se promovía con solo sus puertas; ahora la herramienta real la reabre y el puntero no se mueve."""
    from convertersmartgrid.digital_twin.oraculo import _decidir_promocion
    from convertersmartgrid.model_registry import RegistroModelo
    bufer, carpeta = _candidato_pinn(tmp_path)        # sin readback.json: no se puede comprobar, luego no entra
    assert _puntero_pinn(bufer) == 'anterior'
    registro = RegistroModelo(tmp_path / 'registro')
    fallos = []
    r = _decidir_promocion(bufer, carpeta, {}, fallos, 'mae 0.001', registro=registro)
    assert r['promovido'] is False and any('reapertura' in f for f in fallos), fallos
    assert json.loads((bufer.raiz / 'modelos/promovido.json').read_text(encoding='utf-8'))['version'] == 'anterior'
    ultimo = registro.ultimo('pinn')
    assert ultimo['status'] == 'RECHAZADO' and ultimo['candidate_id'] == r['candidate_id']


def test_pinn_aprobada_queda_en_el_registro_y_en_su_puntero(tmp_path):
    """043:RF-1 — la decisión consta en el registro común y lo que la pone en uso sigue siendo un puntero (071:RF-5)."""
    from convertersmartgrid.digital_twin.oraculo import _decidir_promocion
    from convertersmartgrid.model_registry import RegistroModelo
    bufer, carpeta = _candidato_pinn(tmp_path)
    registro = RegistroModelo(tmp_path / 'registro')
    r = _decidir_promocion(bufer, carpeta, {'cfg': {'ocultas': 8}}, [], 'mae 0.001', registro=registro,
                           reabrir=lambda _c: {'ok': True, 'proceso_nuevo': True})
    assert r['promovido'] is True
    assert json.loads((bufer.raiz / 'modelos/promovido.json').read_text(encoding='utf-8'))['version'] == carpeta.name
    detalle = registro.ultimo('pinn')['detalle']
    assert detalle['decision']['status'] == 'PROMOVIDO' and detalle['model_manifest']['version'] == carpeta.name
    assert registro.activo('pinn') is None


def test_pinn_del_ciclo_registra_sin_publicar_individual(tmp_path):
    """050:RF-4, 050:RF-7 — el candidato aprobado no cambia el modelo en uso."""
    from convertersmartgrid.digital_twin.oraculo import _decidir_promocion
    from convertersmartgrid.model_registry import RegistroModelo
    bufer, carpeta = _candidato_pinn(tmp_path)
    assert _puntero_pinn(bufer) == 'anterior'
    registro = RegistroModelo(tmp_path / 'registro')
    r = _decidir_promocion(bufer, carpeta, {}, [], 'ciclo común', registro=registro,
        reabrir=lambda _c: {'ok': True}, publicar_individual=False)
    assert r['promovido'] is False and r['candidato_aprobado'] is True
    assert r['publicacion_pendiente'] is True and r['candidate_id']
    assert registro.ultimo('pinn')['detalle']['decision']['gates']['approved'] is True
    assert json.loads((bufer.raiz / 'modelos/promovido.json').read_text(encoding='utf-8'))['version'] == 'anterior'
    assert registro.activo('pinn') is None
    from tools.reentrenar_modelos import _estado
    estado = _estado({**r, 'entrenado': True}, 'pinn')
    assert estado['status'] == 'PROMOVIDO' and estado['publicacion_pendiente'] is True


def test_pinn_del_ciclo_exige_registro(tmp_path):
    """050:RF-7, 050:RF-8 — sin candidato registrado no se declara publicable."""
    from convertersmartgrid.digital_twin.oraculo import _decidir_promocion
    bufer, carpeta = _candidato_pinn(tmp_path)
    with pytest.raises(ValueError, match='registro'):
        _decidir_promocion(bufer, carpeta, {}, [], 'ciclo común', publicar_individual=False)


@pytest.mark.parametrize('caso', ['puertas', 'sin_anotar'])
def test_pinn_sin_puertas_o_sin_anotar_no_toca_el_puntero(tmp_path, caso):
    """043:RF-5 — con puertas falladas ni se reabre; sin decisión anotada tampoco hay promoción."""
    from convertersmartgrid.digital_twin.oraculo import _decidir_promocion
    from convertersmartgrid.model_registry import RegistroModelo
    bufer, carpeta = _candidato_pinn(tmp_path)
    _puntero_pinn(bufer)
    fallos = ['error de tensión sobre el umbral'] if caso == 'puertas' else []
    registro = RegistroModelo(tmp_path / 'registro')
    if caso == 'sin_anotar':
        (tmp_path / 'registro').write_text('no es una carpeta', encoding='utf-8')
    reabrir = (lambda _c: pytest.fail('reabrió un candidato rechazado')) if caso == 'puertas' else (lambda _c: {'ok': True})
    r = _decidir_promocion(bufer, carpeta, {}, fallos, 'mae', registro=registro, reabrir=reabrir)
    assert r['promovido'] is False and fallos
    assert json.loads((bufer.raiz / 'modelos/promovido.json').read_text(encoding='utf-8'))['version'] == 'anterior'


def _config(ruta, semillas, algoritmo='gru'):
    from dataclasses import asdict
    from test_experimentos import contexto
    ruta.write_text(json.dumps({'schema_version': 1, 'contexto': asdict(contexto()), 'algoritmo': algoritmo, 'semillas': semillas,
                                'revision': 'revision-fijada', 'politica': {'cobertura_objetivo': 0.9}}), encoding='utf-8')
    return ruta


def _main_sin_entrenar(monkeypatch, llamadas, status='RECHAZADO'):
    """El ``main`` real con etapas que no tocan la GPU: se cuenta qué etapas corren de verdad."""
    import tools.reentrenar_modelos as m
    from convertersmartgrid.training_coordinator import ORDEN_MODELOS, TrainingStage

    def etapas(_args, _run_dir):
        return [TrainingStage(n, lambda n=n: llamadas.append(n) or {'status': status, 'metrica': len(llamadas)}, uses_gpu=False)
                for n in ORDEN_MODELOS]
    monkeypatch.setattr(m, '_etapas', etapas)
    return m


def test_resume_otra_semilla_no_reutiliza_metricas(tmp_path, monkeypatch, capsys):
    """043:RF-7 — cambiar una semilla del contrato rechaza la reanudación: ni corre ni devuelve lo anterior."""
    llamadas = []
    m = _main_sin_entrenar(monkeypatch, llamadas)
    run = tmp_path / 'run'
    base = ['run', '--run-dir', str(run), '--dataset', str(tmp_path / 'd'), '--vocabulario', str(tmp_path / 'v'),
            '--twin', str(tmp_path / 't'), '--resume']
    assert m.main([*base, '--config', str(_config(tmp_path / 'a.json', [11, 23]))]) == 0
    capsys.readouterr()
    antes = (run / 'report.json').read_text(encoding='utf-8')
    assert llamadas == ['gru']
    assert m.main([*base, '--config', str(_config(tmp_path / 'b.json', [11, 29]))]) == 2
    salida = json.loads(capsys.readouterr().out)
    assert salida['ok'] is False and 'configuraci' in salida['reason']
    assert llamadas == ['gru'] and (run / 'report.json').read_text(encoding='utf-8') == antes


def test_resume_compatible_preserva_las_terminales(tmp_path):
    """043:RF-7 — tras un corte se conservan las etapas terminales y solo corre lo que faltaba."""
    from convertersmartgrid.training_coordinator import TrainingCoordinator, TrainingStage
    llamadas = []
    def etapa(nombre, cae=False):
        def correr():
            llamadas.append(nombre)
            if cae:
                raise KeyboardInterrupt
            return {'status': 'RECHAZADO', 'corrida': len(llamadas)}
        return correr
    with pytest.raises(KeyboardInterrupt):
        TrainingCoordinator([TrainingStage('gru', etapa('gru'), uses_gpu=False), TrainingStage('qlora', etapa('qlora', cae=True), uses_gpu=False)],
                            tmp_path, config_hash='c' * 64).run()
    informe = TrainingCoordinator([TrainingStage('gru', etapa('gru'), uses_gpu=False), TrainingStage('qlora', etapa('qlora'), uses_gpu=False)],
                                  tmp_path, config_hash='c' * 64).run(resume=True)
    assert llamadas == ['gru', 'qlora', 'qlora']
    assert informe['complete'] is True and informe['stages'][0]['corrida'] == 1


def test_etapa_temporal_conserva_alias_gru(tmp_path, monkeypatch, capsys):
    """043:RF-7, 046:RF-13 — PatchTST se ejecuta y se informa como ``algorithm`` dentro de la etapa ``gru``."""
    import tools.reentrenar_modelos as m
    vistas = []
    def subproceso(comando, reporte, modelo, **_k):
        vistas.append((comando, modelo))
        return {'status': 'RECHAZADO', 'training_completed': True, 'report': str(reporte)}
    monkeypatch.setattr(m, '_subproceso', subproceso)
    monkeypatch.setattr('convertersmartgrid.asistente.ollama.liberar_gpu_para_entrenar', lambda: None)
    run = tmp_path / 'run'
    assert m.main(['run', '--config', str(_config(tmp_path / 'c.json', [11], 'patchtst')), '--run-dir', str(run),
                   '--dataset', str(tmp_path / 'd'), '--vocabulario', str(tmp_path / 'v'), '--twin', str(tmp_path / 't'),
                   '--cabeceras', str(tmp_path / 'libro.xlsx'), '--zona-horaria', 'America/Lima',
                   '--cadencia-temporal', '15']) == 0
    capsys.readouterr()
    informe = json.loads((run / 'report.json').read_text(encoding='utf-8'))
    assert [(s['model'], s['algorithm']) for s in informe['stages']] == [('gru', 'patchtst')]
    assert vistas[0][1] == 'gru' and any('ingenuo,estacional_semanal,gru,patchtst' == a for a in vistas[0][0])


def test_runner_no_acepta_promovido_sin_candidato(tmp_path):
    """043:RF-5 — un trabajador que dice promovido sin candidato en el registro no da PROMOVIDO: nunca un OK falso."""
    from tools.reentrenar_modelos import _subproceso
    ruta = tmp_path / 'r.json'
    def correr(datos):
        codigo = f'import json,pathlib; pathlib.Path({str(ruta)!r}).write_text(json.dumps({datos!r}))'
        return _subproceso([sys.executable, '-c', codigo], ruta, 'gru')
    falso = correr({'promovido': True, 'entrenado': True})
    assert falso['status'] == 'RECHAZADO' and 'candidato' in falso['reason']
    real = correr({'promovido': True, 'entrenado': True, 'candidate_id': 'a' * 64, 'modelo_registro': 'pronostico_cabecera'})
    assert real['status'] == 'PROMOVIDO' and real['candidate_id'] == 'a' * 64
    assert real['modelo_registro'] == 'pronostico_cabecera'


def _guardia_en_otro_proceso(lock, segundos: float | None = None):
    """Un doble de la otra sesión que tiene la GPU: toma la guardia común y la suelta tras ``segundos``
    o al cerrar su entrada; no toca CUDA."""
    import subprocess

    espera = f'time.sleep({segundos})' if segundos is not None else 'sys.stdin.read()'
    codigo = ('import sys,time; sys.path.insert(0,sys.argv[2]); '
              'from convertersmartgrid.training_coordinator import BloqueoGPU; '
              'b=BloqueoGPU(sys.argv[1],"otra-sesion"); b.__enter__(); print("LOCKED",flush=True); '
              f'{espera}; b.__exit__(None,None,None)')
    src = Path(__file__).resolve().parents[1] / 'src'
    proc = subprocess.Popen([sys.executable, '-c', codigo, str(lock), str(src)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == 'LOCKED'
    return proc


def test_reapertura_con_la_gpu_de_otro_dice_gpu_ocupada(tmp_path, monkeypatch):
    """043:RF-5, 043:RF-6 — entrenar sin turno y con otra sesión en la GPU: la reapertura real no se hace,
    nada se promueve y el motivo dice «GPU ocupada», no un código de salida (2026-11-03)."""
    from convertersmartgrid.digital_twin.oraculo import _decidir_promocion
    lock = tmp_path / 'gpu.lock'
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(lock))
    monkeypatch.delenv('CSG_GPU_PARENT_TOKEN', raising=False)
    bufer, carpeta = _candidato_pinn(tmp_path)
    otra = _guardia_en_otro_proceso(lock)
    try:
        fallos = []
        r = _decidir_promocion(bufer, carpeta, {}, fallos, 'mae')
    finally:
        otra.communicate('', timeout=30)
    assert r['promovido'] is False and r['smoke_reload']['ok'] is False
    assert any('reapertura' in f and 'GPU ocupada' in f for f in fallos), fallos


def test_con_el_turno_tomado_la_reapertura_lo_hereda(tmp_path, monkeypatch):
    """043:RF-5, 043:RF-6 — quien entrena con el turno lo pasa al hijo que reabre: el hijo llega a abrir el
    candidato (aquí sin ``readback.json``, luego falla por eso) y no por la GPU."""
    from apoyo import turno_gpu_esperando
    from convertersmartgrid.digital_twin.oraculo import _decidir_promocion
    lock = tmp_path / 'gpu.lock'
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(lock))
    monkeypatch.delenv('CSG_GPU_PARENT_TOKEN', raising=False)
    bufer, carpeta = _candidato_pinn(tmp_path)
    fallos = []
    with turno_gpu_esperando('prueba-reapertura', limite_s=0):
        r = _decidir_promocion(bufer, carpeta, {}, fallos, 'mae')
    assert r['promovido'] is False and fallos and not any('GPU ocupada' in f for f in fallos), fallos
    assert 'readback' in fallos[0]


def test_la_prueba_que_entrena_espera_su_turno(tmp_path, monkeypatch):
    """043:RF-6 — con otra sesión en la GPU, la prueba espera su turno; si no llega a tiempo, falla diciendo
    «GPU ocupada» en vez de dejar que el candidato se rechace por otro motivo."""
    import time

    from apoyo import turno_gpu_esperando
    lock = tmp_path / 'gpu.lock'
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(lock))
    monkeypatch.delenv('CSG_GPU_PARENT_TOKEN', raising=False)
    otra = _guardia_en_otro_proceso(lock)
    try:
        with pytest.raises(RuntimeError, match='GPU ocupada'):
            with turno_gpu_esperando('prueba', limite_s=0.3, pausa_s=0.1):
                pass
    finally:
        otra.communicate('', timeout=30)
    otra = _guardia_en_otro_proceso(lock, segundos=1.0)
    t0 = time.monotonic()
    with turno_gpu_esperando('prueba', limite_s=60, pausa_s=0.2):
        assert json.loads(lock.read_text(encoding='utf-8'))['model'] == 'prueba'
    assert time.monotonic() - t0 >= 0.5
    otra.wait(timeout=30)
