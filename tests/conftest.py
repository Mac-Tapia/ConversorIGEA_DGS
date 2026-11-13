"""Shared fixtures for CYMDIST TXT integration tests.

Feeders and codes come only from the loaded TXT set — no company-specific names
are required (IN111/TA121 etc. are optional samples when present).
"""

from __future__ import annotations

from contextlib import contextmanager
import os
import tempfile
from pathlib import Path

import pytest

from csg_paths import SKIP_MSG, resolve_txt_paths
from convertersmartgrid import sesion_web
from convertersmartgrid.naming import feeder_short_name

# Aquí y no en un fixture: hay módulos que crean la aplicación al importarse o con fixtures de
# módulo. La puerta de la web se prueba en test_seguridad_web.py (086:RF-17 a RF-20), que la
# enciende; las demás prueban las rutas. Y la sesión real de la máquina no se toca nunca.
sesion_web.EXIGIR_SEGURIDAD = False
os.environ[sesion_web.VARIABLE_CARPETA] = tempfile.mkdtemp(prefix='csg-sesiones-pruebas-')
os.environ.pop(sesion_web.VARIABLE_PUERTO, None)

# 106:RF-1: la GPU de la máquina se pide una vez por sesión (ver pytest_sessionstart); dentro, la guardia es de la
# sesión. Aquí y no en un fixture: con un fixture de módulo, test_digital_twin_oraculo tomaba la guardia real antes que
# el fixture por prueba de 102:RF-22, y la puerta del 2026-11-12 esperó 40 min en silencio a la T7.
from convertersmartgrid.training_coordinator import ruta_guardia_gpu as _ruta_guardia_gpu

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


def pytest_collection_modifyitems(config, items):
    """106:RF-6: la marca ``gpu`` se pone sola; ninguna prueba depende de que alguien se acuerde de marcarla."""
    for item in items:
        if usa_gpu(item.path):
            item.add_marker(pytest.mark.gpu)


def tomar_turno_si_hace_falta(items) -> None:
    """106:RF-1 a RF-4, RF-7: el turno común, solo si alguna prueba elegida usa la GPU, esperando con plazo.

    Con otro proceso en la GPU (un entrenamiento de tools/, otra puerta), las pruebas de CUDA fallaban por memoria
    (suite de 10a80812: 61 de 62 fallidas, «CUDA error: out of memory»). Una puerta sin pruebas de GPU no espera
    (102:RF-18). Si el plazo vence, pytest sale con :data:`SALIDA_SIN_TURNO_GPU` y el dueño, sin juzgar ni omitir
    nada. Una sesión de pytest lanzada por una prueba no lo pide: es de su padre.
    """
    import sys

    if (os.environ.get('PYTEST_CURRENT_TEST') or not any(i.get_closest_marker('gpu') for i in items)
            or not _hay_cuda()):
        return
    from convertersmartgrid.trabajadores_ml import SALIDA_SIN_TURNO_GPU, turno_gpu_con_plazo

    limite = float(os.environ.get(VARIABLE_ESPERA_GPU_SUITE, ESPERA_GPU_SUITE_S))
    turno = turno_gpu_con_plazo('suite-pytest', ruta=GUARDIA_GPU_DE_LA_MAQUINA, limite_s=limite,
                                avisar=lambda t: print(t, file=sys.__stderr__, flush=True))
    try:
        turno.__enter__()
    except RuntimeError as exc:
        pytest.exit(f'La suite no puede juzgar: {exc}', returncode=SALIDA_SIN_TURNO_GPU)
    _turno_de_la_sesion.append(turno)


