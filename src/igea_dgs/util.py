"""Utilidades de E/S y de números compartidas por el motor y la web.

Estaban copiadas hasta en siete sitios (diagnóstico del 2026-10-07, B5): el hash de
fichero en cuatro, la escritura atómica de JSON en tres con formatos que ya divergían.
``tests/test_util.py`` falla si alguna vuelve a copiarse en ``src/igea_dgs``.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
from pathlib import Path
from types import ModuleType
from typing import Any


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: Any) -> None:
    """Escribe en ``<nombre>.tmp`` y lo publica con ``replace``: nunca queda a medias.

    Se serializa antes de abrir el temporal, así que un error de serialización deja el
    fichero anterior intacto. ``default=str`` admite rutas y fechas en los manifiestos.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8',
    )
    temporary.replace(path)


def finite_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def importar_opcional(modulo: str, error: Exception) -> ModuleType:
    """Importa una dependencia opcional o lanza ``error``, que elige quien llama.

    Cada vía conserva su excepción (``DownloadError``, ``ArcGISError``…) porque sus
    llamadores la capturan por tipo; lo común es solo el intento de importar.
    """
    try:
        return importlib.import_module(modulo)
    except ImportError as exc:
        raise error from exc


def nombre_seguro(texto: str, *, maximo: int | None = None, defecto: str = 'GRUPO') -> str:
    """Nombre apto para fichero y para PowerFactory: letras, dígitos, ``-`` y ``_``."""
    limpio = ''.join(c if c.isalnum() or c in '-_' else '_' for c in texto)
    return limpio[:maximo] or defecto
