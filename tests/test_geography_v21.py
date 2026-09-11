from pathlib import Path

from igea_dgs.dataset import CymdistDataset
from igea_dgs.model import build_feeder_model

RED = Path('/mnt/data/RED_030826(1).txt')
LOAD = Path('/mnt/data/CARGA_030826(1).txt')
EQUIP = Path('/mnt/data/BD_Equipo_V261124 (1)(1).txt')


def _data():
    ds = CymdistDataset.from_files(RED, LOAD, EQUIP)
    model = build_feeder_model(ds, 'IN111')
    return ds, model


def test_build_geography_has_full_in111_coverage():
    from igea_dgs.geography import build_geography

    ds, model = _data()
    geo = build_geography(ds, model, source_crs='EPSG:32718')
    assert len(geo.nodes) == len(model.nodes) == 1936
    assert len(geo.lines) == len(model.lines) == 1934
    assert geo.intermediate_point_count == 1551
    assert geo.source_crs == 'EPSG:32718'
    assert geo.target_crs == 'EPSG:4326'
    src = geo.nodes[model.source_node]
    assert -14.1 < src.lat < -13.9
    assert -75.9 < src.lon < -75.6


def test_line_geometry_starts_and_ends_at_electrical_nodes():
    from igea_dgs.geography import build_geography

    ds, model = _data()
    geo = build_geography(ds, model, source_crs='EPSG:32718')
    for line in model.lines[:50]:
        path = geo.lines[line.section_id].path
        assert path[0] == geo.nodes[line.from_node]
        assert path[-1] == geo.nodes[line.to_node]


def test_dgs_writer_includes_geographic_graphic_layer(tmp_path):
    from igea_dgs.geography import build_geography
    from igea_dgs.dgs import write_dgs
    from igea_dgs.validate import parse_dgs

    ds, model = _data()
    geo = build_geography(ds, model, source_crs='EPSG:32718')
    out = tmp_path / 'IN111.dgs'
    manifest = write_dgs(model, out, geography=geo)
    tables = parse_dgs(out)

    assert len(tables['IntGrfnet']['rows']) == 1
    pointterms = [r for r in tables['IntGrf']['rows_dict'] if r.get('sSymNam') == 'PointTerm']
    assert len(pointterms) == len(manifest.visible_pointterm_nodes)
    assert len(pointterms) < len(model.nodes)
    assert len(tables['IntGrf']['rows']) == (
        len(manifest.visible_pointterm_nodes)
        + len(model.lines)
        + len(model.loads)
        + len(model.seds)
        + 1
    )
    assert len(tables['IntGrfcon']['rows']) == 2 * len(model.lines) + len(model.loads) + 1
    symbols = {r.get('sSymNam') for r in tables['IntGrf']['rows_dict']}
    assert 'd_lin' in symbols
    assert 'd_load' in symbols
    assert 'd_net' in symbols
    if model.seds:
        assert 'SecSubProd' in symbols
        assert len(tables['ElmSubstat']['rows']) == len(model.seds)
    assert manifest.diagram_fid
    net = tables['ElmNet']['rows_dict'][0]
    assert net['pDiagram'] == manifest.diagram_fid
    terms = tables['ElmTerm']['rows_dict']
    assert all(row['GPSlat'] and row['GPSlon'] for row in terms)
