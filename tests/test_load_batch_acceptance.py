from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


PATH = Path(__file__).parents[1] / 'tools' / 'load_batch_acceptance.py'
SPEC = importlib.util.spec_from_file_location('load_batch_acceptance', PATH)
assert SPEC and SPEC.loader
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


class Load:
    def __init__(self):
        self.value = 10.0


class FakeEngine:
    def __init__(self):
        self.load = Load()
        self.restored = 0
        self.calls = 0

    def resolve_feeder_loads(self, _app, _project, _plan):
        return {'project': object(), 'objects': {'SE01': self.load}, 'errors': []}

    def snapshot_load(self, obj):
        return {'value': obj.value}

    def apply_feeder_transaction(self, _app, feeder_plan, *, dry_run):
        assert not dry_run
        self.calls += 1
        self.load.value = feeder_plan['updates'][0]['plini_mw']
        return {'feeder': feeder_plan['feeder'], 'status': 'PASS', 'written': 1}

    def restore_load(self, obj, snapshot):
        self.restored += 1
        obj.value = snapshot['value']

    def run_load_flow(self, _app):
        return {'return_code': 0, 'ldf_valid': True, 'converged': True}


def plan_file(tmp_path: Path, project='IGEA_DGS_CONVERTER_AL209') -> Path:
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps({
        'batch_id': 'batch-test',
        'feeders': [{
            'feeder': 'AL209', 'network_id': 'NETWORK_AL209', 'project_name': project,
            'updates': [{'sed_code': 'SE01', 'plini_mw': 20.0, 'qlini_mvar': 4.0}],
        }],
    }), encoding='utf-8')
    return path


def test_acceptance_requires_dedicated_projects(tmp_path):
    with pytest.raises(ValueError, match='IGEA_DGS_CONVERTER_'):
        acceptance.run_acceptance(
            plan_file(tmp_path, project='PRODUCCION_AL209'), app=object(), engine=FakeEngine(),
        )


def test_acceptance_always_requests_restore(tmp_path):
    with pytest.raises(ValueError, match='restaur'):
        acceptance.run_acceptance(
            plan_file(tmp_path), restore_originals=False, app=object(), engine=FakeEngine(),
        )


def test_acceptance_report_proves_values_were_restored(tmp_path):
    engine = FakeEngine()

    report = acceptance.run_acceptance(
        plan_file(tmp_path), app=object(), engine=engine,
        output_path=tmp_path / 'acceptance.json',
    )

    assert report['status'] == 'PASS'
    assert report['application']['feeders'][0]['status'] == 'PASS'
    assert report['restoration']['feeders'][0]['restored'] is True
    assert report['restoration']['feeders'][0]['load_flow']['converged'] is True
    assert engine.load.value == 10.0
    assert engine.restored == 1
    assert (tmp_path / 'acceptance.json').is_file()
