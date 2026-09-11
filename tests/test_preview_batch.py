"""Integration: preview + TSV export wired through convert_selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from igea_dgs.batch import convert_selection


def test_convert_with_preview_and_tsv(ds, sample_feeder, tmp_path: Path):
    pytest.importorskip('pyproj')
    manifest = convert_selection(
        ds,
        [sample_feeder],
        tmp_path,
        write_preview=True,
        export_tsv=True,
        preview_backend='leaflet',
    )
    assert manifest['summary']['ok'] == 1
    item = manifest['feeders'][0]
    assert item['status'] == 'ok'
    assert Path(item['preview_html']).is_file()
    assert Path(item['preview_geojson']).is_file()
    assert Path(item['tsv_dir']).is_dir()
    assert (Path(item['tsv_dir']) / 'ElmLne.tsv').is_file()
    html = Path(item['preview_html']).read_text(encoding='utf-8')
    assert 'leaflet' in html.lower()


def test_preview_requires_geography(ds, sample_feeder, tmp_path: Path):
    with pytest.raises(ValueError, match='write_preview'):
        convert_selection(
            ds,
            [sample_feeder],
            tmp_path,
            include_geography=False,
            write_preview=True,
        )
