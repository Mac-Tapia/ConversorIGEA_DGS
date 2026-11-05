"""Pruebas del motor base de conversión.

Spec 034: 034:RF-20.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import types

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


def _runtime_module():
    try:
        return importlib.import_module('convertersmartgrid.web.runtime')
    except ModuleNotFoundError:
        pytest.fail('falta el comprobador único de dependencias del lanzador web')


def test_runtime_probe_covers_all_three_source_modes():
    runtime = _runtime_module()

    required = set(runtime.REQUIRED_MODULES)

    assert {'convertersmartgrid', 'pyproj', 'fastapi', 'uvicorn', 'multipart'} <= required
    assert {'vnr_etl', 'requests', 'shapely', 'networkx', 'yaml', 'geopandas'} <= required


def test_runtime_probe_reports_the_missing_import_name():
    runtime = _runtime_module()

    def importer(name: str):
        if name == 'shapely':
            raise ModuleNotFoundError(name)
        return object()

    assert runtime.missing_dependencies(importer) == ('shapely',)


@pytest.mark.parametrize('version', [(3, 11), (3, 13), (4, 0)])
def test_version_incompatible_no_anuncia_entorno_listo(version):
    """065:RF-15 — una versión incompatible nunca se anuncia como Python válido."""
    runtime = _runtime_module()
    assert hasattr(runtime, 'diagnostico_capacidades')
    diagnostico = runtime.diagnostico_capacidades(lambda _: object(), version=version, drivers=lambda: ())
    assert diagnostico['python_valido'] is False
    assert diagnostico['listo'] is False


def test_import_real_fallido_y_driver_se_diagnostican_separados():
    """065:RF-14 — import presente pero roto y driver ausente tienen causas distintas."""
    runtime = _runtime_module()
    assert hasattr(runtime, 'diagnostico_capacidades')

    def importar(nombre):
        if nombre == 'python_calamine':
            raise OSError('DLL ausente')
        return types.SimpleNamespace(drivers=lambda: ())

    diagnostico = runtime.diagnostico_capacidades(importar, version=(3, 12), drivers=lambda: ())
    assert diagnostico['capacidades']['xlsx']['disponible'] is False
    assert diagnostico['capacidades']['mdb']['modulos_faltantes'] == ()
    assert diagnostico['capacidades']['mdb']['drivers_faltantes']
    assert diagnostico['capacidades']['mdb']['disponible'] is False
    assert diagnostico['capacidades']['vnr_sqlserver']['disponible'] is False


def test_drivers_reales_habilitan_solo_su_capacidad():
    """065:RF-14 — Access disponible no acredita el driver específico SQL Server 18."""
    runtime = _runtime_module()
    assert hasattr(runtime, 'diagnostico_capacidades')
    diagnostico = runtime.diagnostico_capacidades(
        lambda _: object(), version=(3, 12),
        drivers=lambda: ('Microsoft Access Driver (*.mdb, *.accdb)', 'ODBC Driver 17 for SQL Server'))
    assert diagnostico['listo'] is True
    assert diagnostico['capacidades']['mdb']['disponible'] is True
    assert diagnostico['capacidades']['vnr_sqlserver']['disponible'] is False


def test_runtime_arranca_aunque_fastapi_no_este_instalado(tmp_path):
    """065:RF-14 — el diagnóstico no carga la API antes de comprobar sus dependencias."""
    fuente = Path(__file__).resolve().parents[1] / 'src'
    codigo = '''
import importlib.abc, json, sys
class SinFastapi(importlib.abc.MetaPathFinder):
    def find_spec(self, nombre, path=None, target=None):
        if nombre == 'fastapi' or nombre.startswith('fastapi.'):
            raise ModuleNotFoundError('fastapi ausente deliberadamente')
sys.meta_path.insert(0, SinFastapi())
from convertersmartgrid.web.runtime import missing_dependencies
print(json.dumps(missing_dependencies()))
'''
    # Importa de verdad cada dependencia: 3 s solo, 18 s tras las pruebas web y más de 60 s con la memoria justa (2026-11-05). Esta
    # prueba mira que arranque sin FastAPI, no cuánto tarda: el límite solo debe cortar un cuelgue.
    resultado = subprocess.run([sys.executable, '-c', codigo], cwd=tmp_path,
        env={**os.environ, 'PYTHONPATH': str(fuente), 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=300)
    assert resultado.returncode == 0, resultado.stderr
    assert 'fastapi' in json.loads(resultado.stdout)


def test_extras_de_arranque_declaran_los_mismos_imports_requeridos():
    """065:RF-15 — los extras web/all no omiten dependencias verificadas al arrancar."""
    runtime = _runtime_module()
    manifiesto = Path(__file__).resolve().parents[1] / 'pyproject.toml'
    extras = tomllib.loads(manifiesto.read_text(encoding='utf-8'))['project']['optional-dependencies']
    paquetes = {
        'multipart': 'python-multipart', 'python_calamine': 'python-calamine',
        'docx': 'python-docx', 'PIL': 'pillow', 'yaml': 'pyyaml',
    }
    requeridos = {paquetes.get(nombre, nombre).lower() for nombre in runtime.REQUIRED_MODULES
                  if nombre not in ('convertersmartgrid', 'vnr_etl')}
    for grupo in ('web', 'all'):
        declarados = {Requirement(linea).name.lower() for linea in extras[grupo]}
        assert not (requeridos - declarados), (grupo, sorted(requeridos - declarados))
    principal = manifiesto.parent / 'requirements.txt'
    declarados = {Requirement(linea).name.lower() for linea in principal.read_text(encoding='utf-8').splitlines()
                  if linea.strip() and not linea.lstrip().startswith(('#', '-'))}
    assert not (requeridos - declarados), sorted(requeridos - declarados)
    versiones = SpecifierSet(tomllib.loads(manifiesto.read_text(encoding='utf-8'))['project']['requires-python'])
    assert '3.12.0' in versiones
    assert '3.11.9' not in versiones and '3.13.0' not in versiones
