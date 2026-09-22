"""Modelos inmutables para equipos y mappings aprobados."""

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Mapping

from igea_dgs.domain.provenance import Provenanced


@dataclass(frozen=True, slots=True)
class ApprovedMapping:
    source_id: str
    target_id: str
    medium: str
    compared_parameters: tuple[str, ...]
    justification: str
    approved_by: str
    approved_at: str
    sha256: str

    def with_sha256(self, value: str) -> "ApprovedMapping":
        return replace(self, sha256=value)


@dataclass(frozen=True, slots=True)
class ResolvedEquipment:
    kind: str
    source_id: str
    catalog_id: str
    parameters: Mapping[str, Any]
    provenance: Provenanced[str]
    mapping: ApprovedMapping | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
