"""Acceptance contract for reconstructed feeders in PowerFactory."""

from __future__ import annotations

import json

import pytest


def _report(*, catalog=0, assumptions=0, repairs=None, intent=None):
    attempts = [{
        'attempt': 0,
        'phase': 'initial',
        'load_flow': {'pass': intent is None, 'ldf_valid': intent is None},
        'correction': None,
    }]
    if intent:
        attempts.append({
            'attempt': 1,
            'phase': 'correction',
            'intent': intent,
            'load_flow': {'pass': True, 'ldf_valid': True},
            'correction': {
                'intent': intent,
                'ok': True,
                'changes': [{'object': 'LOAD-1', 'field': 'plini', 'before': 10.0, 'after': 5.0}],
            },
        })
    return {
        'source_verification': {'status': 'VERIFIED_BEFORE_MUTATION'},
        'reconstruction_verification': {
            'status': 'VERIFIED_BEFORE_MUTATION',
            'repairs': catalog + assumptions if repairs is None else repairs,
            'catalog_matches': catalog,
            'assumptions': assumptions,
        },
        'load_flow_loop': {
            'pass': True,
            'attempts': attempts,
            'final_load_flow': {'pass': True, 'ldf_valid': True},
            'converged_after_intent': intent,
        },
        'effective_reread': {
            'feeder_metadata': True,
            'feeder_objects': 3,
            'comldf_executed': True,
            'comldf_valid': True,
        },
        'rollback': {'status': 'NOT_REQUIRED_ISOLATED_PROJECT', 'attempted': False},
    }


@pytest.mark.parametrize(
    ('report', 'expected'),
    [
        (_report(), 'CONVERGED_ORIGINAL'),
        (_report(catalog=2), 'CONVERGED_RECONSTRUCTED'),
        (_report(catalog=1, assumptions=1), 'CONVERGED_WITH_ASSUMPTIONS'),
        (_report(intent='scale_loads_50'), 'NEEDS_OPERATOR_REVIEW'),
        (_report(intent='disconnect_floating_loads'), 'NEEDS_OPERATOR_REVIEW'),
    ],
)
def test_classifies_convergence_by_evidence_and_load_intervention(report, expected):
    from igea_dgs.powerfactory_metadata import classify_convergence

    assert classify_convergence(report) == expected


def test_stale_source_evidence_is_rejected_and_reread_or_rollback_fail_closed():
    from igea_dgs.powerfactory_metadata import classify_convergence

    stale = _report()
    stale['source_verification']['status'] = 'MISMATCH'
    assert classify_convergence(stale) == 'REJECTED_STALE_EVIDENCE'

    no_reread = _report()
    no_reread['effective_reread']['comldf_valid'] = False
    assert classify_convergence(no_reread) == 'NEEDS_OPERATOR_REVIEW'

    partial_rollback = _report()
    partial_rollback['rollback'] = {'status': 'PARTIAL', 'attempted': True}
    assert classify_convergence(partial_rollback) == 'NEEDS_OPERATOR_REVIEW'


def test_nonconverged_result_is_not_promoted():
    from igea_dgs.powerfactory_metadata import classify_convergence

    report = _report()
    report['load_flow_loop']['pass'] = False
    report['load_flow_loop']['final_load_flow']['ldf_valid'] = False
    assert classify_convergence(report) == 'NOT_CONVERGED'


def test_reconstruction_report_hash_and_sidecar_are_verified(tmp_path):
    from igea_dgs.powerfactory_metadata import (
        reconstruction_report_sha256,
        verify_reconstruction_contract,
    )

    payload = {
        'source_run_id': 'run-1',
        'selection': ['IN111'],
        'decisions': [{'level': 'catalog_match'}, {'level': 'engineering_assumption'}],
        'counts': {'catalog_match': 1, 'engineering_assumption': 1},
    }
    digest = reconstruction_report_sha256(payload)
    payload['report_sha256'] = digest
    path = tmp_path / 'reconstruction_report.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    sidecar = {
        'source_run_id': 'run-1',
        'reconstruction': {
            'report': path.name,
            'report_sha256': digest,
            'repairs': 2,
            'catalog_matches': 1,
            'assumptions': 1,
        },
    }

    verified = verify_reconstruction_contract(sidecar, path, expected_hash=digest)
    assert verified['status'] == 'VERIFIED_BEFORE_MUTATION'
    assert verified['repairs'] == 2
    assert verified['catalog_matches'] == 1
    assert verified['assumptions'] == 1

    payload['decisions'][0]['level'] = 'engineering_assumption'
    path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError, match='SHA-256'):
        verify_reconstruction_contract(sidecar, path, expected_hash=digest)


def test_load_intervention_extracts_structured_attempt_evidence():
    from igea_dgs.powerfactory_metadata import load_intervention_from_attempts

    attempts = _report(intent='scale_loads_50')['load_flow_loop']['attempts']
    evidence = load_intervention_from_attempts(attempts)
    assert evidence['attempted'] is True
    assert evidence['intents'] == ['scale_loads_50']
    assert evidence['changes'][0]['before'] == 10.0
    assert evidence['changes'][0]['after'] == 5.0
