"""002:RF-6, 002:RF-20, 002:RF-21, 002:RF-22: traslado VNR sin cambiar su CLI."""
from __future__ import annotations

import ast
import importlib
from importlib.metadata import EntryPoint
import os
from pathlib import Path
import pickle
import subprocess
import sys
import tomllib

import pytest

RAIZ = Path(__file__).resolve().parents[1]
PAQUETE = 'convertersmartgrid.adaptadores.entrada.vnr'


def test_implementacion_vive_solo_en_adaptador():
    """002:RF-6: sin paquete paralelo ni segunda identidad del modelo."""
    modulo = importlib.import_module(PAQUETE + '.models')
    modelo = modulo.CanonicalModel()
    assert modelo.__class__.__module__ == PAQUETE + '.models.canonical'
    assert isinstance(pickle.loads(pickle.dumps(modelo)), modulo.CanonicalModel)
    assert not (RAIZ / 'src/vnr_etl').exists()


def test_dos_entrypoints_delegan_en_la_misma_implementacion():
    """002:RF-22: también funciona el launcher instalado antes del traslado."""
    config = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    destino = config['project']['scripts']['vnr-etl']
    assert destino == PAQUETE + '.cli:main'
    nuevo = EntryPoint(name='vnr-etl', value=destino, group='console_scripts').load()
    antiguo = EntryPoint(name='vnr-etl', value='vnr_etl.cli:main', group='console_scripts').load()
    fachada = importlib.import_module('vnr_etl')
    assert nuevo is antiguo is fachada.main is fachada.cli.main
    assert importlib.import_module('vnr_etl.cli') is importlib.import_module(PAQUETE + '.cli')
    assert config['tool']['setuptools']['py-modules'] == ['vnr_etl']


@pytest.mark.parametrize('argumentos,rc', [
    (['--help'], 0), (['--version'], 0), (['ver'], 0), (['comando-inexistente'], 2),
])
def test_cli_real_ruta_nueva_y_compatibilidad(argumentos, rc):
    """002:RF-22: procesos propios, sin servidores ni motores externos."""
    env = {**os.environ, 'PYTHONPATH': str(RAIZ / 'src')}
    resultados = [subprocess.run([sys.executable, '-B', '-m', modulo, *argumentos],
                                cwd=RAIZ, env=env, capture_output=True, text=True, timeout=30)
                  for modulo in ('vnr_etl', PAQUETE)]
    assert [r.returncode for r in resultados] == [rc, rc]
    assert resultados[0].stdout == resultados[1].stdout
    assert resultados[0].stderr == resultados[1].stderr


def test_consumidores_no_importan_paquete_retirado():
    """002:RF-21: ningún consumidor estático necesita las rutas internas antiguas."""
    pendientes = []
    for carpeta in ('src', 'tools', 'tests'):
        for archivo in (RAIZ / carpeta).rglob('*.py'):
            for nodo in ast.walk(ast.parse(archivo.read_text(encoding='utf-8-sig'))):
                nombres = ([n.name for n in nodo.names] if isinstance(nodo, ast.Import)
                           else [nodo.module or ''] if isinstance(nodo, ast.ImportFrom) else [])
                if any(n == 'vnr_etl' or n.startswith('vnr_etl.') for n in nombres):
                    pendientes.append(f'{archivo.relative_to(RAIZ)}:{nodo.lineno}')
    assert not pendientes, pendientes


def test_auditoria_encuentra_modulos_tras_movimiento(tmp_path):
    """002:RF-6: el diagnóstico deja de depender de la carpeta retirada."""
    auditoria = importlib.import_module(PAQUETE + '.audit.project')
    informes = auditoria.run_audit(RAIZ, tmp_path)
    conectores = informes['connectors.md'].read_text(encoding='utf-8')
    assert 'convertersmartgrid/adaptadores/entrada/vnr/connectors/arcgis.py' in conectores
    assert 'convertersmartgrid/adaptadores/entrada/vnr/gis/crs.py' in informes['gis_modules.md'].read_text(encoding='utf-8')


def test_manifest_y_mapa_de_rueda_incluyen_fachada_sin_aceptar_sufijos():
    """002:RF-22; 086:RF-32: el módulo suelto no queda fuera de entrega."""
    import json
    from apoyo import cargar_herramienta

    entrega = cargar_herramienta('comprobar_entrega.py')
    manifiesto = json.loads((RAIZ / 'config/entrega.json').read_text(encoding='utf-8'))
    assert entrega.entra('src/vnr_etl.py', manifiesto)
    assert entrega.entra('src/convertersmartgrid/adaptadores/entrada/vnr/cli.py', manifiesto)
    assert entrega.ruta_en_el_repositorio('vnr_etl.py') == 'src/vnr_etl.py'
    assert entrega.ruta_en_el_repositorio('vnr_etl.pyc') is None


def test_todos_los_modulos_movidos_entran_en_git():
    """002:RF-6; 009:RF-1: AUDIT/ puede ignorar también el código audit/ en Windows."""
    carpeta = 'src/convertersmartgrid/adaptadores/entrada/vnr'
    versionados = set(subprocess.check_output(['git', 'ls-files', '--', carpeta], cwd=RAIZ,
                                            text=True).splitlines())
    reales = {p.relative_to(RAIZ).as_posix() for p in (RAIZ / carpeta).rglob('*.py')}
    assert reales <= versionados, sorted(reales - versionados)
