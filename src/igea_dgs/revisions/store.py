"""Almacén append-only con control optimista de concurrencia."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from .apply import apply_operation
from .models import ChangeOperation, RevisionSnapshot


class RevisionNotFoundError(LookupError):
    pass


class RevisionConflictError(RuntimeError):
    pass


class RevisionStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.directory = self.root / ".igea" / "revisions"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.root / ".igea" / "custody.sqlite3"
        self._lock = threading.RLock()
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS revisions (
                    id TEXT PRIMARY KEY, version INTEGER NOT NULL, initial_state TEXT NOT NULL
                )"""
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _row(self, revision_id: str) -> sqlite3.Row:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, version, initial_state FROM revisions WHERE id = ?", (revision_id,)
            ).fetchone()
        if row is None:
            raise RevisionNotFoundError(revision_id)
        return row

    def _log_path(self, revision_id: str) -> Path:
        return self.directory / f"{revision_id}.jsonl"

    def create(self, initial_state: dict[str, Any]) -> RevisionSnapshot:
        revision_id = str(uuid.uuid4())
        serialized = json.dumps(initial_state, ensure_ascii=False, sort_keys=True)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO revisions(id, version, initial_state) VALUES (?, 0, ?)",
                (revision_id, serialized),
            )
        return RevisionSnapshot(revision_id, 0, json.loads(serialized))

    def read_log(self, revision_id: str) -> list[ChangeOperation]:
        self._row(revision_id)
        path = self._log_path(revision_id)
        if not path.exists():
            return []
        return [
            ChangeOperation.from_dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def snapshot(self, revision_id: str) -> RevisionSnapshot:
        row = self._row(revision_id)
        state = json.loads(row["initial_state"])
        for operation in self.read_log(revision_id):
            state = apply_operation(state, operation)
        return RevisionSnapshot(revision_id, row["version"], state)

    def append(
        self, revision_id: str, expected_version: int, operation: ChangeOperation
    ) -> ChangeOperation:
        with self._lock:
            snapshot = self.snapshot(revision_id)
            if snapshot.version != expected_version:
                raise RevisionConflictError(
                    f"expected {expected_version}, current {snapshot.version}"
                )
            apply_operation(snapshot.state, operation)
            committed = operation.committed(expected_version + 1)
            encoded = json.dumps(committed.to_dict(), ensure_ascii=False, sort_keys=True)
            with self._log_path(revision_id).open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            with self._connect() as connection:
                cursor = connection.execute(
                    "UPDATE revisions SET version = ? WHERE id = ? AND version = ?",
                    (expected_version + 1, revision_id, expected_version),
                )
                if cursor.rowcount != 1:  # pragma: no cover - defensa ante otro proceso
                    raise RevisionConflictError("concurrent writer")
            return committed

    def undo(
        self, revision_id: str, operation_id: str, *, expected_version: int
    ) -> ChangeOperation:
        original = next(
            (item for item in self.read_log(revision_id) if item.operation_id == operation_id),
            None,
        )
        if original is None:
            raise ValueError("OPERATION_NOT_FOUND")
        inverse = replace(original.inverse(), inverse_of=operation_id)
        return self.append(revision_id, expected_version, inverse)
