"""Instantánea de entrada: qué ficheros forman una lectura y su huella.

Son datos puros. Estaban en ``web/source_runs.py``, y por eso los adaptadores de
entrada dependían de la web y el CLI no podía usarlos sin arrastrar FastAPI (spec 001,
RF-1). La custodia (copiar a ``runs/``, escribir el manifiesto) sigue en la web.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
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


def fingerprint(mode: SourceMode, files: list[SourceFile]) -> str:
    identity = {
        'mode': mode,
        'files': [
            {'slot': item.slot, 'name': item.name, 'size': item.size, 'sha256': item.sha256}
            for item in sorted(files, key=lambda item: item.slot)
        ],
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def snapshot_from_paths(
    mode: SourceMode, files: Mapping[str, str | Path], root: Path, *, origin: str,
) -> SourceSnapshot:
    """Instantánea sobre los ficheros donde están, sin copiarlos.

    La web copia cada entrada a ``runs/`` para custodiarla; el CLI es de un solo uso y
    copiar una ``.mdb`` de varios GB no aporta nada. ``root`` es donde un adaptador puede
    escribir derivados (VNR-GIS descomprime ahí el paquete).
    """
    from ..util import sha256_file

    items = [
        SourceFile(slot=slot, name=Path(path).name, path=Path(path),
                   size=Path(path).stat().st_size, sha256=sha256_file(path),
                   origin=origin, source_path=str(path))
        for slot, path in files.items()
    ]
    return SourceSnapshot(
        run_id=f'{origin}-{time.strftime("%Y%m%dT%H%M%S")}', mode=mode, root=root,
        fingerprint=fingerprint(mode, items), created_at=time.time(),
        files={item.slot: item for item in items},
    )
