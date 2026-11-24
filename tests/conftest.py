"""Shared fixtures for TXT integration tests.

Feeders and codes come only from the loaded TXT set — no company-specific names
are required (IN191/TA191 etc. are optional samples when present).
"""

from __future__ import annotations

from contextlib import contextmanager
import os
import tempfile
from pathlib import Path

import pytest

from csg_paths import SKIP_MSG, resolve_txt_paths

# 106:RF-16 y RF-17: antes que cualquier import de la web o del asistente, el runtime y los almacenes de la suite son de
# la sesión. Auditoría del 2026-11-13: las pruebas del lanzador colgaban del registro raíz un manejador sobre
# <runtime>/registros/web.log del runtime real, y 10 de sus 85 carpetas tenían líneas de pruebas; y sin CSG_ASISTENTE_DATA
# ni CSG_TWIN_DATA, almacen.raiz() y el búfer del gemelo caían en output/web/_asistente (3,8 GB) y _digital_twin (1,1 GB)
# del usuario, o en <runtime>/data/web/… desde un worktree. Lo que una prueba fije por su cuenta (monkeypatch) manda.
# La carpeta la crea quien no la hereda y la borra al final esa misma sesión (avisando si no puede): cada suite
# dejaba en %TEMP% su runtime y sus almacenes, que el entrenamiento del gemelo llena. Los trabajadores de xdist la
# heredan por VARIABLE_SESION_DE_DATOS y no crean otra.
VARIABLE_SESION_DE_DATOS = 'CSG_SUITE_DATOS'
_SESION_PROPIA = not os.environ.get(VARIABLE_SESION_DE_DATOS)
if _SESION_PROPIA:
    os.environ[VARIABLE_SESION_DE_DATOS] = tempfile.mkdtemp(prefix='csg-suite-')
_SESION_DE_DATOS = Path(os.environ[VARIABLE_SESION_DE_DATOS])
RUNTIME_REAL = None
if not os.environ.get('CSG_RUNTIME_HOME'):
    from convertersmartgrid.dominio.runtime_paths import rutas_runtime as _rutas_runtime

    RUNTIME_REAL = _rutas_runtime().runtime
    os.environ['CSG_RUNTIME_HOME'] = str(_SESION_DE_DATOS / 'runtime')
for _variable, _carpeta in (('CSG_ASISTENTE_DATA', '_asistente'), ('CSG_TWIN_DATA', '_digital_twin')):
    if not os.environ.get(_variable):
        os.environ[_variable] = str(_SESION_DE_DATOS / _carpeta)
# 102:RF-5 (MEJ15-T20): un trabajador de xdist hereda del controlador el runtime y los dos almacenes de la sesión, y dos
# trabajadores escribían a la vez en el mismo almacén del asistente: en el ensayo con -n 2 del 2026-11-13,
# test_final_entrena_con_todas_las_que_pueden contó 17 órdenes donde esperaba 8. Cada trabajador tiene los suyos dentro
# de la carpeta de la sesión, que se borra con ella, como una sesión sola; una ruta que fijó otro (no la de la sesión) se
# respeta.
TRABAJADOR_XDIST = os.environ.get('PYTEST_XDIST_WORKER', '')
if TRABAJADOR_XDIST:
    for _variable, _carpeta in (('CSG_RUNTIME_HOME', 'runtime'), ('CSG_ASISTENTE_DATA', '_asistente'),
                                ('CSG_TWIN_DATA', '_digital_twin')):
        if os.environ.get(_variable) == str(_SESION_DE_DATOS / _carpeta):
            os.environ[_variable] = str(_SESION_DE_DATOS / TRABAJADOR_XDIST / _carpeta)
_TAMANOS_DE_REGISTROS: dict[Path, int] = {}
if RUNTIME_REAL is not None and RUNTIME_REAL.parent.is_dir():
    for _registro in RUNTIME_REAL.parent.glob('*/registros/*.log'):
        try:
            _TAMANOS_DE_REGISTROS[_registro] = _registro.stat().st_size
        except OSError:
            pass


def lineas_de_pruebas_en_registros(tamanos: dict) -> list[str]:
    """106:RF-16: las líneas con rutas de pytest que llegaron durante la sesión a un registro real de la web."""
    halladas = []
    for ruta, antes in tamanos.items():
        try:
            if ruta.stat().st_size <= antes:
                continue
            with ruta.open('rb') as f:
                f.seek(antes)
                nuevo = f.read().decode('utf-8', 'replace')
        except OSError:
            continue
        halladas += [f'{ruta}: {linea[:160]}' for linea in nuevo.splitlines() if 'pytest-of-' in linea]
    return halladas


from convertersmartgrid.dominio import sesion_web
from convertersmartgrid.dominio.compat_gpu import fijar_dll_nvidia
from convertersmartgrid.dominio.naming import feeder_short_name

