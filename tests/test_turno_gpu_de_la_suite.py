"""106:RF-1 a RF-5 — la suite y los entrenamientos se turnan la GPU de la máquina, con plazo y diciendo quién la tiene.

Suite de 10a80812 (2026-11-12): 62 fallidas, 61 «CUDA error: out of memory», con el entrenamiento T7 en la GPU. Cada
prueba tenía su guardia propia (102:RF-22) y no veía la del entrenamiento; la prueba de módulo del oráculo, en cambio,
tomaba la real y la puerta de un commit esperó 40 min en silencio. Repetidas solas, las 62 pasaron.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import conftest
from test_experimentos_runner import _guardia_en_otro_proceso


def _dueno(lock) -> str:
    """El PID que consta en el turno: el del Python real, no el del lanzador del .venv que da ``Popen.pid``."""
    import json

    return f"PID {json.loads(Path(lock).read_text(encoding='utf-8'))['pid']}"


class _Reloj:
    """Tiempo simulado: la espera avanza sin dormir de verdad."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += s


@pytest.fixture(scope='module')
def ruta_vista_por_un_fixture_de_modulo():
    """Como el ``turno`` de test_digital_twin_oraculo: un fixture de módulo, preparado antes que los de cada prueba."""
    from convertersmartgrid.training_coordinator import ruta_guardia_gpu

    return ruta_guardia_gpu()


def test_un_fixture_de_modulo_no_ve_la_guardia_de_la_maquina(ruta_vista_por_un_fixture_de_modulo):
    """106:RF-1 — el caso de la puerta colgada: antes, el fixture de módulo resolvía la guardia real de la máquina."""
    assert Path(ruta_vista_por_un_fixture_de_modulo) != Path(conftest.GUARDIA_GPU_DE_LA_MAQUINA)
    assert 'csg-gpu-sesion-' in str(ruta_vista_por_un_fixture_de_modulo)


def test_la_espera_dice_quien_tiene_la_gpu_y_vence_con_su_dueno(tmp_path):
    """106:RF-2, 106:RF-3 — con otro proceso en el turno, se avisa de su PID y su orden; al vencer, error con ese dueño."""
    from convertersmartgrid.trabajadores_ml import turno_gpu_con_plazo

    lock = tmp_path / 'gpu.lock'
    otra = _guardia_en_otro_proceso(lock)
    pid = _dueno(lock)
    reloj, avisos = _Reloj(), []
    try:
        with pytest.raises(RuntimeError) as exc:
            with turno_gpu_con_plazo('suite-pytest', ruta=lock, limite_s=120, pausa_s=5, aviso_cada_s=60,
                                     avisar=avisos.append, reloj=reloj, dormir=reloj.dormir):
                pass
    finally:
        otra.communicate('', timeout=30)
    assert pid in str(exc.value) and 'otra-sesion' in str(exc.value) and '106:RF-3' in str(exc.value)
    assert len(avisos) == 2 and all(pid in a and 'otra-sesion' in a for a in avisos)


def test_cuando_el_otro_suelta_la_gpu_la_toma(tmp_path):
    """106:RF-2 — el turno libre se toma, queda a nombre de este proceso y se suelta al salir."""
    import json

    from convertersmartgrid.trabajadores_ml import turno_gpu_con_plazo

    lock = tmp_path / 'gpu.lock'
    otra = _guardia_en_otro_proceso(lock, segundos=1.0)
    with turno_gpu_con_plazo('suite-pytest', ruta=lock, limite_s=60, pausa_s=0.2):
        dueno = json.loads(lock.read_text(encoding='utf-8'))
        assert dueno['pid'] == os.getpid() and dueno['model'] == 'suite-pytest'
    otra.wait(30)
    assert not lock.exists()


class _Item:
    """Un ítem recogido, con o sin la marca ``gpu``."""

    def __init__(self, gpu: bool):
        self._gpu = gpu

    def get_closest_marker(self, nombre):
        return object() if nombre == 'gpu' and self._gpu else None


