from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / 'tools' / 'powerfactory_load_batch.py'
SPEC = importlib.util.spec_from_file_location('powerfactory_load_batch', MODULE_PATH)
assert SPEC and SPEC.loader
pf_batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pf_batch)


class FakeObject:
    def __init__(self, loc_name: str, **attrs):
        object.__setattr__(self, 'loc_name', loc_name)
        object.__setattr__(self, '_attrs', dict(attrs))
        object.__setattr__(self, '_fail_attr', None)
        object.__setattr__(self, '_fail_once_attr', None)
        object.__setattr__(self, '_writes', 0)

    def __getattr__(self, name):
        return self._attrs.get(name, 0.0)

    def __setattr__(self, name, value):
        if name.startswith('_') or name == 'loc_name':
            object.__setattr__(self, name, value)
            return
        object.__setattr__(self, '_writes', self._writes + 1)
        if name == self._fail_once_attr:
            object.__setattr__(self, '_fail_once_attr', None)
            raise RuntimeError(f'fallo simulado una vez en {name}')
        if name == self._fail_attr:
            raise RuntimeError(f'fallo simulado en {name}')
        self._attrs[name] = value

    def GetAttribute(self, name):
        if name == 'loc_name':
            return self.loc_name
        return self._attrs.get(name)

    def SetAttribute(self, name, value):
        setattr(self, name, value)


class FakeProject(FakeObject):
    def __init__(self, app, name: str, network_id: str):
        super().__init__(name, **{'p:network_id': network_id})
        self._app = app

    def Activate(self):
        self._app.active_project = self
        return 0


class FakeUser:
    def __init__(self, projects):
        self.projects = projects

    def GetContents(self, pattern):
        assert pattern == '*.IntPrj'
        return self.projects


class FakeLdf:
    def __init__(self, app, return_codes=None):
        self.app = app
        self.return_codes = list(return_codes or [0])

    def Execute(self):
        rc = self.return_codes.pop(0) if self.return_codes else 0
        self.app.ldf_valid = rc == 0
        return rc


class FakeApp:
    def __init__(self, loads, *, project='PROYECTO', network_id='NETWORK_F1', ldf_codes=None):
        self.loads = loads
        self.active_project = None
        self.ldf_valid = True
        self.project = FakeProject(self, project, network_id)
        self.user = FakeUser([self.project])
        self.ldf = FakeLdf(self, ldf_codes)

    def GetCurrentUser(self):
        return self.user

    def GetCalcRelevantObjects(self, pattern):
        return self.loads if pattern == '*.ElmLod' else []

    def GetFromStudyCase(self, name):
        return self.ldf if name == 'ComLdf' else None

    def IsLdfValid(self):
        return self.ldf_valid


def load(name: str, feeder: str, **overrides):
    attrs = {
        'p:alimentador': feeder,
        'mode_inp': 'PQ',
        'i_sym': 0,
        'plini': 0.01,
        'qlini': 0.002,
        'slini': 0.010198,
        'coslini': 0.98058,
        'pf_recap': 0,
    }
    attrs.update(overrides)
    return FakeObject(name, **attrs)


def feeder_plan(*codes: str, feeder='F1', network_id='NETWORK_F1', project='PROYECTO'):
    return {
        'feeder': feeder,
        'network_id': network_id,
        'project_name': project,
        'updates': [
            {
                'sed_code': code,
                'feeder': feeder,
                'network_id': network_id,
                'plini_mw': 0.02,
                'qlini_mvar': 0.006,
                'slini_mva': 0.0208806130178211,
                'coslini': 0.9578262852211513,
            }
            for code in codes
        ],
    }


def test_same_loc_name_in_other_feeder_is_not_selected():
    wanted = load('SED01', 'F1')
    app = FakeApp([wanted, load('SED01', 'F2')])

    resolved = pf_batch.resolve_feeder_loads(app, 'PROYECTO', feeder_plan('SED01'))

    assert resolved['errors'] == []
    assert resolved['objects']['SED01'] is wanted


def test_duplicate_in_same_feeder_is_ambiguous():
    app = FakeApp([load('SED01', 'F1'), load('SED01', 'F1')])

    resolved = pf_batch.resolve_feeder_loads(app, 'PROYECTO', feeder_plan('SED01'))

    assert any('ambigua' in error.lower() for error in resolved['errors'])


def test_network_id_mismatch_blocks_preflight():
    app = FakeApp([load('SED01', 'F1')], network_id='NETWORK_OTRA')

    resolved = pf_batch.resolve_feeder_loads(app, 'PROYECTO', feeder_plan('SED01'))

    assert any('networkid' in error.lower() for error in resolved['errors'])


def test_preflight_writes_nothing_when_any_load_is_missing():
    present = load('SED01', 'F1')
    app = FakeApp([present])
    before = present.plini

    result = pf_batch.apply_feeder_transaction(
        app, feeder_plan('SED01', 'SED_MISSING'), dry_run=False,
    )

    assert result['status'] == 'ROLLED_BACK'
    assert present.plini == before
    assert result['written'] == 0


