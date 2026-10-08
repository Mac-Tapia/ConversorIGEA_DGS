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
    """001:RF-16 — ni ``igea_dgs.gui`` ni su ``settings.py`` de ventana."""
    assert importlib.util.find_spec('igea_dgs.gui') is None
    assert importlib.util.find_spec('igea_dgs.settings') is None


def test_el_cli_no_ofrece_gui():
    """001:RF-16 — ``igea-dgs gui`` da error de uso."""
    from igea_dgs.cli import _parser

    with pytest.raises(SystemExit) as info:
        _parser().parse_args(['gui'])
    assert info.value.code == 2


def test_no_hay_script_instalable():
    """001:RF-16 — ``pyproject.toml`` no declara ``igea-dgs-gui``."""
    scripts = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    assert 'igea-dgs-gui' not in scripts['project']['scripts']
    assert not any('gui' in destino for destino in scripts['project']['scripts'].values())


def test_ningun_lanzador_abre_la_gui():
    """001:RF-16 — ningún ``.bat`` arranca ``igea_dgs.gui``."""
    lanzadores = [p for p in RAIZ.glob('*.bat')] + [p for p in (RAIZ / 'tools').glob('*.bat')]
    culpables = [p.name for p in lanzadores
                 if 'igea_dgs.gui' in p.read_text(encoding='utf-8', errors='replace')]
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
