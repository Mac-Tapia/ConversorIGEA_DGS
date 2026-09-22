"""Publicación de artefactos validados con reemplazo atómico."""

import os
import shutil
from pathlib import Path


class AtomicRunPublisher:
    def __init__(self, root: Path, run_id: str, feeder: str) -> None:
        self.root = root
        self.run_id = run_id
        self.feeder = feeder
        self.staging = root / ".runs" / run_id / feeder
        self._committed = False

    def __enter__(self) -> "AtomicRunPublisher":
        self.staging.mkdir(parents=True, exist_ok=False)
        return self

    def stage_text(self, name: str, content: str) -> Path:
        target = self.staging / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        return target

    def commit(self) -> None:
        previous = self.root / "releases" / self.feeder / "previous"
        previous.mkdir(parents=True, exist_ok=True)
        staged_files = sorted(path for path in self.staging.rglob("*") if path.is_file())
        for staged in staged_files:
            relative = staged.relative_to(self.staging)
            final = self.root / relative
            if final.exists():
                backup = previous / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(final, backup)
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, final)
        self._committed = True

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.staging.exists():
            shutil.rmtree(self.staging)
        run_root = self.root / ".runs" / self.run_id
        if run_root.exists() and not any(run_root.iterdir()):
            run_root.rmdir()
