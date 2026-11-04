"""081:RF-1 — ningún nombre sin definir en el código: revienta solo cuando esa rama se ejecuta.

`con_proyecto_optimizar` usaba `BIBLIOTECA_TIPOS` sin importarlo, y daba `NameError` en la rama del plan completo de las
zonas, la que menos pruebas cubren (2026-11-03). Ruff (F821) lo ve sin ejecutar nada.
"""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
import subprocess
import sys

RAIZ = Path(__file__).resolve().parent.parent


def test_ningun_nombre_sin_definir():
    """081:RF-1 — F821 limpio en `src/` y `tools/`."""
    r = subprocess.run([sys.executable, '-m', 'ruff', 'check', '--select', 'F821', '--no-cache', 'src', 'tools'],
                       cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    assert r.returncode == 0, r.stdout[-2000:]


def test_ninguna_funcion_definida_dos_veces():
    """081:RF-1 — la última definición tapa a la primera: `_barras_de` rompió las obras de migración (2026-11-04)."""
    repetidas = []
    for carpeta in ('src', 'tools'):
        for fichero in (RAIZ / carpeta).rglob('*.py'):
            arbol = ast.parse(fichero.read_text(encoding='utf-8'))
            nombres = Counter(n.name for n in arbol.body
                              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
            repetidas += [f'{fichero.relative_to(RAIZ)}: {nombre}' for nombre, veces in nombres.items() if veces > 1]
    assert not repetidas, repetidas
