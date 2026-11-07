"""Auxiliares compartidos por varias pruebas.

Estaban copiados: ``_module`` (cargar un script de ``tools/``) en cuatro ficheros y
``_wait`` (esperar a un trabajo de la API) en dos, con plazos distintos sin motivo.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from contextlib import contextmanager
import time
from pathlib import Path
from types import ModuleType

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


#: Carpeta que deja ``tools/aceptacion_nativa.py`` con lecturas e informes de DIgSILENT real (044, 045, 048 y
#: 049, T4). Las pruebas no se conectan a DIgSILENT (084:RF-21): releen esa evidencia, comprueban sus huellas
#: y vuelven a calcular los veredictos. Sin la variable se omiten, como las de los TXT reales con ``CSG_*``.
VARIABLE_EVIDENCIA_NATIVA = 'CSG_EVIDENCIA_NATIVA'


def evidencia_nativa(etapa: str):
    """(guion, carpeta, manifiesto, veredictos) de la evidencia nativa; se omite sin ella."""
    import json

    import pytest

    ruta = os.environ.get(VARIABLE_EVIDENCIA_NATIVA, '').strip()
    if not ruta:
        pytest.skip(f'Defina {VARIABLE_EVIDENCIA_NATIVA} con la carpeta de tools/aceptacion_nativa.py')
    guion = cargar_herramienta('aceptacion_nativa.py', 'aceptacion_nativa_evidencia', tools_en_path=True)
    carpeta = Path(ruta)
    manifiesto = json.loads((carpeta / guion.MANIFIESTO).read_text(encoding='utf-8'))
    assert manifiesto.get('schema') == guion.ESQUEMA
    assert guion.comprobar_huellas(carpeta, manifiesto) == [], 'la evidencia cambió desde que se escribió'
    assert manifiesto.get(etapa), f'la evidencia no tiene la etapa «{etapa}»'
    perfil = manifiesto.get('perfil')
    return guion, carpeta, manifiesto, guion.veredictos(carpeta, manifiesto, Path(perfil) if perfil else None)


def contexto_nativo(project: str, feeders: list[str] | tuple[str, ...], action: str) -> dict:
    """Contexto mínimo pero firmado para planes unitarios que llegan al ``main``."""
    from convertersmartgrid.native_action import build_native_action_context

    return build_native_action_context({'project': project}, project, feeders, action)


def vincular_proyecto(client, wid: str, project: str, feeders, *,
                      sin_verificar: tuple[str, ...] = ()) -> None:
    """Registra en un workspace de prueba el proyecto releído para su fuente activa.

    Con el «Caso base» de cada alimentador verificado (spec 015), salvo los de
    ``sin_verificar``.
    """
    from convertersmartgrid.powerfactory_binding import PowerFactoryProjectBinding

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
        project=project, folder='ConverterSmartGrid', source_run_id='web-test-run',
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
        if state['status'] in ('done', 'parcial', 'no_converge', 'failed', 'cancelled'):
            return state
        time.sleep(0.05)
    raise AssertionError(f"el trabajo {job.get('title', job['id'])} no terminó en {timeout} s")


def contrato_fisico() -> dict:
    """Lo que un grafo versión 3 declara de su física (045:RF-3), para las redes sintéticas."""
    from convertersmartgrid.digital_twin.contratos_fisicos import CONTROLES_LDF, REPRESENTACION

    return {'alcance_fisico': {'representacion': REPRESENTACION, 'no_representados': {}},
            'controles': {'comldf': dict.fromkeys(CONTROLES_LDF, 0)}}


#: Segundos que una prueba que entrena espera su turno de GPU antes de fallar diciendo quién la tiene.
ESPERA_TURNO_GPU_S = 1800.0


@contextmanager
def turno_gpu_esperando(nombre: str, limite_s: float | None = None, pausa_s: float = 5.0):
    """El turno común de la GPU para una prueba que entrena, esperando a que lo suelte otro (043:RF-6).

    Una prueba que llama a ``oraculo.entrenar`` sin turno reabre su candidato en un hijo que sí lo pide
    (043:RF-5): con otro proceso en la GPU, el hijo lo encontraba ocupado, el candidato no se promovía y
    seis pruebas fallaban sin decir por qué (2026-11-03). Como un lanzador de ``tools/``, la prueba toma el
    turno y el hijo lo hereda; si no llega en ``limite_s`` (``CSG_GPU_ESPERA_S``), falla con «GPU ocupada».
    """
    from convertersmartgrid.trabajadores_ml import turno_gpu

    limite = float(os.environ.get('CSG_GPU_ESPERA_S', ESPERA_TURNO_GPU_S)) if limite_s is None else limite_s
    fin = time.monotonic() + limite
    while True:
        turno = turno_gpu(nombre)
        try:
            turno.__enter__()
        except RuntimeError as exc:
            if 'GPU ocupada' not in str(exc) or time.monotonic() >= fin:
                raise
            time.sleep(pausa_s)
            continue
        break
    try:
        yield
    finally:
        turno.__exit__(None, None, None)
