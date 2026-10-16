"""Shared fixtures for IGEA TXT integration tests.

Feeders and codes come only from the loaded TXT set — no company-specific names
are required (IN111/TA121 etc. are optional samples when present).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from igea_paths import SKIP_MSG, resolve_igea_txt_paths
from igea_dgs.naming import feeder_short_name


@pytest.fixture(autouse=True)
def _sin_perfil_de_la_maquina(monkeypatch, tmp_path_factory):
    """Sin perfil de empresa salvo que la prueba lo pida (spec 002, RF-32 y RF-33).

    ``config/perfil_empresa.json`` es local: con el de Electro Dunas, las pruebas
    pasaban en su equipo y fallaban en otro sin él. Una prueba que necesite un perfil lo
    escribe ella o usa uno de ``config/perfiles``.
    """
    from igea_dgs.perfil_empresa import VARIABLE_RUTA

    vacio = tmp_path_factory.getbasetemp() / 'sin_perfil_empresa.json'
    monkeypatch.setenv(VARIABLE_RUTA, str(vacio))


@pytest.fixture(scope='session')
def perfil_real():
    """Perfil de empresa de los datos reales de las variables ``IGEA_*``.

    Los de ``referencia/`` son de Electro Dunas, así que por defecto es su perfil: es
    el de los datos de prueba, no un valor por defecto del código (spec 002, RF-35).
    La entrega de otra empresa lo dice con ``IGEA_PERFIL=<nombre de config/perfiles>``.
    """
    import os

    from igea_dgs.perfil_empresa import perfil_con_nombre

    return perfil_con_nombre(os.environ.get('IGEA_PERFIL', '').strip() or 'electro_dunas')


@pytest.fixture(scope='session')
def opciones_reales(perfil_real) -> dict:
    """CRS, reglas y perfil con que se convierten los datos reales."""
    from igea_dgs.reglas import reglas_de_perfil

    return {'source_crs': perfil_real.crs_origen, 'reglas': reglas_de_perfil(perfil_real),
            'perfil': perfil_real}


@pytest.fixture(scope='session')
def igea_paths() -> tuple[Path, Path, Path]:
    paths = resolve_igea_txt_paths()
    if paths is None:
        pytest.skip(SKIP_MSG)
    return paths


@pytest.fixture(scope='session')
def RED(igea_paths: tuple[Path, Path, Path]) -> Path:
    return igea_paths[0]


@pytest.fixture(scope='session')
def LOAD(igea_paths: tuple[Path, Path, Path]) -> Path:
    return igea_paths[1]


@pytest.fixture(scope='session')
def EQUIP(igea_paths: tuple[Path, Path, Path]) -> Path:
    return igea_paths[2]


@pytest.fixture(scope='session')
def ds(igea_paths: tuple[Path, Path, Path]):
    from igea_dgs.dataset import CymdistDataset

    red, loads, equip = igea_paths
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
    from igea_dgs.model import build_feeder_model

    return build_feeder_model(ds, sample_feeder)


# --- Un alimentador por las dos vías de entrada (test_feeder_*.py) -----------------
#
# Cada módulo que las usa declara ``FEEDER = '<nombre corto>'``. Estaban copiadas en
# test_feeder_pa217.py y test_feeder_sl143.py. Cada fuente se prueba por su cuenta:
# TXT y base son independientes y no se comparan entre sí (2026-10-14). Alcance
# ``module``, como antes: convert_selection prepara el dataset en el sitio, y
# compartirlo entre módulos cambiaría el aislamiento de las pruebas.

@pytest.fixture(scope='module')
def txt_dataset(igea_paths):
    from igea_dgs.dataset import CymdistDataset

    red, loads, equip = igea_paths
    return CymdistDataset.from_files(red, loads, equip)


@pytest.fixture(scope='module')
def mdb_dataset():
    import os

    mdb = os.environ.get('IGEA_MDB', '').strip()
    if not mdb or not Path(mdb).is_file():
        pytest.skip('Defina IGEA_MDB con la ruta de una base de red CYMDIST (.mdb)')
    pytest.importorskip('pyodbc')
    from igea_dgs.access import AccessReadError, read_access_dataset

    try:
        return read_access_dataset(mdb, equipment_db=os.environ.get('IGEA_EQUIPMENT_MDB') or None)
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
