"""Tests for preview layers and Leaflet HTML export (no leafmap required)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from igea_dgs.geography import GeoLine, GeoPoint, GeographyManifest
from igea_dgs.model import FeederModel, Line, LineType, Node
from igea_dgs.preview import (
    PreviewError,
    build_preview_layers,
    layers_to_geojson,
    write_preview_geojson,
    write_preview_html,
)


def _mini_model() -> FeederModel:
    line_type = LineType(
        key='LINE:AAAC',
        code='AAAC',
        source_table='LINE',
        r1_ohm_km=0.3,
        r0_ohm_km=0.9,
        x1_ohm_km=0.4,
        x0_ohm_km=1.2,
        b1_source=0.0,
        b0_source=0.0,
        ampacity_a=400.0,
    )
    line = Line(
        section_id='SEC1',
        from_node='N1',
        to_node='N2',
        phase='ABC',
        type_key='LINE:AAAC',
        source_type_code='AAAC',
        length_m=120.0,
        overhead=True,
    )
    return FeederModel(
        name='DEMO',
        network_id='FEEDER=DEMO',
        nominal_kv=13.2,
        source_node='N1',
        nodes={'N1': Node('N1', 0.0, 0.0), 'N2': Node('N2', 100.0, 0.0)},
        lines=[line],
        loads=[],
        devices=[],
        line_types={'LINE:AAAC': line_type},
        section_by_id={'SEC1': line},
    )


def _mini_geo() -> GeographyManifest:
    n1 = GeoPoint(lat=-12.05, lon=-77.04, x=0.0, y=0.0)
    n2 = GeoPoint(lat=-12.051, lon=-77.039, x=100.0, y=0.0)
    return GeographyManifest(
        feeder='DEMO',
        network_id='FEEDER=DEMO',
        source_node='N1',
        source_crs='EPSG:32718',
        target_crs='EPSG:4326',
        nodes={'N1': n1, 'N2': n2},
        lines={
            'SEC1': GeoLine(
                section_id='SEC1',
                from_node='N1',
                to_node='N2',
                path=(n1, n2),
            )
        },
        source_xy_bounds=(0.0, 0.0, 100.0, 0.0),
        target_bounds=(-77.04, -12.051, -77.039, -12.05),
        intermediate_point_count=0,
        intermediate_section_count=0,
    )


def test_build_preview_layers_populates_dgs_attributes():
    layers = build_preview_layers(_mini_model(), _mini_geo())
    assert layers.feeder == 'DEMO'
    assert len(layers.nodes) == 2
    assert len(layers.lines) == 1
    line = layers.lines[0]
    assert line.section_id == 'SEC1'
    assert line.from_node == 'N1'
    assert line.to_node == 'N2'
    assert line.r1_ohm_km == 0.3
    assert line.x1_ohm_km == 0.4
    assert line.length_km == pytest.approx(0.12)
    assert layers.nodes[0].is_source or layers.nodes[1].is_source


def test_preview_rejects_missing_node_coordinates():
    geo = _mini_geo()
    geo_bad = GeographyManifest(
        feeder=geo.feeder,
        network_id=geo.network_id,
        source_node=geo.source_node,
        source_crs=geo.source_crs,
        target_crs=geo.target_crs,
        nodes={'N1': geo.nodes['N1']},
        lines=geo.lines,
        source_xy_bounds=geo.source_xy_bounds,
        target_bounds=geo.target_bounds,
        intermediate_point_count=0,
        intermediate_section_count=0,
    )
    with pytest.raises(PreviewError, match='sin coordenadas'):
        build_preview_layers(_mini_model(), geo_bad)


def test_write_leaflet_html_and_geojson(tmp_path: Path):
    model = _mini_model()
    geo = _mini_geo()
    html = write_preview_html(model, geo, tmp_path / 'demo_preview.html', backend='leaflet')
    gj = write_preview_geojson(model, geo, tmp_path / 'demo_preview.geojson')
    text = html.read_text(encoding='utf-8')
    assert 'leaflet' in text.lower()
    assert 'ElmLne' in text
    assert 'SEC1' in text
    data = json.loads(gj.read_text(encoding='utf-8'))
    assert data['type'] == 'FeatureCollection'
    assert len(data['features']) == 3  # 2 nodes + 1 line
    kinds = {f['properties']['kind'] for f in data['features']}
    assert kinds == {'ElmTerm', 'ElmLne'}


def test_layers_to_geojson_popup_has_impedance():
    geojson = layers_to_geojson(build_preview_layers(_mini_model(), _mini_geo()))
    line_feat = next(f for f in geojson['features'] if f['properties']['kind'] == 'ElmLne')
    assert 'r1/x1' in line_feat['properties']['popup']
    assert line_feat['properties']['bus1'] == 'N1'
