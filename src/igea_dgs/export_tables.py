"""Exportación tabular DGS (Excel multi-hoja / TSV) a partir del .dgs escrito.

Usa el mismo parseo que la validación (``parse_dgs``) para garantizar que las
pestañas coincidan con lo que PowerFactory importa desde el archivo nativo.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Mapping, Sequence

from .validate import parse_dgs


class ExportError(ValueError):
    pass


def load_dgs_table_rows(dgs_path: Path | str) -> dict[str, list[dict[str, str]]]:
    """Devuelve ``{table_name: [row_dict, ...]}`` desde un .dgs."""
    tables = parse_dgs(dgs_path)
    return {name: list(table['rows_dict']) for name, table in tables.items()}


def _ordered_fields(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if not rows:
        return []
    # Preserve first-row key order; append any late keys stably.
    fields = list(rows[0].keys())
    seen = set(fields)
    for row in rows[1:]:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    return fields


def write_dgs_tsv(
    dgs_path: Path | str,
    out_dir: Path | str,
    *,
    tables: Sequence[str] | None = None,
) -> Path:
    """Escribe un TSV por tabla DGS en ``out_dir`` (sin dependencias opcionales)."""
    rows_by_table = load_dgs_table_rows(dgs_path)
    if not rows_by_table:
        raise ExportError(f'No hay tablas DGS en {dgs_path}')

    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    selected = list(tables) if tables is not None else list(rows_by_table.keys())

    written = 0
    for name in selected:
        rows = rows_by_table.get(name)
        if rows is None:
            continue
        fields = _ordered_fields(rows)
        path = dest / f'{name}.tsv'
        with path.open('w', encoding='utf-8', newline='') as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=fields,
                delimiter='\t',
                lineterminator='\n',
                extrasaction='ignore',
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, '') for k in fields})
        written += 1

    if written == 0:
        raise ExportError(f'Ninguna tabla seleccionada encontrada en {dgs_path}')
    return dest


def write_dgs_xlsx(
    dgs_path: Path | str,
    xlsx_path: Path | str,
    *,
    tables: Sequence[str] | None = None,
) -> Path:
    """Excel multi-hoja (una pestaña por tabla DGS). Requiere pandas + openpyxl."""
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - optional extra
        raise ImportError(
            'pandas y openpyxl son obligatorios para exportar Excel. '
            'Instale con: pip install "igea-dgs[xlsx]"'
        ) from exc

    rows_by_table = load_dgs_table_rows(dgs_path)
    if not rows_by_table:
        raise ExportError(f'No hay tablas DGS en {dgs_path}')

    out = Path(xlsx_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    selected = list(tables) if tables is not None else list(rows_by_table.keys())

    written = 0
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        for name in selected:
            rows = rows_by_table.get(name)
            if rows is None:
                continue
            fields = _ordered_fields(rows)
            frame = pd.DataFrame([{k: row.get(k, '') for k in fields} for row in rows], columns=fields)
            # Excel sheet name limit 31 chars; DGS class names fit.
            sheet = name[:31]
            frame.to_excel(writer, sheet_name=sheet, index=False)
            written += 1

    if written == 0:
        raise ExportError(f'Ninguna tabla seleccionada encontrada en {dgs_path}')
    return out
