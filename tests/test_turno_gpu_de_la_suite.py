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
    from convertersmartgrid.aplicacion.training_coordinator import ruta_guardia_gpu

    return ruta_guardia_gpu()


def test_un_fixture_de_modulo_no_ve_la_guardia_de_la_maquina(ruta_vista_por_un_fixture_de_modulo):
    """106:RF-1 — el caso de la puerta colgada: antes, el fixture de módulo resolvía la guardia real de la máquina."""
    assert Path(ruta_vista_por_un_fixture_de_modulo) != Path(conftest.GUARDIA_GPU_DE_LA_MAQUINA)
    assert 'csg-gpu-sesion-' in str(ruta_vista_por_un_fixture_de_modulo)


def test_la_espera_dice_quien_tiene_la_gpu_y_vence_con_su_dueno(tmp_path):
    """106:RF-2, 106:RF-3 — con otro proceso en el turno, se avisa de su PID y su orden; al vencer, error con ese dueño."""
    from convertersmartgrid.aplicacion.trabajadores_ml import turno_gpu_con_plazo

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
    assert pid in str(exc.value) and 'otra-sesion' in str(exc.value) and 'GPU ocupada' in str(exc.value)
    assert len(avisos) == 2 and all(pid in a and 'otra-sesion' in a for a in avisos)


def test_cuando_el_otro_suelta_la_gpu_la_toma(tmp_path):
    """106:RF-2 — el turno libre se toma, queda a nombre de este proceso y se suelta al salir."""
    import json

    from convertersmartgrid.aplicacion.trabajadores_ml import turno_gpu_con_plazo

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
    monkeypatch.setattr(conftest, '_registro_turno', [], raising=False)
    monkeypatch.delenv('CSG_GPU_REGISTRO_SUITE', raising=False)
    return lock


def test_la_sesion_sin_gpu_libre_sale_sin_veredicto(tmp_path, monkeypatch):
    """106:RF-4 — si el plazo vence, pytest sale con SALIDA_SIN_TURNO_GPU y el dueño; no omite ni juzga nada."""
    from convertersmartgrid.aplicacion.trabajadores_ml import SALIDA_SIN_TURNO_GPU

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
    from convertersmartgrid.aplicacion.trabajadores_ml import SALIDA_SIN_TURNO_GPU

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
        # En GitHub Actions (sin GPU) el conftest la omite con su motivo; en local, SinGPU es un fallo (102:RF-17).
        from convertersmartgrid.aplicacion.training_coordinator import SinGPU
        raise SinGPU('esta prueba necesita CUDA, como el resto de pruebas de GPU de la suite')

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
              'import convertersmartgrid.aplicacion.trabajadores_ml as m; print(m.__file__)')
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
    from convertersmartgrid.adaptadores import powerfactory_env as pe

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


def test_el_guion_de_digsilent_importa_el_paquete_de_la_web(tmp_path, monkeypatch):
    """106:RF-27 — el 26-11, el `.pth` editable del `.venv` apuntaba desde el 23-11 a `D:/converter/wt_integra/src`:
    `powerfactory_acceptance.py`, en su propio proceso, importaba ese código viejo y la importación de PE106 desde la
    web cayó con «eliminar_versiones_anteriores() takes 3 positional arguments but 4 were given». Con el mismo
    intérprete, el entorno lleva la carpeta del paquete de la web, detrás de la API y delante de lo heredado."""
    from convertersmartgrid.adaptadores import powerfactory_env as pe

    ajena = tmp_path / 'libreria_ajena'
    ajena.mkdir()
    monkeypatch.setenv('PYTHONPATH', str(ajena))
    api = tmp_path / 'PowerFactory 2024' / 'Python' / '3.12'
    rutas = pe.pf_subprocess_env(api, Path(__import__('sys').executable))['PYTHONPATH'].split(os.pathsep)
    assert rutas[:2] == [str(api), str(pe.carpeta_del_paquete())], rutas
    assert rutas[-1] == str(ajena)


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
    from convertersmartgrid.adaptadores.registro_rotativo import carpeta_de_registros

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
    from convertersmartgrid.aplicacion.asistente import almacen
    from convertersmartgrid.adaptadores.digital_twin import buffer

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


