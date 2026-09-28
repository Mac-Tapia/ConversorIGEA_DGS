from __future__ import annotations

import importlib.util
from pathlib import Path

from synthetic_export import ExportSpec, write_export


def _load_verifier():
    path = Path(__file__).resolve().parents[1] / 'tools' / 'verify_reference_feeders.py'
    spec = importlib.util.spec_from_file_location('verify_reference_feeders', path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _passing_evidence(feeder: str) -> dict:
    return {
        'validation_errors': 0,
        'completeness_failures': [],
        'mapping_feeders': [feeder],
        'assignment_counts': {'ElmLod': 2, 'ElmSym': 0, 'ElmXnet': 1},
        'dgs_counts': {'ElmLod': 2, 'ElmSym': 0, 'ElmXnet': 1},
        'adaptive_grid': True,
        'scale_units_per_m': 2.08,
        'trafomix_excluded': 3,
        'trafomix_present': 0,
        'source_switches': 4,
        'dgs_switches': 3,
        'bridge_switches': 1,
        'source_seds': 2,
        'dgs_seds': 2,
        'dgs_transformers': 2,
    }


def test_reference_verifier_reports_each_required_feeder(tmp_path):
    verifier = _load_verifier()
    report = verifier.verify_reference_feeders(
        tmp_path / 'missing', tmp_path / 'out',
        ('NA203', 'NA205', 'PE104', 'CA101'),
    )
    assert list(report['feeders']) == ['NA203', 'NA205', 'PE104', 'CA101']


def test_reference_verifier_distinguishes_missing_fixture_from_failure(tmp_path):
    verifier = _load_verifier()
    report = verifier.verify_reference_feeders(
        tmp_path / 'missing', tmp_path / 'out', ('NA203',),
    )
    gates = report['feeders']['NA203']['gates']
    assert gates['input']['status'] == 'SKIP_MISSING_INPUT'
    assert gates['conversion']['status'] == 'SKIP_MISSING_INPUT'
    assert gates['input']['status'] != 'PASS'


def test_reference_verifier_checks_name_to_feeder_mapping():
    verifier = _load_verifier()
    evidence = _passing_evidence('NA203')
    assert verifier.evaluate_evidence('NA203', evidence)['mapping']['status'] == 'PASS'
    evidence['mapping_feeders'] = ['NA205']
    assert verifier.evaluate_evidence('NA203', evidence)['mapping']['status'] == 'FAIL'


def test_reference_verifier_checks_grid_scale_trafomix_switches_and_sed():
    verifier = _load_verifier()
    gates = verifier.evaluate_evidence('PE104', _passing_evidence('PE104'))
    assert {gates[name]['status'] for name in ('grid_scale', 'trafomix', 'switches', 'sed')} == {'PASS'}

    bad = _passing_evidence('PE104')
    bad.update({
        'adaptive_grid': False,
        'trafomix_present': 1,
        'dgs_switches': 1,
        'dgs_transformers': 1,
    })
    failed = verifier.evaluate_evidence('PE104', bad)
    assert {failed[name]['status'] for name in ('grid_scale', 'trafomix', 'switches', 'sed')} == {'FAIL'}


def test_reference_verifier_labels_powerfactory_not_run(tmp_path):
    verifier = _load_verifier()
    report = verifier.verify_reference_feeders(
        tmp_path / 'missing', tmp_path / 'out', ('CA101',), powerfactory=False,
    )
    assert report['feeders']['CA101']['gates']['powerfactory']['status'] == 'NOT_RUN_POWERFACTORY'


def test_reference_verifier_executes_all_non_proprietary_gates_when_input_exists(tmp_path):
    verifier = _load_verifier()
    write_export(ExportSpec(feeders=1, layout='completo'), tmp_path / 'reference')

    report = verifier.verify_reference_feeders(
        tmp_path / 'reference', tmp_path / 'out', ('AL01',), powerfactory=False,
    )

    gates = report['feeders']['AL01']['gates']
    assert {gates[name]['status'] for name in (
        'input', 'conversion', 'mapping', 'grid_scale', 'trafomix', 'switches', 'sed',
    )} == {'PASS'}
    assert gates['powerfactory']['status'] == 'NOT_RUN_POWERFACTORY'
    assert report['status'] == 'PASS'


def test_reference_verifier_accepts_explicit_txt_paths(tmp_path):
    verifier = _load_verifier()
    reference = tmp_path / 'reference'
    write_export(ExportSpec(feeders=1, layout='completo'), reference)
    discovery = verifier._discover_explicit_inputs(
        red=next(reference.glob('RED*.txt')),
        loads=next(reference.glob('CARGA*.txt')),
        equipment=next(reference.glob('BD_Equipo*.txt')),
    )

    assert discovery['kind'] == 'txt'
    assert discovery['status'] == 'PASS'
    assert set(discovery['paths']) == {verifier.RED, verifier.CARGA, verifier.EQUIPOS}


def test_reference_verifier_requires_network_and_equipment_mdb(tmp_path):
    verifier = _load_verifier()
    discovery = verifier._discover_explicit_inputs(mdb=tmp_path / 'network.mdb')

    assert discovery['kind'] == 'mdb'
    assert discovery['status'] == 'SKIP_MISSING_INPUT'
    assert 'catálogo' in discovery['detail']


def test_reference_verifier_combines_txt_and_mdb_reports(monkeypatch, tmp_path):
    verifier = _load_verifier()
    calls = []

    def fake_verify(reference_root, output, feeders, *, powerfactory=False, discovery=None):
        calls.append((Path(output).name, discovery['kind']))
        return {'status': 'PASS', 'feeders': {name: {} for name in feeders}}

    monkeypatch.setattr(verifier, 'verify_reference_feeders', fake_verify)
    report = verifier.verify_input_alternatives(
        tmp_path / 'out', ('NA203', 'NA205'),
        txt={'kind': 'txt', 'status': 'PASS', 'detail': 'ok', 'paths': {}},
        mdb={'kind': 'mdb', 'status': 'PASS', 'detail': 'ok', 'paths': {}},
    )

    assert calls == [('txt', 'txt'), ('mdb', 'mdb')]
    assert set(report['modes']) == {'txt', 'mdb'}
    assert report['status'] == 'PASS'
