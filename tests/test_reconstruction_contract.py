from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from igea_dgs.dataset import CymdistDataset


def _dataset() -> CymdistDataset:
    return CymdistDataset(
        red_path=Path('original-red.txt'),
        loads_path=Path('original-loads.txt'),
        equipment_path=Path('original-equipment.txt'),
        headnodes={'N1': 'UTILITY_X_F-A'},
        nodes={'N1': {'NodeID': 'N1', 'X': '1', 'Y': '2'}},
        sources={'UTILITY_X_F-A': {'NetworkID': 'UTILITY_X_F-A'}},
        line_configurations={'S1': {'SectionID': 'S1', 'LineCableID': ''}},
        sections={'S1': {'SectionID': 'S1', 'FromNodeID': 'N1', 'ToNodeID': 'N2'}},
        section_owner={'S1': 'UTILITY_X_F-A'},
        feeders={'UTILITY_X_F-A': ('S1',)},
        switch_settings=(),
        sectionalizer_settings=(),
        intermediate_nodes=(),
        load_placements={},
        customer_loads={},
        equipment_tables={},
    )


def _fingerprint(dataset: CymdistDataset) -> str:
    return json.dumps(asdict(dataset), sort_keys=True, default=str)


def test_reconstruction_never_mutates_original_dataset():
    from igea_dgs.reconstruction import ReconstructionPolicy, reconstruct_dataset

    dataset = _dataset()
    before = _fingerprint(dataset)

    result = reconstruct_dataset(dataset, ReconstructionPolicy(), [])
    result.dataset.nodes['N1']['X'] = '999'

    assert _fingerprint(dataset) == before
    assert result.dataset is not dataset
    assert result.dataset.nodes is not dataset.nodes
    assert result.dataset.nodes['N1'] is not dataset.nodes['N1']


def test_every_changed_field_has_original_and_evidence():
    from igea_dgs.reconstruction import (
        EvidenceLevel,
        ReconstructionPolicy,
        reconstruct_dataset,
    )

    result = reconstruct_dataset(_dataset(), ReconstructionPolicy(), [])
    result.record_change(
        entity_type='line_configuration',
        entity_id='S1',
        field='LineCableID',
        original_value='',
        applied_value='USER-CODE-17',
        level=EvidenceLevel.ENGINEERING_ASSUMPTION,
        rule='PROVISIONAL_PROFILE',
        reason='No exact catalogue row was available.',
        confidence=0.35,
        candidates=('GLOBAL-AAAC-35', 'GLOBAL-AAAC-50'),
    )

    decision = result.report.decisions[0]
    assert decision.level in {
        EvidenceLevel.CATALOG_MATCH,
        EvidenceLevel.ENGINEERING_ASSUMPTION,
    }
    assert decision.original_value != decision.applied_value
    assert decision.rule and decision.reason and 0 <= decision.confidence <= 1
    assert decision.candidates == ('GLOBAL-AAAC-35', 'GLOBAL-AAAC-50')


def test_reconstruction_report_serializes_enums_paths_and_tuples():
    from igea_dgs.reconstruction import (
        EvidenceLevel,
        ReconstructionPolicy,
        reconstruct_dataset,
    )

    result = reconstruct_dataset(_dataset(), ReconstructionPolicy(), [])
    result.record_change(
        entity_type='node', entity_id='N2', field='NodeID',
        original_value=None, applied_value='N2',
        level=EvidenceLevel.ENGINEERING_ASSUMPTION,
        rule='RECOVER_REFERENCED_NODE', reason='Section references an omitted node.',
        confidence=0.8,
    )

    payload = result.report.to_dict()
    assert payload['decisions'][0]['level'] == 'engineering_assumption'
    assert payload['counts'] == {'engineering_assumption': 1}
    assert json.loads(result.report.to_json()) == payload


def test_record_change_rejects_untraceable_or_noop_decisions():
    import pytest

    from igea_dgs.reconstruction import (
        EvidenceLevel,
        ReconstructionDecision,
        ReconstructionReport,
    )

    report = ReconstructionReport()
    with pytest.raises(ValueError, match='different'):
        report.record_change(ReconstructionDecision(
            entity_type='node', entity_id='N1', field='X',
            original_value='1', applied_value='1',
            level=EvidenceLevel.CATALOG_MATCH, rule='EXACT_GLOBAL',
            reason='match', confidence=1.0,
        ))
    with pytest.raises(ValueError, match='confidence'):
        report.record_change(ReconstructionDecision(
            entity_type='node', entity_id='N1', field='X',
            original_value='1', applied_value='2',
            level=EvidenceLevel.CATALOG_MATCH, rule='EXACT_GLOBAL',
            reason='match', confidence=1.5,
        ))
