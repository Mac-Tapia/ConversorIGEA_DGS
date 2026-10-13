#!/usr/bin/env python3
"""Aceptación universal y auditada de MDB, TXT y VNR-GIS hasta el estudio nativo.

Cada modalidad obtiene su propio ``Workspace`` y ``source_run_id``. Nunca se usa
un archivo de otra modalidad ni se rellena una fuente ausente con un fixture. Todas
recorren los mismos servicios de carga, ajuste, relectura y estudio de PowerFactory.
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

from igea_dgs.util import sha256_file  # noqa: E402
from igea_dgs.web import services  # noqa: E402
from igea_dgs.web.jobs import Job, JobContext  # noqa: E402
from igea_dgs.web.workspace import Workspace  # noqa: E402


@dataclass(frozen=True)
class AcceptanceConfig:
    audit_dir: Path
    feeder: str = ''
    feeders: tuple[str, ...] = ()
    all_feeders: bool = False
    source_company: str = ''
    source_period: str = ''
    #: None: el del perfil de empresa (spec 002, RF-32).
    source_crs: str | None = None
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
    cabecera: Path | None = None
    suministros: Path | None = None
    clientes: Path | None = None
    meters_by_feeder: tuple[tuple[str, str], ...] = ()
    load_tolerance: float = 0.01
    studies: tuple[str, ...] = ('flujo',)


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


def build_native_load_evidence(
    *,
    source_audit: dict[str, Any] | None = None,
    source_audit_sha256: str | None = None,
    conversion_result: dict[str, Any] | None = None,
    powerfactory_reports: list[dict[str, Any]] | None = None,
    adjustments: list[dict[str, Any]] | None = None,
    studies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compone la evidencia pública sin introducir un algoritmo por tipo de fuente."""
    pf_reports = list(powerfactory_reports or [])
    adjustment_rows = list(adjustments or [])
    study_rows = list(studies or [])

    metadata_rows = [dict(report.get('feeder_metadata') or {}) for report in pf_reports]
    capacitor_rows = [dict(report.get('capacitor_reread') or {}) for report in pf_reports]
    bindings = [dict(report['project_binding']) for report in pf_reports
                if isinstance(report.get('project_binding'), dict)]
    expected_capacitors = sum(int(row.get('expected') or 0) for row in capacitor_rows)
    capacitor_banks = [bank for row in capacitor_rows for bank in (row.get('banks') or [])]
    corrections = [item for row in capacitor_rows for item in (row.get('corrections') or [])]
    mismatches = [item for row in capacitor_rows for item in (row.get('mismatches') or [])]

    client_periods: list[dict[str, Any]] = []
    fixed_keys: set[tuple[str, str]] = set()
    scaled_keys: set[tuple[str, str]] = set()
    fixed_evidence: list[dict[str, Any]] = []
    native_reread: list[dict[str, Any]] = []
    head_balance: list[dict[str, Any]] = []
    adjustment_statuses: list[str] = []
    for row in adjustment_rows:
        plan = dict(row.get('plan') or {})
        result = dict(row.get('result') or {})
        report = dict(result.get('informe') or result)
        feeder = str(report.get('feeder') or plan.get('feeder') or '')
        client_periods.append({
            'feeder': feeder,
            'periodo': dict(plan.get('periodo') or {}),
            'client_evidence': dict(plan.get('client_evidence') or {}),
        })
        for item in plan.get('fixed_load_evidence') or []:
            fixed = {'feeder': feeder, **dict(item)}
            fixed_evidence.append(fixed)
            fixed_keys.add((feeder, str(item.get('sed') or '')))
        for item in report.get('sed') or []:
            key = (feeder, str(item.get('sed') or ''))
            if item.get('origen') == 'cliente':
                fixed_keys.add(key)
            else:
                scaled_keys.add(key)
        reread = dict(report.get('relectura_cargas_nativas') or {})
        if reread:
            native_reread.append({'feeder': feeder, **reread})
        status = str(report.get('status') or '')
        if status:
            adjustment_statuses.append(status)
        head_balance.append({
            'feeder': feeder,
            'status': status or None,
            'kw_accepted': bool(report.get('cuadrado')),
            'objective': dict(report.get('objetivo') or {}),
            'native': dict(report.get('cabecera') or {}),
            'kvar_difference': dict(report.get('kvar_no_bloqueante') or {}),
        })

    measures = [dict(item) for study in study_rows for item in (study.get('medidas') or [])]
    physical_violations = [
        dict(item) for study in study_rows for item in (study.get('violaciones') or [])
    ]
    comldf_rows = [dict(report.get('effective_reread') or {}) for report in pf_reports]
    all_valid = bool(comldf_rows) and all(
        row.get('comldf_executed') is True and row.get('comldf_valid') is True
        for row in comldf_rows
    )

    if not pf_reports:
        status = 'NOT_RUN'
    elif not adjustment_rows or not study_rows:
        status = 'BLOQUEADO_DATOS'
    elif physical_violations:
        status = 'VIOLACION_FISICA'
    elif not all_valid or any(not item.get('converge') for item in measures):
        status = 'NO_CONVERGE'
    elif any(value == 'AVISO_KVAR' for value in adjustment_statuses):
        status = 'AVISO_KVAR'
    elif corrections or mismatches:
        status = ('AVISO_PERSISTENCIA_CORREGIDA' if corrections and not mismatches
                  else 'AVISO_PERSISTENCIA_NO_CORREGIDA')
    else:
        status = 'OK'

    return {
        'schema_version': 'igea-dgs-three-source-native-load-v1',
        'status': status,
        'source_audit': {
            'status': (source_audit or {}).get('status'),
            'counts': dict((source_audit or {}).get('counts') or
                           (source_audit or {}).get('totals') or {}),
            'sha256': source_audit_sha256,
        },
        'conversion': dict(conversion_result or {}),
        'capacitors': {
            'expected': expected_capacitors,
            'reread': len(capacitor_banks),
            'banks': capacitor_banks,
            'corrections': corrections,
            'mismatches': mismatches,
            'blocks': False,
        },
        'metadata_assignment': {
            'written': sum(int(row.get('written') or 0) for row in metadata_rows),
            'reread': sum(int(row.get('reread_count') or 0) for row in metadata_rows),
            'verified': bool(metadata_rows) and all(row.get('reread_verified') for row in metadata_rows),
            'by_feeder': {
                feeder: count for row in metadata_rows
                for feeder, count in (row.get('by_feeder') or {}).items()
            },
        },
        'project_bindings': bindings,
        'client_periods': client_periods,
        'loads': {
            'fixed_seds': len({key for key in fixed_keys if key[1]}),
            'scaled_seds': len({key for key in scaled_keys if key[1]}),
            'fixed_evidence': fixed_evidence,
            'native_reread': native_reread,
        },
        'head_balance': head_balance,
        'load_flow': {'all_valid': all_valid, 'reports': comldf_rows},
        'studies': study_rows,
        'measures': measures,
        'physical_violations': physical_violations,
    }


