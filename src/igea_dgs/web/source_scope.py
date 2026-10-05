"""Inventario universal de empresa y periodo para paquetes VNR-GIS."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .source_runs import SourceSnapshot


@dataclass(frozen=True)
class SourceScope:
    companies: tuple[str, ...]
    periods: tuple[str, ...]
    selected_company: str | None
    selected_period: str | None
    ambiguous: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            'companies': list(self.companies),
            'periods': list(self.periods),
            'selected_company': self.selected_company,
            'selected_period': self.selected_period,
            'ambiguous': self.ambiguous,
        }


def _section_rows(root: Path) -> Iterable[dict[str, Any]]:
    from vnr_etl.connectors import resolve_adapter
    from vnr_etl.connectors.registry import iter_supported_sources
    from vnr_etl.discovery.schema import resolve_alias
    from vnr_etl.pipeline import _geojson_rows, normalize_feature_record

    for path in iter_supported_sources(root):
        if path.suffix.lower() in ('.geojson', '.json'):
            rows, _crs = _geojson_rows(path)
            normalized = [normalize_feature_record(row) for row in rows]
            fields = sorted({str(key) for row in normalized for key in row})
            section, _ = resolve_alias('section_id', fields)
            feeder, _ = resolve_alias('feeder_id', fields)
            if section and feeder:
                yield from normalized
            continue
        adapter = resolve_adapter(str(path))
        try:
            for layer in adapter.list_layers():
                rows = [normalize_feature_record(row) for row in adapter.read_layer(layer.name)]
                fields = sorted({str(key) for row in rows for key in row})
                section, _ = resolve_alias('section_id', fields)
                feeder, _ = resolve_alias('feeder_id', fields)
                if section and feeder:
                    yield from rows
        finally:
            adapter.close()


def _inspect_extracted(
    root: Path,
    *,
    selected_company: str | None = None,
    selected_period: str | None = None,
) -> SourceScope:
    from vnr_etl.discovery.schema import resolve_alias
    from vnr_etl.pipeline import _period_key

    rows = list(_section_rows(root))
    if not rows:
        raise ValueError('El paquete no contiene una capa de tramos identificable.')
    fields = sorted({str(key) for row in rows for key in row})
    company_field, _ = resolve_alias('company', fields)
    period_field, _ = resolve_alias('period', fields)
    companies = tuple(sorted({
        str(row.get(company_field)).strip() for row in rows
        if company_field and row.get(company_field) not in (None, '')
    }))
    company = (selected_company or '').strip() or (companies[0] if len(companies) == 1 else None)
    if company is not None and companies and company not in companies:
        raise ValueError(f'Empresa no encontrada en la fuente: {company}')
    scoped = [
        row for row in rows
        if not company_field or company is None or str(row.get(company_field, '')).strip() == company
    ]
    periods = tuple(sorted({
        str(row.get(period_field)).strip() for row in scoped
        if period_field and row.get(period_field) not in (None, '')
    }, key=_period_key))
    period = (selected_period or '').strip() or (periods[0] if len(periods) == 1 else None)
    if period is not None and periods and period not in periods:
        raise ValueError(f'Periodo no encontrado para {company or "la fuente"}: {period}')
    ambiguous = (len(companies) > 1 and company is None) or (len(periods) > 1 and period is None)
    return SourceScope(companies, periods, company, period, ambiguous)


def inspect_package_scope(
    package: Path | str,
    *,
    selected_company: str | None = None,
    selected_period: str | None = None,
) -> SourceScope:
    from vnr_etl.pipeline import safe_extract_package

    with tempfile.TemporaryDirectory(prefix='igea-vnr-scope-') as temporary:
        extracted = safe_extract_package(Path(package), Path(temporary) / 'package')
        return _inspect_extracted(
            extracted.destination,
            selected_company=selected_company,
            selected_period=selected_period,
        )


def inspect_source_scope(
    snapshot: SourceSnapshot,
    *,
    selected_company: str | None = None,
    selected_period: str | None = None,
) -> SourceScope:
    if snapshot.mode != 'vnr' or 'vnr_package' not in snapshot.files:
        raise ValueError('La ejecución no contiene un paquete VNR-GIS.')
    return inspect_package_scope(
        snapshot.files['vnr_package'].path,
        selected_company=selected_company,
        selected_period=selected_period,
    )
