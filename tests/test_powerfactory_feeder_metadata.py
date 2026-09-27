from __future__ import annotations

import pytest

from igea_dgs.powerfactory_metadata import (
    CONFIGURATION_NAME,
    TARGET_CLASSES,
    apply_feeder_assignment_plan,
    build_runtime_identity,
    data_extension_attribute_name,
    ensure_alimentador_data_extensions,
    resolve_feeder_assignments,
)
from igea_dgs.feeder_metadata import FeederAssignment


class FakeConfiguration:
    def __init__(self, class_name: str, *, fail: bool = False):
        self.class_name = class_name
        self.fail = fail
        self.add_string_calls: list[tuple[str, str, str, str]] = []

    def AddString(self, name, description, unit, initial):
        self.add_string_calls.append((name, description, unit, initial))
        if self.fail:
            raise RuntimeError(f'cannot add {self.class_name}')
        return 0


class FakeSettings:
    def __init__(self, *, fail_class: str = ''):
        self.configurations: dict[tuple[str, str], FakeConfiguration] = {}
        self.fail_class = fail_class

    def GetConfiguration(self, class_name, description):
        return self.configurations.get((class_name, description))

    def AddConfiguration(self, class_name, description):
        config = FakeConfiguration(class_name, fail=class_name == self.fail_class)
        self.configurations[(class_name, description)] = config
        return config


class FakeProject:
    def __init__(self, *, fail_class: str = ''):
        self.settings = FakeSettings(fail_class=fail_class)
        self.begin_calls = 0
        self.end_calls = 0

    def BeginDataExtensionModification(self):
        self.begin_calls += 1
        return self.settings

    def EndDataExtensionModification(self):
        self.end_calls += 1


def test_first_run_creates_one_string_extension_for_each_target_class():
    project = FakeProject()
    report = ensure_alimentador_data_extensions(project)

    assert report == {'created': list(TARGET_CLASSES), 'existing': [], 'errors': []}
    assert project.begin_calls == 1 and project.end_calls == 1
    for class_name in TARGET_CLASSES:
        config = project.settings.configurations[(class_name, CONFIGURATION_NAME)]
        assert config.add_string_calls == [('alimentador', 'Alimentador', '', '')]
    assert data_extension_attribute_name() == 'p:alimentador'


def test_second_run_is_idempotent_and_does_not_add_the_parameter_again():
    project = FakeProject()
    ensure_alimentador_data_extensions(project)
    report = ensure_alimentador_data_extensions(project)

    assert report == {'created': [], 'existing': list(TARGET_CLASSES), 'errors': []}
    assert project.begin_calls == 2 and project.end_calls == 2
    assert all(
        len(config.add_string_calls) == 1
        for config in project.settings.configurations.values()
    )


def test_transaction_is_always_closed_when_add_string_fails():
    project = FakeProject(fail_class='ElmSym')
    report = ensure_alimentador_data_extensions(project)

    assert project.end_calls == 1
    assert report['created'] == ['ElmLod', 'ElmXnet']
    assert report['errors'] == [{'class_name': 'ElmSym', 'error': 'cannot add ElmSym'}]


@pytest.mark.parametrize('project', [None, object()])
def test_missing_active_project_or_api_is_rejected(project):
    with pytest.raises(RuntimeError, match='proyecto activo|Data Extensions'):
        ensure_alimentador_data_extensions(project)


class FakePfObject:
    def __init__(
        self,
        class_name: str,
        loc_name: str,
        terminal: str,
        substation: str = '',
        *,
        fail_write: bool = False,
    ):
        self.class_name = class_name
        self.loc_name = loc_name
        self.values = {'p:alimentador': ''}
        self.fail_write = fail_write
        self.parent = _Container('ElmSubstat', substation) if substation else _Container('ElmNet', 'RED')
        term_parent = self.parent if substation else _Container('ElmNet', 'RED')
        term = _Terminal(terminal, term_parent)
        self.bus1 = _Cubicle(term)

    def GetClassName(self):
        return self.class_name

    def GetAttribute(self, name):
        if name == 'loc_name':
            return self.loc_name
        if name == 'bus1':
            return self.bus1
        return self.values.get(name)

    def SetAttribute(self, name, value):
        if self.fail_write and value:
            raise RuntimeError('write rejected')
        self.values[name] = value
        return 0

    def GetParent(self):
        return self.parent


