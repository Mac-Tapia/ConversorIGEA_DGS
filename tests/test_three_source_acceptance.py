"""Contrato del ejecutor auditado de las tres fuentes.

Spec 034: 034:RF-24.
"""

from __future__ import annotations


import pytest

from synthetic_export import CRS_SINTETICO, ExportSpec, write_export
from apoyo import cargar_herramienta


def _module():
    return cargar_herramienta('accept_three_sources.py', 'accept_three_sources')


def test_missing_inputs_are_explicit_and_vnr_is_blocked(tmp_path):
    mod = _module()
    config = mod.AcceptanceConfig(audit_dir=tmp_path / 'audit')
    summary = mod.run_three_sources(config)
    by_mode = {row['mode']: row for row in summary['sources']}
    assert by_mode['txt']['status'] == 'SKIP_MISSING_INPUT'
    assert by_mode['mdb']['status'] == 'SKIP_MISSING_INPUT'
    assert by_mode['vnr']['status'] == 'BLOCKED_MISSING_OFFICIAL_PACKAGE'
    assert summary['overall_status'] == 'INCOMPLETE'
    assert (tmp_path / 'audit' / 'acceptance_summary.json').is_file()


def test_txt_real_file_flow_records_hashes_selection_and_dgs(tmp_path):
    mod = _module()
    red, loads, equipment = write_export(ExportSpec(feeders=2), tmp_path / 'source')
    config = mod.AcceptanceConfig(
        audit_dir=tmp_path / 'audit',
        txt_red=red,
        txt_loads=loads,
        txt_equipment=equipment,
        feeder='AL01',
        source_crs=CRS_SINTETICO,
    )
    summary = mod.run_three_sources(config)
    txt = next(row for row in summary['sources'] if row['mode'] == 'txt')
    assert txt['status'] == 'DGS_READY'
    assert txt['feeder_count'] == 2
    assert txt['selected_ids'] == ['AL01']
    assert {item['slot'] for item in txt['input_files']} == {'red', 'loads', 'equipment'}
    assert all(len(item['sha256']) == 64 for item in txt['input_files'])
    assert txt['source_run_id'] and len(txt['source_fingerprint']) == 64
    assert txt['dgs_files'][0]['feeder'] == 'AL01'
    assert len(txt['dgs_files'][0]['sha256']) == 64
    assert txt['powerfactory']['evidence_level'] == 'NOT_RUN'
    mod.validate_summary(summary)


def test_summary_rejects_cross_mode_run_reuse():
    mod = _module()
    summary = {
        'sources': [
            {'mode': 'txt', 'status': 'DGS_READY', 'source_run_id': 'same'},
            {'mode': 'mdb', 'status': 'DGS_READY', 'source_run_id': 'same'},
            {'mode': 'vnr', 'status': 'BLOCKED_MISSING_OFFICIAL_PACKAGE', 'source_run_id': None},
        ]
    }
    with pytest.raises(ValueError, match='reutiliza.*source_run_id'):
        mod.validate_summary(summary)
