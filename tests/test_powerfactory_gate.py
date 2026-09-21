"""Unit tests for PowerFactory gate helpers that do not need a live PF session."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_pf_mod():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / 'tools' / 'powerfactory_acceptance.py'
    spec = importlib.util.spec_from_file_location('powerfactory_acceptance', path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_geography_expected_counts_include_equipment(ds, sample_model, tmp_path):
    from igea_dgs.geography import build_geography, geography_to_dict

    geo = build_geography(ds, sample_model, source_crs='EPSG:32718')
    payload = geography_to_dict(geo, sample_model)
    expected = payload['expected_counts']
    assert expected['transformers'] == len(sample_model.seds)
    assert expected['substations_sed'] == len(sample_model.seds)
    assert expected['capacitors'] == 0
    assert expected['regulators'] == 0
    assert 'equipment_scope_note' in payload

    out = tmp_path / 'geo.json'
    out.write_text(json.dumps(payload), encoding='utf-8')
    loaded = json.loads(out.read_text(encoding='utf-8'))
    assert loaded['expected_counts']['lines'] == len(sample_model.lines)


def test_powerfactory_acceptance_module_imports():
    """Script must import without powerfactory installed (lazy connect)."""
    mod = _load_pf_mod()
    assert callable(mod.connect_powerfactory)
    assert callable(mod.import_dgs_file)
    assert callable(mod.activate_base_study_and_scenario)
    assert callable(mod.ensure_operation_scenario)
    assert callable(mod.execute_load_flow)
    assert callable(mod.diagnose_nonconvergence)
    assert callable(mod.apply_correction_intent)
    assert callable(mod.run_load_flow_until_converged)
    assert callable(mod.run_import_activate_flow)
    assert callable(mod.execute_short_circuit)
    assert callable(mod.run_study_suite)
    assert callable(mod.list_study_suite)
    assert callable(mod.inventory_network)
    assert callable(mod.run_acceptance)
    assert callable(mod.persist_feeder_dgs)
    assert callable(mod.persist_after_pf_gate)
    assert callable(mod.export_dgs_file)
    assert 'load_flow' in mod.STUDY_REGISTRY
    assert 'short_circuit' in mod.STUDY_REGISTRY


def test_powerfactory_gate_help_exits_zero():
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[1] / 'tools' / 'powerfactory_acceptance.py'
    proc = subprocess.run(
        [sys.executable, str(script), '--help'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert '--import-dgs' in proc.stdout
    assert '--run-load-flow' in proc.stdout
    assert '--ensure-scenario' in proc.stdout
    assert '--fix-until-converge' in proc.stdout
    assert '--run-studies' in proc.stdout
    assert '--list-studies' in proc.stdout


def test_list_studies_exits_zero_without_pf():
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[1] / 'tools' / 'powerfactory_acceptance.py'
    proc = subprocess.run(
        [sys.executable, str(script), '--list-studies'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert 'load_flow' in payload['registered']
    assert 'short_circuit' in payload['registered']
    assert 'opf' in payload['gaps']


def test_relaxed_comldf_attrs_are_documented_names():
    mod = _load_pf_mod()
    names = {n for n, _ in mod._RELAXED_COMLDF_ATTRS}
    # DigSILENT Help localisation (ComLdf.*) — not invented aliases.
    assert 'iopt_lim' in names
    assert 'iopt_at' in names
    assert 'iopt_fl' in names
    assert 'iopt_lev' in names
    assert 'iIgnoreLimits' not in names
    assert 'iopt_start' not in names
    # Relaxed means reactive limits OFF (User Manual §24.6.5).
    assert dict(mod._RELAXED_COMLDF_ATTRS)['iopt_lim'] == 0


def test_configure_comldf_relaxed_sets_documented_attrs():
    mod = _load_pf_mod()

    class FakeCmd:
        def __init__(self) -> None:
            self.values: dict[str, object] = {}

        def SetAttribute(self, name, value):
            self.values[name] = value

        def GetAttribute(self, name):
            return self.values.get(name)

    cmd = FakeCmd()
    applied = mod._configure_comldf(cmd, relaxed=True)
    assert applied.get('iopt_net') == 0
    assert applied.get('iopt_lim') == 0
    assert applied.get('iopt_fl') == 1
    assert applied.get('iopt_lev') == 1
    assert cmd.values['iopt_at'] == 0


def test_execute_short_circuit_reports_unavailable():
    mod = _load_pf_mod()
    app = SimpleNamespace(GetFromStudyCase=lambda _n: None)
    result = mod.execute_short_circuit(app)
    assert result['available'] is False
    assert result['pass'] is False
    assert result['command'] == 'ComShc'
    assert result['errors']


def test_execute_short_circuit_success():
    mod = _load_pf_mod()

    class FakeShc:
        def __init__(self) -> None:
            self.values: dict[str, object] = {}

        def SetAttribute(self, name, value):
            self.values[name] = value

        def GetAttribute(self, name):
            return self.values.get(name)

        def Execute(self):
            return 0

        def GetFaultType(self):
            return 0

    shc = FakeShc()
    app = SimpleNamespace(GetFromStudyCase=lambda _n: shc)
    result = mod.execute_short_circuit(app)
    assert result['available'] is True
    assert result['pass'] is True
    assert result['return_code'] == 0
    assert 'iopt_allbus' in result['comshc_attrs'] or result['comshc_attrs']


def test_run_study_suite_load_flow_and_shc(monkeypatch):
    mod = _load_pf_mod()

    def fake_ldf_study(app, **kwargs):
        return {
            'study': 'load_flow',
            'command': 'ComLdf',
            'pass': True,
            'available': True,
            'load_flow_loop': {'pass': True, 'attempts': []},
            'errors': [],
            'warnings': [],
        }

    def fake_shc(app, **kwargs):
        return {
            'study': 'short_circuit',
            'command': 'ComShc',
            'pass': True,
            'available': True,
            'errors': [],
            'warnings': [],
        }

    monkeypatch.setitem(mod.STUDY_REGISTRY, 'load_flow', fake_ldf_study)
    monkeypatch.setitem(mod.STUDY_REGISTRY, 'short_circuit', fake_shc)
    report = mod.run_study_suite(SimpleNamespace())
    assert report['ok'] is True
    assert [r['study'] for r in report['results']] == ['load_flow', 'short_circuit']


def test_diagnose_uses_comldf_return_meaning():
    mod = _load_pf_mod()
    app = SimpleNamespace(GetCalcRelevantObjects=lambda _p: [])
    diag = mod.diagnose_nonconvergence(
        app,
        last_ldf={'return_code': 2, 'return_meaning': mod._COMLDF_RC_MEANING[2]},
    )
    assert any('outer' in i.lower() or 'Outer' in i for i in diag['issues'])
    assert any('rc=2' in i for i in diag['issues'])


def test_apply_correction_intent_source_in_service():
    mod = _load_pf_mod()

    class FakeSrc:
        def __init__(self) -> None:
            self.outserv = 1
            self.loc_name = 'SRC1'

        def GetAttribute(self, name):
            return getattr(self, name, None)

        def SetAttribute(self, name, value):
            setattr(self, name, value)

        def GetClassName(self):
            return 'ElmXnet'

    src = FakeSrc()
    app = SimpleNamespace()

    def get_calc(pattern):
        if 'ElmXnet' in pattern:
            return [src]
        if 'ElmVac' in pattern:
            return []
        if 'ElmLod' in pattern:
            return []
        return []

    app.GetCalcRelevantObjects = get_calc
    diagnosis = {'floating_loads': []}
    result = mod.apply_correction_intent(app, 'source_in_service', diagnosis)
    assert result['ok'] is True
    assert src.outserv == 0
    assert 'outserv=0' in result['solution'] or result['actions']


def test_run_load_flow_until_converged_succeeds_on_second_attempt(monkeypatch):
    mod = _load_pf_mod()
    calls = {'n': 0}

    def fake_ldf(app, *, relaxed=False, **kwargs):
        calls['n'] += 1
        # Fail first, pass after a correction.
        ok = calls['n'] >= 2
        return {'pass': ok, 'return_code': 0 if ok else 1, 'ldf_valid': ok, 'errors': []}

    def fake_diag(app, *, last_ldf=None):
        return {'issues': ['test'], 'floating_loads': [], 'sources_out_of_service': []}

    def fake_fix(app, intent, diagnosis, *, load_scale_originals=None):
        return {'intent': intent, 'ok': True, 'solution': f'fix:{intent}', 'actions': [], 'errors': []}

    monkeypatch.setattr(mod, 'execute_load_flow', fake_ldf)
    monkeypatch.setattr(mod, 'diagnose_nonconvergence', fake_diag)
    monkeypatch.setattr(mod, 'apply_correction_intent', fake_fix)

    result = mod.run_load_flow_until_converged(SimpleNamespace(), max_intents=3)
    assert result['pass'] is True
    assert result['converged_after_intent'] == mod.CORRECTION_INTENTS[0]
    assert len(result['attempts']) == 2


def test_persist_feeder_dgs_already_in_place(tmp_path):
    mod = _load_pf_mod()
    dgs = tmp_path / 'AL104.dgs'
    dgs.write_text('DGS', encoding='utf-8')
    geo = tmp_path / 'AL104_geography.json'
    geo.write_text('{}', encoding='utf-8')
    info = mod.persist_feeder_dgs(dgs)
    assert info['ok'] is True
    assert info['already_in_place'] is True
    assert info['copied_dgs'] is False
    assert Path(info['dgs']) == dgs.resolve()
    assert any(s['name'] == 'AL104_geography.json' for s in info['sidecars'])


def test_persist_feeder_dgs_copies_into_out_dir(tmp_path):
    mod = _load_pf_mod()
    src_dir = tmp_path / 'tmp_pf'
    out_dir = tmp_path / 'gui_out'
    src_dir.mkdir()
    out_dir.mkdir()
    src = src_dir / 'AL104.dgs'
    src.write_text('DGS-CONTENT', encoding='utf-8')
    (src_dir / 'AL104_validation.json').write_text('{"ok":true}', encoding='utf-8')
    info = mod.persist_feeder_dgs(src, out_dir=out_dir)
    assert info['ok'] is True
    assert info['copied_dgs'] is True
    dest = out_dir / 'AL104.dgs'
    assert dest.is_file()
    assert dest.read_text(encoding='utf-8') == 'DGS-CONTENT'
    assert (out_dir / 'AL104_validation.json').is_file()


def test_persist_after_pf_gate_export_fallback(tmp_path, monkeypatch):
    mod = _load_pf_mod()
    dgs = tmp_path / 'IN111.dgs'
    dgs.write_text('DGS', encoding='utf-8')

    def fake_export(app, dest_path):
        return {
            'ok': False,
            'path': str(dest_path),
            'method': None,
            'errors': ['ComExport unavailable'],
            'warnings': [],
        }

    monkeypatch.setattr(mod, 'export_dgs_file', fake_export)
    report = mod.persist_after_pf_gate(
        dgs,
        app=SimpleNamespace(),
        export_converged=True,
        converged=True,
    )
    assert report['ok'] is True
    assert report['dgs'] == str(dgs.resolve())
    assert report['converged_dgs'] is None
    assert any('ComExport' in w or 'converter DGS' in w for w in report['warnings'])


def test_persist_after_pf_gate_export_ok(tmp_path, monkeypatch):
    mod = _load_pf_mod()
    dgs = tmp_path / 'AL105.dgs'
    dgs.write_text('DGS', encoding='utf-8')

    def fake_export(app, dest_path):
        path = Path(dest_path)
        path.write_text('EXPORTED', encoding='utf-8')
        return {
            'ok': True,
            'path': str(path),
            'method': 'ComExport:DGS File',
            'errors': [],
            'warnings': [],
        }

    monkeypatch.setattr(mod, 'export_dgs_file', fake_export)
    report = mod.persist_after_pf_gate(
        dgs,
        app=SimpleNamespace(),
        export_converged=True,
        converged=True,
    )
    assert report['ok'] is True
    assert report['converged_dgs']
    assert Path(report['converged_dgs']).name == 'AL105_pf_converged.dgs'
    assert Path(report['converged_dgs']).read_text(encoding='utf-8') == 'EXPORTED'


def test_powerfactory_help_mentions_persist_flags():
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[1] / 'tools' / 'powerfactory_acceptance.py'
    proc = subprocess.run(
        [sys.executable, str(script), '--help'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert '--persist-dir' in proc.stdout
    assert '--no-persist-dgs' in proc.stdout
    assert '--no-export-converged-dgs' in proc.stdout