class _Container:
    def __init__(self, class_name: str, loc_name: str, parent=None):
        self.class_name = class_name
        self.loc_name = loc_name
        self.parent = parent

    def GetClassName(self):
        return self.class_name

    def GetAttribute(self, name):
        return getattr(self, name, None)

    def GetParent(self):
        return self.parent


class _Terminal(_Container):
    def __init__(self, loc_name: str, parent):
        super().__init__('ElmTerm', loc_name, parent)


class _Cubicle:
    def __init__(self, terminal):
        self.cterm = terminal

    def GetAttribute(self, name):
        return getattr(self, name, None)


def _assignment(
    class_name='ElmLod', loc_name='LOAD-1', terminal='SE50001_BT',
    substation='SE50001', feeder='NA203', dgs_fid='10',
):
    return FeederAssignment(
        class_name, dgs_fid, loc_name, feeder, f'NETWORK_{feeder}', terminal, substation,
    )


@pytest.mark.parametrize(
    ('obj', 'expected'),
    [
        (FakePfObject('ElmLod', 'LOAD-SED', 'SE50001_BT', 'SE50001'),
         ('ElmLod', 'LOAD-SED', 'SE50001_BT', 'SE50001')),
        (FakePfObject('ElmLod', 'LOAD-DIRECT', 'NODO-10'),
         ('ElmLod', 'LOAD-DIRECT', 'NODO-10', '')),
        (FakePfObject('ElmXnet', 'External Grid NA203', 'SRC-203'),
         ('ElmXnet', 'External Grid NA203', 'SRC-203', '')),
        (FakePfObject('ElmSym', 'GEN-1', 'GEN-BUS'),
         ('ElmSym', 'GEN-1', 'GEN-BUS', '')),
    ],
)
def test_build_runtime_identity_uses_exact_electrical_context(obj, expected):
    assert build_runtime_identity(obj).key == expected


def test_resolution_distinguishes_equal_names_by_terminal_and_assigns_each_feeder():
    na203 = FakePfObject('ElmLod', 'LOAD', 'SE50001_BT', 'SE50001')
    na205 = FakePfObject('ElmLod', 'LOAD', 'SE50002_BT', 'SE50002')
    records = [
        _assignment(loc_name='LOAD', terminal='SE50001_BT', substation='SE50001', feeder='NA203'),
        _assignment(loc_name='LOAD', terminal='SE50002_BT', substation='SE50002', feeder='NA205', dgs_fid='11'),
    ]

    plan = resolve_feeder_assignments(records, [na203, na205])
    report = apply_feeder_assignment_plan(plan)

    assert report['ok'] is True
    assert report['assigned'] == 2
    assert report['counts_by_feeder'] == {'NA203': 1, 'NA205': 1}
    assert na203.values['p:alimentador'] == 'NA203'
    assert na205.values['p:alimentador'] == 'NA205'


@pytest.mark.parametrize('objects, issue', [([], 'unresolved'), (None, 'ambiguous')])
def test_zero_or_two_candidates_block_every_write(objects, issue):
    target = FakePfObject('ElmLod', 'LOAD-1', 'SE50001_BT', 'SE50001')
    candidates = [] if objects == [] else [target, FakePfObject('ElmLod', 'LOAD-1', 'SE50001_BT', 'SE50001')]
    plan = resolve_feeder_assignments([_assignment()], candidates)

    report = apply_feeder_assignment_plan(plan)

    assert report['ok'] is False
    assert report['assigned'] == 0
    assert report[issue]
    assert target.values['p:alimentador'] == ''


def test_failed_write_rolls_back_every_object_already_touched():
    first = FakePfObject('ElmLod', 'A', 'TA')
    second = FakePfObject('ElmXnet', 'B', 'TB', fail_write=True)
    first.values['p:alimentador'] = 'ORIGINAL'
    records = [
        _assignment(loc_name='A', terminal='TA', substation='', feeder='NA203'),
        _assignment(class_name='ElmXnet', loc_name='B', terminal='TB', substation='', feeder='NA205', dgs_fid='20'),
    ]

    report = apply_feeder_assignment_plan(resolve_feeder_assignments(records, [first, second]))

    assert report['ok'] is False
    assert report['assigned'] == 0
    assert report['rolled_back'] == 1
    assert first.values['p:alimentador'] == 'ORIGINAL'
    assert second.values['p:alimentador'] == ''
    assert 'write rejected' in report['errors'][0]
