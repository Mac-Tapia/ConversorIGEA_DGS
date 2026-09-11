from pathlib import Path
import json
import pytest

from igea_dgs.dataset import CymdistDataset

RED = Path('/mnt/data/RED_030826(1).txt')
LOAD = Path('/mnt/data/CARGA_030826(1).txt')
EQUIP = Path('/mnt/data/BD_Equipo_V261124 (1)(1).txt')

@pytest.fixture(scope='module')
def ds():
    return CymdistDataset.from_files(RED, LOAD, EQUIP)


def test_convert_one_feeder(ds, tmp_path):
    from igea_dgs.batch import convert_selection

    manifest = convert_selection(ds, ['IN111'], tmp_path)
    assert manifest['summary'] == {'requested': 1, 'ok': 1, 'failed': 0}
    item = manifest['feeders'][0]
    assert item['feeder'] == 'IN111'
    assert item['status'] == 'ok'
    assert (tmp_path / 'IN111.dgs').exists()
    assert (tmp_path / 'IN111_validation.json').exists()


def test_convert_multiple_feeders(ds, tmp_path):
    from igea_dgs.batch import convert_selection

    manifest = convert_selection(ds, ['IN111', 'TA121'], tmp_path)
    assert manifest['summary']['requested'] == 2
    assert manifest['summary']['ok'] == 2
    assert {x['feeder'] for x in manifest['feeders']} == {'IN111','TA121'}


def test_all_mode_is_independent_and_reports_unresolved_feeders(ds, tmp_path):
    from igea_dgs.batch import convert_selection

    manifest = convert_selection(ds, None, tmp_path, all_feeders=True)
    assert manifest['summary']['requested'] == 96
    assert manifest['summary']['ok'] + manifest['summary']['failed'] == 96
    assert manifest['summary']['failed'] > 0
    in111 = next(x for x in manifest['feeders'] if x['feeder'] == 'IN111')
    na205 = next(x for x in manifest['feeders'] if x['feeder'] == 'NA205')
    assert in111['status'] == 'ok'
    assert na205['status'] == 'failed'
    assert 'AA05001D' in na205['error']
    assert (tmp_path / 'IN111.dgs').exists()
    assert not (tmp_path / 'NA205.dgs').exists()


def test_external_alias_file_can_resolve_missing_type(ds, tmp_path):
    from igea_dgs.batch import convert_selection, load_aliases

    alias_path = tmp_path / 'aliases.json'
    alias_path.write_text(json.dumps({'AA05001D': 'AA05003D'}), encoding='utf-8')
    aliases = load_aliases(alias_path)
    manifest = convert_selection(ds, ['NA205'], tmp_path / 'out', aliases=aliases)
    assert manifest['summary']['ok'] == 1
    assert manifest['feeders'][0]['aliases'] == {'AA05001D': 'AA05003D'}


def test_cli_list_and_convert_do_not_accept_reference_dgs(tmp_path, capsys):
    from igea_dgs.cli import main

    rc = main(['list','--red',str(RED),'--loads',str(LOAD),'--equipment',str(EQUIP)])
    assert rc == 0
    listing = capsys.readouterr().out
    assert 'IN111' in listing and 'TA121' in listing

    out = tmp_path / 'single'
    rc = main(['convert','--red',str(RED),'--loads',str(LOAD),'--equipment',str(EQUIP),'--feeder','IN111','--out-dir',str(out)])
    assert rc == 0
    assert (out / 'IN111.dgs').exists()
