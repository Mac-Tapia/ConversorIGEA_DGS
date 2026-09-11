from igea_dgs.model import build_feeder_model


def test_build_sample_feeder_without_any_reference_dgs(ds, sample_feeder):
    model = build_feeder_model(ds, sample_feeder)
    assert model.name == sample_feeder
    assert model.network_id == ds.resolve_feeder(sample_feeder)
    assert model.nominal_kv > 0
    assert model.source_node
    assert len(model.lines) >= 1
    assert len(model.nodes) >= 2
    # Counts must match the source tables for this feeder, not a fixed export size
    section_ids = ds.feeder_section_ids(model.network_id)
    assert len(model.lines) == len(section_ids)


def test_default_line_type_is_media_specific(sample_model):
    defaults = {line.type_key for line in sample_model.lines if line.source_type_code == 'DEFAULT'}
    assert defaults <= {'LINE:DEFAULT', 'CABLE:DEFAULT'}
    if not defaults:
        return
    for key in defaults:
        typ = sample_model.line_types[key]
        assert typ.source_table in {'LINE', 'CONCENTRIC NEUTRAL CABLE'}


def test_load_location_1_connects_to_section_to_node(sample_model):
    if not sample_model.loads:
        return
    load = next((item for item in sample_model.loads if item.location == '1'), sample_model.loads[0])
    section = sample_model.section_by_id[load.section_id]
    if load.location == '1':
        assert load.node_id == section.to_node
    elif load.location == '0':
        assert load.node_id == section.from_node


def test_switching_location_s_connects_to_section_from_side(sample_model):
    if not sample_model.devices:
        return
    device = next((item for item in sample_model.devices if item.location == 'S'), sample_model.devices[0])
    section = sample_model.section_by_id[device.section_id]
    if device.location == 'S':
        assert device.terminal_side == 0
        assert device.node_id == section.from_node
    assert device.on_off in (0, 1)


def test_missing_catalog_types_do_not_block_any_feeder(ds, feeder_shorts):
    """Every feeder in the loaded TXT set must build; missing IDs auto-map or use DEFAULT."""
    for name in feeder_shorts:
        model = build_feeder_model(ds, name)
        assert model.name == name
        assert len(model.lines) >= 1
