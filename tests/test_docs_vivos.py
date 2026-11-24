"""009:RF-16 — todo fichero versionado de docs/ lo alcanza algo vivo: el código, una prueba, una spec, un manual o una
configuración, directamente o por una cadena de citas.

El 2026-11-24 la auditoría de limpieza halló 50 documentos históricos que solo se citaban entre sí o desde tareas cerradas.
Se retiraron (sus citas apuntan a git); esta prueba impide que vuelva a entrar un documento huérfano.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
#: Lo vivo por sí mismo: el producto, sus pruebas, sus specs, los manuales y lo que el código lee por carpeta.
RAICES = ('src/', 'tools/', 'tests/', 'tests_ml/', 'frontend/', '.githooks/', '.github/', 'pyproject.toml', 'instalador/',
          'run_gui.bat', 'specs/', 'CLAUDE.md', 'README.md', '.claude/', 'config/', 'docs/MANUAL_', 'docs/ARQUITECTURA.md',
          'docs/constitution.md', 'docs/procedimientos/', 'docs/regresiones/', 'docs/architecture/', 'input/')
#: Generados: no hacen vivo a nada por citarlo (repiten el inventario entero).
GENERADOS = {'CODIGO_FUENTE.md', 'docs/ARQUITECTURA_CATALOGO.md', 'specs/README.md'}
BINARIOS = {'.png', '.jpg', '.pdf', '.ico', '.xlsx', '.woff2', '.gz', '.zip', '.parquet', '.npz'}


def _versionados() -> list[str]:
    salida = subprocess.run(['git', '-C', str(RAIZ), 'ls-files', '-z'], capture_output=True, check=True).stdout
    return [f for f in salida.decode('utf-8').split('\0') if f]


def _claves(f: str) -> set[str]:
    base = os.path.basename(f)
    raiz = os.path.splitext(base)[0]
    return {f, base} | ({raiz} if len(raiz) > 12 else set())


def test_009_rf16_ningun_fichero_de_docs_huerfano():
    ficheros = _versionados()
    textos = {}
    for f in ficheros:
        if f in GENERADOS or os.path.splitext(f)[1].lower() in BINARIOS:
            continue
        ruta = RAIZ / f
        try:
            if ruta.stat().st_size < 5_000_000:
                textos[f] = ruta.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            pass
    vivo = {f for f in ficheros if f.startswith(RAICES)}
    pendientes = [f for f in ficheros if f.startswith('docs/') and f not in vivo]
    cambio = True
    while cambio:
        cambio = False
        for f in pendientes:
            if f in vivo:
                continue
            claves = _claves(f)
            if any(g != f and any(k in textos.get(g, '') for k in claves) for g in vivo):
                vivo.add(f)
                cambio = True
    huerfanos = sorted(f for f in pendientes if f not in vivo)
    assert huerfanos == [], f'documentos que no alcanza nada vivo (009:RF-16): {huerfanos}'
