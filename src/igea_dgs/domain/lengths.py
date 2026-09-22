"""Politica dimensional explicita para longitudes electricas."""

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from statistics import median
from typing import Any

from pyproj import CRS, Geod

from igea_dgs.model import FeederModel, Line


class LengthPolicy(StrEnum):
    TXT_AUTHORITATIVE = "txt_authoritative"
    GEODESIC_VALIDATED = "geodesic_validated"
    PROJECTED_VALIDATED = "projected_validated"


@dataclass(frozen=True, slots=True)
class LengthComparison:
    section_id: str
    txt_m: float
    gis_m: float | None
    ratio: float | None
    reason: str
    outlier: bool = False


def _paths(model: FeederModel, dataset: Any, line: Line) -> list[tuple[float, float]] | None:
    start = model.nodes[line.from_node]
    end = model.nodes[line.to_node]
    if None in (start.x, start.y, end.x, end.y):
        return None
    assert start.x is not None and start.y is not None
    assert end.x is not None and end.y is not None
    points = [(start.x, start.y)]
    rows = [row for row in dataset.intermediate_nodes if row.get("SectionID") == line.section_id]
    for row in sorted(rows, key=lambda item: float(item.get("SeqNumber") or 0)):
        try:
            points.append((float(row["CoordX"]), float(row["CoordY"])))
        except (KeyError, TypeError, ValueError):
            return None
    points.append((end.x, end.y))
    return points


def _gis_length(points: list[tuple[float, float]], crs: CRS, policy: LengthPolicy) -> float:
    if policy is LengthPolicy.GEODESIC_VALIDATED:
        if not crs.is_geographic:
            raise ValueError("GEODESIC_VALIDATED requires a geographic CRS")
        geod = crs.get_geod() or Geod(ellps="WGS84")
        return sum(abs(geod.inv(x0, y0, x1, y1)[2]) for (x0, y0), (x1, y1) in zip(points, points[1:]))
    if policy is LengthPolicy.PROJECTED_VALIDATED:
        if not crs.is_projected:
            raise ValueError("PROJECTED_VALIDATED requires a projected CRS")
        factor = crs.axis_info[0].unit_conversion_factor
        return sum(math.hypot(x1 - x0, y1 - y0) * factor for (x0, y0), (x1, y1) in zip(points, points[1:]))
    raise ValueError(f"Policy {policy} does not calculate GIS length")


def compare_lengths(line: Line, points: list[tuple[float, float]] | None, crs: CRS, policy: LengthPolicy) -> LengthComparison:
    txt_m = line.txt_length_m if line.txt_length_m is not None else line.length_m
    if policy is LengthPolicy.TXT_AUTHORITATIVE:
        return LengthComparison(line.section_id, txt_m, None, None, "TXT authoritative")
    if points is None:
        return LengthComparison(line.section_id, txt_m, None, None, "GIS coordinates missing")
    gis_m = _gis_length(points, crs, policy)
    ratio = gis_m / txt_m if txt_m > 0 else None
    return LengthComparison(line.section_id, txt_m, gis_m, ratio, policy.value)


def apply_length_policy(model: FeederModel, dataset: Any, source_crs: str, policy: LengthPolicy) -> FeederModel:
    crs = CRS.from_user_input(source_crs)
    comparisons = [compare_lengths(line, _paths(model, dataset, line), crs, policy) for line in model.lines]
    ratios = [item.ratio for item in comparisons if item.ratio is not None]
    centre: float | None = median(ratios) if ratios else None
    deviations = [abs(value - centre) for value in ratios] if centre is not None else []
    mad = median(deviations) if deviations else 0.0
    updated: list[Line] = []
    for line, comparison in zip(model.lines, comparisons, strict=True):
        if policy is LengthPolicy.TXT_AUTHORITATIVE or comparison.gis_m is None:
            updated.append(replace(line, length_m=comparison.txt_m, length_source="txt"))
            continue
        outlier = bool(mad and centre is not None and comparison.ratio is not None and abs(comparison.ratio - centre) > 3 * mad)
        if outlier:
            updated.append(replace(line, length_m=comparison.txt_m, length_source="txt"))
        else:
            updated.append(replace(line, length_m=comparison.gis_m, length_source=policy.value.removesuffix("_validated") + "_validated"))
    model.lines = updated
    model.section_by_id = {line.section_id: line for line in updated}
    return model
