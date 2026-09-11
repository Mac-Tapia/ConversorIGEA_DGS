from pathlib import Path
import pytest

from igea_dgs.dataset import CymdistDataset
from igea_dgs.model import build_feeder_model
from igea_dgs.schema import load_schema

RED = Path('/mnt/data/RED_030826(1).txt')
LOAD = Path('/mnt/data/CARGA_030826(1).txt')
EQUIP = Path('/mnt/data/BD_Equipo_V261124 (1)(1).txt')

@pytest.fixture(scope='module')
def model():
    ds = CymdistDataset.from_files(RED, LOAD, EQUIP)
    return build_feeder_model(ds, 'IN111')


def _parse(path):
    from igea_dgs.validate import parse_dgs
    return parse_dgs(path)


def test_writer_uses_schema_exactly_and_is_deterministic(model, tmp_path):
    from igea_dgs.dgs import write_dgs

    a = tmp_path / 'a.dgs'
    b = tmp_path / 'b.dgs'
    write_dgs(model, a)
    write_dgs(model, b)
    assert a.read_bytes() == b.read_bytes()
    text = a.read_text(encoding='utf-8')
    schema = load_schema()
    for table in ('General','ElmNet','ElmTerm','TypLne','ElmLne','ElmLod','ElmXnet','StaCubic','StaSwitch'):
        assert schema.header(table) in text
    lowered = text.lower()
    assert 'na205' not in lowered
    assert 'reference-dgs' not in lowered


def test_writer_has_precise_cubicles_and_load_terminal(model, tmp_path):
    from igea_dgs.dgs import write_dgs

    out = tmp_path / 'IN111.dgs'
    manifest = write_dgs(model, out)
    tables = _parse(out)
    assert len(tables['ElmLne']['rows']) == len(model.lines)
    assert len(tables['ElmLod']['rows']) == len(model.loads)
    assert len(tables['StaCubic']['rows']) == 2 * len(model.lines) + len(model.loads) + 1

    line = model.lines[0]
    line_fid = manifest.line_fids[line.section_id]
    cubics = [r for r in tables['StaCubic']['rows_dict'] if r['obj_id'] == line_fid]
    assert {(r['fold_id'], r['obj_bus']) for r in cubics} == {
        (manifest.node_fids[line.from_node], '0'),
        (manifest.node_fids[line.to_node], '1'),
    }

    load = model.loads[0]
    load_fid = manifest.load_fids[(load.section_id, load.device_number)]
    load_cubic = next(r for r in tables['StaCubic']['rows_dict'] if r['obj_id'] == load_fid)
    assert load_cubic['fold_id'] == manifest.node_fids[load.node_id]


def test_switches_are_children_of_the_correct_section_terminal_cubic(model, tmp_path):
    from igea_dgs.dgs import write_dgs

    out = tmp_path / 'IN111.dgs'
    manifest = write_dgs(model, out)
    tables = _parse(out)
    assert len(tables['StaSwitch']['rows']) == len(model.devices)
    device = model.devices[0]
    sw = next(r for r in tables['StaSwitch']['rows_dict'] if r['loc_name'] == device.eq_number)
    assert sw['fold_id'] == manifest.line_cubic_fids[(device.section_id, device.terminal_side)]
    assert sw['on_off'] == str(device.on_off)
