from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from .dataset import CymdistDataset
from .dgs import write_dgs
from .export_tables import write_dgs_tsv, write_dgs_xlsx
from .geography import (
    build_geography,
    validate_geography,
    write_geography_manifest,
    write_geography_validation,
)
from .model import ModelBuildError, build_feeder_model
from .naming import feeder_short_name, sort_key_feeder
from .preview import write_preview_geojson, write_preview_html
from .validate import validate_dgs, write_validation_reports

ProgressCallback = Callable[[str, int, int], None]


def load_aliases(path: Path | str | None) -> dict[str, str]:
    if path is None:
        return {}
    alias_path = Path(path)
    if not alias_path.is_file():
        raise FileNotFoundError(f'Alias file not found: {alias_path}')
    data = json.loads(alias_path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError('Alias file must be a JSON object of string -> string mappings')
    return {
        k.strip(): v.strip()
        for k, v in data.items()
        if k.strip() and v.strip() and not k.strip().startswith('_')
    }


def _selection(dataset: CymdistDataset, selectors: Sequence[str] | None, all_feeders: bool) -> list[str]:
    if all_feeders:
        networks = sorted(dataset.feeder_ids(), key=sort_key_feeder)
    elif not selectors:
        raise ValueError('At least one feeder selector is required unless all_feeders=True')
    else:
        networks = []
        seen: set[str] = set()
        for selector in selectors:
            network = dataset.resolve_feeder(selector)
            if network not in seen:
                seen.add(network)
                networks.append(network)

    short_names = [feeder_short_name(n) for n in networks]
    duplicates = sorted({name for name in short_names if short_names.count(name) > 1})
    if duplicates:
        raise ValueError(
            'Nombres cortos de alimentador duplicados en la selección '
            f'(colisión de salida .dgs): {", ".join(duplicates)}'
        )
    return networks


def convert_selection(
    dataset: CymdistDataset,
    selectors: Sequence[str] | None,
    out_dir: Path | str,
    *,
    all_feeders: bool = False,
    aliases: Mapping[str, str] | None = None,
    strict: bool = True,
    schema_profile: str = 'pf21_dgs_1_8_4',
    include_geography: bool = True,
    source_crs: str = 'EPSG:32718',
    target_crs: str = 'EPSG:4326',
    export_xlsx: bool = False,
    export_tsv: bool = False,
    write_preview: bool = False,
    preview_backend: str = 'auto',
    on_progress: ProgressCallback | None = None,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    aliases = dict(aliases or {})
    if write_preview and not include_geography:
        raise ValueError('write_preview=True requiere include_geography=True')
    networks = _selection(dataset, selectors, all_feeders)

    items: list[dict] = []
    total = len(networks)

    for index, network_id in enumerate(networks, start=1):
        if on_progress is not None:
            on_progress(network_id, index, total)
        feeder = feeder_short_name(network_id)
        dgs_path = out_dir / f'{feeder}.dgs'
        json_path = out_dir / f'{feeder}_validation.json'
        txt_path = out_dir / f'{feeder}_validation.txt'
        geo_path = out_dir / f'{feeder}_geography.json'
        geo_validation_path = out_dir / f'{feeder}_geography_validation.txt'
        xlsx_path = out_dir / f'{feeder}.xlsx'
        tsv_dir = out_dir / f'{feeder}_dgs_tables'
        preview_html_path = out_dir / f'{feeder}_preview.html'
        preview_geojson_path = out_dir / f'{feeder}_preview.geojson'
        written: list[Path] = []
        # Stub FEEDER=/SOURCE blocks with zero SECTION rows cannot become a full DGS.
        # Mark as skipped (not failed) so convert-all keeps converting real feeders.
        if not dataset.feeders.get(network_id):
            items.append({
                'feeder': feeder,
                'network_id': network_id,
                'status': 'skipped',
                'error': (
                    f'{feeder}: sin filas SECTION en RED (cabecera FEEDER=/SOURCE vacía). '
                    'No hay tramos/cargas/SED en el export; se omite para no generar un DGS vacío.'
                ),
                'aliases': {},
                'unresolved_line_types': [],
            })
            continue
        try:
            model = build_feeder_model(dataset, network_id, aliases=aliases, strict=strict)
            geography = None
            geography_report = None
            if include_geography:
                geography = build_geography(dataset, model, source_crs=source_crs, target_crs=target_crs)
                geography_report = validate_geography(model, geography)
                if geography_report['errors_total']:
                    raise ModelBuildError(f'{network_id}: geographic validation failed: {geography_report["errors"]}')
                write_geography_manifest(geography, geo_path, model=model)
                written.append(geo_path)
                write_geography_validation(geography_report, geo_validation_path)
                written.append(geo_validation_path)

            if write_preview:
                assert geography is not None
                write_preview_html(
                    model, geography, preview_html_path, backend=preview_backend,
                )
                written.append(preview_html_path)
                write_preview_geojson(model, geography, preview_geojson_path)
                written.append(preview_geojson_path)

            write_dgs(model, dgs_path, schema_profile=schema_profile, geography=geography)
            written.append(dgs_path)

            if export_xlsx:
                write_dgs_xlsx(dgs_path, xlsx_path)
                written.append(xlsx_path)
            if export_tsv:
                write_dgs_tsv(dgs_path, tsv_dir)
                written.append(tsv_dir)

            report = validate_dgs(model, dgs_path, schema_profile=schema_profile, geography=geography)
            write_validation_reports(report, json_path, txt_path)
            written.extend([json_path, txt_path])
            ok = report['errors_total'] == 0
            item = {
                'feeder': feeder,
                'network_id': network_id,
                'status': 'ok' if ok else 'failed',
                'dgs': str(dgs_path),
                'validation_json': str(json_path),
                'validation_txt': str(txt_path),
                'errors_total': report['errors_total'],
                'aliases': dict(model.line_type_aliases),
                'unresolved_line_types': sorted(model.unresolved_line_types),
                'counts': report['counts'],
                'source_crs': source_crs if include_geography else None,
                'target_crs': target_crs if include_geography else None,
            }
            if include_geography:
                item['geography'] = str(geo_path)
                item['geography_validation'] = str(geo_validation_path)
                item['geography_coverage'] = {
                    'nodes_pct': geography_report['node_coverage_pct'],
                    'lines_pct': geography_report['line_coverage_pct'],
                    'intermediate_points': geography_report['intermediate_points'],
                }
            if write_preview:
                item['preview_html'] = str(preview_html_path)
                item['preview_geojson'] = str(preview_geojson_path)
            if export_xlsx:
                item['xlsx'] = str(xlsx_path)
            if export_tsv:
                item['tsv_dir'] = str(tsv_dir)
            if not ok:
                item['error'] = '; '.join(
                    report['schema_errors'] + report['structural_errors'] + report['connection_errors'] +
                    report.get('geographic_errors', []) + report.get('graphic_errors', [])
                )
        except (ModelBuildError, KeyError, ValueError, OSError, ImportError) as exc:
            # Only remove artifacts created in this attempt — never wipe a prior successful export.
            for path in written:
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                    elif path.exists():
                        path.unlink()
                except OSError:
                    pass
            item = {
                'feeder': feeder,
                'network_id': network_id,
                'status': 'failed',
                'error': str(exc),
                'aliases': {},
                'unresolved_line_types': sorted(getattr(exc, 'types', [])),
            }
        items.append(item)

    ok_count = sum(item['status'] == 'ok' for item in items)
    skipped_count = sum(item['status'] == 'skipped' for item in items)
    failed_count = sum(item['status'] == 'failed' for item in items)
    manifest = {
        'schema_profile': schema_profile,
        'strict': strict,
        'include_geography': include_geography,
        'export_xlsx': export_xlsx,
        'export_tsv': export_tsv,
        'write_preview': write_preview,
        'source_crs': source_crs if include_geography else None,
        'target_crs': target_crs if include_geography else None,
        'runtime_reference_dependency': False,
        'summary': {
            'requested': len(items),
            'ok': ok_count,
            'skipped': skipped_count,
            'failed': failed_count,
        },
        'feeders': items,
    }
    (out_dir / 'batch_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return manifest
