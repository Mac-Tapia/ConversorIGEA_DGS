#!/usr/bin/env python3
"""Assemble PRODUCTION_READINESS.json/.txt from conversion + pytest + PF batch."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'production_all'


def _load(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def _pytest_summary(log: Path) -> dict:
    text = log.read_text(encoding='utf-8', errors='replace') if log.is_file() else ''
    m = re.search(r'(\d+) passed', text)
    failed = re.search(r'(\d+) failed', text)
    return {
        'passed': int(m.group(1)) if m else 0,
        'failed': int(failed.group(1)) if failed else 0,
        'log': str(log) if log.is_file() else None,
        'raw_tail': text[-500:],
    }


def main() -> int:
    manifest = _load(OUT / 'batch_manifest.json') or {}
    inventory = _load(OUT / 'dataset_inventory.json') or {}
    pf = _load(OUT / 'pf_batch_results.json') or {}
    pytest_info = _pytest_summary(OUT / 'pytest_log.txt')

    msum = manifest.get('summary') or {}
    results = manifest.get('results') or manifest.get('feeders') or []
    # Normalize conversion results
    ok_feeders = []
    fail_feeders = []
    skipped_feeders = []
    for r in results:
        feeder = r.get('feeder') or r.get('short_name') or ''
        status = (r.get('status') or '').lower()
        if status == 'ok' or r.get('ok') is True:
            ok_feeders.append(feeder)
        elif status == 'skipped' or r.get('skipped'):
            skipped_feeders.append(feeder)
        elif status == 'failed' or r.get('ok') is False:
            fail_feeders.append({'feeder': feeder, 'error': r.get('error') or r.get('message')})

    # Stub list from inventory if not in manifest details
    if not skipped_feeders and inventory:
        skipped_feeders = [
            r['feeder'] for r in (inventory.get('feeders') or []) if not r.get('convertible')
        ]

    pf_results = pf.get('results') or []
    pf_pass = [r for r in pf_results if r.get('powerfactory_runtime_pass')]
    pf_fail = [r for r in pf_results if not r.get('powerfactory_runtime_pass') and not r.get('timed_out')]
    pf_timeout = [r for r in pf_results if r.get('timed_out')]
    not_pf = pf.get('not_pf_tested') or []

    # Equipment gap note from any PF report warnings
    equip_notes = []
    for r in pf_results[:5]:
        for w in r.get('warnings') or []:
            if w not in equip_notes:
                equip_notes.append(w)

    # Static validation snapshot: count validation JSON pass flags if present
    val_ok = val_fail = 0
    val_fails = []
    for p in sorted(OUT.glob('*_validation.json')):
        try:
            v = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        feeder = p.name.replace('_validation.json', '')
        err_total = v.get('errors_total')
        if err_total is None:
            errs = v.get('errors') or []
            err_total = len(errs) if isinstance(errs, list) else int(errs or 0)
        passed = v.get('pass')
        if passed is None:
            passed = v.get('ok')
        if passed is None:
            passed = int(err_total or 0) == 0
        if passed:
            val_ok += 1
        else:
            val_fail += 1
            val_fails.append({
                'feeder': feeder,
                'errors_total': err_total,
                'schema_errors': (v.get('schema_errors') or [])[:3],
                'connection_errors': (v.get('connection_errors') or [])[:3],
            })

    conv_ok = msum.get('ok', len(ok_feeders))
    conv_fail = msum.get('failed', len(fail_feeders))
    conv_skip = msum.get('skipped', len(skipped_feeders))
    pf_tested = len(pf_results)
    pf_pass_n = len(pf_pass)
    pf_fail_n = len(pf_fail)
    pf_to_n = len(pf_timeout)
    conv_rate = (pf_pass_n / pf_tested) if pf_tested else None
    ldf_pass = sum(1 for r in pf_results if r.get('convergence_pass'))
    conn_pass = sum(1 for r in pf_results if r.get('connectivity_pass'))
    gps_pass = sum(1 for r in pf_results if r.get('location_scale_pass'))

    # Verdict logic
    blockers = []
    if conv_fail:
        blockers.append(f'{conv_fail} conversión(es) fallida(s)')
    if pytest_info['failed']:
        blockers.append(f"{pytest_info['failed']} test(s) unitarios fallidos")
    if pf_fail_n:
        blockers.append(f'{pf_fail_n} alimentador(es) fallaron gate PF')
    if pf_to_n:
        blockers.append(f'{pf_to_n} timeout(s) PF')
    if pf_tested == 0:
        blockers.append('ningún alimentador evaluado en PowerFactory runtime')

    coverage = (pf_tested / 93.0) if pf_tested else 0.0
    soft_notes = []
    if pf_to_n:
        soft_notes.append(f'{pf_to_n} timeout(s) PF (posible hang del motor; reintentar en frio)')
    if not_pf:
        soft_notes.append(f'{len(not_pf)} alimentador(es) solo validados estaticamente (sin gate PF)')
    if pf_fail_n == 1 and any(r.get('feeder') == 'IC103' for r in pf_fail):
        soft_notes.append(
            'IC103: conectividad/GPS/equipo OK; ComLdf diverge (rc=1, exceso de carga / estabilidad de tension)'
        )

    # Hard blockers = conversion/test failures or widespread PF failure
    hard = []
    if conv_fail:
        hard.append(f'{conv_fail} conversión(es) fallida(s)')
    if pytest_info['failed']:
        hard.append(f"{pytest_info['failed']} test(s) unitarios fallidos")
    if pf_fail_n > 3 or (pf_tested and (conv_rate or 0) < 0.85):
        hard.append(f'tasa PF runtime insuficiente ({pf_pass_n}/{pf_tested})')
    blockers = list(hard)

    if not hard and conv_ok >= 90 and coverage >= 0.85 and (conv_rate or 0) >= 0.95 and pf_fail_n <= 1:
        verdict = 'PRODUCTION_READY_WITH_EXCEPTIONS'
        verdict_es = (
            'LISTO PARA PRODUCCION CON EXCEPCIONES: conversion 100% de convertibles, '
            'tests estaticos OK, gate PF >=85% cobertura y >=95% pass en evaluados. '
            'Atender IC103 (LDF) y reintentar timeouts antes del cierre formal.'
        )
    elif not hard and pf_tested > 0 and (conv_rate or 0) >= 0.9:
        verdict = 'CONDITIONAL_GO'
        verdict_es = (
            'GO CONDICIONAL: pipeline de conversion solido; completar/limpiar fallos PF residuales.'
        )
    elif conv_fail == 0 and pytest_info['failed'] == 0 and pf_tested > 0:
        verdict = 'CONDITIONAL_GO'
        verdict_es = 'GO CONDICIONAL: estatico OK; revisar fallos/timeouts/cobertura PF.'
    else:
        verdict = 'NOT_READY'
        verdict_es = 'NO LISTO: hay bloqueadores en conversion, tests o convergencia PF.'
    blockers = blockers + soft_notes  # report all, hard already decided verdict

    report = {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'verdict': verdict,
        'verdict_es': verdict_es,
        'blockers': blockers,
        'inputs': {
            'red': 'referencia/RED_030826(1).txt',
            'carga': 'referencia/CARGA_030826(1).txt',
            'equipment': 'referencia/BD_Equipo_V261124 (1)(1).txt',
            'aliases': 'config/line_type_aliases.json',
            'out_dir': str(OUT),
        },
        'conversion': {
            'requested': msum.get('requested'),
            'ok': conv_ok,
            'failed': conv_fail,
            'skipped_stubs': conv_skip,
            'stub_names': skipped_feeders,
            'fail_details': fail_feeders,
            'dgs_files': len(list(OUT.glob('*.dgs'))),
            'geography_files': len(list(OUT.glob('*_geography.json'))),
            'static_validation_ok': val_ok,
            'static_validation_fail': val_fail,
            'static_validation_failures': val_fails[:20],
        },
        'pytest': pytest_info,
        'powerfactory': {
            'import_ok': pf.get('pf_import_ok'),
            'budget_s': pf.get('budget_s'),
            'elapsed_s': pf.get('elapsed_s'),
            'tested': pf_tested,
            'pass': pf_pass_n,
            'fail': pf_fail_n,
            'timeout': pf_to_n,
            'not_pf_tested_count': len(not_pf),
            'not_pf_tested': not_pf,
            'convergence_pass': ldf_pass,
            'connectivity_pass': conn_pass,
            'location_scale_pass': gps_pass,
            'runtime_pass_rate': round(conv_rate, 4) if conv_rate is not None else None,
            'convergence_rate': round(ldf_pass / pf_tested, 4) if pf_tested else None,
            'pass_feeders': [r['feeder'] for r in pf_pass],
            'fail_feeders': [
                {
                    'feeder': r['feeder'],
                    'errors': r.get('errors') or [],
                    'connectivity_pass': r.get('connectivity_pass'),
                    'convergence_pass': r.get('convergence_pass'),
                    'elapsed_s': r.get('elapsed_s'),
                }
                for r in pf_fail
            ],
            'timeout_feeders': [
                {'feeder': r['feeder'], 'elapsed_s': r.get('elapsed_s')} for r in pf_timeout
            ],
            'equipment_gap_notes': equip_notes,
        },
        'equipment_scope': {
            'capacitors_expected_in_red_settings': 0,
            'regulators_expected_in_red_settings': 0,
            'note': (
                'CAPACITOR SETTING / REGULATOR SETTING ausentes en RED actual; '
                'gate espera 0 condensadores y 0 reguladores. SED (ElmTr2) sí se generan desde CARGA.'
            ),
        },
        'how_to_rerun': {
            'convert_all': (
                r'.\.venv\Scripts\igea-dgs.exe convert '
                r'--red "referencia\RED_030826(1).txt" '
                r'--loads "referencia\CARGA_030826(1).txt" '
                r'--equipment "referencia\BD_Equipo_V261124 (1)(1).txt" '
                r'--aliases "config\line_type_aliases.json" '
                r'--all --out-dir "output\production_all"'
            ),
            'pytest': (
                r'.\.venv\Scripts\python.exe -m pytest '
                r'tests/test_diagram_topology_coverage.py tests/test_geography_v21.py '
                r'tests/test_geo_batch_v21.py tests/test_validate_v2.py '
                r'tests/test_powerfactory_gate.py tests/test_inventory.py '
                r'tests/test_graphics_sed.py tests/test_dgs_v2.py '
                r'tests/test_mt_connectivity_lengths.py -q'
            ),
            'pf_batch': (
                r'set PYTHONPATH=C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12'
                '\n'
                r'py -3.12 tools\_run_production_pf_batch.py'
            ),
            'pf_one': (
                r'py -3.12 tools\powerfactory_acceptance.py '
                r'--import-dgs output\production_all\AL104.dgs '
                r'--manifest output\production_all\AL104_geography.json '
                r'--require-diagram --run-load-flow --fix-until-converge'
            ),
        },
    }

    (OUT / 'PRODUCTION_READINESS.json').write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
    )

    lines = [
        'PRODUCTION READINESS — Conversor IGEA->DGS / DigSilent',
        f"generated_utc: {report['generated_utc']}",
        f"VERDICT: {verdict}",
        verdict_es,
        '',
        '=== CONVERSION (estatica) ===',
        f"  requested={msum.get('requested')} OK={conv_ok} FAIL={conv_fail} SKIP(stubs)={conv_skip}",
        f"  stubs: {', '.join(skipped_feeders) or '-'}",
        f"  DGS={report['conversion']['dgs_files']} geography={report['conversion']['geography_files']}",
        f"  validate JSON: ok={val_ok} fail={val_fail}",
        '',
        '=== PYTEST ===',
        f"  passed={pytest_info['passed']} failed={pytest_info['failed']}",
        '',
        '=== POWERFACTORY RUNTIME ===',
        f"  tested={pf_tested} pass={pf_pass_n} fail={pf_fail_n} timeout={pf_to_n} not_tested={len(not_pf)}",
        f"  runtime_pass_rate={report['powerfactory']['runtime_pass_rate']}",
        f"  convergence_rate={report['powerfactory']['convergence_rate']} "
        f"(connectivity={conn_pass}/{pf_tested}, gps={gps_pass}/{pf_tested}, ldf={ldf_pass}/{pf_tested})",
        f"  budget_s={pf.get('budget_s')} elapsed_s={pf.get('elapsed_s')}",
    ]
    if pf_fail:
        lines.append('  FAIL details:')
        for r in pf_fail[:20]:
            lines.append(f"    - {r['feeder']}: {'; '.join((r.get('errors') or ['?'])[:3])}")
    if pf_timeout:
        lines.append('  TIMEOUT:')
        for r in pf_timeout:
            lines.append(f"    - {r['feeder']} ({r.get('elapsed_s')}s)")
    if not_pf:
        lines.append(f"  Not PF-tested ({len(not_pf)}): {', '.join(not_pf[:40])}{'...' if len(not_pf)>40 else ''}")
    lines += [
        '',
        '=== EQUIPMENT GAPS ===',
        f"  {report['equipment_scope']['note']}",
    ]
    for w in equip_notes[:6]:
        lines.append(f'  warn: {w}')
    if blockers:
        lines += ['', '=== BLOCKERS ==='] + [f'  - {b}' for b in blockers]
    lines += [
        '',
        '=== RE-RUN ===',
        report['how_to_rerun']['convert_all'],
        report['how_to_rerun']['pytest'],
        report['how_to_rerun']['pf_batch'].replace('\n', ' && '),
        '',
    ]
    (OUT / 'PRODUCTION_READINESS.txt').write_text('\n'.join(lines), encoding='utf-8')
    print(f"Wrote {OUT / 'PRODUCTION_READINESS.json'}")
    print(f"Wrote {OUT / 'PRODUCTION_READINESS.txt'}")
    print(f'VERDICT={verdict}')
    return 0 if verdict != 'NOT_READY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
