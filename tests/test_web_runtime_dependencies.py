from __future__ import annotations

import importlib

import pytest


def _runtime_module():
    try:
        return importlib.import_module('igea_dgs.web.runtime')
    except ModuleNotFoundError:
        pytest.fail('falta el comprobador único de dependencias del lanzador web')


def test_runtime_probe_covers_all_three_source_modes():
    runtime = _runtime_module()

    required = set(runtime.REQUIRED_MODULES)

    assert {'igea_dgs', 'pyproj', 'fastapi', 'uvicorn', 'multipart'} <= required
    assert {'vnr_etl', 'requests', 'shapely', 'networkx', 'yaml', 'geopandas'} <= required


def test_runtime_probe_reports_the_missing_import_name():
    runtime = _runtime_module()

    def importer(name: str):
        if name == 'shapely':
            raise ModuleNotFoundError(name)
        return object()

    assert runtime.missing_dependencies(importer) == ('shapely',)
