"""Lo que un servicio de la web exige antes de trabajar, común a todos ellos (002:RF-4).

Aparte de ``services`` para que los servicios que este usa no tengan que importarlo.
"""
from __future__ import annotations

from .workspace import Workspace


class UserError(ValueError):
    """Error del operador (falta un fichero, selección vacía…). Se muestra tal cual."""


def require_loaded(ws: Workspace) -> None:
    if ws.dataset is None:
        raise UserError('Primero cargue y liste los alimentadores (paso 2).')


def require_active_source_run(ws: Workspace, *, verify_files: bool = False):
    """Impide usar un dataset o artefacto que pertenezca a otra ejecución."""
    snapshot = ws.active_run()
    # Tras reiniciar la web la red ya no está en memoria aunque nada haya cambiado: decir
    # «las entradas cambiaron» (IN111 + TA225, 2026-10-14) mandaba a buscar un cambio
    # que no existía.
    if snapshot is not None and ws.loaded_run_id is None:
        raise UserError(
            'SOURCE_RUN_MISMATCH: la red no está cargada en esta sesión de la web (por '
            'ejemplo, tras reiniciarla). Pulse «Cargar / listar alimentadores».'
        )
    if (
        snapshot is None
        or ws.loaded_run_id != snapshot.run_id
        or ws.loaded_source_mode != snapshot.mode
        or ws.loaded_source_fingerprint != snapshot.fingerprint
    ):
        raise UserError(
            'SOURCE_RUN_MISMATCH: las entradas cambiaron desde la carga. '
            'Pulse «Cargar / listar alimentadores» para crear una ejecución nueva.'
        )
    if verify_files:
        from .source_runs import verify_source_files
        try:
            verify_source_files(snapshot)
        except (OSError, ValueError) as exc:
            raise UserError(f'SOURCE_RUN_INTEGRITY: {exc}') from exc
    return snapshot
