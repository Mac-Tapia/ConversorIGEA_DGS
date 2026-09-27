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
import os
import shutil
import tempfile
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import (
    BackgroundTasks, FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket,
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
    BOOL_OPTIONS, DEFAULT_OPTIONS, MAX_WORKERS, SLOTS, Workspace, WorkspaceStore,
)

# Presets de la interfaz. Solo CRS proyectados en metros: uno en
# grados (EPSG:4326) falsea las longitudes ~1e5 veces sin que nada lo detecte (C-01).
CRS_PRESETS = (
    {'code': 'EPSG:32718', 'label': 'UTM 18S (Ica / costa Perú)'},
    {'code': 'EPSG:32717', 'label': 'UTM 17S'},
    {'code': 'EPSG:32719', 'label': 'UTM 19S'},
    {'code': 'EPSG:32716', 'label': 'UTM 16S'},
    {'code': 'EPSG:32618', 'label': 'UTM 18N'},
    {'code': 'EPSG:31983', 'label': 'SIRGAS 2000 / UTM 23S'},
    {'code': 'EPSG:5343', 'label': 'POSGAR 2007 / Argentina 3'},
)


def _server_paths_allowed() -> bool:
    """Si se puede indicar una ruta del disco del servidor en lugar de subir el fichero.

    Útil en local —la base .mdb pesa cientos de MB y ya está en el disco—, peligroso
    si el servidor se expone en red: cualquiera leería cualquier fichero. Por eso el
    lanzador lo activa solo cuando escucha en 127.0.0.1.
    """
    return os.environ.get('IGEA_WEB_SERVER_PATHS', '1').strip() not in ('0', 'false', 'no', '')


def frontend_dist() -> Path:
    env = os.environ.get('IGEA_WEB_FRONTEND', '').strip()
    return Path(env) if env else project_root() / 'frontend' / 'dist'


# ---------------------------------------------------------------------------
# Modelos de petición
# ---------------------------------------------------------------------------


class OptionsIn(BaseModel):
    input_mode: Literal['txt', 'mdb'] | None = None
    source_crs: str | None = None
    target_crs: str | None = None
    include_geography: bool | None = None
    strict: bool | None = None
    write_preview: bool | None = None
    export_xlsx: bool | None = None
    export_tsv: bool | None = None
    workers: int | None = Field(None, ge=0, le=MAX_WORKERS)
    hoja: Literal['AUTO', 'A0', 'A1', 'A2', 'A3', 'A4'] | None = None


class ServerPathIn(BaseModel):
    path: str


class SelectionIn(BaseModel):
    feeders: list[str] = Field(default_factory=list)
    all: bool = False
    # Unir la selección en UN solo DGS (red unida), con este nombre.
    unir: bool = False
    nombre: str = ''


class FeedersIn(BaseModel):
    feeders: list[str] = Field(default_factory=list)


class NewSedIn(BaseModel):
    sed_code: str
    installed_kva: float = 0.0
    coord_x: float | None = None
    coord_y: float | None = None
    node_id: str = ''
    kw: float | None = None
    kvar: float | None = None
    kva: float | None = None
    fp: float | None = 0.95
    conductor: str = ''


# ---------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------


