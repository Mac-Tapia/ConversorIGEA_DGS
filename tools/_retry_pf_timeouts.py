#!/usr/bin/env python3
"""Retry timed-out PF gates and optionally continue untested feeders."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from _run_production_pf_batch import OUT, build_priority, run_one  # noqa: E402

BUDGET_S = int(os.environ.get('PF_RETRY_BUDGET_S', '1200'))  # 20 min
PER_S = int(os.environ.get('PF_PER_FEEDER_S', '600'))  # 10 min


def main() -> int:
    batch_path = OUT / 'pf_batch_results.json'
    batch = json.loads(batch_path.read_text(encoding='utf-8'))
    results = list(batch.get('results') or [])
    by_feeder = {r['feeder']: r for r in results}

    timeouts = [r['feeder'] for r in results if r.get('timed_out')]
    not_tested = list(batch.get('not_pf_tested') or [])
    order_rows = {r['feeder']: r for r in build_priority(OUT)}

    # Retry timeouts first, then continue not_tested in priority order
    queue = []
    for f in timeouts:
        if f in order_rows and order_rows[f]['has_files']:
            queue.append(order_rows[f])
    for f in not_tested:
        if f in order_rows and order_rows[f]['has_files']:
            queue.append(order_rows[f])

    t0 = time.perf_counter()
    print(f'Retry/continue queue={len(queue)} budget={BUDGET_S}s per={PER_S}s', flush=True)
    print(f'Timeouts to retry: {timeouts}', flush=True)

    for i, row in enumerate(queue, 1):
        remaining = BUDGET_S - (time.perf_counter() - t0)
        if remaining < 90:
            print(f'Stop retry budget remaining={remaining:.0f}s', flush=True)
            break
        feeder = row['feeder']
        timeout = min(PER_S, max(60, int(remaining - 20)))
        print(f'[retry {i}/{len(queue)}] {feeder} timeout={timeout}s', flush=True)
        res = run_one(feeder, Path(row['dgs']), Path(row['geography']), timeout)
        by_feeder[feeder] = res
        status = 'PASS' if res['powerfactory_runtime_pass'] else ('TIMEOUT' if res['timed_out'] else 'FAIL')
        print(
            f'  -> {status} conn={res.get("connectivity_pass")} gps={res.get("location_scale_pass")} '
            f'ldf={res.get("convergence_pass")} {res["elapsed_s"]}s',
            flush=True,
        )
        # rewrite results list preserving order of first appearance + new
        seen = []
        merged = []
        for r in results:
            f = r['feeder']
            if f in by_feeder and f not in seen:
                merged.append(by_feeder[f])
                seen.append(f)
        for f, r in by_feeder.items():
            if f not in seen:
                merged.append(r)
                seen.append(f)
        results = merged
        tested = {r['feeder'] for r in results}
        not_pf = [r['feeder'] for r in build_priority(OUT) if r['feeder'] not in tested]
        summary = {
            'started_utc': batch.get('started_utc'),
            'ended_utc': datetime.now(timezone.utc).isoformat(),
            'budget_s': batch.get('budget_s'),
            'retry_budget_s': BUDGET_S,
            'per_feeder_timeout_s': PER_S,
            'elapsed_s': round((batch.get('elapsed_s') or 0) + (time.perf_counter() - t0), 1),
            'pf_import_ok': True,
            'priority_order': batch.get('priority_order'),
            'results': results,
            'not_pf_tested': not_pf,
            'retry_pass': True,
            'summary': {
                'candidates': 93,
                'tested': len(results),
                'pass': sum(1 for r in results if r.get('powerfactory_runtime_pass')),
                'fail': sum(
                    1 for r in results
                    if not r.get('powerfactory_runtime_pass') and not r.get('timed_out')
                ),
                'timeout': sum(1 for r in results if r.get('timed_out')),
                'convergence_pass': sum(1 for r in results if r.get('convergence_pass')),
                'connectivity_pass': sum(1 for r in results if r.get('connectivity_pass')),
                'not_pf_tested': len(not_pf),
            },
        }
        batch_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')

    s = json.loads(batch_path.read_text(encoding='utf-8'))['summary']
    print(
        f"DONE retry tested={s['tested']} pass={s['pass']} fail={s['fail']} "
        f"timeout={s['timeout']} not_tested={s['not_pf_tested']}",
        flush=True,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
