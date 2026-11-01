"""La GUI Tkinter está retirada (spec 001, RF-16).

La web cubre su uso, y mantenerla era una tercera vía de lectura que adaptar en RF-1.
Estas pruebas cierran cada puerta por la que podría volver.
"""
from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def test_el_modulo_ya_no_existe():
    """001:RF-16 — ni ``convertersmartgrid.gui`` ni su ``settings.py`` de ventana."""
    assert importlib.util.find_spec('convertersmartgrid.gui') is None
    assert importlib.util.find_spec('convertersmartgrid.settings') is None


def test_el_cli_no_ofrece_gui():
    """001:RF-16 — ``convertersmartgrid gui`` da error de uso."""
    from convertersmartgrid.cli import _parser

    with pytest.raises(SystemExit) as info:
        _parser().parse_args(['gui'])
    assert info.value.code == 2


def test_no_hay_script_instalable():
    """001:RF-16 — ``pyproject.toml`` no declara ``convertersmartgrid-gui``."""
    scripts = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    assert 'convertersmartgrid-gui' not in scripts['project']['scripts']
    assert not any('gui' in destino for destino in scripts['project']['scripts'].values())


def test_ningun_lanzador_abre_la_gui():
    """001:RF-16 — ningún ``.bat`` arranca ``convertersmartgrid.gui``."""
    lanzadores = [p for p in RAIZ.glob('*.bat')] + [p for p in (RAIZ / 'tools').glob('*.bat')]
    culpables = [p.name for p in lanzadores
                 if 'convertersmartgrid.gui' in p.read_text(encoding='utf-8', errors='replace')]
    assert not culpables
    assert not (RAIZ / 'run_gui_escritorio.bat').exists()


def test_src_no_importa_tkinter():
    """001:RF-16 — ningún módulo del conversor depende de Tk."""
    culpables = [
        p.relative_to(RAIZ).as_posix() for p in (RAIZ / 'src').rglob('*.py')
        if any(linea.lstrip().startswith(('import tkinter', 'from tkinter'))
               for linea in p.read_text(encoding='utf-8').splitlines())
    ]
    assert not culpables
