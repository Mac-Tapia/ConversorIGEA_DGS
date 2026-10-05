from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[1] / 'tools' / 'accept_load_batch.py'
    spec = importlib.util.spec_from_file_location('accept_load_batch', path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generic_acceptance_records_order_hashes_and_isolated_rollback(tmp_path):
    mod = _module()
    workbook = tmp_path / 'mixed.csv'
    workbook.write_text(
        'alimentador,sed,Kw,Kvar\nF-A,SED-A,120,30\nF-B,SED-B,80,20\n',
        encoding='utf-8',
    )

    summary = mod.run_dry_acceptance(
        audit_dir=tmp_path / 'audit', project='UTILITY_PROJECT',
        feeders=['F-A', 'F-B'], update_file=workbook, fail_feeder='F-B',
    )

    assert summary['evidence_level'] == 'SIMULATED_CONTRACT_ONLY'
    assert summary['project'] == 'UTILITY_PROJECT'
    assert summary['ordered_feeders'] == ['F-A', 'F-B']
    assert summary['inputs'][0]['sha256']
    assert [r['status'] for r in summary['feeders']] == ['APPLIED', 'ROLLED_BACK']
    assert summary['feeders'][0]['after']['SED-A']['kw'] == 120.0
    assert summary['feeders'][1]['rollback']['status'] == 'RESTORED'
    assert summary['feeders'][1]['comldf']['converged'] is False
    persisted = json.loads((tmp_path / 'audit' / 'acceptance_summary.json').read_text('utf-8'))
    assert persisted == summary


def test_real_mode_without_powerfactory_is_an_explicit_blocker(tmp_path, monkeypatch):
    mod = _module()
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'project': 'UTILITY_PROJECT', 'feeders': []}), encoding='utf-8')
    monkeypatch.setattr(mod.subprocess, 'run', lambda *a, **k: type('R', (), {'returncode': 3})())

    summary = mod.run_real_acceptance(tmp_path / 'audit', plan)

    assert summary['status'] == 'BLOCKED_POWERFACTORY_UNAVAILABLE'
    assert summary['evidence_level'] == 'REAL_ENGINE_NOT_VERIFIED'
    assert summary['returncode'] == 3
