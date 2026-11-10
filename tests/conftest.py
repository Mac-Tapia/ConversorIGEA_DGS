"""Shared fixtures for CYMDIST TXT integration tests.

Feeders and codes come only from the loaded TXT set — no company-specific names
are required (IN111/TA121 etc. are optional samples when present).
"""

from __future__ import annotations

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
