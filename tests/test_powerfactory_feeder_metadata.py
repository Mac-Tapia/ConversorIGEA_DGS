from __future__ import annotations

from types import SimpleNamespace

import pytest

from igea_dgs.feeder_metadata import FeederAssignment
from igea_dgs.powerfactory_metadata import (
    PowerFactoryMetadataError,
    apply_imported_feeder_metadata,
    apply_feeder_assignment_plan,
    ensure_alimentador_data_extensions,
    resolve_feeder_assignments,
)


class _Variable:
    def __init__(self, name):
        self.loc_name = name

    def GetAttribute(self, name):
        return getattr(self, name, None)


class _Configuration:
    def __init__(self):
        self.variables = []
        self.add_calls = 0

    def AddString(self, name, description, unit, initial):
        self.add_calls += 1
        self.variables.append(_Variable(name))

    def GetContents(self, _pattern, *_args):
        return self.variables


class _Settings:
    def __init__(self):
        self.configurations = {}

    def GetConfiguration(self, class_name, name):
        return self.configurations.get((class_name, name))

    def AddConfiguration(self, class_name, name):
        config = _Configuration()
        self.configurations[(class_name, name)] = config
        return config


class _Project:
    def __init__(self):
        self.settings = _Settings()
        self.begin_calls = 0
        self.end_calls = 0

    def BeginDataExtensionModification(self):
        self.begin_calls += 1
        return self.settings

    def EndDataExtensionModification(self):
        self.end_calls += 1


class _Terminal:
    def __init__(self, name):
        self.loc_name = name

    def GetClassName(self):
        return 'ElmTerm'

    def GetAttribute(self, name):
        return getattr(self, name, None)


class _Cubicle:
    def __init__(self, terminal):
        self.cterm = terminal

    def GetAttribute(self, name):
        return getattr(self, name, None)


class _RuntimeObject:
    def __init__(self, class_name, name, terminal='', substation=None, fail=False):
        self.class_name = class_name
        self.loc_name = name
        self.parent = substation
        self.bus1 = _Cubicle(_Terminal(terminal)) if terminal else None
        self.attributes = {'p:alimentador': ''}
        self.fail = fail

    def GetClassName(self):
        return self.class_name

    def GetParent(self):
        return self.parent

    def GetAttribute(self, name):
        return self.attributes.get(name, getattr(self, name, None))

    def SetAttribute(self, name, value):
        if self.fail:
            raise RuntimeError('SetAttribute failed')
        if not isinstance(value, list):
            raise TypeError("'str' object is not a 'list' object")
        self.attributes[name] = value

    def GetUserAttribute(self, name):
        return self.attributes.get(f'p:{name}', self.attributes.get(name, []))


def _assignment(class_name, name, feeder, terminal='', substation=''):
    return FeederAssignment(
        class_name=class_name, dgs_fid=f'FID_{feeder}_{name}', loc_name=name,
        feeder=feeder, network_id=f'NET_{feeder}', terminal=terminal,
        substation=substation,
    )


def test_extension_is_created_once_and_is_idempotent():
    project = _Project()
    first = ensure_alimentador_data_extensions(project)
    second = ensure_alimentador_data_extensions(project)

    assert first['created'] == ['ElmLod', 'ElmSubstat', 'ElmSym', 'ElmXnet']
    assert second['existing'] == ['ElmLod', 'ElmSubstat', 'ElmSym', 'ElmXnet']
    assert all(config.add_calls == 1 for config in project.settings.configurations.values())
    assert project.begin_calls == project.end_calls == 2


def test_extension_transaction_closes_even_when_api_raises():
    project = _Project()

    def fail_add(*_args):
        raise RuntimeError('configuration denied')

    project.settings.AddConfiguration = fail_add
    with pytest.raises(RuntimeError, match='configuration denied'):
        ensure_alimentador_data_extensions(project)
    assert project.end_calls == 1


