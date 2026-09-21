#!/usr/bin/env python3
"""Retry remaining PF acceptance gaps for production_all and merge into results."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from _run_production_pf_batch import OUT, PF_PYTHON, GATE, run_one  # noqa: E402

# Order: FAIL, TIMEOUT, then untested
RETRY_FEEDERS = [
    'IC103',
    'PN209',
    'PN104',
    'SC215',
    'PA218',
    'TM106',
    'AL107',
    'TM101',
    'COH101',
    'SI114',
]
PER_FEEDER_S = int(os.environ.get('PF_PER_FEEDER_S', str(9 * 60)))


def _kill_pf_engines() -> list[str]:
    killed: list[str] = []
    for name in ('PowerFactory.exe', 'DigSILENT.exe'):
        try:
            proc = subprocess.run(
                ['taskkill', '/F', '/IM', name, '/T'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=30,
            )
            if proc.returncode == 0 or 'SUCCESS' in (proc.stdout or '').upper():
                killed.append(name)
        except Exception:
            pass
    time.sleep(2)
    return killed


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    results_path = OUT / 'pf_batch_results.json'
    prev = {}
    if results_path.is_file():
        prev = json.loads(results_path.read_text(encoding='utf-8'))

    # Verify PF import
    env = os.environ.copy()
    env['PYTHONPATH'] = str(PF_PYTHON) + os.pathsep + env.get('PYTHONPATH', '')
    check = subprocess.run(
        [sys.executable, '-c', 'import powerfactory; print("pf_ok")'],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if check.returncode != 0 or 'pf_ok' not in (check.stdout or ''):
        print('ABORT: powerfactory not importable', check.stdout, check.stderr, flush=True)
        return 3

    print(f'Retrying {len(RETRY_FEEDERS)} feeders, timeout={PER_FEEDER_S}s each', flush=True)
    _kill_pf_engines()

    retry_results: list[dict] = []
    for i, feeder in enumerate(RETRY_FEEDERS, 1):
        dgs = OUT / f'{feeder}.dgs'
        geo = OUT / f'{feeder}_geography.json'
        if not dgs.is_file() or not geo.is_file():
            res = {
                'feeder': feeder,
                'returncode': -1,
                'powerfactory_runtime_pass': False,
                'errors': ['missing dgs/geography'],
                'timed_out': False,
                'elapsed_s': 0,
                'retry': True,
            }
            retry_results.append(res)
            print(f'[{i}/{len(RETRY_FEEDERS)}] {feeder} MISSING FILES', flush=True)
            continue

        print(f'[{i}/{len(RETRY_FEEDERS)}] PF gate {feeder} timeout={PER_FEEDER_S}s', flush=True)
        res = run_one(feeder, dgs, geo, PER_FEEDER_S)
        res['retry'] = True
        res['retry_utc'] = datetime.now(timezone.utc).isoformat()

        if res.get('timed_out') or res.get('killed'):
            killed = _kill_pf_engines()
            res['killed_engines'] = killed
            print(f'  killed engines after hang: {killed}', flush=True)

        # Extra IC103 detail from acceptance JSON if LDF fail
        if feeder == 'IC103' and not res.get('powerfactory_runtime_pass'):
            jpath = OUT / f'{feeder}_powerfactory_acceptance.json'
            detail = {}
            if jpath.is_file():
                try:
                    rep = json.loads(jpath.read_text(encoding='utf-8'))
                    lf = rep.get('load_flow') or {}
                    loop = rep.get('load_flow_loop') or {}
                    detail = {
                        'ldf_return_code': lf.get('return_code'),
                        'ldf_valid': lf.get('ldf_valid'),
                        'ldf_attempts': lf.get('attempts'),
                        'errors': list(rep.get('errors') or [])[:20],
                        'warnings': list(rep.get('warnings') or [])[:12],
                        'load_flow_loop_pass': loop.get('pass'),
                        'last_attempt': (loop.get('attempts') or [None])[-1],
                        'connectivity_pass': rep.get('connectivity_pass'),
                        'location_scale_pass': rep.get('location_scale_pass'),
                        'equipment_pass': rep.get('equipment_pass'),
                        'geographic_diagram_pass': rep.get('geographic_diagram_pass'),
                    }
                except Exception as exc:  # noqa: BLE001
                    detail = {'parse_error': str(exc)}
            res['ic103_ldf_detail'] = detail
            detail_path = OUT / 'IC103_ldf_retry_detail.json'
            detail_path.write_text(
                json.dumps({'feeder': 'IC103', 'retry_result': res, 'detail': detail}, indent=2),
                encoding='utf-8',
            )
            print(f'  IC103 detail written -> {detail_path}', flush=True)

        retry_results.append(res)
        status = 'PASS' if res['powerfactory_runtime_pass'] else ('TIMEOUT' if res['timed_out'] else 'FAIL')
        print(
            f'  -> {status} conn={res.get("connectivity_pass")} gps={res.get("location_scale_pass")} '
            f'ldf={res.get("convergence_pass")} {res["elapsed_s"]}s rc={res.get("returncode")}',
            flush=True,
        )

        # Incremental retry log
        (OUT / 'pf_retry_gaps_results.json').write_text(
            json.dumps(
                {
                    'started_utc': started,
                    'in_progress': True,
                    'per_feeder_timeout_s': PER_FEEDER_S,
                    'results': retry_results,
                },
                indent=2,
            ),
            encoding='utf-8',
        )

    # Merge into pf_batch_results.json (replace prior entries for same feeder)
    old_results = list(prev.get('results') or [])
    by_name = {r['feeder']: r for r in old_results}
    for r in retry_results:
        by_name[r['feeder']] = r
    merged = list(by_name.values())
    # Preserve original order where possible, append new
    ordered: list[dict] = []
    seen = set()
    for r in old_results:
        f = r['feeder']
        if f in by_name and f not in seen:
            ordered.append(by_name[f])
            seen.add(f)
    for r in retry_results:
        if r['feeder'] not in seen:
            ordered.append(r)
            seen.add(r['feeder'])

    tested = {r['feeder'] for r in ordered}
    # Previously not tested minus those now tested
    prev_not = list(prev.get('not_pf_tested') or [])
    not_pf = [f for f in prev_not if f not in tested]
    # Also any convertible still missing? leave as prev residual only

    summary = {
        'started_utc': prev.get('started_utc') or started,
        'ended_utc': datetime.now(timezone.utc).isoformat(),
        'retry_started_utc': started,
        'budget_s': prev.get('budget_s'),
        'per_feeder_timeout_s': PER_FEEDER_S,
        'elapsed_s': prev.get('elapsed_s'),
        'pf_import_ok': True,
        'priority_order': prev.get('priority_order'),
        'results': ordered,
        'not_pf_tested': not_pf,
        'retry_feeders': RETRY_FEEDERS,
        'retry_results': retry_results,
        'summary': {
            'candidates': prev.get('summary', {}).get('candidates', len(ordered)),
            'tested': len(ordered),
            'pass': sum(1 for r in ordered if r.get('powerfactory_runtime_pass')),
            'fail': sum(
                1 for r in ordered
                if not r.get('powerfactory_runtime_pass') and not r.get('timed_out')
            ),
            'timeout': sum(1 for r in ordered if r.get('timed_out')),
            'convergence_pass': sum(1 for r in ordered if r.get('convergence_pass')),
            'connectivity_pass': sum(1 for r in ordered if r.get('connectivity_pass')),
            'not_pf_tested': len(not_pf),
        },
    }
    results_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (OUT / 'pf_retry_gaps_results.json').write_text(
        json.dumps(
            {
                'started_utc': started,
                'ended_utc': summary['ended_utc'],
                'in_progress': False,
                'per_feeder_timeout_s': PER_FEEDER_S,
                'results': retry_results,
                'merged_summary': summary['summary'],
            },
            indent=2,
        ),
        encoding='utf-8',
    )
    s = summary['summary']
    print(
        f"RETRY DONE tested_total={s['tested']} pass={s['pass']} fail={s['fail']} "
        f"timeout={s['timeout']} not_tested={s['not_pf_tested']}",
        flush=True,
    )
    for r in retry_results:
        st = 'PASS' if r.get('powerfactory_runtime_pass') else ('TIMEOUT' if r.get('timed_out') else 'FAIL')
        print(f"  retry {r['feeder']}: {st}", flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
