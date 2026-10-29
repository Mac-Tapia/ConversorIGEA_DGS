"""Spec 034, RF-33: las herramientas de catálogo y esquema del motor base arrancan sin DIgSILENT.

Eran las únicas herramientas sin más prueba que el ``--help`` de la 009 (revisión del
2026-10-29); ``compare_schema`` se comprueba además con un DGS hecho con el propio perfil.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from apoyo import cargar_herramienta

RAIZ = Path(__file__).resolve().parents[1]
HERRAMIENTAS = ('apply_catalog_to_model.py', 'build_input_catalog.py', 'compare_schema.py',
                'suggest_line_type_aliases.py', 'build_system_grid.py', 'prueba_representacion.py')


@pytest.mark.parametrize('herramienta', HERRAMIENTAS)
def test_arrancan_sin_powerfactory(herramienta, tmp_path):
    """034:RF-33 — cada herramienta responde a ``--help`` sin DIgSILENT ni datos."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('IGEA_')}
    env['PYTHONPATH'] = os.pathsep.join([str(RAIZ / 'src'), str(RAIZ / 'tools')])
    env['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run([sys.executable, str(RAIZ / 'tools' / herramienta), '--help'], cwd=tmp_path,
                       env=env, capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def test_el_lanzador_de_la_puerta_usa_el_interprete_de_powerfactory():
    """034:RF-33 — ``run_powerfactory_gate.bat`` lanza la aceptación desde la raíz."""
    bat = (RAIZ / 'tools' / 'run_powerfactory_gate.bat').read_text(encoding='utf-8', errors='replace')
    assert 'cd /d "%~dp0.."' in bat and 'powerfactory_acceptance.py' in bat


def test_compare_schema_con_el_propio_perfil(tmp_path):
    """034:RF-33 / 034:RF-13 — un DGS con las cabeceras del perfil coincide (0); sin una
    tabla, la nombra y sale con 2."""
    cs = cargar_herramienta('compare_schema.py')
    esquema = cs.load_schema('pf21_dgs_1_8_4')
    tablas = sorted(esquema.tables)
    completo = tmp_path / 'completo.dgs'
    completo.write_text('\n'.join(esquema.header(t) for t in tablas) + '\n', encoding='utf-8')
    assert cs.main([str(completo)]) == 0
    falta = tmp_path / 'falta.dgs'
    falta.write_text('\n'.join(esquema.header(t) for t in tablas[1:]) + '\n', encoding='utf-8')
    assert cs.main([str(falta), '--report', str(tmp_path / 'r.txt')]) == 2
    assert f"Faltan: ['{tablas[0]}']" in (tmp_path / 'r.txt').read_text(encoding='utf-8')
