"""Procedencia auditable para valores electricos y geograficos."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class ProvenanceKind(StrEnum):
    OBSERVED_TXT = "observed_txt"
    OBSERVED_CATALOG = "observed_catalog"
    MANUFACTURER_DATASHEET = "manufacturer_datasheet"
    APPROVED_MAPPING = "approved_mapping"
    DERIVED = "derived"
    ASSUMED = "assumed"


_PRODUCTION_KINDS = frozenset(ProvenanceKind) - {ProvenanceKind.ASSUMED}


@dataclass(frozen=True, slots=True)
class Provenanced(Generic[T]):  # noqa: UP046 - contrato publico compatible con Generic[T]
    value: T
    kind: ProvenanceKind
    source: str

    @property
    def production_eligible(self) -> bool:
        return self.kind in _PRODUCTION_KINDS and bool(self.source.strip())

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "kind": self.kind.value, "source": self.source}
