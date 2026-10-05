"""Run-bound diagnosis and reconstruction services for the web workflow."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..catalog_resolution import CatalogSource
from ..reconstruction import EvidenceLevel, ReconstructionPolicy, reconstruct_dataset
from ..reconstruction_topology import repair_discontinuities, repair_missing_nodes
from .readiness import assess_feeder_readiness
from .workspace import Workspace


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


def diagnose_selection(
    ws: Workspace,
    feeders: Sequence[str] | None,
    *,
    all_feeders: bool,
) -> dict[str, Any]:
    """Read-only diagnostics over the active original dataset."""

    from .services import require_active_source_run, require_loaded

    require_loaded(ws)
    snapshot = require_active_source_run(ws)
    names, network_ids = resolve_selection(ws, feeders, all_feeders=all_feeders)
    rows = []
    for name, network_id in zip(names, network_ids):
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
) -> dict[str, Any]:
    """Atomically publish one derived dataset/report for the selected source run."""

    from .services import require_active_source_run, require_loaded

    require_loaded(ws)
    snapshot = require_active_source_run(ws)
    names, network_ids = resolve_selection(ws, feeders, all_feeders=all_feeders)
    effective_policy = policy or ReconstructionPolicy()
    result = reconstruct_dataset(ws.dataset, effective_policy, ())
    result.report.metadata.update({
        'source_run_id': snapshot.run_id,
        'source_mode': snapshot.mode,
        'source_fingerprint': snapshot.fingerprint,
        'selected_network_ids': list(network_ids),
    })

    _repair_missing_sources(result, network_ids)
    _repair_missing_line_configurations(result, network_ids)
    repair_missing_nodes(result, network_ids)
    repair_discontinuities(result, network_ids)
    _complete_coordinates(result, network_ids)
    resolutions = result.resolve_equipment(_catalog_sources(ws), network_ids)

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
    _write_json_atomic(report_path, payload)

    counts = Counter(decision.level for decision in result.report.decisions)
    with ws.lock:
        # Publish only after every rule and the report write completed.
        ws.reconstructed_dataset = result.dataset
        ws.reconstruction_report = payload
        ws.reconstruction_report_hash = report_hash
        ws.reconstruction_run_id = snapshot.run_id
        ws.reconstruction_selection = tuple(network_ids)
        ws.feeder_readiness.update(readiness)
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


def _repair_missing_sources(result, network_ids: Iterable[str]) -> None:
    dataset = result.dataset
    for network_id in network_ids:
        if network_id in dataset.sources:
            continue
        headnodes = sorted(node for node, owner in dataset.headnodes.items() if owner == network_id)
        node_id = headnodes[0] if headnodes else ''
        if not node_id:
            continue
        inferred = _infer_voltage(dataset, network_id)
        voltage = inferred or result.policy.provisional_nominal_voltage_kv
        row = {'NetworkID': network_id, 'NodeID': node_id, 'DesiredVoltage': f'{voltage:g}'}
        dataset.sources[network_id] = row
        result.record_change(
            entity_type='source', entity_id=network_id, field='__row__',
            original_value=None, applied_value=row,
            level=EvidenceLevel.ENGINEERING_ASSUMPTION,
            rule='RECOVER_REFERENCED_NODE',
            reason='A unique declared headnode was used to reconstruct the omitted source.',
            confidence=0.45 if inferred is None else 0.7,
            provenance={
                'voltage_inferred': inferred is not None,
                'policy_fallback_kv': (
                    result.policy.provisional_nominal_voltage_kv if inferred is None else None
                ),
            },
        )


def _repair_missing_line_configurations(result, network_ids: Iterable[str]) -> None:
    dataset = result.dataset
    selected = set(network_ids)
    for section_id, section in sorted(dataset.sections.items()):
        if dataset.section_owner.get(section_id) not in selected:
            continue
        if section_id in dataset.line_configurations:
            continue
        length = _section_distance(dataset, section) or 1.0
        row = {
            'SectionID': section_id,
            'LineCableID': '',
            'Length': f'{length:.12g}',
            'Overhead': str(section.get('Overhead', '1')),
        }
        dataset.line_configurations[section_id] = row
        result.record_change(
            entity_type='line_configuration', entity_id=section_id, field='__row__',
            original_value=None, applied_value=row,
            level=EvidenceLevel.ENGINEERING_ASSUMPTION,
            rule='PROVISIONAL_PROFILE',
            reason='The section had no line configuration; length was derived from coordinates or a 1 m floor.',
            confidence=0.4 if length != 1.0 else 0.2,
        )


def _complete_coordinates(result, network_ids: Iterable[str]) -> None:
    from copy import deepcopy

    from ..coordenadas import completar_coordenadas

    dataset = result.dataset
    selected = set(network_ids)
    selected_nodes = {
        node_id
        for section_id, section in dataset.sections.items()
        if dataset.section_owner.get(section_id) in selected
        for node_id in (section.get('FromNodeID'), section.get('ToNodeID'))
        if node_id
    }
    all_before = deepcopy(dataset.nodes)
    before = {node_id: deepcopy(dataset.nodes.get(node_id, {})) for node_id in selected_nodes}
    completar_coordenadas(dataset)
    for node_id, row in all_before.items():
        if node_id not in selected_nodes:
            dataset.nodes[node_id] = row
    for node_id in sorted(selected_nodes):
        old = before.get(node_id, {})
        current = dataset.nodes.get(node_id, {})
        for field in ('CoordX', 'CoordY', 'CoordOrigen'):
            if old.get(field) == current.get(field):
                continue
            result.record_change(
                entity_type='node', entity_id=node_id, field=field,
                original_value=old.get(field), applied_value=current.get(field),
                level=EvidenceLevel.ENGINEERING_ASSUMPTION,
                rule='CREATE_TERMINAL_NODE',
                reason='Missing coordinates were derived deterministically from the feeder graph.',
                confidence=0.6,
                provenance={'coordinate_method': 'graph'},
            )


def _section_distance(dataset, section) -> float | None:
    points = []
    for key in ('FromNodeID', 'ToNodeID'):
        row = dataset.nodes.get(section.get(key), {})
        try:
            point = float(row.get('CoordX')), float(row.get('CoordY'))
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in point):
            return None
        points.append(point)
    return math.hypot(points[0][0] - points[1][0], points[0][1] - points[1][1])


def _infer_voltage(dataset, network_id: str) -> float | None:
    for section_id in dataset.feeders.get(network_id, ()):
        for row in (
            dataset.sections.get(section_id, {}),
            dataset.line_configurations.get(section_id, {}),
        ):
            for key in ('NominalVoltageKV', 'VoltageKV', 'kV'):
                try:
                    value = float(row.get(key))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value) and value > 0:
                    return value
    return None


def _catalog_sources(ws: Workspace) -> tuple[CatalogSource, ...]:
    from ..reglas import catalogo_del_proyecto

    path = Path(ws.catalog_file) if ws.catalog_file else catalogo_del_proyecto()
    if path is None or not path.is_file():
        return ()
    from ..catalog import tablas_equipo_desde_catalogo

    parsed = tablas_equipo_desde_catalogo(path)
    rows = tuple(
        {**row, 'EquipmentClass': table, 'Overhead': table == 'LINE'}
        for table, table_rows in parsed.tablas.items()
        for row in table_rows
    )
    return (CatalogSource(
        name=path.stem,
        kind='global',
        version=str(path.stat().st_mtime_ns),
        manufacturer='',
        locator=str(path.resolve()),
        sha256=_file_sha256(path),
        rows=rows,
    ),)


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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8',
    )
    temporary.replace(path)
