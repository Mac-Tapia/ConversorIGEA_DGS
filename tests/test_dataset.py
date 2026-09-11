from igea_dgs.dataset import CymdistDataset


def test_dataset_parses_all_source_tables_once(igea_paths):
    red, loads, equip = igea_paths
    ds = CymdistDataset.from_files(red, loads, equip)
    n_feeders = len(ds.feeder_ids())
    assert n_feeders >= 1
    assert len(ds.sources) == n_feeders
    assert len(ds.sections) >= 1
    assert len(ds.line_configurations) == len(ds.sections)
    assert len(ds.nodes) >= 1
    assert len(ds.sections) == len(ds.section_owner)
    # Loads / switches / intermediate nodes are optional per export
    assert len(ds.customer_loads) == len(ds.load_placements)


def test_dataset_resolves_short_name_network_id_and_joins_load_location(ds, sample_feeder):
    from igea_dgs.naming import feeder_short_name

    network_id = ds.resolve_feeder(sample_feeder)
    assert feeder_short_name(network_id) == sample_feeder
    assert ds.resolve_feeder(network_id.lower()) == network_id
    assert ds.resolve_feeder(sample_feeder.lower()) == network_id

    section_ids = ds.feeder_section_ids(network_id)
    loads_on_feeder = [r for r in ds.customer_loads.values() if r['SectionID'] in section_ids]
    if not loads_on_feeder:
        return
    first = loads_on_feeder[0]
    placement = ds.load_placements[(first['SectionID'], first['DeviceNumber'])]
    assert placement['Location'] in {'0', '1'}
    assert placement.get('LoadType', '') != ''


def test_every_section_has_unique_owner_and_configuration(ds):
    assert len(ds.sections) == len(ds.section_owner) == len(ds.line_configurations)
    assert set(ds.sections) == set(ds.section_owner) == set(ds.line_configurations)
