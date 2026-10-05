"""Static contract for the universal multi-feeder load web workflow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_batch_tab_is_reachable_and_uses_generic_project_feeder_labels():
    app = (ROOT / 'frontend/src/App.tsx').read_text(encoding='utf-8')
    tab = (ROOT / 'frontend/src/components/LoteTab.tsx').read_text(encoding='utf-8')
    assert '<LoteTab />' in app
    assert 'Proyecto de DIgSILENT' in tab
    assert 'Alimentadores de' in tab
    assert 'Electro Dunas' not in tab and 'IN111' not in tab


def test_one_or_both_books_order_and_error_gate_are_visible():
    tab = (ROOT / 'frontend/src/components/LoteTab.tsx').read_text(encoding='utf-8')
    api = (ROOT / 'frontend/src/api.ts').read_text(encoding='utf-8')
    assert 'updateFile' in tab and 'createFile' in tab
    assert '(!updateFile && !createFile)' in tab
    assert 'plan.order.length' in tab
    assert '!plan.applicable' in tab
    assert "fd.append('feeders', f)" in api


def test_plan_exposes_routing_values_scenario_and_variation():
    tab = (ROOT / 'frontend/src/components/LoteTab.tsx').read_text(encoding='utf-8')
    types = (ROOT / 'frontend/src/types.ts').read_text(encoding='utf-8')
    for field in ('routing_basis', 'changes', 'scenario', 'variation'):
        assert field in tab
        assert field in types
    assert 'before' in tab and 'after' in tab


def test_per_feeder_result_distinguishes_applied_rollback_and_review():
    tab = (ROOT / 'frontend/src/components/LoteTab.tsx').read_text(encoding='utf-8')
    types = (ROOT / 'frontend/src/types.ts').read_text(encoding='utf-8')
    for status in ('APPLIED', 'ROLLED_BACK', 'ROLLBACK_FAILED'):
        assert status in tab
        assert status in types
    assert 'comldf' in tab
    assert 'rollback' in tab
