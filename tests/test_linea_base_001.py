"""001:RF-14 — la reorganización no cambia ningún DGS que hoy sea correcto.

Regenera con los TXT reales y compara contra ``output/linea_base_001.json``, que se crea
una vez, con el código anterior a la reorganización, con ``tools/linea_base_dgs.py``.
Se omite sin las variables ``IGEA_*``, sin línea base, o si las entradas o el catálogo
del proyecto no son los mismos con los que se hizo: entonces no hay nada que comparar.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def _herramienta():
    ruta = RAIZ / 'tools' / 'linea_base_dgs.py'
    spec = importlib.util.spec_from_file_location('linea_base_dgs', ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _diferencias(antes: dict[str, str], ahora: dict[str, str]) -> list[str]:
    return ([f'falta {k}' for k in sorted(antes.keys() - ahora.keys())]
            + [f'sobra {k}' for k in sorted(ahora.keys() - antes.keys())]
            + [f'cambia {k}' for k in sorted(antes.keys() & ahora.keys()) if antes[k] != ahora[k]])


def test_dgs_identicos_a_la_linea_base(igea_paths, tmp_path):
    """001:RF-14 — mismos DGS byte a byte, por alimentador y en la red unida."""
    lb = _herramienta()
    if not lb.DESTINO.is_file():
        pytest.skip(f'Sin línea base: genérela con tools/linea_base_dgs.py ({lb.DESTINO})')
    base = json.loads(lb.DESTINO.read_text(encoding='utf-8'))
    red, loads, equipment = igea_paths
    if lb.huella_entradas(red, loads, equipment) != base['entradas']:
        pytest.skip('La línea base se hizo con otras entradas u otro catálogo del proyecto')

    ahora = lb.calcular(red, loads, equipment, tmp_path)

    assert ahora['parametros'] == base['parametros']
    assert ahora['resumen_lote'] == base['resumen_lote']
    assert ahora['estado_red_unida'] == base['estado_red_unida']
    cambios = (_diferencias(base['dgs_alimentadores'], ahora['dgs_alimentadores'])
               + _diferencias(base['dgs_red_unida'], ahora['dgs_red_unida']))
    assert not cambios, f'{len(cambios)} DGS distintos de la línea base: {cambios[:20]}'


def _base_para(igea_paths):
    lb = _herramienta()
    if not lb.DESTINO.is_file():
        pytest.skip(f'Sin línea base: genérela con tools/linea_base_dgs.py ({lb.DESTINO})')
    base = json.loads(lb.DESTINO.read_text(encoding='utf-8'))
    red, loads, equipment = igea_paths
    if lb.huella_entradas(red, loads, equipment) != base['entradas']:
        pytest.skip('La línea base se hizo con otras entradas u otro catálogo del proyecto')
    return lb, base


def test_dgs_identicos_con_cuatro_procesos(igea_paths, tmp_path):
    """002:RF-20 — con workers=4 los DGS por alimentador son los de la línea base."""
    lb, base = _base_para(igea_paths)
    ahora = lb.calcular(*igea_paths, tmp_path, workers=4)
    cambios = _diferencias(base['dgs_alimentadores'], ahora['dgs_alimentadores'])
    assert not cambios, f'{len(cambios)} DGS distintos con workers=4: {cambios[:20]}'


def test_dgs_identicos_por_la_via_access(tmp_path):
    """002:RF-20 — la vía Access también da los DGS de la línea base."""
    import os

    pytest.importorskip('pyodbc')
    mdb = os.environ.get('IGEA_MDB', '').strip()
    if not mdb:
        pytest.skip('Defina IGEA_MDB para comparar la vía Access')
    equipos = os.environ.get('IGEA_EQUIPMENT_MDB', '').strip() or None
    lb = _herramienta()
    if not lb.DESTINO.is_file():
        pytest.skip(f'Sin línea base: genérela con tools/linea_base_dgs.py ({lb.DESTINO})')
    base = json.loads(lb.DESTINO.read_text(encoding='utf-8')).get('mdb')
    if base is None:
        pytest.skip('La línea base no tiene vía Access: regenérela con --mdb')
    mdb, equipos = Path(mdb), Path(equipos) if equipos else None
    if lb.huella_mdb(mdb, equipos) != base['entradas']:
        pytest.skip('La línea base de Access se hizo con otras bases u otro catálogo')

    ahora = lb.calcular_mdb(mdb, equipos, tmp_path)

    assert ahora['resumen_lote'] == base['resumen_lote']
    cambios = _diferencias(base['dgs_alimentadores'], ahora['dgs_alimentadores'])
    assert not cambios, f'{len(cambios)} DGS distintos por la vía Access: {cambios[:20]}'
