"""Pruebas del módulo adicional `vnr_etl`.

Cubren las capas que no dependen de red ni de drivers opcionales: modelo
canónico, descubrimiento de esquema, huella, catálogo/frescura, seguridad de
archivos, snapping determinista, topología, reconciliación, enriquecimiento,
configuración, doctor, exportadores y CLI. Las dependencias ``shapely``,
``requests`` y ``geopandas`` no se importan en colección (todo es perezoso), así
que estas pruebas no rompen la suite existente.
"""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import pytest

from vnr_etl import __version__
from vnr_etl.application import VnrApplicationService
from vnr_etl.config import Settings, deep_get
from vnr_etl.connectors.arcgis import ArcGISLayer, ArcGISRestAdapter
from vnr_etl.discovery.catalog import Publication, PublicationCatalog
from vnr_etl.discovery.download import (
    DownloadError,
    DownloadManager,
    inventory_zip,
    safe_extract_zip,
    sha256_of,
)
from vnr_etl.discovery.fingerprint import compute_schema_fingerprint
from vnr_etl.discovery.freshness import resolve_freshness
from vnr_etl.discovery.official import (
    default_discovery_pages,
    parse_official_publications,
    refresh_official_catalog,
)
from vnr_etl.discovery.schema import SchemaResolver, resolve_alias
from vnr_etl.doctor import doctor
from vnr_etl.electrical.enrich import apparent_power, enrich_electrical, power_factor
from vnr_etl.exporters.base import ExportBlocked, TargetProfile
from vnr_etl.exporters.cymdist import CymdistExporter
from vnr_etl.exporters.dgs import DgsExporter
from vnr_etl.gis.snapping import deterministic_node_id, snap_endpoints
from vnr_etl.models import CanonicalModel, Load, Node, Section, Source
from vnr_etl.pipeline import (
    canonicalize_sections,
    list_companies,
    list_periods,
    select_source_scope,
)
from vnr_etl.reconciliation.diff import diff_records
from vnr_etl.topology.graph import validate_topology
from vnr_etl.validation import run_gates


# --------------------------------------------------------------------------- modelo
def _model_base() -> CanonicalModel:
    model = CanonicalModel()
    model.metadata = {'schema_fingerprint': 'abc'}
    model.nodes = [Node(node_id='A', x=0.0, y=0.0), Node(node_id='B', x=10.0, y=0.0),
                   Node(node_id='C', x=20.0, y=0.0)]
    model.sections = [Section(section_id='S1', from_node='A', to_node='B')]
    model.sources = [Source(source_id='G', node_id='A')]
    return model


def test_canonical_roundtrip():
    model = _model_base()
    model.loads = [Load(load_id='L1', connection_node='B', kw=100.0, kvar=40.0)]
    data = model.to_dict()
    restored = CanonicalModel.from_dict(data)
    assert restored.counts() == model.counts()
    assert restored.loads[0].load_id == 'L1'


# --------------------------------------------------------------------------- esquema
def test_resolve_alias_exact_and_normalized():
    assert resolve_alias('feeder_id', ['CODSALIDAMT', 'x']) == ('CODSALIDAMT', 'alias')
    assert resolve_alias('period', ['AÑO']) == ('AÑO', 'alias')
    assert resolve_alias('period', ['ANO']) == ('ANO', 'normalized_alias')
    assert resolve_alias('sed_id', ['foo']) == (None, 'missing')


def test_schema_resolver_confidence():
    resolver = SchemaResolver()
    result = resolver.resolve_fields(['CODTRAMOMT', 'LONGITUD'], layer='tramos')
    assert result['section_id'].resolution_method == 'alias'
    assert result['section_id'].confidence == 1.0
    assert result['sed_id'].resolution_method == 'missing'
    assert resolver.missing_required(result, ['section_id', 'sed_id']) == ['sed_id']


# --------------------------------------------------------------------------- contrato GeoJSON
def _arcgis_feature(section_id, start, end, *, feeder='F1', conductor='AA120'):
    return {
        'type': 'Feature',
        'properties': {
            'CODTRAMOMT': section_id,
            'CODSALIDAMT': feeder,
            'CODNORMA': conductor,
            'LONGITUD': '100.0',
        },
        'geometry': {'type': 'LineString', 'coordinates': [start, end]},
    }


def test_canonicalize_arcgis_geojson_preserves_attributes_ids_and_lineage():
    rows = [
        _arcgis_feature('T1', [-75.0, -14.0], [-74.999, -14.0]),
        _arcgis_feature('T2', [-74.999, -14.0], [-74.998, -14.0]),
    ]

    result = canonicalize_sections(rows, source_layer='osinergmin_mt')

    assert [section.section_id for section in result.model.sections] == ['T1', 'T2']
    assert [section.feeder_id for section in result.model.sections] == ['F1', 'F1']
    assert [section.conductor_code for section in result.model.sections] == ['AA120', 'AA120']
    assert len(result.model.sections_by_id()) == 2
    assert result.model.sections[0].lineage.source_layer == 'osinergmin_mt'
    assert result.model.sections[0].lineage.source_id == 'T1'


