"""Parser estricto que nunca reemplaza bytes ni descarta columnas."""

import csv
from hashlib import sha256
from pathlib import Path

from igea_dgs.quality.diagnostics import Diagnostic, SourceLocation
from igea_dgs.quality.gates import GateResult

from .contracts import FileContract
from .records import ParsedFile, RawRecord


def _csv(line: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in next(csv.reader([line])))


def parse_igea_file(path: Path, contract: FileContract) -> ParsedFile:
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    diagnostics: list[Diagnostic] = []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        diagnostics.append(
            Diagnostic.blocking(
                "INVALID_ENCODING",
                "El archivo no es UTF-8 estricto",
                SourceLocation(str(path), row=exc.start),
            )
        )
        return ParsedFile(path, digest, (), (), GateResult("G1", diagnostics))

    section: str | None = None
    columns: tuple[str, ...] | None = None
    records: list[RawRecord] = []
    sections: list[str] = []
    seen: dict[tuple[str, tuple[str, ...]], int] = {}
    unknown_section = False

    for line_number, original in enumerate(text.splitlines(), 1):
        line = original.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().upper()
            columns = None
            unknown_section = contract.table(section) is None
            if section not in sections:
                sections.append(section)
            if unknown_section:
                diagnostics.append(
                    Diagnostic.blocking(
                        "UNKNOWN_SECTION",
                        f"Seccion no registrada: {section}",
                        SourceLocation(str(path), section, line_number),
                    )
                )
            continue
        if line.startswith("FORMAT_") and "=" in line:
            columns = _csv(line.split("=", 1)[1])
            if len(set(columns)) != len(columns):
                diagnostics.append(
                    Diagnostic.blocking(
                        "DUPLICATE_HEADER",
                        "El encabezado contiene columnas repetidas",
                        SourceLocation(str(path), section, line_number),
                    )
                )
            continue
        if line.startswith("FEEDER="):
            continue
        if section is None or columns is None or unknown_section:
            continue

        values = _csv(original)
        extras = values[len(columns) :]
        declared = values[: len(columns)] + ("",) * max(0, len(columns) - len(values))
        location = SourceLocation(str(path), section, line_number)
        if extras:
            diagnostics.append(
                Diagnostic.blocking(
                    "EXTRA_COLUMN", "Fila con columnas no declaradas", location
                )
            )
        record = RawRecord(section, columns, declared, extras, line_number, original)
        records.append(record)

        table = contract.table(section)
        assert table is not None
        row = record.as_dict()
        if table.key_fields:
            key = tuple(row.get(field, "") for field in table.key_fields)
            if any(not value for value in key):
                diagnostics.append(
                    Diagnostic.blocking("EMPTY_KEY", "Clave obligatoria vacia", location)
                )
            identity = (section, key)
            if identity in seen:
                diagnostics.append(
                    Diagnostic.blocking(
                        "DUPLICATE_KEY",
                        f"Clave duplicada; primera fila {seen[identity]}",
                        location,
                    )
                )
            else:
                seen[identity] = line_number

    return ParsedFile(
        path, digest, tuple(records), tuple(sections), GateResult("G1", diagnostics)
    )
