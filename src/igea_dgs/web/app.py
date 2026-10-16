"""API HTTP del conversor: FastAPI sobre el motor ``igea_dgs``, sin reescribirlo.

Las rutas validan, encolan y responden; el trabajo lo hacen :mod:`.services` y el
motor. El progreso y el Registro llegan al navegador por un WebSocket por espacio
de trabajo (``/api/workspaces/{id}/ws``), numerado para que una reconexión no pierda
ni duplique líneas.

Si existe ``frontend/dist`` (``npm run build``), se sirve en ``/`` y la aplicación
entera queda en un solo proceso y un solo puerto.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import threading
import zipfile
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import (
    BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..identify import comprobar_ranura, identificar
from ..powerfactory_env import project_root
from . import services
from .jobs import JobManager
from .services import UserError
from .workspace import (
    BOOL_OPTIONS, DEFAULT_OPTIONS, MAX_WORKERS, SLOTS, Workspace, WorkspaceStore, safe_filename,
)


LOOPBACK_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})


def _server_paths_allowed(host: str | None) -> bool:
    """Si se puede indicar una ruta del disco del servidor en lugar de subir el fichero.

    Útil en local —la base .mdb pesa cientos de MB y ya está en el disco—, peligroso
    si el servidor se expone en red: cualquiera leería cualquier fichero. Antes lo
    decidía solo la variable ``IGEA_WEB_SERVER_PATHS``, que valía ``1`` por defecto y
    que el lanzador ponía a ``0`` con ``setdefault``: con la variable ya a ``1``, o
    arrancando con ``uvicorn --host 0.0.0.0`` sin el lanzador, quedaban abiertas a la
    red (spec 001, RF-15). Ahora manda la interfaz de escucha, y si no se conoce, se
    cierran. La variable solo puede apagarlas en local, nunca abrirlas fuera.
    """
    if (host or '').strip().lower() not in LOOPBACK_HOSTS:
        return False
    return os.environ.get('IGEA_WEB_SERVER_PATHS', '1').strip() not in ('0', 'false', 'no', '')


# Cabecera con la que el lanzador pide cerrar el servidor. Una cabecera propia obliga al
# navegador a una consulta CORS previa, que solo pasan los orígenes de desarrollo: una
# página cualquiera no puede cerrar el Conversor con un formulario.
CABECERA_LANZADOR = 'X-Igea-Lanzador'

_cierre: list = []


def al_pedir_cierre(fn) -> None:
    """Registra cómo se cierra este proceso; lo pone el lanzador, que tiene el servidor."""
    _cierre[:] = [fn]


def frontend_dist() -> Path:
    env = os.environ.get('IGEA_WEB_FRONTEND', '').strip()
    return Path(env) if env else project_root() / 'frontend' / 'dist'


# ---------------------------------------------------------------------------
# Modelos de petición
# ---------------------------------------------------------------------------


class OptionsIn(BaseModel):
    input_mode: Literal['txt', 'mdb', 'vnr'] | None = None
    source_crs: str | None = None
    target_crs: str | None = None
    include_geography: bool | None = None
    strict: bool | None = None
    write_preview: bool | None = None
    export_xlsx: bool | None = None
    export_tsv: bool | None = None
    workers: int | None = Field(None, ge=0, le=MAX_WORKERS)
    hoja: Literal['A0', 'A1', 'A2', 'A3', 'A4'] | None = None


class ServerPathIn(BaseModel):
    path: str


# Libros de la demanda medida (spec 004, RF-39).
DemandaTipo = Literal['medidores', 'cabecera', 'suministros', 'clientes']


class DemandaMedidorIn(BaseModel):
    alimentador: str = ''
    medidor: str


class DemandaMedidoresIn(BaseModel):
    medidores: list[DemandaMedidorIn] = Field(default_factory=list)


class DemandaClientesIn(BaseModel):
    """Alimentadores de la máxima buscada: el cruce se queda con sus clientes (RF-43)."""

    alimentadores: list[str] = Field(default_factory=list)
    # Spec 013, RF-12: con una carpeta de libros mensuales, el mes que eligió el operador.
    periodo: str | None = Field(default=None, pattern=r'^\d{4}-(0[1-9]|1[0-2])$')


class TransformadoresIn(BaseModel):
    """020:RF-13: las SED marcadas de un alimentador del ajuste."""

    feeder: str
    sed: list[str] = Field(default_factory=list, max_length=2000)


class AjusteIn(BaseModel):
    """Ajuste a la máxima de cabecera (spec 006): el trabajo de la máxima que se ve."""

    project: str
    job_id: str
    medidor: str = ''
    # Spec 008, RF-12: un medidor por alimentador, en el orden de ajuste. Vacío: el de
    # ``medidor`` o, si cada alimentador de la máxima tiene uno, todos.
    medidores: list[str] = Field(default_factory=list, max_length=2000)
    # Spec 006, RF-26: Nis de los clientes importantes desmarcados en la tabla del cruce.
    desconectados: list[str] = Field(default_factory=list, max_length=20000)
    # 1 % por defecto; entre 0,1 % y 10 % (requisitos no funcionales de la spec 006).
    tolerancia: float = Field(0.01, ge=0.001, le=0.10)


class VerificarIn(BaseModel):
    """Verificación de la convergencia (spec 008): el proyecto y los alimentadores a medir."""

    project: str
    feeders: list[str] = Field(default_factory=list, max_length=2000)


class DemandaExcelIn(BaseModel):
    """Lo que el operador ve en pantalla: el Excel no se arma con estado guardado (RF-38)."""

    cabecera: list[dict[str, Any]] = Field(default_factory=list)
    clientes: list[dict[str, Any]] = Field(default_factory=list)
    no_cruzados: list[dict[str, Any]] = Field(default_factory=list)


class BibliotecasIn(BaseModel):
    """Lectura de alimentadores y tipos para el formulario de obras (spec 011, RF-88 a RF-94)."""

    project: str
    feeders: list[str] = Field(default_factory=list, max_length=2000)
    otro_proyecto: str = ''
    clases: list[str] = Field(default_factory=list)


class ObrasIn(BaseModel):
    """Obras guardadas que se simulan o aplican; sin ``ids``, todas (spec 011)."""

    project: str
    feeders: list[str] = Field(default_factory=list, max_length=2000)
    ids: list[str] = Field(default_factory=list)
    otro_proyecto: str = ''


class EstudiosIn(BaseModel):
    """Plan de los estudios sobre la base del último ajuste aplicado (spec 011, RF-12, RF-25)."""

    project: str
    feeders: list[str] = Field(default_factory=list, max_length=2000)
    estudios: list[str] = Field(default_factory=list)
    ajuste_job_id: str | None = None
    limites: dict[str, float] = Field(default_factory=dict)
    # RF-39: límite por estudio y caso, entre 10 s y un día.
    limite_s: float | None = Field(None, ge=10, le=86400)


class InformeEstudioIn(BaseModel):
    """Formulario del informe de estudio (spec 017): todo dato del cliente y del encabezado
    sale de aquí; del modelo de la empresa solo se toma la forma."""

    alimentador: str
    # Los flujos de 4.2 de ese proyecto: un espacio puede haber estudiado otro antes.
    project: str = ''
    fecha: str | None = None
    lugar: str = ''
    numero: str = ''
    asunto: str = ''
    destinatario: str = ''
    antecedentes: list[str] = Field(default_factory=list, max_length=200)
    descripcion: list[str] = Field(default_factory=list, max_length=200)
    limites: dict[str, float] = Field(default_factory=dict)
    anio: int | None = None
    imagenes: dict[str, dict[str, str | None]] = Field(default_factory=dict)


class SolicitudIn(BaseModel):
    """Datos de la solicitud de la carga nueva (017:RF-51); el servidor los valida antes de
    empezar (RF-96), para no escribir un Word con antecedentes en blanco."""

    cliente: str = Field(min_length=1)
    ubicacion: str = Field(min_length=1)
    tipo_solicitud: str = Field(min_length=1)
    potencia_kw: float = Field(gt=0)
    fecha_solicitud: date
    set_nombre: str = Field(min_length=1)
    tension_kv: float = Field(gt=0)
    transformador: str = ''
    expediente: str = ''
    en_concesion: bool | None = None


class PerdidasReconocidasIn(BaseModel):
    """Lo que daría el libro de pérdidas de la empresa (RF-62), escrito a mano."""

    sistema_electrico: str = ''
    codigo_sistema: str = ''
    reconocido_kw_pct: float | None = Field(None, ge=0, le=100)
    reconocido_kwh_pct: float | None = Field(None, ge=0, le=100)
    precio_compra: float | None = Field(None, ge=0)


class TransformadorSetIn(BaseModel):
    """Cargabilidad del devanado de la SET (RF-66), leída por el operador en el proyecto
    de transmisión mientras el guion no la obtiene solo (T10 de la spec 017)."""

    kv: float | None = Field(None, gt=0)
    sin_pct: float | None = Field(None, ge=0)
    con_pct: float | None = Field(None, ge=0)
    caso: str = ''


class TransformadorListarIn(BaseModel):
    """Proyecto de transmisión; vacío, el del perfil de empresa (017:RF-95)."""

    transmision: str = ''


class TransformadorCalcularIn(BaseModel):
    """Carga de la barra de la SET en el proyecto de transmisión y su caso (017:RF-65b)."""

    project: str = Field(min_length=1)
    alimentador: str = Field(min_length=1)
    carga: str = Field(min_length=1)
    caso: str = ''
    transmision: str = ''


class InformeFormularioIn(BaseModel):
    """Lo escrito en un formulario de 4.4, para no perderlo al recargar (017:RF-82)."""

    project: str = Field(min_length=1)
    tipo: Literal['estudio', 'factibilidad']
    datos: dict[str, Any] = Field(default_factory=dict)


class InformeFactibilidadIn(BaseModel):
    """Formulario del informe de factibilidad y punto de diseño (spec 017, RF-47 a RF-72)."""

    project: str = Field(min_length=1)
    alimentador: str = Field(min_length=1)
    sed: str = Field(min_length=1)
    fecha: str | None = None
    lugar: str = ''
    numero: str = ''
    asunto: str = ''
    destinatario: str = ''
    solicitud: SolicitudIn
    limites: dict[str, float] = Field(default_factory=dict)
    factor_carga: float | None = Field(None, gt=0, le=1)
    perdidas_reconocidas: PerdidasReconocidasIn = Field(default_factory=PerdidasReconocidasIn)
    transformador_set: TransformadorSetIn = Field(default_factory=TransformadorSetIn)
    codigo_punto: str = ''


class TransferenciaIn(BaseModel):
    """Transferencia de carga entre dos alimentadores (spec 011, RF-104)."""

    project: str
    feeders: list[str] = Field(default_factory=list, max_length=2)
    casos: list[str] = Field(default_factory=lambda: ['Sin proyecto'])
    limites: dict[str, float] = Field(default_factory=dict)


class GuionesIn(BaseModel):
    """Guiones DPL y Python del operador en el proyecto (spec 011, RF-27)."""

    project: str


class GuionIn(BaseModel):
    """Un guion del operador en los casos elegidos, con sus parámetros (RF-28)."""

    project: str
    nombre: str
    origen: Literal['caso', 'proyecto'] = 'caso'
    parametros: dict[str, str] = Field(default_factory=dict)
    casos: list[str] = Field(default_factory=lambda: ['Sin proyecto', 'Con proyecto'])
    limite_s: float | None = Field(None, ge=10, le=86400)


class VnrDownloadIn(BaseModel):
    publication_id: str


class SourceScopeIn(BaseModel):
    company: str | None = None
    period: str | None = None


class SelectionIn(BaseModel):
    feeders: list[str] = Field(default_factory=list)
    all: bool = False
    # Unir la selección en UN solo DGS (red unida), con este nombre.
    unir: bool = False
    nombre: str = ''


class FeedersIn(BaseModel):
    feeders: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------


def create_app(
    data_root: Path | None = None, *, host: str | None = None, vnr_settings=None,
) -> FastAPI:
    """La API web, la única (spec 001, RF-11).

    ``host`` es la interfaz donde escucha el servidor; sin él se lee ``IGEA_WEB_HOST``,
    que pone el lanzador, y si tampoco está, se trata como red (RF-15).
    ``vnr_settings`` configura las rutas de VNR.
    """
    if host is None:
        host = os.environ.get('IGEA_WEB_HOST') or None
    store = WorkspaceStore(data_root)

    def emit(workspace_id: str, kind: str, data: dict) -> None:
        ws = store.get(workspace_id)
        if ws is not None:
            ws.events.append(kind, data)

    jobs = JobManager(emit)
    from .runtime import huella_del_codigo

    huella = huella_del_codigo(frontend_dist())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await asyncio.to_thread(jobs.shutdown)

    app = FastAPI(title='Conversor IGEA/CYMDIST → DGS', version=__version__, lifespan=lifespan)
    app.state.store = store
    app.state.jobs = jobs

    from vnr_etl.web.app import create_router

    # Las rutas de VNR-GIS son parte de esta API y usan su cola de trabajos.
    app.include_router(create_router(store.root, jobs, vnr_settings))

    # Solo el servidor de desarrollo de Vite. En producción el front se sirve desde
    # este mismo origen y CORS no interviene.
    dev_origins = os.environ.get('IGEA_WEB_DEV_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173')
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in dev_origins.split(',') if o.strip()],
        allow_methods=['*'], allow_headers=['*'],
    )

    @app.exception_handler(UserError)
    async def _user_error(_request: Request, exc: UserError):
        return JSONResponse(status_code=400, content={'detail': str(exc)})

    def ws_or_404(wid: str) -> Workspace:
        ws = store.get(wid)
        if ws is None:
            raise HTTPException(404, 'Espacio de trabajo no encontrado.')
        return ws

    # Comprobar el carril y encolar van juntos: las rutas corren en hilos distintos, y dos
    # clics seguidos (o dos pestañas) pasaban los dos la comprobación y encolaban dos veces.
    encolando = threading.Lock()

    def submit(ws: Workspace, kind: str, title: str, fn, *, lane: str = 'engine') -> dict:
        with encolando:
            busy = [j for j in jobs.active(ws.id) if j.lane == lane]
            if busy:
                raise HTTPException(409, f'Ya hay un trabajo en curso en este espacio: «{busy[0].title}». '
                                         'Espere a que termine o cancélelo.')
            return jobs.submit(ws.id, kind, title, fn, lane=lane).public()

    # ------------------------------------------------------------ sistema
    @app.get('/api/health')
    def health() -> dict:
        return {
            'version': __version__,
            'capabilities': services.capabilities(),
            'crs_presets': services.crs_presets(),
            'perfil_empresa': services.perfil_info(),
            'slots': SLOTS,
            'default_options': DEFAULT_OPTIONS,
            'server_paths': _server_paths_allowed(host),
            'parallel': services.parallel_info(),
            'source_modes': ['txt', 'mdb', 'vnr'],
            # Para el lanzador (spec 001, RF-28 a RF-30): si este servidor es el mismo
            # código, si se puede cerrar sin perder trabajo y qué proceso es.
            'servidor': {'pid': os.getpid(), 'huella': huella,
                         'trabajos_en_curso': jobs.en_curso()},
        }

    @app.post('/api/sistema/cerrar', status_code=202)
    def cerrar_servidor(request: Request) -> dict:
        """El lanzador pide cerrar este servidor para arrancar otra versión (RF-29, RF-33)."""
        cliente = request.client.host if request.client else ''
        if request.headers.get(CABECERA_LANZADOR) != '1' or cliente not in LOOPBACK_HOSTS:
            raise HTTPException(403, 'Solo el lanzador de esta máquina puede cerrar el servidor.')
        en_curso = jobs.en_curso()
        if en_curso:
            raise HTTPException(409, f'Hay {en_curso} trabajo(s) en curso: no se cierra.')
        if not _cierre:
            raise HTTPException(503, 'Este servidor no admite el cierre por petición.')
        # Tras responder: si se cierra antes, el lanzador ve la conexión cortada.
        threading.Timer(0.2, _cierre[0]).start()
        return {'cerrando': True}

    @app.get('/api/powerfactory')
    def powerfactory(refresh: bool = False) -> dict:
        return services.powerfactory_status(refresh=refresh)

    # ------------------------------------------------------------ catálogo VNR oficial
    def _vnr_catalog_dir() -> Path:
        return store.root / '_vnr_catalog'

    @app.get('/api/vnr/publications')
    def vnr_publications(refresh: bool = False) -> dict:
        from vnr_etl.discovery.catalog import PublicationCatalog
        from vnr_etl.discovery.official import (
            is_allowed_official_url, is_vnr_data_package, publication_evidence_sha256,
            refresh_official_catalog,
        )

        report = None
        if refresh:
            catalog, report = refresh_official_catalog(_vnr_catalog_dir())
        else:
            catalog = PublicationCatalog.load(_vnr_catalog_dir())
        rows = []
        for publication in catalog.publications():
            convertible = (
                is_vnr_data_package(publication)
                and is_allowed_official_url(publication.download_url)
            )
            rows.append({
                **publication.as_dict(),
                'convertible': convertible,
                'status': (
                    'OFFICIAL_DATA_PACKAGE' if convertible
                    else 'REGULATORY_DOCUMENT_ONLY'
                ),
                'evidence_sha256': publication_evidence_sha256(publication),
            })
        available = any(row['convertible'] for row in rows)
        return {
            'status': (
                'OFFICIAL_PACKAGE_AVAILABLE' if available
                else 'BLOCKED_MISSING_OFFICIAL_PACKAGE'
            ),
            'publications': rows,
            'refresh': report,
        }

    # ------------------------------------------------------------ espacios
    @app.get('/api/workspaces')
    def list_workspaces() -> list[dict]:
        return store.list()

    @app.post('/api/workspaces', status_code=201)
    def create_workspace() -> dict:
        return store.create().public()

    @app.get('/api/workspaces/{wid}')
    def get_workspace(wid: str) -> dict:
        ws = ws_or_404(wid)
        return {**ws.public(), 'jobs': [j.public() for j in jobs.list(wid)[-20:]]}

    @app.get('/api/workspaces/{wid}/runs')
    def source_runs(wid: str) -> list[dict]:
        """Historial inmutable de fuentes, limitado al espacio solicitado."""
        from .source_runs import load_source_run, valid_run_id

        ws = ws_or_404(wid)
        root = ws.root / 'runs'
        rows: list[dict] = []
        for folder in root.iterdir() if root.is_dir() else ():
            if not folder.is_dir() or not valid_run_id(folder.name):
                continue
            try:
                snapshot = load_source_run(ws, folder.name)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            rows.append({
                'run_id': snapshot.run_id,
                'mode': snapshot.mode,
                'created_at': snapshot.created_at,
                'fingerprint': snapshot.fingerprint,
                'files': len(snapshot.files),
                'active': snapshot.run_id == ws.active_run_id,
                'manifest_url': f'/api/workspaces/{wid}/runs/{snapshot.run_id}/manifest',
            })
        return sorted(rows, key=lambda row: (row['created_at'], row['run_id']), reverse=True)

    @app.get('/api/workspaces/{wid}/runs/{run_id}/manifest')
    def source_manifest(wid: str, run_id: str) -> dict:
        """Manifiesto público sin revelar rutas originales del servidor."""
        from .source_runs import load_source_run, valid_run_id

        ws = ws_or_404(wid)
        if not valid_run_id(run_id):
            raise HTTPException(404, 'Ejecución no encontrada.')
        try:
            snapshot = load_source_run(ws, run_id)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(404, 'Ejecución no encontrada.') from exc
        return {
            'version': 1,
            'run_id': snapshot.run_id,
            'mode': snapshot.mode,
            'created_at': snapshot.created_at,
            'fingerprint': snapshot.fingerprint,
            'files': [
                {
                    'slot': item.slot,
                    'name': item.name,
                    'size': item.size,
                    'sha256': item.sha256,
                    'origin': item.origin,
                }
                for item in sorted(snapshot.files.values(), key=lambda item: item.slot)
            ],
        }

    @app.delete('/api/workspaces/{wid}', status_code=204)
    def delete_workspace(wid: str) -> None:
        ws = ws_or_404(wid)
        if jobs.active(ws.id):
            raise HTTPException(409, 'Hay trabajos en curso en este espacio.')
        store.delete(wid)

    @app.put('/api/workspaces/{wid}/options')
    def put_options(wid: str, body: OptionsIn) -> dict:
        ws = ws_or_404(wid)
        changes = {
            key: value
            for key, value in body.model_dump(exclude_unset=True).items()
            if value is not None or key == 'hoja'
        }
        for key in ('source_crs', 'target_crs'):
            if key in changes:
                changes[key] = changes[key].strip()
        warning = ''
        crs = changes.get('source_crs')
        if crs and services.capabilities()['geography']:
            from ..geography import assert_metre_source_crs

            try:
                assert_metre_source_crs(crs)
            except ValueError as exc:
                # Se guarda igual —el operador puede estar escribiendo—, pero se avisa
                # ya; convertir con él se rechaza en check_convert_options.
                warning = str(exc)
        with ws.lock:
            if 'input_mode' in changes and changes['input_mode'] != ws.options['input_mode']:
                ws.invalidate()
            ws.options.update(changes)
            for key in BOOL_OPTIONS:
                ws.options[key] = bool(ws.options[key])
            ws.save()
        return {**ws.public(), 'warning': warning}

    @app.get('/api/workspaces/{wid}/source-scope')
    def get_source_scope(wid: str) -> dict:
        from .source_scope import inspect_package_scope

        ws = ws_or_404(wid)
        package = ws.input_path('vnr_package')
        if not package:
            raise HTTPException(409, 'Asigne primero un paquete VNR-GIS.')
        try:
            return inspect_package_scope(
                package,
                selected_company=ws.options.get('source_company'),
                selected_period=ws.options.get('source_period'),
            ).as_dict()
        except ValueError as exc:
            raise UserError(str(exc)) from exc

    @app.put('/api/workspaces/{wid}/source-scope')
    def put_source_scope(wid: str, body: SourceScopeIn) -> dict:
        from .source_scope import inspect_package_scope

        ws = ws_or_404(wid)
        package = ws.input_path('vnr_package')
        if not package:
            raise HTTPException(409, 'Asigne primero un paquete VNR-GIS.')
        try:
            scope = inspect_package_scope(
                package, selected_company=body.company, selected_period=body.period,
            )
        except ValueError as exc:
            raise UserError(str(exc)) from exc
        if scope.ambiguous:
            raise UserError('SOURCE_SCOPE_SELECTION_REQUIRED')
        with ws.lock:
            ws.invalidate()
            ws.options['source_company'] = scope.selected_company
            ws.options['source_period'] = scope.selected_period
            ws.save()
        return scope.as_dict()

    # ------------------------------------------------------------ entradas
    def _check_slot(slot: str) -> dict:
        spec = SLOTS.get(slot)
        if spec is None:
            raise HTTPException(404, f'Casilla desconocida: {slot}')
        return spec

    def _assign(ws: Workspace, slot: str, path: Path, origin: str) -> dict:
        spec = SLOTS[slot]
        if slot == 'vnr_package':
            from vnr_etl.discovery.official import (
                OfficialDiscoveryError, validate_vnr_package_file,
            )

            try:
                validate_vnr_package_file(path)
            except OfficialDiscoveryError as exc:
                raise UserError(str(exc)) from exc
        warning = comprobar_ranura(path, spec['tipo']) if spec['tipo'] else ''
        meta = ws.set_input(slot, path, origin=origin, warning=warning)
        group = str(spec.get('grupo') or '')
        if group in ('txt', 'mdb', 'vnr'):
            with ws.lock:
                ws.options['input_mode'] = group
                ws.save()
        ws.events.append('log', {'text': f'Archivo asignado a {slot}: {path.name}'
                                 + (f'  (AVISO: {warning.splitlines()[0]})' if warning else '')})
        return {'slot': slot, **meta, 'workspace': ws.public()}

    def _save_upload(target: Path, upload: UploadFile) -> None:
        tmp = target.with_suffix(target.suffix + '.part')
        with tmp.open('wb') as fh:
            shutil.copyfileobj(upload.file, fh, length=1024 * 1024)
        tmp.replace(target)

    @app.post('/api/workspaces/{wid}/inputs/{slot}')
    def upload_input(wid: str, slot: str, file: UploadFile = File(...)) -> dict:
        ws = ws_or_404(wid)
        _check_slot(slot)
        target = ws.upload_target(slot, file.filename or slot)
        _save_upload(target, file)
        try:
            return _assign(ws, slot, target, 'upload')
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @app.post('/api/workspaces/{wid}/inputs/{slot}/path')
    def server_path_input(wid: str, slot: str, body: ServerPathIn) -> dict:
        ws = ws_or_404(wid)
        _check_slot(slot)
        if not _server_paths_allowed(host):
            raise HTTPException(403, 'Este servidor no admite rutas locales: suba el fichero.')
        path = Path(body.path.strip().strip('"'))
        if not path.is_file():
            raise HTTPException(400, f'No existe el fichero: {path}')
        return _assign(ws, slot, path, 'server')

    @app.delete('/api/workspaces/{wid}/inputs/{slot}')
    def delete_input(wid: str, slot: str) -> dict:
        ws = ws_or_404(wid)
        _check_slot(slot)
        ws.clear_input(slot)
        return ws.public()

    @app.post('/api/workspaces/{wid}/vnr/download')
    def download_vnr(wid: str, body: VnrDownloadIn) -> dict:
        from vnr_etl.discovery.catalog import PublicationCatalog
        from vnr_etl.discovery.download import DownloadManager
        from vnr_etl.discovery.official import (
            DEFAULT_ALLOWED_HOSTS, is_allowed_official_url, is_vnr_data_package,
            validate_vnr_package_file,
        )

        ws = ws_or_404(wid)
        catalog = PublicationCatalog.load(_vnr_catalog_dir())
        publication = catalog.get(body.publication_id)
        if publication is None:
            raise UserError(f'Publicación VNR desconocida: {body.publication_id}.')
        if not is_vnr_data_package(publication):
            raise UserError(
                f'{publication.file_name or publication.title} no es un paquete de datos VNR-GIS.'
            )
        if not is_allowed_official_url(publication.download_url):
            raise UserError('La descarga no pertenece a un host oficial permitido.')
        target = ws.upload_target('vnr_package', publication.file_name or 'vnr_package.zip')
        manager = DownloadManager(
            ws.inputs_dir / '_vnr_downloads',
            max_file_size_bytes=4096 * 1024 * 1024,
            verify_archive=True,
            allowed_hosts=DEFAULT_ALLOWED_HOSTS,
        )
        manifest = manager.download(
            publication.download_url,
            target,
            publication_id=publication.publication_id,
            company=publication.company,
            period=publication.period_label,
        )
        validate_vnr_package_file(target)
        assigned = _assign(ws, 'vnr_package', target, 'upload')
        return {**assigned, 'manifest': manifest.as_dict()}

    @app.post('/api/workspaces/{wid}/inputs-auto')
    def auto_inputs(wid: str, files: list[UploadFile] = File(...)) -> dict:
        """Varios TXT sueltos: cada uno va a su casilla **por su contenido**.

        Los nombres de la distribuidora no siguen convención; lo que distingue un RED de
        un CARGA son las tablas que declara dentro. Si dos ficheros son del mismo tipo,
        el segundo queda sin asignar: mejor una casilla vacía que una equivocada.
        """
        ws = ws_or_404(wid)
        staging = ws.inputs_dir / '_auto'
        staging.mkdir(parents=True, exist_ok=True)
        slot_of = {'red': 'red', 'carga': 'loads', 'equipos': 'equipment'}
        assigned, unassigned, taken = [], [], set()
        for upload in files:
            tmp = staging / Path(upload.filename or 'fichero.txt').name
            _save_upload(tmp, upload)
            ident = identificar(tmp)
            slot = slot_of.get(ident.tipo)
            if slot is None or slot in taken:
                unassigned.append({'name': tmp.name, 'reason': (
                    'tipo repetido' if slot else 'no declara tablas conocidas de IGEA/CYMDIST')})
                tmp.unlink(missing_ok=True)
                continue
            taken.add(slot)
            target = ws.upload_target(slot, tmp.name)
            tmp.replace(target)
            _assign(ws, slot, target, 'upload')
            assigned.append({'slot': slot, 'name': target.name})
        shutil.rmtree(staging, ignore_errors=True)
        if assigned:
            with ws.lock:
                ws.options['input_mode'] = 'txt'
                ws.save()
        return {'assigned': assigned, 'unassigned': unassigned, 'workspace': ws.public()}

    # ------------------------------------------------------------ carga y tabla
    @app.post('/api/workspaces/{wid}/load', status_code=202)
    def load(wid: str) -> dict:
        ws = ws_or_404(wid)
        services.check_ready(ws)
        return submit(ws, 'load', 'Cargar / listar alimentadores',
                      lambda ctx: services.load_dataset(ws, ctx))

    @app.get('/api/workspaces/{wid}/feeders')
    def feeders(wid: str) -> dict:
        ws = ws_or_404(wid)
        return {'loaded': ws.dataset is not None, 'feeders': services.feeder_rows(ws)}

    def _check_selection(ws: Workspace, body: SelectionIn) -> list[str]:
        # Lo que falla por la petición falla aquí, con 400, y no como trabajo fallido.
        from .reconstruction_service import resolve_selection

        services.require_loaded(ws)
        services.require_active_source_run(ws)
        names, _ = resolve_selection(ws, body.feeders, all_feeders=body.all)
        return names

    @app.post('/api/workspaces/{wid}/diagnose', status_code=202)
    def diagnose(wid: str, body: SelectionIn) -> dict:
        from .reconstruction_service import diagnose_selection

        ws = ws_or_404(wid)
        names = _check_selection(ws, body)
        return submit(ws, 'diagnose', f'Diagnosticar {len(names)} alimentador(es)',
                      lambda ctx: diagnose_selection(
                          ws, body.feeders, all_feeders=body.all, ctx=ctx))

    @app.post('/api/workspaces/{wid}/reconstruct', status_code=202)
    def reconstruct(wid: str, body: SelectionIn) -> dict:
        from .reconstruction_service import reconstruct_selection

        ws = ws_or_404(wid)
        names = _check_selection(ws, body)
        return submit(ws, 'reconstruct', f'Reconstruir {len(names)} alimentador(es)',
                      lambda ctx: reconstruct_selection(
                          ws, body.feeders, all_feeders=body.all, ctx=ctx))

    @app.post('/api/workspaces/{wid}/convert', status_code=202)
    def convert(wid: str, body: SelectionIn) -> dict:
        ws = ws_or_404(wid)
        services.check_ready(ws)
        services.require_loaded(ws)
        if not body.all and not body.feeders:
            raise UserError('Seleccione al menos un alimentador, o convierta todos.')
        services.check_convert_options(ws)
        if body.unir:
            feeders = services.group_selection(ws, body.feeders, body.all)
            nombre = services.group_name(body.nombre, feeders)
            requested = feeders if body.all else body.feeders
            return submit(ws, 'convert_group', f'Unir {len(feeders)} alimentadores en {nombre}.dgs',
                          lambda ctx: services.convert_group(
                              ws, ctx, feeders, nombre, requested_feeders=requested))
        n = len(ws.inventory['feeders']) if body.all and ws.inventory else len(body.feeders)
        title = f'Convertir {"TODOS" if body.all else ""} {n} alimentador(es) a DGS'.replace('  ', ' ')
        return submit(ws, 'convert', title,
                      lambda ctx: services.convert(ws, ctx, body.feeders, body.all))

    # ------------------------------------------------------------ trabajos y registro
    @app.get('/api/jobs/{job_id}')
    def get_job(job_id: str) -> dict:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, 'Trabajo no encontrado.')
        return job.public()

    @app.post('/api/jobs/{job_id}/cancel')
    def cancel_job(job_id: str) -> dict:
        job = jobs.cancel(job_id)
        if job is None:
            raise HTTPException(404, 'Trabajo no encontrado.')
        return job.public()

    @app.get('/api/workspaces/{wid}/events')
    def events(wid: str, since: int = 0) -> list[dict]:
        return ws_or_404(wid).events.since(since)

    @app.websocket('/api/workspaces/{wid}/ws')
    async def events_ws(websocket: WebSocket, wid: str, since: int = 0) -> None:
        ws = store.get(wid)
        if ws is None:
            await websocket.close(code=4404)
            return
        await websocket.accept()
        seq = since
        try:
            while True:
                batch = await asyncio.to_thread(ws.events.wait, seq, 15.0)
                if batch:
                    await websocket.send_json(batch)
                    seq = batch[-1]['seq']
                else:
                    await websocket.send_json([])  # latido: detecta conexiones muertas
        except (WebSocketDisconnect, RuntimeError):
            return

    # ------------------------------------------------------------ salida
    def _safe_out(ws: Workspace, rel: str) -> Path:
        target = (ws.out_dir / rel).resolve()
        root = ws.out_dir.resolve()
        if target != root and root not in target.parents:
            raise HTTPException(400, 'Ruta fuera de la carpeta de salida.')
        return target

    @app.get('/api/workspaces/{wid}/outputs')
    def outputs(wid: str) -> list[dict]:
        ws = ws_or_404(wid)
        root = ws.out_dir
        if not root.is_dir():
            return []
        rows = []
        for path in sorted(root.rglob('*')):
            if not path.is_file() or any(p.startswith('.igea-stage-') for p in path.parts):
                continue
            st = path.stat()
            rows.append({'path': path.relative_to(root).as_posix(), 'size': st.st_size,
                         'modified': st.st_mtime})
        return rows

    @app.get('/api/workspaces/{wid}/files/{rel:path}')
    def get_file(wid: str, rel: str, download: bool = False) -> FileResponse:
        ws = ws_or_404(wid)
        path = _safe_out(ws, rel)
        if not path.is_file():
            raise HTTPException(404, 'Fichero no encontrado.')
        media = 'text/html' if path.suffix.lower() == '.html' and not download else None
        return FileResponse(path, media_type=media,
                            filename=path.name if download or media is None else None)

    @app.get('/api/workspaces/{wid}/outputs.zip')
    def outputs_zip(wid: str, background: BackgroundTasks,
                    feeder: list[str] = Query(default=[])) -> FileResponse:
        ws = ws_or_404(wid)
        root = ws.out_dir
        fd, tmp_name = tempfile.mkstemp(suffix='.zip')
        os.close(fd)
        wanted = tuple(feeder)
        count = 0
        with zipfile.ZipFile(tmp_name, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path in root.rglob('*') if root.is_dir() else ():
                if not path.is_file() or any(p.startswith('.igea-stage-') for p in path.parts):
                    continue
                rel = path.relative_to(root).as_posix()
                if wanted and not any(rel == f'{f}.dgs' or rel.startswith(f'{f}_')
                                      or rel.startswith(f'{f}/') for f in wanted):
                    continue
                zf.write(path, rel)
                count += 1
        if not count:
            os.unlink(tmp_name)
            raise HTTPException(404, 'No hay ficheros de salida que descargar.')
        background.add_task(os.unlink, tmp_name)
        name = f'igea_dgs_{"_".join(wanted[:3]) if wanted else "salida"}.zip'
        return FileResponse(tmp_name, filename=name, media_type='application/zip')

    # ------------------------------------------------------------ PowerFactory
    @app.post('/api/workspaces/{wid}/powerfactory/flow', status_code=202)
    def pf_flow(wid: str, body: FeedersIn) -> dict:
        ws = ws_or_404(wid)
        targets = services.powerfactory_targets(ws, body.feeders)
        services.check_powerfactory_flow(ws, targets)
        return submit(ws, 'powerfactory', f'DigSILENT: import + flujo ({len(targets)})',
                      lambda ctx: services.powerfactory_flow(ws, ctx, targets),
                      lane='powerfactory')

    # ------------------------------------------------------------ cargas en DIgSILENT
    # Spec 004: un módulo aparte de la conversión. No pide entradas cargadas: la web
    # valida los libros y el guion decide en el proyecto de DIgSILENT (RF-1).
    def _upload_tmp(ws: Workspace, upload: UploadFile, default: str) -> Path:
        folder = ws.root / 'subidas'
        folder.mkdir(parents=True, exist_ok=True)
        name = Path(upload.filename or default).name
        suffix = Path(name).suffix.lower() or Path(default).suffix
        fd, tmp = tempfile.mkstemp(suffix=suffix, dir=folder)
        os.close(fd)
        _save_upload(Path(tmp), upload)
        return Path(tmp)

    def _json_form(texto: str | None, campo: str) -> dict | None:
        try:
            valor = json.loads(texto) if texto else None
        except ValueError as exc:
            raise HTTPException(422, f'{campo} no es JSON válido: {exc}') from exc
        if valor is not None and not isinstance(valor, dict):
            raise HTTPException(422, f'{campo} debe ser un objeto JSON.')
        return valor

    @app.get('/api/workspaces/{wid}/cargas/plantilla/{tipo}')
    def cargas_plantilla(wid: str, tipo: Literal['demandas', 'nuevas'],
                         format: Literal['xlsx', 'csv'] = 'xlsx') -> FileResponse:
        path = services.cargas_plantilla(ws_or_404(wid), tipo, format)
        return FileResponse(path, filename=path.name)

    @app.post('/api/workspaces/{wid}/powerfactory/projects', status_code=202)
    def pf_projects(wid: str) -> dict:
        ws = ws_or_404(wid)
        return submit(ws, 'pf_projects', 'Leer proyectos de DIgSILENT',
                      lambda ctx: services.pf_projects(ws, ctx), lane='powerfactory')

    # Spec 018, RF-13: la última lista leída, sin abrir DIgSILENT (los trabajos no sobreviven
    # a un reinicio de la web).
    @app.get('/api/workspaces/{wid}/powerfactory/projects')
    def pf_projects_guardados(wid: str) -> dict:
        return services.pf_proyectos_guardados(ws_or_404(wid))

    # Spec 007, RF-40: el último ajuste aplicado guardado en disco, para la base.
    @app.get('/api/workspaces/{wid}/demanda/ajuste/ultimo')
    def ajuste_ultimo(wid: str, project: str) -> dict:
        return {'ajuste': services.ajuste_aplicado_en_disco(ws_or_404(wid), project)}

    # Spec 018, RF-10: usar la ejecución fuente con la que se aceptó el proyecto. Carril del
    # motor: cambia la ejecución activa, y una conversión en marcha escribe en ella.
    @app.post('/api/workspaces/{wid}/powerfactory/adoptar-fuente', status_code=202)
    def pf_adoptar_fuente(wid: str, body: VerificarIn) -> dict:
        ws = ws_or_404(wid)
        if not body.project.strip():
            raise HTTPException(422, 'Elija el proyecto de DIgSILENT.')
        return submit(ws, 'pf_adoptar_fuente', f'Usar la fuente de {body.project.strip()}',
                      lambda ctx: services.adoptar_fuente_del_vinculo(ws, body.project),
                      lane='engine')

    # Spec 015, RF-1 a RF-14: verificar el «Caso base» del proyecto, repetible tras corregir.
    @app.post('/api/workspaces/{wid}/powerfactory/caso-base', status_code=202)
    def pf_verificar_base(wid: str, body: VerificarIn) -> dict:
        ws = ws_or_404(wid)
        if not body.project.strip():
            raise HTTPException(422, 'Elija el proyecto de DIgSILENT.')
        return submit(ws, 'pf_verificar_base', f'Verificar el Caso base · {body.project.strip()}',
                      lambda ctx: services.pf_verificar_base(ws, ctx, body.project, body.feeders),
                      lane='powerfactory')

    # Spec 008, RF-18: el flujo de carga con lo activo, antes de integrar cargas.
    @app.post('/api/workspaces/{wid}/powerfactory/verificar', status_code=202)
    def pf_verificar(wid: str, body: VerificarIn) -> dict:
        ws = ws_or_404(wid)
        if not body.project.strip():
            raise HTTPException(422, 'Elija el proyecto de DIgSILENT.')
        return submit(ws, 'pf_verificar', f'Verificar la convergencia · {body.project.strip()}',
                      lambda ctx: services.pf_verificar(ws, ctx, body.project, body.feeders),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/lote/plan')
    def lote_plan(
        wid: str,
        project: str = Form(...),
        feeders: list[str] = Form(...),
        update_file: UploadFile | None = File(None),
        create_file: UploadFile | None = File(None),
        nueva: str | None = Form(None),
        economia: str | None = Form(None),
        ajuste_job_id: str | None = Form(None),
        # 016:RF-20, RF-73: a menos de esto de una barra, la carga se engancha en ella.
        minima_m: float | None = Form(None, ge=0, le=100_000),
    ) -> dict:
        ws = ws_or_404(wid)
        eco = _json_form(economia, 'economia')
        una = _json_form(nueva, 'nueva')
        ajuste = _ajuste_aplicado(wid, ajuste_job_id)
        tmps: list[Path] = []
        try:
            upd = cre = None
            if update_file:
                upd = _upload_tmp(ws, update_file, 'demandas.xlsx')
                tmps.append(upd)
            if create_file:
                cre = _upload_tmp(ws, create_file, 'cargas_nuevas.xlsx')
                tmps.append(cre)
            return services.cargas_plan(ws, project, feeders, upd, cre, una, eco, ajuste,
                                        minima_m=minima_m)
        finally:
            for p in tmps:
                p.unlink(missing_ok=True)

    def _cargas_job(wid: str, token: str, simular: bool) -> dict:
        ws = ws_or_404(wid)
        if token not in ws.cargas_planes:
            raise HTTPException(404, 'El plan ya no existe: vuelva a prepararlo.')
        plan = services.cargas_plan_de(ws, token)
        verbo = 'Simular' if simular else 'Aplicar'
        title = f"{verbo} cargas · {plan['project']} ({len(plan['feeders'])} alim.)"
        return submit(ws, 'cargas_simular' if simular else 'cargas_aplicar', title,
                      lambda ctx: services.cargas_ejecutar(ws, ctx, token, simular=simular),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/lote/{token}/simular', status_code=202)
    def lote_simular(wid: str, token: str) -> dict:
        return _cargas_job(wid, token, True)

    @app.post('/api/workspaces/{wid}/lote/{token}/apply', status_code=202)
    def lote_apply(wid: str, token: str) -> dict:
        return _cargas_job(wid, token, False)

    # ------------------------------------------------------------ demanda medida
    # Spec 004, RF-22 a RF-39: misma pestaña que las cargas (RF-40), sin entradas cargadas.
    @app.get('/api/workspaces/{wid}/demanda/medidores')
    def demanda_medidores(wid: str, alimentador: str = Query(...)) -> dict:
        return services.demanda_medidores(ws_or_404(wid), alimentador)

    @app.get('/api/workspaces/{wid}/demanda/alimentadores')
    def demanda_alimentadores(wid: str) -> dict:
        return services.demanda_alimentadores(ws_or_404(wid))

    @app.post('/api/workspaces/{wid}/demanda/cabecera/buscar', status_code=202)
    def demanda_cabecera(wid: str, body: DemandaMedidoresIn) -> dict:
        ws = ws_or_404(wid)
        pares = [(m.alimentador.strip(), m.medidor.strip()) for m in body.medidores if m.medidor.strip()]
        if not pares:
            raise HTTPException(422, 'Indique al menos un medidor.')
        return submit(ws, 'demanda_cabecera', f'Máxima de cabecera ({len(pares)} medidor(es))',
                      lambda ctx: services.demanda_cabecera(ws, ctx, pares))

    @app.get('/api/workspaces/{wid}/demanda/cabecera/{job_id}/curva')
    def demanda_curva(wid: str, job_id: str, medidor: str = Query(...),
                      desde: datetime | None = None, hasta: datetime | None = None) -> dict:
        """Spec 006, RF-31 a RF-39: curva del registro del medidor, entera o por tramo."""
        if desde is not None and hasta is not None and desde > hasta:
            raise HTTPException(422, 'El inicio del tramo es posterior a su fin.')
        try:
            return services.demanda_curva(ws_or_404(wid), job_id, medidor, desde, hasta)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post('/api/workspaces/{wid}/demanda/clientes/cruzar')
    def demanda_clientes(wid: str, body: DemandaClientesIn | None = None) -> dict:
        return services.demanda_clientes(ws_or_404(wid), body.alimentadores if body else None,
                                         periodo=body.periodo if body else None)

    # Spec 006: ajuste de las demandas del alimentador a la máxima de cabecera.
    @app.post('/api/workspaces/{wid}/demanda/ajuste/plan')
    def ajuste_plan(wid: str, body: AjusteIn) -> dict:
        ws = ws_or_404(wid)
        job = jobs.get(body.job_id)
        if job is None or job.workspace_id != wid or job.kind != 'demanda_cabecera':
            raise HTTPException(404, 'No se encuentra la máxima buscada: vuelva a buscarla.')
        if not isinstance(job.result, dict):
            raise HTTPException(409, 'La máxima de cabecera todavía no ha terminado.')
        return services.ajuste_plan(ws, body.project, job.result.get('resultados') or [],
                                    body.medidor, body.tolerancia, body.medidores,
                                    body.desconectados)

    def _ajuste_job(wid: str, token: str, simular: bool) -> dict:
        ws = ws_or_404(wid)
        plan = ws.cargas_planes.get(token)
        if plan is None or plan.get('kind') != 'ajuste_cabecera':
            raise HTTPException(404, 'El plan del ajuste ya no existe: vuelva a prepararlo.')
        verbo = 'Simular' if simular else 'Ajustar'
        quien = plan['feeders'][0] if len(plan['feeders']) == 1 else f"{len(plan['feeders'])} alim."
        return submit(ws, 'ajuste_simular' if simular else 'ajuste_aplicar',
                      f"{verbo} {quien} a la máxima · {plan['project']}",
                      lambda ctx: services.ajuste_ejecutar(ws, ctx, token, simular=simular),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/demanda/ajuste/{token}/simular', status_code=202)
    def ajuste_simular(wid: str, token: str) -> dict:
        return _ajuste_job(wid, token, True)

    @app.post('/api/workspaces/{wid}/demanda/ajuste/{token}/aplicar', status_code=202)
    def ajuste_aplicar(wid: str, token: str) -> dict:
        return _ajuste_job(wid, token, False)

    # Spec 020: transformadores nuevos de las SED fijas sobrecargadas y recalibración.
    @app.post('/api/workspaces/{wid}/demanda/ajuste/{token}/transformadores', status_code=202)
    def ajuste_transformadores(wid: str, token: str, body: TransformadoresIn) -> dict:
        ws = ws_or_404(wid)
        plan = ws.cargas_planes.get(token)
        if plan is None or plan.get('kind') != 'ajuste_cabecera':
            raise HTTPException(404, 'El plan del ajuste ya no existe: vuelva a prepararlo.')
        # 020:RF-13, RF-14: se valida antes de encolar, para decirlo en el acto.
        cambios = services.ajuste_transformadores_pedido(ws, token, body.feeder, body.sed)
        return submit(ws, 'ajuste_transformadores',
                      f"Transformadores nuevos y calibración de {body.feeder} · {plan['project']}",
                      lambda ctx: services.ajuste_transformadores(ws, ctx, token, body.feeder,
                                                                  cambios),
                      lane='powerfactory')

    def _ajuste_aplicado(wid: str, job_id: str | None) -> dict | None:
        """El resultado del ajuste de la base (spec 007, RF-1; spec 011, RF-12).

        Solo uno de este espacio, terminado y aplicado: una simulación no deja variación.
        """
        if not job_id:
            return None
        if job_id.startswith('disco:'):
            # 007:RF-40: el ajuste de una sesión anterior, rehecho con sus informes.
            guardado = services.ajuste_aplicado_en_disco(
                ws_or_404(wid), None, job_id.removeprefix('disco:'))
            if guardado is None:
                raise HTTPException(404, 'No se encuentra el ajuste de la base: quite la base o vuelva a ajustar.')
            return guardado
        job = jobs.get(job_id)
        if job is None or job.workspace_id != wid:
            raise HTTPException(404, 'No se encuentra el ajuste de la base: quite la base o vuelva a ajustar.')
        if job.kind not in ('ajuste_aplicar', 'ajuste_transformadores'):   # 020:RF-28
            raise HTTPException(400, 'La base tiene que ser un ajuste aplicado, no una simulación.')
        if not isinstance(job.result, dict):
            raise HTTPException(409, 'El ajuste de la base todavía no ha terminado.')
        return job.result

    # ------------------------------------------------------------ obras y estudios (spec 011)
    @app.get('/api/workspaces/{wid}/obras')
    def obras_listar(wid: str) -> list[dict]:
        return list(ws_or_404(wid).obras)

    @app.post('/api/workspaces/{wid}/obras', status_code=201)
    def obra_anadir(wid: str, body: dict[str, Any]) -> dict:
        return services.obra_anadir(ws_or_404(wid), body)

    @app.delete('/api/workspaces/{wid}/obras/{obra_id}', status_code=204)
    def obra_quitar(wid: str, obra_id: str) -> None:
        services.obra_quitar(ws_or_404(wid), obra_id)

    @app.post('/api/workspaces/{wid}/pf/obras/bibliotecas', status_code=202)
    def obras_bibliotecas(wid: str, body: BibliotecasIn) -> dict:
        ws = ws_or_404(wid)
        return submit(ws, 'obras_bibliotecas', f'Leer tipos de DIgSILENT · {body.project.strip()}',
                      lambda ctx: services.obras_bibliotecas(ws, ctx, body.project, body.feeders,
                                                             body.otro_proyecto, body.clases),
                      lane='powerfactory')

    @app.get('/api/workspaces/{wid}/pf/obras/bibliotecas')
    def obras_bibliotecas_leidas(wid: str) -> dict:
        return dict(ws_or_404(wid).pf_bibliotecas)

    def _obras_job(wid: str, body: ObrasIn, simular: bool) -> dict:
        ws = ws_or_404(wid)
        verbo = 'Simular' if simular else 'Aplicar'
        return submit(ws, 'obras_simular' if simular else 'obras_aplicar',
                      f'{verbo} obras · {body.project.strip()}',
                      lambda ctx: services.obras_ejecutar(ws, ctx, body.project, body.feeders,
                                                          body.ids, body.otro_proyecto,
                                                          simular=simular),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/pf/obras/simular', status_code=202)
    def obras_simular(wid: str, body: ObrasIn) -> dict:
        return _obras_job(wid, body, True)

    @app.post('/api/workspaces/{wid}/pf/obras/aplicar', status_code=202)
    def obras_aplicar(wid: str, body: ObrasIn) -> dict:
        return _obras_job(wid, body, False)

    @app.get('/api/pf/estudios')
    def estudios_catalogo() -> dict:
        return services.estudios_catalogo()

    @app.post('/api/workspaces/{wid}/pf/estudios/plan')
    def estudios_plan(wid: str, body: EstudiosIn) -> dict:
        ws = ws_or_404(wid)
        return services.estudios_plan(ws, body.project, body.feeders, body.estudios,
                                      _ajuste_aplicado(wid, body.ajuste_job_id), body.limites,
                                      body.limite_s)

    @app.post('/api/workspaces/{wid}/pf/estudios/{token}/ejecutar', status_code=202)
    def estudios_ejecutar(wid: str, token: str) -> dict:
        ws = ws_or_404(wid)
        plan = ws.cargas_planes.get(token)
        if plan is None or plan.get('kind') != 'estudios':
            raise HTTPException(404, 'El plan de los estudios ya no existe: vuelva a prepararlo.')
        return submit(ws, 'estudios', f"Estudios · {plan['project']} ({len(plan['feeders'])} alim.)",
                      lambda ctx: services.estudios_ejecutar(ws, ctx, token), lane='powerfactory')

    @app.post('/api/workspaces/{wid}/pf/guiones', status_code=202)
    def guiones_listar(wid: str, body: GuionesIn) -> dict:
        ws = ws_or_404(wid)
        return submit(ws, 'guiones_listar', f'Leer guiones · {body.project.strip()}',
                      lambda ctx: services.guiones_listar(ws, ctx, body.project), lane='powerfactory')

    @app.post('/api/workspaces/{wid}/pf/guiones/ejecutar', status_code=202)
    def guion_ejecutar(wid: str, body: GuionIn) -> dict:
        ws = ws_or_404(wid)
        return submit(ws, 'guion_ejecutar', f'Guion {body.nombre.strip()} · {body.project.strip()}',
                      lambda ctx: services.guion_ejecutar(ws, ctx, body.project, body.nombre, body.origen,
                                                          body.parametros, body.casos, body.limite_s),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/informes/estudio', status_code=202)
    def informe_estudio(wid: str, body: InformeEstudioIn) -> dict:
        """Spec 017: el informe con lo que guardaron los estudios de «Sin proyecto» y «Con proyecto»."""
        ws = ws_or_404(wid)
        formulario = body.model_dump()
        return submit(ws, 'informe_estudio', f'Informe de estudio · {body.alimentador}',
                      lambda ctx: services.informe_estudio(ws, ctx, formulario), lane='engine')

    @app.get('/api/workspaces/{wid}/informes')
    def informes_contexto(wid: str, project: str, feeder: list[str] = Query(default=[]),
                          job_id: str | None = None) -> dict:
        """Spec 017, paso 4.4: lo que la web ya guardó para cada informe, sin DIgSILENT."""
        return services.informes_contexto(ws_or_404(wid), project, feeder, job_id)

    @app.put('/api/workspaces/{wid}/informes/formulario')
    def informes_formulario(wid: str, body: InformeFormularioIn) -> dict:
        """017:RF-82: lo escrito en 4.4 queda en el servidor al recargar la página."""
        return services.informes_formulario_guardar(ws_or_404(wid), body.project, body.tipo, body.datos)

    @app.post('/api/workspaces/{wid}/informes/perdidas')
    def informes_perdidas_subir(wid: str, file: UploadFile = File(...)) -> dict:
        """017:RF-93: el libro de pérdidas de la empresa, guardado con el espacio."""
        ws = ws_or_404(wid)
        carpeta = services.informes_carpeta_perdidas(ws)
        shutil.rmtree(carpeta, ignore_errors=True)
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / safe_filename(file.filename or 'perdidas.xlsx')
        _save_upload(destino, file)
        return services.informes_perdidas_asignar(ws, destino, 'upload')

    @app.post('/api/workspaces/{wid}/informes/perdidas/path')
    def informes_perdidas_ruta(wid: str, body: ServerPathIn) -> dict:
        ws = ws_or_404(wid)
        if not _server_paths_allowed(host):
            raise HTTPException(403, 'Este servidor no admite rutas locales: suba el fichero.')
        path = Path(body.path.strip().strip('"'))
        if not path.is_file():
            raise HTTPException(400, f'No existe: {path}')
        return services.informes_perdidas_asignar(ws, path, 'server')

    @app.delete('/api/workspaces/{wid}/informes/perdidas')
    def informes_perdidas_quitar(wid: str) -> dict:
        return services.informes_perdidas_quitar(ws_or_404(wid))

    @app.post('/api/workspaces/{wid}/informes/transformador/cargas', status_code=202)
    def informes_trafo_cargas(wid: str, body: TransformadorListarIn) -> dict:
        """Spec 017, T10: cargas de barra y casos del proyecto de transmisión."""
        ws = ws_or_404(wid)
        return submit(ws, 'informe_trafo_cargas', 'Cargas del proyecto de transmisión',
                      lambda ctx: services.transformador_set_listar(ws, ctx, body.transmision),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/informes/transformador', status_code=202)
    def informes_trafo(wid: str, body: TransformadorCalcularIn) -> dict:
        """Spec 017, T10: cargabilidad del devanado de la SET sin y con proyecto."""
        ws = ws_or_404(wid)
        return submit(ws, 'informe_trafo', f'Transformador de la SET · {body.carga}',
                      lambda ctx: services.transformador_set_calcular(
                          ws, ctx, body.project, body.alimentador, body.carga, body.caso, body.transmision),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/informes/factibilidad', status_code=202)
    def informe_factibilidad(wid: str, body: InformeFactibilidadIn) -> dict:
        """Spec 017: factibilidad y punto de diseño de una carga nueva ingresada sola."""
        ws = ws_or_404(wid)
        formulario = body.model_dump(mode='json')
        # RF-96: la carga se comprueba antes de poner el trabajo en cola.
        services.carga_del_informe(ws, body.project, body.alimentador, body.sed)
        return submit(ws, 'informe_factibilidad', f'Informe de factibilidad · {body.sed}',
                      lambda ctx: services.informe_factibilidad(ws, ctx, formulario), lane='engine')

    @app.post('/api/workspaces/{wid}/pf/transferencia', status_code=202)
    def transferencia(wid: str, body: TransferenciaIn) -> dict:
        ws = ws_or_404(wid)
        if len({f.strip() for f in body.feeders if f.strip()}) != 2:
            raise HTTPException(400, 'Elija dos alimentadores distintos.')
        return submit(ws, 'transferencia', f"Transferencia · {' ↔ '.join(body.feeders)}",
                      lambda ctx: services.transferencia_ejecutar(ws, ctx, body.project, body.feeders,
                                                                  body.casos, body.limites),
                      lane='powerfactory')

    @app.post('/api/workspaces/{wid}/demanda/excel')
    def demanda_excel(wid: str, body: DemandaExcelIn) -> FileResponse:
        path = services.demanda_excel(ws_or_404(wid), body.model_dump())
        return FileResponse(path, filename=path.name)

    @app.post('/api/workspaces/{wid}/demanda/{tipo}/path')
    def demanda_ruta(wid: str, tipo: DemandaTipo, body: ServerPathIn) -> dict:
        ws = ws_or_404(wid)
        if not _server_paths_allowed(host):
            raise HTTPException(403, 'Este servidor no admite rutas locales: suba el fichero.')
        path = Path(body.path.strip().strip('"'))
        if not (path.is_file() or (tipo in {'cabecera', 'clientes'} and path.is_dir())):
            raise HTTPException(400, f'No existe: {path}')
        return services.demanda_asignar(ws, tipo, path, 'server')

    @app.post('/api/workspaces/{wid}/demanda/clientes/indexar', status_code=202)
    def demanda_clientes_indexar(wid: str) -> dict:
        ws = ws_or_404(wid)
        return submit(ws, 'demanda_clientes_index', 'Actualizar libros de clientes',
                      lambda ctx: services.demanda_clientes_indexar(ws, ctx), lane='engine')

    @app.post('/api/workspaces/{wid}/demanda/{tipo}')
    def demanda_subir(wid: str, tipo: DemandaTipo, files: list[UploadFile] = File(...)) -> dict:
        """Subida de libros. Cabecera y clientes admiten varios, guardados en una carpeta."""
        ws = ws_or_404(wid)
        if tipo not in {'cabecera', 'clientes'} and len(files) != 1:
            raise HTTPException(422, 'Suba un solo libro.')
        carpeta = services.demanda_carpeta(ws, tipo)
        if tipo != 'cabecera':
            shutil.rmtree(carpeta, ignore_errors=True)
        carpeta.mkdir(parents=True, exist_ok=True)
        destinos = []
        for f in files:
            destino = carpeta / safe_filename(f.filename or f'{tipo}.xlsx')
            _save_upload(destino, f)
            destinos.append(destino)
        fuente = carpeta if tipo == 'cabecera' or (tipo == 'clientes' and len(destinos) > 1) else destinos[0]
        return services.demanda_asignar(ws, tipo, fuente, 'upload')

    @app.delete('/api/workspaces/{wid}/demanda/{tipo}')
    def demanda_quitar(wid: str, tipo: DemandaTipo) -> dict:
        return services.demanda_quitar(ws_or_404(wid), tipo)

    # ------------------------------------------------------------ catálogo
    @app.post('/api/workspaces/{wid}/catalog/build', status_code=202)
    def catalog_build(wid: str, body: FeedersIn) -> dict:
        ws = ws_or_404(wid)
        services.require_loaded(ws)
        return submit(ws, 'catalog', 'Generar catálogo y auditar',
                      lambda ctx: services.build_catalog(ws, ctx, body.feeders))

    @app.post('/api/workspaces/{wid}/catalog/apply')
    def catalog_apply(wid: str, file: UploadFile = File(...),
                      preview_feeder: str | None = Query(default=None)) -> dict:
        ws = ws_or_404(wid)
        tmp = _upload_tmp(ws, file, 'catalogo.xlsx')
        try:
            result = services.apply_catalog(ws, tmp, preview_feeder)
        finally:
            tmp.unlink(missing_ok=True)
        ws.events.append('log', {'text': f"Catálogo corregido aplicado: {result['count']} código(s). "
                                         'Reconvierta para llevarlo al DGS.'})
        return {**result, 'workspace': ws.public()}

    @app.delete('/api/workspaces/{wid}/catalog')
    def catalog_clear(wid: str) -> dict:
        ws = ws_or_404(wid)
        services.clear_catalog(ws)
        return ws.public()

    # ------------------------------------------------------------ sistema completo
    @app.post('/api/workspaces/{wid}/system/{action}', status_code=202)
    def system(wid: str, action: Literal['grid', 'base', 'missing-data']) -> dict:
        ws = ws_or_404(wid)
        services.system_command(ws, action)  # valida entradas y guion antes de encolar
        title, lane = services.SYSTEM_ACTIONS[action]
        return submit(ws, 'system', title, lambda ctx: services.run_system(ws, ctx, action),
                      lane=lane)

    # ------------------------------------------------------------ front compilado
    dist = frontend_dist()
    if (dist / 'index.html').is_file():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

        @app.get('/{full_path:path}', include_in_schema=False)
        def spa(full_path: str) -> Any:
            if full_path.startswith('api/'):
                raise HTTPException(404)
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / 'index.html')

    return app
