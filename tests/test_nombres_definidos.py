"""081:RF-1 — ningún nombre sin definir en el código: revienta solo cuando esa rama se ejecuta.

`con_proyecto_optimizar` usaba `BIBLIOTECA_TIPOS` sin importarlo, y daba `NameError` en la rama del plan completo de las
zonas, la que menos pruebas cubren (2026-11-03). Ruff (F821) lo ve sin ejecutar nada.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

RAIZ = Path(__file__).resolve().parent.parent


def test_ningun_nombre_sin_definir():
    """081:RF-1 — F821 limpio en `src/` y `tools/`."""
    r = subprocess.run([sys.executable, '-m', 'ruff', 'check', '--select', 'F821', '--no-cache', 'src', 'tools'],
                       cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    assert r.returncode == 0, r.stdout[-2000:]
