from __future__ import annotations


def _model():
    from igea_dgs.model import CapacitorBank, FeederModel, Node

    return FeederModel(
        name='CA101', network_id='NET_CA101', nominal_kv=10,
        source_node='N1', nodes={'N1': Node('N1', 0, 0)},
        lines=[], loads=[], devices=[], line_types={},
        capacitors=[
            CapacitorBank('BC_450', 'N1', 'NET_CA101', 'CA101', 'ABC',
                          150, 3, 450, 10, True),
            CapacitorBank('BC_SIN_Q', 'N1', 'NET_CA101', 'CA101', 'A',
                          None, 1, None, 10, True,
                          issues=('MISSING_CAPACITOR_CAPACITY',)),
        ],
    )


def test_dgs_exports_only_complete_source_bank_with_exact_values(tmp_path):
    from igea_dgs.dgs import write_dgs
    from igea_dgs.validate import parse_dgs

    path = tmp_path / 'CA101.dgs'
    manifest = write_dgs(_model(), path)
    tables = parse_dgs(path)
    rows = tables['ElmShnt']['rows_dict']

    assert len(rows) == 1
    assert rows[0]['loc_name'] == 'BC_450'
    assert rows[0]['ctech'] == '1'
    assert rows[0]['shtype'] == '2'
    assert rows[0]['qcapn'] == '0.15'
    assert rows[0]['ncapx'] == rows[0]['ncapa'] == '3'
    assert rows[0]['qtotn'] == '0.45'
    assert rows[0]['ushnm'] == '10'
    assert rows[0]['outserv'] == '0'
    assert manifest.shunt_fids == {('NET_CA101', 'BC_450'): rows[0]['FID']}
    assert manifest.capacitor_issues == ({
        'capacitor_id': 'BC_SIN_Q', 'feeder': 'CA101',
        'network_id': 'NET_CA101', 'node_id': 'N1',
        'codes': ['MISSING_CAPACITOR_CAPACITY'],
    },)


def test_complete_bank_has_one_terminal_cubicle(tmp_path):
    from igea_dgs.dgs import write_dgs
    from igea_dgs.validate import parse_dgs

    path = tmp_path / 'CA101.dgs'
    manifest = write_dgs(_model(), path)
    tables = parse_dgs(path)
    shunt_fid = manifest.shunt_fids[('NET_CA101', 'BC_450')]
    cubicles = [row for row in tables['StaCubic']['rows_dict'] if row['obj_id'] == shunt_fid]

    assert len(cubicles) == 1
    assert cubicles[0]['fold_id'] == manifest.node_fids['N1']


def test_feeder_metadata_includes_shunt_assignment(tmp_path):
    from igea_dgs.dgs import write_dgs
    from igea_dgs.feeder_metadata import assignments_from_model, read_feeder_metadata, write_feeder_metadata

    model = _model()
    manifest = write_dgs(model, tmp_path / 'CA101.dgs')
    shunts = [row for row in assignments_from_model(model, manifest)
              if row.class_name == 'ElmShnt']

    assert len(shunts) == 1
    assert shunts[0].loc_name == 'BC_450'
    assert shunts[0].terminal == 'N1'
    assert shunts[0].feeder == 'CA101'
    assert shunts[0].network_id == 'NET_CA101'
    sidecar = tmp_path / 'CA101_feeder_metadata.json'
    write_feeder_metadata(
        assignments_from_model(model, manifest), tmp_path / 'CA101.dgs', sidecar,
        capacitor_banks=manifest.capacitor_banks,
        capacitor_issues=manifest.capacitor_issues,
    )
    payload = read_feeder_metadata(sidecar, expected_dgs=tmp_path / 'CA101.dgs')
    assert payload['capacitor_banks'][0]['total_source_mvar'] == .45
    assert payload['capacitor_issues'][0]['codes'] == ['MISSING_CAPACITOR_CAPACITY']