def test_cada_trabajador_de_xdist_tiene_su_runtime_y_sus_almacenes():
    """102:RF-5, 106:RF-17 — un trabajador de xdist no comparte con otro el runtime ni los almacenes del asistente y
    del gemelo: los suyos van en la carpeta de la sesión, bajo su nombre. Lo que fijó otro (no la ruta de la sesión) se
    respeta. Ensayo con -n 2 del 2026-11-13: dos trabajadores en el mismo almacén del asistente contaron 17 órdenes
    donde había 8."""
    import subprocess
    import sys

    sesion = conftest._SESION_DE_DATOS
    fijada = str(sesion / 'otra_del_usuario')
    entorno = {**os.environ, 'PYTEST_XDIST_WORKER': 'gw7', 'CSG_RUNTIME_HOME': str(sesion / 'runtime'),
               'CSG_ASISTENTE_DATA': str(sesion / '_asistente'), 'CSG_TWIN_DATA': fijada}
    codigo = ('import os, sys; sys.path.insert(0, "tests"); import conftest; '
              'print("|".join(os.environ[v] for v in ("CSG_RUNTIME_HOME", "CSG_ASISTENTE_DATA", "CSG_TWIN_DATA")))')
    salida = subprocess.run([sys.executable, '-c', codigo], cwd=RAIZ, env=entorno, capture_output=True, text=True,
                            timeout=120)
    assert salida.returncode == 0, salida.stderr
    runtime, asistente, gemelo = salida.stdout.strip().splitlines()[-1].split('|')
    assert Path(runtime) == sesion / 'gw7' / 'runtime' and Path(asistente) == sesion / 'gw7' / '_asistente'
    assert gemelo == fijada


def test_sin_gpu_la_prueba_de_cuda_se_omite_en_github_y_falla_en_local():
    """102:RF-17 — en GitHub Actions no hay GPU: la prueba que necesita CUDA queda omitida con su motivo, como el resto de
    pruebas de GPU; en local, sin la variable de CI, sigue siendo un fallo. Actions, run 43815847560 (15-11)."""
    import subprocess
    import sys

    raiz = Path(__file__).resolve().parents[1]
    nodo = 'tests/test_turno_gpu_de_la_suite.py::test_una_prueba_sin_marca_que_usa_cuda_falla_diciendolo'

    def correr(con_ci: bool) -> str:
        entorno = {k: v for k, v in os.environ.items() if k != conftest.VARIABLE_CI_SIN_GPU}
        # En Windows una variable vacía no llega al proceso hijo, que vería la GPU: «-1» la oculta en todos los
        # sistemas (como corrida_e6 en el carril sin GPU).
        entorno['CUDA_VISIBLE_DEVICES'] = '-1'
        if con_ci:
            entorno[conftest.VARIABLE_CI_SIN_GPU] = '1'
        r = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider', '-q', '-rs', nodo], cwd=raiz,
                           env=entorno, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
        return r.stdout + r.stderr

    en_github = correr(con_ci=True)
    assert '1 skipped' in en_github and 'GitHub Actions no la tiene' in en_github, \
        f'en GitHub sin GPU tiene que quedar omitida con su motivo:\n{en_github[-1500:]}'
    en_local = correr(con_ci=False)
    assert '1 failed' in en_local, f'en local sin GPU tiene que fallar, nunca omitirse:\n{en_local[-1500:]}'