# 106:RF-18: antes de _hay_cuda y de cualquier torch.cuda de la sesión. Con el controlador NVIDIA 560.94, el primer
# cuInit dejaba un hilo en nvdxgdmal64.dll ya descargada y pytest moría con 0xC0000005 a los ~90 s, a mitad de la suite
# (D:/csg/AV_diagnostico). Importar el paquete ya lo deja listo para el primer import torch; aquí se hace explícito.
fijar_dll_nvidia()

# Aquí y no en un fixture: hay módulos que crean la aplicación al importarse o con fixtures de
# módulo. La puerta de la web se prueba en test_seguridad_web.py (086:RF-17 a RF-20), que la
# enciende; las demás prueban las rutas. Y la sesión real de la máquina no se toca nunca.
sesion_web.EXIGIR_SEGURIDAD = False
os.environ[sesion_web.VARIABLE_CARPETA] = tempfile.mkdtemp(prefix='csg-sesiones-pruebas-')
os.environ.pop(sesion_web.VARIABLE_PUERTO, None)

# 106:RF-1: la GPU de la máquina se pide una vez por sesión (ver pytest_sessionstart); dentro, la guardia es de la
# sesión. Aquí y no en un fixture: con un fixture de módulo, test_digital_twin_oraculo tomaba la guardia real antes que
# el fixture por prueba de 102:RF-22, y la puerta del 2026-11-12 esperó 40 min en silencio a la T7.
from convertersmartgrid.aplicacion.training_coordinator import ruta_guardia_gpu as _ruta_guardia_gpu

# 106:RF-12: los hijos (guiones de tools/, --help, lanzadores) cargan el src de ESTE árbol. pytest pone «pythonpath =
# ["src"]» solo en su propio sys.path; un hijo con el python del .venv cargaba el src del árbol principal por el .pth
# del paquete editable, y una puerta de rama podía dar verde con código que no era el suyo (auditoría, 2026-11-12).
SRC_DEL_ARBOL = Path(__file__).resolve().parents[1] / 'src'
os.environ['PYTHONPATH'] = os.pathsep.join(
    [str(SRC_DEL_ARBOL)] + [p for p in os.environ.get('PYTHONPATH', '').split(os.pathsep)
                            if p and Path(p).resolve() != SRC_DEL_ARBOL.resolve()])

GUARDIA_GPU_DE_LA_MAQUINA = _ruta_guardia_gpu()
os.environ['CSG_ML_GPU_LOCK'] = str(Path(tempfile.mkdtemp(prefix='csg-gpu-sesion-')) / 'gpu.lock')
#: Segundos que la suite espera la GPU de la máquina antes de salir sin veredicto (106:RF-3).
VARIABLE_ESPERA_GPU_SUITE = 'CSG_GPU_ESPERA_SUITE_S'
ESPERA_GPU_SUITE_S = 7200.0
#: Lo que delata un módulo de pruebas que usa la GPU (106:RF-6), sin distinguir mayúsculas: torch, CUDA o la GPU
#: (``turno_gpu``, ``*_gpu``). Con «CUDA» en mayúsculas, test_pronostico_demanda se quedaba fuera.
SEÑALES_GPU = ('torch', 'cuda', 'gpu')
_turno_de_la_sesion: list = []
_usa_gpu_cache: dict = {}


def _hay_cuda() -> bool:
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())


def usa_gpu(ruta) -> bool:
    """106:RF-6: el módulo de pruebas usa la GPU si su texto trae una de :data:`SEÑALES_GPU`."""
    ruta = Path(ruta)
    if ruta not in _usa_gpu_cache:
        try:
            texto = ruta.read_text(encoding='utf-8')
        except OSError:
            texto = ''
        texto = texto.lower()
        _usa_gpu_cache[ruta] = any(s in texto for s in SEÑALES_GPU)
    return _usa_gpu_cache[ruta]


