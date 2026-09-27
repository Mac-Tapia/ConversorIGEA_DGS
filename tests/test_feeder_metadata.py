from __future__ import annotations

import json

import pytest

from igea_dgs.combine import combine_models
from igea_dgs.dgs import write_dgs
from igea_dgs.feeder_metadata import (
    FeederAssignment,
    read_feeder_metadata,
    validate_assignments,
    write_feeder_metadata,
)
from igea_dgs.model import FeederModel, Line, LineType, Load, Node, Sed


def _model(feeder: str, prefix: str) -> FeederModel:
    network_id = f'NET_2026_229_{feeder}'
    source, terminal = f'{prefix}SRC', f'{prefix}N1'
    section = f'{prefix}SEC'
    device = f'{prefix}D1'
    sed_name = f'SE_{feeder}'
    typ = LineType('LINE:AA05003D', 'AA05003D', 'LINE', 0.6, 1.2, 0.4, 1.0, 3.0, 1.0, 180)
    load = Load(
        section, device, 'C1', '1', terminal, 0.05, 0.01, 0.98, 100, 0, 'ABC',
        sed_code=sed_name, display_name='CARGA_DUPLICADA', feeder=feeder,
        network_id=network_id,
    )
    sed = Sed(
        sed_name, sed_name, terminal, 100, section, device, (section, device),
        feeder=feeder, network_id=network_id,
    )
    line = Line(section, source, terminal, 'ABC', typ.key, typ.code, 100, True)
    return FeederModel(
        name=feeder, network_id=network_id, nominal_kv=22.9, source_node=source,
        nodes={source: Node(source, 0, 0), terminal: Node(terminal, 100, 0)},
        lines=[line], loads=[load], devices=[], line_types={typ.key: typ},
        section_by_id={section: line}, seds=[sed],
    )


def test_dgs_manifest_maps_each_load_and_source_to_its_original_feeder(tmp_path):
    model, _ = combine_models([_model('NA203', 'A'), _model('NA205', 'B')], name='NA203_NA205')
    manifest = write_dgs(model, tmp_path / 'NA203_NA205.dgs')

    loads = [r for r in manifest.feeder_assignments if r.class_name == 'ElmLod']
    sources = [r for r in manifest.feeder_assignments if r.class_name == 'ElmXnet']
    assert {(r.feeder, r.network_id) for r in loads} == {
        ('NA203', 'NET_2026_229_NA203'), ('NA205', 'NET_2026_229_NA205'),
    }
    assert {r.feeder for r in sources} == {'NA203', 'NA205'}
    assert len(loads) == 2 and len(sources) == 2
    assert {r.loc_name for r in loads} == {'CARGA_DUPLICADA'}
    assert {r.terminal for r in loads} == {'SE_NA203_BT', 'SE_NA205_BT'}


def test_metadata_is_bound_to_the_exact_dgs_hash(tmp_path):
    dgs = tmp_path / 'red.dgs'
    dgs.write_text('DGS original', encoding='utf-8')
    record = FeederAssignment('ElmXnet', '1', 'External Grid NA203', 'NA203',
                              'NET_NA203', 'SOURCE', '')
    path = write_feeder_metadata([record], dgs, tmp_path / 'red_feeder_metadata.json')
    metadata = read_feeder_metadata(path, expected_dgs=dgs)
    assert metadata.assignments == (record,)

    dgs.write_text('DGS alterado', encoding='utf-8')
    with pytest.raises(ValueError, match='SHA-256'):
        read_feeder_metadata(path, expected_dgs=dgs)


@pytest.mark.parametrize('record,match', [
    (FeederAssignment('', '1', 'X', 'NA203', 'NET', 'T', ''), 'clase'),
    (FeederAssignment('ElmLod', '', 'X', 'NA203', 'NET', 'T', ''), 'FID'),
    (FeederAssignment('ElmLne', '1', 'X', 'NA203', 'NET', 'T', ''), 'clase'),
    (FeederAssignment('ElmLod', '1', '', 'NA203', 'NET', 'T', ''), 'nombre'),
    (FeederAssignment('ElmLod', '1', 'X', '', 'NET', 'T', ''), 'alimentador'),
])
def test_invalid_records_fail_closed(record, match):
    with pytest.raises(ValueError, match=match):
        validate_assignments([record])


def test_duplicate_runtime_identity_is_rejected():
    record = FeederAssignment('ElmLod', '1', 'SE1', 'NA203', 'NET', 'SE1_BT', 'SE1')
    duplicate = FeederAssignment('ElmLod', '2', 'SE1', 'NA205', 'NET2', 'SE1_BT', 'SE1')
    with pytest.raises(ValueError, match='duplicada'):
        validate_assignments([record, duplicate])


def test_written_json_declares_all_supported_powerfactory_classes(tmp_path):
    dgs = tmp_path / 'red.dgs'
    dgs.write_bytes(b'DGS')
    record = FeederAssignment('ElmXnet', '1', 'External Grid NA203', 'NA203',
                              'NET_NA203', 'SOURCE', '')
    path = write_feeder_metadata([record], dgs, tmp_path / 'metadata.json')
    raw = json.loads(path.read_text(encoding='utf-8'))
    assert raw['target_classes'] == ['ElmLod', 'ElmSym', 'ElmXnet']
    assert raw['schema_version'] == 1
