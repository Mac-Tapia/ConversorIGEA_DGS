"""Validación independiente del modelo realmente materializado en PowerFactory."""

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from igea_dgs.domain.feeder import StrictFeederModel
from igea_dgs.quality.diagnostics import Diagnostic

from .results import FidelityResult


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def inspect_and_validate_pf(
    feeder: StrictFeederModel,
    port: Any,
    *,
    tolerance: Decimal = Decimal("0.000001"),
) -> FidelityResult:
    diagnostics: list[Diagnostic] = []
    rows: list[Mapping[str, object]] = list(port.list_objects("ElmLne"))
    actual = {str(row.get("external_id", "")): row for row in rows}
    expected_ids = {line.section_id for line in feeder.lines}
    if set(actual) != expected_ids:
        diagnostics.append(Diagnostic.blocking("PF_LINE_IDENTITY_MISMATCH", feeder.feeder_id))
    for line in feeder.lines:
        row = actual.get(line.section_id)
        if row is None:
            diagnostics.append(Diagnostic.blocking("PF_LINE_MISSING", line.section_id))
            continue
        exact = {
            "from_node": (line.from_node, "PF_FROM_NODE_MISMATCH"),
            "to_node": (line.to_node, "PF_TO_NODE_MISMATCH"),
            "phases": (line.phases.value, "PF_PHASES_MISMATCH"),
            "circuits": (line.circuits.count, "PF_CIRCUIT_COUNT_MISMATCH"),
            "conductors_per_phase": (
                line.conductors_per_phase,
                "PF_CONDUCTOR_COUNT_MISMATCH",
            ),
            "outserv": (0, "PF_STATUS_MISMATCH"),
        }
        for field, (expected_exact, code) in exact.items():
            if row.get(field) != expected_exact:
                diagnostics.append(Diagnostic.blocking(code, line.section_id))
        numeric = {
            "length_km": line.length_km,
            "cross_section_mm2": line.cross_section_mm2,
        }
        for field, expected_decimal in numeric.items():
            observed = _decimal(row.get(field))
            if observed is None or abs(observed - expected_decimal) > tolerance:
                diagnostics.append(
                    Diagnostic.blocking(f"PF_{field.upper()}_MISMATCH", line.section_id)
                )
    return FidelityResult(tuple(diagnostics))