@pytest.mark.parametrize(
    ('mode', 'expected'),
    [
        ('PC', {'plini': 0.02, 'coslini': 0.9578262852211513}),
        ('PQ', {'plini': 0.02, 'qlini': 0.006}),
        ('SC', {'slini': 0.0208806130178211, 'coslini': 0.9578262852211513}),
        ('SP', {'slini': 0.0208806130178211, 'plini': 0.02}),
        ('QC', {'qlini': 0.006, 'coslini': 0.9578262852211513}),
    ],
)
def test_write_load_respects_input_mode(mode, expected):
    obj = load('SED01', 'F1', mode_inp=mode)
    requested = feeder_plan('SED01')['updates'][0]

    pf_batch.write_load(obj, requested)

    for attr, value in expected.items():
        assert getattr(obj, attr) == pytest.approx(value)
    assert pf_batch.verify_load(obj, requested) == []


def test_unbalanced_load_preserves_phase_shares():
    obj = load(
        'SED01', 'F1', i_sym=1,
        plinir=0.001, plinis=0.003, plinit=0.006,
        qlinir=0.0002, qlinis=0.0006, qlinit=0.0012,
    )
    requested = feeder_plan('SED01')['updates'][0]

    pf_batch.write_load(obj, requested)

    assert [obj.plinir, obj.plinis, obj.plinit] == pytest.approx([0.002, 0.006, 0.012])
    assert [obj.qlinir, obj.qlinis, obj.qlinit] == pytest.approx([0.0006, 0.0018, 0.0036])
    assert pf_batch.verify_load(obj, requested) == []


def test_verify_checks_p_q_pf_and_each_phase():
    obj = load(
        'SED01', 'F1', i_sym=1,
        plinir=0.001, plinis=0.003, plinit=0.006,
        qlinir=0.0002, qlinis=0.0006, qlinit=0.0012,
    )
    requested = feeder_plan('SED01')['updates'][0]
    pf_batch.write_load(obj, requested)
    obj.plinir += 0.001
    obj.qlinis += 0.001

    errors = pf_batch.verify_load(obj, requested)

    assert any('P total' in error for error in errors)
    assert any('Q total' in error for error in errors)
    assert any('FP' in error for error in errors)
    assert any('plinir' in error for error in errors)
    assert any('qlinis' in error for error in errors)


def test_write_failure_restores_every_changed_load():
    first = load('SED01', 'F1')
    second = load('SED02', 'F1')
    second._fail_once_attr = 'plini'
    app = FakeApp([first, second])
    before = [pf_batch.snapshot_load(obj) for obj in (first, second)]

    result = pf_batch.apply_feeder_transaction(
        app, feeder_plan('SED01', 'SED02'), dry_run=False,
    )

    assert result['status'] == 'ROLLED_BACK'
    assert [pf_batch.snapshot_load(obj) for obj in (first, second)] == before


def test_verification_failure_rolls_back(monkeypatch):
    obj = load('SED01', 'F1')
    app = FakeApp([obj])
    before = pf_batch.snapshot_load(obj)
    monkeypatch.setattr(pf_batch, 'verify_load', lambda *_: ['fallo simulado'])

    result = pf_batch.apply_feeder_transaction(app, feeder_plan('SED01'), dry_run=False)

    assert result['status'] == 'ROLLED_BACK'
    assert pf_batch.snapshot_load(obj) == before


def test_nonconvergent_load_flow_rolls_back_and_returns_failure():
    obj = load('SED01', 'F1')
    app = FakeApp([obj], ldf_codes=[1, 0])
    before = pf_batch.snapshot_load(obj)

    result = pf_batch.apply_feeder_transaction(app, feeder_plan('SED01'), dry_run=False)

    assert result['status'] == 'ROLLED_BACK'
    assert result['load_flow']['converged'] is False
    assert result['rollback_load_flow']['converged'] is True
    assert pf_batch.snapshot_load(obj) == before


def test_failed_rollback_is_critical(monkeypatch):
    first = load('SED01', 'F1')
    second = load('SED02', 'F1')
    second._fail_once_attr = 'plini'
    app = FakeApp([first, second])
    original_restore = pf_batch.restore_load

    def broken_restore(obj, snapshot):
        if obj is first:
            raise RuntimeError('rollback bloqueado')
        return original_restore(obj, snapshot)

    monkeypatch.setattr(pf_batch, 'restore_load', broken_restore)
    result = pf_batch.apply_feeder_transaction(
        app, feeder_plan('SED01', 'SED02'), dry_run=False,
    )

    assert result['status'] == 'CRITICAL'
    assert any('rollback' in error.lower() for error in result['rollback_errors'])


def test_dry_run_never_writes():
    obj = load('SED01', 'F1')
    app = FakeApp([obj])
    before = pf_batch.snapshot_load(obj)
    writes = obj._writes

    result = pf_batch.apply_feeder_transaction(app, feeder_plan('SED01'), dry_run=True)

    assert result['status'] == 'PASS'
    assert result['written'] == 0
    assert obj._writes == writes
    assert pf_batch.snapshot_load(obj) == before
