from __future__ import annotations

from pathlib import Path

import pytest

from igea_dgs.batch import convert_group, convert_selection
from igea_dgs.feeder_metadata import (
    FeederAssignment,
    read_feeder_metadata,
    validate_assignments,
    write_feeder_metadata,
)


def test_conversion_publishes_exact_load_sed_and_source_ownership(ds, sample_feeder, tmp_path):
    manifest = convert_selection(
        ds, [sample_feeder], tmp_path / 'salida', include_geography=False,
    )
    item = manifest['feeders'][0]
    metadata_path = Path(item['feeder_metadata'])
    metadata = read_feeder_metadata(metadata_path, expected_dgs=Path(item['dgs']))
    assignments = metadata['assignments']

    lod = [row for row in assignments if row['class_name'] == 'ElmLod']
    seds = [row for row in assignments if row['class_name'] == 'ElmSubstat']
    sources = [row for row in assignments if row['class_name'] == 'ElmXnet']
    assert len(lod) == item['counts']['dgs_loads']
    assert len(seds) == item['counts']['dgs_seds']
    assert len(sources) == item['counts']['dgs_sources'] == 1
    assert {row['feeder'] for row in lod + seds + sources} == {sample_feeder}
    assert {row['network_id'] for row in lod + seds + sources} == {item['network_id']}
    assert all(row['dgs_fid'] and row['terminal'] for row in lod + sources)
    assert all(row['dgs_fid'] and row['substation'] for row in seds)


def test_group_metadata_keeps_loads_and_seds_separated_by_source_feeder(tmp_path):
    pytest.importorskip('pyproj')
    from synthetic_export import ExportSpec, load_export

    dataset = load_export(
        ExportSpec(feeders=2, sections_per_feeder=5, loads_per_feeder=2),
        tmp_path / 'entrada',
    )
    expected = {network.rsplit('_', 1)[-1] for network in dataset.feeder_ids()}
    out = tmp_path / 'salida'
    result = convert_group(
        dataset, list(dataset.feeder_ids()), out, name='RED_UNIDA',
        source_crs='EPSG:32718',
    )
    assert result['status'] == 'ok', result.get('error')
    metadata = read_feeder_metadata(
        out / 'RED_UNIDA_feeder_metadata.json', expected_dgs=out / 'RED_UNIDA.dgs',
    )
    assignments = metadata['assignments']
    loads = [row for row in assignments if row['class_name'] == 'ElmLod']
    seds = [row for row in assignments if row['class_name'] == 'ElmSubstat']
    assert {row['feeder'] for row in loads} == expected
    assert {row['feeder'] for row in seds} == expected
    assert result['feeder_metadata'] == str(out / 'RED_UNIDA_feeder_metadata.json')


def test_metadata_hash_detects_dgs_changed_after_export(tmp_path):
    dgs = tmp_path / 'RED.dgs'
    dgs.write_text('DGS original', encoding='ascii')
    sidecar = tmp_path / 'RED_feeder_metadata.json'
    assignments = [FeederAssignment(
        class_name='ElmLod', dgs_fid='101', loc_name='LOAD_A', feeder='AL101',
        network_id='NET_AL101', terminal='NODE_A', substation='',
        section_id='SEC_A', node_id='NODE_A',
    )]
    write_feeder_metadata(assignments, dgs, sidecar)
    assert read_feeder_metadata(sidecar, expected_dgs=dgs)['dgs_sha256']

    dgs.write_text('DGS reemplazado', encoding='ascii')
    with pytest.raises(ValueError, match='SHA-256'):
        read_feeder_metadata(sidecar, expected_dgs=dgs)


def test_assignment_identity_must_be_unique():
    row = FeederAssignment(
        class_name='ElmLod', dgs_fid='101', loc_name='LOAD_A', feeder='AL101',
        network_id='NET_AL101', terminal='NODE_A', substation='',
    )
    with pytest.raises(ValueError, match='duplicad'):
        validate_assignments([row, row])


@pytest.mark.parametrize('class_name', ['ElmSwitch', 'TypLne', ''])
def test_assignment_rejects_class_outside_target_scope(class_name):
    row = FeederAssignment(
        class_name=class_name, dgs_fid='101', loc_name='OBJ', feeder='AL101',
        network_id='NET_AL101', terminal='', substation='',
    )
    with pytest.raises(ValueError, match='clase'):
        validate_assignments([row])