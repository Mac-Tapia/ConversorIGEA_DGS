"""La interfaz React/FastAPI es la unica interfaz visual del conversor."""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest

from igea_dgs.cli import _parser

ROOT = Path(__file__).resolve().parents[1]
LEGACY_FILES = (
    'src/igea_dgs/gui.py',
    'run_gui.bat',
    'run_gui_escritorio.bat',
    'tests/test_gui_wiring.py',
)
OPERATIONAL_DOCS = (
    'README.md',
    'CODIGO_FUENTE.md',
    'CLAUDE.md',
    'requirements.txt',
    'docs/MANUAL_COMANDOS.md',
    'docs/POWERFACTORY_ACCEPTANCE.md',
)
LEGACY_INSTRUCTIONS = ('run_gui', 'igea_dgs.gui', 'igea-dgs-gui', 'tkinter')


def test_project_exposes_only_the_web_visual_entry_point():
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    scripts = project['project']['scripts']
    assert scripts['igea-dgs-web'] == 'igea_dgs.web.__main__:main'
    assert 'igea-dgs-gui' not in scripts


def test_cli_rejects_the_removed_gui_subcommand():
    with pytest.raises(SystemExit) as exc:
        _parser().parse_args(['gui'])
    assert exc.value.code == 2


def test_legacy_gui_module_and_launchers_are_absent():
    assert importlib.util.find_spec('igea_dgs.gui') is None
    assert not [relative for relative in LEGACY_FILES if (ROOT / relative).exists()]


def test_run_web_is_the_single_windows_launcher():
    launcher = (ROOT / 'run_web.bat').read_text(encoding='utf-8').lower()
    assert '-m igea_dgs.web' in launcher
    assert 'frontend\\dist\\index.html' in launcher
    assert 'npm run build' in launcher
    assert not any(token in launcher for token in LEGACY_INSTRUCTIONS)


@pytest.mark.parametrize('relative', OPERATIONAL_DOCS)
def test_operational_documentation_has_no_legacy_gui_instruction(relative: str):
    text = (ROOT / relative).read_text(encoding='utf-8').lower()
    assert not [token for token in LEGACY_INSTRUCTIONS if token in text]
