#!/usr/bin/env python3
"""Regenera y verifica alimentadores de referencia sin convertir ausencias en PASS."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from igea_dgs.batch import convert_selection  # noqa: E402
from igea_dgs.dataset import CymdistDataset  # noqa: E402
from igea_dgs.feeder_metadata import read_feeder_metadata, sha256_file  # noqa: E402
from igea_dgs.identify import CARGA, EQUIPOS, RED, identificar  # noqa: E402
from igea_dgs.naming import feeder_short_name  # noqa: E402
from igea_dgs.powerfactory_env import (  # noqa: E402
    pf_python_dir, pf_subprocess_env, python_for_pf,
)
from igea_dgs.validate import parse_dgs  # noqa: E402

PASS = 'PASS'
FAIL = 'FAIL'
SKIP_MISSING_INPUT = 'SKIP_MISSING_INPUT'
NOT_RUN_POWERFACTORY = 'NOT_RUN_POWERFACTORY'
DEFAULT_FEEDERS = ('NA203', 'NA205', 'PE104', 'CA101')
EXPECTED_SCALE = 2.08


def gate(status: str, detail: str, **evidence: Any) -> dict[str, Any]:
    return {'status': status, 'detail': detail, 'evidence': evidence}


def evaluate_evidence(feeder: str, evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Evalúa métricas ya extraídas; se mantiene pura para una regresión precisa."""

    validation_errors = int(evidence.get('validation_errors') or 0)
    completeness = list(evidence.get('completeness_failures') or [])
    conversion_ok = validation_errors == 0 and not completeness

    actual_feeders = set(evidence.get('mapping_feeders') or [])
    assigned = dict(evidence.get('assignment_counts') or {})
    dgs_counts = dict(evidence.get('dgs_counts') or {})
    mapping_ok = actual_feeders == {feeder} and all(
        int(assigned.get(name, 0)) == int(dgs_counts.get(name, 0))
        for name in ('ElmLod', 'ElmSym', 'ElmXnet')
    ) and int(dgs_counts.get('ElmXnet', 0)) == 1

    scale = evidence.get('scale_units_per_m')
    scale_ok = (
        bool(evidence.get('adaptive_grid'))
        and isinstance(scale, (int, float))
        and math.isclose(float(scale), EXPECTED_SCALE, rel_tol=0.05)
    )
    trafomix_ok = int(evidence.get('trafomix_present') or 0) == 0
    switches_ok = (
        int(evidence.get('source_switches') or 0)
        == int(evidence.get('dgs_switches') or 0)
        + int(evidence.get('bridge_switches') or 0)
        and not completeness
    )
    source_seds = int(evidence.get('source_seds') or 0)
    dgs_seds = int(evidence.get('dgs_seds') or 0)
    dgs_transformers = int(evidence.get('dgs_transformers') or 0)
    sed_ok = source_seds == dgs_seds == dgs_transformers

    return {
        'conversion': gate(PASS if conversion_ok else FAIL,
                           'Validación DGS y completitud sin errores.' if conversion_ok
                           else 'La validación DGS o la completitud reportó errores.',
                           validation_errors=validation_errors, failures=completeness),
        'mapping': gate(PASS if mapping_ok else FAIL,
                        'Name y Alimentador coinciden con la pertenencia real.' if mapping_ok
                        else 'La metadata Name→Alimentador es incompleta o inconsistente.',
                        feeders=sorted(actual_feeders), assignments=assigned,
                        dgs_counts=dgs_counts),
        'grid_scale': gate(PASS if scale_ok else FAIL,
                           'Grid adaptativa a escala geográfica de referencia.' if scale_ok
                           else 'La Grid usa hoja fija o la escala no coincide con la referencia.',
                           adaptive=bool(evidence.get('adaptive_grid')),
                           scale_units_per_m=scale, expected=EXPECTED_SCALE),
        'trafomix': gate(PASS if trafomix_ok else FAIL,
                         'No quedan Trafomix M… modelados como SED.' if trafomix_ok
                         else 'Persisten Trafomix M… como SED.',
                         excluded=int(evidence.get('trafomix_excluded') or 0),
                         present=int(evidence.get('trafomix_present') or 0)),
        'switches': gate(PASS if switches_ok else FAIL,
                         'Maniobras reconciliadas entre entrada y DGS.' if switches_ok
                         else 'Las maniobras de entrada no se reconciliaron con el DGS.',
                         source=int(evidence.get('source_switches') or 0),
                         dgs=int(evidence.get('dgs_switches') or 0),
                         bridge=int(evidence.get('bridge_switches') or 0)),
        'sed': gate(PASS if sed_ok else FAIL,
                    'Cada SED conservada tiene subestación y transformador.' if sed_ok
                    else 'Los conteos de SED y transformadores no coinciden.',
                    source=source_seds, substations=dgs_seds,
                    transformers=dgs_transformers),
    }


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


