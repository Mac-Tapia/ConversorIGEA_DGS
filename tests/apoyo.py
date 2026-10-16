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


def contexto_nativo(project: str, feeders: list[str] | tuple[str, ...], action: str) -> dict:
    """Contexto mínimo pero firmado para planes unitarios que llegan al ``main``."""
    from igea_dgs.native_action import build_native_action_context

    return build_native_action_context({'project': project}, project, feeders, action)


def vincular_proyecto(client, wid: str, project: str, feeders, *,
                      sin_verificar: tuple[str, ...] = ()) -> None:
    """Registra en un workspace de prueba el proyecto releído para su fuente activa.

    Con el «Caso base» de cada alimentador verificado (spec 015), salvo los de
    ``sin_verificar``.
    """
    from igea_dgs.powerfactory_binding import PowerFactoryProjectBinding

    project = str(project or '').strip()
    if not project:
        return
    ws = client.app.state.store.get(wid)
    assert ws is not None
    requested = {str(feeder).strip() for feeder in feeders if str(feeder).strip()}
    previous = (ws.pf_project_bindings.get(project) or {}).get('feeders') or []
    bound = tuple(sorted(requested | {str(feeder) for feeder in previous}))
    ws.active_run_id = 'web-test-run'
    ws.loaded_run_id = 'web-test-run'
    ws.loaded_source_mode = 'txt'
    ws.loaded_source_fingerprint = 'f' * 64
    binding = PowerFactoryProjectBinding(
        project=project, folder='Conversor IGEA-DGS', source_run_id='web-test-run',
        source_mode='txt', source_fingerprint='f' * 64, feeders=bound,
        dgs_sha256={feeder: 'd' * 64 for feeder in bound},
        native_inventory_sha256='n' * 64,
        native_reread={'status': 'VERIFICADO_PERSISTENCIA', 'caso_base': {
            feeder: ({'status': 'NO_VERIFICADO', 'fallos': ['flujo']} if feeder in sin_verificar
                     else {'status': 'VERIFICADO', 'fallos': []})
            for feeder in bound}},
        accepted_at=1.0,
    )
    ws.pf_project_bindings[project] = binding.as_dict()


def cargar_herramienta(fichero: str, nombre: str | None = None, *,
                       tools_en_path: bool = False) -> ModuleType:
    """Importa ``tools/<fichero>`` como módulo, sin que ``tools/`` sea un paquete.

    ``tools_en_path`` deja ``tools/`` en ``sys.path`` mientras se ejecuta el módulo,
    para los scripts que importan a sus vecinos.
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
