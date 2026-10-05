"""Deterministic topology reconstruction for a derived canonical dataset."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, is_dataclass
import math
from typing import Any, Iterable

from .reconstruction import EvidenceLevel, ReconstructionResult


@dataclass(frozen=True, order=True)
class TopologyCandidate:
    distance: float
    island_node: str
    target_node: str
    voltage_kv: float | None = None
    phase: str = ''


_COORDINATE_KEYS = {
    'From': (
        ('FromCoordX', 'FromCoordY'), ('FromX', 'FromY'), ('X1', 'Y1'),
    ),
    'To': (
        ('ToCoordX', 'ToCoordY'), ('ToX', 'ToY'), ('X2', 'Y2'),
    ),
}


def repair_missing_nodes(result: ReconstructionResult) -> ReconstructionResult:
    """Create only terminals that are explicitly referenced by source sections."""

    dataset = result.dataset
    for section_id in sorted(dataset.sections):
        section = dataset.sections[section_id]
        for side in ('From', 'To'):
            field = f'{side}NodeID'
            original = (section.get(field) or '').strip()
            node_id = original
            generated = not node_id
            if generated:
                node_id = _available_node_id(dataset.nodes, f'N_DERIVED_{section_id}_{side.upper()}')
                section[field] = node_id
                result.record_change(
                    entity_type='section', entity_id=section_id, field=field,
                    original_value=original, applied_value=node_id,
                    level=EvidenceLevel.ENGINEERING_ASSUMPTION,
                    rule='CREATE_TERMINAL_NODE',
                    reason=f'{field} was empty; a deterministic terminal was required.',
                    confidence=0.55,
                    provenance={'section_id': section_id, 'endpoint': side.lower()},
                )
            if node_id in dataset.nodes:
                continue
            row = _derived_node_row(dataset, section_id, section, side, node_id)
            dataset.nodes[node_id] = row
            result.record_change(
                entity_type='node', entity_id=node_id, field='__row__',
                original_value=None, applied_value=row,
                level=EvidenceLevel.ENGINEERING_ASSUMPTION,
                rule='CREATE_TERMINAL_NODE' if generated else 'RECOVER_REFERENCED_NODE',
                reason=(
                    f'{field} referenced a node omitted from NODE; its available endpoint '
                    'attributes were preserved.'
                ),
                confidence=0.6 if generated else 0.75,
                provenance={'section_id': section_id, 'endpoint': side.lower()},
            )
    return result


def repair_discontinuities(result: ReconstructionResult) -> ReconstructionResult:
    """Reconnect coordinate-coincident islands without crossing scope or voltage."""

    repair_missing_nodes(result)
    dataset = result.dataset
    tolerance = result.policy.topology_snap_tolerance
    if tolerance <= 0:
        return result

    for network_id in sorted(dataset.feeders):
        section_ids = tuple(dataset.feeders[network_id])
        source_node = _source_node(dataset, network_id)
        if not source_node:
            continue
        # One accepted alias may make a second island reachable, so recompute after
        # every repair. At most one new island joins the source component per pass.
        for _ in range(len(section_ids) + 1):
            adjacency = _adjacency(dataset, section_ids)
            reachable = _reachable(source_node, adjacency)
            all_nodes = set(adjacency)
            remaining = all_nodes - reachable
            if not remaining:
                break
            components = _components(remaining, adjacency)
            repaired = False
            for component in components:
                ranked = _rank_candidates(
                    dataset, network_id, section_ids, component, reachable, tolerance,
                )
                if not ranked:
                    continue
                chosen = ranked[0]
                candidate_ids = tuple(dict.fromkeys(item.target_node for item in ranked))
                rule = (
                    'UNIQUE_COMPATIBLE_CONNECTION'
                    if len(candidate_ids) == 1
                    else 'RANKED_AMBIGUOUS_CONNECTION'
                )
                confidence = 0.9 if len(candidate_ids) == 1 else 0.5
                _replace_node_references(
                    result,
                    section_ids,
                    chosen.island_node,
                    chosen.target_node,
                    rule=rule,
                    confidence=confidence,
                    candidates=candidate_ids,
                    distance=chosen.distance,
                    network_id=network_id,
                )
                repaired = True
                break
            if not repaired:
                break
    return result


def record_bridge_transformations(
    result: ReconstructionResult,
    feeder: str,
    bridge_report: Any,
) -> None:
    """Persist the existing ``fundir_puentes`` result after model construction.

    Bridge fusion belongs to the FeederModel stage, not to the canonical dataset.
    This hook keeps that later, derived transformation in the same audit report.
    """

    if is_dataclass(bridge_report):
        payload = asdict(bridge_report)
    elif isinstance(bridge_report, dict):
        payload = dict(bridge_report)
    else:
        raise TypeError('bridge_report must be a dataclass or mapping')
    result.report.metadata.setdefault('bridge_transformations', {})[feeder] = payload


def _available_node_id(nodes: dict[str, Any], base: str) -> str:
    if base not in nodes:
        return base
    index = 2
    while f'{base}_{index}' in nodes:
        index += 1
    return f'{base}_{index}'


def _derived_node_row(dataset, section_id, section, side, node_id) -> dict[str, str]:
    row: dict[str, str] = {'NodeID': node_id}
    for x_key, y_key in _COORDINATE_KEYS[side]:
        x, y = section.get(x_key), section.get(y_key)
        if x not in (None, '') and y not in (None, ''):
            row['CoordX'], row['CoordY'] = str(x), str(y)
            break
    for source_key, target_key in (
        ('Phase', 'Phase'), ('Company', 'Company'), ('CompanyID', 'CompanyID'),
        ('NominalVoltageKV', 'NominalVoltageKV'),
    ):
        if section.get(source_key) not in (None, ''):
            row[target_key] = str(section[source_key])
    owner = dataset.section_owner.get(section_id)
    source = dataset.sources.get(owner, {})
    for key in ('Company', 'CompanyID'):
        if key not in row and source.get(key) not in (None, ''):
            row[key] = str(source[key])
    voltage = _source_voltage(source)
    if 'NominalVoltageKV' not in row and voltage is not None:
        row['NominalVoltageKV'] = f'{voltage:g}'
    return row


def _source_node(dataset, network_id: str) -> str:
    source = dataset.sources.get(network_id, {})
    direct = (source.get('NodeID') or '').strip()
    if direct:
        return direct
    matches = sorted(node for node, owner in dataset.headnodes.items() if owner == network_id)
    return matches[0] if len(matches) == 1 else ''


def _adjacency(dataset, section_ids: Iterable[str]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for section_id in section_ids:
        section = dataset.sections.get(section_id, {})
        left = (section.get('FromNodeID') or '').strip()
        right = (section.get('ToNodeID') or '').strip()
        if not left or not right:
            continue
        graph[left].add(right)
        graph[right].add(left)
    return graph


def _reachable(source: str, adjacency: dict[str, set[str]]) -> set[str]:
    seen = {source}
    pending = deque([source])
    while pending:
        node = pending.popleft()
        for neighbor in adjacency.get(node, ()):
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return seen


def _components(nodes: set[str], adjacency: dict[str, set[str]]) -> list[set[str]]:
    result: list[set[str]] = []
    pending = set(nodes)
    while pending:
        seed = min(pending)
        component = _reachable(seed, adjacency) & nodes
        result.append(component)
        pending -= component
    return result


def _rank_candidates(
    dataset,
    network_id: str,
    section_ids: tuple[str, ...],
    component: set[str],
    reachable: set[str],
    tolerance: float,
) -> list[TopologyCandidate]:
    phases = _node_phases(dataset, section_ids)
    candidates: list[TopologyCandidate] = []
    for island_node in sorted(component):
        island_point = _coordinates(dataset.nodes.get(island_node, {}))
        if island_point is None:
            continue
        for target_node in sorted(reachable):
            target_point = _coordinates(dataset.nodes.get(target_node, {}))
            if target_point is None or not _compatible(
                dataset, network_id, island_node, target_node, phases,
            ):
                continue
            distance = math.hypot(
                island_point[0] - target_point[0],
                island_point[1] - target_point[1],
            )
            if distance <= tolerance:
                candidates.append(TopologyCandidate(
                    distance=distance,
                    island_node=island_node,
                    target_node=target_node,
                    voltage_kv=_node_voltage(dataset, network_id, island_node),
                    phase=''.join(sorted(phases.get(island_node, set()))),
                ))
    return sorted(candidates)


def _coordinates(row: dict[str, Any]) -> tuple[float, float] | None:
    for x_key, y_key in (('CoordX', 'CoordY'), ('X', 'Y'), ('Easting', 'Northing')):
        try:
            x, y = float(row.get(x_key)), float(row.get(y_key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            return x, y
    return None


def _node_phases(dataset, section_ids: Iterable[str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for section_id in section_ids:
        section = dataset.sections.get(section_id, {})
        phase = _phase_set(section.get('Phase'))
        for key in ('FromNodeID', 'ToNodeID'):
            node_id = (section.get(key) or '').strip()
            if node_id:
                result[node_id].update(phase)
    for node_id, row in dataset.nodes.items():
        explicit = _phase_set(row.get('Phase'))
        if explicit:
            result[node_id] = explicit
    return result


def _phase_set(value: Any) -> set[str]:
    return {letter for letter in str(value or '').upper() if letter in 'ABC'}


def _compatible(dataset, network_id, left, right, phases) -> bool:
    left_row, right_row = dataset.nodes.get(left, {}), dataset.nodes.get(right, {})
    source = dataset.sources.get(network_id, {})
    default_company = _first(source, 'CompanyID', 'Company', 'Utility', 'UtilityID')
    left_company = _first(left_row, 'CompanyID', 'Company', 'Utility', 'UtilityID') or default_company
    right_company = _first(right_row, 'CompanyID', 'Company', 'Utility', 'UtilityID') or default_company
    if left_company and right_company and left_company.casefold() != right_company.casefold():
        return False
    left_voltage = _node_voltage(dataset, network_id, left)
    right_voltage = _node_voltage(dataset, network_id, right)
    if (
        left_voltage is not None and right_voltage is not None
        and not math.isclose(left_voltage, right_voltage, rel_tol=1e-6, abs_tol=1e-6)
    ):
        return False
    left_phase, right_phase = phases.get(left, set()), phases.get(right, set())
    return not left_phase or not right_phase or bool(left_phase & right_phase)


def _node_voltage(dataset, network_id: str, node_id: str) -> float | None:
    row = dataset.nodes.get(node_id, {})
    for key in ('NominalVoltageKV', 'NominalVoltage', 'VoltageKV', 'kV'):
        value = _number(row.get(key))
        if value is not None:
            return value
    return _source_voltage(dataset.sources.get(network_id, {}))


def _source_voltage(source: dict[str, Any]) -> float | None:
    desired = _number(source.get('DesiredVoltage'))
    if desired is not None:
        return desired
    phase_voltage = _number(source.get('OperatingVoltageA'))
    return phase_voltage * math.sqrt(3) if phase_voltage is not None else None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or '').strip()
        if value:
            return value
    return ''


def _replace_node_references(
    result: ReconstructionResult,
    section_ids: Iterable[str],
    old_node: str,
    new_node: str,
    *,
    rule: str,
    confidence: float,
    candidates: tuple[str, ...],
    distance: float,
    network_id: str,
) -> None:
    for section_id in section_ids:
        section = result.dataset.sections.get(section_id, {})
        for field in ('FromNodeID', 'ToNodeID'):
            if section.get(field) != old_node:
                continue
            section[field] = new_node
            result.record_change(
                entity_type='section', entity_id=section_id, field=field,
                original_value=old_node, applied_value=new_node,
                level=EvidenceLevel.ENGINEERING_ASSUMPTION,
                rule=rule,
                reason=(
                    f'Disconnected endpoint was matched within {distance:.6g} coordinate '
                    'units using company, voltage and phase compatibility.'
                ),
                confidence=confidence,
                candidates=candidates,
                provenance={
                    'network_id': network_id,
                    'distance': distance,
                    'tolerance': result.policy.topology_snap_tolerance,
                },
            )
