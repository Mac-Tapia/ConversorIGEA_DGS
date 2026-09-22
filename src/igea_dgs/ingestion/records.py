"""Registros lossless provenientes de TXT IGEA."""

from dataclasses import dataclass
from pathlib import Path

from igea_dgs.quality.gates import GateResult


@dataclass(frozen=True, slots=True)
class RawRecord:
    section: str
    columns: tuple[str, ...]
    values: tuple[str, ...]
    extra_columns: tuple[str, ...]
    line_number: int
    original_text: str

    def as_dict(self) -> dict[str, str]:
        return dict(zip(self.columns, self.values, strict=True))


@dataclass(frozen=True, slots=True)
class ParsedFile:
    path: Path
    sha256: str
    records: tuple[RawRecord, ...]
    parsed_sections: tuple[str, ...]
    gate: GateResult
