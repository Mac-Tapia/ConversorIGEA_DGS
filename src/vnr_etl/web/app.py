"""API HTTP del módulo `vnr_etl` (sección E20 de VNR-GIS.md).

El trabajo lo hacen las funciones de :mod:`vnr_etl.pipeline`; estas rutas solo
validan y despachan. Para no replicar el patrón de colas del proyecto anfitrión
aquí se usa una cola mínima de trabajos en segundo plano, de modo que una
descarga o un export no quedan dentro de la petición HTTP.
"""

from __future__ import annotations

import hashlib
import os
import queue
import secrets
import shutil
import threading
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..application import VnrApplicationService
from ..config import Settings
from ..discovery import PublicationCatalog
from ..doctor import doctor


class SourceIn(BaseModel):
    source: str = ''
    source_id: str = ''
    fields: list[str] = Field(default_factory=list)
    layer: str = ''
    aliases: dict = Field(default_factory=dict)


class ValidateIn(BaseModel):
    canonical: dict = Field(default_factory=dict)


class PublicationIn(BaseModel):
    publication_id: str


class DatabaseIn(BaseModel):
    source_id: str


class ReconcileIn(BaseModel):
    previous: dict[str, dict] = Field(default_factory=dict)
    current: dict[str, dict] = Field(default_factory=dict)
    geometry_key: str = 'geometry'
    attribute_keys: list[str] = Field(default_factory=list)