def test_canonicalize_records_effective_projected_crs_and_snap_report():
    result = canonicalize_sections([
        _arcgis_feature('T1', [-75.0, -14.0], [-74.999, -14.0]),
    ])

    assert result.model.metadata['source_crs'] == 'EPSG:4326'
    assert result.model.metadata['working_crs'] == 'EPSG:32718'
    assert result.model.metadata['working_crs_is_projected'] is True
    assert result.snap_report['count'] == 2
    assert result.model.nodes[0].x > 100_000


@pytest.mark.parametrize('rows,match', [
    ([_arcgis_feature('', [-75.0, -14.0], [-74.999, -14.0])], 'identificador'),
    ([_arcgis_feature('T1', [-75.0, -14.0], [-74.999, -14.0]),
      _arcgis_feature('T1', [-74.999, -14.0], [-74.998, -14.0])], 'duplicado'),
])
def test_canonicalize_fails_closed_on_missing_or_duplicate_section_ids(rows, match):
    with pytest.raises(ValueError, match=match):
        canonicalize_sections(rows)


def test_source_scope_selects_company_and_latest_period_without_mixing():
    rows = [
        {'CODEMP': 'ELDU', 'ANIO': 2024, 'CODTRAMOMT': 'A'},
        {'CODEMP': 'ELDU', 'ANIO': 2025, 'CODTRAMOMT': 'B'},
        {'CODEMP': 'SEAL', 'ANIO': 2025, 'CODTRAMOMT': 'C'},
    ]
    selected, scope = select_source_scope(rows, company='ELDU', period='latest_available')
    assert [row['CODTRAMOMT'] for row in selected] == ['B']
    assert scope == {'company': 'ELDU', 'period': '2025'}

    with pytest.raises(ValueError, match='múltiples empresas'):
        select_source_scope(rows, period='latest_available')


# --------------------------------------------------------------------------- huella
def test_schema_fingerprint_deterministic():
    layers = [{'name': 'Tramos', 'fields': [{'name': 'A', 'type': 'int'}], 'geometry_type': 'Polyline'}]
    assert compute_schema_fingerprint(layers) == compute_schema_fingerprint(layers)
    changed = [{'name': 'Tramos', 'fields': [{'name': 'B', 'type': 'int'}], 'geometry_type': 'Polyline'}]
    assert compute_schema_fingerprint(changed) != compute_schema_fingerprint(layers)


# --------------------------------------------------------------------------- catálogo/frescura
def _pub(pid, published, period='2025'):
    return Publication(publication_id=pid, company='ELDU', company_code='ELDU',
                       publication_type='REGULATORY_VNRGIS_PACKAGE',
                       published_at=published, reference_date=published,
                       period_label=period)


def test_catalog_immutable_history():
    catalog = PublicationCatalog()
    pub = _pub('p1', '2025-01-01')
    assert catalog.upsert_publication(pub) is True
    assert catalog.upsert_publication(pub) is False  # idéntico no se reescribe
    newer = _pub('p1', '2025-01-02')
    assert catalog.upsert_publication(newer) is True  # cambio → registro nuevo
    publications = catalog.publications()
    assert len(publications) == 2
    assert catalog.get('p1') == pub
    assert any(item.published_at == '2025-01-02' for item in publications)


def test_freshness_latest_by_date_not_lexical():
    pubs = [_pub('older', '2024-09-01'), _pub('newer', '2025-03-01')]
    result = resolve_freshness(pubs, company='ELDU')
    assert result.selected_publication == 'newer'
    assert result.confidence == 'HIGH'


def test_local_source_discovers_company_and_period_values(tmp_path):
    source = tmp_path / 'vnr.csv'
    source.write_text(
        'CODEMP,ANIO,CODTRAMOMT\nELDU,2024,T1\nELDU,2025,T2\nSEAL,2025,T3\n',
        encoding='utf-8',
    )

    assert list_companies(str(source)) == ['ELDU', 'SEAL']
    assert list_periods(str(source), company='ELDU') == ['2024', '2025']


def test_sqlite_adapter_releases_database_file(tmp_path):
    import sqlite3

    from vnr_etl.connectors.databases import SQLiteAdapter

    path = tmp_path / 'source.sqlite'
    connection = sqlite3.connect(path)
    connection.execute('CREATE TABLE tramos (id TEXT, value INTEGER)')
    connection.execute("INSERT INTO tramos VALUES ('T1', 1)")
    connection.commit()
    connection.close()

    adapter = SQLiteAdapter(path=str(path))
    assert adapter.list_layers()[0].name == 'tramos'
    assert adapter.read_layer('tramos') == [{'id': 'T1', 'value': 1}]
    assert adapter.read_layer('tramos', {'equals': {'id': 'T1'}}) == [
        {'id': 'T1', 'value': 1}
    ]
    with pytest.raises(ValueError, match='WHERE libre'):
        adapter.read_layer('tramos', {'where': '1=1; DROP TABLE tramos'})
    path.unlink()
    assert not path.exists()


