"""Spec 112: la medición de escala de la web y su API con redes sintéticas (112:RF-20, 112:RF-21; 009).

La prueba rápida mide 10 alimentadores con pocas repeticiones y solo comprueba la forma del resultado, no tiempos: un
tope de milisegundos dependería de la máquina y de lo que corra a la vez. La corrida de 10, 50 y 200 con sus
repeticiones es una corrida aparte, con su propio registro.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HERRAMIENTA = RAIZ / 'tools' / 'benchmark_escala_web.py'


def _correr(*args, cwd, timeout=600):
    env = {k: v for k, v in os.environ.items() if not k.startswith('CSG_')}
    env['PYTHONPATH'] = os.pathsep.join([str(RAIZ / 'src'), str(RAIZ / 'tools')])
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run([sys.executable, str(HERRAMIENTA), *args], cwd=cwd, env=env, capture_output=True,
                          text=True, encoding='utf-8', timeout=timeout, check=False)


def _herramienta():
    assert HERRAMIENTA.is_file(), 'falta tools/benchmark_escala_web.py'
    sys.path.insert(0, str(RAIZ / 'tools'))
    try:
        import benchmark_escala_web
    finally:
        sys.path.pop(0)
    return benchmark_escala_web


def test_help_sin_digsilent(tmp_path):
    """112:RF-20 — ``--help`` sale con 0, sin DIgSILENT, y dice que corre en local con redes sintéticas."""
    assert HERRAMIENTA.is_file(), 'falta tools/benchmark_escala_web.py'
    r = _correr('--help', cwd=tmp_path, timeout=120)
    assert r.returncode == 0 and 'usage' in r.stdout.lower(), r.stderr
    assert 'local' in r.stdout and 'sintéticas' in r.stdout and '--tamanos' in r.stdout


def test_por_defecto_mide_10_50_y_200():
    """112:RF-20 — sin opciones, los tres tamaños del benchmark de escala, y ninguno grabado en otro sitio."""
    b = _herramienta()
    assert tuple(b._argumentos([]).tamanos) == (10, 50, 200)
    assert b._argumentos(['--tamanos', '7', '13']).tamanos == [7, 13]


def test_un_tamano_imposible_es_un_error_de_uso(tmp_path):
    """112:RF-20 — cero alimentadores o una sola repetición no miden nada: error de uso, sin traza ni resultado."""
    assert HERRAMIENTA.is_file(), 'falta tools/benchmark_escala_web.py'
    for args in (('--tamanos', '0'), ('--tamanos', '10', '--repeticiones', '1')):
        r = _correr(*args, '--salida', 'r.json', cwd=tmp_path, timeout=120)
        assert r.returncode == 2 and 'Traceback' not in r.stderr, (args, r.stderr)
        assert not (tmp_path / 'r.json').exists()


def test_percentiles_con_interpolacion():
    """112:RF-20 — p50 y p95 con interpolación lineal, y sin valores no hay percentil (nunca un cero inventado)."""
    b = _herramienta()
    assert b.percentil([5.0, 1.0, 3.0, 2.0, 4.0], 50) == 3.0
    assert b.percentil([1.0, 2.0, 3.0, 4.0, 5.0], 95) == pytest.approx(4.8)
    assert b.percentil([7.0], 95) == 7.0
    with pytest.raises(ValueError):
        b.percentil([], 50)


def test_diez_alimentadores_sinteticos_por_la_api(tmp_path):
    """112:RF-20, 112:RF-21 — de punta a punta con 10 alimentadores sintéticos: la API los lista todos, cada petición
    con su primera llamada aparte, su p50 ≤ p95 y su tamaño; la memoria pico del proceso; la revisión del código; y el
    dibujo de la pantalla «no medido» con su motivo, nunca un cero."""
    assert HERRAMIENTA.is_file(), 'falta tools/benchmark_escala_web.py'
    salida = tmp_path / 'resultado' / 'escala.json'
    r = _correr('--tamanos', '10', '--repeticiones', '3', '--tramos', '20', '--cargas', '6', '--salida', str(salida),
                cwd=tmp_path)
    assert r.returncode == 0, r.stderr[-3000:]
    datos = json.loads(salida.read_text(encoding='utf-8'))
    assert datos['revision']['commit'] and 'cambios_sin_registrar' in datos['revision']
    assert datos['red_sintetica']['semilla'] == 112 and datos['repeticiones'] == 3
    [medida] = datos['tamanos']
    assert medida['alimentadores'] == 10 and medida['alimentadores_listados'] == 10
    assert medida['tramos'] > 0 and medida['cargas'] > 0 and medida['carga_red_s'] > 0
    assert {'espacio', 'alimentadores', 'sed_de_un_alimentador'} <= set(medida['api'])
    for nombre, api in medida['api'].items():
        assert api['n'] == 3 and api['primera_ms'] > 0, nombre
        assert 0 < api['p50_ms'] <= api['p95_ms'] <= api['max_ms'], (nombre, api)
        assert api['bytes'] > 0, nombre
    assert 0 < medida['ram_base_mib'] <= medida['ram_pico_mib']
    render = medida['render']
    assert render['medido'] is False and render['motivo'].startswith('no medido')
    assert not [v for v in render.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
