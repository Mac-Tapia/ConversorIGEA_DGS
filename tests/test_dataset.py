from pathlib import Path

RED = Path('/mnt/data/RED_030826(1).txt')
LOAD = Path('/mnt/data/CARGA_030826(1).txt')
EQUIP = Path('/mnt/data/BD_Equipo_V261124 (1)(1).txt')


def test_dataset_parses_all_source_tables_once():
    from igea_dgs.dataset import CymdistDataset

    ds = CymdistDataset.from_files(RED, LOAD, EQUIP)
    assert len(ds.feeder_ids()) == 96
    assert len(ds.sources) == 96
    assert len(ds.sections) == 38657
    assert len(ds.line_configurations) == 38657
    assert len(ds.nodes) == 38681
    assert len(ds.load_placements) == 7287
    assert len(ds.customer_loads) == 7287
    assert len(ds.switch_settings) == 17
    assert len(ds.sectionalizer_settings) == 15196
    assert len(ds.intermediate_nodes) == 37283


def test_dataset_resolves_short_name_network_id_and_joins_load_location():
    from igea_dgs.dataset import CymdistDataset

    ds = CymdistDataset.from_files(RED, LOAD, EQUIP)
    assert ds.resolve_feeder('IN111') == 'NET_2030_142_IN111'
    assert ds.resolve_feeder('net_2030_142_in111') == 'NET_2030_142_IN111'
    assert ds.resolve_feeder('TA121') == 'NET_2030_166_TA121'
    first = next(r for r in ds.customer_loads.values() if r['SectionID'] in ds.feeder_section_ids('NET_2030_142_IN111'))
    placement = ds.load_placements[(first['SectionID'], first['DeviceNumber'])]
    assert placement['Location'] == '1'
    assert placement['LoadType'] == 'SPOT'


def test_every_section_has_unique_owner_and_configuration():
    from igea_dgs.dataset import CymdistDataset

    ds = CymdistDataset.from_files(RED, LOAD, EQUIP)
    assert len(ds.section_owner) == 38657
    assert set(ds.section_owner) == set(ds.line_configurations)