def _run_native_load_contract(
    workspace: Workspace,
    ctx: JobContext,
    config: AcceptanceConfig,
    selected: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Ejecuta ajuste y estudios por los mismos servicios usados por la web."""
    meters = {str(feeder): str(meter) for feeder, meter in config.meters_by_feeder}
    missing_meters = [feeder for feeder in selected if not meters.get(feeder)]
    if config.cabecera is None or not Path(config.cabecera).exists():
        raise ValueError('BLOQUEADO_DATOS: falta la medición de cabecera para el contrato de carga')
    if missing_meters:
        raise ValueError(
            'BLOQUEADO_DATOS: faltan medidores de cabecera para ' + ', '.join(missing_meters)
        )
    if bool(config.suministros) != bool(config.clientes):
        raise ValueError(
            'BLOQUEADO_DATOS: suministros y clientes importantes deben indicarse juntos'
        )

    services.demanda_asignar(workspace, 'cabecera', Path(config.cabecera), 'server')
    if config.suministros and config.clientes:
        services.demanda_asignar(
            workspace, 'suministros', Path(config.suministros), 'server',
        )
        services.demanda_asignar(workspace, 'clientes', Path(config.clientes), 'server')
        if Path(config.clientes).is_dir():
            services.demanda_clientes_indexar(workspace, ctx)

    maxima_result = services.demanda_cabecera(
        workspace, ctx, [(feeder, meters[feeder]) for feeder in selected],
    )
    maximas = list(maxima_result.get('resultados') or [])
    adjustments: list[dict[str, Any]] = []
    studies: list[dict[str, Any]] = []
    for feeder in selected:
        project = str(workspace.pf_projects.get(feeder) or '')
        if not project:
            raise ValueError(
                f'BLOQUEADO_PERSISTENCIA: {feeder} no tiene proyecto nativo aceptado'
            )
        plan_summary = services.ajuste_plan(
            workspace, project, maximas, meters[feeder], config.load_tolerance,
        )
        token = plan_summary['token']
        meta = workspace.cargas_planes[token]
        paths = [Path(path) for path in (meta.get('paths') or [meta['path']])]
        candidate_plans = [
            json.loads(path.read_text(encoding='utf-8')) for path in paths
        ]
        feeder_plan = next(
            (plan for plan in candidate_plans if plan.get('feeder') == feeder), None,
        )
        if feeder_plan is None:
            raise ValueError(f'BLOQUEADO_DATOS: no se conservó el plan de {feeder}')
        adjustment = services.ajuste_ejecutar(workspace, ctx, token, simular=False)
        adjustments.append({'plan': feeder_plan, 'result': adjustment})

        study_plan = services.estudios_plan(
            workspace, project, [feeder], list(config.studies), adjustment,
        )
        study_result = services.estudios_ejecutar(workspace, ctx, study_plan['token'])
        studies.append(study_result)
    return adjustments, studies


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
        'native_load_contract': build_native_load_evidence(),
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
        audit_path = workspace.out_dir / 'universal_source_audit.json'
        row['source_audit'] = {
            'path': str(audit_path) if audit_path.is_file() else None,
            'sha256': sha256_file(audit_path) if audit_path.is_file() else None,
            'evidence': dict(workspace.source_audit or {}),
        }
        rows = services.feeder_rows(workspace)
        available = [item['feeder'] for item in rows]
        requested = list(config.feeders or ((config.feeder,) if config.feeder else ()))
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
            row['status'] = 'BLOQUEADO_DATOS'
            return row
        row['status'] = 'DGS_READY'
        row['native_load_contract'] = build_native_load_evidence(
            source_audit=(row.get('source_audit') or {}).get('evidence'),
            source_audit_sha256=(row.get('source_audit') or {}).get('sha256'),
            conversion_result=conversion,
        )

        if config.run_powerfactory:
            services.check_powerfactory_flow(workspace, selected)
            pf_result = services.powerfactory_flow(workspace, ctx, selected)
            report_paths = [
                workspace.out_dir / f'{feeder}_powerfactory_acceptance.json'
                for feeder in selected
            ]
            reports = [json.loads(path.read_text(encoding='utf-8'))
                       for path in report_paths if path.is_file()]
            report_path = report_paths[0]
            report = reports[0] if reports else {}
            reread = report.get('effective_reread') or {}
            verified = bool(
                len(reports) == len(selected)
                and pf_result.get('ok') == len(selected)
                and all(item.get('powerfactory_runtime_pass') for item in reports)
                and all((item.get('source_verification') or {}).get('status') ==
                        'VERIFIED_BEFORE_MUTATION' for item in reports)
                and all((item.get('effective_reread') or {}).get('feeder_metadata')
                        for item in reports)
                and all((item.get('effective_reread') or {}).get('comldf_valid') is True
                        for item in reports)
            )
            row['powerfactory'] = {
                'evidence_level': (
                    'POWERFACTORY_REAL_VERIFIED' if verified else 'BLOQUEADO_PERSISTENCIA'
                ),
                'result': pf_result,
                'report': str(report_path) if report_path.is_file() else None,
                'project': (report.get('import') or {}).get('project_name'),
                'effective_reread': reread,
                'rollback': report.get('rollback'),
                'reconstruction': report.get('reconstruction_verification'),
                'convergence_classification': report.get('convergence_classification'),
            }
            row['native_load_contract'] = build_native_load_evidence(
                source_audit=(row.get('source_audit') or {}).get('evidence'),
                source_audit_sha256=(row.get('source_audit') or {}).get('sha256'),
                conversion_result=conversion,
                powerfactory_reports=reports,
            )
            if verified:
                adjustments, studies = _run_native_load_contract(
                    workspace, ctx, config, selected,
                )
                row['native_load_contract'] = build_native_load_evidence(
                    source_audit=(row.get('source_audit') or {}).get('evidence'),
                    source_audit_sha256=(row.get('source_audit') or {}).get('sha256'),
                    conversion_result=conversion,
                    powerfactory_reports=reports,
                    adjustments=adjustments,
                    studies=studies,
                )
                nonblocking = {
                    'OK', 'AVISO_KVAR', 'AVISO_PERSISTENCIA_CORREGIDA',
                    'AVISO_PERSISTENCIA_NO_CORREGIDA',
                }
                row['status'] = (
                    'NATIVE_LOAD_VERIFIED'
                    if row['native_load_contract']['status'] in nonblocking
                    else row['native_load_contract']['status']
                )
            else:
                row['status'] = 'BLOQUEADO_PERSISTENCIA'
        return row
    except Exception as exc:  # noqa: BLE001 - el resumen debe persistir también el bloqueo
        row['status'] = 'BLOQUEADO_DATOS'
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
        contract = row.get('native_load_contract') or {}
        if contract.get('schema_version') != 'igea-dgs-three-source-native-load-v1':
            raise ValueError(f'{mode} no contiene el contrato nativo universal')
        if (contract.get('capacitors') or {}).get('blocks') is not False:
            raise ValueError(f'{mode} intenta bloquear por la potencia reactiva de bancos')
        for balance in contract.get('head_balance') or []:
            kvar = balance.get('kvar_difference') or {}
            if kvar and kvar.get('bloquea') is not False:
                raise ValueError(f'{mode} intenta bloquear por diferencia de kVAR')
        if row.get('status') == 'NATIVE_LOAD_VERIFIED':
            allowed = {
                'OK', 'AVISO_KVAR', 'AVISO_PERSISTENCIA_CORREGIDA',
                'AVISO_PERSISTENCIA_NO_CORREGIDA',
            }
            if contract.get('status') not in allowed:
                raise ValueError(f'{mode} acredita carga nativa con estado {contract.get("status")}')
            if len(((contract.get('source_audit') or {}).get('sha256') or '')) != 64:
                raise ValueError(f'{mode} acredita carga nativa sin hash de auditoría fuente')
            if not contract.get('project_bindings'):
                raise ValueError(f'{mode} acredita carga nativa sin vínculo de proyecto')
            if not (contract.get('load_flow') or {}).get('all_valid'):
                raise ValueError(f'{mode} acredita carga nativa sin ComLdf válido')
            if contract.get('physical_violations'):
                raise ValueError(f'{mode} acredita carga nativa con violaciones físicas')


def run_three_sources(config: AcceptanceConfig) -> dict[str, Any]:
    config.audit_dir.mkdir(parents=True, exist_ok=True)
    sources = [_accept_mode(config, mode) for mode in ('txt', 'mdb', 'vnr')]
    complete_states = ({'NATIVE_LOAD_VERIFIED'} if config.run_powerfactory else {'DGS_READY'})
    summary = {
        'schema_version': 'igea-dgs-three-source-native-load-v1',
        'created_at': time.time(),
        'audit_dir': str(config.audit_dir.resolve()),
        'requested_feeder': config.feeder,
        'requested_feeders': list(config.feeders or ((config.feeder,) if config.feeder else ())),
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
    parser.add_argument('--source-crs', default=None, help='CRS de las coordenadas (EPSG en metros). Por defecto, el del perfil de empresa.')
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
    parser.add_argument('--cabecera', type=Path,
                        help='Libro o carpeta de medición de cabecera del periodo analizado')
    parser.add_argument('--suministros', type=Path)
    parser.add_argument('--clientes', type=Path,
                        help='Libro o carpeta mensual de clientes importantes')
    parser.add_argument('--meter', action='append', default=[], metavar='ALIMENTADOR=MEDIDOR')
    parser.add_argument('--load-tolerance', type=float, default=0.01)
    parser.add_argument('--study-key', action='append', default=[])
    return parser


def _meter_pairs(values: list[str]) -> tuple[tuple[str, str], ...]:
    pairs = []
    for value in values:
        feeder, separator, meter = value.partition('=')
        if not separator or not feeder.strip() or not meter.strip():
            raise ValueError(f'--meter debe ser ALIMENTADOR=MEDIDOR, no {value!r}')
        pairs.append((feeder.strip(), meter.strip()))
    return tuple(pairs)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    args = _parser().parse_args(argv)
    audit_dir = args.audit_dir or ROOT / 'AUDIT' / f'three_source_{time.strftime("%Y%m%d_%H%M%S")}'
    config = AcceptanceConfig(
        audit_dir=audit_dir,
        feeder=(args.feeders or [''])[0],
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
        cabecera=args.cabecera,
        suministros=args.suministros,
        clientes=args.clientes,
        meters_by_feeder=_meter_pairs(args.meter),
        load_tolerance=args.load_tolerance,
        studies=tuple(args.study_key or ('flujo',)),
    )
    summary = run_three_sources(config)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
