"""La identidad vinculada se muestra y gobierna los controles nativos.

Spec 034: 034:RF-21.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAB = (ROOT / 'frontend' / 'src' / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
TYPES = (ROOT / 'frontend' / 'src' / 'types.ts').read_text(encoding='utf-8')


def test_front_declares_and_renders_project_binding_evidence():
    assert 'export interface PowerFactoryProjectBinding' in TYPES
    for text in ('source_run_id', 'source_fingerprint', 'native_inventory_sha256', 'native_reread'):
        assert text in TYPES
    assert 'current?.binding' in TAB
    assert 'Ejecución fuente' in TAB
    assert 'Huella fuente' in TAB
    assert 'Última relectura nativa' in TAB


def test_front_disables_native_workflow_for_unbound_or_stale_project():
    assert 'binding_blocked_reason' in TYPES
    assert 'bindingBlocked' in TAB
    assert 'disabled={bindingBlocked' in TAB
