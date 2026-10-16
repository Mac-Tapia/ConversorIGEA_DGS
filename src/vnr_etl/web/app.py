"""Rutas HTTP del módulo `vnr_etl` (sección E20 de VNR-GIS.md), dentro de la API principal.

Eran una segunda aplicación FastAPI, con su propia cola de trabajos y su propio
lanzador (`vnr-etl-web`): dos API y dos colas que vigilar, y dos sitios donde corregir
lo mismo (spec 001, RF-11). Ahora son un ``APIRouter`` bajo ``/api/vnr`` que
:func:`igea_dgs.web.app.create_app` monta, y sus trabajos van al ``JobManager`` común.
Lo que la API principal ya ofrece (salud, catálogo oficial con ``refresh``, estado de
un trabajo) no se repite aquí.

El trabajo lo hacen las funciones de :mod:`vnr_etl.pipeline`; estas rutas solo
validan y despachan.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..application import VnrApplicationService
from ..config import Settings
from ..discovery import PublicationCatalog
from ..doctor import doctor

# Los trabajos de VNR no son de ningún espacio de trabajo; el JobManager los guarda
# bajo este identificador, que no corresponde a ninguno (sus eventos no se publican).
VNR_JOBS = '_vnr'


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


def create_router(root: Path | str, jobs: Any, settings: Settings | None = None) -> APIRouter:
    """Rutas de VNR bajo ``/api/vnr``. ``jobs`` es el ``JobManager`` de la API principal."""
    from igea_dgs.web.jobs import DONE

    resolved_settings = settings or Settings()
    root = Path(root).resolve()
    catalog_root = root / '_vnr_catalog'
    artifacts_root = root / '_vnr_output'
    uploads_root = root / '_vnr_uploads'
    uploads_root.mkdir(parents=True, exist_ok=True)
    uploaded_sources: dict[str, Path] = {}
    service = VnrApplicationService(resolved_settings)
    router = APIRouter(prefix='/api/vnr')

    def submit(kind: str, title: str, fn) -> dict:
        return jobs.submit(VNR_JOBS, kind, title, lambda _ctx: fn(), lane='engine').public()

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

    @router.get('/doctor')
    def api_doctor() -> dict:
        d = doctor()
        return {
            'python': d.python_version,
            'packages': d.packages,
            'native': d.native,
            'web_ui': d.web_ui,
        }

    @router.get('/companies')
    def companies() -> dict:
        catalog = PublicationCatalog.load(catalog_root)
        return {'companies': [c.as_dict() for c in catalog.companies()]}

    @router.post('/download', status_code=202)
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

        return submit('download', f'Descargar {publication.publication_id}', run)

    @router.post('/sources/upload')
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

    @router.post('/schema/resolve')
    def schema_resolve(body: SourceIn) -> dict:
        from ..discovery.schema import SchemaResolver

        resolver = SchemaResolver(aliases=body.aliases or None)
        result = resolver.resolve_fields(body.fields, layer=body.layer)
        return {'mapping': {k: v.as_dict() for k, v in result.items()}}

    @router.post('/sources/inspect')
    def sources_inspect(body: SourceIn) -> dict:
        from ..pipeline import discover_layers, probe_source

        source = source_for(body)
        try:
            probe = probe_source(source)
            layers = discover_layers(source)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc))
        return {'probe': probe, 'layers': layers}

    @router.post('/topology/build')
    def topology_build(body: SourceIn) -> dict:
        from ..pipeline import (
            buscar_capa_de_tramos, canonicalize_sections, discover_layers, read_layer,
        )

        try:
            source = source_for(body)
            layers = discover_layers(source)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc))
        target = buscar_capa_de_tramos(layers)
        if target is None:
            raise HTTPException(400, 'no se identificó una capa de tramos.')
        rows = read_layer(source, target.get('name') or target.get('layer_id'))
        source_crs = target.get('crs')
        avisos = []
        if not source_crs:
            # Se deduce de las coordenadas en vez de rechazar la capa (RF-25).
            from ..pipeline import deducir_crs_de_tramos

            source_crs, motivo = deducir_crs_de_tramos(rows)
            avisos.append(motivo)
        result = canonicalize_sections(
            rows,
            source_crs=source_crs,
            source_layer=str(target.get('name') or target.get('layer_id')),
        )
        return {'counts': result.model.counts(), 'warnings': avisos + result.warnings,
                'source_crs': source_crs}

    @router.post('/database/test')
    def database_test(body: DatabaseIn) -> dict:
        from ..connectors.databases import SQLiteAdapter

        path = Path(source_for(body))
        if path.suffix.lower() not in ('.sqlite', '.db'):
            raise HTTPException(400, 'esta ruta demuestra solo SQLite en modo lectura.')
        adapter = SQLiteAdapter(path=str(path), read_only=True)
        return {'ok': True, 'engine': 'sqlite', 'read_only': True,
                'tables': len(adapter.list_layers())}

    @router.post('/database/discover')
    def database_discover(body: DatabaseIn) -> dict:
        from ..connectors.databases import SQLiteAdapter

        path = Path(source_for(body))
        if path.suffix.lower() not in ('.sqlite', '.db'):
            raise HTTPException(400, 'adaptador directo no disponible para este formato.')
        adapter = SQLiteAdapter(path=str(path), read_only=True)
        return {'engine': 'sqlite', 'read_only': True,
                'layers': [item.as_dict() for item in adapter.list_layers()]}

    @router.post('/validate')
    def validate(body: ValidateIn) -> dict:
        from ..models import CanonicalModel

        try:
            model = CanonicalModel.from_dict(body.canonical)
        except (TypeError, ValueError, KeyError) as exc:
            raise HTTPException(400, f'modelo canónico inválido: {exc}') from exc
        return service.assess(model, 'dgs').as_dict()

    @router.post('/reconcile')
    def reconcile(body: ReconcileIn) -> dict:
        from ..reconciliation.diff import diff_records

        result = diff_records(
            body.previous,
            body.current,
            geometry_key=body.geometry_key,
            attribute_keys=body.attribute_keys,
        )
        return {'summary': result.summary(), 'classified': result.as_dict()}

    @router.post('/export/{target}', status_code=202)
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

        return submit(f'vnr_export_{target}', f'Exportar a {target.upper()}', run)

    @router.get('/artifacts/{job_id}/{index}')
    def get_artifact(job_id: str, index: int):
        job = jobs.get(job_id)
        if job is None or job.workspace_id != VNR_JOBS or job.status != DONE:
            raise HTTPException(404, 'trabajo o artefacto no disponible.')
        paths = (job.result or {}).get('paths') or []
        if index < 0 or index >= len(paths):
            raise HTTPException(404, 'artefacto no encontrado.')
        path = Path(paths[index]).resolve()
        if artifacts_root != path and artifacts_root not in path.parents:
            raise HTTPException(403, 'artefacto fuera del directorio autorizado.')
        if not path.is_file():
            raise HTTPException(404, 'artefacto no encontrado.')
        return FileResponse(path, filename=path.name)

    return router