#: 102:RF-5 (aclaración del 2026-11-15, PUERTA-XDIST): los recursos que no admiten paralelo. Con la suite repartida
#: (tools/puerta_calidad.py, SELECCION_*), las pruebas «serie» corren una tras otra en una sesión aparte, como hoy, a la
#: vez que el resto; las «a_solas», al final y sin nada más. La GPU va en «serie» por su marca ``gpu`` (106:RF-6), con su
#: turno de la máquina (106:RF-1), que solo pide esa sesión.
RECURSOS_EN_SERIE = {
    'sqlserver': ('restauran la copia real de VNR-GIS (CSG_VNR_BAK) en la instancia de SQL Server de la máquina: '
                  'sqlserver_vnr.restaurar hace DROP y RESTORE DATABASE de una base con nombre fijo por copia, y dos a '
                  'la vez se pisan'),
    'a_solas': ('miden tiempos con la CPU, o comparan lo generado con el árbol entero: otra sesión a la vez cambia lo '
                'que miden'),
}
#: Fichero de pruebas → (recurso, motivo). Revisado el 2026-11-15 sobre tests/ entero; lo que NO está y por qué, en
#: specs/102-puerta-de-calidad-ci-cd/plan.md (DIgSILENT, Word/COM, puertos, candados y Access no lo necesitan).
EN_SERIE: dict[str, tuple[str, str]] = {
    'test_vnr_sqlserver.py': ('sqlserver', 'su prueba con CSG_VNR_BAK llama a sv.cargar_copia: restaura la copia real'),
    'test_asistente_vocabulario.py': ('sqlserver', 'test_vnr_real llama a sv.cargar_copia(CSG_VNR_BAK): restaura la copia'),
    'test_flexibility_and_scale.py': ('a_solas', ('compara el coste por tramo de 4N frente a N (cociente < 8 y por tramo '
                                                  '< 2×): ya tumbó puertas en un solo proceso (fallos_de_puerta.tsv)')),
    'test_performance_budget.py': ('a_solas', 'presupuesto absoluto de segundos del alimentador mayor y cociente de 4N'),
    'test_arquitectura_generada.py': ('a_solas', ('compara el catálogo generado con el árbol entero; falló en los dos '
                                                  'ensayos de la 106:RF-16 con -n 2 (2026-11-14)')),
    'test_trazabilidad_specs.py': ('a_solas', ('compara specs/README.md con el árbol entero; falló en los dos ensayos de '
                                              'la 106:RF-16 con -n 2 (2026-11-14)')),
}


def pytest_configure(config):
    config.addinivalue_line('markers', 'serie: no admite paralelo; la suite repartida la corre aparte, una tras otra '
                                       '(102:RF-5, EN_SERIE de tests/conftest.py)')
    config.addinivalue_line('markers', 'a_solas: la suite repartida la corre al final, sin nada más (102:RF-5)')


def marcar_en_serie(items) -> None:
    """102:RF-5: las marcas ``serie`` y ``a_solas`` salen de :data:`EN_SERIE`, por fichero, como la ``gpu`` (106:RF-6)."""
    for item in items:
        fila = EN_SERIE.get(Path(item.path).name)
        if fila:
            item.add_marker(pytest.mark.serie)
            if fila[0] == 'a_solas':
                item.add_marker(pytest.mark.a_solas)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    """106:RF-6: la marca ``gpu`` se pone sola; ninguna prueba depende de que alguien se acuerde de marcarla.

    106:RF-22: y las de GPU van al final del recorrido. Va el último (``trylast``): después del orden por fixtures de
    pytest y de cualquier complemento que baraje, para que el turno de la máquina se tome una sola vez y tarde.
    """
    for item in items:
        if usa_gpu(item.path):
            item.add_marker(pytest.mark.gpu)
    marcar_en_serie(items)
    items[:] = gpu_al_final(items)


def _es_de_gpu(item) -> bool:
    return item is not None and item.get_closest_marker('gpu') is not None


def gpu_al_final(items) -> list:
    """106:RF-22: las pruebas de GPU al final, sin cambiar el orden dentro de cada grupo.

    Es una partición estable: el mismo recorrido da siempre el mismo orden, así que los trabajadores de xdist recogen
    lo mismo (102:RF-5), y la marca va por módulo (RF-6), así que sus fixtures de módulo no se parten. El 2026-11-21
    la suite tomaba el turno al empezar y lo guardaba 45-50 min con la GPU al 0 %: casi todo lo que corría no la usaba.
    """
    return [i for i in items if not _es_de_gpu(i)] + [i for i in items if _es_de_gpu(i)]


def tomar_turno_si_hace_falta(items) -> None:
    """106:RF-1 a RF-4, RF-7: el turno común, solo si alguna prueba elegida usa la GPU, esperando con plazo.

    Con otro proceso en la GPU (un entrenamiento de tools/, otra puerta), las pruebas de CUDA fallaban por memoria
    (suite de 10a80812: 61 de 62 fallidas, «CUDA error: out of memory»). Una puerta sin pruebas de GPU no espera
    (102:RF-18). Si el plazo vence, pytest sale con :data:`SALIDA_SIN_TURNO_GPU` y el dueño, sin juzgar ni omitir
    nada. Una sesión de pytest lanzada por una prueba no lo pide: es de su padre.
    """
    import sys
    import time

    if (_turno_de_la_sesion or os.environ.get('PYTEST_CURRENT_TEST')
            or not any(i.get_closest_marker('gpu') for i in items) or not _hay_cuda()):
        return
    from convertersmartgrid.aplicacion.trabajadores_ml import SALIDA_SIN_TURNO_GPU, turno_gpu_con_plazo

    limite = float(os.environ.get(VARIABLE_ESPERA_GPU_SUITE, ESPERA_GPU_SUITE_S))
    turno = turno_gpu_con_plazo('suite-pytest', ruta=GUARDIA_GPU_DE_LA_MAQUINA, limite_s=limite,
                                avisar=lambda t: print(t, file=sys.__stderr__, flush=True))
    registrar_turno('pidió', plazo_s=limite)
    inicio = time.monotonic()
    try:
        turno.__enter__()
    except RuntimeError as exc:
        registrar_turno('sin turno', espera_s=round(time.monotonic() - inicio, 1), motivo=str(exc))
        pytest.exit(f'La suite no puede juzgar: {exc}', returncode=SALIDA_SIN_TURNO_GPU)
    registrar_turno('obtuvo', espera_s=round(time.monotonic() - inicio, 1))
    _turno_de_la_sesion.append((turno, time.monotonic()))


