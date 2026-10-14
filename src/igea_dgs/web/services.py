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
import time
import uuid
from datetime import datetime
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


def native_action_context(
    ws: Workspace, project: str, feeders: list[str], action: str,
) -> dict[str, Any]:
    """Vincula toda acción nativa con la fuente y relectura PowerFactory aceptadas."""
    from ..native_action import build_native_action_context
    from ..powerfactory_binding import (
        ProjectBindingError, project_binding_warnings, require_project_binding,
    )

    project = str(project or '').strip()
    normalized = sorted({str(feeder).strip() for feeder in feeders if str(feeder).strip()})
    if not normalized:
        normalized = sorted({
            str(feeder).strip()
            for feeder in ((ws.pf_project_bindings.get(project) or {}).get('feeders') or [])
            if str(feeder).strip()
        })
    try:
        binding = require_project_binding(ws, project, normalized)
    except ProjectBindingError as exc:
        raise UserError(str(exc)) from exc
    warnings = project_binding_warnings(ws, project, normalized)
    return build_native_action_context(
        binding, project, normalized, action, warnings=warnings,
    )


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
    from ..source_contract import audit_source

    source_audit = audit_source(dataset, loaded.provenance)
    loaded.audit = source_audit
    source_audit_dict = source_audit.as_dict()
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
    inventory['universal_audit'] = source_audit_dict
    from .readiness import build_feeder_readiness

    readiness = build_feeder_readiness(
        dataset,
        inventory['feeders'],
        loaded.provenance,
        supplied=loaded.readiness,
        aliases=aliases,
        audit=source_audit_dict,
    )
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    audit_path = ws.out_dir / 'universal_source_audit.json'
    write_json_atomic(audit_path, source_audit_dict)
    inv_path = write_inventory(inventory, ws.out_dir / 'dataset_inventory.json')
    ctx.log(format_inventory_report(inventory))
    ctx.log(f'Inventario JSON: {inv_path.name}')
    ctx.log(f'Auditoria universal: {source_audit.status} ({audit_path.name})')

    import time

    with ws.lock:
        ws.dataset = dataset
        ws.loaded_run_id = snapshot.run_id
        ws.loaded_source_mode = snapshot.mode
        ws.loaded_source_fingerprint = snapshot.fingerprint
        ws.inventory = inventory
        ws.source_audit = source_audit_dict
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
        'universal_audit': source_audit_dict,
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
            'source_audit_status': readiness.get('source_audit_status'),
            'source_audit_counts': readiness.get('source_audit_counts') or {},
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
                'capacitor_banks': list(conv.get('capacitor_banks') or []),
                'capacitor_issues': list(conv.get('capacitor_issues') or []),
                'capacitor_reread': conv.get('capacitor_reread'),
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
            assert_metre_source_crs(crs_origen_exigido(ws))
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
        source_crs=crs_origen(ws),
        target_crs=opts['target_crs'] or 'EPSG:4326',
        perfil=perfil_de(ws),
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
            ctx.log(f"  BLOQUEADO_DATOS {name}: {item.get('error') or 'error de conversión'}")
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
            # El mismo modelo que se convirtió: sin georreferenciación, la prueba de
            # conexión no exige coordenadas, y un VNR-GIS sin CRS no se descarta aquí.
            model = build_feeder_model(
                ws.dataset, feeder, aliases=aliases,
                strict=bool(ws.options.get('strict', True)),
                include_geography=bool(ws.options.get('include_geography', True)),
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
        capacitor_reread = acceptance.get('capacitor_reread')
        if capacitor_reread:
            with ws.lock:
                for conversion in ws.conversions.values():
                    if conversion.get('feeder') == feeder:
                        conversion['capacitor_reread'] = capacitor_reread
                group = ws.groups.get(feeder)
                if group is not None:
                    group['capacitor_reread'] = capacitor_reread
                ws.save()
        if metadata.get('status') == 'assigned':
            ctx.log(f"  Columna Alimentador: {metadata.get('written', 0)} objeto(s) — "
                    f"{metadata.get('by_feeder', {})}")
        elif metadata.get('status') == 'failed':
            ctx.log(f"  ERROR columna Alimentador: {metadata.get('error')}")
        proyecto = _proyecto_importado(acceptance_path)
        if proyecto:
            # 015:RF-14: también si el «Caso base» no quedó verificado, para poder
            # volver a verificarlo tras corregirlo en DIgSILENT.
            _registrar_vinculo(ws, acceptance, proyecto)
            with ws.lock:
                ws.pf_projects[feeder] = proyecto
                ws.save()
            ctx.log(f'  proyecto de PowerFactory: {proyecto}')
        if rc == 0:
            ok_n += 1
            lines.append(f'OK {feeder} → convergencia / aceptación')
        elif rc == 3:
            fail_n += 1
            lines.append(
                f'BLOQUEADO_DATOS {feeder}: API PowerFactory no disponible '
                '(abra PF o configure PF_PYTHON)'
            )
        else:
            fail_n += 1
            lines.append(f'BLOQUEADO_PERSISTENCIA {feeder}: código nativo {rc}')
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


def perfil_de(ws: Workspace):
    """Perfil de empresa activo (``config/perfil_empresa.json``), o ninguno.

    Se lee en cada conversión, no al arrancar: quien crea el perfil con la web abierta no
    tiene que reiniciarla.
    """
    from ..perfil_empresa import PerfilError, cargar_perfil

    try:
        return cargar_perfil()
    except PerfilError as exc:
        raise UserError(f'Perfil de empresa: {exc}') from exc


def perfil_info() -> dict[str, Any]:
    """El perfil activo para la interfaz; un perfil roto se informa, no tumba la página."""
    from ..perfil_empresa import PerfilError, cargar_perfil

    try:
        return {**cargar_perfil().valores(), 'error': None}
    except PerfilError as exc:
        return {'error': str(exc)}


def crs_presets() -> list[dict[str, str]]:
    """CRS sugeridos: el del perfil activo y los de ``config/perfiles``, sin repetir.

    Antes era una lista fija que empezaba por el UTM de Ica; ahora la dan los perfiles,
    y cualquier otro EPSG en metros se puede escribir a mano.
    """
    from ..perfil_empresa import PerfilError, cargar_perfil, perfil_con_nombre, perfiles_disponibles

    sugeridos: dict[str, str] = {}
    try:
        activo = cargar_perfil()
        if activo.crs_origen:
            sugeridos[activo.crs_origen] = f'Perfil activo{f" ({activo.nombre})" if activo.nombre else ""}'
    except PerfilError:
        pass
    for nombre in perfiles_disponibles():
        try:
            crs = perfil_con_nombre(nombre).crs_origen
        except PerfilError:
            continue
        if crs and crs not in sugeridos:
            sugeridos[crs] = f'Perfil {nombre}'
    return [{'code': code, 'label': label} for code, label in sugeridos.items()]


def crs_origen(ws: Workspace) -> str | None:
    """El CRS elegido en la web, o el del perfil de empresa; None si ninguno lo da."""
    return ws.options.get('source_crs') or perfil_de(ws).crs_origen


def crs_origen_exigido(ws: Workspace) -> str:
    """:func:`crs_origen`, o un error que dice cómo elegirlo (spec 002, RF-32)."""
    from ..geography import MENSAJE_FALTA_CRS

    crs = crs_origen(ws)
    if not crs:
        raise UserError(MENSAJE_FALTA_CRS)
    return crs


def reglas_de(ws: Workspace):
    """Reglas del proyecto con la hoja elegida y las convenciones del perfil de empresa."""
    from dataclasses import replace

    from ..reglas import REGLAS_PROYECTO, reglas_de_perfil

    return reglas_de_perfil(perfil_de(ws), replace(REGLAS_PROYECTO, hoja=ws.options.get('hoja')))


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
        # Las mismas opciones que un lote suelto: antes la red unida solo recibía
        # «strict» y salía siempre georreferenciada, sin Excel, sin TSV y sin mapa.
        include_geography=bool(opts['include_geography']),
        export_xlsx=bool(opts['export_xlsx']),
        export_tsv=bool(opts['export_tsv']),
        write_preview=bool(opts['write_preview']),
        source_crs=crs_origen(ws),
        target_crs=opts['target_crs'] or 'EPSG:4326',
        perfil=perfil_de(ws),
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
        ctx.log(f"BLOQUEADO_DATOS {nombre}: {man.get('error')}")
    with ws.lock:
        ws.groups[nombre] = {k: man.get(k) for k in (
            'name', 'feeders', 'status', 'error', 'dgs', 'feeder_metadata',
            'hoja', 'ties', 'completitud', 'source_run_id', 'source_mode',
            'source_fingerprint', 'reconstruction')}
        ws.groups[nombre]['preview_html'] = _rel(ws, man.get('preview_html'))
        ws.groups[nombre]['xlsx'] = _rel(ws, man.get('xlsx'))
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


#: Tiempo para que ``pf_proyectos.py`` escriba su primera línea, que sale cuando
#: PowerFactory ya ha dado el usuario (spec 005, RF-21). El arranque normal medido el
#: 2026-10-14 fue de unos 20 s; el margen cubre un equipo frío o la licencia lenta.
LIMITE_ARRANQUE_PF_S = 180.0


def pf_projects(ws: Workspace, ctx: JobContext) -> dict:
    """Proyectos de la carpeta de importación de PowerFactory y sus alimentadores (spec 005)."""
    from .jobs import TIEMPO_AGOTADO

    carpeta = carpeta_pf()
    pf_dir, interpreter = _require_pf()
    out = ws.out_dir / 'pf_proyectos.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    rc = ctx.run_process(
        [str(interpreter), str(_script('pf_proyectos.py')), '--output-json', str(out),
         '--carpeta', carpeta],
        env=pf_subprocess_env(pf_dir), cwd=str(project_root()),
        limite_arranque_s=LIMITE_ARRANQUE_PF_S,
    )
    if rc == TIEMPO_AGOTADO:
        raise UserError(
            f'PowerFactory no responde: en {LIMITE_ARRANQUE_PF_S:g} s no entregó el usuario '
            'de DIgSILENT. Suele quedar así tras cortar una sesión anterior. Cierre '
            'PowerFactory si está abierto, compruebe que no queda ningún python.exe de '
            'DIgSILENT y vuelva a leer los proyectos.')
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
    from ..powerfactory_binding import (
        ProjectBindingError, project_binding_warnings, require_project_binding,
    )

    for project in result.get('projects') or []:
        path = str(project.get('path') or project.get('name') or '')
        project['binding'] = ws.pf_project_bindings.get(path)
        try:
            require_project_binding(ws, path, project.get('feeders') or [])
        except ProjectBindingError as exc:
            project['binding_blocked_reason'] = str(exc)
            project['binding_warnings'] = []
        else:
            project['binding_blocked_reason'] = None
            project['binding_warnings'] = project_binding_warnings(
                ws, path, project.get('feeders') or [],
            )
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