def _diagram_scale(tables: dict[str, Any]) -> float | None:
    terms = {row.get('FID', ''): row for row in _rows(tables, 'ElmTerm')}
    points: list[tuple[float, float, float, float]] = []
    for row in _rows(tables, 'IntGrf'):
        if row.get('sSymNam') != 'PointTerm':
            continue
        term = terms.get(row.get('pDataObj', ''))
        x, y = _number(row.get('rCenterX')), _number(row.get('rCenterY'))
        lat = _number(term.get('GPSlat')) if term else None
        lon = _number(term.get('GPSlon')) if term else None
        if None not in (x, y, lat, lon) and (-90 <= lat <= 90) and (-180 <= lon <= 180):
            points.append((x, y, lat, lon))
    if len(points) > 12:
        points = list({
            min(points, key=lambda p: p[i]) for i in range(4)
        } | {
            max(points, key=lambda p: p[i]) for i in range(4)
        })
    ratios = []
    for index, first in enumerate(points):
        for second in points[index + 1:]:
            metres = _haversine_m((first[2], first[3]), (second[2], second[3]))
            units = math.hypot(first[0] - second[0], first[1] - second[1])
            if metres > 1 and units > 0:
                ratios.append(units / metres)
    return statistics.median(ratios) if ratios else None