def _maquina(tmp_path, monkeypatch, nombre='maquina.lock'):
    lock = tmp_path / nombre
    monkeypatch.setattr(conftest, 'GUARDIA_GPU_DE_LA_MAQUINA', lock)
    monkeypatch.setattr(conftest, '_hay_cuda', lambda: True)
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    # El turno de esta misma sesión (este módulo usa la GPU) no se toca: cada prueba con su lista.
    monkeypatch.setattr(conftest, '_turno_de_la_sesion', [])
    return lock


def test_la_sesion_sin_gpu_libre_sale_sin_veredicto(tmp_path, monkeypatch):
    """106:RF-4 — si el plazo vence, pytest sale con SALIDA_SIN_TURNO_GPU y el dueño; no omite ni juzga nada."""
    from convertersmartgrid.trabajadores_ml import SALIDA_SIN_TURNO_GPU

    lock = _maquina(tmp_path, monkeypatch)
    monkeypatch.setenv(conftest.VARIABLE_ESPERA_GPU_SUITE, '0')
    otra = _guardia_en_otro_proceso(lock)
    pid = _dueno(lock)
    try:
        with pytest.raises(pytest.exit.Exception) as exc:
            conftest.tomar_turno_si_hace_falta([_Item(gpu=True)])
    finally:
        otra.communicate('', timeout=30)
    assert exc.value.returncode == SALIDA_SIN_TURNO_GPU and pid in str(exc.value.msg)
    assert SALIDA_SIN_TURNO_GPU not in range(0, 6), 'no se confunde con los códigos de pytest'
    assert conftest._turno_de_la_sesion == []


def test_la_sesion_con_gpu_libre_la_toma_y_la_suelta(tmp_path, monkeypatch):
    """106:RF-1 — la sesión con pruebas de GPU toma el turno de la máquina una vez y lo suelta al terminar."""
    import json

    lock = _maquina(tmp_path, monkeypatch)
    conftest.tomar_turno_si_hace_falta([_Item(gpu=False), _Item(gpu=True)])
    try:
        assert json.loads(lock.read_text(encoding='utf-8'))['model'] == 'suite-pytest'
    finally:
        conftest.pytest_sessionfinish(None, 0)
    assert not lock.exists() and conftest._turno_de_la_sesion == []


def test_una_sesion_sin_pruebas_de_gpu_no_espera_aunque_este_tomada(tmp_path, monkeypatch):
    """106:RF-7, 102:RF-18 — la puerta de un commit sin pruebas de GPU no espera a un entrenamiento."""
    lock = _maquina(tmp_path, monkeypatch)
    monkeypatch.setenv(conftest.VARIABLE_ESPERA_GPU_SUITE, '3600')
    otra = _guardia_en_otro_proceso(lock)
    try:
        import time

        t0 = time.monotonic()
        conftest.tomar_turno_si_hace_falta([_Item(gpu=False), _Item(gpu=False)])
        assert time.monotonic() - t0 < 5 and conftest._turno_de_la_sesion == []
    finally:
        otra.communicate('', timeout=30)


def test_una_sesion_lanzada_por_una_prueba_no_pide_la_gpu(tmp_path, monkeypatch):
    """106:RF-1 — un pytest hijo de una prueba no espera el turno que ya tiene su padre."""
    lock = _maquina(tmp_path, monkeypatch)
    monkeypatch.setenv('PYTEST_CURRENT_TEST', 'tests/x.py::y (call)')
    conftest.tomar_turno_si_hace_falta([_Item(gpu=True)])
    assert not lock.exists() and conftest._turno_de_la_sesion == []


def test_la_marca_gpu_se_pone_sola_a_todo_modulo_que_usa_torch():
    """106:RF-6 — gobierno: ningún módulo de pruebas que nombre torch, CUDA o el turno queda sin la marca ``gpu``."""
    carpeta = Path(__file__).resolve().parent
    sin_marca = [p.name for p in sorted(carpeta.glob('test_*.py'))
                 if re.search(r'torch|cuda|gpu', p.read_text(encoding='utf-8'), re.IGNORECASE)
                 and not conftest.usa_gpu(p)]
    assert sin_marca == []
    assert conftest.usa_gpu(carpeta / 'test_digital_twin_oraculo.py')
    assert not conftest.usa_gpu(carpeta / 'test_inventario.py')


