"""Parser independiente para pruebas de ida y vuelta DGS."""

from pathlib import Path
from typing import Any


def parse_dgs(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("$$"):
            parts = raw[2:].split(";")
            name = parts[0]
            fields = [item.split("(", 1)[0].replace(":MATRIX", "") for item in parts[1:]]
            current = {"fields": fields, "rows": [], "rows_dict": []}
            result[name] = current
        elif raw.startswith("  ") and current is not None:
            values = raw[2:].split(";")
            current["rows"].append(values)
            current["rows_dict"].append(dict(zip(current["fields"], values, strict=True)))
    return result
