"""Resolucion exacta: sin vecinos, fuzzy matching ni DEFAULT."""

from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping

from igea_dgs.domain.provenance import ProvenanceKind, Provenanced

from .models import ApprovedMapping, ResolvedEquipment


class UnresolvedEquipmentError(LookupError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class EquipmentCatalog:
    def __init__(
        self,
        equipment: Mapping[str, Mapping[str, Mapping[str, Any]]],
        mappings: Mapping[tuple[str, str], ApprovedMapping] | None = None,
    ) -> None:
        self.equipment = MappingProxyType(
            {kind: MappingProxyType(dict(entries)) for kind, entries in equipment.items()}
        )
        self.mappings = MappingProxyType(dict(mappings or {}))

    @staticmethod
    def mapping_fingerprint(mapping: ApprovedMapping, parameters: Mapping[str, Any]) -> str:
        def canonical(value: Any) -> str:
            if isinstance(value, float):
                return format(value, ".15g")
            return str(value)

        payload = "|".join(
            [mapping.target_id]
            + [canonical(parameters.get(name, "")) for name in mapping.compared_parameters]
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def resolve_exact(self, kind: str, source_id: str) -> ResolvedEquipment:
        entries: Mapping[str, Mapping[str, Any]] = self.equipment.get(kind, {})
        if source_id in entries and source_id != "DEFAULT":
            return ResolvedEquipment(
                kind,
                source_id,
                source_id,
                entries[source_id],
                Provenanced(source_id, ProvenanceKind.OBSERVED_CATALOG, source_id),
            )

        mapping = self.mappings.get((kind, source_id))
        if mapping is None or mapping.target_id not in entries:
            raise UnresolvedEquipmentError(
                "EQUIPMENT_NOT_FOUND", f"No exact equipment for {kind}:{source_id}"
            )
        parameters = entries[mapping.target_id]
        if self.mapping_fingerprint(mapping, parameters) != mapping.sha256:
            raise UnresolvedEquipmentError(
                "MAPPING_FINGERPRINT_MISMATCH",
                f"Approved mapping changed for {kind}:{source_id}",
            )
        return ResolvedEquipment(
            kind,
            source_id,
            mapping.target_id,
            parameters,
            Provenanced(mapping.target_id, ProvenanceKind.APPROVED_MAPPING, mapping.sha256),
            mapping,
        )