def test_un_hijo_que_toma_el_turno_sin_la_marca_se_detecta(tmp_path):
    """106:RF-10 — RF-9 no ve lo que reserva un hijo; su turno, sí: queda el ``.guard`` de la guardia de la prueba."""
    lock = tmp_path / 'gpu.lock'
    assert conftest.turno_sin_marca(lock, marcada=False) is None
    otra = _guardia_en_otro_proceso(lock, segundos=0.1)
    otra.wait(30)
    motivo = conftest.turno_sin_marca(lock, marcada=False)
    assert motivo and 'sin la marca gpu' in motivo and '106:RF-10' in motivo
    assert conftest.turno_sin_marca(lock, marcada=True) is None


def test_el_turno_de_una_marcada_no_dispara_el_de_la_siguiente(tmp_path_factory):
    """106:RF-10 — cada prueba mira solo la guardia de su ``tmp_path``: una marcada que deja su ``.guard`` no hace fallar a
    la sin marca que viene después en el mismo módulo."""
    marcada = tmp_path_factory.mktemp('marcada') / 'gpu.lock'
    otra = _guardia_en_otro_proceso(marcada, segundos=0.1)
    otra.wait(30)
    assert conftest.turno_sin_marca(marcada, marcada=True) is None
    siguiente = tmp_path_factory.mktemp('sin_marca') / 'gpu.lock'
    assert conftest.turno_sin_marca(siguiente, marcada=False) is None


def test_el_fixture_mira_la_guardia_de_su_propia_prueba(tmp_path):
    """106:RF-10 — la guardia que vigila el fixture es la de ``tmp_path`` de esta prueba, no una común."""
    assert Path(os.environ['CSG_ML_GPU_LOCK']) == tmp_path / 'gpu.lock'


def test_la_puerta_trata_la_salida_sin_turno_como_fallo_con_su_dueno(tmp_path, monkeypatch):
    """106:RF-8 — la puerta de calidad nunca da «0 fallidas» si pytest salió sin el turno de GPU."""
    import subprocess

    from apoyo import cargar_herramienta
    from convertersmartgrid.trabajadores_ml import SALIDA_SIN_TURNO_GPU

    puerta = cargar_herramienta('puerta_calidad.py', 'puerta_turno_gpu', tools_en_path=True)
    lock = tmp_path / 'maquina.lock'
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(lock))
    otra = _guardia_en_otro_proceso(lock)
    pid = _dueno(lock)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, SALIDA_SIN_TURNO_GPU))
    try:
        juicio = puerta._pytest(['tests/test_x.py'], {}, tmp_path)
    finally:
        otra.communicate('', timeout=30)
    assert len(juicio['fallidas']) == 1 and pid in juicio['fallidas'][0]['motivo']
    assert puerta._informar(juicio, omitidas_cuentan=False) is False


def test_una_prueba_sin_marca_que_usa_cuda_falla_diciendolo():
    """106:RF-9 — gobierno en ejecución: la prueba sin la marca que reserva memoria de CUDA falla con su motivo; con la
    marca, o sin reservar nada, pasa."""
    torch = pytest.importorskip('torch')
    if not torch.cuda.is_available():
        pytest.fail('esta prueba necesita CUDA, como el resto de pruebas de GPU de la suite (102:RF-17)')

    class Item:
        nodeid = 'tests/test_x.py::test_entrena_por_src'

        def __init__(self, gpu):
            self.gpu = gpu

        def get_closest_marker(self, nombre):
            return object() if self.gpu else None

    def correr(item, reservar):
        gancho = conftest.pytest_runtest_call(item)
        next(gancho)
        x = torch.ones(1 << 20, device='cuda') if reservar else None
        try:
            gancho.send('hecho')
        except StopIteration as fin:
            return fin.value
        finally:
            del x

    with pytest.raises(pytest.fail.Exception, match=r'usa CUDA .* sin la marca gpu.*106:RF-9'):
        correr(Item(gpu=False), reservar=True)
    assert correr(Item(gpu=True), reservar=True) == 'hecho'
    assert correr(Item(gpu=False), reservar=False) == 'hecho'


