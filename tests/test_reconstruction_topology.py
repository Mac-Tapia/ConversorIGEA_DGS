from __future__ import annotations

from pathlib import Path

from igea_dgs.dataset import CymdistDataset
from igea_dgs.reconstruction import EvidenceLevel, ReconstructionPolicy, reconstruct_dataset


NETWORK = 'UTILITY_X_F-A'


def _dataset(nodes, sections, *, source='N0') -> CymdistDataset:
    section_ids = tuple(sections)
    return CymdistDataset(
        red_path=Path('red.txt'), loads_path=Path('loads.txt'),
        equipment_path=Path('equipment.txt'),
        headnodes={source: NETWORK},
        nodes=nodes,
        sources={NETWORK: {
            'NetworkID': NETWORK, 'NodeID': source, 'DesiredVoltage': '10',
            'Company': 'UTILITY_X',
        }},
        line_configurations={
            sid: {'SectionID': sid, 'LineCableID': 'C1', 'Length': '1'}
            for sid in section_ids
        },
        sections=sections,
        section_owner={sid: NETWORK for sid in section_ids},
        feeders={NETWORK: section_ids},
        switch_settings=(), sectionalizer_settings=(), intermediate_nodes=(),
        load_placements={}, customer_loads={}, equipment_tables={},
    )


def _node(node_id, x, y, *, kv='10', company='UTILITY_X', phase='ABC'):
    return {
        'NodeID': node_id, 'CoordX': str(x), 'CoordY': str(y),
        'NominalVoltageKV': kv, 'Company': company, 'Phase': phase,
    }


def _result(dataset, *, tolerance=1.0):
    return reconstruct_dataset(
        dataset,
        ReconstructionPolicy(topology_snap_tolerance=tolerance),
        [],
    )


def test_recovers_a_referenced_node_omitted_from_node_table():
    from igea_dgs.reconstruction_topology import repair_missing_nodes

    dataset = _dataset(
        {'N0': _node('N0', 0, 0)},
        {'S1': {
            'SectionID': 'S1', 'FromNodeID': 'N0', 'ToNodeID': 'N_MISSING',
            'ToCoordX': '4', 'ToCoordY': '5', 'Phase': 'ABC',
        }},
    )
    result = _result(dataset)
    repair_missing_nodes(result)

    assert result.dataset.nodes['N_MISSING']['CoordX'] == '4'
    [decision] = result.report.decisions
    assert decision.rule == 'RECOVER_REFERENCED_NODE'
    assert decision.level is EvidenceLevel.ENGINEERING_ASSUMPTION


def test_creates_a_deterministic_terminal_for_a_blank_endpoint():
    from igea_dgs.reconstruction_topology import repair_missing_nodes

    dataset = _dataset(
        {'N0': _node('N0', 0, 0)},
        {'S1': {
            'SectionID': 'S1', 'FromNodeID': 'N0', 'ToNodeID': '',
            'ToCoordX': '4', 'ToCoordY': '5', 'Phase': 'ABC',
        }},
    )
    result = _result(dataset)
    repair_missing_nodes(result)

    assert result.dataset.sections['S1']['ToNodeID'] == 'N_DERIVED_S1_TO'
    assert 'N_DERIVED_S1_TO' in result.dataset.nodes
    assert {item.rule for item in result.report.decisions} == {
        'CREATE_TERMINAL_NODE',
    }


def test_repairs_a_unique_compatible_same_voltage_connection():
    from igea_dgs.reconstruction_topology import repair_discontinuities

    dataset = _dataset(
        {
            'N0': _node('N0', -10, 0), 'R': _node('R', 0, 0),
            'A': _node('A', 0.2, 0), 'B': _node('B', 10, 0),
        },
        {
            'S0': {'SectionID': 'S0', 'FromNodeID': 'N0', 'ToNodeID': 'R', 'Phase': 'ABC'},
            'I1': {'SectionID': 'I1', 'FromNodeID': 'A', 'ToNodeID': 'B', 'Phase': 'ABC'},
        },
    )
    result = _result(dataset)
    repair_discontinuities(result)

    assert result.dataset.sections['I1']['FromNodeID'] == 'R'
    decision = result.report.decisions[-1]
    assert decision.rule == 'UNIQUE_COMPATIBLE_CONNECTION'
    assert decision.candidates == ('R',)