def test_safe_extract_zip_rejects_symbolic_link(tmp_path):
    archive = tmp_path / 'symlink.zip'
    info = zipfile.ZipInfo('link')
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.writestr(info, '../outside')

    with pytest.raises(DownloadError, match='simbólico'):
        safe_extract_zip(archive, tmp_path / 'extract')


def test_arcgis_company_period_discovery_uses_distinct_queries(monkeypatch):
    adapter = ArcGISRestAdapter('https://official.example/MapServer')
    monkeypatch.setattr(adapter, 'metadata_of', lambda: {
        'layers': [{'id': 22, 'name': 'Tramo Red MT Existente'}],
    })
    monkeypatch.setattr(ArcGISLayer, 'metadata', lambda self: {
        'fields': [{'name': 'CODEMP'}, {'name': 'ANIO'}],
        'objectIdField': 'OBJECTID',
        'maxRecordCount': 2000,
    })
    calls = []

    def distinct(self, field, where='1=1'):
        calls.append((field, where))
        if field == 'CODEMP':
            return ['SEAL', 'ELDU', 'ELDU']
        return [2025, 2024]

    monkeypatch.setattr(ArcGISLayer, 'distinct_values', distinct, raising=False)

    assert adapter.available_companies() == ['ELDU', 'SEAL']
    assert adapter.available_periods('ELDU') == ['2024', '2025']
    assert ('ANIO', "CODEMP = 'ELDU'") in calls


def test_arcgis_layer_inventory_reports_actual_count(monkeypatch):
    adapter = ArcGISRestAdapter('https://official.example/MapServer')
    monkeypatch.setattr(adapter, 'metadata_of', lambda: {
        'layers': [{'id': 22, 'name': 'Tramo Media Tensión'}],
    })
    monkeypatch.setattr(ArcGISLayer, 'metadata', lambda self: {
        'fields': [{'name': 'OBJECTID'}],
        'geometryType': 'esriGeometryPolyline',
        'maxRecordCount': 2000,
    })
    monkeypatch.setattr(ArcGISLayer, 'count', lambda self, where='1=1': 17)

    assert adapter.list_layers()[0].record_count == 17


def test_arcgis_pagination_can_take_a_bounded_audit_sample(monkeypatch):
    import sys
    import types

    offsets = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def get(url, params, timeout):
        if not url.endswith('/query'):
            return Response({'objectIdField': 'OBJECTID', 'maxRecordCount': 2})
        offsets.append(params['resultOffset'])
        start = params['resultOffset']
        size = params['resultRecordCount']
        return Response({'features': [
            {'type': 'Feature', 'properties': {'OBJECTID': value}, 'geometry': None}
            for value in range(start + 1, start + size + 1)
        ]})

    monkeypatch.setitem(sys.modules, 'requests', types.SimpleNamespace(get=get))
    features, crs = ArcGISLayer('https://official.example/MapServer/22').query_geojson(
        page_size=2,
        max_features=5,
    )

    assert len(features) == 5
    assert offsets == [0, 2, 4]
    assert crs == 4326


def test_official_discovery_keeps_only_official_vnr_links(tmp_path):
    page = 'https://www.osinergmin.gob.pe/Resoluciones/Resoluciones-GRT-2026.aspx'
    html = '''
      <tr><td><a href="/docs/Resolucion-154-2026-OS-CD.pdf">Resolución 154-2026-OS/CD</a>
      <br>Proyecto de fijación del Valor Nuevo de Reemplazo (VNR) al 31 de diciembre de 2025</td></tr>
      <a href="https://www2.osinergmin.gob.pe/GRT/VNR/ELDU_2025.rar">VNRGIS Electro Dunas 2025</a>
      <a href="https://example.com/falso-vnr.zip">VNR externo</a>
      <a href="/docs/otro.pdf">Documento no relacionado</a>
    '''

    publications = parse_official_publications(page, html)

    assert len(publications) == 2
    assert {p.publication_type for p in publications} == {
        'REGULATORY_VNR_PUBLICATION', 'REGULATORY_VNRGIS_PACKAGE',
    }
    assert all('osinergmin.gob.pe' in p.download_url for p in publications)
    assert {p.period_label for p in publications} == {'2025'}


def test_official_catalog_refresh_is_additive_and_runtime_year_based(tmp_path):
    pages = default_discovery_pages()
    assert str(__import__('datetime').datetime.now().year) in pages[0]
    html = '<a href="/VNR/VNRGIS_2025.zip">VNRGIS 2025</a>'
    fetcher = lambda _url: html

    catalog, first = refresh_official_catalog(tmp_path, pages=[pages[0]], fetcher=fetcher)
    _, second = refresh_official_catalog(tmp_path, pages=[pages[0]], fetcher=fetcher)

    assert first['added'] == 1
    assert second['added'] == 0
    assert len(catalog.publications()) == 1


