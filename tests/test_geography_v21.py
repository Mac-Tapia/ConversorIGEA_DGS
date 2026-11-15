"""Pruebas del motor base de conversión.

Spec 034: 034:RF-11.
"""
def test_build_geography_has_full_sample_coverage(ds, sample_model):
    from convertersmartgrid.geography import build_geography

    geo = build_geography(ds, sample_model, source_crs='EPSG:32718')
    assert len(geo.nodes) == len(sample_model.nodes)
    assert len(geo.lines) == len(sample_model.lines)
    assert geo.intermediate_point_count >= 0
    assert geo.source_crs == 'EPSG:32718'
    assert geo.target_crs == 'EPSG:4326'
    src = geo.nodes[sample_model.source_node]
    assert src.lat is not None and src.lon is not None
    assert -90.0 <= src.lat <= 90.0
    assert -180.0 <= src.lon <= 180.0


def test_line_geometry_starts_and_ends_at_electrical_nodes(ds, sample_model):
    from convertersmartgrid.geography import build_geography

    geo = build_geography(ds, sample_model, source_crs='EPSG:32718')
    sample_lines = sample_model.lines[: min(50, len(sample_model.lines))]
    for line in sample_lines:
        path = geo.lines[line.section_id].path
        assert path[0] == geo.nodes[line.from_node]
        assert path[-1] == geo.nodes[line.to_node]


def test_dgs_writer_includes_geographic_graphic_layer(ds, sample_model, tmp_path):
    from convertersmartgrid.geography import build_geography
    from convertersmartgrid.dgs import diagram_line_rail_counts, write_dgs
    from convertersmartgrid.validate import parse_dgs

    geo = build_geography(ds, sample_model, source_crs='EPSG:32718')
    out = tmp_path / f'{sample_model.name}.dgs'
    manifest = write_dgs(sample_model, out, geography=geo)
    tables = parse_dgs(out)

    nested_keys = {sed.load_key for sed in sample_model.seds}
    free_loads = [load for load in sample_model.loads if (load.section_id, load.device_number) not in nested_keys]
    _oh, _ug, d_lin_graphics = diagram_line_rail_counts(sample_model)

    assert len(tables['IntGrfnet']['rows']) == 1
    pointterms = [r for r in tables['IntGrf']['rows_dict'] if r.get('sSymNam') == 'PointTerm']
    assert len(pointterms) == len(manifest.visible_pointterm_nodes)
    assert len(pointterms) <= len(sample_model.nodes)
    assert len(tables['IntGrf']['rows']) == (
        len(manifest.visible_pointterm_nodes)
        + d_lin_graphics
        + len(free_loads)
        + len(sample_model.seds)
        + 1
    )
    assert len(tables['IntGrfcon']['rows']) == 2 * d_lin_graphics + len(free_loads) + 1
    symbols = {r.get('sSymNam') for r in tables['IntGrf']['rows_dict']}
    assert 'd_lin' in symbols
    assert 'd_net' in symbols
    if free_loads:
        assert 'd_load' in symbols
    else:
        assert 'd_load' not in symbols
    if sample_model.seds:
        assert 'SecSubProd' in symbols
        assert len(tables['ElmSubstat']['rows']) == len(sample_model.seds)
        # SED loads are modules inside the triangle, not separate sheet symbols.
        for load in sample_model.loads:
            if (load.section_id, load.device_number) not in nested_keys:
                continue
            name = (load.display_name or load.customer_number or load.device_number)[:40]
            lod = next(r for r in tables['ElmLod']['rows_dict'] if r.get('loc_name') == name)
            sed = next(
                r for r in tables['ElmSubstat']['rows_dict']
                if r.get('FID') == lod.get('fold_id')
            )
            assert sed.get('loc_name')
            assert not any(g.get('pDataObj') == lod.get('FID') for g in tables['IntGrf']['rows_dict'])
    assert manifest.diagram_fid
    net = tables['ElmNet']['rows_dict'][0]
    assert net['pDiagram'] == manifest.diagram_fid
    terms = tables['ElmTerm']['rows_dict']
    assert all(row['GPSlat'] and row['GPSlon'] for row in terms)


def test_seqnumber_no_entero_conserva_el_orden_del_fichero_y_avisa():
    """010:RF-8 (H14, 2026-11-14): con un SeqNumber vacío o no entero en un tramo no hay orden que comparar: se
    conservan sus puntos en el orden del fichero (estable) y se avisa con el tramo y el valor. Antes «x» iba al
    final y el vacío al principio, sin aviso."""
    from convertersmartgrid.geography import ordenar_intermedios
    filas = [{'SeqNumber': '2', 'CoordX': 'b'}, {'SeqNumber': 'x', 'CoordX': 'x'},
             {'SeqNumber': '', 'CoordX': 'v'}, {'SeqNumber': '1', 'CoordX': 'a'}]
    orden, avisos = ordenar_intermedios('S7', filas)
    assert [f['CoordX'] for f in orden] == ['b', 'x', 'v', 'a']
    assert len(avisos) == 1 and 'S7' in avisos[0] and "'x'" in avisos[0] and "''" in avisos[0]


def test_seqnumber_entero_escrito_con_decimal_se_ordena_por_su_numero():
    """010:RF-1 / 010:RF-8: «3.0» vale 3; todos enteros, los puntos van por su número y sin aviso."""
    from convertersmartgrid.geography import ordenar_intermedios
    filas = [{'SeqNumber': '3.0', 'CoordX': 'c'}, {'SeqNumber': '1', 'CoordX': 'a'},
             {'SeqNumber': ' 2 ', 'CoordX': 'b'}, {'SeqNumber': '10', 'CoordX': 'd'}]
    orden, avisos = ordenar_intermedios('S1', filas)
    assert [f['CoordX'] for f in orden] == ['a', 'b', 'c', 'd'] and avisos == []


def test_el_aviso_del_seqnumber_llega_a_la_validacion_de_la_geografia(ds, sample_model):
    """010:RF-8: el aviso del tramo sale en los ``warnings`` de validate_geography, que ve el operador."""
    from dataclasses import replace
    from convertersmartgrid.geography import build_geography, validate_geography
    geo = build_geography(ds, sample_model, source_crs='EPSG:32718')
    con_aviso = replace(geo, avisos=('S1: SeqNumber vacío o no entero (010:RF-8)',))
    assert 'S1: SeqNumber vacío o no entero (010:RF-8)' in validate_geography(sample_model, con_aviso)['warnings']
