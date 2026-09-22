"""Adaptador estricto TXT a dominio electrico por fase y circuito."""

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from igea_dgs.quality.diagnostics import Diagnostic
from igea_dgs.quality.gates import GateResult

from .equipment import (
    CircuitMultiplicity,
    LoadSpec,
    OverheadLine,
    SourceSpec,
    UndergroundCable,
)
from .phases import PhaseSet


@dataclass(frozen=True, slots=True)
class StrictFeederModel:
    feeder_id: str
    source: SourceSpec
    lines: tuple[OverheadLine | UndergroundCable, ...]
    loads: tuple[LoadSpec, ...]


def _decimal(value: str | None, field: str) -> Decimal:
    try:
        result = Decimal(value or "")
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {field}: {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"Invalid {field}: {value!r}")
    return result


def _load_power(row: dict[str, str]) -> tuple[Decimal, Decimal]:
    value_type = row.get("ValueType", "")
    if value_type != "2":
        GateResult(
            "G2-LOAD",
            [Diagnostic.blocking("UNSUPPORTED_LOAD_VALUE_TYPE", f"Unsupported ValueType={value_type!r}")],
        ).raise_if_blocked()
    kw = _decimal(row.get("Value1"), "Value1")
    pf = _decimal(row.get("Value2"), "Value2")
    if not (Decimal("0") < abs(pf) <= Decimal("1")):
        raise ValueError("Power factor must be in (0, 1]")
    p_mw = kw / Decimal("1000")
    q = Decimal(str(abs(float(p_mw)) * math.tan(math.acos(float(abs(pf))))))
    return p_mw, -q if pf < 0 else q


def build_strict_feeder_model(dataset: Any, feeder_id: str) -> StrictFeederModel:
    source_row = dataset.sources[feeder_id]
    source = SourceSpec(
        feeder_id,
        source_row["NodeID"],
        _decimal(source_row.get("DesiredVoltage"), "DesiredVoltage"),
    )
    lines: list[OverheadLine | UndergroundCable] = []
    for section_id in dataset.feeders[feeder_id]:
        section = dataset.sections[section_id]
        cfg = dataset.line_configurations[section_id]
        common = dict(
            section_id=section_id,
            from_node=section["FromNodeID"],
            to_node=section["ToNodeID"],
            phases=PhaseSet.parse(section["Phase"]),
            catalog_id=cfg["LineCableID"],
            length_km=_decimal(cfg.get("Length"), "Length"),
            circuits=CircuitMultiplicity(int(cfg["NumberOfCircuits"])),
            conductors_per_phase=int(cfg["ConductorsPerPhase"]),
            cross_section_mm2=_decimal(cfg.get("CrossSection"), "CrossSection"),
        )
        line_type = OverheadLine if cfg.get("Overhead") == "1" else UndergroundCable
        lines.append(line_type(**common))
    loads: list[LoadSpec] = []
    for key, row in dataset.customer_loads.items():
        if key[0] not in dataset.feeders[feeder_id]:
            continue
        p_mw, q_mvar = _load_power(row)
        loads.append(LoadSpec(key[0], key[1], PhaseSet.parse(row["Phase"]), p_mw, q_mvar))
    return StrictFeederModel(feeder_id, source, tuple(lines), tuple(loads))
