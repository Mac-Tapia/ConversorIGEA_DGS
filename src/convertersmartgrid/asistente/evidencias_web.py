"""067:RF-1 a RF-7: lo que produce la web queda como evidencia del espacio, con su contexto verdadero.

La revisión por roles exige evidencia del mismo proyecto y la misma fuente, y solo la escribía una
herramienta aparte, en otro sitio: desde el botón, los cuatro roles salían siempre bloqueados. Aquí se
custodia el resultado de un trabajo terminado, tal como salió, sin deducir nada: si no nombra su proyecto o
no hay huella de fuente, no es evidencia de ese contexto y se dice.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..runtime_paths import staging_publicacion
from .ejecutor import entregables
from .observacion import FAMILIA_OPERACION, leer_evidencias, registrar_evidencia

#: Los trabajos cuyo resultado sostiene una revisión: informes, estudios y obras. Convertir o leer no dicen
#: nada de un proyecto y sus decisiones.
TRABAJOS_CON_EVIDENCIA = frozenset({
    'informe_estudio', 'informe_factibilidad', 'estudios', 'pide', 'pf_verificar_base', 'obras_aplicar',
    'obras_escalera', 'obras_con_proyecto', 'transferencia', 'set_nueva_operacion'})

_MAX_LISTA = 50
_MAX_TEXTO = 2000
_MAX_PROFUNDIDAD = 4
_MAX_ENTREGABLES = 20


def huella_fuente(ws: Any, proyecto: str | None) -> str | None:
    """La fuente con la que se vinculó el proyecto o, sin vínculo, la cargada (067:RF-3).

    Tras reiniciar la web no hay fuente en memoria, pero un proyecto importado sigue atado a la suya
    (spec 018); y si el espacio cargó otra, sus estudios siguen siendo de la primera.
    """
    vinculo = (getattr(ws, 'pf_project_bindings', None) or {}).get(proyecto) or {}
    return vinculo.get('source_fingerprint') or getattr(ws, 'loaded_source_fingerprint', None)


def _acotado(valor: Any, profundidad: int = 0) -> Any:
    """El resultado sin curvas ni tablas enormes: el informe completo sigue en sus entregables."""
    if isinstance(valor, dict):
        if profundidad >= _MAX_PROFUNDIDAD:
            return f'({len(valor)} campos)'
        return {str(k): _acotado(v, profundidad + 1) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        if profundidad >= _MAX_PROFUNDIDAD or len(valor) > _MAX_LISTA:
            return f'({len(valor)} elementos)'
        return [_acotado(v, profundidad + 1) for v in valor]
    if isinstance(valor, str):
        return valor if len(valor) <= _MAX_TEXTO else f'{valor[:_MAX_TEXTO]}… ({len(valor)} caracteres)'
    return valor if isinstance(valor, (int, float, bool, type(None))) else str(valor)


def _entregables(raiz: Path, resultado: Any) -> list[dict]:
    """Las huellas de los ficheros que dejó el trabajo, para que la evidencia no se pueda sustituir."""
    filas = []
    base = raiz.resolve()
    for nombre in entregables(resultado)[:_MAX_ENTREGABLES]:
        ruta = (raiz / nombre).resolve()
        # El nombre viene de un resultado: solo se abre lo que está en la salida del espacio.
        if not ruta.is_relative_to(base) or not ruta.is_file():
            continue
        with ruta.open('rb') as f:
            filas.append({'archivo': nombre, 'sha256': hashlib.file_digest(f, 'sha256').hexdigest(),
                          'bytes': ruta.stat().st_size})
    return filas


def custodiar_trabajo(ws: Any, trabajo: dict) -> str | None:
    """Custodia un trabajo terminado; devuelve el aviso para el Registro si no se puede (067:RF-4)."""
    if trabajo.get('kind') not in TRABAJOS_CON_EVIDENCIA or trabajo.get('status') not in ('done', 'parcial', 'no_converge'):
        return None
    resultado = trabajo.get('result')
    proyecto = resultado.get('project') if isinstance(resultado, dict) else None
    fuente = huella_fuente(ws, proyecto)
    if not proyecto or not fuente:
        falta = 'no nombra su proyecto' if not proyecto else f'no hay huella de la fuente de {proyecto}'
        return f'«{trabajo.get("title")}» no se custodia como evidencia: {falta}.'
    raiz = Path(ws.out_dir)
    documento = {
        'contexto': {'workspace_id': ws.id, 'project': proyecto, 'source_fingerprint': fuente,
                     'source_mode': getattr(ws, 'loaded_source_mode', None)},
        'trabajo': {k: trabajo.get(k) for k in ('id', 'kind', 'title', 'created_at', 'finished_at')},
        # Antes que el resultado: el revisor lee un fragmento del principio, y estas huellas son lo verificable.
        'entregables': _entregables(raiz, resultado),
        'resultado': _acotado(resultado)}
    carpeta = raiz / 'observacion' / 'evidencias'
    carpeta.mkdir(parents=True, exist_ok=True)
    with staging_publicacion(carpeta / f"{trabajo.get('id')}.json") as temporal:
        temporal.write_text(json.dumps(documento, ensure_ascii=False, default=str), encoding='utf-8')
        registrar_evidencia(raiz, temporal, familia=FAMILIA_OPERACION, etiqueta=str(trabajo.get('kind')),
                            alcance='espacio_proyecto_fuente', origen=f"trabajo:{trabajo.get('id')}")
    return None


def evidencias_del_contexto(raiz: Path, proyecto: str | None, fuente: str | None, *, limite: int = 8) -> dict:
    """Las más recientes del proyecto y la fuente, listas para ``revisar_propuesta`` (067:RF-5)."""
    evidencia: dict[str, dict] = {}
    if not proyecto or not fuente:
        return evidencia
    for registro in leer_evidencias(raiz):
        informe = registro['informe']
        contexto = informe.get('contexto') or {} if isinstance(informe, dict) else {}
        if contexto.get('project') != proyecto or contexto.get('source_fingerprint') != fuente:
            continue
        ruta = Path(raiz) / 'observacion/evidencias' / f"{registro['id']}.json"
        evidencia[registro['id']] = {'archivo': str(ruta), 'sha256': registro['sha256'], 'proyecto': proyecto,
                                     'fuente': fuente, 'localizador': 'texto[0:6000]',
                                     'fragmento': ruta.read_text(encoding='utf-8')[:6000]}
        if len(evidencia) >= limite:
            break
    return evidencia


def resumen_del_espacio(raiz: Path, limite: int = 50) -> list[dict]:
    """Lo custodiado, para enseñarlo sin el contenido de los informes (067:RF-7)."""
    filas = []
    for registro in leer_evidencias(raiz)[:limite]:
        informe = registro['informe'] if isinstance(registro['informe'], dict) else {}
        contexto = informe.get('contexto') or {}
        filas.append({'id': registro['id'], 'etiqueta': registro['etiqueta'], 'familia': registro['familia'],
                      'registrado': registro['registrado'], 'proyecto': contexto.get('project'),
                      'fuente': contexto.get('source_fingerprint'),
                      'titulo': (informe.get('trabajo') or {}).get('title')})
    return filas