def _discover_inputs(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        return {'kind': None, 'status': SKIP_MISSING_INPUT,
                'detail': f'No existe la carpeta de referencia: {root}', 'paths': {}}
    classified: dict[str, list[Path]] = {RED: [], CARGA: [], EQUIPOS: []}
    for path in sorted(root.rglob('*.txt')):
        identity = identificar(path)
        if identity.tipo in classified:
            classified[identity.tipo].append(path)
    if all(len(classified[k]) == 1 for k in (RED, CARGA, EQUIPOS)):
        return {'kind': 'txt', 'status': PASS, 'detail': 'Tripleta TXT identificada por contenido.',
                'paths': {k: str(classified[k][0]) for k in (RED, CARGA, EQUIPOS)}}
    mdbs = sorted(root.rglob('*.mdb'))
    if len(mdbs) == 1:
        return {'kind': 'mdb', 'status': PASS, 'detail': 'Base MDB única descubierta.',
                'paths': {'mdb': str(mdbs[0])}}
    reason = 'No hay una tripleta TXT completa ni una base MDB única.'
    if any(len(classified[k]) > 1 for k in classified) or len(mdbs) > 1:
        reason = 'Entradas ambiguas: hay varios candidatos TXT o MDB.'
    return {'kind': None, 'status': SKIP_MISSING_INPUT, 'detail': reason,
            'paths': {k: [str(p) for p in v] for k, v in classified.items()},
            'mdb_candidates': [str(p) for p in mdbs]}


def _discover_explicit_inputs(
    *,
    red: Path | str | None = None,
    loads: Path | str | None = None,
    equipment: Path | str | None = None,
    mdb: Path | str | None = None,
    equipment_mdb: Path | str | None = None,
) -> dict[str, Any]:
    """Construye una entrada inequívoca sin depender del nombre o la carpeta."""

    txt_values = {RED: red, CARGA: loads, EQUIPOS: equipment}
    if any(value is not None for value in txt_values.values()):
        paths = {name: str(Path(value)) for name, value in txt_values.items() if value is not None}
        missing = [name for name, value in txt_values.items()
                   if value is None or not Path(value).is_file()]
        if missing:
            labels = {RED: 'RED', CARGA: 'CARGA', EQUIPOS: 'EQUIPOS'}
            return {
                'kind': 'txt', 'status': SKIP_MISSING_INPUT,
                'detail': 'Faltan entradas TXT reales: ' + ', '.join(labels[name] for name in missing),
                'paths': paths,
            }
        return {
            'kind': 'txt', 'status': PASS,
            'detail': 'Tripleta TXT indicada explícitamente.', 'paths': paths,
        }

    if mdb is not None or equipment_mdb is not None:
        paths = {}
        if mdb is not None:
            paths['mdb'] = str(Path(mdb))
        if equipment_mdb is not None:
            paths['equipment_mdb'] = str(Path(equipment_mdb))
        missing = []
        if mdb is None or not Path(mdb).is_file():
            missing.append('base de red MDB')
        if equipment_mdb is None or not Path(equipment_mdb).is_file():
            missing.append('catálogo de equipos MDB')
        if missing:
            return {
                'kind': 'mdb', 'status': SKIP_MISSING_INPUT,
                'detail': 'Falta ' + ' y '.join(missing) + '.', 'paths': paths,
            }
        return {
            'kind': 'mdb', 'status': PASS,
            'detail': 'Par MDB de red y catálogo indicado explícitamente.', 'paths': paths,
        }

    return {
        'kind': None, 'status': SKIP_MISSING_INPUT,
        'detail': 'No se indicaron entradas TXT ni MDB.', 'paths': {},
    }


def _load_dataset(discovery: dict[str, Any]):
    paths = discovery['paths']
    if discovery['kind'] == 'txt':
        return CymdistDataset.from_files(paths[RED], paths[CARGA], paths[EQUIPOS])
    if discovery['kind'] == 'mdb':
        from igea_dgs.access import read_access_dataset
        return read_access_dataset(paths['mdb'], equipment_db=paths.get('equipment_mdb'))
    raise ValueError(discovery['detail'])


def _extract_evidence(feeder: str, item: dict[str, Any]) -> dict[str, Any]:
    dgs = Path(item['dgs'])
    tables = parse_dgs(dgs)
    metadata = read_feeder_metadata(item['feeder_metadata'], expected_dgs=dgs)
    assignment_counts = {
        name: sum(record.class_name == name for record in metadata.assignments)
        for name in ('ElmLod', 'ElmSym', 'ElmXnet')
    }
    dgs_counts = {name: len(_rows(tables, name)) for name in assignment_counts}
    completeness = item.get('completitud') or {}
    rules = item.get('reglas') or {}
    trafomix = rules.get('trafomix') or {}
    names = [row.get('loc_name', '') for row in _rows(tables, 'ElmSubstat')]
    return {
        'validation_errors': item.get('errors_total'),
        'completeness_failures': completeness.get('fallos') or [],
        'mapping_feeders': sorted({record.feeder for record in metadata.assignments}),
        'assignment_counts': assignment_counts,
        'dgs_counts': dgs_counts,
        'adaptive_grid': item.get('hoja') is None,
        'scale_units_per_m': _diagram_scale(tables),
        'trafomix_excluded': trafomix.get('excluidos') or 0,
        'trafomix_present': sum(bool(re.fullmatch(r'M\d+(?:-\d+)?', name, re.I)) for name in names),
        'source_switches': (completeness.get('entrada') or {}).get('maniobras') or 0,
        'dgs_switches': (completeness.get('dgs') or {}).get('StaSwitch') or 0,
        'bridge_switches': (rules.get('puentes') or {}).get('interruptores') or 0,
        'source_seds': (item.get('counts') or {}).get('source_seds') or 0,
        'dgs_seds': len(_rows(tables, 'ElmSubstat')),
        'dgs_transformers': len(_rows(tables, 'ElmTr2')),
        'dgs_sha256': sha256_file(dgs),
    }


def _powerfactory(feeder: str, item: dict[str, Any], output: Path) -> dict[str, Any]:
    pf_dir = pf_python_dir()
    interpreter, reason = python_for_pf(pf_dir)
    if pf_dir is None or interpreter is None or not (pf_dir / 'powerfactory.pyd').is_file():
        return gate(NOT_RUN_POWERFACTORY, f'API o intérprete PowerFactory no disponible: {reason}')
    report_json = output / f'{feeder}_powerfactory_acceptance.json'
    report_txt = output / f'{feeder}_powerfactory_acceptance.txt'
    command = [
        str(interpreter), str(PROJECT_ROOT / 'tools' / 'powerfactory_acceptance.py'),
        '--import-dgs', str(item['dgs']), '--manifest', str(item['geography']),
        '--feeder-metadata', str(item['feeder_metadata']), '--ensure-scenario',
        '--run-load-flow', '--fix-until-converge', '--require-diagram',
        '--output-json', str(report_json), '--output-txt', str(report_txt),
    ]
    try:
        result = subprocess.run(command, env=pf_subprocess_env(pf_dir), cwd=PROJECT_ROOT,
                                capture_output=True, text=True, timeout=1800, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return gate(NOT_RUN_POWERFACTORY, f'No se pudo ejecutar PowerFactory: {exc}')
    if result.returncode == 0:
        return gate(PASS, 'Aceptación PowerFactory y flujo ejecutados.', report=str(report_json))
    if result.returncode == 3:
        return gate(NOT_RUN_POWERFACTORY, 'PowerFactory/API no estaba disponible.',
                    report=str(report_json), stderr=result.stderr[-2000:])
    return gate(FAIL, f'PowerFactory devolvió código {result.returncode}.',
                report=str(report_json), stderr=result.stderr[-2000:])


def _skipped_gates(reason: str, *, powerfactory: bool) -> dict[str, dict[str, Any]]:
    gates = {'input': gate(SKIP_MISSING_INPUT, reason)}
    for name in ('conversion', 'mapping', 'grid_scale', 'trafomix', 'switches', 'sed'):
        gates[name] = gate(SKIP_MISSING_INPUT, reason)
    gates['powerfactory'] = gate(
        NOT_RUN_POWERFACTORY,
        'No se solicitó PowerFactory.' if not powerfactory else 'Sin DGS verificable para PowerFactory.',
    )
    return gates


def verify_reference_feeders(
    reference_root: Path | str,
    output: Path | str,
    feeders: Iterable[str] = DEFAULT_FEEDERS,
    *,
    powerfactory: bool = False,
    discovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reference_root, output = Path(reference_root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    feeders = tuple(dict.fromkeys(str(name).strip() for name in feeders if str(name).strip()))
    discovery = discovery or _discover_inputs(reference_root)
    report: dict[str, Any] = {
        'schema_version': 1,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'reference_root': str(reference_root.resolve()),
        'output': str(output.resolve()),
        'input': discovery,
        'input_artifacts': [
            {'path': str(Path(path).resolve()), 'sha256': sha256_file(Path(path))}
            for path in discovery.get('paths', {}).values()
            if isinstance(path, str) and Path(path).is_file()
        ],
        'reference_artifacts': [
            {'path': str(path.resolve()), 'sha256': sha256_file(path)}
            for path in sorted(reference_root.glob('*.dgs'))
        ] if reference_root.is_dir() else [],
        'feeders': {},
    }
    if discovery['status'] != PASS:
        for feeder in feeders:
            report['feeders'][feeder] = {'gates': _skipped_gates(discovery['detail'], powerfactory=powerfactory)}
        report['status'] = SKIP_MISSING_INPUT
        _write_reports(report, output)
        return report

    try:
        dataset = _load_dataset(discovery)
    except Exception as exc:
        detail = f'No se pudo leer la entrada descubierta: {exc}'
        for feeder in feeders:
            gates = _skipped_gates(detail, powerfactory=powerfactory)
            gates['input'] = gate(FAIL, detail)
            report['feeders'][feeder] = {'gates': gates}
        report['status'] = FAIL
        _write_reports(report, output)
        return report

    available = {feeder_short_name(network): network for network in dataset.feeder_ids()}
    for feeder in feeders:
        network = available.get(feeder)
        if network is None:
            reason = f'El export descubierto no contiene el alimentador {feeder}.'
            report['feeders'][feeder] = {'gates': _skipped_gates(reason, powerfactory=powerfactory)}
            continue
        feeder_output = output / feeder
        try:
            manifest = convert_selection(dataset, [network], feeder_output, workers=1)
            item = manifest['feeders'][0]
            if item.get('status') != 'ok':
                gates = _skipped_gates('La conversión no publicó un DGS.', powerfactory=powerfactory)
                gates['input'] = gate(PASS, 'Alimentador localizado en la entrada.', network_id=network)
                gates['conversion'] = gate(FAIL, item.get('error') or 'Conversión fallida.', item=item)
            else:
                evidence = _extract_evidence(feeder, item)
                gates = {'input': gate(PASS, 'Alimentador localizado en la entrada.', network_id=network)}
                gates.update(evaluate_evidence(feeder, evidence))
                gates['powerfactory'] = (
                    _powerfactory(feeder, item, feeder_output) if powerfactory
                    else gate(NOT_RUN_POWERFACTORY, 'No se solicitó PowerFactory.')
                )
            report['feeders'][feeder] = {'gates': gates, 'artifact': item}
        except Exception as exc:
            gates = _skipped_gates('No se produjeron artefactos verificables.', powerfactory=powerfactory)
            gates['input'] = gate(PASS, 'Alimentador localizado en la entrada.', network_id=network)
            gates['conversion'] = gate(FAIL, str(exc))
            report['feeders'][feeder] = {'gates': gates}

    statuses = [g['status'] for item in report['feeders'].values() for g in item['gates'].values()]
    report['status'] = FAIL if FAIL in statuses else (SKIP_MISSING_INPUT if SKIP_MISSING_INPUT in statuses else PASS)
    _write_reports(report, output)
    return report


def verify_input_alternatives(
    output: Path | str,
    feeders: Iterable[str] = DEFAULT_FEEDERS,
    *,
    txt: dict[str, Any],
    mdb: dict[str, Any],
    powerfactory: bool = False,
) -> dict[str, Any]:
    """Ejecuta y conserva por separado las dos rutas reales soportadas."""

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    feeders = tuple(feeders)
    modes = {
        'txt': verify_reference_feeders(
            PROJECT_ROOT, output / 'txt', feeders,
            powerfactory=powerfactory, discovery=txt,
        ),
        'mdb': verify_reference_feeders(
            PROJECT_ROOT, output / 'mdb', feeders,
            powerfactory=powerfactory, discovery=mdb,
        ),
    }
    statuses = {mode: result['status'] for mode, result in modes.items()}
    status = FAIL if FAIL in statuses.values() else (
        SKIP_MISSING_INPUT if SKIP_MISSING_INPUT in statuses.values() else PASS
    )
    report = {
        'schema_version': 2,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'status': status,
        'output': str(output.resolve()),
        'mode_statuses': statuses,
        'modes': modes,
    }
    (output / 'input_alternatives_validation.json').write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8',
    )
    lines = [
        '# Validación real de alternativas TXT y MDB', '',
        f'Estado global: **{status}**', '',
        '| Ruta | Estado | Informe detallado |', '|---|---|---|',
    ]
    for mode, mode_status in statuses.items():
        lines.append(f'| {mode.upper()} | {mode_status} | `{mode}/reference_feeders_validation.md` |')
    lines += ['', 'Cada ruta se evalúa contra su propia instantánea de origen; no se exige igualdad de conteos entre TXT y MDB.', '']
    (output / 'input_alternatives_validation.md').write_text('\n'.join(lines), encoding='utf-8')
    return report


def _write_reports(report: dict[str, Any], output: Path) -> None:
    json_path = output / 'reference_feeders_validation.json'
    md_path = output / 'reference_feeders_validation.md'
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    lines = [
        '# Validación de alimentadores de referencia', '',
        f"Estado global: **{report.get('status', FAIL)}**", '',
        '| Alimentador | Entrada | Conversión | Mapping | Escala | Trafomix | SW | SED | PowerFactory |',
        '|---|---|---|---|---|---|---|---|---|',
    ]
    for feeder, item in report.get('feeders', {}).items():
        gates = item['gates']
        lines.append('| ' + ' | '.join([
            feeder, gates['input']['status'], gates['conversion']['status'],
            gates['mapping']['status'], gates['grid_scale']['status'],
            gates['trafomix']['status'], gates['switches']['status'],
            gates['sed']['status'], gates['powerfactory']['status'],
        ]) + ' |')
    lines += ['', '## Límites', '',
              '- `SKIP_MISSING_INPUT` significa que no se ejecutó esa comprobación.',
              '- `NOT_RUN_POWERFACTORY` no demuestra importación ni convergencia en DIgSILENT.',
              '- Solo `PASS` procede de una comprobación ejecutada con artefactos disponibles.', '']
    md_path.write_text('\n'.join(lines), encoding='utf-8')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-root', type=Path, default=PROJECT_ROOT / 'referencia')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--feeders', nargs='+', default=list(DEFAULT_FEEDERS))
    parser.add_argument('--red', type=Path)
    parser.add_argument('--loads', type=Path)
    parser.add_argument('--equipment', type=Path)
    parser.add_argument('--mdb', type=Path)
    parser.add_argument('--equipment-mdb', type=Path)
    parser.add_argument('--powerfactory', action='store_true')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    txt_requested = any((args.red, args.loads, args.equipment))
    mdb_requested = any((args.mdb, args.equipment_mdb))
    txt = _discover_explicit_inputs(red=args.red, loads=args.loads, equipment=args.equipment)
    mdb = _discover_explicit_inputs(mdb=args.mdb, equipment_mdb=args.equipment_mdb)
    if txt_requested and mdb_requested:
        report = verify_input_alternatives(
            args.output, args.feeders, txt=txt, mdb=mdb, powerfactory=args.powerfactory,
        )
    else:
        discovery = txt if txt_requested else (mdb if mdb_requested else None)
        report = verify_reference_feeders(
            args.reference_root, args.output, args.feeders,
            powerfactory=args.powerfactory, discovery=discovery,
        )
    print(f"Reference validation: {report['status']}")
    filename = ('input_alternatives_validation.json'
                if txt_requested and mdb_requested else 'reference_feeders_validation.json')
    print(args.output / filename)
    return 2 if report['status'] == FAIL else 0


if __name__ == '__main__':
    raise SystemExit(main())
