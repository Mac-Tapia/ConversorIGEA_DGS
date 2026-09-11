from pathlib import Path


def test_packaged_schema_has_exact_core_headers_and_no_reference_dependency():
    from igea_dgs.schema import load_schema

    schema = load_schema('pf21_dgs_1_8_4')
    assert schema.general_version == '7.0'
    assert schema.header('General') == '$$General;FID(a:40);Descr(a:40);Val(a:40)'
    assert schema.header('ElmLne') == '$$ElmLne;FID(a:40);OP(a:1);loc_name(a:40);fold_id(p);typ_id(p);dline(r);fline(r);GPScoords:MATRIX;nlnum(i);inAir(i)'
    assert schema.header('StaCubic') == '$$StaCubic;FID(a:40);OP(a:1);loc_name(a:40);fold_id(p);obj_bus(i);obj_id(p);it2p1(i);it2p2(i);it2p3(i)'
    assert schema.header('StaSwitch') == '$$StaSwitch;FID(a:40);OP(a:1);loc_name(a:40);fold_id(p);on_off(i);typ_id(p);aUsage(a)'
    raw = Path(schema.source_path).read_text(encoding='utf-8')
    lowered = raw.lower()
    assert 'na205.dgs' not in lowered
    assert '/mnt/data' not in lowered
    assert 'node_2030_957807_na205' not in lowered
