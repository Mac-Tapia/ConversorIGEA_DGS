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
        'powerfactory': {'evidence_level': 'NOT_RUN'},
    }


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
        selected = [item['feeder'] for item in rows if item['feeder'] == config.feeder]
        row['selected_ids'] = selected
        if not selected:
            row['status'] = 'SKIP_FEEDER_NOT_PRESENT'
            return row
        selected_row = next(item for item in rows if item['feeder'] == config.feeder)
        if selected_row['readiness'] == 'INVENTORY_ONLY':
            row['status'] = 'BLOCKED_FEEDER_NOT_READY'
            row['blocking_codes'] = selected_row['blocking_codes']
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
            }
            row['status'] = 'POWERFACTORY_VERIFIED' if verified else 'FAILED_POWERFACTORY'
        return row
    except Exception as exc:  # noqa: BLE001 - el resumen debe persistir también el bloqueo
        row['status'] = 'FAILED'
        row['error'] = f'{type(exc).__name__}: {exc}'
        return row


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


def run_three_sources(config: AcceptanceConfig) -> dict[str, Any]:
    config.audit_dir.mkdir(parents=True, exist_ok=True)
    sources = [_accept_mode(config, mode) for mode in ('txt', 'mdb', 'vnr')]
    complete_states = {'DGS_READY', 'POWERFACTORY_VERIFIED'}
    summary = {
        'schema_version': 'igea-dgs-three-source-acceptance-v1',
        'created_at': time.time(),
        'audit_dir': str(config.audit_dir.resolve()),
        'requested_feeder': config.feeder,
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
    parser.add_argument('--feeder', default='IN111')
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
        feeder=args.feeder,
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
