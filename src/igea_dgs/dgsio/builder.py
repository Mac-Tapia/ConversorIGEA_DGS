"""Constructor DGS determinista sin decisiones electricas implícitas."""

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from igea_dgs.domain.feeder import StrictFeederModel
from igea_dgs.domain.equipment import UndergroundCable


@dataclass(frozen=True, slots=True)
class DgsDocument:
    tables: Mapping[str, tuple[Mapping[str, str], ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tables", MappingProxyType(dict(self.tables)))


def _text(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def build_dgs_document(feeder: StrictFeederModel) -> DgsDocument:
    type_rows: dict[str, dict[str, str]] = {}
    line_rows: list[dict[str, str]] = []
    terminal_rows: dict[str, dict[str, str]] = {}
    for index, line in enumerate(feeder.lines, 1):
        type_fid = f"T{index}"
        type_rows.setdefault(
            line.catalog_id,
            {
                "FID": type_fid,
                "OP": "C",
                "loc_name": line.catalog_id,
                "uline": _text(feeder.source.nominal_kv),
                "sline": _text(line.cross_section_mm2),
                "InomAir": _text(line.ampacity_a / Decimal("1000")),
                "cohl_": "1" if isinstance(line, UndergroundCable) else "0",
                "rline": _text(line.r1_ohm_km),
                "xline": _text(line.x1_ohm_km),
                "rline0": _text(line.r0_ohm_km),
                "xline0": _text(line.x0_ohm_km),
                "Ithr": _text(line.ampacity_a / Decimal("1000")),
                "nlnph": str(len(line.phases.value)),
                "bline": _text(line.b1_us_km),
                "bline0": _text(line.b0_us_km),
            },
        )
        for node in (line.from_node, line.to_node):
            terminal_rows.setdefault(node, {"FID": f"N{len(terminal_rows)+1}", "OP": "C", "loc_name": node, "uknom": _text(feeder.source.nominal_kv)})
        line_rows.append(
            {
                "FID": f"L{index}", "OP": "C", "loc_name": line.section_id,
                "typ_id": type_rows[line.catalog_id]["FID"], "dline": _text(line.length_km),
                "fline": "1", "nlnum": str(line.circuits.count),
                "inAir": "0" if isinstance(line, UndergroundCable) else "1",
            }
        )
    tables: dict[str, tuple[Mapping[str, str], ...]] = {
        "TypLne": tuple(type_rows.values()),
        "ElmTerm": tuple(terminal_rows.values()),
        "ElmLne": tuple(line_rows),
    }
    return DgsDocument(tables)
