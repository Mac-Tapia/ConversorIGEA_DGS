"""Immutable custody contract for multi-feeder load/SED plans."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


class LoadBatchPlanError(RuntimeError):
    """A load batch plan cannot be created or read safely."""


class LoadBatchPlanStale(LoadBatchPlanError):
    """Optimistic identities changed after the operator reviewed the plan."""


@dataclass(frozen=True)
class CustodiedInput:
    slot: str
    name: str
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class FeederLoadPlan:
    feeder: str
    update: dict[str, Any] | None
    create: dict[str, Any] | None


@dataclass(frozen=True)
class LoadBatchPlan:
    token: str
    path: str
    project: str
    project_identity: str
    source_run_id: str
    source_fingerprint: str
    feeders: tuple[str, ...]
    inputs: tuple[CustodiedInput, ...]
    feeder_plans: tuple[FeederLoadPlan, ...]
    economics: dict[str, Any] | None
    row_errors: tuple[str, ...]
    applicable: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str,
    ).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def project_identity(ws: Any, project: str) -> str:
    """Stable optimistic identity of the selected PowerFactory inventory."""

    inventory = getattr(ws, 'pf_inventory', None) or {
        'projects_from_workspace': getattr(ws, 'pf_projects', {}),
    }
    return _json_sha256({'project': project, 'inventory': inventory})


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8',
    )
    temporary.replace(path)


def create_load_batch_plan(
    ws: Any,
    project: str,
    feeders: Sequence[str],
    update_file: Path | None,
    create_file: Path | None,
    economics: dict[str, Any] | None,
    *,
    payload: dict[str, Any],
    feeders_summary: Sequence[dict[str, Any]],
    row_errors: Sequence[str],
) -> dict[str, Any]:
    """Custody the reviewed books and atomically publish an immutable plan."""

    if not project.strip():
        raise LoadBatchPlanError('el proyecto PowerFactory es obligatorio')
    ordered = tuple(dict.fromkeys(str(item).strip() for item in feeders if str(item).strip()))
    if not ordered:
        raise LoadBatchPlanError('seleccione al menos un alimentador')
    if not ws.active_run_id or ws.loaded_run_id != ws.active_run_id:
        raise LoadBatchPlanStale('LOAD_BATCH_PLAN_STALE: no hay ejecución fuente activa cargada')
    if not ws.loaded_source_fingerprint:
        raise LoadBatchPlanStale('LOAD_BATCH_PLAN_STALE: falta fingerprint de la fuente')

    token = uuid.uuid4().hex[:12]
    plan_dir = ws.plans_dir / f'load_batch_{token}'
    plan_dir.mkdir(parents=True, exist_ok=False)
    custody: list[CustodiedInput] = []
    for slot, source in (('update', update_file), ('create', create_file)):
        if source is None:
            continue
        source = Path(source)
        if not source.is_file():
            raise LoadBatchPlanError(f'archivo {slot} no encontrado: {source}')
        destination = plan_dir / f'{slot}_{source.name}'
        before = _sha256(source)
        shutil.copy2(source, destination)
        after = _sha256(destination)
        if before != after:
            raise LoadBatchPlanError(f'falló la custodia SHA-256 de {source.name}')
        custody.append(CustodiedInput(
            slot=slot,
            name=source.name,
            path=str(destination.resolve()),
            size=destination.stat().st_size,
            sha256=after,
        ))

    identity = project_identity(ws, project.strip())
    errors = tuple(str(item) for item in row_errors)
    applicable = not errors and bool(payload.get('feeders'))
    document = {
        **payload,
        'schema_version': 'igea-dgs-load-batch-plan-v1',
        'token': token,
        'project': project.strip(),
        'project_identity': identity,
        'source_run_id': ws.active_run_id,
        'source_fingerprint': ws.loaded_source_fingerprint,
        'ordered_feeders': list(ordered),
        'inputs': [item.__dict__ for item in custody],
        'economics': economics,
        'feeders_summary': list(feeders_summary),
        'row_errors': list(errors),
        'applicable': applicable,
    }
    plan_path = plan_dir / 'load_batch_plan.json'
    _write_json_atomic(plan_path, document)
    plan_sha256 = _sha256(plan_path)
    ws.plans[token] = {
        'kind': 'lote',
        'token': token,
        'path': str(plan_path.resolve()),
        'plan_sha256': plan_sha256,
        'project': project.strip(),
        'project_identity': identity,
        'source_run_id': ws.active_run_id,
        'source_fingerprint': ws.loaded_source_fingerprint,
        'order': list(ordered),
        'feeders_summary': list(feeders_summary),
        'row_errors': list(errors),
        'input_paths': {item.slot: item.path for item in custody},
        'applicable': applicable,
    }
    return {
        'token': token,
        'kind': 'lote',
        'project': project.strip(),
        'project_identity': identity,
        'order': list(ordered),
        'feeders_summary': list(feeders_summary),
        'row_errors': list(errors),
        'applicable': applicable,
        'plan_file': plan_path.name,
        'plan_path': str(plan_path.resolve()),
        'plan_sha256': plan_sha256,
        'inputs': [item.__dict__ for item in custody],
    }


def require_current_load_batch_plan(ws: Any, token: str) -> LoadBatchPlan:
    """Fail before mutation if source, project, plan or custodied books changed."""

    registry = ws.plans.get(token)
    if not registry or registry.get('kind') != 'lote':
        raise LoadBatchPlanError('el plan ya no existe')
    path = Path(registry['path'])
    if not path.is_file() or _sha256(path) != registry.get('plan_sha256'):
        raise LoadBatchPlanStale('LOAD_BATCH_PLAN_STALE: cambió el archivo del plan')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if (
        ws.active_run_id != payload.get('source_run_id')
        or ws.loaded_run_id != ws.active_run_id
        or ws.loaded_source_fingerprint != payload.get('source_fingerprint')
    ):
        raise LoadBatchPlanStale('LOAD_BATCH_PLAN_STALE: cambió la ejecución fuente')
    if project_identity(ws, payload['project']) != payload.get('project_identity'):
        raise LoadBatchPlanStale('LOAD_BATCH_PLAN_STALE: cambió el inventario/proyecto PowerFactory')

    inputs = tuple(CustodiedInput(**item) for item in payload.get('inputs') or [])
    for item in inputs:
        item_path = Path(item.path)
        if (
            not item_path.is_file()
            or item_path.stat().st_size != item.size
            or _sha256(item_path) != item.sha256
        ):
            raise LoadBatchPlanStale(
                f'LOAD_BATCH_PLAN_STALE: cambió el libro custodiado {item.name}'
            )
    feeder_plans = tuple(
        FeederLoadPlan(
            feeder=str(item['feeder']),
            update=item.get('update'),
            create=item.get('create'),
        )
        for item in payload.get('feeders') or []
    )
    return LoadBatchPlan(
        token=token,
        path=str(path),
        project=str(payload['project']),
        project_identity=str(payload['project_identity']),
        source_run_id=str(payload['source_run_id']),
        source_fingerprint=str(payload['source_fingerprint']),
        feeders=tuple(payload.get('ordered_feeders') or []),
        inputs=inputs,
        feeder_plans=feeder_plans,
        economics=payload.get('economics'),
        row_errors=tuple(payload.get('row_errors') or []),
        applicable=bool(payload.get('applicable')),
    )