def test_official_fetch_retries_transient_failures(monkeypatch):
    import sys
    import types

    from vnr_etl.discovery import official

    calls = []

    class Response:
        url = 'https://www.osinergmin.gob.pe/Resoluciones/Resoluciones-GRT-2026.aspx'
        apparent_encoding = 'utf-8'
        encoding = 'utf-8'
        text = '<html>ok</html>'

        def raise_for_status(self):
            return None

    def get(url, timeout):
        calls.append((url, timeout))
        if len(calls) == 1:
            raise RuntimeError('timeout transitorio')
        return Response()

    monkeypatch.setitem(sys.modules, 'requests', types.SimpleNamespace(get=get))
    monkeypatch.setattr('time.sleep', lambda _seconds: None)

    assert official._fetch_html(Response.url) == '<html>ok</html>'
    assert len(calls) == 2


# --------------------------------------------------------------------------- archivos
def test_sha256_and_archive_safety(tmp_path):
    f = tmp_path / 'x.txt'
    f.write_text('contenido', encoding='utf-8')
    d1 = sha256_of(f)
    f.write_text('otro', encoding='utf-8')
    assert sha256_of(f) != d1

    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.writestr('../evil.txt', 'data')  # recorrido hacia arriba
    with pytest.raises(DownloadError):
        inventory_zip(archive)

    out = tmp_path / 'out'
    good = tmp_path / 'good.zip'
    with zipfile.ZipFile(good, 'w') as zf:
        zf.writestr('a/b.txt', 'x')
    names = inventory_zip(good)
    assert names == ['a/b.txt']
    extracted = safe_extract_zip(good, out)
    assert len(extracted) == 1


def test_download_finalize_rejects_corrupt_archive_before_publish(tmp_path):
    manager = DownloadManager(tmp_path / 'cache')
    destination = tmp_path / 'cache' / 'bad.zip'
    part = destination.with_suffix('.zip.part')
    part.write_bytes(b'not-a-zip')

    with pytest.raises(DownloadError, match='archivo'):
        manager._finalize(part, destination, 'https://www.osinergmin.gob.pe/bad.zip', '', '', '')

    assert not destination.exists()


def test_download_manager_rejects_non_official_hosts(tmp_path):
    manager = DownloadManager(
        tmp_path / 'cache',
        allowed_hosts=['osinergmin.gob.pe'],
    )

    with pytest.raises(DownloadError, match='no permitido'):
        manager.download('https://example.com/file.zip', tmp_path / 'cache' / 'file.zip')


# --------------------------------------------------------------------------- snapping
def test_snapping_deterministic_and_tolerance():
    anchors = [('s1:a', 0.0, 0.0), ('s1:b', 0.1, 0.0), ('s2:a', 0.2, 0.0),
               ('s3:a', 100.0, 100.0)]
    result = snap_endpoints(anchors, 0.5)
    # Los tres primeros caen en el mismo clúster; el último es otro nodo.
    assert len(result.node_coords) == 2
    ids1 = result.node_ids[(0.0, 0.0)]
    ids2 = result.node_ids[(100.0, 100.0)]
    assert ids1 != ids2
    assert deterministic_node_id([(0.0, 0.0)]) == deterministic_node_id([(0.0, 0.0)])


# --------------------------------------------------------------------------- topología
def test_topology_island_and_self_loop():
    model = _model_base()
    model.sections.append(Section(section_id='S2', from_node='B', to_node='G'))
    result = validate_topology(model)
    assert result.island_count == 1
    assert not result.ok()

    model2 = _model_base()
    model2.sections = [Section(section_id='S1', from_node='A', to_node='A')]
    result2 = validate_topology(model2, allow_self_loops=True)
    assert result2.self_loop_count == 1


def test_topology_missing_source():
    model = _model_base()
    model.sources = []
    result = validate_topology(model)
    assert any(i.code == 'missing_source' for i in result.issues)


# --------------------------------------------------------------------------- reconciliación
def test_diff_records():
    prev = {'a': {'geometry': 'g1', 'kw': 1}, 'c': {'geometry': 'g3', 'kw': 3}}
    curr = {'a': {'geometry': 'g9', 'kw': 1}, 'b': {'geometry': 'g2', 'kw': 2},
            'c': {'geometry': 'g3', 'kw': 4}}
    result = diff_records(prev, curr, attribute_keys=('kw',))
    assert result.classified['ADDED'] == ['b']
    assert result.classified['MODIFIED_GEOMETRY'] == ['a']
    assert result.classified['MODIFIED_ATTRIBUTES'] == ['c']


# --------------------------------------------------------------------------- eléctrico
def test_apparent_and_power_factor():
    assert apparent_power(3.0, 4.0) == pytest.approx(5.0)
    assert power_factor(3.0, 4.0) == pytest.approx(0.6)


