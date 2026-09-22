"""Comparación fuente-modelo calculada directamente desde registros TXT."""

from decimal import Decimal
from typing import Any

from igea_dgs.domain.feeder import StrictFeederModel
from igea_dgs.quality.diagnostics import Diagnostic

from .results import FidelityResult


def validate_source_model(source: Any, feeder: StrictFeederModel) -> FidelityResult:
    diagnostics: list[Diagnostic] = []
    actual = {line.section_id: line for line in feeder.lines}
    expected_sections = source.feeders[feeder.feeder_id]
    for section_id in expected_sections:
        row = source.sections[section_id]
        cfg = source.line_configurations[section_id]
        line = actual.get(section_id)
        if line is None:
            diagnostics.append(Diagnostic.blocking("MISSING_MODEL_LINE", section_id))
            continue
        expected_phase = "".join(phase for phase in "ABC" if phase in row["Phase"].upper())
        if line.phases.value != expected_phase:
            diagnostics.append(Diagnostic.blocking("PHASE_MISMATCH", section_id))
        if line.circuits.count != int(cfg["NumberOfCircuits"]):
            diagnostics.append(Diagnostic.blocking("CIRCUIT_COUNT_MISMATCH", section_id))
        if line.cross_section_mm2 != Decimal(cfg["CrossSection"]):
            diagnostics.append(Diagnostic.blocking("CROSS_SECTION_MISMATCH", section_id))
    if set(actual) != set(expected_sections):
        diagnostics.append(Diagnostic.blocking("LINE_IDENTITY_MISMATCH", feeder.feeder_id))
    return FidelityResult(tuple(diagnostics))