# 106:RF-22 a RF-24 (MEJ28, 2026-11-21) — la suite tomaba el turno al empezar y lo guardaba 45-50 min con la GPU al 0 %:
# casi todo lo que corría no la usaba, y los entrenamientos de la cola de GPU esperaban horas.
_ENTRENAMIENTO = '''import sys, time
sys.path.insert(0, sys.argv[3])
from convertersmartgrid.aplicacion.training_coordinator import BloqueoGPU
b = BloqueoGPU(sys.argv[1], 'entrenamiento-de-la-cola')
b.__enter__()
print('LOCKED', flush=True)
time.sleep(float(sys.argv[2]))
b.__exit__(None, None, None)
'''
#: Se recoge primero y usa la GPU: la suite tiene que dejarla para el final.
_PRUEBA_DE_GPU = '''import json, os
from pathlib import Path


def test_a_con_la_gpu():
    dueno = json.loads(Path(os.environ['MEJ28_MAQUINA']).read_text(encoding='utf-8'))
    assert dueno['model'] == 'suite-pytest' and dueno['pid'] == os.getpid(), dueno
'''
#: No nombra nada de la GPU (106:RF-6): corre sin el turno, y en su tiempo un entrenamiento toma la máquina.
_PRUEBA_DEL_RESTO = '''import os, subprocess, sys
from pathlib import Path


def test_b_el_resto():
    maquina = Path(os.environ['MEJ28_MAQUINA'])
    assert not maquina.exists(), 'la suite tiene el turno mientras corre una prueba que no lo usa'
    hijo = subprocess.Popen([sys.executable, os.environ['MEJ28_ENTRENAMIENTO'], str(maquina), '3',
                             os.environ['MEJ28_SRC']], stdout=subprocess.PIPE, text=True)
    assert hijo.stdout.readline().strip() == 'LOCKED', 'el entrenamiento no pudo tomar la máquina'
'''
#: Este equipo puede no tener CUDA (o tenerla oculta): la sesión hija hace como si la tuviera.
_CUDA_SIMULADA = '''import conftest

conftest._hay_cuda = lambda: True
'''


def _sesion_hija(tmp_path, *ficheros, espera_s='120'):
    """Una sesión de pytest con el conftest de la suite (como complemento) sobre ficheros de ``tmp_path``."""
    import subprocess
    import sys

    maquina = tmp_path / 'maquina.lock'
    (tmp_path / 'entrenamiento.py').write_text(_ENTRENAMIENTO, encoding='utf-8')
    (tmp_path / 'cuda_simulada.py').write_text(_CUDA_SIMULADA, encoding='utf-8')
    (tmp_path / 'test_a_gpu.py').write_text(_PRUEBA_DE_GPU, encoding='utf-8')
    (tmp_path / 'test_b_resto.py').write_text(_PRUEBA_DEL_RESTO, encoding='utf-8')
    entorno = {k: v for k, v in os.environ.items()
               if k not in ('PYTEST_CURRENT_TEST', 'PYTEST_XDIST_WORKER', 'CSG_GPU_REGISTRO_SUITE')}
    entorno.update({'CSG_ML_GPU_LOCK': str(maquina), 'MEJ28_MAQUINA': str(maquina),
                    'MEJ28_ENTRENAMIENTO': str(tmp_path / 'entrenamiento.py'), 'MEJ28_SRC': str(RAIZ / 'src'),
                    conftest.VARIABLE_ESPERA_GPU_SUITE: espera_s,
                    'PYTHONPATH': os.pathsep.join([str(RAIZ / 'src'), str(RAIZ / 'tests'), str(tmp_path)])})
    r = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider', '-p', 'no:randomly', '-p',
                        'conftest', '-p', 'cuda_simulada', '-v', '-rfs', '--rootdir', str(tmp_path),
                        *[str(tmp_path / f) for f in ficheros]],
                       cwd=tmp_path, env=entorno, capture_output=True, text=True, encoding='utf-8', check=False,
                       errors='replace', timeout=600)
    return r, maquina


def test_la_suite_toma_el_turno_solo_para_sus_pruebas_de_gpu_y_un_entrenamiento_lo_usa_antes(tmp_path):
    """106:RF-22, 106:RF-23, 106:RF-24 — con la de GPU recogida primero, la sesión corre antes el resto sin el turno; en
    ese tiempo un entrenamiento toma la máquina; la suite lo espera al llegar a la suya, lo toma, lo suelta al acabar y
    deja dicho cuándo pidió, obtuvo y soltó."""
    import json

    r, maquina = _sesion_hija(tmp_path, 'test_a_gpu.py', 'test_b_resto.py')
    salida = r.stdout + r.stderr
    assert r.returncode == 0, salida[-3000:]
    orden = [m for m in re.findall(r'(test_[ab]_\w+) PASSED', salida)]
    assert orden == ['test_b_el_resto', 'test_a_con_la_gpu'], salida[-3000:]
    registro = maquina.with_name(maquina.name + '.suite.jsonl')
    filas = [json.loads(linea) for linea in registro.read_text(encoding='utf-8').splitlines()]
    assert [f['suceso'] for f in filas] == ['pidió', 'obtuvo', 'soltó'], filas
    assert filas[1]['espera_s'] > 0, f'la suite no esperó al entrenamiento: {filas}'
    assert all(f['hora'] and f['pid'] for f in filas)
    assert 'turno de GPU de la suite' in salida and not maquina.exists()