def test_enrichment_blocks_without_catalog():
    model = _model_base()
    model.sections[0].conductor_code = 'AA120'
    report = enrich_electrical(model)
    assert 'AA120' in report.missing['conductors']
    assert not report.ready


# --------------------------------------------------------------------------- config/doctor
def test_settings_defaults_and_load(tmp_path):
    s = Settings()
    assert s.strict is True
    assert deep_get(s.as_dict(), 'gis.snap_tolerance_m') == 0.5
    cfg = tmp_path / 's.yaml'
    cfg.write_text('gis:\n  snap_tolerance_m: 2.0\n', encoding='utf-8')
    loaded = Settings.load(cfg)
    assert loaded.gis['snap_tolerance_m'] == 2.0
    assert loaded.gis['equipment_snap_tolerance_m'] == 1.00  # no se pierde lo no tocado


def test_doctor_report():
    report = doctor().report()
    assert 'Python:' in report
    assert 'Web UI' in report


# --------------------------------------------------------------------------- exportadores
def test_cymdist_blocked_without_verified_profile():
    model = _model_base()
    model.loads = [Load(load_id='L1', connection_node='B', kw=1, kvar=0)]
    exporter = CymdistExporter()
    assert exporter.validate_mapping(model) == []
    with pytest.raises(Exception) as info:
        exporter.export(model, Path('output'))
    assert 'bloqueado' in str(info.value).lower() or 'contract' in str(info.value).lower()


def _verified_dgs_profile(tmp_path):
    sample = tmp_path / 'verified-sample.dgs'
    sample.write_text('known-good-template', encoding='utf-8')
    return TargetProfile(
        simulator='PowerFactory',
        version='2024',
        workflow='DGS import',
        sample_path=str(sample),
        sample_hash=sha256_of(sample),
        object_mapping={'schema_profile': 'pf21_dgs_1_8_4'},
    )


def _production_ready_model() -> CanonicalModel:
    model = _model_base()
    model.metadata.update({
        'schema_fingerprint': 'schema',
        'source_fingerprint': 'source',
        'source_publication_id': 'PUB-1',
        'source_company': 'ELDU',
        'source_period': '2025',
        'source_url': 'https://www.osinergmin.gob.pe/source',
        'source_sha256': 'abc123',
        'retrieved_at': '2026-10-05T00:00:00Z',
        'canonical_model_version': '1.0',
        'working_crs': 'EPSG:32718',
        'working_crs_is_projected': True,
    })
    for node in model.nodes:
        node.nominal_kv = 10.0
    model.nodes = model.nodes[:2]
    model.sections[0].phases = 'ABC'
    model.loads = [Load(load_id='L1', connection_node='B', kw=100.0, kvar=40.0)]
    return model


def test_dgs_export_is_blocked_without_verified_profile(tmp_path):
    model = _model_base()
    model.nodes[0].nominal_kv = 10.0
    model.nodes[1].nominal_kv = 10.0
    model.loads = [Load(load_id='L1', connection_node='B', kw=100.0, kvar=40.0)]
    exporter = DgsExporter()

    with pytest.raises(ExportBlocked, match='perfil'):
        exporter.export(model, tmp_path)


def test_dgs_export_writes_file_with_verified_profile(tmp_path):
    model = _model_base()
    model.metadata.update({
        'schema_fingerprint': 'schema',
        'source_fingerprint': 'source',
        'source_publication_id': 'PUB-1',
        'source_company': 'ELDU',
        'source_period': '2025',
        'source_url': 'https://www.osinergmin.gob.pe/source',
        'source_sha256': 'abc123',
        'retrieved_at': '2026-10-05T00:00:00Z',
        'canonical_model_version': '1.0',
    })
    model.nodes[0].nominal_kv = 10.0
    model.nodes[1].nominal_kv = 10.0
    model.loads = [Load(load_id='L1', connection_node='B', kw=100.0, kvar=40.0)]
    exporter = DgsExporter(profile=_verified_dgs_profile(tmp_path))
    paths = exporter.export(model, tmp_path)
    assert len(paths) == 2 and all(path.is_file() for path in paths)
    dgs_path = next(path for path in paths if path.suffix == '.dgs')
    manifest_path = next(path for path in paths if path.name.endswith('.manifest.json'))
    text = dgs_path.read_text(encoding='utf-8')
    assert 'ElmTerm' in text and 'ElmLne' in text and 'ElmXnet' in text
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['source_publication_id'] == 'PUB-1'
    assert manifest['target_profile_hash'] == exporter.profile.sample_hash
    assert manifest['artifact_sha256'] == sha256_of(dgs_path)


