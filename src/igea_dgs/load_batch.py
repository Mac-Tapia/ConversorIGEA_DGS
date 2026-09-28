"""Planificación determinista de actualizaciones de cargas multi-alimentador."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .loads import (
    LoadUpdatePlan,
    SheetRead,
    build_plan,
    model_sed_loads,
    plan_to_payload,
    write_template,
)


@dataclass(frozen=True)
class FeederLoadContext:
    feeder: str
    network_id: str
    model: Any
    project_name: str
    dgs_sha256: str
    metadata_sha256: str
    revision: str


@dataclass
class BulkLoadUpdatePlan:
    batch_id: str
    input_sha256: str
    feeders: dict[str, LoadUpdatePlan]
    contexts: dict[str, FeederLoadContext]
    ignored_sheets: list[str] = field(default_factory=list)
    row_errors: list[str] = field(default_factory=list)
    blocked_feeders: dict[str, list[str]] = field(default_factory=dict)


def _canonical_feeder(value: str) -> str:
    return str(value).strip().upper()


def _is_auxiliary_sheet(sheet: SheetRead) -> bool:
    return bool(sheet.errors) and not sheet.rows and all(
        'columna de código de SED' in error for error in sheet.errors
    )


def build_bulk_update_plan(
    contexts: Mapping[str, FeederLoadContext],
    sheets: Mapping[str, SheetRead],
    *,
    input_sha256: str,
) -> BulkLoadUpdatePlan:
    """Cruza todas las hojas con sus modelos sin ignorar entradas silenciosamente."""
    by_name: dict[str, FeederLoadContext] = {}
    for context in contexts.values():
        key = _canonical_feeder(context.feeder)
        if key in by_name:
            raise ValueError(f'Alimentador repetido en el contexto: {context.feeder}')
        by_name[key] = context

    sheet_by_name: dict[str, SheetRead] = {}
    ignored: list[str] = []
    blocked: dict[str, list[str]] = {}
    row_errors: list[str] = []
    for raw_name, sheet in sorted(sheets.items(), key=lambda pair: _canonical_feeder(pair[0])):
        key = _canonical_feeder(raw_name)
        context = by_name.get(key)
        if context is None:
            if _is_auxiliary_sheet(sheet):
                ignored.append(str(raw_name))
            else:
                error = f'Alimentador {raw_name!r} del archivo no existe en la selección'
                blocked.setdefault(str(raw_name), []).append(error)
                row_errors.append(error)
            continue
        if key in sheet_by_name:
            error = f'Alimentador {context.feeder!r} repetido en el archivo'
            blocked.setdefault(context.feeder, []).append(error)
            row_errors.append(error)
            continue
        sheet_by_name[key] = sheet

    feeder_plans: dict[str, LoadUpdatePlan] = {}
    ordered_contexts: dict[str, FeederLoadContext] = {}
    for key, context in sorted(by_name.items(), key=lambda pair: pair[1].feeder):
        ordered_contexts[context.feeder] = context
        sheet = sheet_by_name.get(key)
        if sheet is None:
            error = f'El archivo no contiene datos para {context.feeder}'
            blocked.setdefault(context.feeder, []).append(error)
            row_errors.append(error)
            sheet = SheetRead(feeder=context.feeder)
        plan = build_plan(context.model, sheet)
        feeder_plans[context.feeder] = plan
        if plan.row_errors:
            blocked.setdefault(context.feeder, []).extend(plan.row_errors)
            row_errors.extend(plan.row_errors)

    seed = {
        'input_sha256': input_sha256,
        'feeders': [
            {
                'feeder': context.feeder,
                'network_id': context.network_id,
                'dgs_sha256': context.dgs_sha256,
                'metadata_sha256': context.metadata_sha256,
                'revision': context.revision,
            }
            for context in ordered_contexts.values()
        ],
    }
    batch_id = hashlib.sha256(
        json.dumps(seed, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()[:16]
    return BulkLoadUpdatePlan(
        batch_id=batch_id,
        input_sha256=input_sha256,
        feeders=feeder_plans,
        contexts=ordered_contexts,
        ignored_sheets=sorted(ignored),
        row_errors=row_errors,
        blocked_feeders=blocked,
    )


def bulk_plan_to_payload(plan: BulkLoadUpdatePlan) -> dict:
    """Serializa el plan sin timestamps ni orden dependiente de la entrada."""
    feeder_payloads = []
    for feeder in sorted(plan.feeders):
        context = plan.contexts[feeder]
        item = plan_to_payload(plan.feeders[feeder])
        item.update({
            'feeder': context.feeder,
            'network_id': context.network_id,
            'project_name': context.project_name,
            'dgs_sha256': context.dgs_sha256,
            'metadata_sha256': context.metadata_sha256,
            'revision': context.revision,
        })
        for row in item['updates']:
            row['feeder'] = context.feeder
            row['network_id'] = context.network_id
        for row in item['unknown']:
            row['feeder'] = context.feeder
            row['network_id'] = context.network_id
        item['updates'] = sorted(item['updates'], key=lambda row: row['sed_code'])
        item['unknown'] = sorted(item['unknown'], key=lambda row: row['sed_code'])
        feeder_payloads.append(item)
    return {
        'batch_id': plan.batch_id,
        'input_sha256': plan.input_sha256,
        'feeders': feeder_payloads,
        'ignored_sheets': sorted(plan.ignored_sheets),
        'row_errors': sorted(plan.row_errors),
        'blocked_feeders': {
            feeder: sorted(errors) for feeder, errors in sorted(plan.blocked_feeders.items())
        },
    }


def write_bulk_template(
    contexts: Mapping[str, FeederLoadContext],
    path: Path | str,
) -> Path:
    """Genera una plantilla consolidada ordenada por alimentador."""
    rows = {
        context.feeder: model_sed_loads(context.model)
        for context in sorted(contexts.values(), key=lambda item: item.feeder)
    }
    return write_template(rows, path)
