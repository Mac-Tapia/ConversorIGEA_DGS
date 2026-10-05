"""Puertas deterministas por alimentador antes de producir artefactos DGS.

El inventario siempre permanece visible. La preparación, en cambio, falla cerrada:
un lote solo se autoriza cuando cada alimentador solicitado tiene topología, fuente y
una correspondencia exacta entre los códigos usados y el catálogo custodiado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..dataset import TABLAS_TIPOS_LINEA
from ..naming import feeder_short_name


READY_STATES = frozenset({
    'CONVERSION_READY', 'READY_ORIGINAL', 'READY_RECONSTRUCTED',
    'CONVERTED_WITH_ASSUMPTIONS', 'DGS_READY', 'POWERFACTORY_VERIFIED',
})


@dataclass(frozen=True)
class FeederReadiness:
    feeder: str
    network_id: str
    status: str
    blocking_codes: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            'feeder': self.feeder,
            'network_id': self.network_id,
            'status': self.status,
            'blocking_codes': list(self.blocking_codes),
            'details': dict(self.details),
        }


class FeederReadinessError(ValueError):
    """La selección no existe o contiene alimentadores no convertibles."""


def _network_id(dataset: Any, feeder: str) -> str | None:
    if feeder in dataset.feeders:
        return feeder
    matches = [item for item in dataset.feeder_ids() if feeder_short_name(item) == feeder]
    return matches[0] if len(matches) == 1 else None


def _catalog_ids(dataset: Any) -> set[str]:
    result: set[str] = set()
    for table, rows in dataset.equipment_tables.items():
        if table not in TABLAS_TIPOS_LINEA:
            continue
        result.update((row.get('ID') or '').strip() for row in rows)
    result.discard('')
    return result


def assess_feeder_readiness(
    dataset: Any,
    feeder: str,
    provenance: Mapping[str, Any],
    *,
    aliases: Mapping[str, str] | None = None,
) -> FeederReadiness:
    """Evalúa un alimentador sin recurrir a vecinos ni a ``DEFAULT`` implícito."""
    network_id = _network_id(dataset, feeder)
    if network_id is None:
        return FeederReadiness(
            feeder=feeder,
            network_id=feeder,
            status='INVENTORY_ONLY',
            blocking_codes=('UNKNOWN_OR_AMBIGUOUS_FEEDER',),
        )

    blockers: list[str] = []
    section_ids = tuple(dataset.feeders.get(network_id) or ())
    if network_id not in dataset.sources:
        blockers.append('MISSING_SOURCE')
    if not section_ids:
        blockers.append('MISSING_TOPOLOGY')

    missing_configuration = False
    missing_nodes = False
    used_codes: set[str] = set()
    for section_id in section_ids:
        section = dataset.sections.get(section_id) or {}
        if (
            not section.get('FromNodeID')
            or not section.get('ToNodeID')
            or section.get('FromNodeID') not in dataset.nodes
            or section.get('ToNodeID') not in dataset.nodes
        ):
            missing_nodes = True
        configuration = dataset.line_configurations.get(section_id)
        if configuration is None:
            missing_configuration = True
            continue
        used_codes.add((configuration.get('LineCableID') or '').strip())
    if missing_configuration:
        blockers.append('MISSING_LINE_CONFIGURATION')
    if missing_nodes:
        blockers.append('MISSING_NODES')

    catalog_ids = _catalog_ids(dataset)
    alias_map = aliases or {}
    unresolved = sorted(
        code for code in used_codes
        if not code or (code not in catalog_ids and alias_map.get(code) not in catalog_ids)
    )
    if unresolved:
        blockers.append('MISSING_EXACT_CONDUCTOR_MAPPING')

    blockers = list(dict.fromkeys(blockers))
    return FeederReadiness(
        feeder=feeder_short_name(network_id),
        network_id=network_id,
        status='CONVERSION_READY' if not blockers else 'INVENTORY_ONLY',
        blocking_codes=tuple(blockers),
        details={
            'source_mode': provenance.get('source_mode'),
            'sections': len(section_ids),
            'unresolved_conductor_codes': unresolved,
        },
    )


def build_feeder_readiness(
    dataset: Any,
    inventory_rows: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
    *,
    supplied: Mapping[str, Mapping[str, Any]] | None = None,
    aliases: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Normaliza la evaluación propia o las puertas más estrictas de un adaptador."""
    result: dict[str, dict[str, Any]] = {}
    supplied = supplied or {}
    for inventory in inventory_rows:
        feeder = str(inventory['feeder'])
        network_id = str(inventory['network_id'])
        row = supplied.get(network_id) or supplied.get(feeder)
        if row is None:
            normalized = assess_feeder_readiness(
                dataset, network_id, provenance, aliases=aliases,
            ).as_dict()
        else:
            blockers = list(dict.fromkeys(str(code) for code in row.get('blocking_codes') or []))
            status = str(row.get('status') or 'INVENTORY_ONLY')
            if status in READY_STATES and blockers:
                status = 'INVENTORY_ONLY'
            normalized = {
                **dict(row),
                'feeder': feeder,
                'network_id': network_id,
                'status': status,
                'blocking_codes': blockers,
            }
        result[network_id] = normalized
    return result


def validate_selection(
    inventory_rows: Sequence[Mapping[str, Any]],
    readiness: Mapping[str, Mapping[str, Any]],
    feeders: Sequence[str] | None,
    *,
    all_feeders: bool,
) -> list[str]:
    """Resuelve uno/varios/todos y rechaza el lote completo si una fila no está lista."""
    by_name: dict[str, Mapping[str, Any]] = {}
    for row in inventory_rows:
        by_name[str(row['feeder'])] = row
        by_name[str(row['network_id'])] = row

    selected_rows: list[Mapping[str, Any]] = []
    if all_feeders:
        selected_rows = list(inventory_rows)
    else:
        unknown: list[str] = []
        seen: set[str] = set()
        for requested in feeders or ():
            row = by_name.get(str(requested))
            if row is None:
                unknown.append(str(requested))
                continue
            network_id = str(row['network_id'])
            if network_id not in seen:
                selected_rows.append(row)
                seen.add(network_id)
        if unknown:
            raise FeederReadinessError('UNKNOWN_FEEDER: ' + ', '.join(unknown))
    if not selected_rows:
        raise FeederReadinessError('EMPTY_FEEDER_SELECTION')

    blocked: list[str] = []
    for row in selected_rows:
        state = readiness.get(str(row['network_id'])) or {}
        status = state.get('status', 'INVENTORY_ONLY')
        if status not in READY_STATES:
            codes = list(state.get('blocking_codes') or ['READINESS_NOT_ASSESSED'])
            blocked.append(f"{row['feeder']} [{', '.join(codes)}]")
    if blocked:
        raise FeederReadinessError(
            'FEEDER_NOT_CONVERSION_READY: ' + '; '.join(blocked)
        )
    return [str(row['feeder']) for row in selected_rows]
