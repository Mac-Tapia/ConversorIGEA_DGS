#!/usr/bin/env python3
"""Verifica los artefactos NA203–NA205 antes de abrir PowerFactory."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import statistics
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from igea_dgs.feeder_metadata import read_feeder_metadata
from igea_dgs.validate import parse_dgs


DEFAULT_FEEDERS = ('NA203', 'NA205')
DEFAULT_TRAFOMIX = 92
EXPECTED_SCALE = 2.08


def _read_json(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'No se pudo leer {source}: {exc}') from exc
    if not isinstance(payload, dict):
        raise ValueError(f'{source} no contiene un objeto JSON')
    return payload


def _rows(tables: dict[str, Any], class_name: str) -> list[dict[str, str]]:
    return list((tables.get(class_name) or {}).get('rows_dict') or [])


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(value)))


def _diagram_metrics(tables: dict[str, Any]) -> dict[str, Any]:
    terms = {row.get('FID', ''): row for row in _rows(tables, 'ElmTerm')}
    points: list[tuple[float, float, float, float]] = []
    all_xy: list[tuple[float, float]] = []
    for row in _rows(tables, 'IntGrf'):
        x, y = _number(row.get('rCenterX')), _number(row.get('rCenterY'))
        if x is not None and y is not None:
            all_xy.append((x, y))
        if row.get('sSymNam') != 'PointTerm' or x is None or y is None:
            continue
        term = terms.get(row.get('pDataObj', ''))
        if not term:
            continue
        lat, lon = _number(term.get('GPSlat')), _number(term.get('GPSlon'))
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            points.append((x, y, lat, lon))

    selected = points
    if len(points) > 12:
        selected = list({
            min(points, key=lambda p: p[0]), max(points, key=lambda p: p[0]),
            min(points, key=lambda p: p[1]), max(points, key=lambda p: p[1]),
            min(points, key=lambda p: p[2]), max(points, key=lambda p: p[2]),
            min(points, key=lambda p: p[3]), max(points, key=lambda p: p[3]),
        })
    ratios: list[float] = []
    for index, first in enumerate(selected):
        for second in selected[index + 1:]:
            metres = _haversine_m((first[2], first[3]), (second[2], second[3]))
            units = math.hypot(first[0] - second[0], first[1] - second[1])
            if metres > 1.0 and units > 0:
                ratios.append(units / metres)
    scale = statistics.median(ratios) if ratios else None
    xs = [point[0] for point in all_xy]
    ys = [point[1] for point in all_xy]
    return {
        'scale_units_per_m': scale,
        'scale_samples': len(ratios),
        'width': max(xs) - min(xs) if xs else 0.0,
        'height': max(ys) - min(ys) if ys else 0.0,
        'pointterm_gps_pairs': len(points),
    }


def verify_artifacts(
    *,
    dgs: Path | str,
    manifest: Path | str,
    feeder_metadata: Path | str,
    validation: Path | str,
    expected_feeders: tuple[str, ...] = DEFAULT_FEEDERS,
    expected_trafomix: int = DEFAULT_TRAFOMIX,
) -> dict[str, Any]:
    """Devuelve un diagnóstico fail-closed de los cuatro artefactos."""

    errors: list[str] = []
    checks: dict[str, Any] = {}
    paths = {
        'dgs': str(Path(dgs).resolve()),
        'manifest': str(Path(manifest).resolve()),
        'feeder_metadata': str(Path(feeder_metadata).resolve()),
        'validation': str(Path(validation).resolve()),
    }
    try:
        group = _read_json(manifest)
        validation_data = _read_json(validation)
        tables = parse_dgs(dgs)
        metadata = read_feeder_metadata(feeder_metadata, expected_dgs=dgs)
    except Exception as exc:
        return {'ok': False, 'paths': paths, 'checks': checks, 'errors': [str(exc)]}

    actual_feeders = tuple(group.get('feeders') or ())
    checks['feeders'] = list(actual_feeders)
    if actual_feeders != tuple(expected_feeders):
        errors.append(
            f'Alimentadores incorrectos: esperado={list(expected_feeders)}, actual={list(actual_feeders)}'
        )

    rules = group.get('reglas_por_alimentador') or {}
    trafomix = sum(int(((item.get('trafomix') or {}).get('excluidos') or 0)) for item in rules.values())
    substation_names = [row.get('loc_name', '') for row in _rows(tables, 'ElmSubstat')]
    m_present = sum(bool(re.fullmatch(r'M\d+(?:-\d+)?', name, re.IGNORECASE)) for name in substation_names)
    checks['trafomix'] = {'excluded': trafomix, 'expected': expected_trafomix, 'm_present': m_present}
    if trafomix != expected_trafomix:
        errors.append(f'Trafomix excluidos: esperado={expected_trafomix}, actual={trafomix}')
    if m_present:
        errors.append(f'Persisten {m_present} Trafomix M… como ElmSubstat')

    dgs_counts = {name: len(_rows(tables, name)) for name in ('ElmLod', 'ElmSym', 'ElmXnet')}
    assignment_counts = Counter(record.class_name for record in metadata.assignments)
    assignment_feeders = sorted({record.feeder for record in metadata.assignments})
    metadata_checks = {
        name: {
            'dgs_rows': dgs_counts[name],
            'assignments': assignment_counts[name],
            'matches_dgs': dgs_counts[name] == assignment_counts[name],
        }
        for name in dgs_counts
    }
    metadata_checks['feeders'] = assignment_feeders
    checks['metadata'] = metadata_checks
    for class_name in dgs_counts:
        if dgs_counts[class_name] != assignment_counts[class_name]:
            errors.append(
                f'{class_name}: filas DGS={dgs_counts[class_name]} != asignaciones={assignment_counts[class_name]}'
            )
    if dgs_counts['ElmXnet'] != len(expected_feeders):
        errors.append(f'ElmXnet: se esperaban {len(expected_feeders)} fuentes, hay {dgs_counts["ElmXnet"]}')
    if set(assignment_feeders) != set(expected_feeders):
        errors.append(
            f'Pertenencia incompleta: esperado={sorted(expected_feeders)}, actual={assignment_feeders}'
        )

    substation_fids = {row.get('FID', '') for row in _rows(tables, 'ElmSubstat')}
    child_counts = {
        class_name: Counter(row.get('fold_id', '') for row in _rows(tables, class_name))
        for class_name in ('ElmTr2', 'ElmCoup', 'ElmTerm')
    }
    incomplete = [
        fid for fid in sorted(substation_fids)
        if child_counts['ElmTr2'][fid] != 1
        or child_counts['ElmCoup'][fid] != 1
        or child_counts['ElmTerm'][fid] < 2
    ]
    checks['sed_internal_topology'] = {
        'seds': len(substation_fids), 'complete': not incomplete, 'incomplete_fids': incomplete,
    }
    if incomplete:
        errors.append(f'Topología SED interna incompleta en {len(incomplete)} subestaciones')

    completeness = group.get('completitud') or {}
    completeness_errors = list(completeness.get('fallos') or [])
    entry_switches = int((completeness.get('entrada') or {}).get('maniobras') or 0)
    dgs_switches = len(_rows(tables, 'StaSwitch'))
    bridge_switches = sum(
        int(((item.get('puentes') or {}).get('interruptores') or 0)) for item in rules.values()
    )
    ties = int(group.get('ties') or 0)
    dgs_couplers = len(_rows(tables, 'ElmCoup'))
    expected_couplers = len(substation_fids) + bridge_switches + ties
    switch_ok = (
        not completeness_errors
        and entry_switches == dgs_switches + bridge_switches
        and dgs_couplers == expected_couplers
    )
    checks['switch_reconciliation'] = {
        'ok': switch_ok,
        'source_maneuvers': entry_switches,
        'StaSwitch': dgs_switches,
        'bridge_couplers': bridge_switches,
        'tie_couplers': ties,
        'sed_internal_couplers': len(substation_fids),
        'ElmCoup': dgs_couplers,
        'completeness_errors': completeness_errors,
    }
    if completeness_errors:
        errors.extend(f'Completitud de maniobras/cargas: {item}' for item in completeness_errors)
    if entry_switches != dgs_switches + bridge_switches:
        errors.append('Reconciliación de maniobras falló entre fuente, StaSwitch y puentes')
    if dgs_couplers != expected_couplers:
        errors.append('Reconciliación ElmCoup falló para SED, puentes y enlaces')

    diagram = _diagram_metrics(tables)
    diagram['adaptive'] = group.get('hoja') is None
    diagram['expected_scale_units_per_m'] = EXPECTED_SCALE
    checks['diagram'] = diagram
    if not diagram['adaptive']:
        errors.append('El diagrama no es adaptativo: el manifiesto declara una hoja fija')
    scale = diagram['scale_units_per_m']
    if scale is None or not math.isclose(scale, EXPECTED_SCALE, rel_tol=0.05):
        errors.append(f'Escala de diagrama distinta de {EXPECTED_SCALE} u/m: {scale!r}')
    if max(diagram['width'], diagram['height']) <= 0:
        errors.append('La extensión del diagrama colapsó; ancho/alto no provienen de la geometría')

    validation_errors = int(validation_data.get('errors_total') or 0)
    checks['validation_errors_total'] = validation_errors
    if validation_errors:
        errors.append(f'La validación DGS reporta {validation_errors} error(es)')
    if group.get('status') != 'ok':
        errors.append(f'El manifiesto de grupo no está OK: {group.get("status")!r}')

    return {'ok': not errors, 'paths': paths, 'checks': checks, 'errors': errors}


def verify_and_write(
    *,
    output_json: Path | str,
    output_txt: Path | str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Verifica y siempre publica diagnósticos JSON/TXT."""

    try:
        report = verify_artifacts(**kwargs)
    except Exception as exc:  # Última barrera para que nunca falte el diagnóstico.
        report = {'ok': False, 'paths': {}, 'checks': {}, 'errors': [str(exc)]}
    json_path, txt_path = Path(output_json), Path(output_txt)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    lines = [
        f'NA203-NA205 ARTIFACT ACCEPTANCE: {"PASS" if report["ok"] else "FAIL"}',
        '=' * 72,
        json.dumps(report.get('checks') or {}, indent=2, ensure_ascii=False),
        '',
        f'ERRORS: {len(report.get("errors") or [])}',
    ]
    lines.extend(f'  - {error}' for error in report.get('errors') or [])
    txt_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dgs', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--feeder-metadata', required=True)
    parser.add_argument('--validation', required=True)
    parser.add_argument('--output-json', required=True)
    parser.add_argument('--output-txt', required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = verify_and_write(
        dgs=args.dgs,
        manifest=args.manifest,
        feeder_metadata=args.feeder_metadata,
        validation=args.validation,
        output_json=args.output_json,
        output_txt=args.output_txt,
    )
    print(f'Artifact acceptance: {"PASS" if report["ok"] else "FAIL"}')
    for error in report.get('errors') or []:
        print(f'  - {error}')
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
