from __future__ import annotations

from pathlib import Path

import pytest

from igea_dgs.catalog_resolution import (
    CatalogSource,
    EquipmentQuery,
    resolve_equipment,
)
from igea_dgs.dataset import CymdistDataset
from igea_dgs.reconstruction import (
    EvidenceLevel,
    ReconstructionPolicy,
    reconstruct_dataset,
)


def _catalog(name, kind, rows, *, manufacturer=''):
    return CatalogSource(
        name=name, kind=kind, version='2026.1', manufacturer=manufacturer,
        locator=f'https://catalog.example/{name}', sha256='a' * 64,
        rows=tuple(rows),
    )


def _row(code, r1, **attributes):
    return {'ID': code, 'R1': r1, 'R0': r1, 'X1': 0.4, 'X0': 1.2,
            'B1': 0, 'B0': 0, 'Amps': 150, **attributes}


def _query(**changes):
    values = {
        'original_code': 'USER-CODE-17', 'equipment_class': 'LINE',
        'material': 'AAAC', 'section_mm2': 50.0, 'voltage_kv': 10.0,
        'overhead': True, 'manufacturer': '', 'physical': {},
    }
    values.update(changes)
    return EquipmentQuery(**values)


def test_exact_source_beats_manufacturer_and_global():
    catalogs = [
        _catalog('global', 'global', [_row('USER-CODE-17', 0.9)]),
        _catalog('maker', 'manufacturer', [_row('USER-CODE-17', 0.8)], manufacturer='M'),
        _catalog('source', 'source', [_row('USER-CODE-17', 0.7)]),
    ]

    resolved = resolve_equipment(_query(), catalogs, ReconstructionPolicy())

    assert resolved.parameters['R1'] == pytest.approx(0.7)
    assert resolved.rule == 'EXACT_SOURCE'
    assert resolved.catalog is not None and resolved.catalog.name == 'source'


def test_exact_manufacturer_beats_exact_global():
    catalogs = [
        _catalog('global', 'global', [_row('USER-CODE-17', 0.9)]),
        _catalog('maker', 'manufacturer', [_row('USER-CODE-17', 0.8)], manufacturer='M'),
    ]

    resolved = resolve_equipment(
        _query(manufacturer='M'), catalogs, ReconstructionPolicy(),
    )

    assert resolved.parameters['R1'] == pytest.approx(0.8)
    assert resolved.rule == 'EXACT_MANUFACTURER'


def test_exact_source_keeps_its_values_and_fills_only_gaps_from_lower_catalog():
    source = _row('USER-CODE-17', 0.7)
    source['X1'] = ''
    global_row = _row('USER-CODE-17', 0.9)

    resolved = resolve_equipment(
        _query(), [
            _catalog('global', 'global', [global_row]),
            _catalog('source', 'source', [source]),
        ], ReconstructionPolicy(),
    )

    assert resolved.rule == 'EXACT_SOURCE'
    assert resolved.parameters['R1'] == pytest.approx(0.7)
    assert resolved.parameters['X1'] == pytest.approx(0.4)
    assert [item['kind'] for item in resolved.provenance['contributors']] == [
        'source', 'global',
    ]


def test_compatible_attributes_require_class_material_section_voltage_and_aerial():
    good = _row(
        'AAAC-50-10KV', 0.65, EquipmentClass='LINE', Material='AAAC',
        SectionMM2=50, VoltageKV=10, Overhead=True,
    )
    wrong_voltage = {**good, 'ID': 'AAAC-50-22KV', 'VoltageKV': 22.9, 'R1': 0.5}

    resolved = resolve_equipment(
        _query(), [_catalog('global', 'global', [wrong_voltage, good])],
        ReconstructionPolicy(),
    )

    assert resolved.rule == 'COMPATIBLE_ATTRIBUTES'
    assert resolved.source_code == 'AAAC-50-10KV'
    assert resolved.parameters['R1'] == pytest.approx(0.65)


def test_physical_derivation_preserves_the_original_code():
    expected_r1 = 0.028264 * 1000 / 50
    resolved = resolve_equipment(
        _query(physical={'resistivity_ohm_mm2_m': 0.028264}),
        [], ReconstructionPolicy(),
    )

    assert resolved.original_code == 'USER-CODE-17'
    assert resolved.parameters['R1'] == pytest.approx(expected_r1)
    assert resolved.rule == 'PHYSICAL_DERIVATION'
    assert resolved.materialize_row()['ID'] == 'USER-CODE-17'


def test_ambiguous_compatible_tie_uses_provisional_profile_and_records_both():
    common = {
        'EquipmentClass': 'LINE', 'Material': 'AAAC', 'SectionMM2': 50,
        'VoltageKV': 10, 'Overhead': True,
    }
    catalogs = [_catalog('global', 'global', [
        _row('CAT-A', 0.6, **common), _row('CAT-B', 0.7, **common),
    ])]

    resolved = resolve_equipment(_query(), catalogs, ReconstructionPolicy())

    assert resolved.rule == 'PROVISIONAL_PROFILE'
    assert resolved.level is EvidenceLevel.ENGINEERING_ASSUMPTION
    assert resolved.candidates == ('CAT-A', 'CAT-B')
    assert resolved.original_code == 'USER-CODE-17'


def test_dataset_materialization_keeps_linecableid_and_records_provenance():
    from igea_dgs.catalog_resolution import resolve_dataset_equipment

    dataset = CymdistDataset(
        red_path=Path('red.txt'), loads_path=Path('loads.txt'),
        equipment_path=Path('equipment.txt'),
        headnodes={'N0': 'UTILITY_X_F-A'},
        nodes={'N0': {'NodeID': 'N0'}, 'N1': {'NodeID': 'N1'}},
        sources={'UTILITY_X_F-A': {
            'NetworkID': 'UTILITY_X_F-A', 'NodeID': 'N0', 'DesiredVoltage': '10',
        }},
        line_configurations={'S1': {
            'SectionID': 'S1', 'LineCableID': 'USER-CODE-17', 'Overhead': '1',
            'Material': 'AAAC', 'SectionMM2': '50',
        }},
        sections={'S1': {
            'SectionID': 'S1', 'FromNodeID': 'N0', 'ToNodeID': 'N1', 'Phase': 'ABC',
        }},
        section_owner={'S1': 'UTILITY_X_F-A'}, feeders={'UTILITY_X_F-A': ('S1',)},
        switch_settings=(), sectionalizer_settings=(), intermediate_nodes=(),
        load_placements={}, customer_loads={}, equipment_tables={},
    )
    result = reconstruct_dataset(dataset, ReconstructionPolicy(), [])
    catalog = _catalog('global', 'global', [_row(
        'CAT-50', 0.65, EquipmentClass='LINE', Material='AAAC',
        SectionMM2=50, VoltageKV=10, Overhead=True,
    )])

    resolved = resolve_dataset_equipment(result, [catalog])

    assert result.dataset.line_configurations['S1']['LineCableID'] == 'USER-CODE-17'
    [materialized] = result.dataset.equipment_tables['LINE']
    assert materialized['ID'] == 'USER-CODE-17'
    assert resolved['USER-CODE-17'].source_code == 'CAT-50'
    decision = result.report.decisions[-1]
    assert decision.rule == 'COMPATIBLE_ATTRIBUTES'
    assert decision.provenance['catalog']['sha256'] == 'a' * 64
