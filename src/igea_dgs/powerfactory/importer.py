from pathlib import Path

from .port import DgsImportPort


class DgsImportError(RuntimeError):
    pass


def import_dgs(port: DgsImportPort, path: Path) -> None:
    if not path.is_file():
        raise DgsImportError(f"DGS does not exist: {path}")
    rc = port.import_dgs(path)
    if rc != 0:
        raise DgsImportError(f"PowerFactory DGS import failed with code {rc}")
