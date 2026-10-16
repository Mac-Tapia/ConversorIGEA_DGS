from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest


def _feature(section: str, feeder: str, company: str, year: int, x: float) -> dict:
    return {
        'type': 'Feature',
        'properties': {
            'CODEMP': company,
            'ANIO': year,
            'CODTRAMOMT': section,
            'CODSALIDAMT': feeder,
            'CODNORMA': 'AA120',
            'LONGITUD': 100.0,
        },
        'geometry': {
            'type': 'LineString',
            'coordinates': [[x, -14.0], [x + 0.001, -14.0]],
        },
    }


def _vnr_zip(tmp_path: Path) -> Path:
    geojson = {
        'type': 'FeatureCollection',
        'features': [
            _feature('OLD', 'OLD101', 'ELDU', 2024, -75.10),
            _feature('S1', 'IN111', 'ELDU', 2025, -75.00),
            _feature('S2', 'AL209', 'ELDU', 2025, -74.99),
            _feature('OTHER', 'SE101', 'SEAL', 2025, -74.90),
        ],
    }
    archive = tmp_path / 'VNR_GIS_Electro_Dunas_2025.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.writestr('capas/Tramo_MT.geojson', json.dumps(geojson))
    return archive


def test_safe_extract_package_rechaza_traversal_y_duplicados(tmp_path):
    from vnr_etl.pipeline import safe_extract_package
    from vnr_etl.discovery.download import ArchiveSecurityError

    traversal = tmp_path / 'traversal.zip'
    with zipfile.ZipFile(traversal, 'w') as zf:
        zf.writestr('../escape.geojson', '{}')
    with pytest.raises(ArchiveSecurityError, match='insegura'):
        safe_extract_package(traversal, tmp_path / 'out-traversal')
    assert not (tmp_path / 'escape.geojson').exists()

    duplicate = tmp_path / 'duplicate.zip'
    with pytest.warns(UserWarning, match='Duplicate name'):
        with zipfile.ZipFile(duplicate, 'w') as zf:
            zf.writestr('layer.geojson', '{}')
            zf.writestr('layer.geojson', '{}')
    with pytest.raises(ArchiveSecurityError, match='duplicada'):
        safe_extract_package(duplicate, tmp_path / 'out-duplicate')


def test_bridge_conserva_identidad_de_dos_alimentadores():
    from igea_dgs.model import build_feeder_model
    from vnr_etl.application.cymdist_bridge import canonical_to_cymdist
    from vnr_etl.models import CanonicalModel, ConductorType, Load, Node, Section, Source

    model = CanonicalModel(metadata={
        'working_crs': 'EPSG:32718', 'working_crs_is_projected': True,
    })
    model.nodes = [
        Node('A', 500000, 8450000, nominal_kv=10), Node('B', 500100, 8450000, nominal_kv=10),
        Node('C', 501000, 8450000, nominal_kv=22.9), Node('D', 501100, 8450000, nominal_kv=22.9),
    ]
    model.sections = [
        Section('S1', 'A', 'B', conductor_code='AA120', phases='ABC', nominal_kv=10,
                length_m=100, feeder_id='IN111'),
        Section('S2', 'C', 'D', conductor_code='AA120', phases='ABC', nominal_kv=22.9,
                length_m=100, feeder_id='AL209'),
    ]
    model.sources = [
        Source('SRC1', 'A', nominal_kv=10, feeder_id='IN111'),
        Source('SRC2', 'C', nominal_kv=22.9, feeder_id='AL209'),
    ]
    model.loads = [
        Load('LD1', 'B', kw=120, kvar=40, phases='ABC', feeder_id='IN111'),
        Load('LD2', 'D', kw=80, kvar=20, phases='ABC', feeder_id='AL209'),
    ]
    model.conductor_types = [ConductorType(
        'AA120', r1_ohm_km=0.25, x1_ohm_km=0.35, r0_ohm_km=0.7,
        x0_ohm_km=1.1, ampacity_a=300,
    )]

    result = canonical_to_cymdist(model, source_path=Path('VNR.zip'))

    assert set(result.dataset.feeders) == {'IN111', 'AL209'}
    assert result.dataset.section_owner == {'S1': 'IN111', 'S2': 'AL209'}
    assert set(result.dataset.sources) == {'IN111', 'AL209'}
    assert {row['feeder']: row['status'] for row in result.readiness.values()} == {
        'IN111': 'CONVERSION_READY', 'AL209': 'CONVERSION_READY',
    }
    assert len(result.dataset.customer_loads_by_feeder['IN111']) == 1
    assert len(result.dataset.customer_loads_by_feeder['AL209']) == 1
    converted = build_feeder_model(result.dataset, 'IN111', include_geography=True)
    assert converted.loads[0].p_mw == pytest.approx(0.120)
    assert converted.loads[0].q_mvar == pytest.approx(0.040)


def test_bridge_enumera_pero_bloquea_vnr_sin_fuente_ni_cargas():
    from vnr_etl.application.cymdist_bridge import canonical_to_cymdist
    from vnr_etl.pipeline import canonicalize_sections

    rows = [
        _feature('S1', 'IN111', 'ELDU', 2025, -75.00),
        _feature('S2', 'AL209', 'ELDU', 2025, -74.99),
    ]
    model = canonicalize_sections(rows).model

    result = canonical_to_cymdist(model, source_path=Path('VNR.zip'))

    assert set(result.dataset.feeders) == {'IN111', 'AL209'}
    for readiness in result.readiness.values():
        assert readiness['status'] == 'INVENTORY_ONLY'
        assert {'MISSING_SOURCE', 'MISSING_LOADS', 'MISSING_CONDUCTOR_CATALOG'} <= set(
            readiness['blocking_codes']
        )


def test_vnr_adapter_respeta_empresa_y_periodo_explicitos(tmp_path):
    from igea_dgs.web.source_runs import create_source_run
    from igea_dgs.web.sources import adapter_for
    from igea_dgs.web.workspace import Workspace

    archive = _vnr_zip(tmp_path)
    ws = Workspace(id='vnr-adapter', root=tmp_path / 'workspace')
    ws.options['input_mode'] = 'vnr'
    ws.set_input('vnr_package', archive, origin='server')
    snapshot = create_source_run(ws)

    result = adapter_for('vnr', company='ELDU', period='2025').load(snapshot, aliases={})

    assert set(result.dataset.feeders) == {'IN111', 'AL209'}
    assert set(result.readiness) == {'IN111', 'AL209'}
    assert result.provenance['company'] == 'ELDU'
    assert result.provenance['period'] == '2025'
    assert result.provenance['source_run_id'] == snapshot.run_id
    assert all(row['status'] == 'INVENTORY_ONLY' for row in result.readiness.values())
