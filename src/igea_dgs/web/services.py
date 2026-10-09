"""Las acciones de la interfaz, sin interfaz.

Cada función de aquí es lo que hacía un botón de la GUI de escritorio (retirada en la
spec 001), pero sin Tk y sin diálogos: recibe el espacio de trabajo y un
:class:`JobContext`, escribe en el Registro y devuelve un resultado serializable. Las
rutas de la API solo validan, encolan y responden.

Un defecto de aquella GUI se corrigió aquí en lugar de copiarse:

* «Aplicar catálogo corregido» corregía un modelo en memoria que se tiraba a
  continuación: ninguna conversión posterior lo usaba. Aquí el catálogo aplicado queda
  en el espacio y **toda conversión siguiente** lo pasa a ``convert_selection`` como
  ``catalog_corrections``, que es por donde el motor lo espera.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

from ..naming import feeder_short_name
from ..powerfactory_env import (
    pf_api_version, pf_python_dir, pf_subprocess_env, project_root, python_for_pf, tools_dir,
)
from ..util import nombre_seguro, write_json_atomic
from .jobs import JobContext
from .workspace import Workspace


class UserError(ValueError):
    """Error del operador (falta un fichero, selección vacía…). Se muestra tal cual."""


# ---------------------------------------------------------------------------
# Capacidades del entorno
# ---------------------------------------------------------------------------


def _importable(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def parallel_info() -> dict:
    """Lo que la interfaz necesita para explicar el selector de procesos."""
    import os

    from ..batch import AUTO_WORKERS_MAX

    cpus = os.cpu_count() or 1
    return {'cpus': cpus, 'auto': min(AUTO_WORKERS_MAX, cpus)}

def capabilities() -> dict[str, bool]:
    return {
        'geography': _importable('pyproj'),
        'xlsx': _importable('pandas') and _importable('openpyxl'),
        'access': _importable('pyodbc'),
        'pandapower': _importable('pandapower'),
    }


_PF_CACHE: dict[str, Any] | None = None


def powerfactory_status(refresh: bool = False) -> dict[str, Any]:
    """Qué PowerFactory hay y con qué intérprete se le hablaría.

    Se cachea: buscar el intérprete puede lanzar ``py -3.12``, que tarda.
    """
    global _PF_CACHE
    if _PF_CACHE is not None and not refresh:
        return _PF_CACHE
    pf_dir = pf_python_dir()
    interpreter, why = python_for_pf(pf_dir)
    _PF_CACHE = {
        'api_dir': str(pf_dir) if pf_dir else None,
        'api_version': pf_api_version(pf_dir),
        'interpreter': str(interpreter) if interpreter else None,
        'interpreter_reason': why,
        'running_python': f'{sys.version_info.major}.{sys.version_info.minor}',
        'available': pf_dir is not None and interpreter is not None,
    }
    return _PF_CACHE


def _require_pf() -> tuple[Path | None, Path]:
    status = powerfactory_status()
    pf_dir = Path(status['api_dir']) if status['api_dir'] else None
    if status['interpreter'] is None:
        raise UserError(
            f"La API de PowerFactory es para Python {status['api_version']}, pero el "
            f"conversor corre sobre Python {status['running_python']}. powerfactory.pyd "
            'solo carga en su versión exacta. Instale esa versión o indique el '
            'intérprete en la variable de entorno IGEA_PF_INTERPRETER.'
        )
    return pf_dir, Path(status['interpreter'])


def _script(name: str) -> Path:
    path = tools_dir() / name
    if not path.is_file():
        raise UserError(f'No se encuentra el guion tools/{name}.')
    return path


# ---------------------------------------------------------------------------
# Carga del dataset
# ---------------------------------------------------------------------------


def check_ready(ws: Workspace) -> None:
    missing = ws.missing_inputs()
    if missing:
        raise UserError('Faltan entradas: ' + ', '.join(missing) + '.')
    aliases = ws.input_path('aliases')
    if aliases and not Path(aliases).is_file():
        raise UserError(f'No se encuentra el JSON de aliases: {aliases}')


def require_loaded(ws: Workspace) -> None:
    if ws.dataset is None:
        raise UserError('Primero cargue y liste los alimentadores (paso 2).')


def load_dataset(ws: Workspace, ctx: JobContext) -> dict:
    from ..inventory import build_dataset_inventory, format_inventory_report, write_inventory
    from ..batch import load_aliases
    from ..sources import adapter_for
    from .source_runs import create_source_run

    ctx.log('--- Carga e inventario de alimentadores ---')
    snapshot = create_source_run(ws)
    mode = snapshot.mode
    slots = ('mdb', 'equipment_mdb', 'study', 'aliases') if mode == 'mdb' else (
        'red', 'loads', 'equipment', 'equipment_extra', 'aliases')
    for slot in slots:
        if ws.input_path(slot):
            ctx.log(f'{slot}: {Path(ws.input_path(slot)).name}')

    aliases = load_aliases(snapshot.path_for('aliases') or None)
    loaded = adapter_for(
        mode,
        company=ws.options.get('source_company'),
        period=ws.options.get('source_period'),
    ).load(snapshot, aliases=aliases)
    dataset, catalog_report = loaded.dataset, loaded.catalog_report
    if catalog_report and (
        snapshot.path_for('equipment_extra') or catalog_report.get('final_coverage', 1.0) < 1.0
    ):
        ctx.log('--- Catálogo de conductores ---')
        ctx.log(catalog_report.get('text') or '')
    ctx.check_cancel()
    # Reglas de entrada del proyecto: coordenadas por el grafo y catálogo Excel.
    from ..reglas import catalogo_del_proyecto, preparar_dataset

    entrada = preparar_dataset(dataset, catalogo=catalogo_del_proyecto())
    ctx.log(entrada.texto())
    inventory = build_dataset_inventory(dataset, aliases=aliases)
    inventory['provenance'] = dict(loaded.provenance)
    from .readiness import build_feeder_readiness

    readiness = build_feeder_readiness(
        dataset,
        inventory['feeders'],
        loaded.provenance,
        supplied=loaded.readiness,
        aliases=aliases,
    )
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    inv_path = write_inventory(inventory, ws.out_dir / 'dataset_inventory.json')
    ctx.log(format_inventory_report(inventory))
    ctx.log(f'Inventario JSON: {inv_path.name}')

    import time

    with ws.lock:
        ws.dataset = dataset
        ws.loaded_run_id = snapshot.run_id
        ws.loaded_source_mode = snapshot.mode
        ws.loaded_source_fingerprint = snapshot.fingerprint
        ws.inventory = inventory
        ws.feeder_readiness = readiness
        ws.catalog_report = catalog_report
        ws.reconstructed_dataset = None
        ws.reconstruction_report = None
        ws.reconstruction_report_hash = None
        ws.reconstruction_run_id = None
        ws.reconstruction_selection = ()
        ws.loaded_at = time.time()
        ws.plans.clear()
    return {
        'totals': inventory['totals'],
        'conversion': inventory['conversion'],
        'integrity': inventory['integrity'],
        'catalog_report': catalog_report,
        **loaded.provenance,
    }


def require_active_source_run(ws: Workspace):
    """Impide usar un dataset o artefacto que pertenezca a otra ejecución."""
    snapshot = ws.active_run()
    if (
        snapshot is None
        or ws.loaded_run_id != snapshot.run_id
        or ws.loaded_source_mode != snapshot.mode
        or ws.loaded_source_fingerprint != snapshot.fingerprint
    ):
        raise UserError(
            'SOURCE_RUN_MISMATCH: las entradas cambiaron desde la carga. '
            'Pulse «Cargar / listar alimentadores» para crear una ejecución nueva.'
        )
    return snapshot


def feeder_rows(ws: Workspace) -> list[dict]:
    """Filas de la tabla: inventario + último resultado de conversión de cada una."""
    if not ws.inventory:
        return []
    rows = []
    for row in ws.inventory['feeders']:
        conv = ws.conversions.get(row['network_id']) or {}
        if conv.get('source_run_id') != ws.active_run_id:
            conv = {}
        dgs = conv.get('dgs')
        readiness = ws.feeder_readiness.get(row['network_id']) or {
            'status': 'INVENTORY_ONLY',
            'blocking_codes': ['READINESS_NOT_ASSESSED'],
        }
        reconstruction = conv.get('reconstruction') or {}
        if conv.get('status') == 'ok' and reconstruction.get('assumptions'):
            state = 'CONVERTED_WITH_ASSUMPTIONS'
        elif conv.get('status') == 'ok':
            state = 'DGS_READY'
        else:
            state = readiness['status']
        rows.append({
            **row,
            'readiness': state,
            'blocking_codes': list(readiness.get('blocking_codes') or []),
            'source_quality': readiness.get('source_quality'),
            'repair_count': readiness.get('repair_count', 0),
            'assumption_count': readiness.get('assumption_count', 0),
            'catalog_sources': list(readiness.get('catalog_sources') or []),
            'convergence_state': readiness.get('convergence_state'),
            'source_run_id': ws.loaded_run_id,
            'source_mode': ws.loaded_source_mode,
            'source_fingerprint': ws.loaded_source_fingerprint,
            'conversion': {
                'status': conv.get('status'),
                'error': conv.get('error'),
                'errors_total': conv.get('errors_total'),
                'warnings': len(conv.get('warnings') or []),
                'unresolved_line_types': conv.get('unresolved_line_types') or [],
                'dgs': _rel(ws, dgs),
                'preview_html': _rel(ws, conv.get('preview_html')),
                'xlsx': _rel(ws, conv.get('xlsx')),
                'validation_txt': _rel(ws, conv.get('validation_txt')),
                'counts': conv.get('counts'),
                'converted_at': conv.get('converted_at'),
                'output_name': conv.get('feeder'),
            } if conv else None,
        })
    return rows


def _rel(ws: Workspace, path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    try:
        rel = p.resolve().relative_to(ws.out_dir.resolve())
    except (ValueError, OSError):
        return None
    return rel.as_posix() if p.exists() else None


# ---------------------------------------------------------------------------
# Conversión
# ---------------------------------------------------------------------------


def _stamp_source_manifest(
    ws: Workspace,
    manifest: dict,
    snapshot,
    reconstruction: dict[str, Any] | None = None,
) -> None:
    """Liga el manifiesto y la metadata DGS a la ejecución que los produjo."""
    source = {
        'source_run_id': snapshot.run_id,
        'source_mode': snapshot.mode,
        'source_fingerprint': snapshot.fingerprint,
    }
    manifest.update(source)
    if reconstruction is not None:
        manifest['reconstruction'] = reconstruction
    for item in manifest.get('feeders') or []:
        item.update(source)
        if reconstruction is not None:
            item['reconstruction'] = reconstruction
        metadata_path = item.get('feeder_metadata')
        if not metadata_path:
            continue
        path = Path(metadata_path)
        if not path.is_file():
            continue
        metadata = json.loads(path.read_text(encoding='utf-8'))
        metadata.update(source)
        if reconstruction is not None:
            metadata['reconstruction'] = reconstruction
        write_json_atomic(path, metadata)
    write_json_atomic(ws.out_dir / 'batch_manifest.json', manifest)


def check_convert_options(ws: Workspace) -> None:
    """Lo que se comprueba antes de lanzar el lote."""
    opts = ws.options
    caps = capabilities()
    if opts['include_geography'] and not caps['geography']:
        raise UserError('Para georreferenciar instale pyproj (pip install -r requirements.txt) '
                        'o desactive «Georreferenciación».')
    if opts['write_preview'] and not opts['include_geography']:
        raise UserError('La vista previa del mapa requiere georreferenciación activa.')
    if opts['export_xlsx'] and not caps['xlsx']:
        raise UserError('Para Excel instale pandas y openpyxl, o desactive «Exportar Excel».')
    if opts['include_geography']:
        from ..geography import assert_metre_source_crs

        try:
            assert_metre_source_crs(opts['source_crs'] or 'EPSG:32718')
        except ValueError as exc:
            raise UserError(str(exc)) from exc


def check_selection_readiness(
    ws: Workspace,
    feeders: list[str] | None,
    all_feeders: bool,
) -> list[str]:
    """Puerta común y síncrona para TXT, MDB y VNR-GIS."""
    require_loaded(ws)
    from .readiness import FeederReadinessError, validate_selection

    try:
        return validate_selection(
            (ws.inventory or {}).get('feeders') or [],
            ws.feeder_readiness,
            feeders,
            all_feeders=all_feeders,
        )
    except FeederReadinessError as exc:
        raise UserError(str(exc)) from exc


def convert(ws: Workspace, ctx: JobContext, feeders: list[str] | None, all_feeders: bool) -> dict:
    from ..batch import convert_selection, load_aliases
    from .reconstruction_service import (
        matching_reconstruction,
        reconstruct_selection,
        reconstruction_evidence,
        resolve_selection,
    )

    snapshot = require_active_source_run(ws)
    selected, network_ids = resolve_selection(ws, feeders, all_feeders=all_feeders)
    ready_without_reconstruction = all(
        (ws.feeder_readiness.get(network_id) or {}).get('status')
        in {'CONVERSION_READY', 'READY_ORIGINAL'}
        for network_id in network_ids
    )
    if not ready_without_reconstruction:
        from ..dataset import CymdistDataset

        # Keep the preflight fail-closed for adapter/test doubles that did not
        # provide a canonical dataset. Real TXT/MDB/VNR loads always do.
        if not isinstance(ws.dataset, CymdistDataset):
            check_selection_readiness(ws, feeders, all_feeders)
    if not ready_without_reconstruction and not matching_reconstruction(ws, network_ids):
        ctx.log('La selección tiene datos incompletos: se crea una reconstrucción auditable.')
        reconstruct_selection(ws, selected, all_feeders=False)
    use_reconstruction = matching_reconstruction(ws, network_ids)
    dataset = ws.reconstructed_dataset if use_reconstruction else ws.dataset
    reconstruction = reconstruction_evidence(ws) if use_reconstruction else None
    opts = ws.options
    aliases = load_aliases(snapshot.path_for('aliases') or None)
    corrections = ws.catalog_corrections()
    if all_feeders:
        ctx.log(f"Alcance: todos ({len(ws.inventory['feeders']) if ws.inventory else '?'})")
    else:
        ctx.log(f'Alcance: {len(feeders or [])} seleccionado(s): '
                + ', '.join((feeders or [])[:8]) + ('…' if len(feeders or []) > 8 else ''))
    if corrections:
        ctx.log(f'Catálogo corregido aplicado: {len(corrections)} código(s).')
    ctx.log('--- Inicio de conversión ---')

    from ..batch import resolve_workers

    total = len(selected)
    workers = int(opts.get('workers') or 0)
    n_workers = resolve_workers(workers, max(total, 1))
    if n_workers > 1:
        ctx.log(f'Convirtiendo con {n_workers} procesos en paralelo.')

    def on_progress(network_id: str, index: int, total: int) -> None:
        name = feeder_short_name(network_id)
        ctx.progress(index, total, name)
        # En serie el aviso llega al empezar cada alimentador; en paralelo, al
        # terminar (varios están en marcha a la vez). El texto dice cuál de los dos.
        ctx.log(f'[{index}/{total}] {name} listo' if n_workers > 1 else f'[{index}/{total}] {name}…')

    from ..reglas import catalogo_del_proyecto

    manifest = convert_selection(
        dataset, None if all_feeders else selected, ws.out_dir,
        all_feeders=all_feeders,
        aliases=aliases,
        strict=bool(opts['strict']),
        include_geography=bool(opts['include_geography']),
        source_crs=opts['source_crs'] or 'EPSG:32718',
        target_crs=opts['target_crs'] or 'EPSG:4326',
        export_xlsx=bool(opts['export_xlsx']),
        export_tsv=bool(opts['export_tsv']),
        write_preview=bool(opts['write_preview']),
        preview_backend='auto',
        on_progress=on_progress,
        cancel=ctx.cancel,
        # Sin catálogo corregido subido, valen las fichas del catálogo del proyecto.
        catalog_corrections=corrections or None,
        # El carril «engine» sigue siendo uno: dos lotes nunca compiten entre sí;
        # dentro de un lote, los alimentadores se reparten entre procesos.
        workers=workers,
        reglas=reglas_de(ws),
        # El dataset reconstruido ya contiene filas exactas y no puede volver a la
        # resolución difusa/DEFAULT del camino literal.
        catalogo=None if use_reconstruction else catalogo_del_proyecto(),
    )
    _stamp_source_manifest(ws, manifest, snapshot, reconstruction)
    ws.record_conversions(manifest)

    summary = manifest['summary']
    ctx.log(f"Solicitados: {summary['requested']} · OK: {summary['ok']} · "
            f"Omitidos: {summary.get('skipped', 0)} · Fallidos: {summary['failed']}")
    for item in manifest.get('feeders', []):
        name = item.get('feeder') or item.get('network_id', '?')
        status = item.get('status')
        if status == 'ok':
            counts = item.get('counts') or {}
            reglas = item.get('reglas') or {}
            extra = []
            if (reglas.get('trafomix') or {}).get('excluidos'):
                extra.append(f"trafomix excluidos={reglas['trafomix']['excluidos']}")
            if (reglas.get('puentes') or {}).get('tramos'):
                extra.append(f"puentes fundidos={reglas['puentes']['tramos']}")
            if reglas.get('sed_redimensionadas'):
                extra.append(f"SED redimensionadas={len(reglas['sed_redimensionadas'])}")
            hoja = item.get('hoja') or {}
            if hoja:
                extra.append(f"hoja {hoja['formato']} {hoja['orientacion']} 1:{hoja['escala_1_a']:,}")
            ctx.log(f"  OK {name} → líneas={counts.get('source_lines', '?')} "
                    f"cargas={counts.get('source_loads', '?')} "
                    f"SED={counts.get('source_seds', counts.get('dgs_seds', '?'))}"
                    + (f" · {' · '.join(extra)}" if extra else ''))
            for linea in reglas.get('sed_redimensionadas') or []:
                ctx.log(f"      SED redimensionada — {linea}")
        elif status == 'skipped':
            ctx.log(f"  OMITIDO {name}: {item.get('error') or 'sin topología'}")
        else:
            ctx.log(f"  FAIL {name}: {item.get('error') or 'error'}")
    ctx.log('--- Fin de conversión ---')
    return {
        'summary': summary,
        'status': manifest.get('status'),
        'input_warnings': manifest.get('input_warnings') or [],
        'manifest': 'batch_manifest.json',
        'workers': manifest.get('workers', 1),
        'reconstruction': reconstruction,
    }


# ---------------------------------------------------------------------------
# PowerFactory: import + escenario + flujo
# ---------------------------------------------------------------------------


def powerfactory_targets(ws: Workspace, feeders: list[str]) -> list[str]:
    """Usa un DGS unido vigente cuando coincide con toda la selección."""
    if len(feeders) < 2:
        return list(feeders)

    selected = set(feeders)
    latest_conversion = max(
        (float(item.get('converted_at') or 0)
         for item in ws.conversions.values()
         if item.get('feeder') in selected),
        default=0.0,
    )
    candidates: list[tuple[float, str]] = []
    for name, group in ws.groups.items():
        members = list(group.get('feeders') or [])
        requested_members = list(group.get('requested_feeders') or members)
        converted_at = group.get('converted_at')
        group_path = ws.out_dir / f'{name}.dgs'
        selection_matches = (
            set(members) == selected and len(members) == len(selected)
        ) or (
            set(requested_members) == selected and len(requested_members) == len(selected)
        )
        if group.get('status') != 'ok' or not selection_matches or not group_path.is_file():
            continue
        latest_member_conversion = max(
            (float(item.get('converted_at') or 0)
             for item in ws.conversions.values()
             if item.get('feeder') in set(members)),
            default=0.0,
        )
        if converted_at is not None:
            if float(converted_at) < max(latest_conversion, latest_member_conversion):
                continue
            group_time = float(converted_at)
        else:
            group_mtime = group_path.stat().st_mtime_ns
            individual_mtimes = [
                (ws.out_dir / f'{feeder}.dgs').stat().st_mtime_ns
                for feeder in members
                if (ws.out_dir / f'{feeder}.dgs').is_file()
            ]
            if individual_mtimes and group_mtime < max(individual_mtimes):
                continue
            group_time = group_path.stat().st_mtime
        candidates.append((group_time, name))

    if candidates:
        return [max(candidates)[1]]
    return list(feeders)


def dgs_jobs(ws: Workspace, feeders: list[str]) -> tuple[list[tuple[str, Path, Path | None]], list[str]]:
    jobs, missing = [], []
    for feeder in powerfactory_targets(ws, feeders):
        dgs = ws.out_dir / f'{feeder}.dgs'
        if not dgs.is_file():
            missing.append(feeder)
            continue
        geo = ws.out_dir / f'{feeder}_geography.json'
        jobs.append((feeder, dgs, geo if geo.is_file() else None))
    return jobs, missing


def check_powerfactory_source_run(ws: Workspace, feeders: list[str]) -> dict[str, Any]:
    """Liga cada DGS y sidecar al run activo antes de cualquier mutación en PF."""
    from ..feeder_metadata import read_feeder_metadata
    from ..powerfactory_metadata import verify_reconstruction_contract

    snapshot = require_active_source_run(ws)
    jobs, missing = dgs_jobs(ws, feeders)
    if missing:
        raise UserError('Primero convierta a DGS. Faltan: '
                        + ', '.join(f'{name}.dgs' for name in missing[:12]))
    evidence: list[dict[str, Any]] = []
    for feeder, dgs, _geo in jobs:
        metadata_path = dgs.with_name(f'{dgs.stem}_feeder_metadata.json')
        if not metadata_path.is_file():
            raise UserError(f'POWERFACTORY_SOURCE_RUN_MISMATCH: {feeder} no tiene sidecar.')
        try:
            metadata = read_feeder_metadata(metadata_path, expected_dgs=dgs)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise UserError(
                f'POWERFACTORY_SOURCE_RUN_MISMATCH: {feeder}: {exc}'
            ) from exc
        actual = (
            metadata.get('source_run_id'),
            metadata.get('source_mode'),
            metadata.get('source_fingerprint'),
        )
        expected = (snapshot.run_id, snapshot.mode, snapshot.fingerprint)
        if actual != expected:
            raise UserError(
                f'POWERFACTORY_SOURCE_RUN_MISMATCH: {feeder} pertenece a '
                f'{actual[0] or "una ejecución sin identidad"}, no a {snapshot.run_id}.'
            )
        reconstruction_verification = None
        reconstruction = metadata.get('reconstruction')
        if reconstruction is not None:
            report_path = ws.out_dir / str(reconstruction.get('report') or '')
            try:
                reconstruction_verification = verify_reconstruction_contract(
                    metadata,
                    report_path,
                    expected_hash=ws.reconstruction_report_hash,
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise UserError(
                    f'POWERFACTORY_RECONSTRUCTION_MISMATCH: {feeder}: {exc}'
                ) from exc
            if (
                ws.reconstruction_run_id != snapshot.run_id
                or ws.reconstruction_report_hash
                != reconstruction_verification['report_sha256']
            ):
                raise UserError(
                    f'POWERFACTORY_RECONSTRUCTION_MISMATCH: {feeder} no pertenece '
                    'a la reconstrucción activa.'
                )
        evidence.append({
            'target': feeder,
            'dgs': dgs.name,
            'dgs_sha256': metadata['dgs_sha256'],
            'metadata': metadata_path.name,
            'reconstruction': reconstruction_verification,
        })
    return {
        'source_run_id': snapshot.run_id,
        'source_mode': snapshot.mode,
        'source_fingerprint': snapshot.fingerprint,
        'targets': evidence,
    }


def carpeta_pf() -> str:
    """Carpeta de DIgSILENT de los proyectos importados, según el perfil de empresa.

    Se valida aquí, antes de lanzar nada en DIgSILENT (spec 005, RF-4): un nombre que
    PowerFactory recorte o rechace dejaría la carpeta con otro nombre, y la siguiente
    lectura no la encontraría.
    """
    from ..carpeta_pf import CarpetaError, nombre_de_perfil

    try:
        return nombre_de_perfil(project_root() / 'config' / 'perfil_empresa.json')
    except CarpetaError as exc:
        raise UserError(str(exc)) from exc


def check_powerfactory_flow(ws: Workspace, feeders: list[str]) -> None:
    carpeta_pf()
    if not feeders:
        raise UserError('Seleccione al menos un alimentador ya convertido.')
    jobs, missing = dgs_jobs(ws, feeders)
    if not jobs:
        raise UserError('Primero convierta a DGS. Faltan: '
                        + ', '.join(f'{f}.dgs' for f in missing[:12]))
    missing_metadata = [
        dgs.name for _feeder, dgs, _geo in jobs
        if not dgs.with_name(f'{dgs.stem}_feeder_metadata.json').is_file()
    ]
    if missing_metadata:
        raise UserError(
            'Falta la trazabilidad por alimentador de '
            + ', '.join(missing_metadata[:8])
            + '. Vuelva a convertir esos alimentadores para generar el manifiesto.'
        )
    if ws.active_run_id:
        check_powerfactory_source_run(ws, feeders)
    _script('powerfactory_acceptance.py')
    _require_pf()


def pandapower_preflight(
    ws: Workspace,
    targets: list[str],
    ctx: JobContext,
) -> dict[str, Any]:
    """Informa de conectividad con pandapower sin omitir DGS de la importación."""
    from ..batch import load_aliases
    from ..oraculo import disponible, validar

    if not disponible():
        return {
            'disponible': False,
            'avisos': ['pandapower no está instalado; se continúa con el import DGS.'],
            'feeders': [],
        }

    members: list[str] = []
    for target in targets:
        group = ws.groups.get(target)
        names = group.get('feeders', []) if group else [target]
        for name in names:
            if name not in members:
                members.append(name)

    from ..catalog import leer_catalogo
    from ..model import build_feeder_model
    from ..reglas import aplicar_reglas, catalogo_del_proyecto

    corrections = ws.catalog_corrections()
    catalog = catalogo_del_proyecto()
    if not corrections and catalog:
        corrections = leer_catalogo(catalog)
    aliases = load_aliases(ws.input_path('aliases') or None)
    reports: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, feeder in enumerate(members, start=1):
        ctx.check_cancel()
        ctx.progress(index - 1, len(members), f'pandapower: {feeder}')
        try:
            model = build_feeder_model(
                ws.dataset, feeder, aliases=aliases,
                strict=bool(ws.options.get('strict', True)),
            )
            aplicar_reglas(model, reglas_de(ws), correcciones=corrections)
            report = validar(model)
        except Exception as exc:  # noqa: BLE001 - el oráculo nunca debe omitir un DGS
            warnings.append(f'{feeder}: no se pudo completar preflight pandapower: {exc}')
            ctx.log(f'  AVISO pandapower {feeder}: {warnings[-1]} Se continúa con el import.')
            continue
        data = report.as_dict()
        data['feeder'] = feeder
        reports.append(data)
        ctx.log(f"  pandapower {feeder}: {report.resumen()}; "
                f'barras sin alimentar={report.barras_sin_alimentar}')
        if not report.disponible or not report.convergio or report.barras_sin_alimentar:
            warnings.append(
                f'{feeder}: {report.barras_sin_alimentar} barra(s) sin alimentar; '
                f'{report.resumen()}. Se continúa con el import DGS completo.')
        errors = [h.linea() for h in report.errores]
        warnings.extend(errors)
    return {
        'disponible': True,
        'import_continued': True,
        'feeders': reports,
        'avisos': warnings,
    }


def powerfactory_flow(ws: Workspace, ctx: JobContext, feeders: list[str]) -> dict:
    script = _script('powerfactory_acceptance.py')
    jobs, missing = dgs_jobs(ws, feeders)
    source_evidence = check_powerfactory_source_run(ws, feeders) if ws.active_run_id else None
    ctx.log('--- Inicio DigSILENT: import + escenario + flujo ---')
    ctx.log('--- Preflight pandapower: conectividad, islas y convergencia ---')
    preflight = pandapower_preflight(ws, [name for name, _dgs, _geo in jobs], ctx)
    for aviso in preflight.get('avisos') or []:
        ctx.log(f'  AVISO pandapower: {aviso}')
    ctx.log('Preflight informativo terminado; se importará completo cada DGS solicitado.')

    carpeta = carpeta_pf()
    pf_dir, interpreter = _require_pf()
    ctx.log(f'Intérprete para la API: {interpreter}  [{powerfactory_status()["interpreter_reason"]}]')
    ctx.log(f'Carpeta de DIgSILENT: {carpeta}')
    for feeder in missing:
        ctx.log(f'  (sin DGS, se omite) {feeder}')
    env = pf_subprocess_env(pf_dir)
    lines, ok_n, fail_n = [], 0, 0
    for index, (feeder, dgs, geo) in enumerate(jobs, start=1):
        ctx.check_cancel()
        ctx.progress(index - 1, len(jobs), feeder)
        ctx.log(f'[{index}/{len(jobs)}] Import + escenario + flujo {feeder}…')
        # Importar, activar escenario y correr el flujo: segundos. Sin --run-studies
        # (el cortocircuito de una red unida tardaba más de 20 min y 7 GB de RAM en
        # cada clic) y sin --fix-until-converge, que ante un flujo que no converge
        # modifica el modelo (escala cargas) sin pedirlo. Los estudios se lanzan aparte.
        cmd = [str(interpreter), str(script), '--import-dgs', str(dgs),
               '--ensure-scenario', '--run-load-flow', '--pf-carpeta', carpeta]
        metadata_path = dgs.with_name(f'{dgs.stem}_feeder_metadata.json')
        cmd += ['--feeder-metadata', str(metadata_path)]
        if source_evidence is not None:
            cmd += [
                '--source-run-id', source_evidence['source_run_id'],
                '--source-mode', source_evidence['source_mode'],
                '--source-fingerprint', source_evidence['source_fingerprint'],
            ]
            target_evidence = next(
                item for item in source_evidence['targets'] if item['target'] == feeder
            )
            reconstruction = target_evidence.get('reconstruction')
            if reconstruction:
                cmd += [
                    '--reconstruction-report',
                    str(ws.out_dir / reconstruction['report']),
                    '--reconstruction-report-sha256', reconstruction['report_sha256'],
                ]
        if geo is not None:
            cmd += ['--manifest', str(geo)]
        cmd += ['--output-json', str(ws.out_dir / f'{feeder}_powerfactory_acceptance.json'),
                '--output-txt', str(ws.out_dir / f'{feeder}_powerfactory_acceptance.txt')]
        rc = ctx.run_process(cmd, env=env, cwd=str(project_root()))
        acceptance_path = ws.out_dir / f'{feeder}_powerfactory_acceptance.json'
        try:
            acceptance = json.loads(acceptance_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            acceptance = {}
        metadata = acceptance.get('feeder_metadata') or {}
        if metadata.get('status') == 'assigned':
            ctx.log(f"  Columna Alimentador: {metadata.get('written', 0)} objeto(s) — "
                    f"{metadata.get('by_feeder', {})}")
        elif metadata.get('status') == 'failed':
            ctx.log(f"  ERROR columna Alimentador: {metadata.get('error')}")
        proyecto = _proyecto_importado(acceptance_path)
        if proyecto:
            with ws.lock:
                ws.pf_projects[feeder] = proyecto
                ws.save()
            ctx.log(f'  proyecto de PowerFactory: {proyecto}')
        if rc == 0:
            ok_n += 1
            lines.append(f'OK {feeder} → convergencia / aceptación')
        elif rc == 3:
            fail_n += 1
            lines.append(f'FAIL {feeder}: API PowerFactory no disponible (abra PF o configure PF_PYTHON)')
        else:
            fail_n += 1
            lines.append(f'FAIL {feeder}: código {rc}')
    ctx.progress(len(jobs), len(jobs), '')
    for line in lines:
        ctx.log('  ' + line)
    ctx.log('--- Fin DigSILENT ---')
    return {'ok': ok_n, 'failed': fail_n, 'requested': len(jobs),
            'missing_dgs': missing, 'lines': lines, 'preflight': preflight,
            'source': source_evidence}


# ---------------------------------------------------------------------------
# Modelos de un alimentador (cargas, SED nuevas, catálogo)
# ---------------------------------------------------------------------------


def reglas_de(ws: Workspace):
    """Reglas del proyecto con la hoja elegida; por defecto se ajusta a la red."""
    from dataclasses import replace

    from ..reglas import REGLAS_PROYECTO

    return replace(REGLAS_PROYECTO, hoja=ws.options.get('hoja'))


def build_model(ws: Workspace, feeder: str, *, geography: bool | None = None):
    """El modelo del alimentador **con las reglas del proyecto**, igual que en el DGS.

    Las plantillas y los planes de cargas se construyen sobre él: si la plantilla
    listara trafomix o SED que el DGS ya no tiene, el plan buscaría en PowerFactory
    cargas que no existen.
    """
    require_loaded(ws)
    from ..model import build_feeder_model
    from ..reglas import aplicar_reglas, catalogo_del_proyecto

    dataset = _dataset_for_feeder(ws, feeder)
    try:
        modelo = build_feeder_model(
            dataset, feeder, strict=False,
            include_geography=ws.options['include_geography'] if geography is None else geography,
        )
    except Exception as exc:  # noqa: BLE001 - se informa al operador
        raise UserError(f'No se pudo construir {feeder}: {exc}') from exc
    correcciones = ws.catalog_corrections()
    if not correcciones and catalogo_del_proyecto():
        from ..catalog import leer_catalogo

        correcciones = leer_catalogo(catalogo_del_proyecto())
    aplicar_reglas(modelo, reglas_de(ws), correcciones=correcciones)
    return modelo


def _dataset_for_feeder(ws: Workspace, feeder: str):
    """Use derived data only when it belongs to this active run and feeder."""
    if (
        ws.reconstructed_dataset is not None
        and ws.reconstruction_run_id == ws.loaded_run_id == ws.active_run_id
    ):
        try:
            network_id = ws.reconstructed_dataset.resolve_feeder(feeder)
        except KeyError:
            network_id = feeder
        if network_id in ws.reconstruction_selection:
            return ws.reconstructed_dataset
    return ws.dataset


# ---------------------------------------------------------------------------
# Varios alimentadores en un solo DGS
# ---------------------------------------------------------------------------


def group_selection(ws: Workspace, feeders: list[str], all_feeders: bool) -> list[str]:
    require_loaded(ws)
    from .reconstruction_service import resolve_selection

    feeders, _network_ids = resolve_selection(ws, feeders, all_feeders=all_feeders)
    if len(feeders) < 2:
        raise UserError('Para unir en un solo DGS seleccione al menos dos alimentadores.')
    from ..batch import expand_connected_feeders

    expanded = list(expand_connected_feeders(ws.dataset, feeders))
    expanded_names, _expanded_ids = resolve_selection(ws, expanded, all_feeders=False)
    return expanded_names


def group_name(nombre: str, feeders: list[str]) -> str:
    base = (nombre or '').strip() or '_'.join(feeders[:4]) + ('_ETC' if len(feeders) > 4 else '')
    return nombre_seguro(base, maximo=60)


def convert_group(
    ws: Workspace,
    ctx: JobContext,
    feeders: list[str],
    nombre: str,
    *,
    requested_feeders: list[str] | None = None,
) -> dict:
    import time

    from ..batch import convert_group as convertir_grupo
    from ..batch import load_aliases
    from ..reglas import catalogo_del_proyecto
    from .reconstruction_service import (
        matching_reconstruction,
        reconstruct_selection,
        reconstruction_evidence,
        resolve_selection,
    )

    snapshot = require_active_source_run(ws)
    selected, network_ids = resolve_selection(ws, feeders, all_feeders=False)
    ready_without_reconstruction = all(
        (ws.feeder_readiness.get(network_id) or {}).get('status')
        in {'CONVERSION_READY', 'READY_ORIGINAL'}
        for network_id in network_ids
    )
    if not ready_without_reconstruction and not matching_reconstruction(ws, network_ids):
        ctx.log('La red unida contiene datos incompletos: se reconstruye el lote completo.')
        reconstruct_selection(ws, selected, all_feeders=False)
    use_reconstruction = matching_reconstruction(ws, network_ids)
    dataset = ws.reconstructed_dataset if use_reconstruction else ws.dataset
    reconstruction = reconstruction_evidence(ws) if use_reconstruction else None
    opts = ws.options
    ctx.log(f'--- Red unida {nombre}: {", ".join(feeders)} ---')
    añadidos = sorted(set(feeders) - set(requested_feeders or feeders))
    if añadidos:
        ctx.log('Alimentadores añadidos por continuidad de red y tensión: '
                + ', '.join(añadidos))

    def on_progress(network_id: str, index: int, total: int) -> None:
        name = feeder_short_name(network_id)
        ctx.progress(index, total, name)
        ctx.log(f'[{index}/{total}] {name}…')

    man = convertir_grupo(
        dataset, selected, ws.out_dir, name=nombre,
        aliases=load_aliases(snapshot.path_for('aliases') or None),
        strict=bool(opts['strict']),
        source_crs=opts['source_crs'] or 'EPSG:32718',
        target_crs=opts['target_crs'] or 'EPSG:4326',
        catalog_corrections=ws.catalog_corrections() or None,
        reglas=reglas_de(ws),
        catalogo=None if use_reconstruction else catalogo_del_proyecto(),
        on_progress=on_progress, cancel=ctx.cancel,
    )
    source = {
        'source_run_id': snapshot.run_id,
        'source_mode': snapshot.mode,
        'source_fingerprint': snapshot.fingerprint,
    }
    man.update(source)
    if reconstruction is not None:
        man['reconstruction'] = reconstruction
    metadata_path = man.get('feeder_metadata')
    if metadata_path and Path(metadata_path).is_file():
        metadata = json.loads(Path(metadata_path).read_text(encoding='utf-8'))
        metadata.update(source)
        if reconstruction is not None:
            metadata['reconstruction'] = reconstruction
        write_json_atomic(Path(metadata_path), metadata)
    write_json_atomic(ws.out_dir / f'{nombre}_manifest.json', man)
    ctx.log(man.get('entrada') or '')
    if man.get('union'):
        ctx.log(man['union'])
    for alim, inf in (man.get('reglas_por_alimentador') or {}).items():
        t = (inf.get('trafomix') or {}).get('excluidos', 0)
        pu = (inf.get('puentes') or {}).get('tramos', 0)
        ctx.log(f'  {alim}: puentes fundidos {pu}, trafomix excluidos {t}, '
                f'SED redimensionadas {len(inf.get("sed_redimensionadas") or [])}')
        for linea in inf.get('sed_redimensionadas') or []:
            ctx.log(f'      SED redimensionada — {linea}')
    if man.get('de_energised_nodes'):
        ctx.log(f"AVISO: {len(man['de_energised_nodes'])} barras sin camino a ninguna fuente: "
                'quedan en el DGS fuera de servicio.')
    if man['status'] == 'ok':
        hoja = man.get('hoja') or {}
        ctx.log(f"OK {nombre}.dgs — {man['counts'].get('dgs_lines', '?')} líneas; "
                f"hoja {hoja.get('formato')} {hoja.get('orientacion')}; "
                f"completitud: {'OK' if not man['completitud']['fallos'] else man['completitud']['fallos']}")
    else:
        ctx.log(f"FAIL {nombre}: {man.get('error')}")
    with ws.lock:
        ws.groups[nombre] = {k: man.get(k) for k in (
            'name', 'feeders', 'status', 'error', 'dgs', 'feeder_metadata',
            'hoja', 'ties', 'completitud', 'source_run_id', 'source_mode',
            'source_fingerprint', 'reconstruction')}
        ws.groups[nombre]['requested_feeders'] = list(requested_feeders or feeders)
        ws.groups[nombre]['converted_at'] = time.time() if man['status'] == 'ok' else None
        ws.save()
    return {'group': nombre, 'status': man['status'], 'error': man.get('error'),
            'dgs': f'{nombre}.dgs' if man['status'] == 'ok' else None,
            'feeder_metadata': f'{nombre}_feeder_metadata.json' if man['status'] == 'ok' else None,
            'feeders': feeders, 'completitud': man.get('completitud'),
            'hoja': man.get('hoja'), 'manifest': f'{nombre}_manifest.json',
            'reconstruction': reconstruction}


def _proyecto_importado(informe: Path) -> str | None:
    """Ruta en la carpeta del proyecto que creó la importación, leída del informe.

    Los informes anteriores a la spec 005 solo traen el nombre.
    """
    import json

    try:
        datos = json.loads(informe.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    importacion = datos.get('import') or {}
    return importacion.get('project_path') or importacion.get('project_name') or None


# ---------------------------------------------------------------------------
# Cargas en varios alimentadores de un proyecto de PowerFactory
# ---------------------------------------------------------------------------


def pf_projects(ws: Workspace, ctx: JobContext) -> dict:
    """Proyectos de la carpeta de importación de PowerFactory y sus alimentadores (spec 005)."""
    carpeta = carpeta_pf()
    pf_dir, interpreter = _require_pf()
    out = ws.out_dir / 'pf_proyectos.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    rc = ctx.run_process(
        [str(interpreter), str(_script('pf_proyectos.py')), '--output-json', str(out),
         '--carpeta', carpeta],
        env=pf_subprocess_env(pf_dir), cwd=str(project_root()),
    )
    if rc == 3:
        raise UserError('No se pudo conectar con PowerFactory. Ábralo y reintente.')
    if rc != 0 or not out.is_file():
        raise UserError(f'No se pudieron leer los proyectos de PowerFactory (código {rc}).')
    result = json.loads(out.read_text(encoding='utf-8'))
    if result.get('aviso'):
        ctx.log(f"AVISO: {result['aviso']}")
    with ws.lock:
        ws.pf_inventory = result
        ws.save()
    return result


def _economia_del_lote(economia: dict | None):
    """``{'costos': {...}, 'tec': {...}}`` → (CostosUnitarios, ParametrosTec) validados."""
    from ..economia import CostosUnitarios, EconomiaError, ParametrosTec

    if not economia:
        return None, None
    try:
        costos = CostosUnitarios(**(economia.get('costos') or {}))
        costos.validar()
        tec = ParametrosTec(**economia['tec']) if economia.get('tec') else None
        if tec is not None:
            tec.validar()
    except (TypeError, KeyError) as exc:
        raise UserError(f'Datos económicos incompletos o con campos desconocidos: {exc}') from exc
    except EconomiaError as exc:
        raise UserError(str(exc)) from exc
    return costos, tec


def cargas_plantilla(ws: Workspace, tipo: str, fmt: str) -> Path:
    """Plantilla **vacía** de demandas o de cargas nuevas: sin modelo ni entradas (RF-1)."""
    from ..cargas_pf import escribir_plantilla

    nombre = {'demandas': 'demandas', 'nuevas': 'cargas_nuevas'}[tipo]
    return escribir_plantilla(tipo, ws.out_dir / 'plantillas' / f'{nombre}.{fmt}')


def cargas_plan(
    ws: Workspace, project: str, feeders: list[str],
    demandas_file: Path | None, nuevas_file: Path | None,
    nueva: dict | None = None, economia: dict | None = None,
) -> dict:
    """Valida los libros y guarda el plan para ``tools/cargas_pf.py`` (spec 004).

    No mira las entradas del espacio: qué SED coincide y dónde se conecta cada carga
    nueva lo decide el guion en el proyecto de DIgSILENT (RF-1). Una fila con error se
    informa y no impide aplicar las demás. ``nueva`` es la carga del formulario: pasa por
    el mismo lector que el libro, para que no haya dos definiciones de «fila válida».
    """
    from dataclasses import asdict

    from ..cargas_pf import Lectura, armar_plan, leer_demandas, leer_hoja_nuevas, leer_nuevas
    from ..loads import LoadTemplateError

    costos, tec = _economia_del_lote(economia)
    crs = ws.options.get('source_crs') or ''
    try:
        demandas = leer_demandas(demandas_file) if demandas_file is not None else None
        nuevas = leer_nuevas(nuevas_file, source_crs=crs) if nuevas_file is not None else None
        if nueva:
            filas, errores = leer_hoja_nuevas(list(nueva), [list(nueva.values())], 'formulario',
                                              source_crs=crs)
            nuevas = nuevas or Lectura()
            nuevas.filas += filas
            nuevas.errores += errores
        if tec is not None and not (nuevas and nuevas.filas):
            raise UserError('La evaluación técnico-económica valora las cargas nuevas: '
                            'suba también el libro de cargas nuevas o use el formulario.')
        plan = armar_plan(
            project=project, feeders=feeders, demandas=demandas, nuevas=nuevas,
            costos=asdict(costos) if costos is not None else None,
            tec=None if tec is None else {'parametros': tec.to_dict(), 'comtececo': tec.a_comtececo()},
            carpeta=carpeta_pf(),
        )
    except LoadTemplateError as exc:
        raise UserError(str(exc)) from exc
    token = uuid.uuid4().hex[:12]
    ws.plans_dir.mkdir(parents=True, exist_ok=True)
    path = ws.plans_dir / f'cargas_pf_{token}.json'
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    resumen = {
        'token': token, 'kind': 'cargas_pf', 'project': plan['project'],
        'folder': plan['folder'], 'feeders': plan['feeders'], 'variacion': plan['variacion'],
        'demandas': plan['demandas'][:500], 'nuevas': plan['nuevas'][:500],
        'n_demandas': len(plan['demandas']), 'n_nuevas': len(plan['nuevas']),
        'row_errors': plan['row_errors'], 'omitidas_por_el_operador': plan['omitidas_por_el_operador'],
        'sin_datos': plan['sin_datos'], 'applicable': plan['aplicable'],
        'tec': plan['tec']['parametros'] if plan['tec'] else None,
    }
    with ws.lock:
        ws.cargas_planes[token] = {'path': str(path), 'project': plan['project'],
                                   'feeders': plan['feeders'], 'applicable': plan['aplicable']}
    return resumen


def cargas_plan_de(ws: Workspace, token: str) -> dict:
    plan = ws.cargas_planes.get(token)
    if plan is None or not Path(plan['path']).is_file():
        raise UserError('El plan ya no existe: vuelva a prepararlo.')
    if not plan['applicable']:
        raise UserError('El plan no tiene nada que aplicar: ninguna fila válida.')
    return plan


def cargas_ejecutar(ws: Workspace, ctx: JobContext, token: str, *, simular: bool) -> dict:
    """Simula o aplica el plan en DIgSILENT con ``tools/cargas_pf.py`` (RF-17 a RF-21).

    Cancelar no mata el guion: se le avisa con un fichero y termina el alimentador en
    curso (RF-19). El trabajo acaba con el informe, que dice qué no se empezó.
    """
    plan = cargas_plan_de(ws, token)
    pf_dir, interpreter = _require_pf()
    modo = 'simulacion' if simular else 'aplicacion'
    report = ws.out_dir / f'cargas_pf_{modo}_{token}.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.unlink(missing_ok=True)
    flag = ws.plans_dir / f'cancelar_{token}.flag'
    flag.unlink(missing_ok=True)
    ctx.log(f"Proyecto de DIgSILENT: {plan['project']}  ·  orden: {', '.join(plan['feeders'])}")
    cmd = [str(interpreter), str(_script('cargas_pf.py')), '--plan', plan['path'],
           '--output-json', str(report), '--cancel-file', str(flag)]
    if simular:
        cmd.append('--simular')
    rc = ctx.run_process(cmd, env=pf_subprocess_env(pf_dir), cwd=str(project_root()),
                         cancel_file=flag)
    flag.unlink(missing_ok=True)
    if rc == 3:
        raise UserError('No se pudo conectar con DIgSILENT. Ábralo y reintente.')
    try:
        informe = json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
    except (OSError, ValueError):
        informe = {}
    if not informe:
        raise UserError(f'El guion terminó con el código {rc} sin dejar informe: vea el Registro.')
    if informe.get('error'):
        raise UserError(informe['error'])
    if rc == 2:
        ctx.log('Hubo cargas que no se pudieron escribir o crear: vea «fallos» en el informe.')
    return {'returncode': rc, 'modo': informe.get('modo'), 'report': report.name,
            'project': plan['project'], 'informe': informe}


# ---------------------------------------------------------------------------
# Demanda medida (spec 004, RF-22 a RF-39)
# ---------------------------------------------------------------------------

DEMANDA_TIPOS = ('medidores', 'cabecera', 'suministros', 'clientes')
DEMANDA_ETIQUETAS = {
    'medidores': 'libro medidor por alimentador', 'cabecera': 'medición de cabecera',
    'suministros': 'libro de suministros', 'clientes': 'libro de clientes importantes',
}


def demanda_alias():
    """Alias genéricos y, delante, los de la empresa en ``config/demanda_medida_alias.json``."""
    from ..demanda_medida import DemandaError, cargar_alias

    try:
        return cargar_alias(project_root() / 'config' / 'demanda_medida_alias.json')
    except DemandaError as exc:
        raise UserError(str(exc)) from exc


def demanda_carpeta(ws: Workspace, tipo: str) -> Path:
    return ws.root / 'demanda' / tipo


def demanda_asignar(ws: Workspace, tipo: str, path: Path, origin: str) -> dict:
    """Guarda en el espacio el libro (o la carpeta de cabecera) de ``tipo`` (RF-39)."""
    from ..demanda_medida import EXTENSIONES, libros_de_cabecera

    if tipo == 'cabecera':
        try:
            libros = libros_de_cabecera([path])
        except Exception as exc:  # noqa: BLE001 - DemandaError o de E/S: error de usuario
            raise UserError(str(exc)) from exc
        meta = {'path': str(path), 'name': path.name, 'origin': origin,
                'libros': [p.name for p in libros]}
    else:
        if not path.is_file() or path.suffix.lower() not in EXTENSIONES:
            raise UserError(f'{path.name}: el {DEMANDA_ETIQUETAS[tipo]} debe ser un libro '
                            + ', '.join(EXTENSIONES))
        meta = {'path': str(path), 'name': path.name, 'origin': origin}
    with ws.lock:
        ws.demanda[tipo] = meta
        ws.save()
    return ws.public()


def demanda_quitar(ws: Workspace, tipo: str) -> dict:
    import shutil

    with ws.lock:
        ws.demanda.pop(tipo, None)
        ws.save()
    shutil.rmtree(demanda_carpeta(ws, tipo), ignore_errors=True)
    return ws.public()


def _demanda_ruta(ws: Workspace, tipo: str) -> Path:
    meta = ws.demanda.get(tipo)
    if not meta or not Path(meta['path']).exists():
        raise UserError(f'Falta el {DEMANDA_ETIQUETAS[tipo]}: súbalo o indique su ruta.')
    return Path(meta['path'])


def demanda_medidores(ws: Workspace, alimentador: str) -> dict:
    """Medidores del alimentador según el libro (RF-22). Vacío si no está (RF-23)."""
    from ..demanda_medida import DemandaError, leer_medidores, medidores_de

    if not alimentador.strip():
        raise UserError('Escriba el código de alimentador.')
    try:
        medidores = medidores_de(leer_medidores(_demanda_ruta(ws, 'medidores'), demanda_alias()),
                                 alimentador)
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    return {'alimentador': alimentador.strip(), 'medidores': medidores, 'encontrado': bool(medidores)}


def demanda_cabecera(ws: Workspace, ctx: JobContext, pares: list[tuple[str, str]]) -> dict:
    """Máxima de cada medidor en la medición de cabecera (RF-24 a RF-32). Es un trabajo:
    abrir los libros cuesta segundos (P7). Se cancela entre medidores."""
    from ..demanda_medida import DemandaError, maximas

    if not pares:
        raise UserError('Indique al menos un medidor.')
    ruta = _demanda_ruta(ws, 'cabecera')
    alias = demanda_alias()
    ctx.log(f'Medición de cabecera: {ruta.name} · {len(pares)} medidor(es)')
    try:
        res = maximas([ruta], pares, alias=alias, cancelado=ctx.cancel.is_set,
                      progreso=lambda i, n, m: ctx.progress(i, n, m))
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    for r in res:
        if r.error:
            ctx.log(f'  {r.medidor}: {r.error}')
        else:
            ctx.log(f'  {r.medidor}: kW máx {r.kw:g} el {r.fecha} ({r.libro} › {", ".join(r.hojas)})')
        for aviso in r.avisos:
            ctx.log(f'    aviso: {aviso}')
    return {'resultados': [r.to_dict() for r in res],
            'cancelado': len(res) < len(pares)}


def demanda_clientes(ws: Workspace) -> dict:
    """Clientes importantes cruzados con los suministros, sin filtrar (RF-33 a RF-37)."""
    from ..demanda_medida import DemandaError, cruzar, leer_clientes, leer_suministros

    alias = demanda_alias()
    try:
        suministros, avisos_s = leer_suministros(_demanda_ruta(ws, 'suministros'), alias)
        clientes, avisos_c = leer_clientes(_demanda_ruta(ws, 'clientes'), alias)
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    cruzados, aparte = cruzar(clientes, suministros)
    return {
        'cruzados': [c.to_dict() for c in cruzados],
        'no_cruzados': [c.to_dict() for c in aparte],
        'avisos': avisos_s + avisos_c,
        'totales': {'clientes': len(clientes), 'cruzados': len(cruzados), 'no_cruzados': len(aparte),
                    'por_actual': sum(c.cruzado_por == 'actual' for c in cruzados),
                    'por_anterior': sum(c.cruzado_por == 'anterior' for c in cruzados)},
    }


def demanda_excel(ws: Workspace, datos: dict) -> Path:
    """Excel con lo que el operador ve en pantalla (RF-38): sin estado que se desfase."""
    import time as _time

    from ..demanda_medida import escribir_excel

    destino = ws.out_dir / 'demanda_medida' / f"demanda_medida_{_time.strftime('%Y%m%d_%H%M%S')}.xlsx"
    return escribir_excel(destino, cabecera=datos.get('cabecera') or [],
                          clientes=datos.get('clientes') or [],
                          no_cruzados=datos.get('no_cruzados') or [])


# ---------------------------------------------------------------------------
# Catálogo de parámetros eléctricos
# ---------------------------------------------------------------------------


def build_catalog(ws: Workspace, ctx: JobContext, feeders: list[str] | None) -> dict:
    from ..catalog import CatalogError, auditar, escribir_catalogo
    from ..model import build_feeder_model

    wanted = set(feeders or [])
    ids = ws.dataset.feeder_ids()
    models, failed = [], 0
    for index, net in enumerate(ids, start=1):
        ctx.check_cancel()
        ctx.progress(index, len(ids), feeder_short_name(net))
        try:
            m = build_feeder_model(ws.dataset, net, strict=False, include_geography=False)
        except Exception:  # noqa: BLE001 - un alimentador malo no tumba la auditoría
            failed += 1
            continue
        if not wanted or m.name in wanted:
            models.append(m)
    if failed:
        ctx.log(f'{failed} alimentador(es) no se pudieron construir y quedan fuera del catálogo.')
    if not models:
        raise UserError('No se pudo construir ningún alimentador.')
    try:
        aud = auditar(models)
        dest = escribir_catalogo(aud, ws.out_dir / 'catalogo_parametros.xlsx',
                                 nominal_kv=models[0].nominal_kv)
    except CatalogError as exc:
        raise UserError(str(exc)) from exc
    ctx.log('--- Auditoría de parámetros eléctricos ---')
    ctx.log(aud.resumen())
    for h in aud.hallazgos:
        ctx.log('  ' + h.linea())
    return {
        'summary': aud.resumen(),
        'serious': len(aud.graves),
        'warnings': len(aud.avisos),
        'file': Path(dest).name,
        'findings': [
            {'severity': h.severidad, 'element': h.elemento, 'code': h.codigo,
             'attribute': h.atributo, 'model': h.valor_modelo, 'reference': h.valor_referencia,
             'unit': h.unidad, 'deviation_pct': h.desviacion_pct, 'km': h.km,
             'sections': h.tramos, 'message': h.mensaje}
            for h in aud.hallazgos[:500]
        ],
    }


def apply_catalog(ws: Workspace, upload: Path, preview_feeder: str | None) -> dict:
    from ..catalog import CatalogError, aplicar_correcciones, leer_catalogo

    try:
        corrections = leer_catalogo(upload)
    except CatalogError as exc:
        raise UserError(str(exc)) from exc
    if not corrections:
        raise UserError(
            'El catálogo no trae ninguna fila marcada «ficha» o «derivado» con un valor '
            'que aplicar. Escriba el valor de la ficha en «R1_ficha_ohm_km» o '
            '«ampacidad_ficha_A» y ponga «ficha» en la columna «estado».'
        )
    dest = ws.root / 'catalogo_corregido.xlsx'
    upload.replace(dest)
    with ws.lock:
        ws.catalog_file = str(dest)
        ws._corrections_cache = None
        ws.save()
    changes: list[dict] = []
    if preview_feeder and ws.dataset is not None:
        # Vista previa sobre un modelo desechable: el efecto real ocurre al convertir.
        model = build_model(ws, preview_feeder, geography=False)
        for c in aplicar_correcciones(model, corrections):
            changes.append({'line': c.linea(), 'variation_pct': c.variacion_pct,
                            'code': c.codigo, 'attribute': c.atributo_pf})
    return {'codes': sorted(corrections), 'count': len(corrections),
            'preview_feeder': preview_feeder, 'changes': changes}


def clear_catalog(ws: Workspace) -> None:
    with ws.lock:
        if ws.catalog_file:
            try:
                Path(ws.catalog_file).unlink()
            except OSError:
                pass
        ws.catalog_file = None
        ws._corrections_cache = None
        ws.save()


# ---------------------------------------------------------------------------
# Sistema completo
# ---------------------------------------------------------------------------

SYSTEM_ACTIONS = {
    'grid': ('Red unida en una sola grid', 'powerfactory'),
    'base': ('Escenario base año 0', 'powerfactory'),
    'missing-data': ('Datos que faltan para el año 0', 'engine'),
}


def script_inputs(ws: Workspace) -> list[str]:
    if ws.options.get('input_mode') == 'mdb':
        if not ws.input_path('mdb'):
            raise UserError('Elija la base .mdb de CYMDIST en el paso 1.')
        args = ['--mdb', ws.input_path('mdb')]
        if ws.input_path('equipment_mdb'):
            args += ['--equipment-mdb', ws.input_path('equipment_mdb')]
        return args
    paths = {'--red': ws.input_path('red'), '--cargas': ws.input_path('loads'),
             '--equipos': ws.input_path('equipment')}
    missing = [k for k, v in paths.items() if not v]
    if missing:
        raise UserError('Elija los tres TXT en el paso 1. Sin indicar: ' + ', '.join(missing))
    args: list[str] = []
    for key, value in paths.items():
        args += [key, value]
    return args


def system_command(ws: Workspace, action: str) -> list[str]:
    crs = ws.options['source_crs'] or 'EPSG:32718'
    args = script_inputs(ws)
    if action == 'grid':
        out = ws.out_dir / 'sistema' / 'SISTEMA.dgs'
        return [sys.executable, str(_script('build_system_grid.py')), *args,
                '--nombre', 'SISTEMA', '--out', str(out), '--source-crs', crs,
                '--importar', '--run-load-flow', '--pf-carpeta', carpeta_pf()]
    if action == 'base':
        return [sys.executable, str(_script('base_scenario.py')), *args,
                '--nombre', 'PIDE_ANIO_0', '--out-dir', str(ws.out_dir / 'anio0'),
                '--source-crs', crs]
    if action == 'missing-data':
        return [sys.executable, str(_script('base_scenario.py')), *args,
                '--solo-datos', '--out-dir', str(ws.out_dir / 'anio0')]
    raise UserError(f'Acción desconocida: {action}')


def run_system(ws: Workspace, ctx: JobContext, action: str) -> dict:
    title = SYSTEM_ACTIONS[action][0]
    ctx.log(f'--- {title} ---')
    rc = ctx.run_process(system_command(ws, action), cwd=str(project_root()))
    if rc != 0:
        ctx.log(f'El proceso devolvió el código {rc}. Causas frecuentes: PowerFactory no '
                'está abierto, u otro proceso tiene tomado su motor (solo admite uno).')
    return {'returncode': rc, 'action': action}
