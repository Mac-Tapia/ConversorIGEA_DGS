"""Inventario estricto de cobertura antes de construir el modelo electrico."""

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from igea_dgs.dataset import CymdistDataset
from igea_dgs.quality.diagnostics import Diagnostic
from igea_dgs.quality.gates import GateResult


@dataclass(frozen=True, slots=True)
class SectionCoverage:
    status: str
    count: int
    adapter: str | None


@dataclass(frozen=True, slots=True)
class DatasetInventory:
    coverage: Mapping[str, SectionCoverage]
    metrics: Mapping[str, Any]
    gate: GateResult

    @property
    def coverage_percent(self) -> float:
        if not self.coverage:
            return 100.0
        covered = sum(item.status != "unsupported" for item in self.coverage.values())
        return round(100.0 * covered / len(self.coverage), 2)


def _registry() -> dict[str, dict[str, Any]]:
    path = Path(__file__).resolve().parents[3] / "config" / "igea_sections.json"
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _section_count(dataset: CymdistDataset, name: str) -> int:
    adapters: dict[str, Any] = {
        "HEADNODES": dataset.headnodes,
        "NODE": dataset.nodes,
        "SOURCE": dataset.sources,
        "SECTION": dataset.sections,
        "LINE CONFIGURATION": dataset.line_configurations,
        "SWITCH SETTING": dataset.switch_settings,
        "SECTIONALIZER SETTING": dataset.sectionalizer_settings,
        "INTERMEDIATE NODES": dataset.intermediate_nodes,
        "LOADS": dataset.load_placements,
        "CUSTOMER LOADS": dataset.customer_loads,
    }
    target = adapters.get(name, dataset.equipment_tables.get(name, ()))
    return len(target)


def build_strict_inventory(dataset: CymdistDataset) -> DatasetInventory:
    registry = _registry()
    observed = {name for names in dataset.parsed_sections.values() for name in names}
    diagnostics = list(dataset.diagnostics)
    coverage: dict[str, SectionCoverage] = {}
    for name in sorted(observed):
        declaration = registry.get(name)
        if declaration is None:
            coverage[name] = SectionCoverage("unsupported", _section_count(dataset, name), None)
            diagnostics.append(
                Diagnostic.blocking(
                    "UNSUPPORTED_SECTION", f"Seccion TXT sin adaptador registrado: {name}"
                )
            )
            continue
        coverage[name] = SectionCoverage(
            str(declaration["status"]),
            _section_count(dataset, name),
            str(declaration.get("adapter") or "") or None,
        )

    phases = sorted(
        {row.get("Phase", "").strip() for row in dataset.sections.values() if row.get("Phase", "").strip()}
    )
    line_codes = sorted(
        {row.get("LineCableID", "").strip() for row in dataset.line_configurations.values() if row.get("LineCableID", "").strip()}
    )
    metrics: dict[str, Any] = {
        "sections": len(dataset.sections),
        "loads": len(dataset.customer_loads),
        "feeders": len(dataset.feeders),
        "phases": phases,
        "line_types_used": line_codes,
        "elements_per_feeder": {
            feeder: len(section_ids) for feeder, section_ids in dataset.feeders.items()
        },
    }
    return DatasetInventory(
        MappingProxyType(coverage),
        MappingProxyType(metrics),
        GateResult("G1-G2", diagnostics),
    )
