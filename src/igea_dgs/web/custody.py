"""Huella inmutable de las entradas que pertenecen a un espacio web."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class InputFingerprint:
    size: int
    mtime_ns: int
    sha256: str

    def public(self) -> dict[str, int | str]:
        return asdict(self)


@dataclass(frozen=True)
class FingerprintVerification:
    matches: bool
    current: InputFingerprint | None
    reason: str


def fingerprint(path: Path) -> InputFingerprint:
    source = Path(path)
    stat = source.stat()
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return InputFingerprint(
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=digest.hexdigest(),
    )


def verify_fingerprint(
    path: Path,
    expected: Mapping[str, Any],
) -> FingerprintVerification:
    source = Path(path)
    if not source.is_file():
        return FingerprintVerification(False, None, 'El fichero ya no existe.')
    expected_hash = str(expected.get('sha256') or '')
    stat = source.stat()
    if (
        expected_hash
        and stat.st_size == int(expected.get('size') or -1)
        and stat.st_mtime_ns == int(expected.get('mtime_ns') or -1)
    ):
        return FingerprintVerification(True, InputFingerprint(
            size=stat.st_size, mtime_ns=stat.st_mtime_ns, sha256=expected_hash,
        ), '')
    if (
        expected.get('stale')
        and stat.st_size == int(expected.get('current_size') or -1)
        and stat.st_mtime_ns == int(expected.get('current_mtime_ns') or -1)
        and expected.get('current_sha256')
    ):
        return FingerprintVerification(False, InputFingerprint(
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            sha256=str(expected['current_sha256']),
        ), 'El contenido cambió después de asignarlo al espacio de trabajo.')
    current = fingerprint(source)
    if not expected_hash:
        return FingerprintVerification(True, current, 'Huella creada al migrar un espacio anterior.')
    if current.sha256 == expected_hash:
        return FingerprintVerification(True, current, 'El contenido no cambió; se actualizó su marca de tiempo.')
    return FingerprintVerification(
        False,
        current,
        'El contenido cambió después de asignarlo al espacio de trabajo.',
    )