def test_la_puerta_importa_el_codigo_del_arbol_que_juzga():
    """106:RF-11 — en un worktree con el .venv del principal, la puerta usa el src de su propio árbol."""
    import subprocess
    import sys

    raiz = Path(__file__).resolve().parents[1]
    codigo = ('import runpy, sys; runpy.run_path(sys.argv[1], run_name="no_main"); '
              'import convertersmartgrid.trabajadores_ml as m; print(m.__file__)')
    salida = subprocess.run([sys.executable, '-c', codigo, str(raiz / 'tools' / 'puerta_calidad.py')],
                            capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'PYTHONPATH': ''},
                            cwd=raiz.parent, check=True).stdout.strip()
    assert Path(salida).resolve().is_relative_to((raiz / 'src').resolve()), salida


def test_un_hijo_de_una_prueba_carga_el_src_de_este_arbol():
    """106:RF-12 — un hijo con el python del .venv, lanzado desde un worktree, carga el src de ese worktree y no el del
    árbol principal, al que apunta el .pth del paquete editable."""
    import subprocess
    import sys

    raiz = Path(__file__).resolve().parents[1]
    salida = subprocess.run([sys.executable, '-c', 'import convertersmartgrid; print(convertersmartgrid.__file__)'],
                            capture_output=True, text=True, encoding='utf-8', cwd=raiz.parent, check=True).stdout.strip()
    assert Path(salida).resolve().is_relative_to((raiz / 'src').resolve()), salida


def test_el_entorno_de_digsilent_no_hereda_otro_paquete(tmp_path, monkeypatch):
    """106:RF-14, 103:RF-6 — con un PYTHONPATH heredado que trae otro src del conversor, el entorno de DIgSILENT no lo
    pasa; las rutas heredadas sin el paquete siguen detrás."""
    from convertersmartgrid import powerfactory_env as pe

    otro_src = tmp_path / 'otro_arbol' / 'src'
    (otro_src / 'convertersmartgrid').mkdir(parents=True)
    (otro_src / 'convertersmartgrid' / '__init__.py').write_text('', encoding='utf-8')
    ajena = tmp_path / 'libreria_ajena'
    ajena.mkdir()
    monkeypatch.setenv('PYTHONPATH', os.pathsep.join([str(otro_src), str(ajena)]))
    api = tmp_path / 'PowerFactory 2021 SP3' / 'Python' / '3.9'
    otro = tmp_path / 'python_pf' / '3.9' / 'python.exe'
    for interprete in (otro, Path(__import__('sys').executable)):
        rutas = pe.pf_subprocess_env(api, interprete)['PYTHONPATH'].split(os.pathsep)
        assert str(otro_src) not in rutas and rutas[-1] == str(ajena) and rutas[0] == str(api)


def test_una_prueba_colgada_vuelca_su_pila():
    """106:RF-5 — ``faulthandler_timeout`` en la configuración de pytest: una prueba de más de 30 min deja su pila."""
    import tomllib

    datos = tomllib.loads((Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text(encoding='utf-8'))
    assert datos['tool']['pytest']['ini_options']['faulthandler_timeout'] == 1800


# 106:RF-16 y RF-17 — la suite no escribe en los datos del usuario (auditoría del 2026-11-13: 10 de las 85 carpetas del
# runtime real con líneas de pruebas en registros/web.log; y sin CSG_ASISTENTE_DATA ni CSG_TWIN_DATA, el almacén del
# asistente y el del gemelo caían en output/web/_asistente y _digital_twin del usuario, o en <runtime>/data/web/…).
import tempfile  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def _dentro_de_tmp(ruta: Path) -> bool:
    return Path(ruta).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())


def test_el_runtime_de_la_suite_es_de_la_sesion():
    """106:RF-16 — el runtime (y con él registros/web.log) es una carpeta temporal de la sesión, no el del usuario."""
    from convertersmartgrid.registro_rotativo import carpeta_de_registros

    runtime = Path(os.environ['CSG_RUNTIME_HOME'])
    assert _dentro_de_tmp(runtime), runtime
    assert carpeta_de_registros().resolve().is_relative_to(runtime.resolve())
    if conftest.RUNTIME_REAL is not None:
        assert not carpeta_de_registros().resolve().is_relative_to(conftest.RUNTIME_REAL.resolve())


