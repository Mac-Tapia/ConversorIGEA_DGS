"""Contrato universal aplicado despues de los adaptadores de entrada.

Spec 034: 034:RF-19.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def _dataset(*, orphan: bool = False):
    load_section = 'UNKNOWN' if orphan else 'S1'
    return SimpleNamespace(
        feeders={'NET_CA191': ('S1',)},
        sources={'NET_CA191': {'NetworkID': 'NET_CA191'}},
        sections={'S1': {'SectionID': 'S1'}},
        section_owner={'S1': 'NET_CA191'},
        customer_loads={(load_section, 'L1'): {'DeviceNumber': 'L1'}},
        load_placements={(load_section, 'L1'): {'DeviceNumber': 'L1'}},
    )


@pytest.mark.parametrize('mode', ['txt', 'mdb', 'vnr'])
def test_same_audit_contract_for_txt_mdb_vnr(mode):
    from convertersmartgrid.dominio.source_contract import audit_source

    audit = audit_source(
        _dataset(),
        {
            'source_run_id': f'run-{mode}',
            'source_mode': mode,
            'source_fingerprint': f'sha-{mode}',
        },
    ).as_dict()

    assert set(audit) == {
        'format', 'status', 'source_run_id', 'source_mode',
        'source_fingerprint', 'totals', 'feeders', 'issues',
    }
    assert audit['status'] == 'SOURCE_AUDIT_OK'
    assert set(audit['feeders'][0]) == {
        'feeder', 'network_id', 'status', 'counts', 'blocking_codes', 'warning_codes',
    }


def test_missing_or_ambiguous_feeder_is_reported_once():
    from convertersmartgrid.dominio.source_contract import audit_source

    audit = audit_source(_dataset(orphan=True), {}).as_dict()

    issues = [item for item in audit['issues'] if item['code'] == 'MISSING_LOAD_FEEDER']
    assert len(issues) == 1
    assert issues[0]['object_id'] == 'UNKNOWN/L1'
    assert audit['status'] == 'SOURCE_AUDIT_BLOCKED'


def test_source_audit_keeps_mode_run_and_fingerprint():
    from convertersmartgrid.dominio.source_contract import audit_source

    audit = audit_source(
        _dataset(),
        {
            'source_run_id': 'run-custodiado',
            'source_mode': 'mdb',
            'source_fingerprint': 'abc123',
        },
    )

    assert audit.source_run_id == 'run-custodiado'
    assert audit.source_mode == 'mdb'
    assert audit.source_fingerprint == 'abc123'


def test_common_contract_has_no_mode_branch():
    import convertersmartgrid.dominio.source_contract as contract

    source = Path(contract.__file__).read_text(encoding='utf-8')
    for literal in ("'txt'", "'mdb'", "'vnr'", '"txt"', '"mdb"', '"vnr"'):
        assert literal not in source


def test_source_load_result_can_carry_the_same_audit():
    from convertersmartgrid.dominio.source_contract import audit_source
    from convertersmartgrid.puertos.sources.base import SourceLoadResult

    audit = audit_source(_dataset(), {})
    result = SourceLoadResult(dataset=_dataset(), audit=audit)

    assert result.audit is audit
