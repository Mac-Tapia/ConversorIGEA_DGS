"""Custody and optimistic-version contract for multi-feeder load plans."""

from __future__ import annotations

from pathlib import Path

import pytest


def _workspace(tmp_path):
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='load-batch', root=tmp_path / 'workspace')
    ws.active_run_id = ws.loaded_run_id = 'run-1'
    ws.loaded_source_mode = 'txt'
    ws.loaded_source_fingerprint = 'f' * 64
    ws.pf_inventory = {
        'projects': [{'name': 'UTILITY_PROJECT', 'feeders': ['F-A', 'F-B']}],
        'revision': 'pf-rev-1',
    }
    return ws


def _create(ws, tmp_path, *, errors=()):
    from igea_dgs.web.load_batch import create_load_batch_plan

    update = tmp_path / 'mixed-loads.xlsx'
    create = tmp_path / 'new-sed.csv'
    update.write_bytes(b'update-v1')
    create.write_bytes(b'create-v1')
    payload = {
        'project': 'UTILITY_PROJECT',
        'feeders': [
            {'feeder': 'F-B', 'update': {'updates': []}, 'create': None},
            {'feeder': 'F-A', 'update': None, 'create': {'create': []}},
        ],
        'run_load_flow': True,
    }
    return create_load_batch_plan(
        ws, 'UTILITY_PROJECT', ['F-B', 'F-A'], update, create, {'currency': 'USD'},
        payload=payload,
        feeders_summary=[{'feeder': 'F-B'}, {'feeder': 'F-A'}],
        row_errors=list(errors),
    )


def test_plan_custodies_books_hashes_and_preserves_order(tmp_path):
    from igea_dgs.web.load_batch import require_current_load_batch_plan

    ws = _workspace(tmp_path)
    response = _create(ws, tmp_path)
    plan = require_current_load_batch_plan(ws, response['token'])

    assert plan.feeders == ('F-B', 'F-A')
    assert plan.project == 'UTILITY_PROJECT'
    assert plan.source_run_id == 'run-1'
    assert plan.source_fingerprint == 'f' * 64
    assert plan.applicable is True
    assert [item.slot for item in plan.inputs] == ['update', 'create']
    assert all(len(item.sha256) == 64 and Path(item.path).is_file() for item in plan.inputs)
    assert Path(response['plan_path']).is_file()
    assert response['order'] == ['F-B', 'F-A']


def test_plan_with_row_errors_is_not_applicable(tmp_path):
    ws = _workspace(tmp_path)
    response = _create(ws, tmp_path, errors=['F-B: duplicate SED'])
    assert response['applicable'] is False
    assert response['row_errors'] == ['F-B: duplicate SED']


@pytest.mark.parametrize('mutation', ['run', 'project', 'custody'])
def test_changed_identity_invalidates_plan_before_apply(tmp_path, mutation):
    from igea_dgs.web.load_batch import LoadBatchPlanStale, require_current_load_batch_plan

    ws = _workspace(tmp_path)
    response = _create(ws, tmp_path)
    if mutation == 'run':
        ws.active_run_id = 'run-2'
    elif mutation == 'project':
        ws.pf_inventory['revision'] = 'pf-rev-2'
    else:
        plan = ws.plans[response['token']]
        Path(plan['input_paths']['update']).write_bytes(b'tampered')

    with pytest.raises(LoadBatchPlanStale, match='LOAD_BATCH_PLAN_STALE'):
        require_current_load_batch_plan(ws, response['token'])


def test_token_and_published_plan_are_immutable_snapshots(tmp_path):
    from igea_dgs.web.load_batch import require_current_load_batch_plan

    ws = _workspace(tmp_path)
    first = _create(ws, tmp_path)
    second = _create(ws, tmp_path)
    assert first['token'] != second['token']
    plan = require_current_load_batch_plan(ws, first['token'])
    with pytest.raises((AttributeError, TypeError)):
        plan.project = 'CHANGED'
