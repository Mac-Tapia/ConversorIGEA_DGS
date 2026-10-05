from __future__ import annotations

import hashlib
import time
import zipfile
from pathlib import Path

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('httpx')

from fastapi.testclient import TestClient

from vnr_etl.discovery.catalog import Publication, PublicationCatalog


def _publication(publication_id: str, url: str, kind: str) -> Publication:
    return Publication(
        publication_id=publication_id,
        title='VNRGIS Electro Dunas 2025',
        publication_type=kind,
        regulatory_reference='154-2026-OS/CD',
        reference_date='2025',
        published_at='2026-08-27',
        discovered_at='2026-10-05T00:00:00+00:00',
        official_page='https://www.osinergmin.gob.pe/Resoluciones/Resoluciones-GRT-2026.aspx',
        company='Electro Dunas',
        company_code='ELDU',
        period_label='2025',
        download_url=url,
        file_name=Path(url).name,
        file_type=Path(url).suffix.lstrip('.').upper(),
    )


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from igea_dgs.web.app import create_app

    monkeypatch.setenv('IGEA_WEB_FRONTEND', str(tmp_path / 'no-front'))
    data_root = tmp_path / 'web'
    catalog = PublicationCatalog()
    catalog.upsert_publication(_publication(
        'PDF-154',
        'https://www.osinergmin.gob.pe/docs/Resolucion-154-2026-OS-CD.pdf',
        'REGULATORY_VNR_PUBLICATION',
    ))
    catalog.upsert_publication(_publication(
        'PKG-ELDU',
        'https://www2.osinergmin.gob.pe/GRT/VNR/ELDU_2025.zip',
        'REGULATORY_VNRGIS_PACKAGE',
    ))
    catalog.upsert_publication(_publication(
        'PKG-EVIL',
        'https://evil.example/VNR/ELDU_2025.zip',
        'REGULATORY_VNRGIS_PACKAGE',
    ))
    catalog.save(data_root / '_vnr_catalog')
    with TestClient(create_app(data_root)) as value:
        yield value


def _workspace(client: TestClient) -> str:
    response = client.post('/api/workspaces')
    assert response.status_code == 201
    return response.json()['id']


def _valid_zip(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('Tramo_MT.geojson', '{"type":"FeatureCollection","features":[]}')
    return path


def test_publications_expone_evidencia_y_no_ofrece_pdf_como_paquete(client):
    response = client.get('/api/vnr/publications')

    assert response.status_code == 200
    body = response.json()
    rows = {row['publication_id']: row for row in body['publications']}
    assert rows['PDF-154']['convertible'] is False
    assert rows['PDF-154']['status'] == 'REGULATORY_DOCUMENT_ONLY'
    assert rows['PKG-ELDU']['convertible'] is True
    assert rows['PKG-ELDU']['published_at'] == '2026-08-27'
    assert len(rows['PKG-ELDU']['evidence_sha256']) == 64
    assert body['status'] == 'OFFICIAL_PACKAGE_AVAILABLE'


def test_download_rechaza_documento_y_host_no_oficial(client):
    wid = _workspace(client)

    pdf = client.post(f'/api/workspaces/{wid}/vnr/download', json={'publication_id': 'PDF-154'})
    assert pdf.status_code == 400
    assert 'no es un paquete de datos' in pdf.json()['detail']

    evil = client.post(f'/api/workspaces/{wid}/vnr/download', json={'publication_id': 'PKG-EVIL'})
    assert evil.status_code == 400
    assert 'oficial' in evil.json()['detail'].lower()


def test_download_oficial_custodia_hash_y_asigna_slot(client, monkeypatch):
    from vnr_etl.discovery.download import DownloadManifest, DownloadManager

    def fake_download(self, url, destination, **kwargs):
        del self, kwargs
        destination = _valid_zip(Path(destination))
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        return DownloadManifest(
            publication_id='PKG-ELDU', company='Electro Dunas', period='2025',
            source_url=url, retrieved_at='2026-10-05T00:00:00Z', http_status=200,
            content_type='application/zip', bytes=destination.stat().st_size,
            sha256=digest, archive_test='PASS',
        )

    monkeypatch.setattr(DownloadManager, 'download', fake_download)
    wid = _workspace(client)

    response = client.post(
        f'/api/workspaces/{wid}/vnr/download', json={'publication_id': 'PKG-ELDU'},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body['manifest']['archive_test'] == 'PASS'
    assert len(body['manifest']['sha256']) == 64
    assert body['workspace']['inputs']['vnr_package']['name'] == 'ELDU_2025.zip'
    assert body['workspace']['options']['input_mode'] == 'vnr'


def test_carga_manual_vnr_por_upload_y_ruta_rechaza_pdf(client, tmp_path):
    wid = _workspace(client)
    archive = _valid_zip(tmp_path / 'manual.zip')

    with archive.open('rb') as handle:
        uploaded = client.post(
            f'/api/workspaces/{wid}/inputs/vnr_package',
            files={'file': (archive.name, handle, 'application/zip')},
        )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()['workspace']['inputs']['vnr_package']['name'] == 'manual.zip'

    assigned = client.post(
        f'/api/workspaces/{wid}/inputs/vnr_package/path', json={'path': str(archive)},
    )
    assert assigned.status_code == 200
    assert assigned.json()['workspace']['options']['input_mode'] == 'vnr'

    rejected = client.post(
        f'/api/workspaces/{wid}/inputs/vnr_package',
        files={'file': ('resolucion.pdf', b'%PDF-1.7 regulatory document', 'application/pdf')},
    )
    assert rejected.status_code == 400
    assert 'paquete VNR-GIS' in rejected.json()['detail']


def test_health_y_opciones_exponen_modo_vnr(client):
    health = client.get('/api/health').json()
    assert health['slots']['vnr_package']['grupo'] == 'vnr'
    assert health['slots']['vnr_package']['obligatorio'] is True
    wid = _workspace(client)
    response = client.put(f'/api/workspaces/{wid}/options', json={'input_mode': 'vnr'})
    assert response.status_code == 200
    assert response.json()['options']['input_mode'] == 'vnr'
    assert response.json()['missing_inputs'] == ['Paquete completo VNR-GIS']


@pytest.mark.parametrize('content_type', ['application/pdf', 'text/html; charset=utf-8'])
def test_stream_rechaza_respuesta_documental_aunque_url_diga_zip(tmp_path, content_type):
    from vnr_etl.discovery.download import DownloadError, DownloadManager

    class Response:
        status_code = 200
        url = 'https://www2.osinergmin.gob.pe/GRT/VNR/ELDU_2025.zip'
        headers = {'Content-Type': content_type, 'Content-Length': '8'}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def iter_content(self, chunk_size):
            del chunk_size
            yield b'%PDF-1.7'

    class Requests:
        @staticmethod
        def get(*_args, **_kwargs):
            return Response()

    manager = DownloadManager(tmp_path / 'cache')
    with pytest.raises(DownloadError, match='no es un paquete de datos'):
        manager._stream(
            Requests, Response.url, tmp_path / 'download.part', on_progress=None,
        )
