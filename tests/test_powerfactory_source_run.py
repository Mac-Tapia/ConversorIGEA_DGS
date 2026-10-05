"""PowerFactory solo puede consumir artefactos de la ejecución fuente activa."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest


def _ws(tmp_path, *, metadata_run: str = 'run-active'):
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='pf-source', root=tmp_path)
    ws.active_run_id = 'run-active'
    ws.loaded_run_id = 'run-active'
    ws.loaded_source_mode = 'txt'
    ws.loaded_source_fingerprint = 'f' * 64
    ws.dataset = SimpleNamespace()
    ws.out_dir.mkdir(parents=True)
    dgs = ws.out_dir / 'IN111.dgs'
    dgs.write_bytes(b'DGS-IN111')
    metadata = {
        'schema_version': 'igea-dgs-feeder-metadata-v1',
        'dgs_file': dgs.name,
        'dgs_sha256': hashlib.sha256(dgs.read_bytes()).hexdigest(),
        'assignments': [{'class_name': 'ElmXnet', 'dgs_fid': 'X', 'loc_name': 'External Grid IN111',
                         'feeder': 'IN111', 'network_id': 'NET_IN111', 'terminal': 'N1',
                         'substation': '', 'section_id': '', 'node_id': 'N1'}],
        'source_run_id': metadata_run,
        'source_mode': 'txt',
        'source_fingerprint': 'f' * 64,
    }
    (ws.out_dir / 'IN111_feeder_metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
    snapshot = SimpleNamespace(
        run_id='run-active', mode='txt', fingerprint='f' * 64,
    )
    ws.active_run = lambda: snapshot
    return ws


def test_same_name_historical_dgs_is_rejected(tmp_path):
    from igea_dgs.web.services import UserError, check_powerfactory_source_run

    ws = _ws(tmp_path, metadata_run='run-historical')
    with pytest.raises(UserError, match=r'POWERFACTORY_SOURCE_RUN_MISMATCH.*IN111'):
        check_powerfactory_source_run(ws, ['IN111'])


def test_exact_active_source_run_is_accepted(tmp_path):
    from igea_dgs.web.services import check_powerfactory_source_run

    ws = _ws(tmp_path)
    evidence = check_powerfactory_source_run(ws, ['IN111'])
    assert evidence['source_run_id'] == 'run-active'
    assert evidence['source_mode'] == 'txt'
    assert evidence['targets'][0]['dgs_sha256']


def test_acceptance_source_contract_runs_before_powerfactory_connect(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / 'tools' / 'powerfactory_acceptance.py'
    spec = importlib.util.spec_from_file_location('pf_acceptance_source', path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    ws = _ws(tmp_path)
    dgs = ws.out_dir / 'IN111.dgs'
    metadata = ws.out_dir / 'IN111_feeder_metadata.json'
    connected = False

    def connect(**_kwargs):
        nonlocal connected
        connected = True
        raise AssertionError('no debe conectar')

    monkeypatch.setattr(module, 'connect_powerfactory', connect)
    rc = module.main([
        '--import-dgs', str(dgs), '--feeder-metadata', str(metadata),
        '--source-run-id', 'otra-ejecucion', '--source-mode', 'txt',
        '--source-fingerprint', 'f' * 64,
    ])
    assert rc == 4
    assert connected is False


def test_assignment_report_proves_plan_identity_reread_and_rollback(tmp_path):
    from igea_dgs.feeder_metadata import FeederAssignment
    from igea_dgs.powerfactory_metadata import (
        PowerFactoryMetadataWriteError, apply_feeder_assignment_plan,
        assignment_plan_sha256,
    )

    class Obj:
        def __init__(self, fail=False):
            self.value = ['OLD']
            self.fail = fail

        def SetAttribute(self, _name, value):
            if self.fail:
                raise RuntimeError('write failed')
            self.value = value

        def GetAttribute(self, _name):
            return self.value

        def GetUserAttribute(self, _name):
            return self.value

    def item(name, obj):
        record = FeederAssignment('ElmLod', name, name, 'IN111', 'NET_IN111', 'N1', '')
        return SimpleNamespace(record=record, obj=obj)

    good = Obj()
    plan = [item('A', good)]
    digest = assignment_plan_sha256(plan)
    result = apply_feeder_assignment_plan(plan, expected_plan_sha256=digest)
    assert result['dry_run_plan_sha256'] == result['applied_plan_sha256'] == digest
    assert result['reread_verified'] is True
    assert result['rollback']['status'] == 'NOT_REQUIRED'

    good.value = ['OLD']
    bad = Obj(fail=True)
    with pytest.raises(PowerFactoryMetadataWriteError) as caught:
        apply_feeder_assignment_plan([item('A', good), item('B', bad)])
    assert caught.value.rollback['attempted'] is True
    assert caught.value.rollback['restored'] == 1
    assert good.value == ['OLD']
