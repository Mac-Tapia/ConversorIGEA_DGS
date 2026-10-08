"""Instantánea de entrada: qué ficheros forman una lectura y su huella.

Son datos puros. Estaban en ``web/source_runs.py``, y por eso los adaptadores de
entrada dependían de la web y el CLI no podía usarlos sin arrastrar FastAPI (spec 001,
RF-1). La custodia (copiar a ``runs/``, escribir el manifiesto) sigue en la web.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SourceMode = Literal['txt', 'mdb', 'vnr']

MODE_SLOTS: dict[SourceMode, tuple[str, ...]] = {
    'txt': ('red', 'loads', 'equipment', 'equipment_extra'),
    'mdb': ('mdb', 'equipment_mdb', 'study'),
    'vnr': ('vnr_package',),
}
COMMON_SLOTS = ('aliases',)


@dataclass(frozen=True)
class SourceFile:
    slot: str
    name: str
    path: Path
    size: int
    sha256: str
    origin: str
    source_path: str

    def to_dict(self, run_root: Path) -> dict[str, Any]:
        return {
            'slot': self.slot,
            'name': self.name,
            'path': self.path.relative_to(run_root).as_posix(),
            'size': self.size,
            'sha256': self.sha256,
            'origin': self.origin,
            'source_path': self.source_path,
        }


@dataclass(frozen=True)
class SourceSnapshot:
    run_id: str
    mode: SourceMode
    root: Path
    fingerprint: str
    created_at: float
    files: dict[str, SourceFile]

    def path_for(self, slot: str) -> str:
        item = self.files.get(slot)
        return str(item.path) if item else ''
