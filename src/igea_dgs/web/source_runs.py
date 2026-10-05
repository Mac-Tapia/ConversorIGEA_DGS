"""Custodia inmutable de los archivos que forman una ejecución web.

Una instantánea se crea antes de leer la fuente. Los lectores posteriores reciben
únicamente las rutas custodiadas, de modo que un cambio en una ruta del servidor o
la presencia de casillas de otra modalidad no puede alterar la conversión activa.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:  # pragma: no cover - solo para tipos, evita un ciclo de imports
    from .workspace import Workspace

SourceMode = Literal['txt', 'mdb', 'vnr']

MODE_SLOTS: dict[SourceMode, tuple[str, ...]] = {
    'txt': ('red', 'loads', 'equipment', 'equipment_extra'),
    'mdb': ('mdb', 'equipment_mdb', 'study'),
    'vnr': ('vnr_package',),
}
COMMON_SLOTS = ('aliases',)
_RUN_ID_RE = re.compile(r'^\d{8}T\d{6}-[a-f0-9]{12}$')


def valid_run_id(run_id: str) -> bool:
    """Solo acepta el identificador generado, nunca componentes de ruta."""
    return bool(_RUN_ID_RE.fullmatch(run_id or ''))


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
class SourceRunManifest:
    version: int
    run_id: str
    mode: SourceMode
    created_at: float
    fingerprint: str
    files: tuple[SourceFile, ...]

    def to_dict(self, run_root: Path) -> dict[str, Any]:
        return {
            'version': self.version,
            'run_id': self.run_id,
            'mode': self.mode,
            'created_at': self.created_at,
            'fingerprint': self.fingerprint,
            'files': [item.to_dict(run_root) for item in self.files],
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


def _sha256_copy(source: Path, target: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.part')
    try:
        with source.open('rb') as src, temporary.open('xb') as dst:
            while chunk := src.read(1024 * 1024):
                dst.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return size, digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8',
    )
    temporary.replace(path)


def _fingerprint(mode: SourceMode, files: list[SourceFile]) -> str:
    identity = {
        'mode': mode,
        'files': [
            {'slot': item.slot, 'name': item.name, 'size': item.size, 'sha256': item.sha256}
            for item in sorted(files, key=lambda item: item.slot)
        ],
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def create_source_run(ws: Workspace) -> SourceSnapshot:
    """Copia solo las entradas del modo activo y activa la instantánea resultante."""
    raw_mode = str(ws.options.get('input_mode') or '')
    if raw_mode not in MODE_SLOTS:
        raise ValueError(f'Modo de entrada desconocido: {raw_mode!r}.')
    mode: SourceMode = raw_mode  # type: ignore[assignment]
    run_id = f'{time.strftime("%Y%m%dT%H%M%S")}-{uuid.uuid4().hex[:12]}'
    run_root = ws.root / 'runs' / run_id
    custody_root = run_root / 'originales'
    copied: list[SourceFile] = []
    try:
        for slot in (*MODE_SLOTS[mode], *COMMON_SLOTS):
            meta = ws.inputs.get(slot)
            if not meta:
                continue
            source = Path(meta['path'])
            if not source.is_file():
                raise FileNotFoundError(f'No se encuentra la entrada {slot}: {source}')
            target = custody_root / ('comun' if slot in COMMON_SLOTS else mode) / slot / source.name
            size, digest = _sha256_copy(source, target)
            copied.append(SourceFile(
                slot=slot,
                name=source.name,
                path=target,
                size=size,
                sha256=digest,
                origin=str(meta.get('origin') or ''),
                source_path=str(source),
            ))
        fingerprint = _fingerprint(mode, copied)
        manifest = SourceRunManifest(
            version=1,
            run_id=run_id,
            mode=mode,
            created_at=time.time(),
            fingerprint=fingerprint,
            files=tuple(copied),
        )
        _atomic_json(run_root / 'source_manifest.json', manifest.to_dict(run_root))
    except BaseException:
        shutil.rmtree(run_root, ignore_errors=True)
        raise

    snapshot = SourceSnapshot(
        run_id=run_id,
        mode=mode,
        root=run_root,
        fingerprint=fingerprint,
        created_at=manifest.created_at,
        files={item.slot: item for item in copied},
    )
    with ws.lock:
        ws.active_run_id = run_id
        ws.save()
    return snapshot


def load_source_run(ws: Workspace, run_id: str) -> SourceSnapshot:
    if not valid_run_id(run_id):
        raise ValueError(f'Identificador de ejecución inválido: {run_id!r}.')
    run_root = ws.root / 'runs' / run_id
    manifest_path = run_root / 'source_manifest.json'
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    mode = payload.get('mode')
    if mode not in MODE_SLOTS:
        raise ValueError(f'Manifiesto con modo desconocido: {mode!r}.')
    files: dict[str, SourceFile] = {}
    for raw in payload.get('files') or []:
        relative = Path(str(raw['path']))
        path = (run_root / relative).resolve()
        if run_root.resolve() not in path.parents:
            raise ValueError(f'Ruta fuera de la ejecución: {relative}.')
        item = SourceFile(
            slot=str(raw['slot']),
            name=str(raw['name']),
            path=path,
            size=int(raw['size']),
            sha256=str(raw['sha256']),
            origin=str(raw.get('origin') or ''),
            source_path=str(raw.get('source_path') or ''),
        )
        files[item.slot] = item
    return SourceSnapshot(
        run_id=str(payload['run_id']),
        mode=mode,
        root=run_root,
        fingerprint=str(payload['fingerprint']),
        created_at=float(payload['created_at']),
        files=files,
    )
