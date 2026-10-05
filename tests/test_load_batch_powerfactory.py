"""Fake-engine tests for per-feeder PowerFactory transaction boundaries."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def _module():
    tools = Path(__file__).resolve().parents[1] / 'tools'
    import sys

    sys.path.insert(0, str(tools))
    try:
        spec = importlib.util.spec_from_file_location('load_batch_pf', tools / 'aplicar_lote_cargas.py')
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(tools))


class Container:
    def __init__(self, name, *, fail_delete=False):
        self.loc_name = name
        self.deleted = False
        self.fail_delete = fail_delete

    def Deactivate(self, *_args):
        return 0

    def Delete(self):
        if self.fail_delete:
            raise RuntimeError('delete failed')
        self.deleted = True
        return 0

    def Save(self):
        return 0


def _patch_parts(monkeypatch, mod, *, converged=True, rollback_failure=False):
    scenario = Container('Cargas_F-A', fail_delete=rollback_failure)
    variation = Container('SED_F-A')

    def update(*_args, **_kwargs):
        return {
            'escenario': scenario.loc_name,
            '_scenario_obj': scenario,
            'applied': 1,
            'not_found': [],
            'ambiguous': [],
            'write_errors': [],
            'changes': [{
                'object': 'SED-1',
                'before': {'plini': 1.0, 'qlini': 0.2, 'coslini': 0.98},
                'after': {'plini': 1.2, 'qlini': 0.3, 'coslini': 0.97},
            }],
        }

    def create(*_args, **_kwargs):
        return {
            'variacion': variation.loc_name,
            '_variation_obj': variation,
            'created': [{'sed_code': 'SED-NEW'}],
            'skipped': [],
            'failed': [],
            'undrawn': [],
        }

    monkeypatch.setattr(mod, '_actualizar', update)
    monkeypatch.setattr(mod, '_crear', create)
    monkeypatch.setattr(
        mod.actualizar,
        'flujo_de_carga',
        lambda _app: {'return_code': 0 if converged else 1,
                      'ldf_valid': converged, 'converged': converged},
    )
    return scenario, variation


def test_apply_feeder_plan_rereads_and_commits_only_after_comldf(monkeypatch):
    mod = _module()
    scenario, variation = _patch_parts(monkeypatch, mod, converged=True)
    entry = {'feeder': 'F-A', 'update': {'updates': [{}]}, 'create': {'create': [{}]}}

    result = mod.apply_feeder_plan(
        SimpleNamespace(), SimpleNamespace(), SimpleNamespace(), SimpleNamespace(),
        entry, 'stamp', {}, True,
    )

    assert result['status'] == 'APPLIED'
    assert result['before']['SED-1']['plini'] == 1.0
    assert result['after']['SED-1']['plini'] == 1.2
    assert result['created'] == ['SED-NEW']
    assert result['comldf']['converged'] is True
    assert result['rollback']['status'] == 'NOT_REQUIRED'
    assert scenario.deleted is False and variation.deleted is False


def test_failed_second_feeder_rolls_back_only_its_containers(monkeypatch):
    mod = _module()
    scenario, variation = _patch_parts(monkeypatch, mod, converged=False)
    entry = {'feeder': 'F-B', 'update': {'updates': [{}]}, 'create': {'create': [{}]}}

    result = mod.apply_feeder_plan(
        SimpleNamespace(), SimpleNamespace(), SimpleNamespace(), SimpleNamespace(),
        entry, 'stamp', {}, True,
    )

    assert result['status'] == 'ROLLED_BACK'
    assert result['comldf']['converged'] is False
    assert scenario.deleted is True and variation.deleted is True
    assert result['rollback']['status'] == 'RESTORED'
    assert set(result['rollback']['containers_deleted']) == {'Cargas_F-A', 'SED_F-A'}


def test_partial_rollback_is_never_reported_as_restored(monkeypatch):
    mod = _module()
    _patch_parts(monkeypatch, mod, converged=False, rollback_failure=True)
    result = mod.apply_feeder_plan(
        SimpleNamespace(), SimpleNamespace(), SimpleNamespace(), SimpleNamespace(),
        {'feeder': 'F-B', 'update': {'updates': [{}]}, 'create': None},
        'stamp', {}, True,
    )
    assert result['status'] == 'ROLLBACK_FAILED'
    assert result['rollback']['status'] == 'PARTIAL'
    assert result['rollback']['errors']


def test_append_only_evidence_survives_before_final_summary(tmp_path):
    mod = _module()
    path = tmp_path / 'batch.evidence.jsonl'
    mod.append_evidence(path, {'feeder': 'F-A', 'status': 'APPLIED'})
    mod.append_evidence(path, {'feeder': 'F-B', 'status': 'ROLLED_BACK'})
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    assert [row['feeder'] for row in rows] == ['F-A', 'F-B']
