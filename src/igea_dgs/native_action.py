"""Contrato común para ejecutar acciones en el proyecto nativo de PowerFactory.

El contexto firmado demuestra que el plan fue preparado contra el vínculo
fuente/proyecto aceptado. El guion vuelve a validarlo inmediatamente antes de tocar
PowerFactory, evitando ejecutar un JSON viejo o mezclado con otra importación.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any


NATIVE_CONTEXT_SCHEMA = 'igea-dgs-native-action-context-v1'

NATIVE_RESULT_STATUSES = frozenset({
    'OK',
    'AVISO_KVAR',
    'AVISO_PERSISTENCIA_CORREGIDA',
    'AVISO_PERSISTENCIA_NO_CORREGIDA',
    'BLOQUEADO_DATOS',
    'BLOQUEADO_PERSISTENCIA',
    'NO_CONVERGE',
    'VIOLACION_FISICA',
    'NO_APLICA',
})

_BLOCKING_STUDY_STATUSES = frozenset({
    'BLOQUEADO_DATOS',
    'BLOQUEADO_PERSISTENCIA',
    'NO_CONVERGE',
    'VIOLACION_FISICA',
    'NO_APLICA',
})


class NativeActionContextError(ValueError):
    """Un plan no conserva un contexto nativo íntegro y verificable."""


def _sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def build_native_action_context(
    binding: Any,
    project: str,
    feeders: Iterable[str],
    action: str,
) -> dict[str, Any]:
    """Construye la única identidad fuente/proyecto que acompaña al plan."""
    project = str(project or '').strip()
    action = str(action or '').strip()
    normalized_feeders = sorted({
        str(feeder).strip() for feeder in feeders if str(feeder).strip()
    })
    binding_data = binding.as_dict() if hasattr(binding, 'as_dict') else dict(binding)
    payload = {
        'schema': NATIVE_CONTEXT_SCHEMA,
        'action': action,
        'project': project,
        'feeders': normalized_feeders,
        'source': {
            'source_run_id': binding_data.get('source_run_id'),
            'source_mode': binding_data.get('source_mode'),
            'source_fingerprint': binding_data.get('source_fingerprint'),
        },
        'binding': binding_data,
    }
    return {**payload, 'context_sha256': _sha256(payload)}


def verify_native_action_context(
    plan: Mapping[str, Any],
    expected_action: str | Iterable[str] | None = None,
) -> dict[str, Any]:
    """Recalcula la firma y verifica proyecto/alimentadores antes de mutar."""
    raw = plan.get('native_action_context')
    if not isinstance(raw, Mapping):
        raise NativeActionContextError(
            'BLOQUEADO_DATOS: el plan no contiene native_action_context',
        )
    context = dict(raw)
    signature = str(context.pop('context_sha256', '') or '')
    if context.get('schema') != NATIVE_CONTEXT_SCHEMA:
        raise NativeActionContextError(
            'BLOQUEADO_DATOS: esquema de contexto nativo ausente o incompatible',
        )
    if not signature or signature != _sha256(context):
        raise NativeActionContextError(
            'BLOQUEADO_DATOS: la firma del contexto nativo no coincide',
        )
    expected = ({expected_action} if isinstance(expected_action, str)
                else set(expected_action or []))
    if expected and context.get('action') not in expected:
        raise NativeActionContextError(
            f"BLOQUEADO_DATOS: acción {context.get('action')!r} no corresponde a {sorted(expected)}",
        )
    project = str(plan.get('project') or '').strip()
    context_project = str(context.get('project') or '').strip()
    binding = context.get('binding')
    if not project or project != context_project or not isinstance(binding, Mapping):
        raise NativeActionContextError(
            'BLOQUEADO_DATOS: el proyecto del plan no coincide con su vínculo firmado',
        )
    if str(binding.get('project') or '').strip() != project:
        raise NativeActionContextError(
            'BLOQUEADO_DATOS: el vínculo firmado pertenece a otro proyecto',
        )
    plan_feeders = sorted({
        str(feeder).strip() for feeder in (plan.get('feeders') or [])
        if str(feeder).strip()
    })
    if not plan_feeders and plan.get('feeder'):
        plan_feeders = [str(plan['feeder']).strip()]
    if plan_feeders != list(context.get('feeders') or []):
        raise NativeActionContextError(
            'BLOQUEADO_DATOS: los alimentadores del plan no coinciden con el contexto firmado',
        )
    return {**context, 'context_sha256': signature}


def native_result_status(evidence: Mapping[str, Any]) -> str:
    """Reduce evidencia heterogénea al vocabulario auditable, nunca a ``FAIL``."""
    explicit = str(evidence.get('status') or '').strip().upper()
    if explicit in NATIVE_RESULT_STATUSES:
        return explicit
    if evidence.get('not_applicable'):
        return 'NO_APLICA'
    if evidence.get('data_error') or explicit == 'FAIL':
        return 'BLOQUEADO_DATOS'
    if evidence.get('persistence_error'):
        return 'BLOQUEADO_PERSISTENCIA'
    if evidence.get('converged') is False:
        return 'NO_CONVERGE'
    if evidence.get('physical_violations'):
        return 'VIOLACION_FISICA'
    if evidence.get('persistence_corrected'):
        return 'AVISO_PERSISTENCIA_CORREGIDA'
    if evidence.get('persistence_warning'):
        return 'AVISO_PERSISTENCIA_NO_CORREGIDA'
    return 'OK' if evidence.get('ok') else 'BLOQUEADO_DATOS'


def status_blocks_studies(status: str) -> bool:
    """Los avisos de Q o persistencia corregida nunca bloquean estudios."""
    return str(status or '').strip().upper() in _BLOCKING_STUDY_STATUSES


def native_action_block_report(
    plan: Mapping[str, Any], expected_action: str | Iterable[str],
) -> dict[str, Any] | None:
    """Devuelve un informe preciso si el guion no debe abrir PowerFactory."""
    try:
        verify_native_action_context(plan, expected_action)
    except NativeActionContextError as exc:
        return {
            'project': plan.get('project'),
            'feeders': plan.get('feeders') or (
                [plan.get('feeder')] if plan.get('feeder') else []
            ),
            'status': 'BLOQUEADO_DATOS',
            'error': str(exc),
            'avisos': [],
        }
    return None