def soltar_turno() -> None:
    """106:RF-22, RF-24: suelta el turno de la máquina, si lo tiene, y deja dicho cuánto lo tuvo."""
    import time

    while _turno_de_la_sesion:
        turno, desde = _turno_de_la_sesion.pop()
        turno.__exit__(None, None, None)
        registrar_turno('soltó', con_turno_s=round(time.monotonic() - desde, 1))


#: 106:RF-24: lo que la sesión hizo con el turno de la máquina, en orden (lo resume el informe del final).
_registro_turno: list[dict] = []
#: Dónde queda el registro del turno de la suite (una línea JSON por suceso); sin la variable, junto a la guardia.
VARIABLE_REGISTRO_TURNO = 'CSG_GPU_REGISTRO_SUITE'


def ruta_registro_turno() -> Path:
    """106:RF-24: el fichero del registro: ``CSG_GPU_REGISTRO_SUITE`` o, sin ella, al lado de la guardia de la máquina."""
    fijada = os.environ.get(VARIABLE_REGISTRO_TURNO)
    guardia = Path(GUARDIA_GPU_DE_LA_MAQUINA)
    return Path(fijada) if fijada else guardia.with_name(guardia.name + '.suite.jsonl')


def registrar_turno(suceso: str, **datos) -> dict:
    """106:RF-24: cuándo pidió, obtuvo y soltó la suite el turno de GPU (o vio vencer su plazo), con su hora y su PID.

    Va al error estándar del proceso, al informe del final de la sesión y, una línea JSON por suceso, al fichero de
    :func:`ruta_registro_turno`, que puede leer quien espera la GPU. Si ese fichero no se puede escribir, la suite sigue.
    """
    import datetime as dt
    import json
    import sys

    fila = {'suceso': suceso, 'hora': dt.datetime.now().astimezone().isoformat(timespec='seconds'), 'pid': os.getpid(), **datos}
    _registro_turno.append(fila)
    extra = ', '.join(f'{k}={v}' for k, v in datos.items())
    print(f'[turno de GPU de la suite] {fila["hora"]} {suceso}' + (f' ({extra})' if extra else ''),
          file=sys.__stderr__, flush=True)
    try:
        with ruta_registro_turno().open('a', encoding='utf-8') as f:
            f.write(json.dumps(fila, ensure_ascii=False) + '\n')
    except OSError as exc:  # justificado: el registro es un aviso; sin el fichero la suite juzga igual y lo dice
        print(f'[turno de GPU de la suite] no se pudo escribir el registro: {exc}', file=sys.__stderr__, flush=True)
    return fila


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """106:RF-22, RF-23: el turno de la máquina solo mientras corren pruebas de GPU.

    Se pide justo antes de la primera de GPU (con su plazo y sus avisos, RF-3, RF-4) y se suelta al terminar la última
    del tramo, con sus fixtures ya cerrados (``nextitem`` sin la marca, o el fin de la sesión). Mientras corre el resto,
    un entrenamiento puede tomar la GPU; la suite lo espera cuando llega a las suyas.
    """
    if _es_de_gpu(item):
        tomar_turno_si_hace_falta([item])
    try:
        return (yield)
    finally:
        if not _es_de_gpu(nextitem):
            soltar_turno()


def pytest_terminal_summary(terminalreporter):
    """106:RF-24: el resumen del turno de GPU de la sesión, en la salida que guarda la puerta."""
    if not _registro_turno:
        return
    terminalreporter.section('turno de GPU de la suite')
    for fila in _registro_turno:
        extra = ', '.join(f'{k}={v}' for k, v in fila.items() if k not in ('suceso', 'hora', 'pid'))
        terminalreporter.write_line(f'{fila["hora"]} PID {fila["pid"]} {fila["suceso"]}'
                                    + (f' ({extra})' if extra else ''))


