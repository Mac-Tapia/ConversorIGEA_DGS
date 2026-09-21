#!/usr/bin/env python3
"""Batch PowerFactory acceptance for production_all DGS files.

Prioritizes known-critical / double-circuit / large feeders, applies a global
time budget, and kills hung per-feeder subprocesses.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'production_all'
PF_PYTHON = Path(r'C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12')
GATE = ROOT / 'tools' / 'powerfactory_acceptance.py'

# Soft budget for the whole PF campaign (seconds). Leave headroom for report.
DEFAULT_BUDGET_S = 50 * 60
# Hard kill per feeder if PF hangs
DEFAULT_PER_FEEDER_TIMEOUT_S = 8 * 60
PRIORITY_NAMES = [
    'AL104', 'AL105', 'AL209', 'IN111', 'IN112', 'CHI201', 'CA101', 'LL203',
    'NA205', 'SI113', 'AL108', 'IC107', 'CA105', 'LL204', 'IN113',
]


def _endpoint_key(sec: dict) -> tuple[str, str]:
    a, b = sec.get('FromNodeID', ''), sec.get('ToNodeID', '')
    return tuple(sorted((a, b)))


def build_priority(out_dir: Path) -> list[dict]:
    sys.path.insert(0, str(ROOT / 'src'))
    from igea_dgs.dataset import CymdistDataset
    from igea_dgs.inventory import build_dataset_inventory

    ds = CymdistDataset.from_files(
        ROOT / 'referencia' / 'RED_030826(1).txt',
        ROOT / 'referencia' / 'CARGA_030826(1).txt',
        ROOT / 'referencia' / 'BD_Equipo_V261124 (1)(1).txt',
    )
    inv = build_dataset_inventory(ds)
    convertible = [r for r in inv['feeders'] if r['convertible']]
    rows: list[dict] = []
    for r in convertible:
        nid = r['network_id']
        ends: Counter[tuple[str, str]] = Counter()
        for sid in ds.feeders[nid]:
            ends[_endpoint_key(ds.sections[sid])] += 1
        doubles = sum(1 for c in ends.values() if c >= 2)
        feeder = r['feeder']
        dgs = out_dir / f'{feeder}.dgs'
        geo = out_dir / f'{feeder}_geography.json'
        rows.append({
            'feeder': feeder,
            'sections': r['sections'],
            'loads': r['loads'],
            'doubles': doubles,
            'dgs': str(dgs),
            'geography': str(geo),
            'has_files': dgs.is_file() and geo.is_file(),
        })
    prio = {n: i for i, n in enumerate(PRIORITY_NAMES)}
    rows.sort(key=lambda x: (prio.get(x['feeder'], 100), -x['doubles'], -x['sections'], x['feeder']))
    return rows


def _python312() -> str:
    # Prefer py -3.12 launcher when available
    return sys.executable  # caller should invoke with 3.12


def run_one(feeder: str, dgs: Path, geo: Path, timeout_s: int) -> dict:
    env = os.environ.copy()
    pf_path = str(PF_PYTHON)
    env['PYTHONPATH'] = pf_path + os.pathsep + env.get('PYTHONPATH', '')
    env['PATH'] = str(PF_PYTHON.parent.parent) + os.pathsep + env.get('PATH', '')

    json_out = OUT / f'{feeder}_powerfactory_acceptance.json'
    txt_out = OUT / f'{feeder}_powerfactory_acceptance.txt'
    cmd = [
        sys.executable,
        str(GATE),
        '--import-dgs', str(dgs),
        '--manifest', str(geo),
        '--require-diagram',
        '--run-load-flow',
        '--fix-until-converge',
        '--output-json', str(json_out),
        '--output-txt', str(txt_out),
    ]
    t0 = time.perf_counter()
    killed = False
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            encoding='utf-8',
            errors='replace',
        )
        rc = proc.returncode
        stdout = proc.stdout[-4000:] if proc.stdout else ''
        stderr = proc.stderr[-4000:] if proc.stderr else ''
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        killed = True
        rc = -9
        stdout = (exc.stdout or b'')
        stderr = (exc.stderr or b'')
        if isinstance(stdout, bytes):
            stdout = stdout.decode('utf-8', errors='replace')[-4000:]
        if isinstance(stderr, bytes):
            stderr = stderr.decode('utf-8', errors='replace')[-4000:]
        stdout = stdout or ''
        stderr = (stderr or '') + f'\nTIMEOUT after {timeout_s}s — process killed'

    elapsed = time.perf_counter() - t0
    report = None
    if json_out.is_file():
        try:
            report = json.loads(json_out.read_text(encoding='utf-8'))
        except Exception as exc:  # noqa: BLE001
            report = {'parse_error': str(exc)}

    result = {
        'feeder': feeder,
        'returncode': rc,
        'elapsed_s': round(elapsed, 2),
        'timed_out': timed_out,
        'killed': killed,
        'powerfactory_runtime_pass': bool(report and report.get('powerfactory_runtime_pass')),
        'connectivity_pass': (report or {}).get('connectivity_pass'),
        'location_scale_pass': (report or {}).get('location_scale_pass'),
        'equipment_pass': (report or {}).get('equipment_pass'),
        'geographic_diagram_pass': (report or {}).get('geographic_diagram_pass'),
        'convergence_pass': (report or {}).get('convergence_pass'),
        'errors': list((report or {}).get('errors') or [])[:12],
        'warnings': list((report or {}).get('warnings') or [])[:8],
        'stdout_tail': stdout[-1500:],
        'stderr_tail': stderr[-1500:],
        'report_json': str(json_out) if json_out.is_file() else None,
    }
    return result


def main() -> int:
    budget_s = int(os.environ.get('PF_BUDGET_S', DEFAULT_BUDGET_S))
    per_feeder_s = int(os.environ.get('PF_PER_FEEDER_S', DEFAULT_PER_FEEDER_TIMEOUT_S))
    max_feeders = int(os.environ.get('PF_MAX_FEEDERS', '0'))  # 0 = until budget

    OUT.mkdir(parents=True, exist_ok=True)
    order = build_priority(OUT)
    (OUT / 'pf_priority_order.json').write_text(json.dumps(order, indent=2), encoding='utf-8')

    # Verify PF module import with this interpreter
    try:
        env = os.environ.copy()
        env['PYTHONPATH'] = str(PF_PYTHON) + os.pathsep + env.get('PYTHONPATH', '')
        check = subprocess.run(
            [sys.executable, '-c', 'import powerfactory; print("pf_ok", getattr(powerfactory, "__file__", "?"))'],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        pf_import_ok = check.returncode == 0 and 'pf_ok' in (check.stdout or '')
        pf_import_msg = (check.stdout or '') + (check.stderr or '')
    except Exception as exc:  # noqa: BLE001
        pf_import_ok = False
        pf_import_msg = str(exc)

    started = datetime.now(timezone.utc).isoformat()
    t_budget0 = time.perf_counter()
    results: list[dict] = []
    skipped_budget: list[str] = []

    print(f'PF import check: ok={pf_import_ok} msg={pf_import_msg[:200]!r}', flush=True)
    print(f'Budget={budget_s}s per_feeder={per_feeder_s}s candidates={len(order)}', flush=True)
    if not pf_import_ok:
        summary = {
            'started_utc': started,
            'ended_utc': datetime.now(timezone.utc).isoformat(),
            'pf_import_ok': False,
            'pf_import_msg': pf_import_msg,
            'results': [],
            'summary': {'tested': 0, 'pass': 0, 'fail': 0, 'timeout': 0},
        }
        (OUT / 'pf_batch_results.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print('ABORT: powerfactory module not importable with this Python', flush=True)
        return 3

    for i, row in enumerate(order, 1):
        remaining = budget_s - (time.perf_counter() - t_budget0)
        if remaining < 90:
            skipped_budget.extend(r['feeder'] for r in order[i - 1 :])
            print(f'Budget exhausted with {remaining:.0f}s left — stop after {len(results)} tested', flush=True)
            break
        if max_feeders and len(results) >= max_feeders:
            skipped_budget.extend(r['feeder'] for r in order[i - 1 :])
            break
        if not row['has_files']:
            results.append({
                'feeder': row['feeder'],
                'returncode': -1,
                'powerfactory_runtime_pass': False,
                'errors': ['missing dgs/geography'],
                'timed_out': False,
                'elapsed_s': 0,
            })
            continue

        feeder = row['feeder']
        timeout = min(per_feeder_s, max(60, int(remaining - 30)))
        print(
            f'[{i}/{len(order)}] PF gate {feeder} (sec={row["sections"]} doubles={row["doubles"]}) '
            f'timeout={timeout}s remaining_budget={remaining:.0f}s',
            flush=True,
        )
        res = run_one(feeder, Path(row['dgs']), Path(row['geography']), timeout)
        results.append(res)
        status = 'PASS' if res['powerfactory_runtime_pass'] else ('TIMEOUT' if res['timed_out'] else 'FAIL')
        print(
            f'  -> {status} conn={res.get("connectivity_pass")} gps={res.get("location_scale_pass")} '
            f'ldf={res.get("convergence_pass")} {res["elapsed_s"]}s',
            flush=True,
        )
        # Persist incremental results
        partial = {
            'started_utc': started,
            'pf_import_ok': True,
            'results': results,
            'skipped_budget': skipped_budget,
            'in_progress': True,
        }
        (OUT / 'pf_batch_results.json').write_text(json.dumps(partial, indent=2), encoding='utf-8')

    # any not tested after loop break already in skipped_budget; if finished all, empty
    tested = {r['feeder'] for r in results}
    not_tested = [r['feeder'] for r in order if r['feeder'] not in tested]
    if not skipped_budget:
        skipped_budget = not_tested

    summary = {
        'started_utc': started,
        'ended_utc': datetime.now(timezone.utc).isoformat(),
        'budget_s': budget_s,
        'per_feeder_timeout_s': per_feeder_s,
        'elapsed_s': round(time.perf_counter() - t_budget0, 1),
        'pf_import_ok': True,
        'priority_order': [r['feeder'] for r in order],
        'results': results,
        'not_pf_tested': not_tested,
        'summary': {
            'candidates': len(order),
            'tested': len(results),
            'pass': sum(1 for r in results if r.get('powerfactory_runtime_pass')),
            'fail': sum(
                1 for r in results
                if not r.get('powerfactory_runtime_pass') and not r.get('timed_out')
            ),
            'timeout': sum(1 for r in results if r.get('timed_out')),
            'convergence_pass': sum(1 for r in results if r.get('convergence_pass')),
            'connectivity_pass': sum(1 for r in results if r.get('connectivity_pass')),
            'not_pf_tested': len(not_tested),
        },
    }
    (OUT / 'pf_batch_results.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    s = summary['summary']
    print(
        f"DONE tested={s['tested']} pass={s['pass']} fail={s['fail']} "
        f"timeout={s['timeout']} not_tested={s['not_pf_tested']}",
        flush=True,
    )
    return 0 if s['fail'] == 0 and s['timeout'] == 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
