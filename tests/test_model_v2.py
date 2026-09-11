from pathlib import Path
import pytest

from igea_dgs.dataset import CymdistDataset

RED = Path('/mnt/data/RED_030826(1).txt')
LOAD = Path('/mnt/data/CARGA_030826(1).txt')
EQUIP = Path('/mnt/data/BD_Equipo_V261124 (1)(1).txt')

@pytest.fixture(scope='module')
def ds():
    return CymdistDataset.from_files(RED, LOAD, EQUIP)


def test_build_in111_without_any_reference_dgs(ds):
    from igea_dgs.model import build_feeder_model

    model = build_feeder_model(ds, 'IN111')
    assert model.network_id == 'NET_2030_142_IN111'
    assert model.name == 'IN111'
    assert model.nominal_kv == 10.0
    assert model.source_node == 'NODE_2030_142_IN111'
    assert len(model.lines) == 1934
    assert len(model.nodes) == 1936
    assert len(model.loads) == 383
    assert len(model.devices) == 791
    assert not model.unresolved_line_types


def test_default_line_type_is_media_specific(ds):
    from igea_dgs.model import build_feeder_model

    model = build_feeder_model(ds, 'IN111')
    defaults = {line.type_key for line in model.lines if line.source_type_code == 'DEFAULT'}
    assert defaults <= {'LINE:DEFAULT', 'CABLE:DEFAULT'}
    assert defaults
    for key in defaults:
        typ = model.line_types[key]
        assert typ.source_table in {'LINE', 'CONCENTRIC NEUTRAL CABLE'}


def test_load_location_1_connects_to_section_to_node(ds):
    from igea_dgs.model import build_feeder_model

    model = build_feeder_model(ds, 'IN111')
    load = model.loads[0]
    section = model.section_by_id[load.section_id]
    assert load.location == '1'
    assert load.node_id == section.to_node


def test_switching_location_s_connects_to_section_from_side(ds):
    from igea_dgs.model import build_feeder_model

    model = build_feeder_model(ds, 'IN111')
    device = model.devices[0]
    section = model.section_by_id[device.section_id]
    assert device.location == 'S'
    assert device.terminal_side == 0
    assert device.node_id == section.from_node
    assert device.on_off == 1


def test_unresolved_type_is_fatal_in_strict_mode_and_alias_is_external(ds):
    from igea_dgs.model import build_feeder_model, UnresolvedLineTypesError

    with pytest.raises(UnresolvedLineTypesError) as exc:
        build_feeder_model(ds, 'NA205')
    assert 'AA05001D' in str(exc.value)

    model = build_feeder_model(ds, 'NA205', aliases={'AA05001D': 'AA05003D'})
    assert model.line_type_aliases == {'AA05001D': 'AA05003D'}
    assert not model.unresolved_line_types
