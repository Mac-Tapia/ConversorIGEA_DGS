#!/usr/bin/env python3
"""Audited acceptance for universal multi-feeder load batches.

``--dry-run`` validates the evidence contract without PowerFactory.  It is never
reported as real persistence.  ``--real-plan`` invokes the production applicator
and classifies API/startup failures explicitly.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def run_dry_acceptance(
    audit_dir: Path, project: str, feeders: list[str], update_file: Path,
    fail_feeder: str | None = None,
) -> dict[str, Any]:
    """Exercise ordering/evidence/rollback using a generic delimited workbook."""
    rows: dict[str, list[dict[str, str]]] = {name: [] for name in feeders}
    with update_file.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            feeder = (row.get('alimentador') or row.get('feeder') or '').strip()
            if feeder in rows:
                rows[feeder].append(row)
    results = []
    for feeder in feeders:
        before: dict[str, dict[str, float]] = {}
        after: dict[str, dict[str, float]] = {}
        for row in rows[feeder]:
            sed = (row.get('sed') or row.get('SED') or '').strip()
            before[sed] = {'kw': 0.0, 'kvar': 0.0, 'fp': 1.0}
            after[sed] = {
                'kw': float(row.get('Kw') or row.get('kw') or 0),
                'kvar': float(row.get('Kvar') or row.get('kvar') or 0),
                'fp': 1.0,
            }
        failed = feeder == fail_feeder
        results.append({
            'feeder': feeder,
            'status': 'ROLLED_BACK' if failed else 'APPLIED',
            'before': before,
            'after': after,
            'created': [],
            'comldf': {'return_code': 1 if failed else 0, 'ldf_valid': not failed,
                       'converged': not failed},
            'rollback': {'attempted': failed, 'status': 'RESTORED' if failed else 'NOT_REQUIRED',
                         'containers_deleted': [f'Cargas_{feeder}'] if failed else [], 'errors': []},
        })
    summary = {
        'status': 'PASS_SIMULATED_CONTRACT',
        'evidence_level': 'SIMULATED_CONTRACT_ONLY',
        'project': project,
        'ordered_feeders': feeders,
        'inputs': [{'path': str(update_file.resolve()), 'sha256': _sha256(update_file)}],
        'feeders': results,
        'real_persistence_verified': False,
    }
    _write(audit_dir / 'acceptance_summary.json', summary)
    return summary


def run_real_acceptance(audit_dir: Path, plan: Path) -> dict[str, Any]:
    audit_dir.mkdir(parents=True, exist_ok=True)
    report = audit_dir / 'powerfactory_result.json'
    command = [sys.executable, str(ROOT / 'tools' / 'aplicar_lote_cargas.py'),
               '--lote', str(plan), '--output-json', str(report)]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    payload: dict[str, Any] = {}
    if report.is_file():
        try:
            payload = json.loads(report.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            payload = {}
    status = 'PASS_REAL_POWERFACTORY' if completed.returncode == 0 and payload.get('feeders') else (
        'BLOCKED_POWERFACTORY_UNAVAILABLE' if completed.returncode == 3 else 'FAIL_REAL_POWERFACTORY'
    )
    summary = {
        'status': status,
        'evidence_level': 'REAL_ENGINE_REREAD' if status == 'PASS_REAL_POWERFACTORY'
                          else 'REAL_ENGINE_NOT_VERIFIED',
        'returncode': completed.returncode,
        'plan': str(plan.resolve()),
        'plan_sha256': _sha256(plan),
        'report': payload,
        'real_persistence_verified': status == 'PASS_REAL_POWERFACTORY',
    }
    _write(audit_dir / 'acceptance_summary.json', summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit-dir', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--real-plan', type=Path)
    parser.add_argument('--project', default='UTILITY_PROJECT')
    parser.add_argument('--feeder', action='append', default=[])
    parser.add_argument('--update-file', type=Path)
    parser.add_argument('--fail-feeder')
    args = parser.parse_args()
    if args.dry_run:
        if not args.update_file or not args.feeder:
            parser.error('--dry-run requires --update-file and at least one --feeder')
        result = run_dry_acceptance(args.audit_dir, args.project, args.feeder,
                                    args.update_file, args.fail_feeder)
    else:
        result = run_real_acceptance(args.audit_dir, args.real_plan)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result['status'].startswith('PASS') else 2


if __name__ == '__main__':
    raise SystemExit(main())
