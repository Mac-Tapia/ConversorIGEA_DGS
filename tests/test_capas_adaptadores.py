"""Spec 002 T7 (a) — los casos de uso no importan adaptadores: los piden por su puerto (002:RF-1, RF-2, RF-9).

batch, cargas_pf y reglas resuelven cada adaptador interno por su entry point del grupo
``convertersmartgrid.adaptadores``, al usarlo y solo el pedido; sin él, un error claro que dice cómo arreglarlo.
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import subprocess
import sys
import tomllib
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'src' / 'convertersmartgrid'
CASOS_DE_USO = ('batch', 'cargas_pf', 'reglas')
ADAPTADORES = ('dgs', 'export_tables', 'geography', 'preview', 'validate', 'feeder_metadata', 'oraculo', 'loads')


def _registro():
    """Lo nuevo de la pieza: su ausencia es la falla de la aserción, no un error de importación."""
    mod = importlib.import_module('convertersmartgrid.registro_modulos')
    assert hasattr(mod, 'adaptador') and hasattr(mod, 'AdaptadorFaltante'), \
        'falta registro_modulos.adaptador (002 T7, a)'
    return mod


def _declarados():
    datos = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    return dict(datos['project'].get('entry-points', {}).get('convertersmartgrid.adaptadores', {}))


def test_002_rf1_ningun_caso_de_uso_importa_un_adaptador_y_la_deuda_de_capas_queda_vacia():
    """002:RF-1, RF-2 — ni batch, ni cargas_pf, ni reglas importan dgs, export_tables, geography, preview, validate,
    feeder_metadata, oraculo ni loads (tampoco dentro de una función), y la lista de excepciones de capa está vacía."""
    _registro()
    for nombre in CASOS_DE_USO:
        arbol = ast.parse((SRC / f'{nombre}.py').read_text(encoding='utf-8'))
        importados = {n.module.split('.')[-1] for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
        assert not importados & set(ADAPTADORES), f'{nombre} importa {sorted(importados & set(ADAPTADORES))}'
    deuda = json.loads((RAIZ / 'docs' / 'implementacion065' / 'deuda_arquitectura.json').read_text(encoding='utf-8'))
    assert deuda['excepciones'] == {}
    salida = subprocess.run([sys.executable, '-I', str(RAIZ / 'tools' / 'arquitectura.py'), '--json'], cwd=RAIZ,
                            capture_output=True, text=True, encoding='utf-8')
    assert salida.returncode == 0, salida.stdout[-2000:] + salida.stderr[-2000:]


def test_002_rf9_cada_adaptador_esta_declarado_con_su_puerto_y_lo_cumple():
    """002:RF-9 — cada adaptador que piden los casos de uso tiene su entry point en el pyproject, su puerto en
    puertos.PUERTOS_ADAPTADORES con el mismo nombre (aparte de los de los enchufables), y su módulo trae todo lo que el puerto pide."""
    _registro()
    from convertersmartgrid.puertos import PUERTOS, PUERTOS_ADAPTADORES
    declarados = _declarados()
    pedidos = set()
    for nombre in CASOS_DE_USO:
        texto = (SRC / f'{nombre}.py').read_text(encoding='utf-8')
        pedidos |= {n.args[0].value for n in ast.walk(ast.parse(texto)) if isinstance(n, ast.Call)
                    and getattr(n.func, 'id', '') in ('adaptador', '_del_adaptador') and n.args
                    and isinstance(n.args[0], ast.Constant)}
    assert pedidos and pedidos <= set(declarados), f'sin entry point: {sorted(pedidos - set(declarados))}'
    for puerto, valor in declarados.items():
        assert puerto in PUERTOS_ADAPTADORES and puerto not in PUERTOS, f'{puerto}: sin su puerto interno'
        modulo = importlib.import_module(valor)
        assert not [a for a in PUERTOS_ADAPTADORES[puerto] if not hasattr(modulo, a)], (puerto, valor)


def test_002_rf9_resolucion_perezosa_un_entry_point_roto_que_no_se_pide_no_rompe(monkeypatch):
    """002:RF-9 — solo se resuelve el puerto pedido: con un entry point roto en los metadatos, pedir otro funciona; el
    roto, al pedirlo, da el error claro con el puerto y la orden que lo arregla, y uno que falta también."""
    mod = _registro()
    monkeypatch.setattr(mod, '_ADAPTADORES', {})
    monkeypatch.delenv(mod.VARIABLE_DESDE_PYPROJECT, raising=False)
    metadatos = [EntryPoint('salida-dgs', 'convertersmartgrid.dgs', 'convertersmartgrid.adaptadores'),
                 EntryPoint('oraculo', 'convertersmartgrid.modulo_que_no_existe', 'convertersmartgrid.adaptadores')]
    vistos = []

    def entry_points(group, name):
        vistos.append(name)
        return [e for e in metadatos if e.group == group and e.name == name]
    monkeypatch.setattr(mod, 'entry_points', entry_points)
    from convertersmartgrid import dgs
    assert mod.adaptador('salida-dgs') is dgs and vistos == ['salida-dgs']
    with pytest.raises(mod.AdaptadorFaltante, match=r'«oraculo».*pip install -e \. --no-deps'):
        mod.adaptador('oraculo')
    with pytest.raises(mod.AdaptadorFaltante, match=r'falta el entry point «geografia».*puerto geografia'):
        mod.adaptador('geografia')
    assert not issubclass(mod.AdaptadorFaltante, ImportError), 'un «except ImportError» no debe tragarlo'


def test_002_rf9_desde_el_pyproject_del_arbol_para_un_worktree_sin_reinstalar(monkeypatch):
    """002:RF-9 — con CSG_ENTRY_POINTS_DESDE_PYPROJECT=1, el adaptador sale del pyproject del árbol (un worktree que
    declara adaptadores que el .venv compartido aún no tiene instalados), y la conversión los usa."""
    mod = _registro()
    monkeypatch.setattr(mod, '_ADAPTADORES', {})
    monkeypatch.setenv(mod.VARIABLE_DESDE_PYPROJECT, '1')
    monkeypatch.setattr(mod, 'entry_points', lambda **_k: pytest.fail('no se leen los metadatos instalados'))
    from convertersmartgrid import geography
    assert mod.adaptador('geografia') is geography
    from convertersmartgrid import batch
    assert batch.exigir_crs_origen('EPSG:32718') == geography.exigir_crs_origen('EPSG:32718')