def _cuda_iniciada() -> bool:
    import sys

    torch = sys.modules.get('torch')
    return bool(torch is not None and torch.cuda.is_initialized())


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """106:RF-9: gobierno en ejecución: una prueba sin la marca ``gpu`` que reserva memoria de CUDA falla diciéndolo.

    El texto del módulo (RF-6) no ve el uso indirecto, una prueba que entrena por ``src`` sin nombrar torch; sin el
    turno de RF-1 esa prueba volvería a chocar con un entrenamiento. No mira lo que reserva un proceso hijo.
    """
    import sys

    vigilar = item.get_closest_marker('gpu') is None
    antes = _cuda_iniciada()
    base = 0
    if vigilar and antes:
        torch = sys.modules['torch']
        torch.cuda.reset_peak_memory_stats()
        base = torch.cuda.memory_allocated()
    resultado = yield
    if vigilar and _cuda_iniciada():
        torch = sys.modules['torch']
        pico = torch.cuda.max_memory_allocated()
        if not antes or pico > base:
            pytest.fail(f'{item.nodeid} usa CUDA ({pico} bytes) sin la marca gpu: añada a su módulo una de '
                        f'{SEÑALES_GPU} o la marca, para que tome el turno de la GPU (106:RF-9).', pytrace=False)
    return resultado


