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
