from __future__ import annotations

import inspect
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient


def _package(tmp_path: Path, *, companies: tuple[str, ...], periods: tuple[int, ...]) -> Path:
    features = []
    index = 0
    for company in companies:
        for period in periods:
            index += 1
            features.append({
                'type': 'Feature',
                'properties': {
                    'CODEMP': company,
                    'ANIO': period,
                    'CODTRAMOMT': f'S{index}',
                    'CODSALIDAMT': f'F-{index}',
                    'CODNORMA': 'COND-1',
                    'LONGITUD': 100,
                },
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[-75 + index / 100, -14], [-75 + index / 100 + .001, -14]],
                },
            })
    archive = tmp_path / 'generic-vnr.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('sections.geojson', json.dumps({
            'type': 'FeatureCollection', 'features': features,
        }))
    return archive


def _snapshot(tmp_path: Path, package: Path):
    from igea_dgs.web.source_runs import create_source_run
    from igea_dgs.web.workspace import Workspace

    ws = Workspace(id='scope-test', root=tmp_path / 'workspace')
    ws.options['input_mode'] = 'vnr'
    ws.set_input('vnr_package', package, origin='server')
    return create_source_run(ws)


def test_vnr_single_scope_is_detected_without_company_default(tmp_path):
    from igea_dgs.web.source_scope import inspect_source_scope

    scope = inspect_source_scope(_snapshot(
        tmp_path, _package(tmp_path, companies=('GENERIC_CO',), periods=(2031,)),
    ))

    assert scope.companies == ('GENERIC_CO',)
    assert scope.periods == ('2031',)
    assert scope.selected_company == 'GENERIC_CO'
    assert scope.selected_period == '2031'
    assert scope.ambiguous is False


def test_vnr_multiple_companies_requires_explicit_selection(tmp_path):
    from igea_dgs.web.source_scope import inspect_source_scope

    scope = inspect_source_scope(_snapshot(
        tmp_path, _package(tmp_path, companies=('UTILITY_A', 'UTILITY_B'), periods=(2030,)),
    ))

    assert scope.companies == ('UTILITY_A', 'UTILITY_B')
    assert scope.selected_company is None
    assert scope.selected_period == '2030'
    assert scope.ambiguous is True


def test_pipeline_and_adapter_have_no_company_specific_default():
    from igea_dgs.web.sources.vnr import VnrSourceAdapter
    from vnr_etl.pipeline import canonicalize_vnr_package

    assert inspect.signature(canonicalize_vnr_package).parameters['company'].default is None
    assert inspect.signature(VnrSourceAdapter).parameters['company'].default is None


def test_source_scope_api_exposes_options_and_selection_invalidates_run(tmp_path):
    from igea_dgs.web.app import create_app

    app = create_app(tmp_path / 'web')
    with TestClient(app) as client:
        ws = app.state.store.create()
        package = _package(tmp_path, companies=('UTILITY_A', 'UTILITY_B'), periods=(2030, 2031))
        ws.options['input_mode'] = 'vnr'
        ws.set_input('vnr_package', package, origin='server')
        ws.active_run_id = '20260101T000000-aaaaaaaaaaaa'
        ws.save()

        response = client.get(f'/api/workspaces/{ws.id}/source-scope')
        assert response.status_code == 200
        assert response.json()['companies'] == ['UTILITY_A', 'UTILITY_B']
        assert response.json()['ambiguous'] is True

        selected = client.put(
            f'/api/workspaces/{ws.id}/source-scope',
            json={'company': 'UTILITY_B', 'period': '2031'},
        )
        assert selected.status_code == 200
        assert selected.json()['selected_company'] == 'UTILITY_B'
        assert selected.json()['selected_period'] == '2031'
        assert app.state.store.get(ws.id).active_run_id is None


def test_inputs_panel_contains_scope_selectors_without_test_company_defaults():
    source = (
        Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'components' / 'InputsPanel.tsx'
    ).read_text(encoding='utf-8')

    assert 'sourceScope' in source
    assert 'Empresa de la fuente' in source
    assert 'Periodo de la fuente' in source
    assert 'ELDU' not in source
    assert 'IN111' not in source
    assert 'Electro Dunas' not in source