def pytest_sessionfinish(session, exitstatus):
    import sys

    soltar_turno()
    # 106:RF-16: si una prueba escribió en un registro real de la web, la sesión falla y dice dónde. Lo mira el
    # proceso principal; la web del usuario escribe a la vez en el suyo, por eso solo cuentan las líneas de pytest.
    if os.environ.get('PYTEST_XDIST_WORKER'):
        return
    halladas = lineas_de_pruebas_en_registros(_TAMANOS_DE_REGISTROS)
    if halladas:
        print('\nUNA PRUEBA ESCRIBIÓ EN UN REGISTRO REAL DE LA WEB (106:RF-16):', *halladas[:10], sep='\n  ',
              file=sys.__stderr__, flush=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    if _SESION_PROPIA:
        aviso = retirar_sesion_de_datos(_SESION_DE_DATOS)
        if aviso:
            print(f'\n{aviso}', file=sys.__stderr__, flush=True)


def retirar_sesion_de_datos(carpeta: Path) -> str | None:
    """106:RF-17: borra la carpeta de datos de la sesión; si algo queda, lo dice sin hacer fallar la suite.

    Antes cierra los manejadores de registro que apuntan dentro: en Windows, el web.log que abren las pruebas del
    lanzador sigue abierto y un fichero abierto no se borra.
    """
    import logging
    import shutil

    raiz = Path(carpeta).resolve()
    for registrador in [logging.getLogger(), *[logging.getLogger(n) for n in logging.root.manager.loggerDict]]:
        for manejador in list(getattr(registrador, 'handlers', [])):
            destino = getattr(manejador, 'baseFilename', None)
            if destino and Path(destino).resolve().is_relative_to(raiz):
                registrador.removeHandler(manejador)
                manejador.close()
    shutil.rmtree(raiz, ignore_errors=True)
    if raiz.exists():
        return f'No se pudo borrar la carpeta de datos de la suite {raiz}: bórrela a mano (106:RF-17).'
    return None


#: El flujo de GitHub Actions lo declara: allí no hay GPU (102:RF-17).
VARIABLE_CI_SIN_GPU = 'CSG_CI_SIN_GPU'


def _ci_sin_cuda() -> bool:
    if os.environ.get(VARIABLE_CI_SIN_GPU) != '1':
        return False
    try:
        import torch
    except ImportError:
        return True
    return not torch.cuda.is_available()


def _por_falta_de_gpu(exc: BaseException | None) -> bool:
    """El fallo es la falta de GPU que el código declara (``SinGPU``), también como causa encadenada."""
    from convertersmartgrid.aplicacion.training_coordinator import SinGPU

    vistos = set()
    while exc is not None and id(exc) not in vistos:
        vistos.add(id(exc))
        if isinstance(exc, SinGPU):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """102:RF-17: en GitHub, una prueba que exige GPU CUDA y no la tiene queda omitida con su motivo, no fallida.

    Solo con ``CSG_CI_SIN_GPU=1`` y sin CUDA, y solo si el fallo es ``SinGPU``: cualquier otro sigue siendo un fallo.
    En la máquina de desarrollo nunca se activa: allí la suite completa no admite omitidas (102:RF-9).
    """
    resultado = yield
    informe = resultado.get_result()
    if informe.failed and call.excinfo is not None and _ci_sin_cuda() and _por_falta_de_gpu(call.excinfo.value):
        informe.outcome = 'skipped'
        informe.longrepr = (str(item.path), item.location[1] or 0,
                            'Skipped: exige GPU CUDA y GitHub Actions no la tiene (102:RF-17)')


@contextmanager
def entorno_restituido():
    """102:RF-20: lo que haya escrito el bloque en ``os.environ`` se deshace al salir."""
    antes = dict(os.environ)
    try:
        yield
    finally:
        if os.environ != antes:
            os.environ.clear()
            os.environ.update(antes)


@pytest.fixture(autouse=True)
def _entorno_restituido():
    """102:RF-20: cada prueba deja las variables de entorno como las encontró.

    ``web.__main__.main`` escribe ``CSG_WEB_HOST`` y el puerto en ``os.environ`` (es el proceso del servidor). Las pruebas
    del lanzador lo llaman dentro de pytest y, en la puerta del 2026-11-11 (4 749 pruebas en un proceso), la ruta del libro
    de pérdidas ya no daba 403 y el cierre del lanzador daba 202: ambas pasaban solas.
    """
    with entorno_restituido():
        yield
    # Lo mismo con el cierre que ``main`` registra en la web: con él, «cerrar» de otra prueba daba 202 y no 503.
    import sys
    app_mod = sys.modules.get('convertersmartgrid.presentacion.web.app')
    if app_mod is not None:
        app_mod._cierre.clear()
        app_mod._motivo_cierre.clear()


@pytest.fixture(autouse=True)
def _guardia_de_gpu_propia(monkeypatch, tmp_path, request):
    """102:RF-22: cada prueba con su guardia de GPU, no la de la máquina.

    El 2026-11-11 un entrenamiento real tenía la guardia y 25 pruebas del oráculo fallaron en la puerta con «GPU ocupada:
    otro proceso conserva la guardia». Sus modelos son de prueba y caben junto al entrenamiento.

    106:RF-10: un hijo que entrena toma el turno, que aquí es el de la prueba, y su ``.guard`` queda en disco (043:RF-6
    nunca lo borra). Si la prueba no lleva la marca ``gpu``, ella o un hijo suyo usaron la GPU sin pedir el turno común.
    """
    monkeypatch.setenv('CSG_ML_GPU_LOCK', str(tmp_path / 'gpu.lock'))
    yield
    fallo = turno_sin_marca(tmp_path / 'gpu.lock', marcada=request.node.get_closest_marker('gpu') is not None)
    if fallo:
        pytest.fail(f'{request.node.nodeid}: {fallo}', pytrace=False)


def turno_sin_marca(lock: Path, *, marcada: bool) -> str | None:
    """106:RF-10: el motivo si una prueba sin la marca ``gpu`` dejó el turno de su guardia tomado alguna vez."""
    if marcada or not lock.with_name(lock.name + '.guard').exists():
        return None
    return ('tomó el turno de GPU (ella o un proceso que lanzó) sin la marca gpu: añada a su módulo una de '
            f'{SEÑALES_GPU} o la marca (106:RF-10).')


@pytest.fixture(autouse=True)
def _sin_perfil_de_la_maquina(monkeypatch, tmp_path_factory):
    """Sin perfil de empresa salvo que la prueba lo pida (spec 002, RF-32 y RF-33).

    ``config/perfil_empresa.json`` es local: con el de una distribuidora real, las pruebas
    pasaban en su equipo y fallaban en otro sin él. Una prueba que necesite un perfil lo
    escribe ella o usa uno de ``config/perfiles``.
    """
    from convertersmartgrid.dominio.perfil_empresa import VARIABLE_RUTA

    vacio = tmp_path_factory.getbasetemp() / 'sin_perfil_empresa.json'
    monkeypatch.setenv(VARIABLE_RUTA, str(vacio))


@pytest.fixture(autouse=True)
def _sin_salidas_guardadas_de_la_maquina(monkeypatch, tmp_path):
    """086:RF-66: cada prueba con su fichero de salidas, ni el del equipo ni el de otra prueba.

    En desarrollo la carpeta local es el repositorio: un ``config/salidas.json`` con el fondo de mapa
    encendido desde la web cambiaba lo que las pruebas de la edición de producto esperan.
    """
    from convertersmartgrid.dominio.salidas_red import VARIABLE_RUTA_GUARDADAS

    monkeypatch.setenv(VARIABLE_RUTA_GUARDADAS, str(tmp_path / '_salidas_guardadas.json'))


#: 086:RF-22 (H8H5 v3, orden de c3): los ficheros de pruebas de red y SSRF (salidas, ArcGIS, OSRM). En ellos ningún
#: socket sale de verdad: el rojo viejo de H8H5 llegó a conectar con 127.0.0.1:9 y con 169.254.169.254.
MODULOS_SIN_RED_REAL = frozenset({'test_seguridad_web', 'test_vnr_etl', 'test_vias'})
RED_REAL_PROHIBIDA = 'conexión de red real prohibida en las pruebas'
#: Las pruebas que levantan un uvicorn de verdad en 127.0.0.1 (``servidor_real``) se conectan a él: esas sí.
FIXTURES_CON_RED_LOCAL = frozenset({'servidor_real'})


def _host_y_puerto(direccion) -> str:
    if isinstance(direccion, tuple) and len(direccion) >= 2:
        return f'{direccion[0]}:{direccion[1]}'
    return str(direccion)


@pytest.fixture(autouse=True)
def _sin_red_real(request, monkeypatch):
    """086:RF-22: en las pruebas de red, ``connect``, ``create_connection``, ``getaddrinfo`` y ``gethostbyname`` reales
    fallan con una AssertionError que dice adónde iban. Lo que la prueba simule con monkeypatch después la sustituye y
    sigue funcionando. Solo se admite el ``socketpair`` del bucle de asyncio (en Windows se une por 127.0.0.1)."""
    modulo = Path(getattr(request.module, '__file__', '') or '').stem
    if modulo not in MODULOS_SIN_RED_REAL or FIXTURES_CON_RED_LOCAL & set(request.fixturenames):
        yield False
        return
    import socket
    import threading

    permiso = threading.local()
    connect, connect_ex, socketpair = socket.socket.connect, socket.socket.connect_ex, socket.socketpair

    def vedado(direccion):
        raise AssertionError(f'{RED_REAL_PROHIBIDA}: {_host_y_puerto(direccion)}')

    def marcar(f):
        f._red_real_prohibida = True
        return f

    @marcar
    def connect_vedado(sock, direccion):
        if getattr(permiso, 'par', False):
            return connect(sock, direccion)
        vedado(direccion)

    @marcar
    def connect_ex_vedado(sock, direccion):
        if getattr(permiso, 'par', False):
            return connect_ex(sock, direccion)
        vedado(direccion)

    @marcar
    def create_connection_vedado(direccion, *_a, **_k):
        vedado(direccion)

    @marcar
    def getaddrinfo_vedado(host, puerto, *_a, **_k):
        vedado((host, puerto))

    @marcar
    def gethostbyname_vedado(host):
        vedado((host, ''))

    def socketpair_permitido(*a, **k):
        permiso.par = True
        try:
            return socketpair(*a, **k)
        finally:
            permiso.par = False

    monkeypatch.setattr(socket.socket, 'connect', connect_vedado)
    monkeypatch.setattr(socket.socket, 'connect_ex', connect_ex_vedado)
    monkeypatch.setattr(socket, 'create_connection', create_connection_vedado)
    monkeypatch.setattr(socket, 'getaddrinfo', getaddrinfo_vedado)
    monkeypatch.setattr(socket, 'gethostbyname', gethostbyname_vedado)
    monkeypatch.setattr(socket, 'socketpair', socketpair_permitido)
    yield True


@pytest.fixture(autouse=True)
def _sin_turno_de_la_maquina(monkeypatch, tmp_path):
    """Cada prueba con su propio turno de DIgSILENT (spec 019).

    El turno es un fichero de la máquina, común a la web, el CLI y DIgSILENT abierto a
    mano. Las pruebas de los guiones con el doble de PowerFactory lo tomaban de verdad: el
    2026-10-17 la suite lo tuvo más de 10 minutos y una sonda real se quedó sin DIgSILENT
    («ocupado por ajuste_cabecera_pf.py», que era pytest).
    """
    from convertersmartgrid.adaptadores import powerfactory_env
    from convertersmartgrid.adaptadores.pf_arnes import VARIABLE_TURNO

    monkeypatch.setenv(VARIABLE_TURNO, str(tmp_path / 'powerfactory.turno'))
    # Tampoco miran el DIgSILENT de la máquina: el 2026-10-22 el operador lo abrió a mano
    # para calibrar y los guiones con el doble se negaron a correr (019:RF-13).
    monkeypatch.setattr(powerfactory_env, 'powerfactory_abierto', lambda lista=None: [])


@pytest.fixture(autouse=True)
def _sin_gemelo_de_la_maquina(monkeypatch, tmp_path):
    """Cada prueba con su búfer del gemelo y sin captura tras las acciones (spec 024).

    La captura lanza la lectura nativa después de cada acción de DIgSILENT; en las pruebas
    de la web sería un proceso más que no esperan. Las pruebas del gemelo la encienden.
    """
    from convertersmartgrid.adaptadores.digital_twin.integration import VARIABLE_CAPTURA

    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / '_digital_twin'))
    monkeypatch.setenv(VARIABLE_CAPTURA, '0')
    # 081:RF-80: el registro de aperturas de las obras, de cada prueba y no el de la máquina.
    from convertersmartgrid.aplicacion.obras_pf import VARIABLE_APERTURAS

    monkeypatch.setenv(VARIABLE_APERTURAS, str(tmp_path / '_aperturas_pf'))


