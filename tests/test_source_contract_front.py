"""El frontend muestra el contrato calculado por el servidor, sin recalcularlo.

Spec 034: 034:RF-19.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


def test_frontend_types_expose_universal_source_audit():
    types = _read('frontend/src/types.ts')

    assert 'export interface UniversalSourceAudit' in types
    assert 'universal_audit: UniversalSourceAudit | null' in types
    assert 'source_audit_status:' in types


def test_feeders_panel_renders_server_source_audit_without_mode_branch():
    panel = _read('frontend/src/components/FeedersPanel.tsx')

    assert 'ws.universal_audit' in panel
    assert 'source_audit_status' in panel
    assert "source_mode === 'txt'" not in panel
    assert "source_mode === 'mdb'" not in panel
    assert "source_mode === 'vnr'" not in panel
