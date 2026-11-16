"""Spec 112 T13: el generador de exports sintéticos vive en el núcleo y no cambia ni un byte (112:RF-13).

El benchmark publicable sale de ``ExportSpec`` con las estadísticas agregadas del origen, así que el generador pasa de
``tests/synthetic_export.py`` a ``benchmarks/sintetico.py`` (decisión del coordinador, opción A, 2026-11-14). Las pruebas
de toda la suite lo usan: con los campos nuevos apagados, la salida tiene que ser la de antes byte a byte. Se compara con
la revisión anterior al cambio (``ANTERIOR``).
"""
from __future__ import annotations

import importlib.util

import hashlib
import subprocess
import sys
import types
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
#: La última revisión con el generador en tests/ (e182c823, punta del 15-11): contra ella se compara byte a
#: byte. Un cambio intencionado del generador actualiza esta revisión en el mismo commit.
ANTERIOR = 'e182c8233294975d916a78244ca69bc435a8e157'


def _generador_anterior():
    try:
        fuente = subprocess.run(['git', 'show', f'{ANTERIOR}:tests/synthetic_export.py'], cwd=RAIZ, capture_output=True,
                                check=True, text=True, encoding='utf-8').stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.fail(f'sin git o sin la revisión {ANTERIOR}: no hay con qué comparar')
    modulo = types.ModuleType('synthetic_export_anterior')
    sys.modules[modulo.__name__] = modulo      # las dataclasses buscan su módulo en sys.modules
    try:
        exec(compile(fuente, 'synthetic_export_anterior', 'exec'), modulo.__dict__)
    finally:
        sys.modules.pop(modulo.__name__, None)
    return modulo


def _huellas(rutas):
    return [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in rutas]


@pytest.mark.parametrize('layout', ['reducido', 'completo'])
@pytest.mark.parametrize('semilla', [None, 1, 7, 42, 2024, 99991])
def test_misma_salida_que_el_generador_anterior(tmp_path, semilla, layout):
    """112:RF-13 — con los campos nuevos apagados, write_export da los mismos tres TXT que antes del cambio."""
    assert importlib.util.find_spec('convertersmartgrid.benchmarks.sintetico'), 'falta convertersmartgrid.benchmarks.sintetico'
    import synthetic_export as nuevo
    viejo = _generador_anterior()
    kw = dict(feeders=4, sections_per_feeder=5, loads_per_feeder=3, sectionalizers_per_feeder=1, seed=semilla,
              layout=layout, header_only_feeders=1)
    a = viejo.write_export(viejo.ExportSpec(**kw), tmp_path / 'antes')
    b = nuevo.write_export(nuevo.ExportSpec(**kw), tmp_path / 'despues')
    assert _huellas(a) == _huellas(b)


def test_la_reexportacion_es_explicita():
    """112:RF-13 — tests/synthetic_export.py reexporta por nombre, también lo privado que alguna prueba use."""
    assert importlib.util.find_spec('convertersmartgrid.benchmarks.sintetico'), 'falta convertersmartgrid.benchmarks.sintetico'
    import synthetic_export as S

    from convertersmartgrid.benchmarks import sintetico as N
    for nombre in ('ExportSpec', 'FeederSize', 'write_export', 'CRS_SINTETICO', '_pad', 'FMT_NODE',
                   'FMT_SECTION', 'FMT_CUSTOMERLOADS', 'FMT_BD_LINE', 'FMT_BD_CABLE'):
        assert getattr(S, nombre) is getattr(N, nombre), nombre
    assert 'import *' not in Path(S.__file__).read_text(encoding='utf-8')


def test_longitudes_y_cargas_por_cuantiles(tmp_path):
    """112:RF-13 — encendidos, los tramos y las cargas siguen los cuantiles dados y las coordenadas cuadran con la longitud."""
    assert importlib.util.find_spec('convertersmartgrid.benchmarks.sintetico'), 'falta convertersmartgrid.benchmarks.sintetico'
    import math

    from convertersmartgrid.benchmarks.sintetico import ExportSpec
    from synthetic_export import load_export
    cuantiles = (2.0, 10.0, 50.0, 200.0, 1000.0)
    ds = load_export(ExportSpec(feeders=3, sections_per_feeder=40, loads_per_feeder=10, seed=5,
                                longitudes_m=cuantiles, cargas_kw=(1.0, 5.0, 20.0, 80.0, 300.0)), tmp_path)
    largos = sorted(float(c['Length']) for c in ds.line_configurations.values())
    assert largos[0] >= 2.0 and largos[-1] <= 1000.0 and len(set(largos)) > 10
    cargas = sorted(float(c['Value1']) for c in ds.customer_loads.values())
    assert cargas[0] >= 1.0 and cargas[-1] <= 300.0 and len(set(cargas)) > 5
    for sid, s in ds.sections.items():
        a, b = ds.nodes[s['FromNodeID']], ds.nodes[s['ToNodeID']]
        d = math.dist((float(a['CoordX']), float(a['CoordY'])), (float(b['CoordX']), float(b['CoordY'])))
        assert math.isclose(d, float(ds.line_configurations[sid]['Length']), rel_tol=1e-3, abs_tol=0.01)