def test_resolution_uses_name_terminal_and_substation_together():
    parent = _RuntimeObject('ElmSubstat', 'SE100')
    load_a = _RuntimeObject('ElmLod', 'CUST1', 'SE100_BT', parent)
    load_b = _RuntimeObject('ElmLod', 'CUST1', 'NODE2')
    records = [
        _assignment('ElmLod', 'CUST1', 'AL101', 'SE100_BT', 'SE100'),
        _assignment('ElmLod', 'CUST1', 'AL102', 'NODE2'),
    ]

    plan = resolve_feeder_assignments(records, [load_a, load_b])
    assert [item.record.feeder for item in plan] == ['AL101', 'AL102']


@pytest.mark.parametrize(
    ('class_name', 'name', 'feeder', 'terminal', 'substation'),
    [
        ('ElmSubstat', 'SE100', 'AL101', '', 'SE100'),
        ('ElmXnet', 'External Grid AL101', 'AL101', 'NODE_A', ''),
        ('ElmSym', 'GEN_A', 'AL101', 'NODE_A', ''),
    ],
)
def test_resolution_supports_sed_source_and_synchronous_machine(
    class_name, name, feeder, terminal, substation,
):
    record = _assignment(class_name, name, feeder, terminal, substation)
    obj = _RuntimeObject(class_name, name, terminal, _RuntimeObject('ElmSubstat', substation)
                         if substation else None)
    plan = resolve_feeder_assignments([record], [obj])
    assert plan[0].record.feeder == feeder


def test_imported_metadata_requires_the_exact_active_project_and_assigns_attribute(tmp_path):
    from igea_dgs.feeder_metadata import write_feeder_metadata

    dgs = tmp_path / 'RED.dgs'
    dgs.write_text('DGS', encoding='ascii')
    sidecar = tmp_path / 'RED_feeder_metadata.json'
    record = _assignment('ElmLod', 'LOAD_A', 'AL101', 'NODE_A')
    write_feeder_metadata([record], dgs, sidecar)
    project = _Project()
    project.loc_name = 'NEW_RED'
    load = _RuntimeObject('ElmLod', 'LOAD_A', 'NODE_A')
    app = SimpleNamespace(
        GetActiveProject=lambda: project,
        GetCalcRelevantObjects=lambda pattern: [load] if pattern == '*.ElmLod' else [],
    )

    result = apply_imported_feeder_metadata(
        app, {'project_name': 'NEW_RED'}, str(dgs), str(sidecar),
    )

    assert result['status'] == 'assigned'
    assert result['by_feeder'] == {'AL101': {'ElmLod': 1}}
    assert load.GetUserAttribute('alimentador') == ['AL101']


def test_ambiguous_identity_blocks_before_any_write():
    record = _assignment('ElmLod', 'CUST1', 'AL101', 'NODE1')
    obj_a = _RuntimeObject('ElmLod', 'CUST1', 'NODE1')
    obj_b = _RuntimeObject('ElmLod', 'CUST1', 'NODE1')
    with pytest.raises(PowerFactoryMetadataError, match='2 objetos'):
        resolve_feeder_assignments([record], [obj_a, obj_b])
    assert obj_a.GetAttribute('p:alimentador') == ''
    assert obj_b.GetAttribute('p:alimentador') == ''


def test_apply_assignment_rolls_back_if_a_write_fails():
    one = _RuntimeObject('ElmLod', 'CUST1', 'NODE1')
    two = _RuntimeObject('ElmLod', 'CUST2', 'NODE2', fail=True)
    records = [
        _assignment('ElmLod', 'CUST1', 'AL101', 'NODE1'),
        _assignment('ElmLod', 'CUST2', 'AL102', 'NODE2'),
    ]
    plan = resolve_feeder_assignments(records, [one, two])

    with pytest.raises(RuntimeError, match='SetAttribute failed'):
        apply_feeder_assignment_plan(plan)
    assert one.GetUserAttribute('alimentador') == ['']