def base_del_ajuste(ajuste: dict, project: str) -> dict:
    """La base de las cargas desde el resultado de un ajuste aplicado (spec 007, RF-1, RF-37).

    ``ajuste`` es el ``result`` del trabajo ``ajuste_aplicar``. Cada alimentador ajustado
    aporta su variación; el que falló o no se empezó queda fuera, con su motivo. La
    demanda que el ajuste dejó en cada SED va en ``sed``, para decir qué SED calibradas
    cambia el libro de demandas (RF-21).
    """
    if (ajuste.get('project') or '').strip() != project.strip():
        raise UserError(f"El ajuste es de {ajuste.get('project')!r}, no de {project!r}: "
                        'elija el mismo proyecto o quite la base.')
    informes = ajuste.get('informes') or ([ajuste['informe']] if ajuste.get('informe') else [])
    base = {'variaciones': [], 'feeders': [], 'ajustes': [], 'sed': {}, 'excluidos': []}
    for inf in informes:
        feeder = inf.get('feeder') or ''
        if inf.get('no_empezado'):
            base['excluidos'].append({'feeder': feeder, 'motivo': 'su ajuste no se empezó (cancelado)'})
            continue
        if inf.get('error') or inf.get('calibracion_revertida'):
            base['excluidos'].append({'feeder': feeder, 'motivo': inf.get('error')
                                      or 'su calibración no superó la relectura y se revirtió'})
            continue
        # 015:RF-26: la calibración está en el escenario de «Sin proyecto»; un ajuste de
        # antes de la spec 015 aún trae su variación, que se sigue nombrando.
        if inf.get('variacion'):
            base['variaciones'].append(inf['variacion'])
        base['feeders'].append(feeder)
        base['ajustes'].append({k: inf.get(k) for k in ('feeder', 'variacion', 'cuadrado', 'desvio',
                                                        'cabecera', 'objetivo', 'motivo')})
        for x in inf.get('sed') or []:
            despues = x.get('despues') or {}
            base['sed'][x['sed']] = {'kw': despues.get('kw'), 'kvar': despues.get('kvar'), 'feeder': feeder}
    if not base['feeders']:
        raise UserError('Ningún alimentador del ajuste quedó calibrado: no hay base. Quite la '
                        'base o vuelva a ajustar.')
    return base


def cargas_plan(
    ws: Workspace, project: str, feeders: list[str],
    demandas_file: Path | None, nuevas_file: Path | None,
    nueva: dict | None = None, economia: dict | None = None,
    ajuste: dict | None = None,
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

    if not project.strip():
        raise UserError('Elija el proyecto de DIgSILENT.')
    action_context = native_action_context(ws, project, feeders, 'cargas')
    costos, tec = _economia_del_lote(economia)
    crs = crs_origen(ws) or ''
    base = base_del_ajuste(ajuste, project) if ajuste is not None else None
    try:
        demandas = leer_demandas(demandas_file) if demandas_file is not None else None
        nuevas = leer_nuevas(nuevas_file, source_crs=crs) if nuevas_file is not None else None
        if nueva:
            nuevas = nuevas or Lectura()
            filas, errores = leer_hoja_nuevas(list(nueva), [list(nueva.values())], 'formulario',
                                              source_crs=crs, avisos=nuevas.avisos)
            # Spec 008, RF-24: primero la carga sola y después las del libro, el orden
            # del trabajo; con la misma SED en los dos, se crea la del formulario.
            nuevas.filas = filas + nuevas.filas
            nuevas.errores += errores
        if tec is not None and not (nuevas and nuevas.filas):
            raise UserError('La evaluación técnico-económica valora las cargas nuevas: '
                            'suba también el libro de cargas nuevas o use el formulario.')
        plan = armar_plan(
            project=project, feeders=feeders, demandas=demandas, nuevas=nuevas,
            costos=asdict(costos) if costos is not None else None,
            tec=None if tec is None else {'parametros': tec.to_dict(), 'comtececo': tec.a_comtececo()},
            carpeta=carpeta_pf(), base=base,
        )
        plan['native_action_context'] = action_context
        # 015:RF-17: «Sin» y «Con proyecto» solo se crean con el «Caso base» verificado.
        from ..powerfactory_binding import caso_base_verificado

        plan['caso_base_sin_verificar'] = caso_base_verificado(ws, project, feeders)
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
        'base': plan['base'], 'avisos': plan['avisos'],
        'calibradas_cambiadas': plan['calibradas_cambiadas'],
        'variacion_demandas': plan['variacion_demandas'],
        'native_action_context': action_context,
    }
    with ws.lock:
        ws.cargas_planes[token] = {'path': str(path), 'project': plan['project'],
                                   'feeders': plan['feeders'], 'applicable': plan['aplicable']}
    return resumen


def cargas_plan_de(ws: Workspace, token: str) -> dict:
    plan = ws.cargas_planes.get(token)
    # Un plan del ajuste (spec 006) comparte el registro, pero no es para cargas_pf.py.
    if plan is None or plan.get('kind') == 'ajuste_cabecera' or not Path(plan['path']).is_file():
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
    """Guarda en el espacio la fuente de ``tipo``; cabecera y clientes admiten carpeta."""
    from ..demanda_medida import EXTENSIONES, libros_de_cabecera

    if tipo == 'cabecera':
        try:
            libros = libros_de_cabecera([path])
        except Exception as exc:  # noqa: BLE001 - DemandaError o de E/S: error de usuario
            raise UserError(str(exc)) from exc
        meta = {'path': str(path), 'name': path.name, 'origin': origin,
                'source_kind': 'folder' if path.is_dir() else 'file',
                'libros': [p.name for p in libros]}
    elif tipo == 'clientes' and path.is_dir():
        # El índice se construye en un trabajo aparte: un nombre no reconocido puede
        # obligar a abrir un libro grande para buscar una fecha interna (013:RF-4).
        meta = {'path': str(path), 'name': path.name, 'origin': origin,
                'source_kind': 'folder',
                'libros': [], 'catalogo': [], 'vigente': False, 'avisos': []}
    else:
        if not path.is_file() or path.suffix.lower() not in EXTENSIONES:
            raise UserError(f'{path.name}: el {DEMANDA_ETIQUETAS[tipo]} debe ser un libro '
                            + ', '.join(EXTENSIONES))
        meta = {'path': str(path), 'name': path.name, 'origin': origin, 'source_kind': 'file'}
    with ws.lock:
        ws.demanda[tipo] = meta
        ws.save()
    return ws.public()


def _foto_fuente_clientes(path: Path) -> tuple[tuple[str, int, int], ...]:
    """Identidad observable del fichero/carpeta para detectar cambios durante el índice."""
    from ..demanda_medida import EXTENSIONES

    if path.is_file():
        rutas = [path] if path.suffix.lower() in EXTENSIONES else []
    elif path.is_dir():
        rutas = sorted(
            (p for p in path.iterdir()
             if p.is_file() and p.suffix.lower() in EXTENSIONES and not p.name.startswith('~$')),
            key=lambda p: (p.name.casefold(), p.name),
        )
    else:
        return ()
    return tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in rutas)


