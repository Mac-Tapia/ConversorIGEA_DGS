"""Spec 086 (Plan Maestro V1, F-11) — WCAG 2.2 AA de la web: teclado, ARIA de las pestañas, contraste y objetivos.

Las comprobaciones de la spec 086 viven en ``frontend/test/accesibilidad.test.mjs`` (Node, sin navegador). Esta prueba las ejecuta
sola, para que el corredor de pytest tenga su rojo y su verde propios; ``test_frontend_rutas.py`` las vuelve a correr
con todas las demás. Los recorridos en navegador con axe son los E2E de ``frontend/test/e2e``.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from test_frontend_rutas import _dependencias, _enlazar

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / 'frontend'
PRUEBA = 'accesibilidad.test.mjs'


def test_la_web_cumple_teclado_aria_contraste_y_objetivos_wcag_22_aa(tmp_path):
    """086:RF-106 (F-11) — rojo sin teclado.ts, Pestanas.tsx ni los tokens nuevos; verde con ellos."""
    dependencias = _dependencias()
    if shutil.which('node') is None or dependencias is None:
        pytest.skip('Falta Node.js o `npm ci` en frontend: las pruebas del frontend no se pueden ejecutar.')
    assert (FRONT / 'test' / PRUEBA).is_file(), f'falta frontend/test/{PRUEBA}'
    destino = tmp_path / 'frontend'
    shutil.copytree(FRONT / 'src', destino / 'src')
    (destino / 'test').mkdir()
    shutil.copy2(FRONT / 'test' / PRUEBA, destino / 'test' / PRUEBA)
    shutil.copy2(FRONT / 'package.json', destino / 'package.json')
    shutil.copy2(FRONT / 'tsconfig.json', destino / 'tsconfig.json')
    enlace = destino / 'node_modules'
    _enlazar(enlace, dependencias)
    try:
        r = subprocess.run(['node', '--test', f'test/{PRUEBA}'], cwd=destino, capture_output=True, timeout=240,
                           env={k: v for k, v in os.environ.items() if k != 'NODE_TEST_CONTEXT'})
    finally:
        # Se retira el enlace, nunca lo enlazado: las dependencias pueden ser las del checkout primario.
        if os.name == 'nt':
            os.rmdir(enlace)
        else:
            enlace.unlink()
    salida = r.stdout.decode('utf-8', errors='replace') + r.stderr.decode('utf-8', errors='replace')
    aprobadas = re.search(r'^(?:# |ℹ )pass (\d+)', salida, re.M)
    fallidas = re.search(r'^(?:# |ℹ )fail (\d+)', salida, re.M)
    assert r.returncode == 0, salida
    assert aprobadas and int(aprobadas.group(1)) >= 12, salida
    assert fallidas and int(fallidas.group(1)) == 0, salida
