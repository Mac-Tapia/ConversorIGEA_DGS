"""Shared fixtures for IGEA TXT integration tests.

Feeders and codes come only from the loaded TXT set — no company-specific names
are required (IN111/TA121 etc. are optional samples when present).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from igea_paths import SKIP_MSG, resolve_igea_txt_paths
from igea_dgs.naming import feeder_short_name


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
# test_feeder_pa217.py y test_feeder_sl143.py (y ``both`` tres veces); el criterio de
# «misma foto de la red» se había corregido en las tres copias a mano. Alcance
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


@pytest.fixture
def both(request, txt_dataset, mdb_dataset):
    """Los dos datasets, solo si son la misma exportación de la red."""
    feeder = request.module.FEEDER
    for ds in (txt_dataset, mdb_dataset):
        try:
            ds.resolve_feeder(feeder)
        except KeyError:
            pytest.skip(f'{feeder} no está en las dos entradas')
    # Solo tiene sentido comparar tramo a tramo la MISMA exportación. CYMDIST renumera
    # nodos entre entregas: con TXT y base de fechas distintas, esto daba 10 fallos
    # que no eran del lector. El criterio mira los ID de NODE y SECTION, no los
    # extremos de cada tramo, así que un fallo real de mapeo sigue detectándose.
    from igea_dgs.huella import comparar

    huella = comparar(txt_dataset, mdb_dataset)
    if not huella.misma_foto:
        pytest.skip(huella.motivo())
    return txt_dataset, mdb_dataset
