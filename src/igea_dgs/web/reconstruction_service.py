"""Run-bound diagnosis and reconstruction services for the web workflow."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Sequence

from ..catalog_resolution import CatalogSource
from ..reconstruction import EvidenceLevel, ReconstructionPolicy
from ..reconstruction_pipeline import PASOS, catalogos_del_fichero, reconstruir_seleccion
from .readiness import assess_feeder_readiness
from .workspace import Workspace
from ..util import write_json_atomic


def resolve_selection(
    ws: Workspace,
    feeders: Sequence[str] | None,
    *,
    all_feeders: bool,
) -> tuple[list[str], list[str]]:
    """Return display feeder names and NetworkIDs without applying readiness gates."""

    inventory = list((ws.inventory or {}).get('feeders') or [])
    if not inventory:
        from .services import UserError

        raise UserError('EMPTY_FEEDER_INVENTORY')
    by_key: dict[str, dict[str, Any]] = {}
    for row in inventory:
        by_key[str(row['feeder'])] = row
        by_key[str(row['network_id'])] = row
    selected = inventory if all_feeders else []
    if not all_feeders:
        unknown: list[str] = []
        seen: set[str] = set()
        for requested in feeders or ():
            row = by_key.get(str(requested))
            if row is None:
                unknown.append(str(requested))
                continue
            network_id = str(row['network_id'])
            if network_id not in seen:
                selected.append(row)
                seen.add(network_id)
        if unknown:
            from .services import UserError

            raise UserError('UNKNOWN_FEEDER: ' + ', '.join(unknown))
    if not selected:
        from .services import UserError

        raise UserError('EMPTY_FEEDER_SELECTION')
    return (
        [str(row['feeder']) for row in selected],
        [str(row['network_id']) for row in selected],
    )


def _paso(ctx, index: int, total: int, label: str) -> None:
    """Avance y punto de cancelación de un trabajo; sin ``ctx`` (llamada directa), nada.

    Diagnosticar y reconstruir eran peticiones síncronas: con muchos alimentadores el
    navegador esperaba sin ver avance y sin poder cancelar (spec 001, RF-8). Ahora
    corren en el carril ``engine`` y comprueban la cancelación entre pasos, nunca a
    mitad de uno.
    """
    if ctx is None:
        return
    ctx.check_cancel()
    ctx.progress(index, total, label)


def diagnose_selection(
    ws: Workspace,
    feeders: Sequence[str] | None,
    *,
    all_feeders: bool,
    ctx=None,
) -> dict[str, Any]:
    """Read-only diagnostics over the active original dataset."""

    from .services import require_active_source_run, require_loaded

    require_loaded(ws)
    snapshot = require_active_source_run(ws)
    names, network_ids = resolve_selection(ws, feeders, all_feeders=all_feeders)
    rows = []
    for index, (name, network_id) in enumerate(zip(names, network_ids)):
        _paso(ctx, index, len(names), name)
        state = ws.feeder_readiness.get(network_id) or assess_feeder_readiness(
            ws.dataset, network_id, {'source_mode': snapshot.mode},
        ).as_dict()
        rows.append({
            'feeder': name,
            'network_id': network_id,
            'readiness': state.get('status', 'INVENTORY_ONLY'),
            'blocking_codes': list(state.get('blocking_codes') or []),
            'details': dict(state.get('details') or {}),
            'source_quality': 'original_complete' if not state.get('blocking_codes') else 'incomplete',
            'repair_count': 0,
            'assumption_count': 0,
            'catalog_sources': [],
            'convergence_state': None,
        })
    _paso(ctx, len(names), len(names), '')
    return {
        'source_run_id': snapshot.run_id,
        'source_mode': snapshot.mode,
        'source_fingerprint': snapshot.fingerprint,
        'feeders': rows,
    }


def reconstruct_selection(
    ws: Workspace,
    feeders: Sequence[str] | None,
    *,
    all_feeders: bool,
    policy: ReconstructionPolicy | None = None,
    ctx=None,
) -> dict[str, Any]:
    """Atomically publish one derived dataset/report for the selected source run.

    Con ``ctx``, una cancelación antes de publicar deja activo el dataset anterior
    (RF-9): todo se construye sobre una copia y el espacio solo se toca al final.
    """

    from .services import require_active_source_run, require_loaded

    require_loaded(ws)
    snapshot = require_active_source_run(ws)
    names, network_ids = resolve_selection(ws, feeders, all_feeders=all_feeders)
    pasos = PASOS + 2
    result, resolutions = reconstruir_seleccion(
        ws.dataset, network_ids, _catalog_sources(ws), policy=policy,
        paso=lambda index, _total, label: _paso(ctx, index, pasos, label),
    )
    result.report.metadata.update({
        'source_run_id': snapshot.run_id,
        'source_mode': snapshot.mode,
        'source_fingerprint': snapshot.fingerprint,
        'selected_network_ids': list(network_ids),
    })
    _paso(ctx, PASOS, pasos, 'Disponibilidad por alimentador')

    decisions_by_network = _decisions_by_network(result, network_ids)
    readiness: dict[str, dict[str, Any]] = {}
    response_rows = []
    for name, network_id in zip(names, network_ids):
        assessed = assess_feeder_readiness(
            result.dataset, network_id, {'source_mode': snapshot.mode},
        ).as_dict()
        decisions = decisions_by_network[network_id]
        assumptions = sum(
            decision.level is EvidenceLevel.ENGINEERING_ASSUMPTION for decision in decisions
        )
        # A source-only feeder is valid in the model builder; it has no line to repair.
        blockers = [
            code for code in assessed.get('blocking_codes') or []
            if code != 'MISSING_TOPOLOGY'
        ]
        status = 'READY_RECONSTRUCTED' if decisions else 'READY_ORIGINAL'
        if blockers:
            status = 'NEEDS_OPERATOR_REVIEW'
        assessed.update({
            'status': status,
            'blocking_codes': blockers,
            'repair_count': len(decisions),
            'assumption_count': assumptions,
            'source_quality': 'reconstructed' if decisions else 'original_complete',
            'catalog_sources': sorted({
                str((decision.provenance.get('catalog') or {}).get('name'))
                for decision in decisions if decision.provenance.get('catalog')
            }),
            'convergence_state': None,
        })
        readiness[network_id] = assessed
        response_rows.append({
            'feeder': name,
            'network_id': network_id,
            'readiness': status,
            'blocking_codes': blockers,
            'repair_count': len(decisions),
            'assumption_count': assumptions,
            'source_quality': assessed['source_quality'],
            'catalog_sources': assessed['catalog_sources'],
            'convergence_state': None,
        })

    source_sha256 = {
        slot: str(item.sha256) for slot, item in sorted(snapshot.files.items())
    }
    payload = {
        **result.report.to_dict(),
        'version': 1,
        'source_sha256': source_sha256,
        'feeders': response_rows,
        'resolved_equipment': {
            code: {
                'rule': item.rule,
                'level': item.level.value,
                'source_code': item.source_code,
                'candidates': list(item.candidates),
            }
            for code, item in sorted(resolutions.items())
        },
    }
    report_hash = _payload_hash(payload)
    payload['report_sha256'] = report_hash
    report_path = ws.out_dir / 'reconstruction_report.json'

    counts = Counter(decision.level for decision in result.report.decisions)
    _paso(ctx, PASOS + 1, pasos, 'Publicar')
    # El informe se escribe tras el punto sin retorno: si se escribiera antes, una
    # cancelación dejaría en disco un informe que no corresponde al dataset activo.
    if ctx is not None:
        ctx.sin_retorno()
    write_json_atomic(report_path, payload)
    with ws.lock:
        # Publish only after every rule and the report write completed.
        ws.reconstructed_dataset = result.dataset
        ws.reconstruction_report = payload
        ws.reconstruction_report_hash = report_hash
        ws.reconstruction_run_id = snapshot.run_id
        ws.reconstruction_selection = tuple(network_ids)
        ws.feeder_readiness.update(readiness)
    if ctx is not None:
        ctx.progress(pasos, pasos, '')
    return {
        'source_run_id': snapshot.run_id,
        'source_fingerprint': snapshot.fingerprint,
        'source_sha256': source_sha256,
        'feeders': response_rows,
        'repairs': len(result.report.decisions),
        'catalog_matches': counts[EvidenceLevel.CATALOG_MATCH],
        'assumptions': counts[EvidenceLevel.ENGINEERING_ASSUMPTION],
        'report': report_path.name,
        'report_sha256': report_hash,
    }


def matching_reconstruction(ws: Workspace, network_ids: Sequence[str]) -> bool:
    return bool(
        ws.reconstructed_dataset is not None
        and ws.reconstruction_run_id == ws.loaded_run_id == ws.active_run_id
        and tuple(network_ids) == ws.reconstruction_selection
        and ws.reconstruction_report_hash
    )


def reconstruction_evidence(ws: Workspace) -> dict[str, Any] | None:
    if not ws.reconstruction_report_hash or not ws.reconstruction_report:
        return None
    counts = ws.reconstruction_report.get('counts') or {}
    return {
        'report': 'reconstruction_report.json',
        'report_sha256': ws.reconstruction_report_hash,
        'repairs': len(ws.reconstruction_report.get('decisions') or []),
        'catalog_matches': int(counts.get(EvidenceLevel.CATALOG_MATCH.value, 0)),
        'assumptions': int(counts.get(EvidenceLevel.ENGINEERING_ASSUMPTION.value, 0)),
        'selection': list(ws.reconstruction_selection),
    }


def _catalog_sources(ws: Workspace) -> tuple[CatalogSource, ...]:
    from ..reglas import catalogo_del_proyecto

    return catalogos_del_fichero(ws.catalog_file or catalogo_del_proyecto())


def _decisions_by_network(result, network_ids):
    dataset = result.dataset
    section_to_network = dataset.section_owner
    code_to_networks: dict[str, set[str]] = {}
    for section_id, config in dataset.line_configurations.items():
        code = str(config.get('LineCableID') or '')
        owner = section_to_network.get(section_id)
        if code and owner:
            code_to_networks.setdefault(code, set()).add(owner)
    output = {network_id: [] for network_id in network_ids}
    for decision in result.report.decisions:
        owners: set[str] = set()
        if decision.entity_type in {'section', 'line_configuration'}:
            owner = section_to_network.get(decision.entity_id)
            if owner:
                owners.add(owner)
        elif decision.entity_type == 'equipment':
            owners.update(code_to_networks.get(decision.entity_id, ()))
        elif decision.entity_type == 'source':
            owners.add(decision.entity_id)
        elif decision.entity_type == 'node':
            for section_id, section in dataset.sections.items():
                if decision.entity_id in {
                    section.get('FromNodeID'), section.get('ToNodeID'),
                }:
                    owner = section_to_network.get(section_id)
                    if owner:
                        owners.add(owner)
        for owner in owners:
            if owner in output:
                output[owner].append(decision)
    return output


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()
