"""Auditoria canonica posterior a cualquier adaptador de fuente.

Los adaptadores solo traducen su formato a ``CymdistDataset``. Desde aqui no existe
ninguna bifurcacion por procedencia: la propiedad del alimentador, los conteos y los
bloqueos se calculan una sola vez sobre el dataset normalizado.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .naming import feeder_short_name, sort_key_feeder


@dataclass(frozen=True)
class SourceIssue:
    code: str
    severity: str
    object_type: str
    object_id: str
    feeder: str = ''
    detail: str = ''

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeederSourceAudit:
    feeder: str
    network_id: str
    status: str
    counts: Mapping[str, int]
    blocking_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            'feeder': self.feeder,
            'network_id': self.network_id,
            'status': self.status,
            'counts': dict(self.counts),
            'blocking_codes': list(self.blocking_codes),
            'warning_codes': list(self.warning_codes),
        }


@dataclass(frozen=True)
class UniversalSourceAudit:
    source_run_id: str
    source_mode: str
    source_fingerprint: str
    totals: Mapping[str, int]
    feeders: tuple[FeederSourceAudit, ...]
    issues: tuple[SourceIssue, ...] = ()
    format: str = 'igea-dgs-universal-source-audit-v1'

    @property
    def status(self) -> str:
        return (
            'SOURCE_AUDIT_BLOCKED'
            if any(issue.severity == 'blocking' for issue in self.issues)
            else 'SOURCE_AUDIT_OK'
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            'format': self.format,
            'status': self.status,
            'source_run_id': self.source_run_id,
            'source_mode': self.source_mode,
            'source_fingerprint': self.source_fingerprint,
            'totals': dict(self.totals),
            'feeders': [item.as_dict() for item in self.feeders],
            'issues': [item.as_dict() for item in self.issues],
        }


def audit_source(dataset: Any, provenance: Mapping[str, Any]) -> UniversalSourceAudit:
    """Recorre una vez el dataset comun y devuelve evidencia determinista."""
    owners = dict(dataset.section_owner)
    issues: dict[tuple[str, str], SourceIssue] = {}
    loads_by_owner: dict[str, set[tuple[str, str]]] = {
        network_id: set() for network_id in dataset.feeders
    }
    placements_by_owner: dict[str, set[tuple[str, str]]] = {
        network_id: set() for network_id in dataset.feeders
    }

    for table_name, rows, target in (
        ('CUSTOMER_LOADS', dataset.customer_loads, loads_by_owner),
        ('LOADS', dataset.load_placements, placements_by_owner),
    ):
        for raw_key in rows:
            section_id, device = str(raw_key[0]), str(raw_key[1])
            key = (section_id, device)
            owner = owners.get(section_id)
            if owner in target:
                target[owner].add(key)
                continue
            issue_key = ('MISSING_LOAD_FEEDER', f'{section_id}/{device}')
            previous = issues.get(issue_key)
            detail = table_name if previous is None else f'{previous.detail},{table_name}'
            issues[issue_key] = SourceIssue(
                code='MISSING_LOAD_FEEDER',
                severity='blocking',
                object_type='load',
                object_id=issue_key[1],
                detail=detail,
            )

    global_blockers = tuple(sorted({
        issue.code for issue in issues.values() if issue.severity == 'blocking'
    }))
    feeder_audits: list[FeederSourceAudit] = []
    for network_id in sorted(dataset.feeders, key=sort_key_feeder):
        counts = {
            'sections': len(dataset.feeders.get(network_id) or ()),
            'sources': int(network_id in dataset.sources),
            'customer_loads': len(loads_by_owner[network_id]),
            'load_placements': len(placements_by_owner[network_id]),
        }
        feeder_audits.append(FeederSourceAudit(
            feeder=feeder_short_name(network_id),
            network_id=network_id,
            status='SOURCE_AUDIT_BLOCKED' if global_blockers else 'SOURCE_AUDIT_OK',
            counts=counts,
            blocking_codes=global_blockers,
        ))

    return UniversalSourceAudit(
        source_run_id=str(provenance.get('source_run_id') or ''),
        source_mode=str(provenance.get('source_mode') or ''),
        source_fingerprint=str(provenance.get('source_fingerprint') or ''),
        totals={
            'feeders': len(dataset.feeders),
            'sections': len(dataset.sections),
            'customer_loads': len(dataset.customer_loads),
            'load_placements': len(dataset.load_placements),
            'issues': len(issues),
        },
        feeders=tuple(feeder_audits),
        issues=tuple(issues[key] for key in sorted(issues)),
    )