def test_dgs_export_projects_node_coordinates_to_gps(tmp_path):
    from igea_dgs.validate import parse_dgs

    model = _production_ready_model()
    model.nodes[0].x, model.nodes[0].y = 500000.0, 8450000.0
    model.nodes[1].x, model.nodes[1].y = 500100.0, 8450000.0
    exporter = DgsExporter(profile=_verified_dgs_profile(tmp_path))
    dgs_path = next(path for path in exporter.export(model, tmp_path) if path.suffix == '.dgs')
    table = parse_dgs(dgs_path)['ElmTerm']
    lat_index = table['fields'].index('GPSlat')
    lon_index = table['fields'].index('GPSlon')
    assert all(row[lat_index] and row[lon_index] for row in table['rows'])
    assert all(-90 <= float(row[lat_index]) <= 90 for row in table['rows'])
    assert all(-180 <= float(row[lon_index]) <= 180 for row in table['rows'])


def test_dgs_export_blocks_missing_provenance(tmp_path):
    exporter = DgsExporter(profile=_verified_dgs_profile(tmp_path))
    with pytest.raises(ExportBlocked, match='procedencia'):
        exporter.export(_model_base(), tmp_path)


def test_target_profile_loads_relative_sample_and_validates_hash(tmp_path):
    sample = tmp_path / 'reference.dgs'
    sample.write_text('known-good', encoding='utf-8')
    profile_path = tmp_path / 'profile.json'
    profile_path.write_text(json.dumps({
        'simulator': 'PowerFactory',
        'version': '2024',
        'workflow': 'DGS import',
        'sample_path': 'reference.dgs',
        'sample_hash': sha256_of(sample),
        'object_mapping': {'schema_profile': 'pf21_dgs_1_8_4'},
    }), encoding='utf-8')

    profile = TargetProfile.load(profile_path)

    assert Path(profile.sample_path) == sample.resolve()
    assert profile.verified


def test_repository_dgs_profile_matches_reference_sample():
    profile = TargetProfile.load(Path('config/vnr_dgs_profile.json'))
    assert profile.verified
    assert profile.object_mapping['schema_profile'] == 'pf21_dgs_1_8_4'


def test_target_profile_detects_tampered_sample(tmp_path):
    profile = _verified_dgs_profile(tmp_path)
    assert profile.verified
    Path(profile.sample_path).write_text('tampered', encoding='utf-8')
    assert not profile.verified


def test_validation_gates_fail_closed_without_explicit_evidence():
    verdict = run_gates(_model_base())
    states = {result.gate: result.passed for result in verdict.results}
    assert states == {gate: False for gate in 'ABCDEFGH'}
    assert verdict.blocked


def test_validation_gates_require_and_accept_complete_simulator_evidence(tmp_path):
    model = _model_base()
    model.metadata.update({'schema_fingerprint': 'schema', 'source_fingerprint': 'source'})
    verdict = run_gates(
        model,
        crs_report={'ok': True, 'projected': True, 'working_crs': 'EPSG:32718'},
        topology_report={'ok': True, 'issues': []},
        enrichment={'ready': True},
        exporter_errors=[],
        export_profile_verified=_verified_dgs_profile(tmp_path).verified,
        roundtrip_ok=True,
        simulator_import_ok=True,
        load_flow_ok=True,
        require_simulator=True,
    )
    assert verdict.all_passed()
    assert not verdict.blocked


def test_application_service_blocks_before_writing_invalid_export(tmp_path):
    settings = Settings()
    profile_path = tmp_path / 'profile.json'
    profile = _verified_dgs_profile(tmp_path)
    profile_path.write_text(json.dumps({
        'simulator': profile.simulator,
        'version': profile.version,
        'workflow': profile.workflow,
        'sample_path': profile.sample_path,
        'sample_hash': profile.sample_hash,
        'object_mapping': profile.object_mapping,
    }), encoding='utf-8')
    settings.templates['dgs'] = str(profile_path)
    service = VnrApplicationService(settings)

    with pytest.raises(ExportBlocked):
        service.export(_model_base(), 'dgs', tmp_path / 'out')

    assert not list((tmp_path / 'out').rglob('*.dgs'))


def test_application_service_exports_only_after_a_to_f_evidence(tmp_path):
    settings = Settings()
    profile_path = tmp_path / 'profile.json'
    profile = _verified_dgs_profile(tmp_path)
    profile_path.write_text(json.dumps({
        'simulator': profile.simulator,
        'version': profile.version,
        'workflow': profile.workflow,
        'sample_path': profile.sample_path,
        'sample_hash': profile.sample_hash,
        'object_mapping': profile.object_mapping,
    }), encoding='utf-8')
    settings.templates['dgs'] = str(profile_path)

    result = VnrApplicationService(settings).export(
        _production_ready_model(), 'dgs', tmp_path / 'out'
    )

    assert all(result.verdict.results[index].passed for index in range(6))
    assert result.readiness == 'EXPORT_READY'
    assert len(result.paths) == 2