@pytest.fixture(scope='session')
def perfil_real():
    """Perfil de empresa de los datos reales de las variables ``CSG_*``.

    Los de ``referencia/`` son de una distribuidora real, así que por defecto es su perfil: es
    el de los datos de prueba, no un valor por defecto del código (spec 002, RF-35).
    La entrega de otra empresa lo dice con ``CSG_PERFIL=<nombre de config/perfiles>``.
    """
    import os

    from convertersmartgrid.dominio.perfil_empresa import perfil_con_nombre

    return perfil_con_nombre(os.environ.get('CSG_PERFIL', '').strip() or 'electro_dunas')


@pytest.fixture(scope='session')
def opciones_reales(perfil_real) -> dict:
    """CRS, reglas y perfil con que se convierten los datos reales."""
    from convertersmartgrid.aplicacion.reglas import reglas_de_perfil

    return {'source_crs': perfil_real.crs_origen, 'reglas': reglas_de_perfil(perfil_real),
            'perfil': perfil_real}


@pytest.fixture(scope='session')
def csg_paths() -> tuple[Path, Path, Path]:
    paths = resolve_txt_paths()
    if paths is None:
        pytest.skip(SKIP_MSG)
    return paths


@pytest.fixture(scope='session')
def RED(csg_paths: tuple[Path, Path, Path]) -> Path:
    return csg_paths[0]