class _Jobs:
    """Cola mínima de trabajos en segundo plano (estado + resultado)."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._workers: dict[str, threading.Thread] = {}
        self._queues: dict[str, queue.Queue] = {}

    def submit(self, kind: str, fn: Callable[[], Any]) -> dict:
        job_id = uuid.uuid4().hex[:12]
        lane = kind
        now = datetime.now(UTC).isoformat()
        self._jobs[job_id] = {
            'id': job_id, 'kind': kind, 'status': 'QUEUED', 'progress': 0,
            'result': None, 'error': None, 'created_at': now, 'updated_at': now,
        }
        self._queues.setdefault(lane, queue.Queue()).put((job_id, fn))
        self._ensure_worker(lane)
        return self._jobs[job_id]

    def get(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    def _ensure_worker(self, lane: str) -> None:
        thread = self._workers.get(lane)
        if thread is None or not thread.is_alive():
            thread = threading.Thread(target=self._worker, args=(lane,), daemon=True, name=f'vnr-{lane}')
            self._workers[lane] = thread
            thread.start()

    def _worker(self, lane: str) -> None:
        q = self._queues[lane]
        while True:
            item = q.get()
            if item is None:
                return
            job_id, fn = item
            job = self._jobs[job_id]
            job['status'] = 'RUNNING'
            job['progress'] = 10
            job['updated_at'] = datetime.now(UTC).isoformat()
            try:
                job['result'] = fn()
                job['status'] = 'SUCCEEDED'
                job['progress'] = 100
            except Exception as exc:  # noqa: BLE001 - el trabajo informa
                job['error'] = str(exc) or exc.__class__.__name__
                job['status'] = 'FAILED'
                job['progress'] = 100
            job['updated_at'] = datetime.now(UTC).isoformat()

    def shutdown(self) -> None:
        for lane in list(self._queues):
            self._queues[lane].put(None)


def create_app(
    data_root: Path | str = 'data/vnr_catalog',
    output_root: Path | str = 'output/vnr',
    settings: Settings | None = None,
    auth_token: str | None = None,
) -> FastAPI:
    jobs = _Jobs()
    resolved_settings = settings or Settings()
    catalog_root = Path(data_root).resolve()
    artifacts_root = Path(output_root).resolve()
    uploads_root = (catalog_root.parent / 'uploads').resolve()
    uploads_root.mkdir(parents=True, exist_ok=True)
    uploaded_sources: dict[str, Path] = {}
    service = VnrApplicationService(resolved_settings)

    def source_for(body: SourceIn | DatabaseIn) -> str:
        source_id = getattr(body, 'source_id', '')
        if source_id:
            path = uploaded_sources.get(source_id)
            if path is None or not path.is_file():
                raise HTTPException(404, 'fuente cargada no encontrada.')
            return str(path)
        source = getattr(body, 'source', '')
        parsed = urlparse(source)
        allowed_hosts = tuple(resolved_settings.discovery.get('allowed_hosts', ()))
        if parsed.scheme == 'https' and any(
            (parsed.hostname or '').lower() == host
            or (parsed.hostname or '').lower().endswith('.' + host)
            for host in allowed_hosts
        ):
            return source
        raise HTTPException(400, 'use source_id de una carga controlada o una URL oficial HTTPS.')

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        jobs.shutdown()

    app = FastAPI(title='vnr_etl — VNRGIS/CYMDIST/DGS', version=__version__, lifespan=lifespan)

    @app.middleware('http')
    async def authentication(request: Request, call_next):
        if auth_token and request.url.path != '/api/health':
            supplied = request.headers.get('X-Session-Token', '')
            if not secrets.compare_digest(supplied, auth_token):
                return JSONResponse(status_code=401, content={'detail': 'token de sesión inválido.'})
        return await call_next(request)

    @app.exception_handler(HTTPException)
    async def _http(_req, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})

    @app.get('/api/health')
    def health() -> dict:
        return {'version': __version__, 'modules': {'igea_dgs': True, 'vnr_etl': True}}

    @app.get('/api/doctor')
    def api_doctor() -> dict:
        d = doctor()
        return {
            'python': d.python_version,
            'packages': d.packages,
            'native': d.native,
            'web_ui': d.web_ui,
        }

    @app.get('/api/vnr/companies')
    def companies() -> dict:
        catalog = PublicationCatalog.load(catalog_root)
        return {'companies': [c.as_dict() for c in catalog.companies()]}

    @app.get('/api/vnr/publications')
    def publications(company: str | None = None) -> dict:
        catalog = PublicationCatalog.load(catalog_root)
        pubs = catalog.publications(company=company)
        return {'publications': [p.as_dict() for p in pubs]}

    @app.post('/api/discovery/refresh')
    def refresh() -> dict:
        def run() -> dict:
            from ..discovery import refresh_official_catalog

            _catalog, report = refresh_official_catalog(catalog_root)
            return report
        return jobs.submit('discovery', run)

    @app.post('/api/vnr/download')
    def download_publication(body: PublicationIn) -> dict:
        publication = PublicationCatalog.load(catalog_root).get(body.publication_id)
        if publication is None or not publication.download_url:
            raise HTTPException(404, 'publicación descargable no encontrada.')

        def run() -> dict:
            from ..discovery import DownloadManager

            destination = uploads_root / (publication.file_name or f'{publication.publication_id}.bin')
            manager = DownloadManager(
                uploads_root,
                max_file_size_bytes=int(resolved_settings.download['max_file_size_mb']) * 1024 * 1024,
                allowed_hosts=resolved_settings.discovery.get('allowed_hosts', ()),
            )
            manifest = manager.download(
                publication.download_url,
                destination,
                publication_id=publication.publication_id,
                company=publication.company or publication.company_code,
                period=publication.period_label,
            )
            source_id = uuid.uuid4().hex
            uploaded_sources[source_id] = destination.resolve()
            return {'source_id': source_id, 'manifest': manifest.as_dict()}

        return jobs.submit('download', run)

    @app.post('/api/sources/upload')
    async def upload_source(file: Annotated[UploadFile, File()]) -> dict:
        from ..connectors.databases import inspect_sql_dump
        from ..discovery.download import DownloadError, inventory_zip, safe_extract_zip

        filename = Path(file.filename or 'upload.bin').name
        suffix = Path(filename).suffix.lower()
        allowed = {'.zip', '.rar', '.sql', '.sqlite', '.db', '.mdb', '.accdb',
                   '.shp', '.gpkg', '.geojson', '.json', '.csv', '.tsv', '.txt'}
        if suffix not in allowed:
            raise HTTPException(415, f'formato no permitido: {suffix or "sin extensión"}.')
        max_bytes = min(
            int(resolved_settings.download.get('max_file_size_mb', 512)), 512
        ) * 1024 * 1024
        source_id = uuid.uuid4().hex
        destination = uploads_root / f'{source_id}{suffix}'
        extraction_root = uploads_root / f'{source_id}_extracted'
        temporary = destination.with_suffix(destination.suffix + '.part')
        size = 0
        digest = hashlib.sha256()
        try:
            with temporary.open('wb') as stream:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(413, 'la carga supera el límite permitido.')
                    digest.update(chunk)
                    stream.write(chunk)
            os.replace(temporary, destination)
            details: dict = {}
            if suffix == '.zip':
                import zipfile

                if not zipfile.is_zipfile(destination):
                    raise HTTPException(400, 'el contenido no corresponde a un ZIP válido.')
                try:
                    details['archive_inventory'] = inventory_zip(destination)
                    extracted = safe_extract_zip(
                        destination,
                        extraction_root,
                        uncompressed_limit_bytes=max_bytes * 2,
                    )
                except DownloadError as exc:
                    raise HTTPException(400, str(exc)) from exc
                details['archive_safety'] = 'PASS'
                supported = {'.shp', '.gpkg', '.geojson', '.json', '.csv', '.tsv',
                             '.txt', '.sqlite', '.db', '.mdb', '.accdb'}
                extracted_sources = []
                for extracted_path in extracted:
                    if extracted_path.suffix.lower() not in supported:
                        continue
                    extracted_id = uuid.uuid4().hex
                    uploaded_sources[extracted_id] = extracted_path.resolve()
                    extracted_sources.append({
                        'source_id': extracted_id,
                        'member': str(extracted_path.relative_to(extraction_root)),
                    })
                details['extracted_sources'] = extracted_sources
            elif suffix == '.sql':
                details['sql_inspection'] = inspect_sql_dump(destination)
            elif suffix in ('.sqlite', '.db'):
                with destination.open('rb') as stream:
                    if stream.read(16) != b'SQLite format 3\x00':
                        raise HTTPException(400, 'el contenido no corresponde a SQLite 3.')
            uploaded_sources[source_id] = destination.resolve()
            return {
                'source_id': source_id,
                'file_name': filename,
                'detected_format': suffix.lstrip('.').upper(),
                'bytes': size,
                'sha256': digest.hexdigest(),
                'stored_name': destination.name,
                **details,
            }
        except Exception:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            if extraction_root.is_dir():
                shutil.rmtree(extraction_root, ignore_errors=True)
            raise
        finally:
            await file.close()

    @app.post('/api/schema/resolve')
    def schema_resolve(body: SourceIn) -> dict:
        from ..discovery.schema import SchemaResolver

        resolver = SchemaResolver(aliases=body.aliases or None)
        result = resolver.resolve_fields(body.fields, layer=body.layer)
        return {'mapping': {k: v.as_dict() for k, v in result.items()}}

    @app.post('/api/sources/inspect')
    def sources_inspect(body: SourceIn) -> dict:
        from ..pipeline import discover_layers, probe_source

        source = source_for(body)
        try:
            probe = probe_source(source)
            layers = discover_layers(source)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc))
        return {'probe': probe, 'layers': layers}

    @app.post('/api/topology/build')
    def topology_build(body: SourceIn) -> dict:
        from ..pipeline import canonicalize_sections, discover_layers, read_layer

        try:
            source = source_for(body)
            layers = discover_layers(source)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc))
        target = next((l for l in layers if 'tramo' in (l.get('name') or '').lower()), None)
        if target is None:
            raise HTTPException(400, 'no se identificó una capa de tramos.')
        source_crs = target.get('crs')
        if not source_crs:
            raise HTTPException(400, 'la capa no declara CRS; no se asumirá uno.')
        rows = read_layer(source, target.get('name') or target.get('layer_id'))
        result = canonicalize_sections(
            rows,
            source_crs=source_crs,
            source_layer=str(target.get('name') or target.get('layer_id')),
        )
        return {'counts': result.model.counts(), 'warnings': result.warnings}

    @app.post('/api/database/test')
    def database_test(body: DatabaseIn) -> dict:
        from ..connectors.databases import SQLiteAdapter

        path = Path(source_for(body))
        if path.suffix.lower() not in ('.sqlite', '.db'):
            raise HTTPException(400, 'esta ruta demuestra solo SQLite en modo lectura.')
        adapter = SQLiteAdapter(path=str(path), read_only=True)
        return {'ok': True, 'engine': 'sqlite', 'read_only': True,
                'tables': len(adapter.list_layers())}

    @app.post('/api/database/discover')
    def database_discover(body: DatabaseIn) -> dict:
        from ..connectors.databases import SQLiteAdapter

        path = Path(source_for(body))
        if path.suffix.lower() not in ('.sqlite', '.db'):
            raise HTTPException(400, 'adaptador directo no disponible para este formato.')
        adapter = SQLiteAdapter(path=str(path), read_only=True)
        return {'engine': 'sqlite', 'read_only': True,
                'layers': [item.as_dict() for item in adapter.list_layers()]}

    @app.post('/api/validate')
    def validate(body: ValidateIn) -> dict:
        from ..models import CanonicalModel

        try:
            model = CanonicalModel.from_dict(body.canonical)
        except (TypeError, ValueError, KeyError) as exc:
            raise HTTPException(400, f'modelo canónico inválido: {exc}') from exc
        return service.assess(model, 'dgs').as_dict()

    @app.post('/api/reconcile')
    def reconcile(body: ReconcileIn) -> dict:
        from ..reconciliation.diff import diff_records

        result = diff_records(
            body.previous,
            body.current,
            geometry_key=body.geometry_key,
            attribute_keys=body.attribute_keys,
        )
        return {'summary': result.summary(), 'classified': result.as_dict()}

    @app.post('/api/export/{target}')
    def export(target: str, body: ValidateIn) -> dict:
        from ..models import CanonicalModel
        if target not in ('cymdist', 'dgs'):
            raise HTTPException(404, 'destino desconocido.')
        try:
            model = CanonicalModel.from_dict(body.canonical)
        except (TypeError, ValueError, KeyError) as exc:
            raise HTTPException(400, f'modelo canónico inválido: {exc}') from exc

        def run() -> dict:
            result = service.export(model, target, artifacts_root)
            return result.as_dict()

        return jobs.submit(target, run)

    @app.get('/api/jobs/{job_id}')
    def get_job(job_id: str) -> dict:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, 'trabajo no encontrado.')
        return job

    @app.get('/api/artifacts/{job_id}/{index}')
    def get_artifact(job_id: str, index: int):
        job = jobs.get(job_id)
        if job is None or job.get('status') != 'SUCCEEDED':
            raise HTTPException(404, 'trabajo o artefacto no disponible.')
        paths = (job.get('result') or {}).get('paths') or []
        if index < 0 or index >= len(paths):
            raise HTTPException(404, 'artefacto no encontrado.')
        path = Path(paths[index]).resolve()
        if artifacts_root != path and artifacts_root not in path.parents:
            raise HTTPException(403, 'artefacto fuera del directorio autorizado.')
        if not path.is_file():
            raise HTTPException(404, 'artefacto no encontrado.')
        return FileResponse(path, filename=path.name)

    return app
