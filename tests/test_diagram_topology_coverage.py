"""Topology from TXT coords, DigSilent sheet coverage, and DGS convergence checks."""

from __future__ import annotations

import math
from collections import Counter

import pytest

from igea_dgs.batch import convert_selection, load_aliases
from igea_dgs.dgs import (
    DIAGRAM_SHEET_MARGIN_DU,
    NA205_DIAGRAM_UNITS_PER_METER,
    NA205_MAX_DIAGRAM_EXTENT,
    _diagram_mapper,
    write_dgs,
)
from igea_dgs.geography import build_geography
from igea_dgs.model import build_feeder_model
from igea_dgs.naming import feeder_short_name
from igea_dgs.validate import parse_dgs, validate_dgs


def _aliases():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / 'config' / 'line_type_aliases.json'
    return load_aliases(path) if path.is_file() else {}


def _convertible_feeders(ds):
    return [
        feeder_short_name(nid)
        for nid in ds.feeder_ids()
        if ds.feeders.get(nid)
    ]


def _txt_xy(model):
    return {
        nid: (node.x, node.y)
        for nid, node in model.nodes.items()
        if node.x is not None and node.y is not None
    }


def _diagram_xy_from_dgs(tables):
    """PointTerm centers keyed by electrical node loc_name."""
    out = {}
    for row in tables.get('IntGrf', {}).get('rows_dict', []):
        if row.get('sSymNam') != 'PointTerm':
            continue
        fid = row.get('pDataObj')
        term = next(
            (t for t in tables['ElmTerm']['rows_dict'] if t.get('FID') == fid),
            None,
        )
        if term is None:
            continue
        x = float(row['rCenterX'])
        y = float(row['rCenterY'])
        out[term['loc_name']] = (x, y)
    return out


def _all_graphic_xy(tables):
    xs, ys = [], []
    for row in tables.get('IntGrf', {}).get('rows_dict', []):
        xs.append(float(row['rCenterX']))
        ys.append(float(row['rCenterY']))
    for row in tables.get('IntGrfcon', {}).get('rows_dict', []):
        n = int(float(row.get('rX:SIZEROW') or 0))
        for i in range(n):
            xs.append(float(row[f'rX:{i}']))
            ys.append(float(row[f'rY:{i}']))
    return xs, ys


def test_diagram_topology_matches_scaled_txt_coordinates(ds, sample_model, tmp_path):
    """Isotropic scale: relative distances in DigSilent IntGrf match TXT CoordX/Y."""
    geo = build_geography(ds, sample_model, source_crs='EPSG:32718')
    out = tmp_path / f'{sample_model.name}_topo.dgs'
    write_dgs(sample_model, out, geography=geo)
    tables = parse_dgs(out)

    txt = _txt_xy(sample_model)
    diagram = _diagram_xy_from_dgs(tables)
    shared = [nid for nid in txt if nid[:40] in diagram or nid in diagram]
    # loc_name is truncated to 40 chars
    name_map = {nid: nid[:40] for nid in txt}
    shared = [nid for nid in txt if name_map[nid] in diagram]
    assert len(shared) >= min(8, len(txt))

    # Pairwise distance ratios: dig / txt ≈ constant (uniform scale + rotation-free
    # after CRS→local meters; allow small CRS projection residual).
    ratios = []
    for i, a in enumerate(shared[:40]):
        for b in shared[i + 1 : i + 6]:
            tax, tay = txt[a]
            tbx, tby = txt[b]
            d_txt = math.hypot(tbx - tax, tby - tay)
            if d_txt < 5.0:
                continue
            dax, day = diagram[name_map[a]]
            dbx, dby = diagram[name_map[b]]
            d_dig = math.hypot(dbx - dax, dby - day)
            ratios.append(d_dig / d_txt)
    assert len(ratios) >= 10
    mean = sum(ratios) / len(ratios)
    assert mean > 0
    for r in ratios:
        assert abs(r - mean) / mean < 0.08, f'ratio {r} vs mean {mean} (topology warped)'


