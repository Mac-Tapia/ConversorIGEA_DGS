"""Regla conservadora para excluir TRAFOMIX y solo su carga demostrablemente asociada."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from igea_dgs.quality.diagnostics import Diagnostic
from igea_dgs.quality.gates import GateResult

AssetKey = tuple[str, str]


class AssetClassification(StrEnum):
    TRAFOMIX = "trafomix"
    SED_LOAD = "sed_load"
    LOAD = "load"
    UNKNOWN = "unknown"


def classify_distribution_asset(record_set: dict[str, str]) -> AssetClassification:
    explicit = (record_set.get("EquipmentType") or record_set.get("DeviceType") or "").strip().upper()
    if explicit == "TRAFOMIX":
        return AssetClassification.TRAFOMIX
    if explicit in {"SED_LOAD", "SED", "DISTRIBUTION_SUBSTATION_LOAD"}:
        return AssetClassification.SED_LOAD
    if record_set.get("ParentDevice"):
        return AssetClassification.LOAD
    return AssetClassification.UNKNOWN


@dataclass(frozen=True, slots=True)
class RuleResult:
    excluded_keys: frozenset[AssetKey]
    retained_load_keys: frozenset[AssetKey]
    gate: GateResult


def apply_trafomix_rule(dataset: Any) -> RuleResult:
    placements: dict[AssetKey, dict[str, str]] = dataset.load_placements
    trafomix = {
        key for key, row in placements.items()
        if classify_distribution_asset(row) is AssetClassification.TRAFOMIX
    }
    excluded: set[AssetKey] = set(trafomix)
    diagnostics: list[Diagnostic] = []
    for section_id, device_number in trafomix:
        related = {
            key for key, row in placements.items()
            if key[0] == section_id and row.get("ParentDevice", "").strip() == device_number
        }
        if len(related) > 1:
            diagnostics.append(
                Diagnostic.blocking(
                    "TRAFOMIX_AMBIGUOUS_RELATION",
                    f"TRAFOMIX {section_id}/{device_number} has {len(related)} associated loads",
                )
            )
            continue
        excluded.update(related)
    retained = frozenset(set(dataset.customer_loads) - excluded)
    return RuleResult(frozenset(excluded), retained, GateResult("G2-TRAFOMIX", diagnostics))