def demanda_clientes_indexar(ws: Workspace, ctx: JobContext) -> dict:
    """Reescanea la fuente persistida y publica un catálogo mensual sin rutas absolutas."""
    from ..demanda_medida import DemandaError, catalogar_libros_clientes

    with ws.lock:
        meta = dict(ws.demanda.get('clientes') or {})
    if not meta:
        raise UserError('Falta la fuente de clientes importantes: indique un libro o una carpeta.')
    fuente = Path(meta.get('path', ''))
    foto_inicial = _foto_fuente_clientes(fuente)
    if not foto_inicial:
        raise UserError('No hay libros de clientes importantes en la fuente elegida.')

    ctx.progress(0, len(foto_inicial), 'Leyendo nombres y meses')
    try:
        catalogo = catalogar_libros_clientes(
            fuente, perfil_de(ws).patron_libro_clientes, meta.get('asignaciones') or {})
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    ctx.check_cancel()
    foto_final = _foto_fuente_clientes(fuente)
    vigente = foto_final == foto_inicial
    avisos = [] if vigente else [
        'La carpeta cambió mientras se construía el índice; pulse «Actualizar índice» antes de usarla.'
    ]
    publico = [{
        'nombre': libro.nombre,
        'mes': libro.mes,
        'origen_mes': libro.origen_mes,
        'activo': libro.activo,
        'avisos': list(libro.avisos),
    } for libro in catalogo]

    with ws.lock:
        actual = ws.demanda.get('clientes') or {}
        if actual.get('path') != str(fuente):
            raise UserError('La fuente de clientes cambió durante el índice; vuelva a actualizarla.')
        actual.update({
            'libros': [libro.nombre for libro in catalogo],
            'catalogo': publico,
            'vigente': vigente,
            'avisos': avisos,
            'indexado_en': time.time(),
        })
        ws.save()
    ctx.progress(len(catalogo), len(catalogo), f'{len(catalogo)} libro(s)')
    return {'catalogo': publico, 'vigente': vigente, 'avisos': avisos}


def demanda_quitar(ws: Workspace, tipo: str) -> dict:
    import shutil

    with ws.lock:
        ws.demanda.pop(tipo, None)
        ws.save()
    shutil.rmtree(demanda_carpeta(ws, tipo), ignore_errors=True)
    return ws.public()


def _demanda_ruta(ws: Workspace, tipo: str, *, periodo: str | None = None) -> Path:
    meta = ws.demanda.get(tipo)
    if not meta or not Path(meta['path']).exists():
        raise UserError(f'Falta el {DEMANDA_ETIQUETAS[tipo]}: súbalo o indique su ruta.')
    path = Path(meta['path'])
    if tipo == 'clientes' and path.is_dir():
        if not meta.get('vigente'):
            raise UserError('Actualice el índice de clientes importantes antes de usar la carpeta.')
        activos = [x for x in meta.get('catalogo') or [] if x.get('activo')]
        if periodo:
            activos = [x for x in activos if str(x.get('mes') or '').strip() == periodo]
        if len(activos) != 1:
            detalle = f' para el periodo {periodo}' if periodo else ''
            raise UserError(
                f'La carpeta tiene {len(activos)} libros mensuales activos{detalle}; '
                'elija un mes (debe existir uno solo) para cruzar clientes.')
        elegido = path / activos[0]['nombre']
        if not elegido.is_file():
            raise UserError('El libro indexado ya no existe; pulse «Actualizar índice».')
        return elegido
    return path


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


def demanda_alimentadores(ws: Workspace) -> dict:
    """Alimentadores del libro de medidores, para el desplegable del código (RF-42)."""
    from ..demanda_medida import DemandaError, alimentadores_de, leer_medidores

    try:
        return {'alimentadores': alimentadores_de(
            leer_medidores(_demanda_ruta(ws, 'medidores'), demanda_alias()))}
    except DemandaError as exc:
        raise UserError(str(exc)) from exc


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
    # La curva no va en el resultado, que viaja entero por el WebSocket: se guarda aparte
    # y se pide reducida (spec 006, RF-31 y RF-39).
    with ws.lock:
        ws.curvas_cabecera = {ctx.job.id: {r.medidor: {'curva': r.curva, 'fuera': r.fuera_de_curva}
                                           for r in res if r.curva}}
    return {'resultados': [r.to_dict() for r in res],
            'cancelado': len(res) < len(pares)}


# Puntos de la curva que se envían a la web: con ~1 000 px de gráfica, más no se distinguen.
CURVA_MAX_PUNTOS = 2000


def demanda_curva(ws: Workspace, job_id: str, medidor: str, desde: datetime | None = None,
                  hasta: datetime | None = None) -> dict:
    """Curva de un medidor de la última máxima buscada, entera o por tramo (spec 006,
    RF-31, RF-32, RF-35, RF-38, RF-39). ``LookupError`` si no está: la API da 404."""
    from ..demanda_medida import clave_codigo, reducir_curva

    with ws.lock:
        curvas = ws.curvas_cabecera.get(job_id)
    if curvas is None:
        raise LookupError('La curva no es de la última máxima buscada: vuelva a buscarla.')
    clave = clave_codigo(medidor)
    nombre = next((m for m in curvas if m == medidor), None) or         next((m for m in curvas if clave_codigo(m) == clave), None)
    if nombre is None:
        raise LookupError(f'El medidor {medidor} no tiene curva en la última máxima buscada.')
    curva = curvas[nombre]['curva']
    tramo = reducir_curva(curva, desde, hasta, max_puntos=len(curva) or 1)
    puntos = reducir_curva(tramo, max_puntos=CURVA_MAX_PUNTOS)
    pico = max(curva, key=lambda p: p[1])
    return {'medidor': nombre, 'inicio': curva[0][0].isoformat(), 'fin': curva[-1][0].isoformat(),
            'maxima': {'fecha': pico[0].isoformat(), 'kw': pico[1]},
            'puntos': [[f.isoformat(), kw, kvar] for f, kw, kvar in puntos],
            'total': len(tramo), 'reducida': len(puntos) < len(tramo),
            'fuera_de_curva': curvas[nombre]['fuera']}


