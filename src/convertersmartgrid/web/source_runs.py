"""Custodia inmutable de los archivos que forman una ejecución web.

Una instantánea se crea antes de leer la fuente. Los lectores posteriores reciben
únicamente las rutas custodiadas, de modo que un cambio en una ruta del servidor o
la presencia de casillas de otra modalidad no puede alterar la conversión activa.
"""

from __future__ import annotations

from ..runtime_paths import staging_publicacion
from ..util import publicar_duradero

import hashlib
import json
import math
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..sources.snapshot import (  # noqa: F401 - SourceFile/SourceSnapshot: API pública
    COMMON_SLOTS, MODE_SLOTS, SourceFile, SourceMode, SourceSnapshot,
    fingerprint as source_fingerprint,
)


class EspacioDeFuentes(Protocol):
    """Lo que la custodia usa del espacio de trabajo; ``Workspace`` lo cumple (002:RF-4)."""

    active_run_id: str | None
    inputs: Any
    lock: Any
    options: Any
    root: Path

    def save(self) -> None:
        ...


_RUN_ID_RE = re.compile(r'^\d{8}T\d{6}-[a-f0-9]{12}$')


def valid_run_id(run_id: str) -> bool:
    """Solo acepta el identificador generado, nunca componentes de ruta."""
    return isinstance(run_id, str) and bool(_RUN_ID_RE.fullmatch(run_id))


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


def _sha256_copy(source: Path, target: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with staging_publicacion(target) as temporary:
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
    publicar_duradero(path, json.dumps(payload, indent=2, ensure_ascii=False))


def create_source_run(ws: EspacioDeFuentes) -> SourceSnapshot:
    """Copia solo las entradas del modo activo y activa la instantánea resultante."""
    raw_mode = str(ws.options.get('input_mode') or '')
    if not raw_mode:
        # 059:RF-7: sin fuente no hay nada que convertir; se pide, no se supone una.
        raise ValueError('Cargue primero la fuente: los tres TXT de CYMDIST, una base Access '
                         '(.mdb) o un paquete VNR-GIS.')
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
        fingerprint = source_fingerprint(mode, copied)
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


def load_source_run(ws: EspacioDeFuentes, run_id: str, *, verify_files: bool = False) -> SourceSnapshot:
    """Relee la identidad; el trabajo de preparación verifica además todos los bytes.

    Las consultas HTTP solo leen el manifiesto: una base de varios GB se verifica en
    el trabajo en cola, nunca bloqueando la petición ni renovando su hash de referencia.
    """
    if not valid_run_id(run_id):
        raise ValueError(f'Identificador de ejecución inválido: {run_id!r}.')
    run_root = ws.root / 'runs' / run_id
    manifest_path = run_root / 'source_manifest.json'
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (not isinstance(payload, dict) or type(payload.get('version')) is not int
            or payload['version'] != 1 or payload.get('run_id') != run_id):
        raise ValueError('Manifiesto de otra ejecución o versión no admitida.')
    mode = payload.get('mode')
    if not isinstance(mode, str) or mode not in MODE_SLOTS:
        raise ValueError(f'Manifiesto con modo desconocido: {mode!r}.')
    created_at = payload.get('created_at')
    if (type(created_at) not in (int, float) or not math.isfinite(created_at)
            or created_at < 0):
        raise ValueError('Fecha de ejecución inválida en el manifiesto.')
    files: dict[str, SourceFile] = {}
    rows = payload.get('files')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Manifiesto sin archivos custodiados.')
    allowed = {*MODE_SLOTS[mode], *COMMON_SLOTS}
    for raw in rows:
        if (not isinstance(raw, dict) or not isinstance(raw.get('slot'), str)
                or raw['slot'] not in allowed
                or raw['slot'] in files):
            raise ValueError('Entrada duplicada o de otra fuente en el manifiesto.')
        if (any(not isinstance(raw.get(key), str) or not raw[key] for key in ('path', 'name', 'sha256'))
                or any(not isinstance(raw.get(key, ''), str) for key in ('origin', 'source_path'))):
            raise ValueError('Tipos de metadatos custodiados inválidos.')
        if (type(raw.get('size')) is not int or raw['size'] < 0
                or not re.fullmatch(r'[0-9a-f]{64}', raw['sha256'])):
            raise ValueError(f'Metadatos custodiados inválidos: {raw["slot"]}.')
        relative = Path(raw['path'])
        if relative.anchor or '..' in relative.parts or relative.name != raw['name']:
            raise ValueError(f'Ruta no relativa a la ejecución: {relative}.')
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
    expected = source_fingerprint(mode, list(files.values()))
    if payload.get('fingerprint') != expected:
        raise ValueError('La huella del manifiesto no coincide con las entradas custodiadas.')
    snapshot = SourceSnapshot(
        run_id=str(payload['run_id']),
        mode=mode,
        root=run_root,
        fingerprint=str(payload['fingerprint']),
        created_at=float(created_at),
        files=files,
    )
    if verify_files:
        verify_source_files(snapshot)
    return snapshot


def verify_source_files(snapshot: SourceSnapshot) -> None:
    """034:RF-20: coteja bytes en preparación, conservando hashes e inventario previos."""
    from ..util import sha256_file

    for item in snapshot.files.values():
        if not item.path.is_file():
            raise ValueError(f'Original custodiado ausente: {item.slot}.')
        # Ni tamaño ni mtime prueban identidad: una alteración puede conservar ambos.
        if item.path.stat().st_size != item.size or sha256_file(item.path) != item.sha256:
            raise ValueError(f'Cambió la huella del original custodiado: {item.slot}.')