def test_application_service_requires_simulator_evidence_before_production_write(tmp_path):
    settings = Settings()
    profile_path = tmp_path / 'profile.json'
    profile = _verified_dgs_profile(tmp_path)
    profile_path.write_text(json.dumps({
        'simulator': profile.simulator,
        'version': profile.version,
        'workflow': profile.workflow,
        'sample_path': profile.sample_path,
        'sample_hash': profile.sample_hash,
        'object_mapping': profile.object_mapping,
    }), encoding='utf-8')
    settings.templates['dgs'] = str(profile_path)

    with pytest.raises(ExportBlocked, match='G/H'):
        VnrApplicationService(settings).export(
            _production_ready_model(), 'dgs', tmp_path / 'out', require_simulator=True
        )
    assert not (tmp_path / 'out').exists()


def test_web_uses_same_gates_and_protects_artifacts(tmp_path):
    from fastapi.testclient import TestClient

    from vnr_etl.web.app import create_app

    settings = Settings()
    profile_path = tmp_path / 'profile.json'
    profile = _verified_dgs_profile(tmp_path)
    profile_path.write_text(json.dumps({
        'simulator': profile.simulator,
        'version': profile.version,
        'workflow': profile.workflow,
        'sample_path': profile.sample_path,
        'sample_hash': profile.sample_hash,
        'object_mapping': profile.object_mapping,
    }), encoding='utf-8')
    settings.templates['dgs'] = str(profile_path)
    app = create_app(
        tmp_path / 'catalog', tmp_path / 'artifacts', settings, auth_token='secret'
    )

    with TestClient(app) as client:
        assert client.get('/api/doctor').status_code == 401
        headers = {'X-Session-Token': 'secret'}
        validation = client.post(
            '/api/validate', json={'canonical': _model_base().to_dict()}, headers=headers
        )
        assert validation.status_code == 200
        assert validation.json()['gates']['blocked'] is True

        submitted = client.post(
            '/api/export/dgs',
            json={'canonical': _production_ready_model().to_dict()},
            headers=headers,
        )
        assert submitted.status_code == 200
        job_id = submitted.json()['id']
        for _ in range(100):
            job = client.get(f'/api/jobs/{job_id}', headers=headers).json()
            if job['status'] in ('SUCCEEDED', 'FAILED'):
                break
            time.sleep(0.01)
        assert job['status'] == 'SUCCEEDED', job
        assert job['result']['readiness'] == 'EXPORT_READY'
        artifact = client.get(f'/api/artifacts/{job_id}/0', headers=headers)
        assert artifact.status_code == 200


def test_web_refuses_non_loopback_without_session_token(monkeypatch):
    from vnr_etl.web.__main__ import main

    monkeypatch.delenv('VNR_WEB_TOKEN', raising=False)
    with pytest.raises(SystemExit, match='VNR_WEB_TOKEN'):
        main(['--host', '0.0.0.0', '--no-browser'])


