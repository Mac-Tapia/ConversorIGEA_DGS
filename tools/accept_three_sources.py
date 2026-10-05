#!/usr/bin/env python3
"""Aceptación auditada y separada de MDB, TXT y VNR-GIS.

Cada modalidad obtiene su propio ``Workspace`` y ``source_run_id``. Nunca se usa
un archivo de otra modalidad ni se rellena una fuente ausente con un fixture.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from igea_dgs.feeder_metadata import sha256_file  # noqa: E402
from igea_dgs.web import services  # noqa: E402
from igea_dgs.web.jobs import Job, JobContext  # noqa: E402
from igea_dgs.web.workspace import Workspace  # noqa: E402


@dataclass(frozen=True)
class AcceptanceConfig:
    audit_dir: Path
    feeder: str = 'IN111'
    feeders: tuple[str, ...] = ()
    all_feeders: bool = False
    source_company: str = ''
    source_period: str = ''
    source_crs: str = 'EPSG:32718'
    reconstruct: bool = True
    allow_catalog_matches: bool = True
    allow_engineering_assumptions: bool = True
    minimum_catalog_confidence: float = 0.75
    topology_snap_tolerance: float = 1.0
    provisional_nominal_voltage_kv: float = 10.0
    txt_red: Path | None = None
    txt_loads: Path | None = None
    txt_equipment: Path | None = None
    txt_equipment_extra: Path | None = None
    mdb: Path | None = None
    equipment_mdb: Path | None = None
    study: Path | None = None
    vnr_package: Path | None = None
    run_powerfactory: bool = False


MODE_INPUTS: dict[str, tuple[tuple[str, str], ...]] = {
    'txt': (
        ('red', 'txt_red'), ('loads', 'txt_loads'), ('equipment', 'txt_equipment'),
        ('equipment_extra', 'txt_equipment_extra'),
    ),
    'mdb': (('mdb', 'mdb'), ('equipment_mdb', 'equipment_mdb'), ('study', 'study')),
    'vnr': (('vnr_package', 'vnr_package'),),
}
REQUIRED: dict[str, tuple[str, ...]] = {
    'txt': ('txt_red', 'txt_loads', 'txt_equipment'),
    'mdb': ('mdb',),
    'vnr': ('vnr_package',),
}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def _context(workspace: Workspace, log_path: Path) -> JobContext:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(_wid: str, kind: str, data: dict) -> None:
        workspace.events.append(kind, data)
        if kind == 'log' and data.get('text'):
            with log_path.open('a', encoding='utf-8') as stream:
                stream.write(str(data['text']) + '\n')

    job = Job(kind='acceptance', title='Aceptación de fuente', workspace_id=workspace.id,
              lane='engine', fn=lambda _ctx: None)
    return JobContext(job, emit)


def _missing(config: AcceptanceConfig, mode: str) -> list[str]:
    missing = []
    for field in REQUIRED[mode]:
        value = getattr(config, field)
        if value is None or not Path(value).is_file():
            missing.append(field)
    return missing


def _empty_result(mode: str, status: str, *, error: str | None = None) -> dict[str, Any]:
    return {
        'mode': mode,
        'status': status,
        'error': error,
        'input_files': [],
        'source_run_id': None,
        'source_fingerprint': None,
        'feeder_count': None,
        'selected_ids': [],
        'dgs_files': [],
        'reconstruction': None,
        'original_hashes_before': {},
        'original_hashes_after': {},
        'originals_unchanged': None,
        'powerfactory': {'evidence_level': 'NOT_RUN'},
    }


def _original_hashes(config: AcceptanceConfig, mode: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for _slot, field in MODE_INPUTS[mode]:
        value = getattr(config, field)
        if value is not None and Path(value).is_file():
            hashes[str(Path(value).resolve())] = sha256_file(Path(value))
    return hashes


def _finalize_original_hashes(
    row: dict[str, Any], config: AcceptanceConfig, mode: str,
) -> None:
    after = _original_hashes(config, mode)
    row['original_hashes_after'] = after
    row['originals_unchanged'] = bool(row['original_hashes_before']) and (
        row['original_hashes_before'] == after
    )


def _accept_mode(config: AcceptanceConfig, mode: str) -> dict[str, Any]:
    missing = _missing(config, mode)
    if missing:
        status = 'BLOCKED_MISSING_OFFICIAL_PACKAGE' if mode == 'vnr' else 'SKIP_MISSING_INPUT'
        row = _empty_result(mode, status)
        row['missing_inputs'] = missing
        return row

    workspace = Workspace(id=f'accept-{mode}', root=config.audit_dir / mode / 'workspace')
    workspace.options.update({
        'input_mode': mode,
        'include_geography': True,
        'write_preview': False,
        'export_xlsx': False,
        'export_tsv': False,
        'workers': 1,
        'source_company': config.source_company,
        'source_period': config.source_period,
        'source_crs': config.source_crs,
    })
    workspace.save()
    for slot, field in MODE_INPUTS[mode]:
        value = getattr(config, field)
        if value is not None:
            workspace.set_input(slot, Path(value), origin='server')
    with workspace.lock:
        workspace.options['input_mode'] = mode
        workspace.save()

    ctx = _context(workspace, config.audit_dir / mode / 'acceptance.log')
    row = _empty_result(mode, 'RUNNING')
    row['original_hashes_before'] = _original_hashes(config, mode)
    try:
        services.check_ready(workspace)
        services.load_dataset(workspace, ctx)
        snapshot = services.require_active_source_run(workspace)
        row.update({
            'source_run_id': snapshot.run_id,
            'source_fingerprint': snapshot.fingerprint,
            'source_manifest': str(snapshot.root / 'source_manifest.json'),
            'input_files': [
                {
                    'slot': item.slot,
                    'name': item.name,
                    'size': item.size,
                    'sha256': item.sha256,
                }
                for item in sorted(snapshot.files.values(), key=lambda item: item.slot)
            ],
            'feeder_count': len((workspace.inventory or {}).get('feeders') or []),
        })
        rows = services.feeder_rows(workspace)
        available = [item['feeder'] for item in rows]
        requested = list(config.feeders or (config.feeder,))
        selected = available if config.all_feeders else [name for name in requested if name in available]
        row['selected_ids'] = selected
        missing_selected = [] if config.all_feeders else [name for name in requested if name not in available]
        if not selected or missing_selected:
            row['status'] = 'SKIP_FEEDER_NOT_PRESENT'
            row['missing_feeders'] = missing_selected or requested
            return row

        if config.reconstruct:
            from igea_dgs.reconstruction import ReconstructionPolicy
            from igea_dgs.web.reconstruction_service import reconstruct_selection

            reconstruction = reconstruct_selection(
                workspace,
                selected,
                all_feeders=config.all_feeders,
                policy=ReconstructionPolicy(
                    allow_catalog_matches=config.allow_catalog_matches,
                    allow_engineering_assumptions=config.allow_engineering_assumptions,
                    minimum_catalog_confidence=config.minimum_catalog_confidence,
                    topology_snap_tolerance=config.topology_snap_tolerance,
                    provisional_nominal_voltage_kv=config.provisional_nominal_voltage_kv,
                ),
            )
            row['reconstruction'] = {
                **reconstruction,
                'selection': list(selected),
                'path': str(workspace.out_dir / reconstruction['report']),
            }
            rows = services.feeder_rows(workspace)

        blocked_rows = [
            item for item in rows
            if item['feeder'] in selected and item['readiness'] == 'INVENTORY_ONLY'
        ]
        if blocked_rows:
            row['status'] = 'BLOCKED_FEEDER_NOT_READY'
            row['blocking_codes'] = {
                item['feeder']: item['blocking_codes'] for item in blocked_rows
            }
            return row

        conversion = services.convert(workspace, ctx, selected, False)
        row['conversion_result'] = conversion
        dgs_files = []
        for feeder in selected:
            dgs = workspace.out_dir / f'{feeder}.dgs'
            if dgs.is_file():
                dgs_files.append({
                    'feeder': feeder,
                    'path': str(dgs),
                    'size': dgs.stat().st_size,
                    'sha256': sha256_file(dgs),
                })
        row['dgs_files'] = dgs_files
        if len(dgs_files) != len(selected) or conversion['summary']['ok'] != len(selected):
            row['status'] = 'FAILED_CONVERSION'
            return row
        row['status'] = 'DGS_READY'

        if config.run_powerfactory:
            services.check_powerfactory_flow(workspace, selected)
            pf_result = services.powerfactory_flow(workspace, ctx, selected)
            report_path = workspace.out_dir / f'{selected[0]}_powerfactory_acceptance.json'
            report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.is_file() else {}
            reread = report.get('effective_reread') or {}
            verified = bool(
                pf_result.get('ok') == len(selected)
                and report.get('powerfactory_runtime_pass')
                and (report.get('source_verification') or {}).get('status') == 'VERIFIED_BEFORE_MUTATION'
                and reread.get('feeder_metadata')
                and reread.get('comldf_valid') is True
            )
            row['powerfactory'] = {
                'evidence_level': (
                    'POWERFACTORY_REAL_VERIFIED' if verified else 'POWERFACTORY_EXECUTED_FAILED'
                ),
                'result': pf_result,
                'report': str(report_path) if report_path.is_file() else None,
                'project': (report.get('import') or {}).get('project_name'),
                'effective_reread': reread,
                'rollback': report.get('rollback'),
                'reconstruction': report.get('reconstruction_verification'),
                'convergence_classification': report.get('convergence_classification'),
            }
            row['status'] = 'POWERFACTORY_VERIFIED' if verified else 'FAILED_POWERFACTORY'
        return row
    except Exception as exc:  # noqa: BLE001 - el resumen debe persistir también el bloqueo
        row['status'] = 'FAILED'
        row['error'] = f'{type(exc).__name__}: {exc}'
        return row
    finally:
        _finalize_original_hashes(row, config, mode)


def validate_summary(summary: dict[str, Any]) -> None:
    rows = summary.get('sources') or []
    if {row.get('mode') for row in rows} != {'txt', 'mdb', 'vnr'}:
        raise ValueError('el resumen debe contener exactamente txt, mdb y vnr')
    run_ids = [row.get('source_run_id') for row in rows if row.get('source_run_id')]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError('se reutiliza un source_run_id entre modalidades')
    allowed_slots = {mode: {slot for slot, _field in fields} for mode, fields in MODE_INPUTS.items()}
    for row in rows:
        mode = row['mode']
        foreign = {item['slot'] for item in row.get('input_files') or []} - allowed_slots[mode]
        if foreign:
            raise ValueError(f'{mode} contiene slots de otra modalidad: {sorted(foreign)}')
        for item in row.get('input_files') or []:
            if len(item.get('sha256') or '') != 64:
                raise ValueError(f'{mode} tiene una entrada sin SHA-256')
        for item in row.get('dgs_files') or []:
            if len(item.get('sha256') or '') != 64:
                raise ValueError(f'{mode} tiene un DGS sin SHA-256')
        if row.get('originals_unchanged') is False:
            raise ValueError(f'{mode} modificó un archivo original durante la aceptación')


def run_three_sources(config: AcceptanceConfig) -> dict[str, Any]:
    config.audit_dir.mkdir(parents=True, exist_ok=True)
    sources = [_accept_mode(config, mode) for mode in ('txt', 'mdb', 'vnr')]
    complete_states = {'DGS_READY', 'POWERFACTORY_VERIFIED'}
    summary = {
        'schema_version': 'igea-dgs-three-source-acceptance-v2',
        'created_at': time.time(),
        'audit_dir': str(config.audit_dir.resolve()),
        'requested_feeder': config.feeder,
        'requested_feeders': list(config.feeders or (config.feeder,)),
        'all_feeders': config.all_feeders,
        'requested_company': config.source_company,
        'requested_period': config.source_period,
        'source_crs': config.source_crs,
        'reconstruction_requested': config.reconstruct,
        'powerfactory_requested': config.run_powerfactory,
        'sources': sources,
        'overall_status': (
            'COMPLETE' if all(row['status'] in complete_states for row in sources) else 'INCOMPLETE'
        ),
    }
    validate_summary(summary)
    _atomic_json(config.audit_dir / 'acceptance_summary.json', summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path)
    parser.add_argument('--feeder', action='append', dest='feeders')
    parser.add_argument('--all-feeders', action='store_true')
    parser.add_argument('--company', default='')
    parser.add_argument('--period', default='')
    parser.add_argument('--source-crs', default='EPSG:32718')
    parser.add_argument('--no-reconstruct', action='store_true')
    parser.add_argument('--no-catalog-matches', action='store_true')
    parser.add_argument('--no-engineering-assumptions', action='store_true')
    parser.add_argument('--minimum-catalog-confidence', type=float, default=0.75)
    parser.add_argument('--topology-snap-tolerance', type=float, default=1.0)
    parser.add_argument('--provisional-nominal-voltage-kv', type=float, default=10.0)
    parser.add_argument('--txt-red', type=Path)
    parser.add_argument('--txt-loads', type=Path)
    parser.add_argument('--txt-equipment', type=Path)
    parser.add_argument('--txt-equipment-extra', type=Path)
    parser.add_argument('--mdb', type=Path)
    parser.add_argument('--equipment-mdb', type=Path)
    parser.add_argument('--study', type=Path)
    parser.add_argument('--vnr-package', type=Path)
    parser.add_argument('--powerfactory', action='store_true')
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    args = _parser().parse_args(argv)
    audit_dir = args.audit_dir or ROOT / 'AUDIT' / f'three_source_{time.strftime("%Y%m%d_%H%M%S")}'
    config = AcceptanceConfig(
        audit_dir=audit_dir,
        feeder=(args.feeders or ['IN111'])[0],
        feeders=tuple(args.feeders or ()),
        all_feeders=args.all_feeders,
        source_company=args.company,
        source_period=args.period,
        source_crs=args.source_crs,
        reconstruct=not args.no_reconstruct,
        allow_catalog_matches=not args.no_catalog_matches,
        allow_engineering_assumptions=not args.no_engineering_assumptions,
        minimum_catalog_confidence=args.minimum_catalog_confidence,
        topology_snap_tolerance=args.topology_snap_tolerance,
        provisional_nominal_voltage_kv=args.provisional_nominal_voltage_kv,
        txt_red=args.txt_red,
        txt_loads=args.txt_loads,
        txt_equipment=args.txt_equipment,
        txt_equipment_extra=args.txt_equipment_extra,
        mdb=args.mdb,
        equipment_mdb=args.equipment_mdb,
        study=args.study,
        vnr_package=args.vnr_package,
        run_powerfactory=args.powerfactory,
    )
    summary = run_three_sources(config)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
