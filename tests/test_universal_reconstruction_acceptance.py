"""Generic end-to-end acceptance for reconstruction before DGS conversion."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

from synthetic_export import ExportSpec, write_export


def _module():
    path = Path(__file__).resolve().parents[1] / 'tools' / 'accept_three_sources.py'
    spec = importlib.util.spec_from_file_location('accept_reconstruction', path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_two_generic_feeders_reconstruct_without_mutating_originals(tmp_path):
    mod = _module()
    red, loads, equipment = write_export(
        ExportSpec(
            feeders=2,
            naming='plain',
            origin_x=500_000,
            origin_y=5_400_000,
            sections_per_feeder=2,
        ),
        tmp_path / 'UTILITY_X',
    )
    # Remove one declared node per feeder and reference a conductor absent from
    # the supplied catalogue. The derived dataset must repair both; originals stay put.
    red_text = red.read_text(encoding='utf-8')
    red_text = '\n'.join(
        line for line in red_text.splitlines()
        if not line.startswith(('N1_1,', 'N2_1,'))
    ).replace(',DEFAULT,40.0,', ',UTILITY_UNKNOWN_50,40.0,') + '\n'
    red.write_text(red_text, encoding='utf-8')
    original_hashes = {path.name: _sha(path) for path in (red, loads, equipment)}

    config = mod.AcceptanceConfig(
        audit_dir=tmp_path / 'audit',
        txt_red=red,
        txt_loads=loads,
        txt_equipment=equipment,
        feeders=('AL01', 'AL02'),
        source_company='UTILITY_X',
        source_period='2035',
        source_crs='EPSG:32632',
        reconstruct=True,
    )
    summary = mod.run_three_sources(config)
    txt = next(row for row in summary['sources'] if row['mode'] == 'txt')

    assert txt['status'] == 'DGS_READY'
    assert txt['selected_ids'] == ['AL01', 'AL02']
    assert [item['feeder'] for item in txt['dgs_files']] == ['AL01', 'AL02']
    assert txt['reconstruction']['report_sha256']
    assert txt['reconstruction']['repairs'] >= 4
    assert txt['reconstruction']['assumptions'] >= 2
    assert txt['reconstruction']['selection'] == ['AL01', 'AL02']
    assert txt['originals_unchanged'] is True
    assert {path.name: _sha(path) for path in (red, loads, equipment)} == original_hashes
    assert summary['requested_company'] == 'UTILITY_X'
    assert summary['requested_period'] == '2035'
    mod.validate_summary(summary)


def test_summary_rejects_changed_original_hash():
    mod = _module()
    summary = {
        'sources': [
            {
                'mode': mode,
                'status': 'DGS_READY' if mode == 'txt' else 'SKIP_MISSING_INPUT',
                'source_run_id': mode,
                'input_files': [],
                'dgs_files': [],
                'original_hashes_before': {'source.txt': 'a' * 64},
                'original_hashes_after': {'source.txt': 'b' * 64},
                'originals_unchanged': False,
            }
            for mode in ('txt', 'mdb', 'vnr')
        ],
    }
    try:
        mod.validate_summary(summary)
    except ValueError as exc:
        assert 'original' in str(exc).lower()
    else:
        raise AssertionError('a changed original must invalidate the acceptance summary')