def test_web_upload_rejects_unsafe_archive_and_does_not_execute_sql(tmp_path):
    from fastapi.testclient import TestClient

    from vnr_etl.web.app import create_app

    app = create_app(tmp_path / 'catalog', tmp_path / 'artifacts')
    unsafe = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(unsafe, 'w') as zf:
        zf.writestr('../escape.txt', 'no')
    with TestClient(app) as client:
        with unsafe.open('rb') as stream:
            response = client.post(
                '/api/sources/upload', files={'file': ('unsafe.zip', stream, 'application/zip')}
            )
        assert response.status_code == 400
        assert not (tmp_path / 'escape.txt').exists()

        response = client.post(
            '/api/sources/upload',
            files={'file': ('backup.sql', b'CREATE TABLE danger (id INTEGER);', 'text/plain')},
        )
        assert response.status_code == 200
        assert response.json()['sql_inspection']['non_executed'] is True

        valid = tmp_path / 'valid.zip'
        with zipfile.ZipFile(valid, 'w') as zf:
            zf.writestr('network/sections.csv', 'CODTRAMOMT\nT1\n')
        with valid.open('rb') as stream:
            response = client.post(
                '/api/sources/upload', files={'file': ('valid.zip', stream, 'application/zip')}
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload['archive_safety'] == 'PASS'
        assert payload['extracted_sources'][0]['member'] == 'network\\sections.csv' or (
            payload['extracted_sources'][0]['member'] == 'network/sections.csv'
        )


def test_web_discovers_uploaded_sqlite_read_only(tmp_path):
    import sqlite3

    from fastapi.testclient import TestClient

    from vnr_etl.web.app import create_app

    database = tmp_path / 'network.sqlite'
    connection = sqlite3.connect(database)
    connection.execute('CREATE TABLE sections (id TEXT)')
    connection.commit()
    connection.close()
    app = create_app(tmp_path / 'catalog', tmp_path / 'artifacts')

    with TestClient(app) as client, database.open('rb') as stream:
        uploaded = client.post(
            '/api/sources/upload',
            files={'file': ('network.sqlite', stream, 'application/octet-stream')},
        ).json()
        source_id = uploaded['source_id']
        tested = client.post('/api/database/test', json={'source_id': source_id})
        discovered = client.post('/api/database/discover', json={'source_id': source_id})
    assert tested.json() == {'ok': True, 'engine': 'sqlite', 'read_only': True, 'tables': 1}
    assert discovered.json()['layers'][0]['name'] == 'sections'

    with TestClient(app) as client:
        spoofed = client.post(
            '/api/sources/upload',
            files={'file': ('fake.sqlite', b'not a database', 'application/octet-stream')},
        )
    assert spoofed.status_code == 400


# --------------------------------------------------------------------------- CLI
def test_cli_doctor(capsys):
    from vnr_etl.cli import main

    assert main(['doctor']) == 0
    assert 'Python:' in capsys.readouterr().out


def test_cli_version(capsys):
    from vnr_etl.cli import main

    assert main(['ver']) == 0
    assert __version__ in capsys.readouterr().out


def test_cli_companies_and_periods_report_source_values(tmp_path, capsys):
    from vnr_etl.cli import main

    source = tmp_path / 'vnr.csv'
    source.write_text(
        'CODEMP,ANIO,CODTRAMOMT\nELDU,2024,T1\nELDU,2025,T2\nSEAL,2025,T3\n',
        encoding='utf-8',
    )

    assert main(['companies', str(source)]) == 0
    company_output = capsys.readouterr().out
    assert 'ELDU' in company_output and 'SEAL' in company_output

    assert main(['periods', str(source), '--company', 'ELDU']) == 0
    period_output = capsys.readouterr().out
    assert '2024' in period_output and '2025' in period_output


def test_cli_inspects_sql_without_execution_and_reconciles(tmp_path, capsys):
    from vnr_etl.cli import main

    sql = tmp_path / 'backup.sql'
    sql.write_text('CREATE TABLE sections (id INTEGER PRIMARY KEY);', encoding='utf-8')
    assert main(['inspect-sql', str(sql)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection['non_executed'] is True
    assert inspection['tables'] == ['sections']

    previous = tmp_path / 'previous.json'
    current = tmp_path / 'current.json'
    previous.write_text(json.dumps({'A': {'value': 1}}), encoding='utf-8')
    current.write_text(json.dumps({'A': {'value': 2}, 'B': {'value': 1}}), encoding='utf-8')
    assert main([
        'reconcile', str(previous), str(current), '--attribute', 'value'
    ]) == 0
    reconciliation = json.loads(capsys.readouterr().out)
    assert reconciliation['summary']['ADDED'] == 1
    assert reconciliation['summary']['MODIFIED_ATTRIBUTES'] == 1


def test_cli_convert_scopes_records_and_writes_provenance(tmp_path):
    from vnr_etl.cli import main

    source = tmp_path / 'sections.geojson'
    source.write_text(json.dumps({
        'type': 'FeatureCollection',
        'features': [
            _arcgis_feature('OLD', [-75.0, -14.0], [-74.999, -14.0], feeder='F1'),
            _arcgis_feature('NEW', [-75.0, -14.0], [-74.998, -14.0], feeder='F1'),
        ],
    }), encoding='utf-8')
    payload = json.loads(source.read_text(encoding='utf-8'))
    payload['features'][0]['properties'].update({'CODEMP': 'ELDU', 'ANIO': 2024})
    payload['features'][1]['properties'].update({'CODEMP': 'ELDU', 'ANIO': 2025})
    source.write_text(json.dumps(payload), encoding='utf-8')
    output = tmp_path / 'out'

    assert main([
        'convert', str(source), '--company', 'ELDU', '--period', 'latest_available',
        '--source-crs', 'EPSG:4326', '--output', str(output),
    ]) == 0
    canonical = json.loads((output / 'canonical.json').read_text(encoding='utf-8'))
    assert [item['section_id'] for item in canonical['sections']] == ['NEW']
    assert canonical['metadata']['source_company'] == 'ELDU'
    assert canonical['metadata']['source_period'] == '2025'
    assert len(canonical['metadata']['source_sha256']) == 64


def test_cli_search_vnr_refreshes_official_catalog(tmp_path, capsys, monkeypatch):
    from vnr_etl.cli import main
    from vnr_etl.discovery import official

    monkeypatch.setattr(
        official,
        '_fetch_html',
        lambda _url: '<a href="/VNR/VNRGIS_2025.zip">VNRGIS 2025</a>',
    )
    page = 'https://www.osinergmin.gob.pe/Resoluciones/Resoluciones-GRT-2026.aspx'

    assert main([
        'search-vnr', '--source', page,
        '--catalog-dir', str(tmp_path / 'catalog'),
    ]) == 0
    output = capsys.readouterr().out
    assert 'REGULATORY_VNRGIS_PACKAGE' in output
    assert '"added": 1' in output


def test_cli_audit(tmp_path):
    from vnr_etl.cli import main

    assert main(['audit', '--project', str(tmp_path)]) == 0
    assert (tmp_path / 'AUDIT' / 'integration_plan.md').is_file()
