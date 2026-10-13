"""Bancos de fuente: no se inventa potencia, fases ni escalones."""

from __future__ import annotations

from dataclasses import replace

import pytest

from synthetic_export import ExportSpec, load_export


@pytest.mark.parametrize(
    ('row', 'phases', 'per_step', 'steps', 'total'),
    [
        ({'DeviceNumber': 'C1', 'NodeID': 'N1', 'Phase': 'A', 'TotalKVAR': '150'},
         'A', 150.0, 1, 150.0),
        ({'DeviceNumber': 'C2', 'NodeID': 'N1', 'Phase': 'ABC', 'TotalKVAR': '300'},
         'ABC', 300.0, 1, 300.0),
        ({'DeviceNumber': 'C3', 'NodeID': 'N1', 'Phase': 'ABC', 'TotalKVAR': '450'},
         'ABC', 450.0, 1, 450.0),
        ({'DeviceNumber': 'C4', 'NodeID': 'N1', 'Phase': 'ABC',
          'KVARPerStep': '150', 'NumberOfSteps': '3'},
         'ABC', 150.0, 3, 450.0),
    ],
)
def test_capacitor_preserves_source_capacity(row, phases, per_step, steps, total):
    from igea_dgs.model import capacitor_from_source

    bank = capacitor_from_source(row)

    assert bank.phases == phases
    assert bank.kvar_per_step == per_step
    assert bank.steps == steps
    assert bank.total_kvar == total
    assert bank.issues == ()


def test_missing_capacity_is_retained_without_synthetic_number():
    from igea_dgs.model import capacitor_from_source

    bank = capacitor_from_source({'DeviceNumber': 'SIN_Q', 'NodeID': 'N1', 'Phase': 'ABC'})

    assert bank.kvar_per_step is None
    assert bank.total_kvar is None
    assert bank.issues == ('MISSING_CAPACITOR_CAPACITY',)


def test_txt_reader_preserves_shunt_capacitor_setting(tmp_path):
    from igea_dgs.dataset import CymdistDataset
    from synthetic_export import write_export

    red, loads, equipment = write_export(ExportSpec(feeders=1), tmp_path / 'export')
    base = CymdistDataset.from_files(red, loads, equipment)
    network_id = base.feeder_ids()[0]
    node = base.sources[network_id]['NodeID']
    with red.open('a', encoding='utf-8') as stream:
        stream.write(
            '\n[SHUNT CAPACITOR SETTING]\n'
            'FORMAT_SHUNT_CAPACITOR_SETTING=DeviceNumber,NetworkID,NodeID,Phase,'
            'KVARPerStep,NumberOfSteps,TotalKVAR,NominalKV,Status\n'
            f'BC_TXT,{network_id},{node},7,150,3,450,10,1\n'
        )

    dataset = CymdistDataset.from_files(red, loads, equipment)

    assert dataset.capacitor_settings == ({
        'DeviceNumber': 'BC_TXT', 'NetworkID': network_id, 'NodeID': node,
        'Phase': '7', 'KVARPerStep': '150', 'NumberOfSteps': '3',
        'TotalKVAR': '450', 'NominalKV': '10', 'Status': '1',
    },)


def test_feeder_model_keeps_complete_and_incomplete_banks(tmp_path):
    from igea_dgs.model import build_feeder_model

    dataset = load_export(ExportSpec(feeders=1), tmp_path / 'export')
    network_id = dataset.feeder_ids()[0]
    node = dataset.sources[network_id]['NodeID']
    dataset = replace(dataset, capacitor_settings=(
        {'DeviceNumber': 'BC_OK', 'NodeID': node, 'NetworkID': network_id,
         'Phase': 'ABC', 'TotalKVAR': '450'},
        {'DeviceNumber': 'BC_SIN_Q', 'NodeID': node, 'NetworkID': network_id,
         'Phase': 'A'},
    ))

    model = build_feeder_model(dataset, network_id, include_geography=False)

    assert [bank.capacitor_id for bank in model.capacitors] == ['BC_OK', 'BC_SIN_Q']
    assert model.capacitors[0].total_kvar == 450.0
    assert model.capacitors[1].issues == ('MISSING_CAPACITOR_CAPACITY',)


def test_missing_node_and_ambiguous_feeder_are_audited(tmp_path):
    from igea_dgs.source_contract import audit_source

    dataset = load_export(ExportSpec(feeders=2), tmp_path / 'export')
    shared = next(iter(dataset.nodes))
    # Sin NetworkID, un nodo que se fuerza a pertenecer a ambos alimentadores es ambiguo.
    sections = dict(dataset.sections)
    owners = dict(dataset.section_owner)
    feeder_ids = dataset.feeder_ids()
    for index, feeder in enumerate(feeder_ids):
        sid = f'CAP_LINK_{index}'
        sections[sid] = {'SectionID': sid, 'FromNodeID': shared, 'ToNodeID': shared}
        owners[sid] = feeder
    dataset = replace(dataset, sections=sections, section_owner=owners,
                      capacitor_settings=(
                          {'DeviceNumber': 'SIN_NODO', 'TotalKVAR': '100'},
                          {'DeviceNumber': 'AMBIGUO', 'NodeID': shared, 'TotalKVAR': '100'},
                      ))

    codes = [item['code'] for item in audit_source(dataset, {}).as_dict()['issues']]

    assert 'MISSING_CAPACITOR_NODE' in codes
    assert 'AMBIGUOUS_CAPACITOR_FEEDER' in codes
    assert audit_source(dataset, {}).status == 'SOURCE_AUDIT_OK'


def test_combined_model_preserves_capacitor_identity_and_resolves_shared_node():
    from igea_dgs.combine import combine_models
    from igea_dgs.model import CapacitorBank, FeederModel, Node

    def feeder(name: str) -> FeederModel:
        bank = CapacitorBank(
            capacitor_id=f'BC_{name}', node_id='N_SHARED', network_id=f'NET_{name}',
            feeder=name, phases='ABC', kvar_per_step=150, steps=3,
            total_kvar=450, nominal_kv=10, in_service=True,
        )
        return FeederModel(
            name=name, network_id=f'NET_{name}', nominal_kv=10,
            source_node=f'SRC_{name}',
            nodes={f'SRC_{name}': Node(f'SRC_{name}', 0, 0),
                   'N_SHARED': Node('N_SHARED', 10, 0)},
            lines=[], loads=[], devices=[], line_types={}, capacitors=[bank],
        )

    combined, _report = combine_models([feeder('A'), feeder('B')])

    assert [(bank.capacitor_id, bank.node_id, bank.feeder, bank.network_id)
            for bank in combined.capacitors] == [
        ('BC_A', 'N_SHARED@A', 'A', 'NET_A'),
        ('BC_B', 'N_SHARED@B', 'B', 'NET_B'),
    ]