@pytest.fixture(scope='session')
def LOAD(csg_paths: tuple[Path, Path, Path]) -> Path:
    return csg_paths[1]


@pytest.fixture(scope='session')
def EQUIP(csg_paths: tuple[Path, Path, Path]) -> Path:
    return csg_paths[2]


@pytest.fixture(scope='session')
def ds(csg_paths: tuple[Path, Path, Path]):
    from convertersmartgrid.adaptadores.dataset import DatasetRed

    red, loads, equip = csg_paths
    dataset = DatasetRed.from_files(red, loads, equip)
    if not dataset.feeder_ids():
        pytest.skip('El dataset cargado no contiene alimentadores')
    return dataset


@pytest.fixture(scope='session')
def feeder_shorts(ds) -> list[str]:
    return [feeder_short_name(network_id) for network_id in ds.feeder_ids()]


@pytest.fixture(scope='session')
def sample_feeder(feeder_shorts) -> str:
    return feeder_shorts[0]


@pytest.fixture(scope='session')
def second_feeder(feeder_shorts, sample_feeder) -> str:
    others = [name for name in feeder_shorts if name != sample_feeder]
    if not others:
        pytest.skip('Se necesita al menos 2 alimentadores en el dataset cargado')
    return others[0]


@pytest.fixture(scope='session')
def sample_model(ds, sample_feeder):
    from convertersmartgrid.dominio.model import build_feeder_model

    return build_feeder_model(ds, sample_feeder)


# --- Un alimentador por las dos vías de entrada (test_feeder_*.py) -----------------
#
# Cada módulo que las usa declara ``FEEDER = '<nombre corto>'``. Estaban copiadas en
# test_feeder_pa297.py y test_feeder_sl193.py. Cada fuente se prueba por su cuenta:
# TXT y base son independientes y no se comparan entre sí (2026-10-14). Alcance
# ``module``, como antes: convert_selection prepara el dataset en el sitio, y
# compartirlo entre módulos cambiaría el aislamiento de las pruebas.

@pytest.fixture(scope='module')
def txt_dataset(csg_paths):
    from convertersmartgrid.adaptadores.dataset import DatasetRed

    red, loads, equip = csg_paths
    return DatasetRed.from_files(red, loads, equip)


@pytest.fixture(scope='module')
def mdb_dataset():
    import os

    mdb = os.environ.get('CSG_MDB', '').strip()
    if not mdb or not Path(mdb).is_file():
        pytest.skip('Defina CSG_MDB con la ruta de una base de red CYMDIST (.mdb)')
    pytest.importorskip('pyodbc')
    from convertersmartgrid.adaptadores.access import AccessReadError, read_access_dataset

    try:
        return read_access_dataset(mdb, equipment_db=os.environ.get('CSG_EQUIPMENT_MDB') or None)
    except AccessReadError as exc:
        pytest.skip(f'No se pudo leer {mdb}: {exc}')


@pytest.fixture(params=['txt', 'mdb'])
def dataset_for(request, txt_dataset, mdb_dataset):
    """Parametriza cada prueba sobre las dos alternativas de entrada."""
    from apoyo import codigo_real

    # LIMPIEZA-CODIGOS: el módulo escribe la versión inventada del alimentador; la entrada real trae el suyo.
    feeder = codigo_real(request.module.FEEDER)
    ds = txt_dataset if request.param == 'txt' else mdb_dataset
    try:
        ds.resolve_feeder(feeder)
    except KeyError:
        pytest.skip(f'{feeder} no está en la entrada «{request.param}»')
    return request.param, ds


@pytest.fixture(autouse=True)
def _sin_crecimiento_de_otra_prueba():
    """098:RF-49: el crecimiento ya calculado vive en el proceso; cada prueba empieza sin el de otra."""
    import sys
    mod = sys.modules.get('convertersmartgrid.presentacion.web.services')
    if mod is not None and hasattr(mod, 'CRECIMIENTO_DEL_TRABAJO'):
        mod.CRECIMIENTO_DEL_TRABAJO.clear()
    yield