def test_las_lineas_de_pruebas_en_un_registro_real_se_detectan(tmp_path):
    """106:RF-16 — solo cuenta lo que llegó durante la sesión y lleva rutas de pytest; lo de la web del usuario, no."""
    registro = tmp_path / 'registros' / 'web.log'
    registro.parent.mkdir()
    registro.write_text('2026-11-12 10:30 INFO arranque de la web\n', encoding='utf-8')
    tamanos = {registro: registro.stat().st_size}
    assert conftest.lineas_de_pruebas_en_registros(tamanos) == []
    with registro.open('a', encoding='utf-8') as f:
        f.write('2026-11-13 09:41 INFO la web del usuario sigue\n')
    assert conftest.lineas_de_pruebas_en_registros(tamanos) == []
    with registro.open('a', encoding='utf-8') as f:
        f.write("2026-11-13 09:42 ERROR retencion: [WinError 183] 'C:/Temp/pytest-of-x/pytest-1/a'\n")
    halladas = conftest.lineas_de_pruebas_en_registros(tamanos)
    assert len(halladas) == 1 and 'pytest-of-' in halladas[0]


def test_los_almacenes_del_asistente_y_del_gemelo_son_de_la_sesion():
    """106:RF-17 — sin fijar nada en la prueba, el almacén del asistente y el del gemelo caen en la carpeta de la
    sesión, nunca en output/web/_asistente ni en output/web/_digital_twin del checkout."""
    from convertersmartgrid.asistente import almacen
    from convertersmartgrid.digital_twin import buffer

    for raiz, heredado in ((almacen.raiz(), RAIZ / 'output' / 'web' / '_asistente'),
                           (buffer.raiz_buffer(), RAIZ / 'output' / 'web' / '_digital_twin')):
        assert _dentro_de_tmp(raiz), raiz
        assert not Path(raiz).resolve().is_relative_to(heredado.resolve()), raiz


def test_la_carpeta_de_datos_de_la_sesion_se_retira_aunque_su_registro_siga_abierto(tmp_path):
    """106:RF-17 — al terminar, la carpeta de la sesión se borra; antes se cierran los registros abiertos dentro (en
    Windows un fichero abierto no se borra), y si algo queda se avisa sin hacer fallar la suite."""
    import logging

    carpeta = tmp_path / 'csg-suite-x'
    (carpeta / 'runtime' / 'registros').mkdir(parents=True)
    manejador = logging.FileHandler(carpeta / 'runtime' / 'registros' / 'web.log', encoding='utf-8')
    registrador = logging.getLogger('prueba_106_rf17')
    registrador.addHandler(manejador)
    registrador.warning('una línea')
    assert conftest.retirar_sesion_de_datos(carpeta) is None
    assert not carpeta.exists() and manejador not in registrador.handlers


def test_si_la_carpeta_no_se_puede_borrar_se_avisa(tmp_path, monkeypatch):
    """106:RF-17 — si queda algo, el aviso dice qué carpeta borrar a mano."""
    import shutil

    carpeta = tmp_path / 'csg-suite-y'
    carpeta.mkdir()
    monkeypatch.setattr(shutil, 'rmtree', lambda *a, **k: None)
    aviso = conftest.retirar_sesion_de_datos(carpeta)
    assert aviso and str(carpeta.resolve()) in aviso and '106:RF-17' in aviso


def test_un_trabajador_hereda_la_carpeta_de_datos_y_no_crea_otra():
    """106:RF-17 — con xdist cada trabajador importa el conftest: hereda la carpeta del controlador por su variable y
    no crea una suya, que nadie borraría."""
    import subprocess
    import sys

    assert os.environ[conftest.VARIABLE_SESION_DE_DATOS] == str(conftest._SESION_DE_DATOS)
    codigo = ('import sys; sys.path.insert(0, "tests"); import conftest; '
              'print(conftest._SESION_PROPIA, conftest._SESION_DE_DATOS)')
    salida = subprocess.run([sys.executable, '-c', codigo], cwd=RAIZ, env=dict(os.environ), capture_output=True,
                            text=True, timeout=120)
    assert salida.returncode == 0, salida.stderr
    propia, carpeta = salida.stdout.strip().splitlines()[-1].split(' ', 1)
    assert propia == 'False' and Path(carpeta) == conftest._SESION_DE_DATOS
