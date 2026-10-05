"""Pure, auditable reconstruction contract for canonical CYMDIST datasets.

The source dataset is never changed.  Rules operate on a derived copy and must
record every changed field together with its evidence.  Keeping this module
free of workspace and PowerFactory state makes the same reconstruction usable
by TXT, MDB and VNR-GIS adapters without mixing their primary files.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field, fields
from enum import Enum
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .dataset import CymdistDataset


class EvidenceLevel(str, Enum):
    """Origin of a value present in the derived dataset."""

    ORIGINAL = 'original'
    CATALOG_MATCH = 'catalog_match'
    ENGINEERING_ASSUMPTION = 'engineering_assumption'


@dataclass(frozen=True)
class ReconstructionPolicy:
    """Safety controls shared by reconstruction rule registries.

    Individual rule modules may add their own thresholds later, but the two
    permission flags make assumptions explicit at the contract boundary.
    """

    allow_catalog_matches: bool = True
    allow_engineering_assumptions: bool = True
    minimum_catalog_confidence: float = 0.75

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_catalog_confidence <= 1:
            raise ValueError('minimum_catalog_confidence must be between 0 and 1')


@dataclass(frozen=True)
class ReconstructionDecision:
    entity_type: str
    entity_id: str
    field: str
    original_value: Any
    applied_value: Any
    level: EvidenceLevel
    rule: str
    reason: str
    confidence: float
    candidates: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.original_value == self.applied_value:
            raise ValueError('original_value and applied_value must be different')
        if self.level is EvidenceLevel.ORIGINAL:
            raise ValueError('a changed field cannot have original evidence')
        if not self.entity_type.strip() or not self.entity_id.strip() or not self.field.strip():
            raise ValueError('entity_type, entity_id and field are required')
        if not self.rule.strip() or not self.reason.strip():
            raise ValueError('rule and reason are required')
        if not 0 <= self.confidence <= 1:
            raise ValueError('confidence must be between 0 and 1')

    def to_dict(self) -> dict[str, Any]:
        return {
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'field': self.field,
            'original_value': _json_safe(self.original_value),
            'applied_value': _json_safe(self.applied_value),
            'level': self.level.value,
            'rule': self.rule,
            'reason': self.reason,
            'confidence': self.confidence,
            'candidates': list(self.candidates),
            'provenance': _json_safe(dict(self.provenance)),
        }


@dataclass
class ReconstructionReport:
    decisions: list[ReconstructionDecision] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_change(self, decision: ReconstructionDecision) -> ReconstructionDecision:
        decision.validate()
        self.decisions.append(decision)
        return decision

    def to_dict(self) -> dict[str, Any]:
        counts = Counter(decision.level.value for decision in self.decisions)
        return {
            'decisions': [decision.to_dict() for decision in self.decisions],
            'counts': dict(sorted(counts.items())),
            'metadata': _json_safe(self.metadata),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, indent=indent,
        )


@dataclass
class ReconstructionResult:
    dataset: CymdistDataset
    report: ReconstructionReport
    policy: ReconstructionPolicy

    def record_change(
        self,
        *,
        entity_type: str,
        entity_id: str,
        field: str,
        original_value: Any,
        applied_value: Any,
        level: EvidenceLevel,
        rule: str,
        reason: str,
        confidence: float,
        candidates: Iterable[str] = (),
        provenance: Mapping[str, Any] | None = None,
    ) -> ReconstructionDecision:
        if level is EvidenceLevel.CATALOG_MATCH and not self.policy.allow_catalog_matches:
            raise ValueError('catalog matches are disabled by reconstruction policy')
        if (
            level is EvidenceLevel.ENGINEERING_ASSUMPTION
            and not self.policy.allow_engineering_assumptions
        ):
            raise ValueError('engineering assumptions are disabled by reconstruction policy')
        decision = ReconstructionDecision(
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            original_value=deepcopy(original_value),
            applied_value=deepcopy(applied_value),
            level=level,
            rule=rule,
            reason=reason,
            confidence=confidence,
            candidates=tuple(candidates),
            provenance=deepcopy(dict(provenance or {})),
        )
        return self.report.record_change(decision)


def _copy_dataset(dataset: CymdistDataset) -> CymdistDataset:
    """Copy only declared canonical fields, excluding cached derived indexes."""

    return CymdistDataset(**{
        item.name: deepcopy(getattr(dataset, item.name))
        for item in fields(CymdistDataset)
    })


def reconstruct_dataset(
    dataset: CymdistDataset,
    policy: ReconstructionPolicy | None = None,
    catalogs: Iterable[Any] = (),
) -> ReconstructionResult:
    """Create the isolated reconstruction working copy.

    Topology and catalogue registries are deliberately composed by subsequent
    modules.  At this contract layer no rule is implicit and therefore no
    decision is fabricated merely because the function was called.
    """

    effective_policy = policy or ReconstructionPolicy()
    catalog_list = tuple(catalogs)
    report = ReconstructionReport(metadata={'catalog_count': len(catalog_list)})
    return ReconstructionResult(
        dataset=_copy_dataset(dataset),
        report=report,
        policy=effective_policy,
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
