"""Escritor DGS puro y reproducible."""

from pathlib import Path

from igea_dgs.schema import load_schema

from .builder import DgsDocument


def write_dgs_document(document: DgsDocument, path: Path) -> Path:
    schema = load_schema()
    output = ["DGS-Version: 1.8.4", ""]
    for table in schema.table_order:
        rows = document.tables.get(table)
        if not rows:
            continue
        fields = schema.fields(table)
        output.append(schema.header(table))
        for row in rows:
            values = [str(row.get(field, "")).replace(";", ",").replace("\n", " ") for field in fields]
            output.append("  " + ";".join(values))
        output.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output), encoding="utf-8", newline="\n")
    return path
