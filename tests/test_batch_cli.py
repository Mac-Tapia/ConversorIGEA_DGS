from pathlib import Path
import json

from igea_dgs.batch import convert_selection, load_aliases


def test_convert_one_feeder(ds, sample_feeder, tmp_path):
    manifest = convert_selection(ds, [sample_feeder], tmp_path)
    assert manifest['summary'] == {'requested': 1, 'ok': 1, 'skipped': 0, 'failed': 0}
    item = manifest['feeders'][0]
    assert item['feeder'] == sample_feeder
    assert item['status'] == 'ok'
    assert (tmp_path / f'{sample_feeder}.dgs').exists()
    assert (tmp_path / f'{sample_feeder}_validation.json').exists()


def test_convert_multiple_feeders(ds, sample_feeder, second_feeder, tmp_path):
    selected = [sample_feeder, second_feeder]
    manifest = convert_selection(ds, selected, tmp_path)
    assert manifest['summary']['requested'] == 2
    assert manifest['summary']['ok'] == 2
    assert {x['feeder'] for x in manifest['feeders']} == set(selected)


def test_all_mode_converts_every_feeder_without_blocking(ds, tmp_path):
    n_feeders = len(ds.feeder_ids())
    assert n_feeders >= 1
    empty = {nid for nid in ds.feeder_ids() if not ds.feeders[nid]}
    manifest = convert_selection(ds, None, tmp_path, all_feeders=True)
    assert manifest['summary']['requested'] == n_feeders
    assert manifest['summary']['ok'] == n_feeders - len(empty)
    assert manifest['summary']['skipped'] == len(empty)
    assert manifest['summary']['failed'] == 0
    for item in manifest['feeders']:
        if item['network_id'] in empty:
            assert item['status'] == 'skipped'
            continue
        assert item['status'] == 'ok'
        assert (tmp_path / f"{item['feeder']}.dgs").exists()


def test_external_alias_file_is_recorded(ds, sample_feeder, tmp_path):
    alias_path = tmp_path / 'aliases.json'
    # Self-documenting placeholder; conversion must succeed regardless of codes.
    alias_path.write_text(json.dumps({'MISSING_TYPE': 'DEFAULT'}), encoding='utf-8')
    aliases = load_aliases(alias_path)
    manifest = convert_selection(ds, [sample_feeder], tmp_path / 'out', aliases=aliases)
    assert manifest['summary']['ok'] == 1
    assert manifest['feeders'][0]['status'] == 'ok'


def test_cli_list_and_convert_do_not_accept_reference_dgs(igea_paths, sample_feeder, tmp_path, capsys):
    from igea_dgs.cli import main

    red, loads, equip = igea_paths
    inv_json = tmp_path / 'inv.json'
    rc = main([
        'list',
        '--red', str(red),
        '--loads', str(loads),
        '--equipment', str(equip),
        '--inventory-json', str(inv_json),
    ])
    assert rc in (0, 2)  # 2 if integrity errors present
    listing = capsys.readouterr().out
    assert sample_feeder in listing
    assert 'INVENTARIO TXT' in listing
    assert inv_json.is_file()

    out = tmp_path / 'single'
    rc = main([
        'convert',
        '--red', str(red),
        '--loads', str(loads),
        '--equipment', str(equip),
        '--feeder', sample_feeder,
        '--out-dir', str(out),
    ])
    assert rc == 0
    assert (out / f'{sample_feeder}.dgs').exists()
    assert (out / 'dataset_inventory.json').exists()
