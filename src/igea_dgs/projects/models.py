"""Contratos inmutables de custodia de proyectos locales."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InputSelection:
    red_path: Path
    carga_path: Path
    equipment_path: Path
    output_dir: Path
    crs: str


@dataclass(frozen=True, slots=True)
class InputFile:
    kind: str
    path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InputManifest:
    project_id: str
    files: tuple[InputFile, ...]
    output_dir: str
    crs: str
    registered_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "files": [item.to_dict() for item in self.files],
            "output_dir": self.output_dir,
            "crs": self.crs,
            "registered_at": self.registered_at,
        }