def test_ranked_ambiguous_connection_is_deterministic_and_keeps_candidates():
    from igea_dgs.reconstruction_topology import repair_discontinuities

    dataset = _dataset(
        {
            'N0': _node('N0', 0, 10),
            'R1': _node('R1', -1, 0), 'R2': _node('R2', 1, 0),
            'A': _node('A', 0, 0), 'B': _node('B', 0, -10),
        },
        {
            'S1': {'SectionID': 'S1', 'FromNodeID': 'N0', 'ToNodeID': 'R1', 'Phase': 'ABC'},
            'S2': {'SectionID': 'S2', 'FromNodeID': 'N0', 'ToNodeID': 'R2', 'Phase': 'ABC'},
            'I1': {'SectionID': 'I1', 'FromNodeID': 'A', 'ToNodeID': 'B', 'Phase': 'ABC'},
        },
    )
    result = _result(dataset, tolerance=1.1)
    repair_discontinuities(result)

    assert result.dataset.sections['I1']['FromNodeID'] == 'R1'
    decision = result.report.decisions[-1]
    assert decision.rule == 'RANKED_AMBIGUOUS_CONNECTION'
    assert decision.level is EvidenceLevel.ENGINEERING_ASSUMPTION
    assert decision.candidates == ('R1', 'R2')


def test_discontinuity_repair_excludes_a_closer_node_at_another_voltage():
    from igea_dgs.reconstruction_topology import repair_discontinuities

    dataset = _dataset(
        {
            'N0': _node('N0', -10, 0),
            'R_BAD': _node('R_BAD', 0, 0, kv='22.9'),
            'R_OK': _node('R_OK', 0.5, 0, kv='10'),
            'A': _node('A', 0.1, 0, kv='10'), 'B': _node('B', 10, 0, kv='10'),
        },
        {
            'S0': {'SectionID': 'S0', 'FromNodeID': 'N0', 'ToNodeID': 'R_BAD', 'Phase': 'ABC'},
            'S1': {'SectionID': 'S1', 'FromNodeID': 'N0', 'ToNodeID': 'R_OK', 'Phase': 'ABC'},
            'I1': {'SectionID': 'I1', 'FromNodeID': 'A', 'ToNodeID': 'B', 'Phase': 'ABC'},
        },
    )
    result = _result(dataset)
    repair_discontinuities(result)

    assert result.dataset.sections['I1']['FromNodeID'] == 'R_OK'
    assert result.report.decisions[-1].candidates == ('R_OK',)


def test_discontinuity_repair_never_crosses_company_scope():
    from igea_dgs.reconstruction_topology import repair_discontinuities

    dataset = _dataset(
        {
            'N0': _node('N0', -10, 0),
            'R_OTHER': _node('R_OTHER', 0, 0, company='UTILITY_Y'),
            'R_SAME': _node('R_SAME', 0.5, 0),
            'A': _node('A', 0.1, 0), 'B': _node('B', 10, 0),
        },
        {
            'S0': {'SectionID': 'S0', 'FromNodeID': 'N0', 'ToNodeID': 'R_OTHER', 'Phase': 'ABC'},
            'S1': {'SectionID': 'S1', 'FromNodeID': 'N0', 'ToNodeID': 'R_SAME', 'Phase': 'ABC'},
            'I1': {'SectionID': 'I1', 'FromNodeID': 'A', 'ToNodeID': 'B', 'Phase': 'ABC'},
        },
    )
    result = _result(dataset)
    repair_discontinuities(result)

    assert result.dataset.sections['I1']['FromNodeID'] == 'R_SAME'
    assert result.report.decisions[-1].candidates == ('R_SAME',)


def test_bridge_transformations_are_preserved_after_model_rules():
    from igea_dgs.puentes import InformePuentes
    from igea_dgs.reconstruction_topology import record_bridge_transformations

    dataset = _dataset(
        {'N0': _node('N0', 0, 0)},
        {'S1': {'SectionID': 'S1', 'FromNodeID': 'N0', 'ToNodeID': 'N0'}},
    )
    result = _result(dataset)
    record_bridge_transformations(
        result, 'F-A', InformePuentes(tramos=2, fundidos=1, interruptores=1),
    )

    assert result.report.to_dict()['metadata']['bridge_transformations']['F-A'] == {
        'tramos': 2,
        'metros': 0.0,
        'fundidos': 1,
        'interruptores': 1,
        'cargas_reubicadas': 0,
        'seds_reubicadas': 0,
        'barras_eliminadas': 0,
        'avisos': [],
    }
