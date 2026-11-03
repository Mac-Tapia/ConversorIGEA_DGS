"""065:RF-8, RF-9 — el frontend se instala desde su lock y sus pruebas no dependen de la ruta.

La auditoría del 2 de noviembre vio pasar las cinco pruebas del frontend en una ruta sin espacios y
fallar en una copia con espacios por usar ``URL.pathname`` sin decodificar. Se corrigió, y dos pruebas
escritas después volvieron a usarlo: la comprobación de ``buildPreservado.test.mjs`` solo copiaba dos
ficheros fijos y `pytest` no la ve. Aquí se ejecutan todas, en las dos rutas.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / 'frontend'
# El de la compilación tiene su propia prueba de rutas, necesita npm y lanza varias compilaciones reales.
PESADAS = {'buildPreservado.test.mjs'}


def _pruebas_ligeras() -> list[Path]:
    return sorted(p for p in (FRONT / 'test').glob('*.test.mjs') if p.name not in PESADAS)


def _dependencias() -> Path | None:
    """Las del checkout o, en un worktree sin instalar, las del checkout primario."""
    candidatas = [FRONT / 'node_modules']
    marca = RAIZ / '.git'
    if marca.is_file():
        # .git de un worktree: «gitdir: <primario>/.git/worktrees/<nombre>».
        gitdir = Path(marca.read_text(encoding='utf-8').partition(':')[2].strip())
        candidatas.append(gitdir.parents[2] / 'frontend' / 'node_modules')
    return next((c for c in candidatas if (c / 'esbuild').is_dir()), None)


def _enlazar(destino: Path, origen: Path) -> None:
    if os.name == 'nt':
        import _winapi
        _winapi.CreateJunction(str(origen), str(destino))
    else:
        os.symlink(origen, destino, target_is_directory=True)


def _ejecutar_en(raiz: Path, dependencias: Path) -> tuple[int, int, str]:
    destino = raiz / 'frontend'
    shutil.copytree(FRONT / 'src', destino / 'src')
    (destino / 'test').mkdir()
    for prueba in _pruebas_ligeras():
        shutil.copy2(prueba, destino / 'test' / prueba.name)
    shutil.copy2(FRONT / 'package.json', destino / 'package.json')
    enlace = destino / 'node_modules'
    _enlazar(enlace, dependencias)
    try:
        r = subprocess.run(['node', '--test', *(f'test/{p.name}' for p in _pruebas_ligeras())],
                           cwd=destino, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=240,
                           env={k: v for k, v in os.environ.items() if k != 'NODE_TEST_CONTEXT'})
    finally:
        # Se retira el enlace, nunca lo enlazado: las dependencias pueden ser las del checkout primario.
        if os.name == 'nt':
            os.rmdir(enlace)
        else:
            enlace.unlink()
    aprobadas = re.search(r'^(?:# |ℹ )pass (\d+)', r.stdout, re.M)
    return r.returncode, int(aprobadas.group(1)) if aprobadas else 0, r.stdout + r.stderr


def test_las_pruebas_del_frontend_dan_lo_mismo_con_y_sin_espacios(tmp_path):
    """065:RF-9 — todas las ligeras, en una ruta sin espacios y en otra con espacios y eñe."""
    dependencias = _dependencias()
    if shutil.which('node') is None or dependencias is None:
        pytest.skip('Falta Node.js o `npm ci` en frontend: las pruebas del frontend no se pueden ejecutar.')
    assert _pruebas_ligeras(), 'No hay pruebas del frontend que ejecutar.'
    sin = _ejecutar_en(tmp_path / 'sin-espacios', dependencias)
    con = _ejecutar_en(tmp_path / 'con espacios y ñ', dependencias)
    assert sin[0] == 0, sin[2]
    assert con[0] == 0, con[2]
    assert sin[1] > 0 and con[1] == sin[1], (sin[1], con[1])


def test_ninguna_prueba_ni_guion_del_frontend_usa_la_ruta_sin_decodificar():
    """065:RF-9 — `URL.pathname` deja «%20» en la ruta: se lee con `fileURLToPath`."""
    ficheros = [*(FRONT / 'test').glob('*.mjs'), *(FRONT / 'scripts').glob('*.mjs')]
    assert ficheros
    usan = [p.name for p in ficheros if re.search(r'import\.meta\.url\)\s*\.pathname', p.read_text(encoding='utf-8'))]
    assert usan == []


def test_el_lock_declara_lo_que_instala_con_las_versiones_de_node_y_npm():
    """065:RF-8 — `npm ci` instala del lock íntegro; Node y npm compatibles quedan declarados."""
    paquete = json.loads((FRONT / 'package.json').read_text(encoding='utf-8'))
    lock = json.loads((FRONT / 'package-lock.json').read_text(encoding='utf-8'))
    raiz_lock = lock['packages']['']
    assert paquete['engines'].get('node') and paquete['engines'].get('npm')
    assert raiz_lock.get('engines') == paquete['engines']
    assert raiz_lock.get('dependencies') == paquete['dependencies']
    assert raiz_lock.get('devDependencies') == paquete['devDependencies']
    sin_huella = [n for n, d in lock['packages'].items() if n and not d.get('link') and not d.get('integrity')]
    assert sin_huella == [], 'Paquetes del lock sin huella de integridad'
    lanzador = (RAIZ / 'run_gui.bat').read_text(encoding='utf-8')
    assert 'npm ci' in lanzador and 'npm install' not in lanzador
