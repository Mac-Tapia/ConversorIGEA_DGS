from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def test_reconstruction_panel_has_generic_actions_and_evidence_fields():
    panel = _read('frontend/src/components/ReconstructionPanel.tsx')
    assert 'Diagnosticar' in panel
    assert 'Reconstruir y convertir' in panel
    assert 'Ver cambios' in panel
    for field in (
        'source_quality', 'repair_count', 'assumption_count',
        'catalog_sources', 'convergence_state',
    ):
        assert field in panel
    assert 'original_value' in panel and 'applied_value' in panel
    assert 'ELDU' not in panel and 'IN111' not in panel and 'Electro Dunas' not in panel


def test_incomplete_feeders_remain_selectable_and_conversion_is_not_disabled_by_readiness():
    feeders = _read('frontend/src/components/FeedersPanel.tsx')
    assert "const canConvert = (row: FeederRow) => row.readiness !== 'INVENTORY_ONLY'" not in feeders
    assert 'ReconstructionPanel' in feeders
    assert 'se reconstruirán de forma auditable' in feeders


def test_semantic_status_contract_covers_original_catalog_assumption_and_review():
    feeders = _read('frontend/src/components/FeedersPanel.tsx')
    assert "READY_ORIGINAL" in feeders and "tone=\"ok\"" in feeders
    assert "READY_RECONSTRUCTED" in feeders and "tone=\"info\"" in feeders
    assert "CONVERTED_WITH_ASSUMPTIONS" in feeders and "tone=\"warn\"" in feeders
    assert "NEEDS_OPERATOR_REVIEW" in feeders and "tone=\"error\"" in feeders


def test_frontend_api_and_types_expose_reconstruction_contract():
    api = _read('frontend/src/api.ts')
    types = _read('frontend/src/types.ts')
    assert '/diagnose' in api and '/reconstruct' in api
    assert 'ReconstructionDecision' in types
    assert 'report_sha256' in types