def create_app(data_root: Path | None = None) -> FastAPI:
    store = WorkspaceStore(data_root)

    def emit(workspace_id: str, kind: str, data: dict) -> None:
        ws = store.get(workspace_id)
        if ws is not None:
            ws.events.append(kind, data)

    jobs = JobManager(emit)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await asyncio.to_thread(jobs.shutdown)

    app = FastAPI(title='Conversor IGEA/CYMDIST → DGS', version=__version__, lifespan=lifespan)
    app.state.store = store
    app.state.jobs = jobs

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
        return JSONResponse(status_code=400, content={
            'detail': str(exc), 'code': exc.code, 'context': exc.context,
        })

    def ws_or_404(wid: str) -> Workspace:
        ws = store.get(wid)
        if ws is None:
            raise HTTPException(404, 'Espacio de trabajo no encontrado.')
        return ws

    def submit(ws: Workspace, kind: str, title: str, fn, *, lane: str = 'engine') -> dict:
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
            'crs_presets': CRS_PRESETS,
            'slots': SLOTS,
            'default_options': DEFAULT_OPTIONS,
            'server_paths': _server_paths_allowed(),
            'parallel': services.parallel_info(),
        }

    @app.get('/api/powerfactory')
    def powerfactory(refresh: bool = False) -> dict:
        return services.powerfactory_status(refresh=refresh)

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

    @app.delete('/api/workspaces/{wid}', status_code=204)
    def delete_workspace(wid: str) -> None:
        ws = ws_or_404(wid)
        if jobs.active(ws.id):
            raise HTTPException(409, 'Hay trabajos en curso en este espacio.')
        store.delete(wid)

    @app.put('/api/workspaces/{wid}/options')
    def put_options(wid: str, body: OptionsIn) -> dict:
        ws = ws_or_404(wid)
        changes = body.model_dump(exclude_none=True)
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

    # ------------------------------------------------------------ entradas
    def _check_slot(slot: str) -> dict:
        spec = SLOTS.get(slot)
        if spec is None:
            raise HTTPException(404, f'Casilla desconocida: {slot}')
        return spec

    def _assign(
        ws: Workspace,
        slot: str,
        path: Path,
        origin: str,
        *,
        original_name: str | None = None,
    ) -> dict:
        spec = SLOTS[slot]
        warning = comprobar_ranura(path, spec['tipo']) if spec['tipo'] else ''
        meta = ws.set_input(
            slot, path, origin=origin, warning=warning, original_name=original_name,
        )
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
        return _assign(
            ws, slot, target, 'upload',
            original_name=Path(file.filename or slot).name,
        )

    @app.post('/api/workspaces/{wid}/inputs/{slot}/path')
    def server_path_input(wid: str, slot: str, body: ServerPathIn) -> dict:
        ws = ws_or_404(wid)
        _check_slot(slot)
        if not _server_paths_allowed():
            raise HTTPException(403, 'Este servidor no admite rutas locales: suba el fichero.')
        path = Path(body.path.strip().strip('"'))
        if not path.is_file():
            raise HTTPException(400, f'No existe el fichero: {path}')
        return _assign(ws, slot, path, 'server', original_name=path.name)

    @app.delete('/api/workspaces/{wid}/inputs/{slot}')
    def delete_input(wid: str, slot: str) -> dict:
        ws = ws_or_404(wid)
        _check_slot(slot)
        ws.clear_input(slot)
        return ws.public()

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
                ambiguous = slot is not None
                unassigned.append({
                    'name': tmp.name,
                    'reason': (
                        'tipo repetido' if ambiguous
                        else 'no declara tablas conocidas de IGEA/CYMDIST'
                    ),
                    'code': 'INPUT_FILE_AMBIGUOUS' if ambiguous else 'INPUT_FILE_UNKNOWN',
                    'context': {'slot': slot} if ambiguous else {},
                })
                tmp.unlink(missing_ok=True)
                continue
            taken.add(slot)
            target = ws.upload_target(slot, tmp.name)
            tmp.replace(target)
            _assign(ws, slot, target, 'upload', original_name=tmp.name)
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

    @app.get('/api/workspaces/{wid}/electrical-inventory')
    def electrical_inventory(
        wid: str,
        feeder: str | None = None,
        status: str | None = None,
        search: str | None = None,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict:
        return services.electrical_inventory(
            ws_or_404(wid), feeder=feeder, status=status, search=search,
            offset=offset, limit=limit,
        )

    @app.get('/api/workspaces/{wid}/electrical-inventory.{fmt}')
    def electrical_inventory_export(
        wid: str,
        fmt: Literal['csv', 'json'],
        feeder: str | None = None,
        status: str | None = None,
        search: str | None = None,
    ) -> FileResponse:
        path = services.export_electrical_inventory(
            ws_or_404(wid), fmt=fmt, feeder=feeder, status=status, search=search,
        )
        media = 'text/csv' if fmt == 'csv' else 'application/json'
        return FileResponse(path, filename=f'inventario_cargas.{fmt}', media_type=media)

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
            return submit(ws, 'convert_group', f'Unir {len(feeders)} alimentadores en {nombre}.dgs',
                          lambda ctx: services.convert_group(ws, ctx, feeders, nombre))
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
        services.check_powerfactory_flow(ws, body.feeders)
        return submit(ws, 'powerfactory', f'DigSILENT: import + flujo ({len(body.feeders)})',
                      lambda ctx: services.powerfactory_flow(ws, ctx, body.feeders),
                      lane='powerfactory')

    # ------------------------------------------------------------ cargas de SED
    def _upload_tmp(ws: Workspace, upload: UploadFile, default: str) -> Path:
        folder = ws.root / 'subidas'
        folder.mkdir(parents=True, exist_ok=True)
        name = Path(upload.filename or default).name
        suffix = Path(name).suffix.lower() or Path(default).suffix
        fd, tmp = tempfile.mkstemp(suffix=suffix, dir=folder)
        os.close(fd)
        _save_upload(Path(tmp), upload)
        return Path(tmp)

    def _template_response(path: Path) -> FileResponse:
        return FileResponse(path, filename=path.name)

    @app.get('/api/workspaces/{wid}/feeders/{feeder}/load-template')
    def load_template(wid: str, feeder: str, format: Literal['xlsx', 'csv'] = 'xlsx') -> FileResponse:
        return _template_response(services.load_template(ws_or_404(wid), feeder, format))

    @app.post('/api/workspaces/{wid}/feeders/{feeder}/load-plan')
    def load_plan(wid: str, feeder: str, file: UploadFile = File(...)) -> dict:
        ws = ws_or_404(wid)
        tmp = _upload_tmp(ws, file, 'plantilla.xlsx')
        try:
            return services.load_update_plan(ws, feeder, tmp)
        finally:
            tmp.unlink(missing_ok=True)

    @app.get('/api/workspaces/{wid}/feeders/{feeder}/create-template')
    def create_template(wid: str, feeder: str, format: Literal['xlsx', 'csv'] = 'xlsx') -> FileResponse:
        return _template_response(services.create_template(ws_or_404(wid), feeder, format))

    @app.post('/api/workspaces/{wid}/feeders/{feeder}/create-plan')
    def create_plan(wid: str, feeder: str, file: UploadFile = File(...)) -> dict:
        ws = ws_or_404(wid)
        tmp = _upload_tmp(ws, file, 'sed_nuevas.xlsx')
        try:
            return services.create_plan_from_file(ws, feeder, tmp)
        finally:
            tmp.unlink(missing_ok=True)

    @app.post('/api/workspaces/{wid}/feeders/{feeder}/create-plan/single')
    def create_plan_single(wid: str, feeder: str, body: NewSedIn) -> dict:
        return services.create_plan_single(ws_or_404(wid), feeder, body.model_dump())

    @app.post('/api/workspaces/{wid}/plans/{token}/apply', status_code=202)
    def apply_plan(wid: str, token: str) -> dict:
        ws = ws_or_404(wid)
        plan = services.check_plan(ws, token)
        title = ('Actualizar cargas' if plan['kind'] == 'cargas' else 'Crear SED') + f" en {plan['feeder']}"
        return submit(ws, 'plan', title, lambda ctx: services.apply_plan(ws, ctx, token),
                      lane='powerfactory')

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
