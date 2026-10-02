"""Repositorio SQLite para identidad y evidencia de entradas."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .models import InputFile, InputManifest, InputSelection, Project


class ProjectNotFoundError(LookupError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ProjectStore:
    def __init__(self, database: Path):
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS input_manifests (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id),
                    output_dir TEXT NOT NULL, crs TEXT NOT NULL, registered_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS input_files (
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    kind TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL, PRIMARY KEY(project_id, kind)
                );
                """
            )

    def create(self, name: str) -> Project:
        project = Project(str(uuid.uuid4()), name.strip(), _now())
        if not project.name:
            raise ValueError("PROJECT_NAME_EMPTY")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO projects(id, name, created_at) VALUES (?, ?, ?)",
                (project.id, project.name, project.created_at),
            )
        return project

    def get(self, project_id: str) -> Project:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, created_at FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(project_id)
        return Project(row["id"], row["name"], row["created_at"])

    def register_inputs(self, project_id: str, selection: InputSelection) -> InputManifest:
        self.get(project_id)
        source_paths = {
            "red": selection.red_path.resolve(strict=True),
            "carga": selection.carga_path.resolve(strict=True),
            "equipment": selection.equipment_path.resolve(strict=True),
        }
        files = tuple(
            InputFile(kind, str(path), _sha256(path), path.stat().st_size)
            for kind, path in source_paths.items()
        )
        manifest = InputManifest(
            project_id,
            files,
            str(selection.output_dir.resolve(strict=False)),
            selection.crs,
            _now(),
        )
        with self._connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO input_manifests
                   (project_id, output_dir, crs, registered_at) VALUES (?, ?, ?, ?)""",
                (project_id, manifest.output_dir, manifest.crs, manifest.registered_at),
            )
            connection.executemany(
                """INSERT OR REPLACE INTO input_files
                   (project_id, kind, path, sha256, size_bytes) VALUES (?, ?, ?, ?, ?)""",
                ((project_id, f.kind, f.path, f.sha256, f.size_bytes) for f in files),
            )
        return manifest

    def get_manifest(self, project_id: str) -> InputManifest:
        self.get(project_id)
        with self._connect() as connection:
            row = connection.execute(
                """SELECT output_dir, crs, registered_at FROM input_manifests
                   WHERE project_id = ?""",
                (project_id,),
            ).fetchone()
            file_rows = connection.execute(
                """SELECT kind, path, sha256, size_bytes FROM input_files
                   WHERE project_id = ? ORDER BY kind""",
                (project_id,),
            ).fetchall()
        if row is None or len(file_rows) != 3:
            raise ValueError("INPUT_MANIFEST_NOT_FOUND")
        return InputManifest(
            project_id,
            tuple(
                InputFile(item["kind"], item["path"], item["sha256"], item["size_bytes"])
                for item in file_rows
            ),
            row["output_dir"],
            row["crs"],
            row["registered_at"],
        )
