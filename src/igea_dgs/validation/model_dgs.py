"""Comparación eléctrica modelo-DGS sin reutilizar el constructor."""

from decimal import Decimal
from typing import Mapping, Sequence

from igea_dgs.domain.feeder import StrictFeederModel
from igea_dgs.quality.diagnostics import Diagnostic

from .results import FidelityResult


def validate_model_dgs(
    feeder: StrictFeederModel,
    tables: Mapping[str, Sequence[Mapping[str, str]]],
) -> FidelityResult:
    diagnostics: list[Diagnostic] = []
    dgs_lines = {row.get("loc_name", ""): row for row in tables.get("ElmLne", ())}
    types = {row.get("FID", ""): row for row in tables.get("TypLne", ())}
    for line in feeder.lines:
        row = dgs_lines.get(line.section_id)
        if row is None:
            diagnostics.append(Diagnostic.blocking("MISSING_DGS_LINE", line.section_id))
            continue
        if int(row.get("nlnum") or 0) != line.circuits.count:
            diagnostics.append(Diagnostic.blocking("CIRCUIT_COUNT_MISMATCH", line.section_id))
        if Decimal(row.get("dline") or "NaN") != line.length_km:
            diagnostics.append(Diagnostic.blocking("LENGTH_MISMATCH", line.section_id))
        typ = types.get(row.get("typ_id", ""))
        if typ is None or Decimal(typ.get("rline") or "NaN") != line.r1_ohm_km:
            diagnostics.append(Diagnostic.blocking("R1_MISMATCH", line.section_id))
        if typ is None or Decimal(typ.get("bline") or "NaN") != line.b1_us_km:
            diagnostics.append(Diagnostic.blocking("B1_MISMATCH", line.section_id))
    return FidelityResult(tuple(diagnostics))
