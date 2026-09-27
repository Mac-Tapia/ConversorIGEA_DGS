from __future__ import annotations

import pytest

from igea_dgs.powerfactory_metadata import (
    CONFIGURATION_NAME,
    TARGET_CLASSES,
    data_extension_attribute_name,
    ensure_alimentador_data_extensions,
)


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