def pytest_collection_finish(session):
    tomar_turno_si_hace_falta(session.items)


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
    while _turno_de_la_sesion:
        _turno_de_la_sesion.pop().__exit__(None, None, None)


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
    from convertersmartgrid.training_coordinator import SinGPU

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
    app_mod = sys.modules.get('convertersmartgrid.web.app')
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

    ``config/perfil_empresa.json`` es local: con el de Electro Dunas, las pruebas
    pasaban en su equipo y fallaban en otro sin él. Una prueba que necesite un perfil lo
    escribe ella o usa uno de ``config/perfiles``.
    """
    from convertersmartgrid.perfil_empresa import VARIABLE_RUTA

    vacio = tmp_path_factory.getbasetemp() / 'sin_perfil_empresa.json'
    monkeypatch.setenv(VARIABLE_RUTA, str(vacio))


@pytest.fixture(autouse=True)
def _sin_salidas_guardadas_de_la_maquina(monkeypatch, tmp_path):
    """086:RF-66: cada prueba con su fichero de salidas, ni el del equipo ni el de otra prueba.

    En desarrollo la carpeta local es el repositorio: un ``config/salidas.json`` con el fondo de mapa
    encendido desde la web cambiaba lo que las pruebas de la edición de producto esperan.
    """
    from convertersmartgrid.salidas_red import VARIABLE_RUTA_GUARDADAS

    monkeypatch.setenv(VARIABLE_RUTA_GUARDADAS, str(tmp_path / '_salidas_guardadas.json'))


@pytest.fixture(autouse=True)
def _sin_turno_de_la_maquina(monkeypatch, tmp_path):
    """Cada prueba con su propio turno de DIgSILENT (spec 019).

    El turno es un fichero de la máquina, común a la web, el CLI y DIgSILENT abierto a
    mano. Las pruebas de los guiones con el doble de PowerFactory lo tomaban de verdad: el
    2026-10-17 la suite lo tuvo más de 10 minutos y una sonda real se quedó sin DIgSILENT
    («ocupado por ajuste_cabecera_pf.py», que era pytest).
    """
    from convertersmartgrid import powerfactory_env
    from convertersmartgrid.pf_arnes import VARIABLE_TURNO

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
    from convertersmartgrid.digital_twin.integration import VARIABLE_CAPTURA

    monkeypatch.setenv('CSG_TWIN_DATA', str(tmp_path / '_digital_twin'))
    monkeypatch.setenv(VARIABLE_CAPTURA, '0')
    # 081:RF-80: el registro de aperturas de las obras, de cada prueba y no el de la máquina.
    from convertersmartgrid.obras_pf import VARIABLE_APERTURAS

    monkeypatch.setenv(VARIABLE_APERTURAS, str(tmp_path / '_aperturas_pf'))


@pytest.fixture(scope='session')
def perfil_real():
    """Perfil de empresa de los datos reales de las variables ``CSG_*``.

    Los de ``referencia/`` son de Electro Dunas, así que por defecto es su perfil: es
    el de los datos de prueba, no un valor por defecto del código (spec 002, RF-35).
    La entrega de otra empresa lo dice con ``CSG_PERFIL=<nombre de config/perfiles>``.
    """
    import os

    from convertersmartgrid.perfil_empresa import perfil_con_nombre

    return perfil_con_nombre(os.environ.get('CSG_PERFIL', '').strip() or 'electro_dunas')


@pytest.fixture(scope='session')
def opciones_reales(perfil_real) -> dict:
    """CRS, reglas y perfil con que se convierten los datos reales."""
    from convertersmartgrid.reglas import reglas_de_perfil

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
    from convertersmartgrid.dataset import CymdistDataset

    red, loads, equip = csg_paths
    dataset = CymdistDataset.from_files(red, loads, equip)
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
    from convertersmartgrid.model import build_feeder_model

    return build_feeder_model(ds, sample_feeder)


# --- Un alimentador por las dos vías de entrada (test_feeder_*.py) -----------------
#
# Cada módulo que las usa declara ``FEEDER = '<nombre corto>'``. Estaban copiadas en
# test_feeder_pa217.py y test_feeder_sl143.py. Cada fuente se prueba por su cuenta:
# TXT y base son independientes y no se comparan entre sí (2026-10-14). Alcance
# ``module``, como antes: convert_selection prepara el dataset en el sitio, y
# compartirlo entre módulos cambiaría el aislamiento de las pruebas.

@pytest.fixture(scope='module')
def txt_dataset(csg_paths):
    from convertersmartgrid.dataset import CymdistDataset

    red, loads, equip = csg_paths
    return CymdistDataset.from_files(red, loads, equip)


@pytest.fixture(scope='module')
def mdb_dataset():
    import os

    mdb = os.environ.get('CSG_MDB', '').strip()
    if not mdb or not Path(mdb).is_file():
        pytest.skip('Defina CSG_MDB con la ruta de una base de red CYMDIST (.mdb)')
    pytest.importorskip('pyodbc')
    from convertersmartgrid.access import AccessReadError, read_access_dataset

    try:
        return read_access_dataset(mdb, equipment_db=os.environ.get('CSG_EQUIPMENT_MDB') or None)
    except AccessReadError as exc:
        pytest.skip(f'No se pudo leer {mdb}: {exc}')


@pytest.fixture(params=['txt', 'mdb'])
def dataset_for(request, txt_dataset, mdb_dataset):
    """Parametriza cada prueba sobre las dos alternativas de entrada."""
    feeder = request.module.FEEDER
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
    mod = sys.modules.get('convertersmartgrid.web.services')
    if mod is not None and hasattr(mod, 'CRECIMIENTO_DEL_TRABAJO'):
        mod.CRECIMIENTO_DEL_TRABAJO.clear()
    yield
