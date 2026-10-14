"""Adopción auditable de un proyecto nativo ya existente, sin ComImport."""

from __future__ import annotations

from types import SimpleNamespace


def test_activate_existing_project_returns_import_compatible_identity(monkeypatch):
    from apoyo import cargar_herramienta

    tool = cargar_herramienta('powerfactory_acceptance.py')
    project = SimpleNamespace(loc_name='20261013-121930_IGEA_CA101')
    monkeypatch.setattr(
        tool,
        '_activate_project_by_path',
        lambda app, path, folder: project,
    )
    app = SimpleNamespace(GetActiveProject=lambda: project)

    info = tool.activate_existing_project(
        app, '20261013-121930_IGEA_CA101', 'Conversor IGEA-DGS',
    )

    assert info['ok'] is True
    assert info['existing_project'] is True
    assert info['project_name'] == '20261013-121930_IGEA_CA101'
    assert info['project_path'] == '20261013-121930_IGEA_CA101'
    assert info['project_folder'] == 'Conversor IGEA-DGS'
    assert info['errors'] == []


def test_parser_rejects_import_and_existing_project_together():
    from apoyo import cargar_herramienta

    parser = cargar_herramienta('powerfactory_acceptance.py')._parser()

    try:
        parser.parse_args(['--import-dgs', 'A.dgs', '--existing-project', 'P'])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - expresa el contrato deseado
        raise AssertionError('Debe ser una selección mutuamente exclusiva')


def test_existing_project_gets_identity_binding_before_calibration_converges():
    from apoyo import cargar_herramienta

    tool = cargar_herramienta('powerfactory_acceptance.py')
    app = SimpleNamespace(GetCalcRelevantObjects=lambda _pattern: [])
    report = {
        'powerfactory_runtime_pass': False,
        'effective_reread': {'comldf_valid': False, 'capacitor_banks': True},
        'capacitor_reread': {'status': 'VERIFICADO_PERSISTENCIA'},
    }
    tool.attach_project_binding(
        report,
        app,
        {
            'status': 'VERIFIED_BEFORE_MUTATION',
            'source_run_id': 'run-active', 'source_mode': 'mdb',
            'source_fingerprint': 'f' * 64, 'dgs_sha256': 'd' * 64,
            'feeders': ['CA101'],
        },
        {
            'ok': True, 'existing_project': True,
            'project_path': '20261013-121930_IGEA_CA101',
            'project_folder': 'sistemaeletricoELD',
        },
        fallback_feeder='CA101',
    )

    assert report['project_binding']['project'] == '20261013-121930_IGEA_CA101'
    assert report['project_binding']['native_reread']['status'] == (
        'IDENTIDAD_VERIFICADA_PENDIENTE_CONVERGENCIA'
    )

