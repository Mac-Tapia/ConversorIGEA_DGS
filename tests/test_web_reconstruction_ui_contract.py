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


def test_diagnosticar_y_reconstruir_se_lanzan_como_trabajos():
    """001:RF-8 — el front inicia diagnosticar y reconstruir con startJob, sin esperar en el clic."""
    import re

    api = _read('frontend/src/api.ts')
    panel = _read('frontend/src/components/ReconstructionPanel.tsx')
    for metodo in ('diagnose', 'reconstruct'):
        assert re.search(rf'{metodo}: \([^)]*\) =>\s*request<Job>', api), metodo
        assert f'startJob(() => api.{metodo}(' in panel, metodo
    assert 'run(() => api.diagnose' not in panel and 'run(() => api.reconstruct(' not in panel


def test_la_descarga_trata_el_detail_como_el_resto_de_peticiones():
    """001:RF-12 — un 422 en una descarga muestra los mensajes, no «[object Object]»."""
    import re

    api = _read('frontend/src/api.ts')
    cuerpo = lambda nombre: re.search(  # noqa: E731
        rf'(?:async )?function {nombre}\b.*?\n}}', api, re.S).group(0)
    assert 'throw await apiError(res)' in cuerpo('request')
    assert 'throw await apiError(res)' in cuerpo('download')
    assert 'Array.isArray(body.detail)' in cuerpo('apiError')
    assert '.detail ??' not in api


def test_el_cliente_no_tiene_metodos_sin_uso():
    """001:RF-13 — cada método de `api` lo llama alguna pantalla."""
    import re

    api = _read('frontend/src/api.ts')
    objeto = api[api.index('export const api = {'):]
    objeto = objeto[:objeto.index('\n};')]
    metodos = re.findall(r'^  (\w+): ', objeto, re.M)
    assert len(metodos) > 10
    resto = '\n'.join(
        p.read_text(encoding='utf-8')
        for p in (ROOT / 'frontend/src').rglob('*.ts*') if p.name != 'api.ts'
    )
    sin_uso = [m for m in metodos if not re.search(rf'\bapi\.{m}\b', resto)]
    assert sin_uso == []
