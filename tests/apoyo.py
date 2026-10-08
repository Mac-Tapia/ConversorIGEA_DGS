"""Auxiliares compartidos por varias pruebas.

Estaban copiados: ``_module`` (cargar un script de ``tools/``) en cuatro ficheros y
``_wait`` (esperar a un trabajo de la API) en dos, con plazos distintos sin motivo.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


def cargar_herramienta(fichero: str, nombre: str | None = None, *,
                       tools_en_path: bool = False) -> ModuleType:
    """Importa ``tools/<fichero>`` como módulo, sin que ``tools/`` sea un paquete.

    ``tools_en_path`` deja ``tools/`` en ``sys.path`` mientras se ejecuta el módulo,
    para los scripts que importan a sus vecinos (``aplicar_lote_cargas.py``).
    """
    path = TOOLS / fichero
    spec = importlib.util.spec_from_file_location(nombre or path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    if tools_en_path:
        sys.path.insert(0, str(TOOLS))
    try:
        spec.loader.exec_module(module)
    finally:
        if tools_en_path:
            sys.path.remove(str(TOOLS))
    return module


def esperar_trabajo(client, job: dict, timeout: float = 60.0) -> dict:
    """Espera a que un trabajo de la API termine y devuelve su estado final."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state['status'] in ('done', 'failed', 'cancelled'):
            return state
        time.sleep(0.05)
    raise AssertionError(f"el trabajo {job.get('title', job['id'])} no terminó en {timeout} s")
