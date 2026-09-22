"""Resolución determinista de los tres TXT de entrada IGEA."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from .models import InputSelection


@dataclass(frozen=True, slots=True)
class InputResolutionError(ValueError):
    code: str
    kind: str
    candidates: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.code}: {self.kind} ({', '.join(self.candidates)})"


PATTERNS: dict[str, tuple[str, ...]] = {
    "red": ("RED_*.txt", "RED.txt"),
    "carga": ("CARGA_*.txt", "CARGA.txt"),
    "equipment": ("BD_Equipo*.txt",),
}


def _matches(folder: Path, patterns: tuple[str, ...]) -> tuple[Path, ...]:
    files = (item for item in folder.iterdir() if item.is_file())
    return tuple(
        sorted(
            (
                item.resolve(strict=True)
                for item in files
                if any(fnmatch.fnmatchcase(item.name.casefold(), p.casefold()) for p in patterns)
            ),
            key=lambda item: item.name.casefold(),
        )
    )


def detect_input_set(folder: Path, *, crs: str = "EPSG:32718") -> InputSelection:
    canonical = folder.resolve(strict=True)
    if not canonical.is_dir():
        raise NotADirectoryError(canonical)
    resolved: dict[str, Path] = {}
    for kind, patterns in PATTERNS.items():
        candidates = _matches(canonical, patterns)
        if not candidates:
            raise InputResolutionError("INPUT_TXT_MISSING", kind, ())
        if len(candidates) > 1:
            raise InputResolutionError(
                "INPUT_FILE_AMBIGUOUS", kind, tuple(str(item) for item in candidates)
            )
        resolved[kind] = candidates[0]
    return InputSelection(
        red_path=resolved["red"],
        carga_path=resolved["carga"],
        equipment_path=resolved["equipment"],
        output_dir=canonical,
        crs=crs,
    )
