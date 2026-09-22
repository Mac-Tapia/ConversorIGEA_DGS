import subprocess
import sys
from pathlib import Path


def test_documented_cli_commands_are_registered():
    help_text = subprocess.run(
        [sys.executable, "-m", "igea_dgs.cli", "--help"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for command in ("inspect", "validate-input", "convert", "import-pf", "validate-pf", "study", "run", "catalog"):
        assert command in help_text


def test_documented_operational_files_exist():
    for path in (
        "docs/OPERATIONS_RUNBOOK.md", "docs/DATA_DICTIONARY.md",
        "docs/EQUIPMENT_CATALOG.md", "scripts/acceptance.ps1",
    ):
        assert Path(path).is_file()
