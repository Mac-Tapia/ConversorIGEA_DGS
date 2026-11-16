"""Spec 112: la herramienta local del benchmark anonimizado (112:RF-1; 009).

Se invoca sin DIgSILENT y sin red; ``--help`` funciona sin datos, y un fichero que falta es un error de uso (código 1),
no una traza.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HERRAMIENTA = RAIZ / 'tools' / 'benchmark_anonimo.py'


def _correr(*args, cwd):
    env = {k: v for k, v in os.environ.items() if not k.startswith('CSG_')}
    env['PYTHONPATH'] = os.pathsep.join([str(RAIZ / 'src'), str(RAIZ / 'tools')])
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run([sys.executable, str(HERRAMIENTA), *args], cwd=cwd, env=env, capture_output=True,
                          text=True, encoding='utf-8', timeout=120)


def test_help_sin_digsilent(tmp_path):
    """112:RF-1 — ``--help`` sale con 0 y dice que todo corre en local."""
    assert HERRAMIENTA.is_file(), 'falta tools/benchmark_anonimo.py'
    r = _correr('--help', cwd=tmp_path)
    assert r.returncode == 0 and 'usage' in r.stdout.lower()
    assert 'local' in r.stdout


def test_un_fichero_que_falta_es_un_error_de_uso(tmp_path):
    """112:RF-1 — sin el trío no se genera nada: código 1 y un mensaje claro, sin traza ni carpeta de destino."""
    assert HERRAMIENTA.is_file(), 'falta tools/benchmark_anonimo.py'
    r = _correr('--red', 'no.txt', '--carga', 'no.txt', '--equipo', 'no.txt', '--destino', 'b', cwd=tmp_path)
    assert r.returncode == 1 and 'No existe' in r.stderr and 'Traceback' not in r.stderr
    assert not (tmp_path / 'b').exists()


def test_emite_un_benchmark_de_una_red_sintetica(tmp_path):
    """112:RF-1, RF-5 — con un trío sintético y un perfil neutro, emite el benchmark en local (código 0) con su
    manifiesto de uso local; repetirlo sobre el mismo destino no lo pisa (código 1)."""
    import json

    import pytest
    pytest.importorskip('pandapower')
    from synthetic_export import ExportSpec, write_export
    assert HERRAMIENTA.is_file(), 'falta tools/benchmark_anonimo.py'
    red, carga, equipo = write_export(ExportSpec(feeders=2, seed=11, layout='reducido', origin_x=300000.0,
                                                 origin_y=8200000.0), tmp_path / 'origen')
    perfil = tmp_path / 'perfil.json'
    perfil.write_text(json.dumps({'nombre': 'prueba'}), encoding='utf-8')
    args = ('--red', str(red), '--carga', str(carga), '--equipo', str(equipo), '--destino', str(tmp_path / 'b'),
            '--perfil', str(perfil), '--carpeta-semilla', str(tmp_path / 'local'))
    r = _correr(*args, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    manifiesto = json.loads((tmp_path / 'b' / 'manifiesto.json').read_text(encoding='utf-8'))
    assert manifiesto['uso_local'] is True and 'uso local' in r.stdout
    assert str(tmp_path) not in (tmp_path / 'b' / 'manifiesto.json').read_text(encoding='utf-8')
    assert list((tmp_path / 'local' / 'benchmarks').glob('*/semilla')), 'la semilla secreta no quedó en la carpeta local'
    otra = _correr(*args, cwd=tmp_path)
    assert otra.returncode == 1 and 'ya existe' in otra.stderr and 'Traceback' not in otra.stderr
