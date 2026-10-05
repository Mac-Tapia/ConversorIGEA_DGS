"""Contrato común para lectores de las tres procedencias web."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..source_runs import SourceSnapshot


class SourceModeError(ValueError):
    """La instantánea no pertenece íntegramente al adaptador elegido."""


@dataclass
class SourceLoadResult:
    dataset: Any
    catalog_report: dict | None = None
    readiness: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)


class SourceAdapter(Protocol):
    mode: str

    def load(self, snapshot: SourceSnapshot, *, aliases: dict[str, str]) -> SourceLoadResult:
        ...


def validate_snapshot(
    snapshot: SourceSnapshot,
    *,
    mode: str,
    allowed: set[str],
    required: set[str],
) -> None:
    if snapshot.mode != mode:
        raise SourceModeError(
            f'La ejecución {snapshot.run_id} es {snapshot.mode}, no {mode}.'
        )
    foreign = sorted(set(snapshot.files) - allowed - {'aliases'})
    if foreign:
        raise SourceModeError(
            f'La entrada {", ".join(foreign)} no pertenece al modo {mode}.'
        )
    missing = sorted(required - set(snapshot.files))
    if missing:
        raise SourceModeError(
            f'La ejecución {snapshot.run_id} no contiene: {", ".join(missing)}.'
        )


def provenance(snapshot: SourceSnapshot) -> dict[str, Any]:
    return {
        'source_run_id': snapshot.run_id,
        'source_mode': snapshot.mode,
        'source_fingerprint': snapshot.fingerprint,
        'source_files': {
            slot: {'name': item.name, 'size': item.size, 'sha256': item.sha256}
            for slot, item in sorted(snapshot.files.items())
        },
    }