def test_las_pruebas_de_gpu_se_recogen_al_final_y_siempre_en_el_mismo_orden():
    """106:RF-22 — el orden de la recogida deja la GPU al final, sin desordenar cada grupo, y es el mismo cada vez
    (los trabajadores de xdist del reparto de 102:RF-5 tienen que recoger lo mismo)."""
    import subprocess
    import sys

    ficheros = ['tests/test_turno_gpu_de_la_suite.py', 'tests/test_textos_sin_requisitos.py']
    assert conftest.usa_gpu(RAIZ / ficheros[0]) and not conftest.usa_gpu(RAIZ / ficheros[1])

    def recoger() -> list[str]:
        # Con PYTEST_CURRENT_TEST heredado la sesión hija no pide la GPU de la máquina (RF-1): solo recoge.
        r = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider', '-p', 'no:randomly',
                            '--collect-only', '-q', *ficheros], cwd=RAIZ, capture_output=True, check=False,
                           text=True, encoding='utf-8', errors='replace', timeout=600)
        assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
        return [linea for linea in r.stdout.splitlines() if '::' in linea]

    ids = recoger()
    de_gpu = [i for i in ids if i.startswith(ficheros[0])]
    resto = [i for i in ids if i.startswith(ficheros[1])]
    assert de_gpu and resto and ids == resto + de_gpu, ids[:5]
    assert recoger() == ids


def test_el_registro_dice_cuando_pidio_obtuvo_y_solto_o_vencio_su_plazo(tmp_path, monkeypatch):
    """106:RF-24 — cada suceso del turno de la suite queda en su registro, con su hora y su PID; también el plazo
    vencido, con el dueño de la GPU."""
    import json

    lock = _maquina(tmp_path, monkeypatch)
    registro = lock.with_name(lock.name + '.suite.jsonl')
    conftest.tomar_turno_si_hace_falta([_Item(gpu=True)])
    conftest.pytest_sessionfinish(None, 0)
    assert registro.exists(), 'la suite no dejó registro de su turno'
    filas = [json.loads(linea) for linea in registro.read_text(encoding='utf-8').splitlines()]
    assert [f['suceso'] for f in filas] == ['pidió', 'obtuvo', 'soltó']
    assert all(f['pid'] == os.getpid() for f in filas) and 'con_turno_s' in filas[2]

    monkeypatch.setenv(conftest.VARIABLE_ESPERA_GPU_SUITE, '0')
    otra = _guardia_en_otro_proceso(lock)
    pid = _dueno(lock)
    try:
        with pytest.raises(pytest.exit.Exception):
            conftest.tomar_turno_si_hace_falta([_Item(gpu=True)])
    finally:
        otra.communicate('', timeout=30)
    filas = [json.loads(linea) for linea in registro.read_text(encoding='utf-8').splitlines()]
    assert [f['suceso'] for f in filas[-2:]] == ['pidió', 'sin turno'] and pid in filas[-1]['motivo']


def test_un_entrenamiento_con_plazo_espera_su_turno(tmp_path, monkeypatch):
    """106:RF-21 — con `CSG_GPU_ESPERA_S`, `turno_gpu` espera a que el otro suelte la GPU y la toma; sin ella, cae."""
    import json

    from convertersmartgrid.aplicacion.trabajadores_ml import turno_gpu

    lock = tmp_path / 'gpu.lock'
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(lock))
    monkeypatch.delenv('CSG_GPU_PARENT_TOKEN', raising=False)
    monkeypatch.delenv('CSG_GPU_ESPERA_S', raising=False)
    otra = _guardia_en_otro_proceso(lock, segundos=3.0)
    with pytest.raises(RuntimeError, match='GPU ocupada'):
        with turno_gpu('entrenamiento-sin-plazo'):
            pass
    monkeypatch.setenv('CSG_GPU_ESPERA_S', '60')
    with turno_gpu('entrenamiento-con-plazo'):
        dueno = json.loads(lock.read_text(encoding='utf-8'))
        assert dueno['pid'] == os.getpid() and dueno['model'] == 'entrenamiento-con-plazo'
    otra.wait(30)
    assert not lock.exists()