def demanda_clientes(ws: Workspace, alimentadores: list[str] | None = None,
                     *, periodo: str | None = None) -> dict:
    """Clientes importantes cruzados con los suministros (RF-33 a RF-37); con
    ``alimentadores``, solo los de esos alimentadores por su radial (RF-43)."""
    from ..demanda_medida import (DemandaError, cruzar, del_alimentador, leer_clientes,
                                  leer_suministros)

    alias = demanda_alias()
    try:
        suministros, avisos_s = leer_suministros(_demanda_ruta(ws, 'suministros'), alias)
        clientes, avisos_c = leer_clientes(
            _demanda_ruta(ws, 'clientes', periodo=periodo), alias,
        )
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    cruzados, aparte = cruzar(clientes, suministros)
    alimentadores = [a.strip() for a in alimentadores or [] if a.strip()]
    de_otros = 0
    if alimentadores:
        cruzados, aparte, de_otros = del_alimentador(cruzados, aparte, alimentadores)
    return {
        'alimentadores': alimentadores,
        'cruzados': [c.to_dict() for c in cruzados],
        'no_cruzados': [c.to_dict() for c in aparte],
        'avisos': avisos_s + avisos_c,
        'totales': {'clientes': len(clientes), 'cruzados': len(cruzados), 'no_cruzados': len(aparte),
                    'por_actual': sum(c.cruzado_por == 'actual' for c in cruzados),
                    'por_anterior': sum(c.cruzado_por == 'anterior' for c in cruzados),
                    'de_otros': de_otros},
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
# Ajuste a la máxima de cabecera (spec 006)
# ---------------------------------------------------------------------------


def _kva_de_la_entrada(ws: Workspace, alimentador: str) -> tuple[dict[str, float], str]:
    """kVA de cada SED del alimentador en la entrada cargada (RF-10), y un aviso si no hay.

    Es el mismo modelo que da el DGS, con sus reglas: el kVA que DIgSILENT debería tener.
    El código del libro de medidores puede venir escrito de otra forma que el de la
    entrada («PA217» y «pa-217»): se compara con ``clave_codigo``.
    """
    from ..demanda_medida import clave_codigo

    if ws.dataset is None:
        return {}, ('Sin fuente canónica activa cargada: las SED sin transformador en '
                    'DIgSILENT no tendrán de dónde sacar su kVA.')
    clave = clave_codigo(alimentador)
    feeder = next((f for f in ws.dataset.feeder_ids() if clave_codigo(f) == clave), None)
    if feeder is None:
        return {}, f'{alimentador} no está en la entrada cargada: no hay kVA de respaldo.'
    try:
        modelo = build_model(ws, feeder, geography=False)
    except UserError as exc:
        return {}, f'{exc} No hay kVA de respaldo.'
    return {sed.code: float(sed.design_kva) for sed in modelo.seds if sed.design_kva}, ''


def periodo_clientes_activo(ws: Workspace, periodo: str | None = None):
    """Evidencia del libro activo; con ``periodo`` elige exactamente el mes de la máxima."""
    import hashlib

    from ..demanda_medida import ClientPeriodEvidence, catalogar_libros_clientes

    meta = dict(ws.demanda.get('clientes') or {})
    if not meta:
        return ClientPeriodEvidence(
            status='NO_CLIENT_BOOK', period=None, file=None, sheet=None,
            fingerprint=None, period_origin=None,
            warning='Sin libro de clientes importantes: todas las SED se escalan por kVA.',
        )
    source = Path(str(meta.get('path') or ''))
    if not source.exists():
        return ClientPeriodEvidence(
            status='CLIENT_PERIOD_UNKNOWN', period=None, file=source.name or None,
            sheet='resumen', fingerprint=None, period_origin=None,
            warning='La fuente activa de clientes importantes ya no existe.',
        )
    catalog = list(meta.get('catalogo') or [])
    if not catalog:
        try:
            catalog = [dict(vars(item)) for item in catalogar_libros_clientes(
                source, perfil_de(ws).patron_libro_clientes, meta.get('asignaciones') or {},
            )]
        except Exception as exc:  # noqa: BLE001 - se convierte en evidencia bloqueante
            return ClientPeriodEvidence(
                status='CLIENT_PERIOD_UNKNOWN', period=None, file=source.name,
                sheet='resumen', fingerprint=None, period_origin=None, warning=str(exc),
            )
    active = [item for item in catalog if item.get('activo')]
    if periodo:
        matching = [item for item in active if str(item.get('mes') or '').strip() == periodo]
        # Con un único libro conservamos su mes real para emitir MISMATCH; con una
        # carpeta multimensual solo es válida la coincidencia exacta.
        active = matching or (active if len(active) == 1 else [])
    if len(active) != 1:
        detalle = f' para {periodo}' if periodo else ''
        return ClientPeriodEvidence(
            status='CLIENT_PERIOD_UNKNOWN', period=None, file=None, sheet='resumen',
            fingerprint=None, period_origin=None,
            warning=(f'La fuente tiene {len(active)} libros activos{detalle}; '
                     'debe existir uno solo.'),
        )
    chosen = active[0]
    path = source if source.is_file() else source / str(chosen.get('nombre') or '')
    if not path.is_file():
        return ClientPeriodEvidence(
            status='CLIENT_PERIOD_UNKNOWN', period=None, file=path.name or None,
            sheet='resumen', fingerprint=None,
            period_origin=str(chosen.get('origen_mes') or '') or None,
            warning='El libro activo de clientes importantes ya no existe.',
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    period = str(chosen.get('mes') or '').strip() or None
    return ClientPeriodEvidence(
        status='CLIENT_PERIOD_VERIFIED' if period else 'CLIENT_PERIOD_UNKNOWN',
        period=period, file=path.name, sheet='resumen', fingerprint=digest,
        period_origin=str(chosen.get('origen_mes') or '') or None,
        warning=None if period else 'El libro activo no tiene un mes demostrable.',
    )


def _periodo_clientes_para_maxima(ws: Workspace, periodo: str | None):
    """Invoca el contrato mensual conservando extensiones antiguas de un solo argumento."""
    import inspect

    parameters = inspect.signature(periodo_clientes_activo).parameters
    if 'periodo' not in parameters:
        return periodo_clientes_activo(ws)
    return periodo_clientes_activo(ws, periodo)


def _medidores_del_ajuste(maximas: list[dict], medidor: str, medidores: list[str] | None) -> list[dict]:
    """Las filas de la máxima que se ajustan: una por alimentador (spec 008, RF-12, RF-13).

    Con ``medidores``, esos, en su orden. Con ``medidor``, ese solo (spec 006). Sin
    ninguno, todas las filas con medidor, si cada alimentador tiene una.
    """
    filas = [m for m in maximas if m.get('medidor')]
    if not filas:
        raise UserError('Busque antes la máxima de cabecera.')
    pedidos = [m.strip() for m in (medidores or []) if m.strip()]
    if not pedidos and medidor.strip():
        pedidos = [medidor.strip()]
    if pedidos:
        por_medidor = {m['medidor']: m for m in filas}
        faltan = [m for m in dict.fromkeys(pedidos) if m not in por_medidor]
        if faltan:
            raise UserError(f"{', '.join(faltan)} no está entre los medidores de la máxima buscada.")
        filas = [por_medidor[m] for m in dict.fromkeys(pedidos)]
    por_alim: dict[str, list[str]] = {}
    for m in filas:
        por_alim.setdefault(str(m.get('alimentador') or '').strip(), []).append(m['medidor'])
    dobles = {a: ms for a, ms in por_alim.items() if len(ms) > 1}
    if dobles:
        # RF-13: con dos medidores para un alimentador no se sabe cuál es su cabecera.
        a, ms = next(iter(dobles.items()))
        quien = f'{a} tiene' if a else 'La máxima tiene'
        raise UserError(f"{quien} {', '.join(ms)}: elija el medidor de la cabecera.")
    return filas


def ajuste_plan(ws: Workspace, project: str, maximas: list[dict], medidor: str,
                tolerancia: float, medidores: list[str] | None = None,
                desconectados: list[str] | None = None) -> dict:
    """Plan para ``tools/ajuste_cabecera_pf.py`` (spec 006, RF-1 a RF-3, RF-10).

    ``maximas`` es el resultado del trabajo de la máxima de cabecera que el operador ve
    en su tabla: el objetivo es ese mismo valor (RF-1), sin volver a abrir los libros de
    cabecera, que pesan cientos de MB. Con varios alimentadores (spec 008, RF-12) hay un
    plan por alimentador, el mismo JSON de la spec 006, y un solo token que los recorre.
    ``desconectados`` son los Nis que el operador desmarcó en la tabla del cruce (RF-26):
    van aparte en el plan, y el guion decide qué carga de SED se queda sin clientes.
    """
    import time as _time

    from ..ajuste_cabecera import AjusteError, fijas_de, objetivo_de
    from ..demanda_medida import periodo_de_fecha
    from ..powerfactory_binding import PowerFactoryProjectBinding, caso_base_verificado

    if not project.strip():
        raise UserError('Elija el proyecto de DIgSILENT.')
    filas = _medidores_del_ajuste(maximas, medidor, medidores)
    requested_feeders = [str(row.get('alimentador') or '').strip() for row in filas]
    action_context = native_action_context(ws, project, requested_feeders, 'ajuste')
    project_binding = PowerFactoryProjectBinding.from_dict(action_context['binding'])
    varios = len(filas) > 1
    stamp = _time.strftime('%Y%m%d_%H%M%S')
    ws.plans_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    fuera = {str(c).strip() for c in desconectados or [] if str(c).strip()}
    ajustes, avisos, paths = [], [], []
    # 015:RF-13, RF-15: sin «Caso base» verificado no se calibra; con varios, los demás sí.
    sin_verificar = caso_base_verificado(ws, project, requested_feeders)
    for fila in filas:
        alim_fila = str(fila.get('alimentador') or '').strip()
        if alim_fila in sin_verificar:
            motivo = (f"{alim_fila}: su «Caso base» no está verificado "
                      f"({', '.join(sin_verificar[alim_fila])}); verifíquelo en el paso 1.1.")
            if not varios:
                raise UserError(motivo)
            avisos.append(motivo + ' No se calibra.')
            continue
        try:
            objetivo = objetivo_de(fila)
        except AjusteError as exc:
            if not varios:
                raise UserError(str(exc)) from exc
            # RF-14: un medidor sin máxima no impide ajustar los demás alimentadores.
            avisos.append(f"{fila.get('alimentador') or fila['medidor']}: no se ajusta. {exc}")
            continue
        alimentador = objetivo.alimentador.strip()
        if not alimentador:
            raise UserError(f'{objetivo.medidor}: la máxima no dice de qué alimentador es.')
        pre = f'{alimentador}: ' if varios else ''
        maximum_period = periodo_de_fecha(objetivo.fecha)
        client_period = _periodo_clientes_para_maxima(ws, maximum_period)
        if client_period.status != 'NO_CLIENT_BOOK':
            if maximum_period is None:
                raise UserError(
                    f'MAXIMUM_PERIOD_UNKNOWN: {objetivo.medidor} no tiene una fecha '
                    'que demuestre el mes de la máxima.'
                )
            if client_period.period is None:
                raise UserError(
                    'CLIENT_PERIOD_UNKNOWN: '
                    + (client_period.warning or 'el libro activo no demuestra su mes')
                )
            if maximum_period != client_period.period:
                raise UserError(
                    f'CLIENT_PERIOD_MISMATCH: la máxima es {maximum_period} y el libro '
                    f'{client_period.file} es {client_period.period}.'
                )
            period_evidence = {
                'status': 'CLIENT_PERIOD_MATCH', 'maxima': maximum_period,
                'clientes': client_period.period,
            }
        else:
            period_evidence = {
                'status': 'NO_CLIENT_BOOK', 'maxima': maximum_period, 'clientes': None,
            }
            if client_period.warning and client_period.warning not in avisos:
                avisos.append(client_period.warning)
        clientes: list[dict] = []
        if ws.demanda.get('suministros') and ws.demanda.get('clientes'):
            clientes = demanda_clientes(
                ws, [alimentador], periodo=maximum_period,
            )['cruzados']
        elif not paths:
            avisos.append('Sin libros de suministros y de clientes: todas las SED se reparten por kVA.')
        apagados = [c for c in clientes if str(c.get('codigo') or '').strip() in fuera]
        clientes = [c for c in clientes if str(c.get('codigo') or '').strip() not in fuera]
        fixed = fijas_de(clientes, objetivo)
        fixed_evidence = [{
            'sed': item.sed, 'p_kw': item.kw, 'q_kvar': item.kvar, 'fp': item.fp,
            'clientes': list(item.clientes), 'derivaciones': list(item.derivaciones),
            'avisos': list(item.avisos),
        } for item in fixed.values()]
        for item in fixed.values():
            avisos.extend(pre + warning for warning in item.avisos if pre + warning not in avisos)
        kva_entrada, aviso = _kva_de_la_entrada(ws, alimentador)
        if aviso:
            avisos.append(pre + aviso)
        plan = {
            'schema': 'igea-dgs-ajuste-cabecera-v2', 'project': project.strip(),
            'folder': carpeta_pf(), 'feeder': alimentador, 'stamp': stamp,
            'source': {
                'source_run_id': project_binding.source_run_id,
                'source_mode': project_binding.source_mode,
                'source_fingerprint': project_binding.source_fingerprint,
            },
            'project_binding': project_binding.as_dict(),
            'native_action_context': native_action_context(
                ws, project, [alimentador], 'ajuste',
            ),
            'periodo': period_evidence,
            'client_evidence': client_period.to_dict(),
            'fixed_load_evidence': fixed_evidence,
            'variacion': f'Ajuste_{alimentador}_{stamp}',
            'objetivo': {'kw': objetivo.kw, 'kvar': objetivo.kvar, 'medidor': objetivo.medidor,
                         'alimentador': alimentador, 'fecha': objetivo.fecha},
            'clientes': clientes, 'desconectados': apagados, 'kva_entrada': kva_entrada,
            'tolerancia': tolerancia,
            'caso_base_sin_verificar': {},
            # 014:RF-10: la demanda que dejó la última calibración, para ver lo manual.
            'ultima_calibracion': (ws.calibraciones.get(project.strip()) or {}).get(alimentador),
        }
        nombre = (f'ajuste_cabecera_{token}.json' if not varios
                  else f'ajuste_cabecera_{token}_{len(paths) + 1}.json')
        path = ws.plans_dir / nombre
        path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        paths.append(str(path))
        ajustes.append({'feeder': alimentador, 'objetivo': plan['objetivo'],
                        'n_clientes': len(clientes), 'n_desconectados': len(apagados),
                        'n_sed_fijas': len(fixed_evidence),
                        'n_sed_escaladas_estimadas': max(0, len(kva_entrada) - len(fixed_evidence)),
                        'n_kva_entrada': len(kva_entrada), 'periodo': period_evidence,
                        'client_evidence': client_period.to_dict()})
    if not ajustes:
        raise UserError('Ningún alimentador se puede calibrar. ' + ' '.join(avisos))
    feeders = [a['feeder'] for a in ajustes]
    with ws.lock:
        ws.cargas_planes[token] = {'path': paths[0], 'paths': paths, 'project': project.strip(),
                                   'feeders': feeders, 'applicable': True,
                                   'kind': 'ajuste_cabecera'}
    primero = ajustes[0]
    return {'token': token, 'project': project.strip(), 'feeder': primero['feeder'],
            'objetivo': primero['objetivo'], 'tolerancia': tolerancia,
            'n_clientes': primero['n_clientes'], 'n_kva_entrada': primero['n_kva_entrada'],
            'n_sed_fijas': primero['n_sed_fijas'],
            'n_sed_escaladas_estimadas': primero['n_sed_escaladas_estimadas'],
            'periodo': primero['periodo'], 'client_evidence': primero['client_evidence'],
            'source': plan['source'], 'project_binding': plan['project_binding'],
            'native_action_context': action_context,
            'feeders': feeders, 'ajustes': ajustes, 'avisos': avisos}


def _guardar_calibracion(ws: Workspace, project: str, feeder: str, informe: dict) -> None:
    """La demanda que dejó la calibración en cada SED (015, T8; 014:RF-10).

    Sin error y sin revertir: una calibración que no quedó en el escenario no es con la
    que comparar lo que cambie el operador.
    """
    if informe.get('error') or informe.get('calibracion_revertida') or not informe.get('sed'):
        return
    sed = {x['sed']: [(x.get('despues') or {}).get('kw'), (x.get('despues') or {}).get('kvar')]
           for x in informe['sed'] if (x.get('despues') or {}).get('kw') is not None}
    with ws.lock:
        ws.calibraciones.setdefault(project.strip(), {})[feeder] = {
            'nombre': f"la calibración del {informe.get('stamp') or time.strftime('%Y-%m-%d %H:%M')}",
            'sed': sed, 'cuadrado': bool(informe.get('cuadrado')),
            'escenario': informe.get('escenario'), 'recorded_at': time.time()}
        ws.save()


def ajuste_ejecutar(ws: Workspace, ctx: JobContext, token: str, *, simular: bool) -> dict:
    """Simula o aplica el ajuste con ``tools/ajuste_cabecera_pf.py`` (RF-19 a RF-22).

    Como las cargas: cancelar no mata el guion, se le avisa con un fichero y termina el
    flujo en curso, dejando la variación con el último reparto que convergió (RF-22).
    Con varios alimentadores (spec 008) se lanzan uno tras otro: el que falla queda en su
    informe y se sigue con el siguiente (RF-14); cancelar no empieza otro (RF-15).
    """
    plan = ws.cargas_planes.get(token)
    if plan is None or plan.get('kind') != 'ajuste_cabecera':
        raise UserError('El plan del ajuste ya no existe: vuelva a prepararlo.')
    paths = plan.get('paths') or [plan['path']]
    if not all(Path(p).is_file() for p in paths):
        raise UserError('El plan del ajuste ya no existe: vuelva a prepararlo.')
    pf_dir, interpreter = _require_pf()
    modo = 'simulacion' if simular else 'aplicacion'
    flag = ws.plans_dir / f'cancelar_{token}.flag'
    flag.unlink(missing_ok=True)
    varios = len(paths) > 1
    informes, reports, codigos = [], [], []
    for n, (path, feeder) in enumerate(zip(paths, plan['feeders'])):
        if ctx.cancel.is_set() or flag.exists():
            resto = plan['feeders'][n:]
            ctx.log(f"Cancelado: no se empezó {', '.join(resto)}.")
            informes += [{'project': plan['project'], 'feeder': f, 'cancelado': True,
                          'no_empezado': True, 'avisos': ['Cancelado antes de empezar.']}
                         for f in resto]
            break
        if varios:
            ctx.progress(n, len(paths), feeder)
        sufijo = f'_{n + 1}' if varios else ''
        report = ws.out_dir / f'ajuste_cabecera_{modo}_{token}{sufijo}.json'
        report.parent.mkdir(parents=True, exist_ok=True)
        report.unlink(missing_ok=True)
        ctx.log(f"Proyecto de DIgSILENT: {plan['project']}  ·  alimentador {feeder}")
        cmd = [str(interpreter), str(_script('ajuste_cabecera_pf.py')), '--plan', path,
               '--output-json', str(report), '--cancel-file', str(flag)]
        if simular:
            cmd.append('--simular')
        rc = ctx.run_process(cmd, env=pf_subprocess_env(pf_dir), cwd=str(project_root()),
                             cancel_file=flag)
        if rc == 3:
            flag.unlink(missing_ok=True)
            raise UserError('No se pudo conectar con DIgSILENT. Ábralo y reintente.')
        try:
            informe = json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
        except (OSError, ValueError):
            informe = {}
        if not informe:
            informe = {'error': f'El guion terminó con el código {rc} sin dejar informe: vea el Registro.'}
        informe.setdefault('feeder', feeder)
        informe.setdefault('project', plan['project'])
        if informe.get('error'):
            ctx.log(f"{feeder}: {informe['error']}")
        elif not simular and not informe.get('cuadrado'):
            ctx.log(f"{feeder}: no cumple la tolerancia: {informe.get('motivo')}. Vea el diagnóstico.")
        if not simular:
            _guardar_calibracion(ws, plan['project'], feeder, informe)
        informes.append(informe)
        reports.append(report.name)
        codigos.append(rc)
    flag.unlink(missing_ok=True)
    errores = [i for i in informes if i.get('error')]
    if errores and len(errores) == len(informes):
        raise UserError(' · '.join(f"{i['feeder']}: {i['error']}" if varios else i['error']
                                   for i in errores))
    hechos = [i for i in informes if not i.get('no_empezado')]
    return {'returncode': max(codigos, default=0), 'modo': hechos[0].get('modo') if hechos else None,
            'report': reports[0] if reports else '', 'reports': reports,
            'project': plan['project'], 'feeders': plan['feeders'],
            'informe': informes[0], 'informes': informes}


def _registrar_vinculo(ws: Workspace, acceptance: dict, proyecto: str) -> None:
    """Guarda el vínculo del informe de aceptación, con el estado de su «Caso base».

    Se guarda aunque el «Caso base» no quede verificado (015:RF-14) y se fusiona con el
    estado de los alimentadores verificados antes en el mismo proyecto.
    """
    binding_payload = acceptance.get('project_binding')
    if not binding_payload:
        return
    from ..powerfactory_binding import (
        PowerFactoryProjectBinding, fusionar_caso_base, record_project_binding,
    )

    binding = PowerFactoryProjectBinding.from_dict(binding_payload)
    if binding.project != proyecto:
        raise UserError('PROJECT_BINDING_PROJECT_MISMATCH: el informe nativo no '
                        'corresponde al proyecto importado.')
    record_project_binding(ws, fusionar_caso_base(ws.pf_project_bindings.get(proyecto), binding))


def pf_verificar_base(ws: Workspace, ctx: JobContext, project: str, feeders: list[str]) -> dict:
    """Verifica el «Caso base» de un proyecto ya importado (spec 015, RF-1 a RF-14).

    Es la aceptación nativa sobre el proyecto existente, sin volver a importar: GPS y
    trazado frente a la geografía del archivo original, conectividad, diagrama,
    capacidades, y grupo de conexión y tensión de baja de los transformadores (que se
    corrigen). Sin flujo: la convergencia se prueba al importar el DGS, con el oráculo
    antes (RF-8, RF-39, RF-41). Se puede repetir tras corregir en DIgSILENT (RF-14). Uno a
    uno: un alimentador sin verificar no impide verificar los demás.
    """
    project = project.strip()
    if not project:
        raise UserError('Elija el proyecto de DIgSILENT.')
    bound = (ws.pf_project_bindings.get(project) or {}).get('feeders') or []
    pedidos = list(dict.fromkeys(f.strip() for f in feeders if f.strip())) or list(bound)
    if not pedidos:
        raise UserError('Elija los alimentadores cuyo «Caso base» quiere verificar.')
    jobs, missing = dgs_jobs(ws, pedidos)
    if not jobs:
        raise UserError('Para verificar hace falta el DGS convertido de cada alimentador. Faltan: '
                        + ', '.join(f'{f}.dgs' for f in missing[:12]))
    source_evidence = check_powerfactory_source_run(ws, [f for f, _d, _g in jobs])
    pf_dir, interpreter = _require_pf()
    script = _script('powerfactory_acceptance.py')
    resultados: list[dict] = [{'feeder': f, 'status': 'NO_VERIFICADO',
                               'motivo': 'no hay DGS convertido'} for f in missing]
    for index, (feeder, dgs, geo) in enumerate(jobs, start=1):
        ctx.check_cancel()
        ctx.progress(index - 1, len(jobs), feeder)
        if geo is None:
            resultados.append({'feeder': feeder, 'status': 'NO_VERIFICADO',
                               'motivo': 'convertido sin georreferenciación: no hay con qué '
                                         'comparar el GPS (015:RF-1)'})
            continue
        report = ws.out_dir / f'{feeder}_caso_base.json'
        report.unlink(missing_ok=True)
        cmd = [str(interpreter), str(script), '--existing-project', project,
               '--pf-carpeta', carpeta_pf(), '--source-dgs', str(dgs), '--manifest', str(geo),
               '--feeder-metadata', str(dgs.with_name(f'{dgs.stem}_feeder_metadata.json')),
               # 015:RF-39: sin flujo; la convergencia se probó al importar el DGS.
               '--require-diagram',
               '--source-run-id', source_evidence['source_run_id'],
               '--source-mode', source_evidence['source_mode'],
               '--source-fingerprint', source_evidence['source_fingerprint'],
               '--output-json', str(report),
               '--output-txt', str(report.with_suffix('.txt'))]
        target = next((t for t in source_evidence['targets'] if t['target'] == feeder), {})
        if target.get('reconstruction'):
            cmd += ['--reconstruction-report', str(ws.out_dir / target['reconstruction']['report']),
                    '--reconstruction-report-sha256', target['reconstruction']['report_sha256']]
        ctx.log(f'[{index}/{len(jobs)}] Verificar el «Caso base» de {feeder} en {project}…')
        rc = ctx.run_process(cmd, env=pf_subprocess_env(pf_dir), cwd=str(project_root()))
        if rc == 3:
            raise UserError('No se pudo conectar con DIgSILENT. Ábralo y reintente.')
        try:
            acceptance = json.loads(report.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            resultados.append({'feeder': feeder, 'status': 'NO_VERIFICADO',
                               'motivo': f'el guion terminó con el código {rc} sin informe'})
            continue
        _registrar_vinculo(ws, acceptance, project)
        caso = acceptance.get('caso_base') or {}
        ctx.log(f"  {feeder}: {caso.get('status') or 'NO_VERIFICADO'}")
        for aviso in caso.get('avisos') or []:
            ctx.log(f'    {aviso}')
        resultados.append({'feeder': feeder, 'status': caso.get('status') or 'NO_VERIFICADO',
                           'comprobaciones': caso.get('comprobaciones') or {},
                           'avisos': caso.get('avisos') or [],
                           'transformadores_corregidos': caso.get('transformadores_corregidos') or [],
                           'report': report.name})
    ctx.progress(len(jobs), len(jobs), 'listo')
    return {'project': project, 'feeders': resultados}


def pf_verificar(ws: Workspace, ctx: JobContext, project: str, feeders: list[str]) -> dict:
    """Convergencia del proyecto con lo que tenga activo (spec 008, RF-18, RF-19).

    No escribe en el proyecto: el guion solo ejecuta el flujo de carga y lee la cabecera
    de cada alimentador.
    """
    if not project.strip():
        raise UserError('Elija el proyecto de DIgSILENT.')
    feeders = list(dict.fromkeys(f.strip() for f in feeders if f.strip()))
    action_context = native_action_context(ws, project, feeders, 'verificar')
    pf_dir, interpreter = _require_pf()
    token = uuid.uuid4().hex[:12]
    ws.plans_dir.mkdir(parents=True, exist_ok=True)
    path = ws.plans_dir / f'verificar_{token}.json'
    path.write_text(json.dumps({'project': project.strip(), 'folder': carpeta_pf(),
                                'feeders': feeders,
                                'native_action_context': action_context},
                               ensure_ascii=False), encoding='utf-8')
    report = ws.out_dir / f'verificar_{token}.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    ctx.log(f'Proyecto de DIgSILENT: {project.strip()}  ·  verificar la convergencia')
    rc = ctx.run_process([str(interpreter), str(_script('verificar_pf.py')), '--plan', str(path),
                          '--output-json', str(report)],
                         env=pf_subprocess_env(pf_dir), cwd=str(project_root()))
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
    return {'returncode': rc, 'report': report.name, 'project': project.strip(),
            'informe': informe}


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
    crs = crs_origen_exigido(ws)
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


# ---------------------------------------------------------------------------
# Obras, estudios y transferencia sobre la red calibrada (spec 011)
# ---------------------------------------------------------------------------

#: Límite de cada estudio en cada caso si el operador no da otro (RF-39). Cada estudio va
#: en su proceso: un contingencias colgado cuesta ese estudio y no el resto (RF-40).
LIMITE_ESTUDIO_S = 1800.0


def _guion_pf(ws: Workspace, ctx: JobContext, script: str, plan: dict, *, nombre: str,
              args: tuple[str, ...] = (), cancelable: bool = True,
              limite_s: float | None = None) -> tuple[int, dict, Path]:
    """Escribe el plan, ejecuta el guion de DIgSILENT y lee su informe.

    Es lo mismo que hacen el ajuste y las cargas, una vez para los guiones de la spec 011.
    Con ``cancelable``, cancelar le avisa con un fichero y el guion termina lo que tiene en
    curso; sin él, cancelar lo termina. Pasado ``limite_s``, el informe dice que no terminó.
    """
    from .jobs import TIEMPO_AGOTADO

    pf_dir, interpreter = _require_pf()
    token = uuid.uuid4().hex[:12]
    ws.plans_dir.mkdir(parents=True, exist_ok=True)
    ruta_plan = ws.plans_dir / f'{nombre}_{token}.json'
    ruta_plan.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    report = ws.out_dir / f'{nombre}_{token}.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(interpreter), str(_script(script)), '--plan', str(ruta_plan),
           '--output-json', str(report), *args]
    flag = ws.plans_dir / f'cancelar_{token}.flag' if cancelable else None
    if flag is not None:
        cmd += ['--cancel-file', str(flag)]
    rc = ctx.run_process(cmd, env=pf_subprocess_env(pf_dir), cwd=str(project_root()),
                         cancel_file=flag, limite_s=limite_s)
    if flag is not None:
        flag.unlink(missing_ok=True)
    if rc == 3:
        raise UserError('No se pudo conectar con DIgSILENT. Ábralo y reintente.')
    if rc == TIEMPO_AGOTADO:
        return rc, {'no_terminado': True,
                    'error': f'no terminó en su límite de {limite_s:g} s'}, report
    try:
        informe = json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
    except (OSError, ValueError):
        informe = {}
    if not informe:
        informe = {'error': f'El guion terminó con el código {rc} sin dejar informe: vea el Registro.'}
    return rc, informe, report


# ------------------------------------------------------------------ obras (RF-95)
def obra_anadir(ws: Workspace, datos: dict) -> dict:
    """Valida una obra del formulario y la guarda en el espacio hasta aplicarla (RF-70, RF-95)."""
    from ..obras_pf import ObrasError, validar_obra

    try:
        obra = validar_obra(datos)
    except ObrasError as exc:
        raise UserError(str(exc)) from exc
    fila = {'id': uuid.uuid4().hex[:10], **obra.a_dict()}
    with ws.lock:
        ws.obras.append(fila)
        ws.save()
    return fila


def obra_quitar(ws: Workspace, obra_id: str) -> None:
    with ws.lock:
        quedan = [o for o in ws.obras if o['id'] != obra_id]
        if len(quedan) == len(ws.obras):
            raise UserError('Esa obra ya no está en el espacio.')
        ws.obras = quedan
        ws.save()


def obras_bibliotecas(ws: Workspace, ctx: JobContext, project: str, feeders: list[str],
                      otro_proyecto: str = '', clases: list[str] | None = None) -> dict:
    """Alimentadores y tipos de las tres bibliotecas para el formulario (RF-88 a RF-94).

    La lectura queda en el espacio para no volver a abrir DIgSILENT al cambiar de obra.
    """
    if not project.strip():
        raise UserError('Elija el proyecto de DIgSILENT.')
    action_context = native_action_context(ws, project, feeders, 'obras_bibliotecas')
    plan = {'project': project.strip(), 'folder': carpeta_pf(),
            'feeders': action_context['feeders'],
            'clases': list(clases or []), 'otro_proyecto': otro_proyecto.strip(),
            'native_action_context': action_context}
    ctx.log(f'Proyecto de DIgSILENT: {plan["project"]}  ·  leer bibliotecas de tipos')
    rc, informe, report = _guion_pf(ws, ctx, 'obras_pf.py', plan, nombre='obras_bibliotecas',
                                    args=('--bibliotecas',), cancelable=False)
    if informe.get('error'):
        raise UserError(informe['error'])
    with ws.lock:
        ws.pf_bibliotecas = {**informe, 'project': plan['project']}
    return {'returncode': rc, 'report': report.name, 'informe': informe}


def obras_ejecutar(ws: Workspace, ctx: JobContext, project: str, feeders: list[str],
                   ids: list[str] | None, otro_proyecto: str, *, simular: bool) -> dict:
    """Simula o aplica las obras guardadas con ``tools/obras_pf.py`` (RF-56 a RF-87).

    Al aplicar, las obras que quedaron creadas en el proyecto salen del espacio (RF-95):
    también la que no converge en un caso, que se conserva en el proyecto (RF-67). La que
    no se pudo crear se queda, para corregirla.
    """
    if not project.strip():
        raise UserError('Elija el proyecto de DIgSILENT.')
    action_context = native_action_context(ws, project, feeders, 'obras')
    elegidas = [o for o in ws.obras if not ids or o['id'] in ids]
    if not elegidas:
        raise UserError('No hay obras que simular ni aplicar: defina alguna primero.')
    plan = {'project': project.strip(), 'folder': carpeta_pf(),
            'feeders': action_context['feeders'],
            'obras': [{k: v for k, v in o.items() if k != 'id'} for o in elegidas],
            'otro_proyecto': otro_proyecto.strip(),
            'native_action_context': action_context}
    modo = 'simulacion' if simular else 'aplicacion'
    ctx.log(f"Proyecto de DIgSILENT: {plan['project']}  ·  {len(elegidas)} obra(s)")
    rc, informe, report = _guion_pf(ws, ctx, 'obras_pf.py', plan, nombre=f'obras_{modo}',
                                    args=('--simular',) if simular else ())
    if informe.get('error') and not informe.get('obras'):
        raise UserError(informe['error'])
    aplicadas: list[str] = []
    if not simular:
        for fila in informe.get('obras') or []:
            n = int(fila.get('obra') or 0)
            if 1 <= n <= len(elegidas) and fila.get('variacion') and not fila.get('error'):
                aplicadas.append(elegidas[n - 1]['id'])
        with ws.lock:
            ws.obras = [o for o in ws.obras if o['id'] not in aplicadas]
            ws.save()
    return {'returncode': rc, 'report': report.name, 'project': plan['project'],
            'informe': informe, 'aplicadas': aplicadas}


# ------------------------------------------------------------------ estudios
def estudios_catalogo() -> dict:
    """Estudios ofrecidos, los demás con lo que les falta y los límites del perfil (RF-23, RF-24, RF-35)."""
    from dataclasses import asdict

    from ..estudios_pf import EstudiosError, estudios_no_ofrecidos, estudios_ofrecidos, limites_de_perfil

    try:
        limites, error = asdict(limites_de_perfil()), None
    except EstudiosError as exc:
        limites, error = None, str(exc)
    return {'ofrecidos': [{'clave': e.clave, 'nombre': e.nombre} for e in estudios_ofrecidos()],
            'no_ofrecidos': estudios_no_ofrecidos(), 'limites': limites,
            'error_limites': error, 'limite_s': LIMITE_ESTUDIO_S}


def estudios_plan(ws: Workspace, project: str, feeders: list[str], estudios: list[str],
                  ajuste: dict | None, limites: dict | None = None,
                  limite_s: float | None = None) -> dict:
    """Valida y guarda el plan de los estudios sobre la base calibrada (RF-12 a RF-15, RF-25).

    La base es la del último ajuste aplicado, la misma de las cargas (RF-12). Sin ajuste
    no hay base (RF-13); un alimentador sin variación de ajuste queda fuera, con el
    motivo (RF-14); uno que no cuadró se estudia y se avisa (RF-15).
    """
    from dataclasses import asdict

    from ..estudios_pf import EstudiosError, limites_de_perfil, validar_estudios

    if not project.strip():
        raise UserError('Elija el proyecto de DIgSILENT.')
    requested_for_gate = list(dict.fromkeys(f.strip() for f in feeders if f.strip()))
    native_action_context(ws, project, requested_for_gate, 'estudios')
    if ajuste is None:
        raise UserError('El proyecto no tiene ningún ajuste a la máxima aplicado en este espacio: '
                        'primero hay que calibrar.')
    try:
        claves = list(validar_estudios(estudios))
        lim = limites_de_perfil().con(**(limites or {}))
    except EstudiosError as exc:
        raise UserError(str(exc)) from exc
    base = base_del_ajuste(ajuste, project)
    pedidos = list(dict.fromkeys(feeders)) or list(base['feeders'])
    excluidos = [x for x in base['excluidos'] if x['feeder'] in pedidos]
    fuera = {x['feeder'] for x in excluidos}
    excluidos += [{'feeder': f, 'motivo': 'no está calibrado'}
                  for f in pedidos if f not in base['feeders'] and f not in fuera]
    estudiables = [f for f in pedidos if f in base['feeders']]
    if not estudiables:
        raise UserError('Ningún alimentador marcado tiene su ajuste aplicado: primero hay que '
                        'calibrar.')
    avisos = [f"{a['feeder']}: su ajuste no cuadró ({a.get('motivo') or 'fuera de tolerancia'}); "
              'se estudia igual.' for a in base['ajustes']
              if a['feeder'] in estudiables and not a.get('cuadrado')]
    token = uuid.uuid4().hex[:12]
    plan = {'project': project.strip(), 'folder': carpeta_pf(), 'feeders': estudiables,
            'base': base, 'estudios': claves, 'limites': asdict(lim),
            'limite_s': float(limite_s or LIMITE_ESTUDIO_S),
            'objetivos': {a['feeder']: a.get('objetivo') for a in base['ajustes']
                          if isinstance(a.get('objetivo'), dict)},
            'tolerancia': float(ajuste.get('tolerancia') or 0.01),
            'native_action_context': native_action_context(
                ws, project, estudiables, 'estudios',
            )}
    ws.plans_dir.mkdir(parents=True, exist_ok=True)
    path = ws.plans_dir / f'estudios_{token}.json'
    path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    with ws.lock:
        ws.cargas_planes[token] = {'kind': 'estudios', 'path': str(path),
                                   'project': plan['project'], 'feeders': estudiables,
                                   'applicable': True}
    return {'token': token, 'kind': 'estudios', 'project': plan['project'],
            'feeders': estudiables, 'estudios': claves, 'excluidos': excluidos,
            'avisos': avisos, 'limites': plan['limites'], 'limite_s': plan['limite_s']}


def estudios_ejecutar(ws: Workspace, ctx: JobContext, token: str) -> dict:
    """Prepara los casos y ejecuta cada estudio en «Sin proyecto» y luego en «Con proyecto»
    (RF-25), cada uno en su proceso con su límite (RF-39, RF-40).

    Cancelar termina el estudio en curso, no empieza otro y conserva los terminados
    (RF-41): los ficheros se escriben con lo que haya.
    """
    from ..estudios_pf import (
        COLUMNAS_RESULTADOS, COLUMNAS_VIOLACIONES, CON_PROYECTO, SIN_PROYECTO, Limites,
        escribir_csv, filas_resultados, filas_violaciones,
    )
    from .jobs import JobCancelled

    meta = ws.cargas_planes.get(token)
    if meta is None or meta.get('kind') != 'estudios' or not Path(meta['path']).is_file():
        raise UserError('El plan de los estudios ya no existe: vuelva a prepararlo.')
    plan = json.loads(Path(meta['path']).read_text(encoding='utf-8'))
    nombres = {'sin': SIN_PROYECTO, 'con': CON_PROYECTO}
    ctx.log(f"Proyecto de DIgSILENT: {plan['project']}  ·  preparar los casos")
    from ..powerfactory_binding import caso_base_verificado

    _rc, casos, casos_report = _guion_pf(
        ws, ctx, 'casos_pf.py', {
            **{k: plan[k] for k in ('project', 'folder', 'feeders', 'base')},
            'native_action_context': plan['native_action_context'],
            # 015:RF-17: sin «Caso base» verificado no se crean «Sin» ni «Con proyecto».
            'caso_base_sin_verificar': caso_base_verificado(ws, plan['project'], plan['feeders']),
        },
        nombre='casos', cancelable=False)
    if casos.get('error'):
        raise UserError(casos['error'])                                # RF-13, RF-16
    feeders = casos.get('feeders') or plan['feeders']
    roles = ['sin'] + (['con'] if (casos.get('casos') or {}).get('con', {}).get('estudiable') else [])
    total = len(roles) * len(plan['estudios'])
    resultados, informes, cancelado, n = [], [], False, 0
    try:
        for rol in roles:
            for estudio in plan['estudios']:
                if ctx.cancel.is_set():
                    cancelado = True
                    break
                ctx.progress(n, total, f'{estudio} · {nombres[rol]}')
                n += 1
                sub = {'project': plan['project'], 'folder': plan['folder'], 'feeders': feeders,
                       'estudio': estudio, 'caso': rol, 'objetivos': plan['objetivos'],
                       'tolerancia': plan['tolerancia'], 'stamp': token,
                       'native_action_context': plan['native_action_context']}
                rc, inf, report = _guion_pf(ws, ctx, 'estudios_pf.py', sub,
                                            nombre=f'estudio_{rol}_{estudio}', cancelable=False,
                                            limite_s=plan['limite_s'])
                if inf.get('no_terminado'):
                    ctx.log(f'{estudio} en «{nombres[rol]}»: {inf["error"]}; se sigue con el siguiente.')
                informes.append({'caso': nombres[rol], 'estudio': estudio, 'returncode': rc,
                                 'report': report.name, 'error': inf.get('error'),
                                 'no_terminado': bool(inf.get('no_terminado')),
                                 'obras_activas': inf.get('obras_activas') or [],     # RF-68
                                 'avisos': inf.get('avisos') or []})
                for f, medida in sorted((inf.get('medidas') or {}).items()):
                    resultados.append({'caso': nombres[rol], 'alimentador': f,
                                       'estudio': estudio, **medida})
            if cancelado:
                break
    except JobCancelled:
        cancelado = True
    if cancelado:
        ctx.log('Cancelado: se conservan los estudios terminados.')
    limites = Limites(**plan['limites'])
    ficheros = []
    result_rows = filas_resultados(resultados, limites) if resultados else []
    violation_rows = filas_violaciones(resultados, limites) if resultados else []
    if resultados:
        for nombre, filas, columnas in (
                ('resultados', result_rows, COLUMNAS_RESULTADOS),
                ('violaciones', violation_rows, COLUMNAS_VIOLACIONES)):
            destino = escribir_csv(filas, columnas, ws.out_dir / f'estudios_{nombre}_{token}.csv')
            ficheros.append(destino.name)
    return {'project': plan['project'], 'feeders': feeders, 'casos': casos,
            'casos_report': casos_report.name, 'estudios': informes, 'ficheros': ficheros,
            'medidas': resultados, 'resultados': result_rows, 'violaciones': violation_rows,
            'cancelado': cancelado}


# ------------------------------------------------------------------ transferencia
def _seccionadores_de_la_entrada(ws: Workspace, feeders: list[str]) -> list[str]:
    """Números de equipo de los seccionadores de la entrada cargada (RF-129).

    Solo hacen falta para un proyecto convertido antes de que el DGS distinguiera los
    seccionadores; sin entrada cargada, el guion lo dice.
    """
    ds = ws.dataset
    if ds is None:
        return []
    cortos = set(feeders)
    out = []
    for network_id, filas in getattr(ds, 'switching_by_feeder', {}).items():
        if network_id in cortos or feeder_short_name(network_id) in cortos:
            out += [fila.get('EqNumber') for clase, fila in filas
                    if clase == 'SWITCH' and fila.get('EqNumber')]
    return sorted(set(out))


def transferencia_ejecutar(ws: Workspace, ctx: JobContext, project: str, feeders: list[str],
                           casos: list[str], limites: dict | None = None) -> dict:
    """Transferencia de carga entre dos alimentadores con ``tools/transferencia_pf.py``
    (RF-104 a RF-129), con su fichero descargable (RF-121)."""
    feeders = list(dict.fromkeys(f.strip() for f in feeders if f.strip()))
    if not project.strip():
        raise UserError('Elija el proyecto de DIgSILENT.')
    if len(feeders) != 2:
        raise UserError('Elija dos alimentadores distintos.')
    action_context = native_action_context(ws, project, feeders, 'transferencia')
    token = uuid.uuid4().hex[:12]
    fichero = ws.out_dir / f'transferencias_{token}.csv'
    plan = {'project': project.strip(), 'folder': carpeta_pf(), 'feeders': feeders,
            'casos': list(casos), 'limites': dict(limites or {}),
            'seccionadores': _seccionadores_de_la_entrada(ws, feeders),
            'native_action_context': action_context}
    ctx.log(f"Proyecto de DIgSILENT: {plan['project']}  ·  transferencia {feeders[0]} ↔ {feeders[1]}")
    rc, informe, report = _guion_pf(ws, ctx, 'transferencia_pf.py', plan, nombre='transferencia',
                                    args=('--fichero', str(fichero)))
    if informe.get('error') and not informe.get('resultados'):
        raise UserError(informe['error'])
    return {'returncode': rc, 'report': report.name, 'project': plan['project'],
            'fichero': fichero.name if fichero.is_file() else None, 'informe': informe}


# ------------------------------------------------------------------ guiones del operador
def guiones_listar(ws: Workspace, ctx: JobContext, project: str) -> dict:
    """Los guiones DPL y Python de los casos y de la carpeta de guiones (RF-27)."""
    if not project.strip():
        raise UserError('Elija el proyecto de DIgSILENT.')
    bound = (ws.pf_project_bindings.get(project.strip()) or {}).get('feeders') or []
    action_context = native_action_context(ws, project, list(bound), 'guion')
    plan = {'project': project.strip(), 'folder': carpeta_pf(),
            'feeders': list(bound), 'native_action_context': action_context}
    ctx.log(f'Proyecto de DIgSILENT: {plan["project"]}  ·  leer los guiones del operador')
    rc, informe, report = _guion_pf(ws, ctx, 'estudios_pf.py', plan, nombre='guiones',
                                    args=('--guion',), cancelable=False)
    if informe.get('error'):
        raise UserError(informe['error'])
    return {'returncode': rc, 'report': report.name, 'project': plan['project'],
            'guiones': informe.get('guiones') or []}


def guion_ejecutar(ws: Workspace, ctx: JobContext, project: str, nombre: str, origen: str,
                   parametros: dict[str, str], casos: list[str],
                   limite_s: float | None = None) -> dict:
    """Un guion del operador en cada caso pedido, con sus parámetros (RF-28 a RF-30).

    Cada caso va en su proceso, con el límite de los estudios. Si en un caso el guion
    devuelve error, se informa con su código y su salida y se sigue con el otro (RF-30).
    """
    from ..estudios_pf import CON_PROYECTO, SIN_PROYECTO
    from .jobs import JobCancelled

    if not project.strip() or not nombre.strip():
        raise UserError('Elija el proyecto y el guion.')
    bound = (ws.pf_project_bindings.get(project.strip()) or {}).get('feeders') or []
    action_context = native_action_context(ws, project, list(bound), 'guion')
    roles = {SIN_PROYECTO: 'sin', CON_PROYECTO: 'con'}
    malos = [c for c in casos if c not in roles]
    if malos or not casos:
        raise UserError(f'Los guiones se ejecutan en «{SIN_PROYECTO}» o «{CON_PROYECTO}»'
                        + (f', no en {", ".join(malos)}.' if malos else '.'))
    resultados, cancelado = [], False
    try:
        for n, caso in enumerate(casos):
            if ctx.cancel.is_set():
                cancelado = True
                break
            ctx.progress(n, len(casos), f'{nombre} · {caso}')
            plan = {'project': project.strip(), 'folder': carpeta_pf(), 'caso': roles[caso],
                    'feeders': list(bound), 'native_action_context': action_context,
                    'guion': {'nombre': nombre.strip(), 'origen': origen},
                    'parametros': dict(parametros)}
            rc, inf, report = _guion_pf(ws, ctx, 'estudios_pf.py', plan, nombre='guion',
                                        args=('--guion',), cancelable=False,
                                        limite_s=limite_s or LIMITE_ESTUDIO_S)
            if inf.get('error'):
                ctx.log(f'{nombre} en «{caso}»: {inf["error"]}; se sigue.')
            resultados.append({'caso': caso, 'returncode': rc, 'report': report.name,
                               'codigo_guion': inf.get('codigo_guion'), 'salida': inf.get('salida') or [],
                               'error': inf.get('error'), 'no_terminado': bool(inf.get('no_terminado'))})
    except JobCancelled:
        cancelado = True
    return {'project': project.strip(), 'guion': nombre.strip(), 'origen': origen,
            'resultados': resultados, 'cancelado': cancelado}
