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


def _vincular(report):
    from apoyo import cargar_herramienta

    tool = cargar_herramienta('powerfactory_acceptance.py')
    app = SimpleNamespace(GetCalcRelevantObjects=lambda _pattern: [])
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
    return report['project_binding']


def test_caso_base_sin_converger_se_vincula_sin_verificar():
    """015:RF-10, 015:RF-14 — CA101 sin converger: el vínculo existe, para volver a verificar,
    pero su «Caso base» no queda verificado (antes, «pendiente de convergencia»)."""
    binding = _vincular({
        'powerfactory_runtime_pass': False,
        'caso_base': {'status': 'NO_VERIFICADO', 'comprobaciones': {
            'gps_barras': {'pass': True}, 'flujo': {'pass': False}}},
    })
    assert binding['project'] == '20261013-121930_IGEA_CA101'
    assert binding['native_reread']['status'] == 'CASO_BASE_NO_VERIFICADO'
    assert binding['native_reread']['caso_base']['CA101']['fallos'] == ['flujo']


def test_sin_manifiesto_no_queda_verificado():
    """015:RF-1 — sin el resumen del «Caso base» no hay verificación."""
    binding = _vincular({'powerfactory_runtime_pass': True})
    assert binding['native_reread']['caso_base']['CA101']['status'] == 'NO_VERIFICADO'


def test_caso_base_verificado_en_el_vinculo():
    """015:RF-9, 015:RF-22 — el estado verificado solo lo pone la aceptación."""
    binding = _vincular({
        'powerfactory_runtime_pass': True,
        'caso_base': {'status': 'VERIFICADO', 'comprobaciones': {'flujo': {'pass': True}}},
    })
    assert binding['native_reread']['status'] == 'VERIFICADO_PERSISTENCIA'
    assert binding['native_reread']['caso_base']['CA101'] == {
        **binding['native_reread']['caso_base']['CA101'],
        'status': 'VERIFICADO', 'fallos': []}