def test_diagram_sheet_covers_full_network_and_map(ds, sample_model, tmp_path):
    """Sheet bbox includes all IntGrf/IntGrfcon points within DigSilent canvas."""
    geo = build_geography(ds, sample_model, source_crs='EPSG:32718')
    visible = set(sample_model.nodes)
    _map_point, sheet = _diagram_mapper(geo, visible)
    assert sheet.span <= NA205_MAX_DIAGRAM_EXTENT + 1e-6
    assert sheet.scale <= NA205_DIAGRAM_UNITS_PER_METER + 1e-12
    assert sheet.width >= 2 * DIAGRAM_SHEET_MARGIN_DU
    assert sheet.height >= 2 * DIAGRAM_SHEET_MARGIN_DU

    out = tmp_path / f'{sample_model.name}_sheet.dgs'
    manifest = write_dgs(sample_model, out, geography=geo)
    assert manifest.diagram_sheet is not None
    assert manifest.diagram_sheet.span <= NA205_MAX_DIAGRAM_EXTENT + 1e-6

    tables = parse_dgs(out)
    xs, ys = _all_graphic_xy(tables)
    assert xs and ys
    assert min(xs) >= sheet.xmin - 1e-6
    assert max(xs) <= sheet.xmax + 1e-6
    assert min(ys) >= sheet.ymin - 1e-6
    assert max(ys) <= sheet.ymax + 1e-6
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    assert span <= NA205_MAX_DIAGRAM_EXTENT * 1.02


def test_validate_dgs_converges_for_digsilent_static_gate(ds, sample_model, tmp_path):
    """Static DigSilent gate: counts, GPS, graphics, sheet, connectivity."""
    geo = build_geography(ds, sample_model, source_crs='EPSG:32718')
    out = tmp_path / f'{sample_model.name}_gate.dgs'
    write_dgs(sample_model, out, geography=geo)
    report = validate_dgs(sample_model, out, geography=geo)
    assert report['errors_total'] == 0, report
    c = report['counts']
    assert c['source_lines'] == c['dgs_lines']
    assert c['source_loads'] == c['dgs_loads']
    assert c['dgs_diagrams'] == 1
    assert c['source_seds'] == c.get('dgs_seds', c['source_seds'])


def test_batch_selection_preserves_double_circuits_and_sheet(ds, tmp_path):
    """Multi-feeder convert: fidelity + sheet coverage, including parallel rails."""
    aliases = _aliases()
    convertibles = _convertible_feeders(ds)
    if len(convertibles) < 2:
        pytest.skip('Need ≥2 convertible feeders')

    # Prefer a feeder with parallel SECTION (doble circuito) if present.
    pick = [convertibles[0]]
    for name in convertibles:
        model = build_feeder_model(ds, name, aliases=aliases, strict=True)
        ends = Counter(tuple(sorted((ln.from_node, ln.to_node))) for ln in model.lines)
        if any(c >= 2 for c in ends.values()):
            pick = [name]
            break
    # Add a second feeder for batch path.
    for name in convertibles:
        if name not in pick:
            pick.append(name)
            break

    out = tmp_path / 'batch_sheet'
    manifest = convert_selection(
        ds,
        pick,
        out,
        aliases=aliases,
        strict=True,
        include_geography=True,
        source_crs='EPSG:32718',
    )
    assert manifest['summary']['failed'] == 0
    assert manifest['summary']['ok'] == len(pick)

    for item in manifest['feeders']:
        assert item['status'] == 'ok'
        counts = item['counts']
        assert counts['source_lines'] == counts['dgs_lines']
        assert counts['source_loads'] == counts['dgs_loads']
        tables = parse_dgs(item['dgs'])
        xs, ys = _all_graphic_xy(tables)
        span = max(max(xs) - min(xs), max(ys) - min(ys))
        assert span <= NA205_MAX_DIAGRAM_EXTENT * 1.02
        assert len(tables['IntGrfnet']['rows']) == 1
        assert tables['ElmNet']['rows_dict'][0]['pDiagram'] == tables['IntGrfnet']['rows_dict'][0]['FID']


def test_geography_path_endpoints_match_electrical_topology(ds, sample_model):
    geo = build_geography(ds, sample_model, source_crs='EPSG:32718')
    for line in sample_model.lines:
        path = geo.lines[line.section_id].path
        assert path[0] == geo.nodes[line.from_node]
        assert path[-1] == geo.nodes[line.to_node]
        assert line.from_node in sample_model.nodes
        assert line.to_node in sample_model.nodes
