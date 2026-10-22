"""Ensamblaje del episodio desde la evidencia nativa (spec 024, T4).

Junta tres cosas que ya existen al terminar una acción en DIgSILENT: el plan con su
contexto firmado (de qué fuente y proyecto, spec 018), el resultado que deja el guion y
la lectura hecha después en una sesión nueva. Lo que falta no se rellena: el episodio va
a cuarentena con la causa y nunca queda como aceptado a medias (RF-9).
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..native_action import (
    NativeActionContextError,
    native_result_status,
    verify_native_action_context,
)
from .episode import (
    ESQUEMA,
    RESULTADOS_FLUJO,
    Artefacto,
    Caso,
    Clase,
    Episodio,
    leer_episodio,
)
from .evaluacion import Evaluacion, Limites, evaluar

__all__ = ['Artefacto', 'CapturaImposible', 'artefacto_de', 'construir_episodio']


class CapturaImposible(ValueError):
    """Sin contexto firmado no se sabe de qué fuente viene el trabajo: no hay episodio."""


def artefacto_de(ruta: Path, rol: str, base: Path) -> Artefacto:
    """Huella y tamaño de un fichero de evidencia, con su ruta relativa a ``base``."""
    datos = ruta.read_bytes()
    try:
        relativa = ruta.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        relativa = ruta.name
    return Artefacto(rol, relativa, hashlib.sha256(datos).hexdigest(), len(datos))


def _flujo_ausente(motivo: str) -> dict[str, Any]:
    return {clave: {'ausente': motivo} for clave in RESULTADOS_FLUJO}


def _bloqueos_de_lectura(lectura: Mapping[str, Any] | None, contexto: Mapping[str, Any],
                         plan: Mapping[str, Any]) -> list[str]:
    if lectura is None:
        return ['falta la lectura nativa tras la acción']
    bloqueos = []
    if lectura.get('project') != contexto['project']:
        bloqueos.append(f"la lectura es del proyecto «{lectura.get('project')}», no de "
                        f"«{contexto['project']}»")
    if sorted(lectura.get('feeders') or []) != list(contexto.get('feeders') or []):
        bloqueos.append('la lectura no tiene los mismos alimentadores que el contexto firmado')
    # El trazado manual de un enlace es intencional: si su huella cambió sin que el plan lo
    # pidiera, el episodio no puede enseñar que ese cambio estaba bien (RF-3, RF-25).
    huellas = (lectura.get('topologia') or {}).get('huellas_gps') or {}
    for elemento, esperada in sorted((plan.get('huellas_gps_esperadas') or {}).items()):
        if huellas.get(elemento) != esperada:
            bloqueos.append(f'el trazado de {elemento} cambió sin autorización')
    return bloqueos


def construir_episodio(plan: Mapping[str, Any], resultado: Mapping[str, Any],
                       lectura: Mapping[str, Any] | None, artefactos: Sequence[Artefacto], *,
                       caso: Caso, limites: Limites | None, referencia: Mapping[str, Any] | None,
                       calibracion_cuadra: bool | None, creado: str,
                       manual: bool = False) -> Episodio:
    """Episodio de una acción nativa ya terminada, clasificado por su caso (RF-1 a RF-5)."""
    try:
        contexto = verify_native_action_context(plan)
    except NativeActionContextError as exc:
        raise CapturaImposible(str(exc)) from exc

    estado = native_result_status(resultado)
    revertido = bool((resultado.get('rollback') or {}).get('restored') or resultado.get('revertido'))
    convergio = estado != 'NO_CONVERGE' and resultado.get('converged') is not False
    aplicada = resultado.get('aplicada', True) is not False
    bloqueos = _bloqueos_de_lectura(lectura, contexto, plan)

    if bloqueos and not revertido and convergio:
        evaluacion = Evaluacion(Clase.QUARANTINE, bloqueos=tuple(bloqueos))
    else:
        evaluacion = evaluar(
            caso, dict((lectura or {}).get('flujo') or {}), convergio=convergio,
            revertido=revertido, reabierto=bool((lectura or {}).get('reopen_verified')),
            limites=limites, calibracion_cuadra=calibracion_cuadra,
            referencia=dict(referencia) if referencia is not None else None, manual=manual)
    clase = evaluacion.clase
    if clase is Clase.ACCEPTED and not aplicada:
        clase = Clase.COUNTERFACTUAL

    lectura = lectura or {}
    flujo = lectura.get('flujo') if lectura and not bloqueos else None
    payload = {
        'schema': ESQUEMA,
        'clase': clase.value,
        'caso': caso.value,
        'creado': creado,
        'fuente': dict(contexto['source']),
        'nativo': {
            'project': contexto['project'],
            'folder': lectura.get('folder'),
            'feeders': list(lectura.get('feeders') or contexto['feeders']),
            'pf_version': lectura.get('pf_version'),
            'reopen_verified': bool(lectura.get('reopen_verified')) and not bloqueos,
        },
        'accion': {'tipo': contexto['action'], 'aplicada': aplicada,
                   'context_sha256': contexto['context_sha256'],
                   # La variante simulada (T10): su familia decide la partición (RF-12).
                   **({'escenario': dict(resultado['escenario'])} if resultado.get('escenario') else {})},
        'topologia': dict(lectura.get('topologia') or {}),
        'flujo': dict(flujo) if flujo else _flujo_ausente(
            bloqueos[0] if bloqueos else 'la lectura no trae resultados del flujo'),
        'aceptacion': {'estado_nativo': estado, 'bloqueos': list(evaluacion.bloqueos),
                       'violaciones': list(evaluacion.violaciones),
                       'diagnostico': list(evaluacion.diagnostico)},
        'obras': [dict(o) for o in resultado.get('obras') or []] if caso is not Caso.CASO_BASE else [],
        'artefactos': [{'rol': a.rol, 'ruta': a.ruta, 'sha256': a.sha256, 'bytes': a.bytes}
                       for a in artefactos],
    }
    return leer_episodio(payload)
