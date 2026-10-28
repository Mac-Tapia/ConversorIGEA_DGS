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
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..naming import feeder_short_name
from ..powerfactory_env import (
    pf_api_version, pf_python_dir, pf_subprocess_env, project_root, python_for_pf, tools_dir,
)
from ..powerfactory_binding import alimentadores_vinculados
from ..util import nombre_seguro, write_json_atomic
from .jobs import LIMITE_ARRANQUE_PF_S, JobContext
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


def comprobar_dgs_vinculados(ws: Workspace, aceptados: dict[str, str], feeders: list[str]) -> None:
    """El DGS que se usaría debe ser el que se aceptó en DIgSILENT (spec 018, RF-6).

    La huella de la fuente no basta: dos espacios con la misma fuente pueden tener opciones
    de conversión distintas y, con ellas, DGS distintos. Un alimentador sin huella
    registrada (vínculo de antes de la spec 018, o aceptado antes de registrarla) no se
    bloquea aquí; la comprobación de sidecar de cada acción sigue vigente.
    """
    from ..feeder_metadata import read_feeder_metadata

    jobs, _missing = dgs_jobs(ws, feeders)
    for feeder, dgs, _geo in jobs:
        esperado = str((aceptados or {}).get(feeder) or '')
        if not esperado:
            continue
        meta = dgs.with_name(f'{dgs.stem}_feeder_metadata.json')
        if not meta.is_file():
            continue
        try:
            actual = str(read_feeder_metadata(meta, expected_dgs=dgs).get('dgs_sha256') or '')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise UserError(
                f'PROJECT_BINDING_DGS_MISMATCH: no se puede leer el sidecar de {feeder}: {exc}'
            ) from exc
        if actual != esperado:
            raise UserError(
                f'PROJECT_BINDING_DGS_MISMATCH: el DGS de {feeder} ya no es el que se aceptó '
                f'en DIgSILENT ({esperado[:12]}… → {actual[:12]}…). Convierta con las mismas '
                'opciones de la aceptación, o reimporte y acepte el proyecto.'
            )


def alimentadores_pedidos(ws: Workspace, nombres: list[str]) -> list[str]:
    """Los alimentadores de lo pedido: el nombre de una red unida o por sistema del espacio
    vale por sus alimentadores (018:RF-14). Nasca, 2026-10-24: el «Caso base» pedido con
    ``SISTEMA_NASCA`` no era subconjunto de los alimentadores del vínculo."""
    salida: list[str] = []
    for nombre in nombres:
        nombre = str(nombre).strip()
        grupo = (ws.groups or {}).get(nombre) if nombre else None
        miembros = list((grupo or {}).get('feeders') or []) if isinstance(grupo, dict) else []
        salida += miembros or ([nombre] if nombre else [])
    return list(dict.fromkeys(salida))


def usar_ejecucion_del_vinculo(ws: Workspace, project: str, binding: Any, pedidos: list[str]) -> str | None:
    """Activa la ejecución del vínculo si la activa es de la misma fuente y no tiene el DGS
    aceptado (018:RF-15); devuelve el aviso, o None si no hizo falta.

    Nasca, 2026-10-24: tras importar ``SISTEMA_NASCA`` se volvió a cargar la misma fuente y la
    verificación del «Caso base» pedía ``CH101.dgs`` y los demás de la ejecución nueva.
    """
    activa = ws.active_run()
    if activa is None or not getattr(binding, 'source_run_id', None):
        return None
    if activa.run_id == binding.source_run_id:
        return None
    if (activa.mode, activa.fingerprint) != (binding.source_mode, binding.source_fingerprint):
        return None
    if not dgs_jobs(ws, pedidos)[1]:
        return None
    adoptar_fuente_del_vinculo(ws, project)
    return (f'Se usa la ejecución {binding.source_run_id}, con la que se aceptó {project}: la activa '
            f'({activa.run_id}) es de la misma fuente pero no tiene su DGS (018:RF-15).')


def native_action_context(
    ws: Workspace, project: str, feeders: list[str], action: str,
) -> dict[str, Any]:
    """Vincula toda acción nativa con la fuente y relectura PowerFactory aceptadas."""
    from ..native_action import build_native_action_context
    from ..powerfactory_binding import (
        ProjectBindingError, alimentadores_vinculados, project_binding_warnings,
        require_project_binding,
    )

    project = str(project or '').strip()
    normalized = sorted(set(alimentadores_pedidos(ws, list(feeders))))           # 018:RF-14
    if not normalized:
        normalized = sorted(set(alimentadores_vinculados(ws, project)))
    try:
        binding = require_project_binding(ws, project, normalized)
        comprobar_dgs_vinculados(ws, binding.dgs_sha256, normalized)
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
    # Tras reiniciar la web la red ya no está en memoria aunque nada haya cambiado: decir
    # «las entradas cambiaron» (IN111 + TA225, 2026-10-14) mandaba a buscar un cambio
    # que no existía.
    if snapshot is not None and ws.loaded_run_id is None:
        raise UserError(
            'SOURCE_RUN_MISMATCH: la red no está cargada en esta sesión de la web (por '
            'ejemplo, tras reiniciarla). Pulse «Cargar / listar alimentadores».'
        )
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


def check_powerfactory_source_run(
    ws: Workspace, feeders: list[str], *, exigir_red_cargada: bool = True,
) -> dict[str, Any]:
    """Liga cada DGS y sidecar al run activo antes de cualquier mutación en PF.

    ``exigir_red_cargada=False`` compara solo con el manifiesto en disco (018:RF-12): basta
    para leer un proyecto ya importado. Importar sigue exigiendo la red cargada.
    """
    from ..feeder_metadata import read_feeder_metadata
    from ..powerfactory_metadata import verify_reconstruction_contract

    if exigir_red_cargada:
        snapshot = require_active_source_run(ws)
    else:
        snapshot = ws.active_run()
        if snapshot is None:
            raise UserError('PROJECT_BINDING_NO_ACTIVE_SOURCE: este espacio de trabajo no tiene '
                            'una ejecución fuente activa.')
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
        if reconstruction is not None and ws.loaded_run_id is None:
            # El informe de la reconstrucción se valida con lo cargado (018:RF-12).
            raise UserError(
                f'SOURCE_RUN_MISMATCH: {feeder} sale de una reconstrucción y la red no está '
                'cargada en esta sesión de la web. Pulse «Cargar / listar alimentadores».'
            )
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
            if not acceptance.get('project_binding'):
                # El guion crea el proyecto pero no adjunta vínculo cuando la importación
                # no quedó ok o la evidencia de la fuente no se verificó antes de mutar.
                # Sin este aviso, el proyecto aparece en DIgSILENT y la web lo bloquea sin
                # que nadie sepa por qué (caso CA101, 2026-10-14).
                ctx.log(f'  AVISO: {proyecto} existe en DIgSILENT pero el informe no trae '
                        'vínculo; este proyecto no se podrá calibrar desde esta web.')
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
    # Solo los seleccionados: ver ``batch.convert_group``.
    return feeders


def estructura_resumen(ws: Workspace) -> dict:
    """Los zonales de la estructura con sus alimentadores en la entrega (022:RF-48)."""
    from ..estructura import asignar

    e = estructura_del_espacio(ws)
    if e is None:
        return {'origen': None, 'zonales': []}
    from .reconstruction_service import resolve_selection

    entrega, _ids = resolve_selection(ws, [], all_feeders=True)
    a = asignar(e, entrega)
    origen = 'excel' if ((ws.demanda or {}).get('estructura') or {}).get('path') else 'perfil'
    deducidos = [{'alimentador': f, 'set': e.set_de(f).codigo, 'zonal': e.set_de(f).zonal,
                  'regla': e.deducidos[f]} for f in sorted(a.set_de) if f in e.deducidos]
    de_set: dict[str, list[str]] = {}
    for f, s in sorted(a.set_de.items()):
        de_set.setdefault(s, []).append(f)
    return {'origen': origen, 'sin_set': a.sin_set, 'deducidos': deducidos, 'zonales': [
        {'nombre': z, 'sets': sorted(s for s in de_set if e.sets[s].zonal == z),
         'alimentadores': sorted(f for f, s in a.set_de.items() if e.sets[s].zonal == z),
         # 022:RF-82: cada SET con su rótulo y sus alimentadores, para convertirla sola.
         'sets_detalle': [{'codigo': s, 'rotulo': e.sets[s].rotulo, 'alimentadores': de_set[s]}
                          for s in sorted(de_set) if e.sets[s].zonal == z]}
        for z in a.zonales]}


def sistema_seleccion(ws: Workspace, zonales: list[str],
                      sets: list[str] | None = None) -> tuple[list[str], str, object]:
    """Los alimentadores de la entrega de los zonales o las SET elegidos (o de todos), el
    nombre del DGS y la estructura (022:RF-47 a RF-49, RF-82)."""
    from ..estructura import asignar, clave

    require_loaded(ws)
    e = estructura_del_espacio(ws)
    if e is None:
        raise UserError('La conversión por sistema eléctrico necesita la estructura de la empresa: '
                        'súbala en Excel en el paso de demanda o póngala en el perfil (022:RF-1).')
    todos = group_selection(ws, [], True)
    a = asignar(e, todos)
    pedidos = [z for z in zonales if z]
    desconocidos = [z for z in pedidos if z not in e.zonales]
    if desconocidos:
        raise UserError(f"Zonal(es) que no están en la estructura: {', '.join(desconocidos)}.")
    pedidas = [clave(s) for s in sets or () if clave(s)]
    desconocidas = [s for s in pedidas if s not in e.sets]
    if desconocidas:
        raise UserError(f"SET que no están en la estructura: {', '.join(desconocidas)}.")
    por_nombre = {f.upper(): f for f in todos}
    if pedidas:
        # RF-82: una SET (o varias) sola, con su red y sus barras, como en su sistema.
        elegidos = [por_nombre[f] for f, s in a.set_de.items() if s in pedidas]
        alcance = pedidas
    elif pedidos:
        elegidos = [por_nombre[f] for f, s in a.set_de.items() if e.sets[s].zonal in pedidos]
        alcance = pedidos
    else:
        elegidos = list(todos)                                       # RF-48: también «Sin SET»
        alcance = []
    if not elegidos:
        raise UserError('Ningún alimentador de la entrega es de ' + ', '.join(alcance) + '.')
    if pedidas:
        zonal = {e.sets[s].zonal for s in pedidas}
        base = '_'.join(sorted(zonal)) + '_' + '_'.join(pedidas)
    else:
        base = '_'.join(pedidos) if pedidos else 'ELECTRICO'
    nombre = nombre_seguro('SISTEMA_' + base, maximo=60)
    return sorted(elegidos), nombre.upper(), e


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
    estructura=None,
    tipo: str = 'unida',
    reconstruir: dict | None = None,
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
        on_progress=on_progress, cancel=ctx.cancel, estructura=estructura,
        reconstruir=reconstruir,                                       # 022:RF-61
    )
    for linea in _informe_por_set(man.get('estructura')):            # 022:RF-25, RF-34
        ctx.log(linea)
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
        # 022:RF-49, RF-51: «sistema» (por sistema eléctrico) o «unida» (dos o más).
        ws.groups[nombre]['tipo'] = tipo
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
    from .jobs import TIEMPO_AGOTADO

    carpeta = carpeta_pf()
    pf_dir, interpreter = _require_pf()
    out = ws.out_dir / 'pf_proyectos.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    for intento in (1, 2):
        rc = ctx.run_process(
            [str(interpreter), str(_script('pf_proyectos.py')), '--output-json', str(out),
             '--carpeta', carpeta],
            env=pf_subprocess_env(pf_dir), cwd=str(project_root()),
            limite_arranque_s=LIMITE_ARRANQUE_PF_S,
        )
        if rc != TIEMPO_AGOTADO or intento == 2:
            break
        # 019:RF-18: con el límite pedido aquí, ``run_process`` no reintenta solo como con
        # los demás guiones. 2026-10-19: tras importar CA101_PE104, el servidor que arrancó
        # 11 s después no conectó en 180 s; el siguiente conectó en 20 s.
        ctx.log('Se reintenta una vez: DIgSILENT a veces no entrega el usuario a la primera.')
        ctx.check_cancel()
    if rc == TIEMPO_AGOTADO:
        raise UserError(
            f'PowerFactory no responde: en {LIMITE_ARRANQUE_PF_S:g} s no entregó el usuario '
            'de DIgSILENT. Los guiones de sesiones anteriores ya se cerraron solos (ver '
            'el Registro); si sigue igual, cierre la ventana de PowerFactory si está '
            'abierta o compruebe la licencia, y vuelva a leer los proyectos.')
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
    estado_vinculos(ws, result.get('projects') or [])
    return result


# Causas que se resuelven usando la ejecución fuente con la que se aceptó (018:RF-9).
_CAUSAS_DE_FUENTE = ('PROJECT_BINDING_NO_ACTIVE_SOURCE', 'PROJECT_BINDING_SOURCE_MISMATCH')


def estado_vinculos(ws: Workspace, projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Añade a cada proyecto leído su vínculo, la causa del bloqueo y sus avisos.

    Se calcula con lo ya leído de DIgSILENT, sin volver a abrirlo: al usar la fuente del
    vínculo (018:RF-10) cambia la fuente activa, no el proyecto.
    """
    from ..powerfactory_binding import (
        ProjectBindingError, project_binding_warnings, require_project_binding,
        vinculo_guardado,
    )

    for project in projects:
        path = str(project.get('path') or project.get('name') or '')
        project['binding'] = None
        project['binding_fuente_disponible'] = False
        try:
            project['binding'] = vinculo_guardado(ws, path)
            require_project_binding(ws, path, project.get('feeders') or [])
        except ProjectBindingError as exc:
            # El código va aparte para que la web explique la causa sin parsear el texto.
            project['binding_blocked_code'] = exc.code
            project['binding_blocked_reason'] = str(exc)
            project['binding_warnings'] = []
            if exc.code in _CAUSAS_DE_FUENTE and project['binding']:
                project['binding_fuente_disponible'] = (
                    _ejecucion_del_vinculo(ws, project['binding']) is not None)
        else:
            project['binding_blocked_code'] = None
            project['binding_blocked_reason'] = None
            project['binding_warnings'] = project_binding_warnings(
                ws, path, project.get('feeders') or [],
            )
    return projects


def _ejecucion_del_vinculo(ws: Workspace, binding: dict[str, Any]) -> Path | None:
    """Carpeta de la ejecución fuente del vínculo, en este espacio o en otro (018:RF-9).

    Solo vale si su manifiesto tiene el modo y la huella del vínculo: el identificador solo
    nombra la carpeta, la huella demuestra que es la misma fuente. Se mira una carpeta por
    espacio de trabajo, nunca un recorrido de todas las ejecuciones.
    """
    from .source_runs import valid_run_id

    run_id = str(binding.get('source_run_id') or '')
    if not valid_run_id(run_id):
        return None
    candidatas = [ws.root / 'runs' / run_id]
    if ws.root.parent.is_dir():
        candidatas += [c / 'runs' / run_id for c in sorted(ws.root.parent.iterdir())
                       if c != ws.root and c.is_dir()]
    for carpeta in candidatas:
        try:
            manifiesto = json.loads((carpeta / 'source_manifest.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if (isinstance(manifiesto, dict) and manifiesto.get('run_id') == run_id
                and manifiesto.get('mode') == binding.get('source_mode')
                and manifiesto.get('fingerprint') == binding.get('source_fingerprint')):
            return carpeta
    return None


def _espacio_que_acepto(ws: Workspace, project: str, run_id: str) -> Path | None:
    """Otro espacio que trabajó el proyecto con esa ejecución: de él sale el contexto.

    No basta con el de la carpeta copiada: al repetir el uso, la ejecución ya es la propia
    y la calibración o los libros de demanda se buscarían en el mismo espacio que no los
    tiene. Si varios lo tienen, el modificado más tarde.
    """
    mejor: tuple[float, Path] | None = None
    if not ws.root.parent.is_dir():
        return None
    for carpeta in ws.root.parent.iterdir():
        meta = carpeta / 'workspace.json'
        if carpeta == ws.root or not meta.is_file():
            continue
        try:
            datos = json.loads(meta.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        vinculo = (datos.get('pf_project_bindings') or {}).get(project) or {}
        if vinculo.get('source_run_id') == run_id:
            cuando = meta.stat().st_mtime
            if mejor is None or cuando > mejor[0]:
                mejor = (cuando, carpeta)
    return mejor[1] if mejor else None


def adoptar_fuente_del_vinculo(ws: Workspace, project: str) -> dict[str, Any]:
    """Hace activa en el espacio la ejecución fuente con la que se aceptó el proyecto.

    Spec 018, RF-10. Caso real (CA101, 2026-10-15): el navegador abrió un espacio nuevo,
    sin fuente, y el proyecto quedó bloqueado aunque su ejecución seguía en disco en el
    espacio que lo aceptó y su «Caso base» estaba verificado. Se copia la ejecución (es
    inmutable; copiar, y no enlazar, evita que una reescritura en el origen cambie esta),
    y con ella la última calibración del proyecto, los DGS unidos de esa ejecución y, si el
    espacio no tiene ninguno, los libros de demanda medida: viven en el espacio y no en la
    ejecución, y sin ellos el paso 2 volvía a pedirlos. Las entradas no se tocan.
    """
    import shutil

    from ..powerfactory_binding import ProjectBindingError, vinculo_guardado

    project = str(project or '').strip()
    if not project:
        raise UserError('Elija el proyecto de DIgSILENT.')
    try:
        binding = vinculo_guardado(ws, project)
    except ProjectBindingError as exc:
        raise UserError(str(exc)) from exc
    if not binding:
        raise UserError(f'PROJECT_BINDING_MISSING: el proyecto {project!r} no tiene aceptación '
                        'registrada en ningún espacio de trabajo.')
    origen = _ejecucion_del_vinculo(ws, binding)
    run_id = str(binding.get('source_run_id') or '')
    if origen is None:
        raise UserError(
            f'PROJECT_BINDING_SOURCE_UNAVAILABLE: la ejecución {run_id!r} con la que se aceptó '
            f'{project!r} ya no está en disco, o su manifiesto no es el de la aceptación. '
            'Cargue y convierta la misma fuente con las mismas opciones.')
    destino = ws.root / 'runs' / run_id
    if origen != destino:
        tmp = destino.with_name(destino.name + '.copia')
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(origen, tmp)
        shutil.rmtree(destino, ignore_errors=True)
        tmp.replace(destino)
    espacio_origen = _espacio_que_acepto(ws, project, run_id) or origen.parent.parent
    calibracion = None
    grupos: dict[str, dict[str, Any]] = {}
    demanda: dict[str, Any] = {}
    if espacio_origen != ws.root:
        try:
            datos = json.loads((espacio_origen / 'workspace.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            datos = {}
        calibracion = (datos.get('calibraciones') or {}).get(project)
        demanda = {tipo: meta for tipo, meta in (datos.get('demanda') or {}).items()
                   if isinstance(meta, dict) and Path(str(meta.get('path') or '')).exists()}
        for nombre, grupo in (datos.get('groups') or {}).items():
            if not isinstance(grupo, dict) or run_id not in str(grupo.get('dgs') or ''):
                continue
            grupos[nombre] = {
                k: (v.replace(str(origen), str(destino))
                    if k in ('dgs', 'feeder_metadata') and isinstance(v, str) else v)
                for k, v in grupo.items()
            }
    with ws.lock:
        if ws.loaded_run_id and ws.loaded_run_id != run_id:
            # La red en memoria es de otra ejecución: dejarla haría creer que está cargada.
            ws.invalidate()
        ws.active_run_id = run_id
        if calibracion and project not in ws.calibraciones:
            ws.calibraciones[project] = calibracion
        for nombre, grupo in grupos.items():
            ws.groups.setdefault(nombre, grupo)
        if not ws.demanda and demanda:
            ws.demanda = demanda
        ws.save()
    inventario = pf_proyectos_guardados(ws)
    inventario['fuente_adoptada'] = {'project': project, 'source_run_id': run_id,
                                     'copiada_de': espacio_origen.name}
    return inventario


def pf_proyectos_guardados(ws: Workspace) -> dict[str, Any]:
    """Última lista de proyectos leída en el espacio, con el vínculo recalculado (018:RF-13).

    Los trabajos viven en memoria: tras reiniciar la web la pestaña perdía la lista, y
    volver a leerla abre DIgSILENT y cada proyecto (231 s con 32 proyectos, 2026-10-15).
    """
    if not (ws.pf_inventory or {}).get('projects'):
        otra = _lectura_mas_reciente_de_la_carpeta(ws)
        if otra:
            # La carpeta de DIgSILENT es común, como el registro de vínculos: un espacio
            # nuevo parte de la última lectura de otro en vez de esperar a abrir DIgSILENT.
            with ws.lock:
                ws.pf_inventory = otra
                ws.save()
    inventario = dict(ws.pf_inventory or {})
    inventario['projects'] = estado_vinculos(
        ws, [dict(p) for p in inventario.get('projects') or []])
    return inventario


def _lectura_mas_reciente_de_la_carpeta(ws: Workspace) -> dict[str, Any] | None:
    """La lectura de proyectos más reciente de otro espacio, de la misma carpeta de DIgSILENT."""
    try:
        carpeta = carpeta_pf()
    except UserError:
        return None
    mejor: tuple[float, dict[str, Any]] | None = None
    if not ws.root.parent.is_dir():
        return None
    for otra in ws.root.parent.iterdir():
        meta = otra / 'workspace.json'
        if otra == ws.root or not meta.is_file():
            continue
        try:
            inventario = json.loads(meta.read_text(encoding='utf-8')).get('pf_inventory') or {}
        except (OSError, ValueError, AttributeError):
            continue
        if inventario.get('folder') != carpeta or not inventario.get('projects'):
            continue
        cuando = max((float(p.get('native_reread_at') or 0) for p in inventario['projects']),
                     default=0.0) or meta.stat().st_mtime
        if mejor is None or cuando > mejor[0]:
            mejor = (cuando, inventario)
    return mejor[1] if mejor else None


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
    # 025:RF-37: las cargas van a los casos del año de su calibración («Sin proyecto 2025»
    # → 2025); la de los casos sin año, a los de siempre.
    import re

    anios = {int(m.group(1)) for inf in informes
             if (m := re.search(r'\s(\d{4})$', str(inf.get('caso') or '')))
             and (inf.get('feeder') or '') in base['feeders']}
    if len(anios) > 1:
        raise UserError('El ajuste base tiene calibraciones de años distintos: '
                        + ', '.join(map(str, sorted(anios))) + '.')
    base['anio_casos'] = next(iter(anios), None)
    return base


def cargas_plan(
    ws: Workspace, project: str, feeders: list[str],
    demandas_file: Path | None, nuevas_file: Path | None,
    nueva: dict | None = None, economia: dict | None = None,
    ajuste: dict | None = None, minima_m: float | None = None,
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
            carpeta=carpeta_pf(), base=base, minima_m=minima_m,
        )
        plan['native_action_context'] = action_context
        # 025:RF-36, RF-37: en los casos del año de la calibración base.
        plan['anio_casos'] = (base or {}).get('anio_casos')
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
    resultado = {'returncode': rc, 'modo': informe.get('modo'), 'report': report.name,
                 'project': plan['project'], 'informe': informe}
    if not simular:
        # 024:RF-1: las cargas nuevas se crean en «Con proyecto» (spec 007).
        plan_json = json.loads(Path(plan['path']).read_text(encoding='utf-8'))
        resultado['digital_twin_episode'] = _gemelo(
            ws, ctx, plan_json, informe, caso='con_proyecto',
            rutas={'plan': Path(plan['path']), 'resultado': report})
    return resultado


# ---------------------------------------------------------------------------
# Demanda medida (spec 004, RF-22 a RF-39)
# ---------------------------------------------------------------------------

DEMANDA_TIPOS = ('medidores', 'cabecera', 'suministros', 'clientes', 'estructura')
DEMANDA_ETIQUETAS = {
    'medidores': 'libro medidor por alimentador', 'cabecera': 'medición de cabecera',
    'suministros': 'libro de suministros', 'clientes': 'libro de clientes importantes',
    # Spec 022, RF-4: la tabla zonal → SET → alimentador de la empresa.
    'estructura': 'tabla de la estructura (zonal, SET y alimentadores)',
}


SIN_SUMINISTROS = ('Ningún libro de suministros en este hueco: sin él, todas las SED se escalan '
                   'con el factor de escala.')


def hay_suministros(ws: Workspace) -> bool:
    """Hueco de suministros con un libro elegido (004:RF-64); los guardados antes de la
    RF-64 no traen «seleccion» y valen como antes."""
    meta = ws.demanda.get('suministros')
    return bool(meta) and meta.get('seleccion', meta.get('name')) is not None


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
    """Guarda la fuente; cabecera, suministros y clientes admiten carpeta."""
    from ..demanda_medida import (
        EXTENSIONES,
        DemandaError,
        aviso_libros_de_clientes,
        descubrir_libro_suministros,
        libros_de_cabecera,
        libros_de_suministros,
    )

    if tipo == 'cabecera':
        from ..libros_por_anio import anios_de, arbol_de_libros
        try:
            libros = libros_de_cabecera([path])
            # 025:RF-3, RF-4: cada libro por su ruta relativa y los años; solo se lista,
            # sin abrir ninguno (P7): el índice con sus hojas es un trabajo aparte.
            arbol = arbol_de_libros(path) if path.is_dir() else []
        except Exception as exc:  # noqa: BLE001 - DemandaError o de E/S: error de usuario
            raise UserError(str(exc)) from exc
        meta = {'path': str(path), 'name': path.name, 'origin': origin,
                'source_kind': 'folder' if path.is_dir() else 'file',
                'libros': [x.relativa for x in arbol] if arbol else [p.name for p in libros],
                'anios': anios_de(arbol), 'indice': [], 'vigente': False, 'avisos': []}
    elif tipo == 'suministros':
        # Cada libro de la carpeta se lee una sola vez: la lista y la elección salen
        # del mismo puntaje (004:RF-58/RF-59).
        # 004:RF-64: nada se rechaza. Sin libro de suministros el hueco queda guardado sin
        # elección y con su aviso; el cruce lo trata como si faltaran los suministros.
        avisos: list[str] = []
        nombres: list[str] = []
        elegido: Path | None = None
        try:
            if path.is_dir():
                candidatos, de_clientes = libros_de_suministros(path, demanda_alias())
                if de_clientes:
                    avisos.append(aviso_libros_de_clientes(de_clientes))
                if candidatos:
                    elegido = max(candidatos, key=candidatos.__getitem__)
                    nombres = [p.name for p in candidatos]
                else:
                    avisos.append(SIN_SUMINISTROS)
            else:
                elegido = descubrir_libro_suministros(path, demanda_alias())
                nombres = [path.name]
        except (DemandaError, OSError, ValueError) as exc:
            avisos += [str(exc), SIN_SUMINISTROS]
        meta = {'path': str(path), 'name': path.name, 'origin': origin,
                'source_kind': 'folder' if path.is_dir() else 'file',
                'libros': nombres, 'seleccion': elegido.name if elegido else None, 'avisos': avisos}
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
        if tipo == 'estructura':
            # 022:RF-5: una tabla mal formada se rechaza al subirla, nombrando la fila.
            from ..estructura import EstructuraError, leer_tabla_excel
            try:
                e = leer_tabla_excel(path)
            except (EstructuraError, OSError, ValueError) as exc:
                raise UserError(f'Estructura: {exc}') from exc
            meta.update(zonales=len(e.zonales), sets=len(e.sets), alimentadores=len(e.alimentadores))
    with ws.lock:
        ws.demanda[tipo] = meta
        ws.save()
    return ws.public()


def _foto_fuente_clientes(path: Path) -> tuple[tuple[str, int, int], ...]:
    """Identidad observable del fichero/carpeta para detectar cambios durante el índice.

    Con sus subcarpetas de año (025:RF-1, RF-31): un libro nuevo en ``2025/`` también
    cambia la foto.
    """
    from ..demanda_medida import EXTENSIONES
    from ..libros_por_anio import arbol_de_libros

    if path.is_file():
        rutas = [(path, path.name)] if path.suffix.lower() in EXTENSIONES else []
    elif path.is_dir():
        rutas = [(x.ruta, x.relativa) for x in arbol_de_libros(path)]
    else:
        return ()
    return tuple((rel, p.stat().st_size, p.stat().st_mtime_ns) for p, rel in rutas)


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
        'anio': libro.anio,
        'mes': libro.mes,
        'origen_mes': libro.origen_mes,
        'activo': libro.activo,
        'avisos': list(libro.avisos),
    } for libro in catalogo]
    # 025:RF-4: los años con libro, para el selector del paso 2.
    anios = sorted({libro.anio for libro in catalogo if libro.anio is not None})

    with ws.lock:
        actual = ws.demanda.get('clientes') or {}
        if actual.get('path') != str(fuente):
            raise UserError('La fuente de clientes cambió durante el índice; vuelva a actualizarla.')
        actual.update({
            'libros': [libro.nombre for libro in catalogo],
            'catalogo': publico,
            'anios': anios,
            'vigente': vigente,
            'avisos': avisos,
            'indexado_en': time.time(),
        })
        ws.save()
    ctx.progress(len(catalogo), len(catalogo), f'{len(catalogo)} libro(s)')
    return {'catalogo': publico, 'anios': anios, 'vigente': vigente, 'avisos': avisos}


def demanda_cabecera_indexar(ws: Workspace, ctx: JobContext) -> dict:
    """Índice de la medición de cabecera por año (025:RF-28 a RF-33).

    Qué trae cada libro (año, hojas de medición, meses con registro) para que el operador
    vea cómo entró cada uno y elija el año. Seguirán llegando años, libros y hojas: solo se
    abren los libros nuevos o cambiados (por tamaño y fecha de modificación). Se publica al
    final, todo de una vez: cancelado o con un fallo, queda el índice anterior entero.
    """
    from .. import demanda_medida as dm
    from ..libros_por_anio import anios_de, arbol_de_libros

    with ws.lock:
        meta = dict(ws.demanda.get('cabecera') or {})
    if not meta:
        raise UserError('Falta la medición de cabecera: indique un libro o una carpeta.')
    fuente = Path(meta.get('path', ''))
    foto_inicial = _foto_fuente_clientes(fuente)
    if not foto_inicial:
        raise UserError('No hay libros de medición de cabecera en la fuente elegida.')
    if fuente.is_dir():
        libros = [(x.ruta, x.relativa, x.anio) for x in arbol_de_libros(fuente)]
    else:
        libros = [(fuente, fuente.name, None)]
    anterior = {x.get('relativa'): x for x in meta.get('indice') or []}
    alias = demanda_alias()
    indice = []
    for n, (path, relativa, anio) in enumerate(libros, start=1):
        ctx.check_cancel()
        ctx.progress(n, len(libros), relativa)
        stat = path.stat()
        previo = anterior.get(relativa)
        if (previo and previo.get('size') == stat.st_size
                and previo.get('mtime_ns') == stat.st_mtime_ns and previo.get('anio') == anio):
            indice.append(previo)
            continue
        datos = dm.indexar_libro_cabecera(path, alias)
        if datos['error']:
            ctx.log(f'  {relativa}: {datos["error"]}')
        indice.append({'relativa': relativa, 'anio': anio, 'size': stat.st_size,
                       'mtime_ns': stat.st_mtime_ns, **datos})
    ctx.check_cancel()
    vigente = _foto_fuente_clientes(fuente) == foto_inicial
    avisos = [] if vigente else [
        'La carpeta cambió mientras se construía el índice; pulse «Actualizar índice» antes '
        'de buscar la máxima.']
    anios = anios_de(x for x in arbol_de_libros(fuente)) if fuente.is_dir() else []
    with ws.lock:
        actual = ws.demanda.get('cabecera') or {}
        if actual.get('path') != str(fuente):
            raise UserError('La medición de cabecera cambió durante el índice; vuelva a actualizarla.')
        actual.update({'libros': [x['relativa'] for x in indice], 'indice': indice,
                       'anios': anios, 'vigente': vigente, 'avisos': avisos,
                       'indexado_en': time.time()})
        ws.save()
    utiles = sum(1 for x in indice if not x.get('error'))
    ctx.progress(len(indice), len(indice), f'{utiles} de {len(indice)} libro(s) con medición')
    return {'indice': indice, 'anios': anios, 'vigente': vigente, 'avisos': avisos}


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
    if tipo == 'suministros':
        from ..demanda_medida import DemandaError, descubrir_libro_suministros
        if not hay_suministros(ws):
            raise UserError(' '.join(meta.get('avisos') or [SIN_SUMINISTROS]))
        try:
            return descubrir_libro_suministros(path, demanda_alias())
        except DemandaError as exc:
            # 004:RF-64 en un hueco guardado antes de ella: la carpeta de clientes subida en
            # «Suministros» (2026-10-22) quedó con uno de sus libros elegido, y «Cruzar
            # clientes» seguía activo y fallaba en cada pulsación sin aviso en el hueco.
            with ws.lock:
                meta.update(seleccion=None, libros=[], avisos=[str(exc), SIN_SUMINISTROS])
                ws.save()
            raise UserError(str(exc)) from exc
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
                                 alimentador, _grafias(ws)(alimentador))
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


def sistema_del_proyecto(ws: Workspace, project: str) -> dict | None:
    """El sistema eléctrico de un proyecto de DIgSILENT, si se convirtió por sistema (022:RF-52).

    ``{'grupo', 'alimentadores', 'medidores'}``, con los medidores de alimentador de cada
    uno en el libro (vacío si no tiene). ``None`` si el proyecto no es de tipo «sistema».
    """
    from ..demanda_medida import DemandaError, leer_medidores, medidores_de

    proyecto = project.strip()
    grupo = next((n for n, p in (ws.pf_projects or {}).items()
                  if p == proyecto and (ws.groups.get(n) or {}).get('tipo') == 'sistema'), None)
    if grupo is None:
        return None
    alimentadores = list(ws.groups[grupo].get('feeders') or [])
    try:
        filas = leer_medidores(_demanda_ruta(ws, 'medidores'), demanda_alias())
    except (DemandaError, UserError):
        filas = []                    # sin libro de medidores, ninguno tiene medidor
    grafias = _grafias(ws)
    medidores = {a: medidores_de(filas, a, grafias(a)) for a in alimentadores}
    return {'grupo': grupo, 'alimentadores': alimentadores, 'medidores': medidores}


def _grafias(ws: Workspace) -> Callable[[str], list[str]]:
    """Las otras grafías de un alimentador según la estructura del espacio, leída una vez
    (022:RF-81): la red trae CN101 y el libro de medidores, CHN101. Sin estructura, ninguna."""
    try:
        e = estructura_del_espacio(ws)
    except UserError:
        e = None
    return (lambda a: e.equivalentes(a)[1:]) if e is not None else (lambda a: [])


def _libros_de_cabecera(ws: Workspace, periodo: str | None) -> list[Path]:
    """Los libros de cabecera en que se busca la máxima del periodo (025:RF-8, RF-9, RF-31).

    Con carpetas de año, solo los del año del periodo y los sueltos: la máxima de 2025 no
    puede salir de un libro de 2026. Sin periodo, con años, no se busca: se mezclarían.
    """
    from ..demanda_medida import DemandaError
    from ..libros_por_anio import arbol_de_libros, libros_del_periodo

    ruta = _demanda_ruta(ws, 'cabecera')
    if not ruta.is_dir():
        return [ruta]
    meta = ws.demanda.get('cabecera') or {}
    if meta.get('indice') and not meta.get('vigente'):
        raise UserError('El índice de la medición de cabecera no está al día: pulse '
                        '«Actualizar índice» antes de buscar la máxima.')
    try:
        libros = libros_del_periodo(arbol_de_libros(ruta), periodo)
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    if not libros:
        raise UserError(f'No hay libros de medición de cabecera de {periodo}.')
    return [x.ruta for x in libros]


def demanda_cabecera(ws: Workspace, ctx: JobContext, pares: list[tuple[str, str]], *,
                     periodo: str | None = None, instante: datetime | None = None,
                     por_barra: bool = False, centrales_tramo: dict[str, str] | None = None) -> dict:
    """Máxima de cada medidor en la medición de cabecera (RF-24 a RF-32). Es un trabajo:
    abrir los libros cuesta segundos (P7). Se cancela entre medidores.

    ``periodo``: la máxima de ese mes (013:RF-11). ``instante``: el registro de esa fecha
    y hora en todos los medidores, para calibrar a la vez (021:RF-50).
    """
    from ..demanda_medida import DemandaError, maximas

    if not pares:
        raise UserError('Indique al menos un medidor.')
    if por_barra and instante is None:
        return _demanda_por_barra(ws, ctx, pares, periodo, centrales_tramo)   # 022:RF-37 a RF-46, RF-88
    # Con un instante, el año es el suyo (021:RF-50): sus libros, no todos.
    libros = _libros_de_cabecera(ws, periodo or (instante.strftime('%Y') if instante else None))
    alias = demanda_alias()
    ctx.log(f'Medición de cabecera: {", ".join(p.name for p in libros)} · {len(pares)} medidor(es)'
            + (f' · registro del {instante}' if instante else f' · máxima de {periodo}' if periodo else ''))
    try:
        res = maximas(libros, pares, alias=alias, periodo=periodo, instante=instante,
                      cancelado=ctx.cancel.is_set,
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
        ws.criterio_cabecera = {ctx.job.id: {'periodo': periodo, 'instante': instante}}
    return {'resultados': [r.to_dict() for r in res],
            'cancelado': len(res) < len(pares),
            'periodo': periodo, 'instante': instante.isoformat(sep=' ') if instante else None}


def _informe_por_set(e: dict | None) -> list[str]:
    """El informe de la conversión por zonal y SET, para el Registro (022:RF-25, RF-34)."""
    if not e:
        return []
    out = ['Por zonal y SET:']
    for zonal, sets in e['zonales'].items():
        out.append(f'  {zonal}: ' + '; '.join(
            f"{s} ({', '.join(d['barras'])}): {', '.join(d['alimentadores'])}" for s, d in sets.items()))
    if e['sin_set']:
        out.append('  Sin SET (con su red externa): ' + ', '.join(e['sin_set']))
    if e['faltan']:
        out.append(f"  De la estructura y no de la entrega: {len(e['faltan'])}")
    for a in e['aperturas']:
        out.append('  ' + a['texto'])
    ora = (e.get('oraculo') or {}).get('general') or {}
    out.append('  Oráculo de la red unida: ' + (ora.get('resumen') or 'no disponible'))
    return out


def estructura_del_espacio(ws: Workspace):
    """La estructura zonal → SET → alimentador del espacio (022:RF-4) o del perfil (RF-1)."""
    from ..estructura import EstructuraError, leer_tabla_excel
    from ..perfil_empresa import PerfilError, estructura_empresa

    from ..estructura import cabeceras_de_inventario, completar

    ruta = ((ws.demanda or {}).get('estructura') or {}).get('path')
    try:
        e = leer_tabla_excel(ruta) if ruta else estructura_empresa()
    except (EstructuraError, PerfilError) as exc:
        raise UserError(f'Estructura de la empresa: {exc}') from exc
    # 022:RF-77: con los alimentadores de la entrega que la tabla aún no trae (Chincha
    # Nueva en RED_231026); un espacio cargado antes de RF-74 no tiene sus cabeceras y
    # solo coloca los de siglas conocidas hasta que se vuelve a cargar.
    filas = (ws.inventory or {}).get('feeders') or []
    return completar(e, cabeceras_de_inventario(filas)) if e is not None and filas else e


def _kv_alimentadores(ws: Workspace) -> dict[str, float]:
    """Tensión nominal de cada alimentador de la entrega (inventario de la ejecución)."""
    ruta = ws.out_dir / 'dataset_inventory.json'
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    out = {}
    for f in datos.get('feeders') or []:
        try:
            out[str(f['feeder']).upper()] = float(f['nominal_kv'])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def demanda_centrales_de_barra(ws: Workspace) -> dict:
    """Las centrales térmicas (medidores CT…) del libro de medidores, con su SET, su tensión
    y los alimentadores de esa SET, para que el operador diga si están en la barra o en el
    tramo de un alimentador (022:RF-88). La propuesta: en el tramo, las del perfil
    (``centrales_termicas``, la de Nasca en NA205); en la barra, las demás (CT_PEDREG)."""
    from ..demanda_medida import DemandaError, clave_codigo, leer_medidores_de_barra
    from ..perfil_empresa import PerfilError, centrales_termicas, datos_perfil

    try:
        filas = leer_medidores_de_barra(_demanda_ruta(ws, 'medidores'), demanda_alias())
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    try:
        perfil = centrales_termicas(datos_perfil())
    except PerfilError:
        perfil = {}
    del_perfil = {clave_codigo(c['generacion']): a for a, c in perfil.items()}
    e = estructura_del_espacio(ws)
    de_set: dict[str, list[str]] = {}
    if e is not None:
        for a in e.alimentadores.values():
            de_set.setdefault(a.set_codigo, []).append(a.codigo)
    out = []
    for m in filas:
        if not m.central:
            continue
        st = (e.set_de_texto(m.siglas) or e.set_de_medidor(m.medidor)) if e is not None else None
        out.append({'medidor': m.medidor, 'kv': m.kv, 'rotulo': m.rotulo,
                    'set': st.codigo if st else '', 'set_rotulo': st.rotulo if st else '',
                    'alimentadores': sorted(de_set.get(st.codigo, [])) if st else [],
                    'tramo': del_perfil.get(clave_codigo(m.medidor), '')})
    return {'centrales': out}


def _demanda_por_barra(ws: Workspace, ctx: JobContext, pares: list[tuple[str, str]],
                       periodo: str | None, centrales_tramo: dict[str, str] | None = None) -> dict:
    """La máxima de cada barra de SET con medidor y sus alimentadores en esa fecha y hora
    (022:RF-37 a RF-46). El usuario, el 2026-10-17: «cuando se identifique el máximo valor
    en la barra, los alimentadores de la misma barra se deben calibrar con la misma fecha
    del medidor de barra, con fecha coincidente». Los de una barra sin medidor, con su
    propia máxima (RF-42).
    """
    from collections import defaultdict

    from ..demanda_medida import (Cabecera, DemandaError, barras_de_calibracion,
                                  leer_medidores_de_barra, maxima_de_barra, maximas,
                                  valor_de_barra_en)

    estructura = estructura_del_espacio(ws)
    if estructura is None:
        raise UserError('La máxima por barra necesita la estructura de la empresa (022:RF-1): '
                        'súbala en Excel o póngala en el perfil.')
    libros = _libros_de_cabecera(ws, periodo)                          # 025:RF-8
    alias = demanda_alias()

    def duenio(a: str) -> str:
        return a[len('Central '):].strip() if a.lower().startswith('central ') else a

    # 022:RF-88: las centrales en el tramo de un alimentador, las que dice el operador y las
    # del formulario de la central de un alimentador (pares «Central NA205»); se miden con
    # él, en su instante, y no van a la barra.
    en_tramo = {m: duenio(a).upper() for a, m in pares if a.lower().startswith('central ')}
    # Solo las de los alimentadores pedidos: la de Nasca (perfil, NA205) entraba en Chincha
    # y traía la SET 51 a su calibración (DIgSILENT, 2026-10-28).
    del_sistema = {duenio(a).upper() for a, _m in pares if a}
    en_tramo.update({m.strip(): a.strip().upper() for m, a in (centrales_tramo or {}).items()
                     if m.strip() and a.strip().upper() in del_sistema})
    vistos = {m.upper() for _a, m in pares}
    pares = list(pares) + [(f'Central {a}', m) for m, a in en_tramo.items() if m.upper() not in vistos]
    try:
        medidores = leer_medidores_de_barra(_demanda_ruta(ws, 'medidores'), alias)
        alimentadores = sorted({duenio(a).upper() for a, _m in pares if a})
        barras, avisos = barras_de_calibracion(estructura, medidores, alimentadores,
                                               _kv_alimentadores(ws), en_tramo)
        ctx.log(f'Máxima por barra de SET: {len(barras)} barra(s) con medidor para '
                f'{len(alimentadores)} alimentador(es)' + (f' · {periodo}' if periodo else ''))
        # Los libros se abren una vez para la barra y todos sus instantes (022:RF-84).
        cabecera = Cabecera(libros, alias)
        de_barra = maximas(libros, [(b.clave, m) for b in barras for m in b.medidores + b.centrales],
                           alias=alias, cancelado=ctx.cancel.is_set, cabecera=cabecera)
        # Las curvas de los alimentadores de las SET con barra de 60 kV, con los libros ya
        # abiertos: su instante tiene que tener registro en todos (022:RF-91).
        con_alta = {f for b in barras if b.alta or b.de_alta for f in b.alimentadores}
        de_alimentador = maximas(libros, [(a, m) for a, m in pares if duenio(a).upper() in con_alta],
                                 alias=alias, periodo=periodo, cancelado=ctx.cancel.is_set,
                                 cabecera=cabecera) if con_alta else []
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    curva_de = {(r.alimentador, r.medidor): r.curva for r in de_barra if r.curva}
    fechas_de: dict[str, list[set]] = defaultdict(list)
    for r in de_alimentador:
        if r.curva:
            fechas_de[duenio(r.alimentador).upper()].append({f for f, kw, _q in r.curva if kw is not None})

    def comunes_de_la_set(alta_clave: str) -> set | None:
        """Los registros que tienen todos los medidores de los alimentadores de la SET de
        esa barra de 60 kV (022:RF-91), o ``None`` si ninguno tiene curva."""
        feeders = {f for b in barras if b.clave == alta_clave or b.de_alta == alta_clave
                   for f in b.alimentadores}
        conjuntos = [s for f in feeders for s in fechas_de.get(f, [])]
        return set.intersection(*conjuntos) if conjuntos else None
    instantes: dict[str, datetime] = {}
    info = []
    maxima_alta: dict[str, dict] = {}
    # 022:RF-84: primero la máxima de cada barra de 60 kV; sus barras de 22,9 y 10 kV se
    # leen después, en esa misma fecha y hora, y no en la suya.
    for b in sorted(barras, key=lambda x: not x.alta):
        # Un transformador sin registros en el periodo (B-PA6T1 en julio de 2026) no entra
        # en la suma: con él, ninguna fecha era común y la barra se quedaba sin instante.
        sin_curva = [m for m in b.medidores if not curva_de.get((b.clave, m))]
        if sin_curva and len(sin_curva) < len(b.medidores):
            avisos.append(f'{b.clave}: {", ".join(sin_curva)} sin registros'
                          + (f' en {periodo}' if periodo else '')
                          + '; la barra se suma con los demás (022:RF-84).')
        curvas = [curva_de[(b.clave, m)] for m in b.medidores if curva_de.get((b.clave, m))]
        alta = maxima_alta.get(b.de_alta) if b.de_alta else None
        if alta is not None:
            mx = valor_de_barra_en(curvas, alta['fecha']) if curvas else None
            if mx is None and b.medidores:
                avisos.append(f'{b.clave}: sin el registro de {", ".join(b.medidores)} el '
                              f'{alta["fecha"]}, el de la máxima de {b.de_alta}; sus alimentadores '
                              'se calibran igual en esa fecha y hora (022:RF-84).')
            mx = mx or {'fecha': alta['fecha'], 'kw': None, 'kvar': None, 'registros': 0}
        else:
            mx = maxima_de_barra(curvas, periodo) if curvas else None
            comunes = comunes_de_la_set(b.clave) if b.alta and mx is not None else None
            if comunes is not None and mx['fecha'] not in comunes:
                # 022:RF-91: CHNB6T1 dio su máxima el 2026-07-24 11:45 y CHN101, CHN102 y
                # CHN201 no tienen ese registro: se quedaban sin calibrar. La máxima de la
                # barra, entre los registros que tienen también todos sus alimentadores.
                filtradas = [[x for x in c if x[0] in comunes] for c in curvas]
                otra = maxima_de_barra(filtradas, periodo) if all(filtradas) else None
                if otra is not None:
                    avisos.append(f"{b.clave}: su máxima del {mx['fecha']} no tiene registro en todos "
                                  f"sus alimentadores; se toma la del {otra['fecha']}, la mayor con "
                                  'registro en todos (022:RF-91).')
                    mx = otra
                else:
                    avisos.append(f'{b.clave}: ningún registro común con sus alimentadores'
                                  + (f' en {periodo}' if periodo else '')
                                  + '; los que no tengan su registro, con su propia máxima (022:RF-91).')
            if mx is None:
                avisos.append(f'{b.clave}: sin registros comunes de {", ".join(b.medidores)}'
                              + (f' en {periodo}' if periodo else '')
                              + ('; sus barras de media, con su propia máxima (022:RF-84).' if b.alta else
                                 '; sus alimentadores, con su propia máxima (022:RF-42).'))
                continue
        if b.alta:
            maxima_alta[b.clave] = mx
        centrales = []
        for m in b.centrales:
            punto = next((x for x in curva_de.get((b.clave, m)) or [] if x[0] == mx['fecha']), None)
            centrales.append({'medidor': m, 'kw': punto[1] if punto else None,
                              'kvar': punto[2] if punto else None})
        for f in b.alimentadores:
            instantes[f] = mx['fecha']
        info.append({'clave': b.clave, 'set': b.set_codigo, 'kv': b.kv, 'suelta': b.suelta,
                     'alta': b.alta, 'de_alta': b.de_alta if alta is not None else '',  # RF-84
                     'transformadores': b.transformadores,                         # RF-87
                     'medidores': b.medidores, 'centrales': centrales,
                     'alimentadores': b.alimentadores, 'fecha': mx['fecha'].isoformat(sep=' '),
                     'kw': mx['kw'], 'kvar': mx['kvar'], 'registros': mx['registros']})
        valor = f'{mx["kw"]:,.1f} kW' if mx['kw'] is not None else 'sin registro'
        suma = ' + '.join(f'{m} ({b.transformadores[m]})' if b.transformadores.get(m) else m
                          for m in b.medidores)
        ctx.log(f'  {b.clave}: {valor} el {mx["fecha"]} ({suma})'
                + (f', instante de {b.de_alta}' if alta is not None else '')
                + (f'; {", ".join(b.alimentadores)} en esa fecha y hora' if b.alimentadores else ''))
    # 022:RF-89: la barra de 60 kV tiene que dar al menos lo que dan sus barras de media en
    # su instante, menos la generación de sus centrales. CHNB6T1 (Chincha Nueva) marcó 8,3
    # frente a ~3 300 kW de media (2026-10-28): otra unidad (MW) o un medidor mal
    # configurado. El instante se usa igual (la máxima no cambia con la unidad), y se avisa.
    for alta in (x for x in info if x['alta'] and x['kw'] is not None):
        media = [x for x in info if x.get('de_alta') == alta['clave'] and x['kw'] is not None]
        neto = (sum(x['kw'] for x in media)
                - sum(c['kw'] or 0.0 for x in media for c in x['centrales']))
        if media and neto > 0 and alta['kw'] < 0.5 * neto:
            avisos.append(f"{alta['clave']}: {alta['kw']:,.1f} kW frente a {neto:,.1f} kW de sus barras de "
                          f"media en ese instante; revise la unidad (¿MW?) o el medidor "
                          f"{', '.join(alta['medidores'])}. El instante se usa igual (022:RF-89).")
    grupos: dict[Any, list[tuple[str, str]]] = defaultdict(list)
    for a, m in pares:
        grupos[instantes.get(duenio(a).upper())].append((a, m))
    # Cada instante (uno por SET con barra de 60 kV) con los mismos libros ya abiertos: un
    # hilo por instante abría cada uno su copia de los .xls de ~400 MB y la web se quedó sin
    # memoria con Nasca (2026-10-27); abrir es lo que cuesta, no buscar un registro.
    res = []
    try:
        for inst, ps in grupos.items():
            res += maximas(libros, ps, alias=alias, periodo=None if inst else periodo,
                           instante=inst, cancelado=ctx.cancel.is_set, cabecera=cabecera)
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    orden = {m: i for i, (_a, m) in enumerate(pares)}
    res.sort(key=lambda r: orden.get(r.medidor, len(orden)))
    for aviso in avisos:
        ctx.log(f'  aviso: {aviso}')
    with ws.lock:
        ws.curvas_cabecera = {ctx.job.id: {r.medidor: {'curva': r.curva, 'fuera': r.fuera_de_curva}
                                           for r in list(res) + list(de_barra) if r.curva}}
        ws.criterio_cabecera = {ctx.job.id: {'periodo': periodo, 'instante': None,
                                             'instantes': instantes}}
    return {'resultados': [r.to_dict() for r in res], 'cancelado': False, 'periodo': periodo,
            'instante': None, 'por_barra': True, 'barras': info, 'avisos': avisos}


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


def demanda_medidores_externos(ws: Workspace, red: list[str]) -> dict:
    """Medidores del libro cuyo alimentador no es de la red (021:RF-26), y las centrales
    que guarda el perfil (021:RF-27).

    La red son los alimentadores del proyecto (``red``) y, si hay una entrada cargada, los
    de la entrada. En el libro de Electro Dunas la central de Nasca sale como CTBarra,
    CTLADOSET y CTLADOCARGA: no se reconoce por el nombre, sino porque no es ninguno de
    los alimentadores de la red.
    """
    from ..demanda_medida import DemandaError, clave_codigo, leer_medidores
    from ..naming import feeder_short_name
    from ..perfil_empresa import PerfilError, centrales_termicas, datos_perfil

    de_la_red = {clave_codigo(a) for a in red if a.strip()}
    if ws.dataset is not None:
        de_la_red |= {clave_codigo(feeder_short_name(f)) for f in ws.dataset.feeder_ids()}
    try:
        filas = leer_medidores(_demanda_ruta(ws, 'medidores'), demanda_alias())
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    grafias = _grafias(ws)                                                      # 022:RF-81
    de_la_red |= {clave_codigo(e) for a in list(de_la_red) for e in grafias(a)}
    externos = [{'alimentador': m.alimentador, 'medidor': m.medidor} for m in filas
                if clave_codigo(m.alimentador) not in de_la_red]
    try:
        centrales, aviso = centrales_termicas(datos_perfil()), None
    except PerfilError as exc:
        centrales, aviso = {}, str(exc)
    return {'medidores': externos, 'centrales_perfil': centrales, 'aviso_perfil': aviso}


def demanda_central(ws: Workspace, job_id: str, *, alimentador: str, cabecera: str,
                    generacion: str, llegada: str, salida: str) -> dict:
    """Máxima de demanda de un alimentador con central, con las curvas de la última
    máxima buscada (021:RF-28 a RF-34). Es memoria, no libros: una fracción de segundo.
    ``LookupError`` si falta una curva: la API da 404."""
    from ..demanda_medida import clave_codigo, demanda_con_central

    with ws.lock:
        curvas = ws.curvas_cabecera.get(job_id)
    if curvas is None:
        raise LookupError('La curva no es de la última máxima buscada: vuelva a buscarla.')

    def curva(medidor: str) -> list:
        nombre = next((m for m in curvas if clave_codigo(m) == clave_codigo(medidor)), None)
        if nombre is None:
            raise LookupError(f'El medidor {medidor} no está en la última máxima buscada: '
                              'búsquela con los de la central.')
        return curvas[nombre]['curva']

    criterio = ws.criterio_cabecera.get(job_id) or {}
    # 022:RF-40: con la máxima por barra, el instante de la barra de su alimentador.
    instante = (criterio.get('instantes') or {}).get(alimentador) or criterio.get('instante')
    res = demanda_con_central(curva(cabecera), curva(generacion), curva(llegada), curva(salida),
                              criterio.get('periodo'), instante)
    return {'alimentador': alimentador, 'cabecera': cabecera, 'generacion': generacion,
            'llegada': llegada, 'salida': salida, **res.to_dict()}


def demanda_curva_central(ws: Workspace, job_id: str, *, alimentador: str, cabecera: str,
                          generacion: str, llegada: str, salida: str,
                          desde: datetime | None = None, hasta: datetime | None = None) -> dict:
    """Curva de la demanda de un alimentador con central (021:RF-47, RF-48), con la forma
    de la de un medidor; la máxima es la de la demanda, el objetivo del ajuste."""
    from ..demanda_medida import clave_codigo, curva_de_demanda, reducir_curva

    with ws.lock:
        curvas = ws.curvas_cabecera.get(job_id)
    if curvas is None:
        raise LookupError('La curva no es de la última máxima buscada: vuelva a buscarla.')

    def curva(medidor: str) -> list:
        nombre = next((m for m in curvas if clave_codigo(m) == clave_codigo(medidor)), None)
        if nombre is None:
            raise LookupError(f'El medidor {medidor} no está en la última máxima buscada.')
        return curvas[nombre]['curva']

    criterio = ws.criterio_cabecera.get(job_id) or {}
    instante = (criterio.get('instantes') or {}).get(alimentador) or criterio.get('instante')
    puntos, res = curva_de_demanda(curva(cabecera), curva(generacion), curva(llegada), curva(salida),
                                   criterio.get('periodo'), instante)
    if not puntos:
        raise LookupError(f'{alimentador}: sin demanda con la central ({res.error}).')
    tramo = reducir_curva(puntos, desde, hasta, max_puntos=len(puntos) or 1)
    reducidos = reducir_curva(tramo, max_puntos=CURVA_MAX_PUNTOS)
    return {'medidor': f'Demanda {alimentador}', 'inicio': puntos[0][0].isoformat(),
            'fin': puntos[-1][0].isoformat(),
            # La máxima marcada es la del objetivo (RF-48), que descarta las transferencias.
            'maxima': {'fecha': (res.fecha or '').replace(' ', 'T'), 'kw': res.demanda_kw}
            if res.fecha else {'fecha': max(puntos, key=lambda p: p[1])[0].isoformat(),
                               'kw': max(p[1] for p in puntos)},
            'puntos': [[f.isoformat(), kw, kvar] for f, kw, kvar in reducidos],
            'total': len(tramo), 'reducida': len(reducidos) < len(tramo), 'fuera_de_curva': 0}


def demanda_clientes(ws: Workspace, alimentadores: list[str] | None = None,
                     *, periodo: str | None = None, instante: datetime | None = None) -> dict:
    """Clientes importantes cruzados con los suministros (RF-33 a RF-37); con
    ``alimentadores``, solo los de esos alimentadores por su radial (RF-43)."""
    from ..demanda_medida import (DemandaError, cruzar, del_alimentador, leer_clientes,
                                  leer_suministros, registros_de_maxima)

    alias = demanda_alias()
    try:
        suministros, avisos_s = leer_suministros(_demanda_ruta(ws, 'suministros'), alias)
        libro = _demanda_ruta(ws, 'clientes', periodo=periodo)
        clientes, avisos_c = leer_clientes(libro, alias)
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    # Spec 013, RF-16: de qué libro y de qué mes salen los clientes; con siete libros
    # mensuales en la carpeta, el operador no lo deduce del nombre de la fuente.
    mes = next((str(x.get('mes') or '') or None
                for x in (ws.demanda.get('clientes') or {}).get('catalogo') or []
                if x.get('activo') and x.get('nombre') == libro.name), None)
    cruzados, aparte = cruzar(clientes, suministros)
    alimentadores = [a.strip() for a in alimentadores or [] if a.strip()]
    de_otros = 0
    if alimentadores:
        cruzados, aparte, de_otros = del_alimentador(cruzados, aparte, alimentadores)
    # 004:RF-66: la reactiva de cada cliente en el registro de 15 minutos de su POT, de su
    # hoja del mismo libro; solo los cruzados (los de un alimentador, en el plan).
    try:
        registro, avisos_r = registros_de_maxima(libro, {c.codigo: c.pot for c in cruzados},
                                                 instante=instante)
    except DemandaError as exc:
        registro, avisos_r = {}, [str(exc)]
    for c in cruzados:
        if c.codigo in registro:
            c.fecha_registro, c.q_registro_kvar, c.p_registro_kw = registro[c.codigo]
    avisos_c = avisos_c + avisos_r
    return {
        'alimentadores': alimentadores,
        'libro': libro.name,
        'mes': mes,
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


def _kva_reconstruido(ws: Workspace, project: str, alimentador: str,
                      kva: dict[str, float]) -> tuple[dict[str, float], set[str]]:
    """El kVA de un alimentador como quedó en el DGS por sistema reconstruido (022:RF-63).

    La reconstrucción por medida pasa SED de un alimentador a otro (TM106 recibió las de
    TM104 en Chincha, 2026-10-18); el kVA de la entrada original seguía dando a TM106 sus
    339 kW y no se calibraba. Las SED salen de la metadata del DGS; el kVA de cada una, de
    los alimentadores que intervinieron. Sin reconstrucción, el de la entrada tal cual.
    Devuelve también los alimentadores que intervinieron (vacío si ninguno): entonces un
    kVA vacío es una red que lo cedió todo.
    """
    sistema = sistema_del_proyecto(ws, project)
    if sistema is None:
        return kva, set()
    grupo = ws.groups.get(sistema['grupo']) or {}
    if not grupo.get('dgs') or not grupo.get('feeder_metadata'):
        return kva, set()
    dgs = Path(str(grupo['dgs']))
    manifest = dgs.with_name(f"{sistema['grupo']}_manifest.json")
    metadata = Path(str(grupo.get('feeder_metadata') or ''))
    try:
        recs = (json.loads(manifest.read_text(encoding='utf-8')).get('estructura') or {}).get(
            'reconstrucciones') or []
    except (OSError, ValueError):
        return kva, set()
    implicados = {r['alimentador'] for r in recs if r.get('cargas_pasadas')} | {
        r['donante'] for r in recs if r.get('cargas_pasadas')}
    if alimentador not in implicados:
        return kva, set()
    try:
        asignadas = {a['substation'] for a in json.loads(metadata.read_text(encoding='utf-8'))
                     .get('assignments', [])
                     if a.get('class_name') == 'ElmSubstat' and a.get('feeder') == alimentador}
    except (OSError, ValueError):
        return kva, set()
    todas: dict[str, float] = {}
    for f in sorted(implicados):
        todas.update(kva if f == alimentador else _kva_de_la_entrada(ws, f)[0])
    return {sed: todas[sed] for sed in sorted(asignadas) if sed in todas}, implicados


def _capacidad_de_la_red(kva_entrada: dict[str, float], fijas: dict, fp: float | None,
                         reconstruido: bool = False) -> float | None:
    """Lo más que puede dar la red de un alimentador en kW (022:RF-55): sus fijas con su
    medida y las demás SED con su kVA instalado por el factor de potencia. ``None`` sin kVA
    de la entrada, para no rechazar sin saber; reconstruido, vacío es cero: TM104 cedió toda
    su red a TM106 y su medidor de 31 kW quedaba en el plan sin ninguna carga."""
    if not kva_entrada and not reconstruido:
        return None
    if reconstruido:
        # Las fijas del libro de suministros van por su RADIAL de siempre: si su SED pasó a
        # otro alimentador, ya no son de esta red (las de TM104 seguían sumando tras cederla).
        fijas = {sed: f for sed, f in fijas.items() if sed in kva_entrada}
    escaladas = sum(kva for sed, kva in kva_entrada.items() if sed not in fijas)
    return sum(f.kw for f in fijas.values()) + escaladas * (fp or 1.0)


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
    # ``feeder_ids`` da el NetworkID entero («NET_2030_142_IN111»), que nunca coincidía
    # con el código del libro: IN111 y TA225 (2026-10-14) se calibraban sin el kVA de la
    # entrada con un aviso falso de «no está en la entrada cargada».
    feeder = next((f for f in ws.dataset.feeder_ids()
                   if clave_codigo(feeder_short_name(f)) == clave or clave_codigo(f) == clave),
                  None)
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
    if periodo and source.is_dir() and len(active) > 1 and not any(
            str(item.get('mes') or '').strip() == periodo for item in active):
        # 025:RF-11 (013:RF-13): una carpeta de libros mensuales sin el del mes de la
        # máxima. Con la de 2025, la máxima de un alimentador puede caer en un mes cuyo
        # libro no llegó: se dice y sus SED se reparten por kVA, sin bloquear a los demás.
        return ClientPeriodEvidence(
            status='NO_CLIENT_BOOK', period=None, file=None, sheet=None,
            fingerprint=None, period_origin=None,
            warning=(f'Sin libro de clientes importantes de {periodo} en {source.name}: '
                     'sus SED se reparten por kVA.'),
        )
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


def _central_del_plan(ws: Workspace, job_id: str, alimentador: str, cabecera: str,
                      declarada: dict | None, avisos: list[str], pre: str) -> dict | None:
    """La central de un alimentador para su plan (021:RF-25, RF-30, RF-33), o ``None``.

    Sin la barra no se puede calibrar con ella (RF-25); con el balance de la barra roto,
    se avisa y se calibra sin ella (RF-30).
    """
    if not declarada:
        return None
    nodo = str(declarada.get('nodo') or '').strip()
    if not nodo:
        # 028:RF-12: sin barra declarada, la del generador que encontró el último escaneo.
        from ..escaneo import nodo_de_central

        proyecto = next((p for p, e in ws.escaneo.items() if alimentador in (e.get('alimentadores') or {})), None)
        nodo = nodo_de_central(ws.escaneo.get(proyecto), alimentador) or ''
        if nodo:
            avisos.append(f'{pre}la central va en la barra {nodo}, la de su generador en el escaneo (028:RF-12).')
    if not nodo:
        raise UserError(f'{alimentador}: indique la barra de la central en DIgSILENT (021:RF-25).')
    try:
        maxima = demanda_central(ws, job_id, alimentador=alimentador, cabecera=cabecera,
                                 generacion=declarada['generacion'], llegada=declarada['llegada'],
                                 salida=declarada['salida'])
    except LookupError as exc:
        raise UserError(f'{alimentador}: {exc}') from exc
    if maxima.get('error'):
        avisos.append(f"{pre}central no usada: {maxima['error']} (021:RF-30).")
        return None
    return {'nodo': nodo, 'medidores': {k: declarada[k] for k in ('generacion', 'llegada', 'salida')},
            'maxima': maxima}


def ajuste_plan(ws: Workspace, project: str, maximas: list[dict], medidor: str,
                tolerancia: float, medidores: list[str] | None = None,
                desconectados: list[str] | None = None, *, job_id: str = '',
                centrales: dict[str, dict] | None = None,
                tension_fuente_pu: float | None = None,
                completar_bancos: bool = False,
                barras: list[dict] | None = None) -> dict:
    """Plan para ``tools/ajuste_cabecera_pf.py`` (spec 006, RF-1 a RF-3, RF-10).

    ``maximas`` es el resultado del trabajo de la máxima de cabecera que el operador ve
    en su tabla: el objetivo es ese mismo valor (RF-1), sin volver a abrir los libros de
    cabecera, que pesan cientos de MB. Con varios alimentadores (spec 008, RF-12) hay un
    plan por alimentador, el mismo JSON de la spec 006, y un solo token que los recorre.
    ``desconectados`` son los Nis que el operador desmarcó en la tabla del cruce (RF-26):
    van aparte en el plan, y el guion decide qué carga de SED se queda sin clientes.
    """
    import time as _time

    from ..ajuste_cabecera import AjusteError, Objetivo, fijas_de, objetivo_de
    from ..demanda_medida import periodo_de_fecha
    from ..perfil_empresa import PerfilError, bancos_kvar_por_tension, datos_perfil, factor_potencia_cargas
    from ..powerfactory_binding import PowerFactoryProjectBinding, caso_base_verificado

    if not project.strip():
        raise UserError('Elija el proyecto de DIgSILENT.')
    filas = _medidores_del_ajuste(maximas, medidor, medidores)
    # 025:RF-18: un año cada vez; antes que nada, para que el motivo sea este.
    anios_medidos = {int(str(f['fecha'])[:4]) for f in filas
                     if f.get('fecha') and not f.get('error') and str(f['fecha'])[:4].isdigit()}
    if len(anios_medidos) > 1:
        raise UserError('Las máximas son de años distintos (' + ', '.join(map(str, sorted(anios_medidos)))
                        + '): se calibra un año cada vez; busque la máxima con un solo año.')
    anio_medicion = next(iter(anios_medidos), None)
    # 015:RF-54, RF-57: el factor de potencia de las escaladas, del perfil de empresa.
    try:
        fp_cargas = factor_potencia_cargas(datos_perfil())
        # 015:RF-62: el mínimo de las fijas, por su banco propio.
        fp_min_fijas = factor_potencia_cargas(datos_perfil(), 'factor_potencia_minimo_fijas')
        # 021:RF-65: el tamaño de los bancos que falten, por tensión.
        por_tension = bancos_kvar_por_tension(datos_perfil()) if completar_bancos else None
    except PerfilError as exc:
        raise UserError(f'Perfil de empresa: {exc}') from exc
    requested_feeders = [str(row.get('alimentador') or '').strip() for row in filas]
    action_context = native_action_context(ws, project, requested_feeders, 'ajuste')
    project_binding = PowerFactoryProjectBinding.from_dict(action_context['binding'])
    varios = len(filas) > 1
    stamp = _time.strftime('%Y%m%d_%H%M%S')
    ws.plans_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    fuera = {str(c).strip() for c in desconectados or [] if str(c).strip()}
    ajustes, avisos, paths = [], [], []
    # 025:RF-14, RF-17, RF-18: el año de la medición decide en qué casos se calibra. Los
    # casos sin año son los del año con que se calibraron; otro año va a «Sin proyecto
    # <año>», copia del «Caso base», sin mezclarse con el otro (usuario, 2026-10-23).
    from ..estudios_pf import SIN_PROYECTO
    anio_base, aviso_anio = anio_de_los_casos(ws, project)
    anio_casos = (anio_medicion if anio_medicion and anio_base and anio_medicion != anio_base
                  else None)
    if aviso_anio:
        avisos.append(aviso_anio)
    # El mismo nombre que da ``tools/casos_pf.nombre_caso``; el guion lo confirma en su informe.
    caso_calibracion = f'{SIN_PROYECTO} {anio_casos}' if anio_casos else SIN_PROYECTO
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
        alimentador = str(fila.get('alimentador') or '').strip()
        pre = f'{alimentador}: ' if varios and alimentador else ''
        # Spec 021: con central, el objetivo es por zonas y en el registro de la máxima de
        # demanda (RF-33) o en el coincidente (RF-50); el mes de los clientes, el de ese
        # registro. La cabecera puede ser negativa (NA205 el 2026-07-23 10:00: −1 520,8 kW,
        # la central exporta hacia la SET): el objetivo del plan es la demanda del
        # alimentador, aguas arriba + aguas abajo, y la cabecera queda como dato.
        central = (_central_del_plan(ws, job_id, alimentador, str(fila.get('medidor') or ''),
                                     (centrales or {}).get(alimentador), avisos, pre)
                   if alimentador and not fila.get('error') else None)
        try:
            if central:
                m = central['maxima']
                objetivo = Objetivo(
                    kw=float(m['demanda_kw']),
                    kvar=float((m.get('arriba_kvar') or 0.0) + (m.get('abajo_kvar') or 0.0)),
                    medidor=str(fila.get('medidor') or ''), alimentador=alimentador,
                    fecha=m.get('fecha'))
            else:
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
        maximum_period = periodo_de_fecha(central['maxima']['fecha'] if central else objetivo.fecha)
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
        kva_entrada, aviso = _kva_de_la_entrada(ws, alimentador)
        if aviso:
            avisos.append(pre + aviso)
        kva_entrada, implicados = _kva_reconstruido(ws, project, alimentador,
                                                    kva_entrada)                # 022:RF-63
        clientes: list[dict] = []
        # 025:RF-11: sin libro del mes de su máxima, todas sus SED por kVA.
        if (hay_suministros(ws) and ws.demanda.get('clientes')
                and client_period.status != 'NO_CLIENT_BOOK'):
            # 004:RF-67: los clientes fijos en el registro del objetivo (el instante de su
            # barra de 60 kV o la máxima del alimentador), coincidentes con él.
            try:
                instante_obj = datetime.fromisoformat(str(objetivo.fecha)) if objetivo.fecha else None
            except ValueError:
                instante_obj = None
            clientes = demanda_clientes(
                ws, sorted(implicados) or [alimentador], periodo=maximum_period,
                instante=instante_obj,
            )['cruzados']
            if implicados:
                # 022:RF-63: el libro de suministros dice el alimentador de siempre (RADIAL);
                # en una red reconstruida, los clientes son los de sus SED en el DGS: los
                # fijos de TM104 pasan con su SED a TM106.
                clientes = [c for c in clientes if str(c.get('sed') or '').strip() in kva_entrada]
        elif not paths:
            avisos.append('Sin libros de suministros y de clientes: todas las SED se reparten por kVA.')
        apagados = [c for c in clientes if str(c.get('codigo') or '').strip() in fuera]
        clientes = [c for c in clientes if str(c.get('codigo') or '').strip() not in fuera]
        fixed = fijas_de(clientes, objetivo, fp_min_fijas)
        fixed_evidence = [{
            'sed': item.sed, 'p_kw': item.kw, 'q_kvar': item.kvar, 'fp': item.fp,
            'clientes': list(item.clientes), 'derivaciones': list(item.derivaciones),
            'avisos': list(item.avisos),
        } for item in fixed.values()]
        for item in fixed.values():
            avisos.extend(pre + warning for warning in item.avisos if pre + warning not in avisos)
        capacidad = _capacidad_de_la_red(kva_entrada, fixed, fp_cargas, bool(implicados))
        if not central and capacidad is not None and objetivo.kw > capacidad:
            # 022:RF-55: Chincha (2026-10-18), TM106 medía 3 133 kW con unos 230 kVA: su
            # factor de escala de 13,7 hundía la tensión y el sistema entero no convergía.
            motivo = (f'{alimentador}: su medidor da {objetivo.kw:,.0f} kW y su red puede dar '
                      f'{capacidad:,.0f} kW (fijas más kVA instalado de las escaladas por el FP); '
                      'no se calibra: revise el medidor o si parte de su carga está en otro '
                      'alimentador (022:RF-55).')
            if not varios:
                raise UserError(motivo)
            avisos.append(motivo)
            continue
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
            # 022:RF-41b, RF-44: la barra de SET con medidor del alimentador, si la tiene.
            'barra_set': next((b for b in barras or []
                               if alimentador.upper() in b.get('alimentadores', [])), None),
            # 021:RF-61: la tensión en la fuente que indicó el operador, o None.
            'tension_fuente_pu': tension_fuente_pu,
            # 021:RF-64, RF-65: poner los bancos que falten, con el tamaño de su tensión.
            'completar_bancos': completar_bancos,
            'bancos_kvar_por_tension': {str(k): v for k, v in (por_tension or {}).items()},
            # 015:RF-54: solo las escaladas; None deja la Q del archivo (RF-55).
            'factor_potencia_cargas': fp_cargas,
            'factor_potencia_minimo_fijas': fp_min_fijas,
            # 020:RF-6 a RF-12: las fichas del perfil para proponer transformadores nuevos;
            # el guion las valida con la misma lectura (020:RF-31).
            'transformadores_sed': (datos_perfil().get('calibracion') or {}).get(
                'transformadores_sed'),
            'caso_base_sin_verificar': {},
            # 025:RF-14, RF-24: el año de la medición y el de los casos en que se graba.
            'anio_medicion': anio_medicion, 'anio_casos': anio_casos, 'caso': caso_calibracion,
            # 014:RF-10: la demanda que dejó la última calibración, para ver lo manual; la
            # de los casos de este año (025:RF-20).
            'ultima_calibracion': (ws.calibraciones.get(clave_calibracion(project, anio_casos))
                                   or {}).get(alimentador),
        }
        if central:
            plan['central'] = central
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
    # 022:RF-52, RF-53: en un proyecto por sistema eléctrico, los que no tienen medidor se
    # dicen y quedan con la demanda del archivo, en los mismos flujos que los calibrados.
    sistema = sistema_del_proyecto(ws, project)
    if sistema is not None:
        calibrados = {f.upper() for f in feeders}
        sistema['calibrados'] = feeders
        sistema['sin_medidor'] = [a for a in sistema['alimentadores']
                                  if a.upper() not in calibrados]
        sistema.pop('medidores', None)
        if sistema['sin_medidor']:
            avisos.append(f"{sistema['grupo']}: {len(sistema['sin_medidor'])} de "
                          f"{len(sistema['alimentadores'])} alimentadores sin medidor "
                          f"({', '.join(sistema['sin_medidor'])}) quedan con la demanda del "
                          'archivo, en los mismos flujos que los calibrados (022:RF-53).')
    with ws.lock:
        ws.cargas_planes[token] = {'path': paths[0], 'paths': paths, 'project': project.strip(),
                                   'feeders': feeders, 'applicable': True,
                                   'kind': 'ajuste_cabecera', 'sistema': sistema,
                                   'anio_casos': anio_casos}
    primero = ajustes[0]
    return {'token': token, 'project': project.strip(), 'feeder': primero['feeder'],
            'objetivo': primero['objetivo'], 'tolerancia': tolerancia,
            'n_clientes': primero['n_clientes'], 'n_kva_entrada': primero['n_kva_entrada'],
            'n_sed_fijas': primero['n_sed_fijas'],
            'n_sed_escaladas_estimadas': primero['n_sed_escaladas_estimadas'],
            'periodo': primero['periodo'], 'client_evidence': primero['client_evidence'],
            'source': plan['source'], 'project_binding': plan['project_binding'],
            'native_action_context': action_context,
            'feeders': feeders, 'ajustes': ajustes, 'avisos': avisos, 'sistema': sistema,
            'anio_medicion': anio_medicion, 'anio_casos': anio_casos, 'caso': caso_calibracion}


def clave_calibracion(project: str, anio_casos: int | None) -> str:
    """Clave de ``ws.calibraciones``: el proyecto, o ``<proyecto>@<año>`` para los casos de
    un año aparte (025:RF-20). La de 2025 no se compara con lo que dejó la de 2026."""
    p = project.strip()
    return f'{p}@{anio_casos}' if anio_casos else p


def anio_de_los_casos(ws: Workspace, project: str) -> tuple[int | None, str | None]:
    """Año de medición de los casos sin año del proyecto, y un aviso si se dedujo (025:RF-17).

    Se registra en la primera calibración que lo sabe. Un proyecto calibrado antes de esta
    spec no lo guardó: sus casos se toman como del año más reciente de la medición de
    cabecera (en Electro Dunas, los proyectos de 2026 calibrados con la de 2026), y se dice.
    """
    p = project.strip()
    if p in ws.anios_casos:
        return int(ws.anios_casos[p]), None
    registros = ws.calibraciones.get(p) or {}
    anios = {int(r['anio']) for r in registros.values() if isinstance(r, dict) and r.get('anio')}
    if len(anios) == 1:
        return anios.pop(), None
    reciente = max((ws.demanda.get('cabecera') or {}).get('anios') or [], default=None)
    if registros and reciente:
        return int(reciente), (
            f'«{p}» se calibró sin guardar el año de la medición: sus «Sin proyecto» y «Con '
            f'proyecto» se toman como de {reciente}, el año más reciente de la cabecera (025:RF-17).')
    return None, None


def _guardar_calibracion(ws: Workspace, project: str, feeder: str, informe: dict, *,
                         anio_casos: int | None = None, anio_medicion: int | None = None) -> None:
    """La demanda que dejó la calibración en cada SED (015, T8; 014:RF-10).

    Por proyecto y año de los casos (025:RF-20), con el año de la medición.

    Sin error y sin revertir: una calibración que no quedó en el escenario no es con la
    que comparar lo que cambie el operador. Solo cuenta si el guion guardó el escenario
    (``escenarios``) o lo encontró ya calibrado: en NA205 (2026-10-17) se registró una que
    no pasó la validación física y no se guardó, y en la siguiente las 93 cargas salían
    «cambiadas a mano», fijas, y ninguna zona de la central quedaba para escalar.
    """
    ya = (informe.get('decision_carga_nativa') or {}).get('status') == 'YA_CARGADO_VALIDADO'
    if (informe.get('error') or informe.get('calibracion_revertida') or not informe.get('sed')
            or not (informe.get('escenarios') or ya)):
        return
    sed = {x['sed']: [(x.get('despues') or {}).get('kw'), (x.get('despues') or {}).get('kvar')]
           for x in informe['sed'] if (x.get('despues') or {}).get('kw') is not None}
    # 015:RF-65: los clientes fijos con su FP real (EA/ERI) y el corregido, para el informe.
    fijas = []
    for x in informe['sed']:
        for d in x.get('derivaciones') or []:
            comp = d.get('compensado') or {}
            fijas.append({
                'sed': x['sed'], 'cliente': d.get('cliente'), 'p_kw': d.get('p_kw'),
                'fp_real': comp.get('fp_ea_eri', d.get('fp')), 'fp_corregido': d.get('fp'),
                'q_real_kvar': comp.get('q_ea_eri_kvar', d.get('q_kvar')),
                'q_kvar': d.get('q_kvar'), 'compensado': bool(comp)})
    with ws.lock:
        ws.calibraciones.setdefault(clave_calibracion(project, anio_casos), {})[feeder] = {
            'nombre': f"la calibración del {informe.get('stamp') or time.strftime('%Y-%m-%d %H:%M')}",
            'sed': sed, 'fijas': fijas, 'cuadrado': bool(informe.get('cuadrado')),
            'escenario': informe.get('escenario'), 'recorded_at': time.time(),
            'anio': anio_medicion, 'caso': informe.get('caso')}
        if anio_medicion and not anio_casos:
            # 025:RF-17: desde ahora los casos sin año son de este año.
            ws.anios_casos.setdefault(project.strip(), int(anio_medicion))
        ws.save()


def _correr_guion_ajuste(ws: Workspace, ctx: JobContext, project: str, feeders: list[str],
                        paths: list[str], reports: list[Path], flag: Path, *,
                        simular: bool) -> tuple[list[dict], int]:
    """Una ejecución de ``tools/ajuste_cabecera_pf.py`` para los alimentadores de un
    proyecto, con un informe por alimentador.

    Todos a la vez, en los mismos flujos de carga (021:RF-54): el usuario, el 2026-10-17,
    «la calibración se debe hacer por proyecto en DIgSILENT […], no de forma
    independiente». La comparten el ajuste (spec 006) y los transformadores nuevos
    (020:RF-25), que recalibran con el mismo guion: aplicando, la calibración que valga
    queda registrada.
    """
    pf_dir, interpreter = _require_pf()
    cmd = [str(interpreter), str(_script('ajuste_cabecera_pf.py'))]
    for path, report in zip(paths, reports):
        report.parent.mkdir(parents=True, exist_ok=True)
        report.unlink(missing_ok=True)
        cmd += ['--plan', path, '--output-json', str(report)]
    cmd += ['--cancel-file', str(flag)]
    if simular:
        cmd.append('--simular')
    ctx.log(f"Proyecto de DIgSILENT: {project}  ·  "
            + (f'alimentador {feeders[0]}' if len(feeders) == 1 else
               f"alimentadores {', '.join(feeders)}, calibrados a la vez"))
    rc = ctx.run_process(cmd, env=pf_subprocess_env(pf_dir), cwd=str(project_root()),
                         cancel_file=flag)
    if rc == 3:
        flag.unlink(missing_ok=True)
        raise UserError('No se pudo conectar con DIgSILENT. Ábralo y reintente.')
    informes = []
    # 025:RF-20: el año de los casos y de la medición, del plan que se ejecutó.
    try:
        primero = json.loads(Path(paths[0]).read_text(encoding='utf-8')) if paths else {}
    except (OSError, ValueError):
        primero = {}
    anios = {'anio_casos': primero.get('anio_casos'), 'anio_medicion': primero.get('anio_medicion')}
    for feeder, report in zip(feeders, reports):
        try:
            informe = json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {}
        except (OSError, ValueError):
            informe = {}
        if not informe:
            informe = {'error': f'El guion terminó con el código {rc} sin dejar informe: vea el Registro.'}
        informe.setdefault('feeder', feeder)
        informe.setdefault('project', project)
        if informe.get('error'):
            ctx.log(f"{feeder}: {informe['error']}")
        elif not simular and not informe.get('cuadrado'):
            ctx.log(f"{feeder}: no cumple la tolerancia: {informe.get('motivo')}. Vea el diagnóstico.")
        if not simular:
            _guardar_calibracion(ws, project, feeder, informe, **anios)
        informes.append(informe)
    if not simular and paths:
        # 024:RF-1 / RF-30: un episodio de «Sin proyecto» por proyecto, aceptado solo si
        # todos sus alimentadores cuadran con la medida.
        fallos = any(i.get('error') for i in informes)
        plan_json = json.loads(Path(paths[0]).read_text(encoding='utf-8'))
        _gemelo(ws, ctx, {**plan_json, 'project': project, 'feeders': list(feeders)},
                {'status': 'BLOQUEADO_DATOS' if fallos else 'OK', 'converged': not fallos,
                 'cuadrado': all(i.get('cuadrado') for i in informes)},
                caso='sin_proyecto', rutas={'plan': Path(paths[0]), 'resultado': reports[0]})
    return informes, rc


def ajuste_ejecutar(ws: Workspace, ctx: JobContext, token: str, *, simular: bool) -> dict:
    """Simula o aplica el ajuste con ``tools/ajuste_cabecera_pf.py`` (RF-19 a RF-22).

    Como las cargas: cancelar no mata el guion, se le avisa con un fichero y termina el
    flujo en curso, dejando el escenario con el último reparto que convergió (RF-22). Con
    varios alimentadores del proyecto, una sola ejecución que los calibra a la vez
    (021:RF-54); el que no se puede preparar queda en su informe (RF-57).
    """
    plan = ws.cargas_planes.get(token)
    if plan is None or plan.get('kind') != 'ajuste_cabecera':
        raise UserError('El plan del ajuste ya no existe: vuelva a prepararlo.')
    paths = plan.get('paths') or [plan['path']]
    if not all(Path(p).is_file() for p in paths):
        raise UserError('El plan del ajuste ya no existe: vuelva a prepararlo.')
    _require_pf()                     # sin DIgSILENT se dice antes de empezar
    modo = 'simulacion' if simular else 'aplicacion'
    flag = ws.plans_dir / f'cancelar_{token}.flag'
    flag.unlink(missing_ok=True)
    varios = len(paths) > 1
    reports = [ws.out_dir / f'ajuste_cabecera_{modo}_{token}{f"_{n + 1}" if varios else ""}.json'
               for n in range(len(paths))]
    informes, rc = _correr_guion_ajuste(ws, ctx, plan['project'], list(plan['feeders']),
                                        list(paths), reports, flag, simular=simular)
    flag.unlink(missing_ok=True)
    errores = [i for i in informes if i.get('error')]
    if errores and len(errores) == len(informes):
        raise UserError(' · '.join(f"{i['feeder']}: {i['error']}" if varios else i['error']
                                   for i in errores))
    return {'returncode': rc, 'modo': informes[0].get('modo'),
            'report': reports[0].name, 'reports': [r.name for r in reports],
            'project': plan['project'], 'feeders': plan['feeders'], 'token': token,
            'informe': informes[0], 'informes': informes,
            'sistema': plan.get('sistema')}                                  # 022:RF-53


def _plan_y_sufijo(plan: dict, feeder: str) -> tuple[str, str]:
    paths = plan.get('paths') or [plan['path']]
    if feeder not in plan['feeders']:
        raise UserError(f'{feeder} no está en este ajuste: vuelva a prepararlo.')
    n = plan['feeders'].index(feeder)
    return paths[n], (f'_{n + 1}' if len(paths) > 1 else '')


def ajuste_transformadores_pedido(ws: Workspace, token: str, feeder: str,
                                  seds: list[str]) -> list[dict]:
    """Las propuestas de las SED marcadas, tomadas del último informe del ajuste (020:RF-13).

    No se acepta lo que mande el navegador: solo la propuesta que dio el guion para ese
    plan y ese alimentador, al simular o al aplicar, la más reciente de las dos.
    """
    plan = ws.cargas_planes.get(token)
    if plan is None or plan.get('kind') != 'ajuste_cabecera':
        raise UserError('El plan del ajuste ya no existe: vuelva a prepararlo.')
    if not seds:
        raise UserError('Marque al menos una SED para implementar sus transformadores (020:RF-14).')
    _, sufijo = _plan_y_sufijo(plan, feeder)
    informes = [p for p in (ws.out_dir / f'ajuste_cabecera_{m}_{token}{sufijo}.json'
                            for m in ('simulacion', 'aplicacion')) if p.is_file()]
    if not informes:
        raise UserError(f'{feeder}: simule o aplique el ajuste antes de implementar transformadores.')
    ultimo = max(informes, key=lambda p: p.stat().st_mtime)
    try:
        informe = json.loads(ultimo.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise UserError(f'No se pudo leer el informe del ajuste ({ultimo.name}): {exc}') from exc
    propuestas = {x['sed']: x for x in informe.get('fijas_sobre_su_transformador') or []}
    cambios, sin = [], []
    for sed in dict.fromkeys(seds):
        x = propuestas.get(sed)
        p = (x or {}).get('propuesta') or {}
        if not x or p.get('kva') is None or len(x.get('transformadores') or []) != 1:
            sin.append(sed)
            continue
        cambios.append({'sed': sed, 'transformador': x['transformadores'][0]['transformador'],
                        'propuesta': p})
    if sin:
        raise UserError(f"Sin propuesta de transformador en el último ajuste de {feeder}: "
                        f"{', '.join(sin)}. Vuelva a simular.")
    return cambios


def ajuste_transformadores(ws: Workspace, ctx: JobContext, token: str, feeder: str,
                           cambios: list[dict]) -> dict:
    """Implementa los transformadores y recalibra «Sin proyecto» en el mismo trabajo (020:RF-15, RF-25).

    Una copia del plan del ajuste con ``transformadores``; el informe sale como el de un
    ajuste aplicado, así que la calibración válida queda registrada (RF-28) y es la base
    de lo que siga (007:RF-40).
    """
    return ajuste_transformadores_varios(ws, ctx, token, {feeder: cambios})


def ajuste_transformadores_varios(ws: Workspace, ctx: JobContext, token: str,
                                  cambios_por: dict[str, list[dict]]) -> dict:
    """Los transformadores de varios alimentadores y una sola recalibración (022:RF-62).

    En Chincha (2026-10-18) las fijas sobre su transformador de CA101, PE102 y PN103 hundían
    la tensión de su barra de BT; uno a uno, cada alimentador recalibraba el sistema entero.
    """
    plan = ws.cargas_planes.get(token)
    if plan is None or plan.get('kind') != 'ajuste_cabecera':
        raise UserError('El plan del ajuste ya no existe: vuelva a prepararlo.')
    copias: dict[str, str] = {}
    for feeder, cambios in cambios_por.items():
        path, sufijo = _plan_y_sufijo(plan, feeder)
        try:
            datos = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise UserError('El plan del ajuste ya no existe: vuelva a prepararlo.') from exc
        datos['transformadores'] = cambios
        datos['ultima_calibracion'] = (ws.calibraciones.get(clave_calibracion(
            plan['project'], plan.get('anio_casos'))) or {}).get(feeder)            # 025:RF-20
        copia = ws.plans_dir / f'ajuste_cabecera_{token}{sufijo}_transformadores.json'
        copia.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        copias[path] = str(copia)
        ctx.log(f"{feeder}: transformadores nuevos para {', '.join(c['sed'] for c in cambios)}.")
    feeder = next(iter(cambios_por))
    flag = ws.plans_dir / f'cancelar_{token}.flag'
    flag.unlink(missing_ok=True)
    ctx.log('Después se recalibra «Sin proyecto» una sola vez.')
    # 021:RF-54: se recalibra el proyecto entero, con los transformadores en sus planes.
    paths = [copias.get(x, x) for x in (plan.get('paths') or [plan['path']])]
    varios = len(paths) > 1
    reports = [ws.out_dir / f'ajuste_cabecera_aplicacion_{token}{f"_{n + 1}" if varios else ""}.json'
               for n in range(len(paths))]
    informes, rc = _correr_guion_ajuste(ws, ctx, plan['project'], list(plan['feeders']), paths,
                                        reports, flag, simular=False)
    flag.unlink(missing_ok=True)
    n = plan['feeders'].index(feeder)
    informe = informes[n]
    if informe.get('error') and not informe.get('transformadores_implementados'):
        raise UserError(f"{feeder}: {informe['error']}")
    return {'returncode': rc, 'modo': informe.get('modo'), 'report': reports[n].name,
            'reports': [r.name for r in reports], 'project': plan['project'],
            'feeders': plan['feeders'], 'token': token, 'informe': informe, 'informes': informes}


def ajuste_aplicado_en_disco(ws: Workspace, project: str | None,
                             token: str | None = None) -> dict[str, Any] | None:
    """El último ajuste aplicado del proyecto, rehecho con sus informes en disco (007:RF-40).

    Los trabajos viven en memoria; los informes ``ajuste_cabecera_aplicacion_<token>[_n]``
    quedan en la salida de la ejecución. Se devuelve con la forma del ``result`` del
    trabajo, y un ``id`` ``disco:<token>`` con el que la web lo pide como base. Con
    ``token`` y sin ``project`` vale el proyecto que diga el informe.
    """
    project = str(project or '').strip()
    rutas = list(ws.out_dir.glob('ajuste_cabecera_aplicacion_*.json'))
    if token and not any(_informe_del_token(p, token) for p in rutas):
        # 025:RF-37: pedido por su token, también en otra ejecución del espacio. Al volver a
        # cargar la fuente hay una ejecución nueva y la calibración de 2025 de Pisco quedó
        # en la anterior (2026-10-23): las cargas no encontraban su base.
        rutas = sorted(p for p in ws.root.glob(f'runs/*/salida/ajuste_cabecera_aplicacion_{token}*.json')
                       if _informe_del_token(p, token))
    grupos = _ajustes_por_token(rutas, project, token)
    if not grupos and not token:
        # 025:RF-37, también sin token: tras reiniciar la web, la base de Pisco no aparecía en
        # el paso de cargas: su calibración de 2025 estaba en la ejecución anterior (2026-10-24).
        grupos = _ajustes_por_token(sorted(ws.root.glob('runs/*/salida/ajuste_cabecera_aplicacion_*.json')),
                                    project, None)
    if not grupos:
        return None
    clave, filas = max(grupos.items(), key=lambda kv: max(p.stat().st_mtime for _, p, _ in kv[1]))
    filas.sort(key=lambda fila: fila[0])
    informes = [informe for _, _, informe in filas]
    return {'id': f'disco:{clave}', 'project': project or str(informes[0].get('project') or ''),
            'feeders': [str(i.get('feeder') or '') for i in informes],
            'modo': informes[0].get('modo'), 'report': filas[0][1].name,
            'reports': [p.name for _, p, _ in filas], 'returncode': 0,
            'informe': informes[0], 'informes': informes,
            'finished_at': max(p.stat().st_mtime for _, p, _ in filas)}


def _informe_del_token(path: Path, token: str) -> bool:
    """Si ``path`` es un informe de la calibración ``token``: ``…_<token>_<n>.json`` con
    varios alimentadores, ``…_<token>.json`` con uno solo (CA101, 2026-10-24)."""
    resto = path.stem.removeprefix('ajuste_cabecera_aplicacion_')
    return resto == token or resto.startswith(f'{token}_')


def _ajustes_por_token(rutas, project: str, token: str | None) -> dict[str, list[tuple[int, Path, dict]]]:
    """Los informes de calibración de ``rutas`` del proyecto, agrupados por su token."""
    grupos: dict[str, list[tuple[int, Path, dict]]] = {}
    for path in rutas:
        resto = path.stem.removeprefix('ajuste_cabecera_aplicacion_')
        clave, _, n = resto.partition('_')
        if token and clave != token:
            continue
        try:
            informe = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(informe, dict) or (
                project and str(informe.get('project') or '').strip() != project):
            continue
        grupos.setdefault(clave, []).append((int(n) if n.isdigit() else 0, path, informe))
    return grupos


def _registrar_vinculo(ws: Workspace, acceptance: dict, proyecto: str) -> None:
    """Guarda el vínculo del informe de aceptación, con el estado de su «Caso base».

    Se guarda aunque el «Caso base» no quede verificado (015:RF-14) y se fusiona con el
    estado de los alimentadores verificados antes en el mismo proyecto.
    """
    binding_payload = acceptance.get('project_binding')
    if not binding_payload:
        return
    from ..powerfactory_binding import (
        PowerFactoryProjectBinding, ProjectBindingError, fusionar_caso_base,
        record_project_binding, vinculo_guardado,
    )

    binding = PowerFactoryProjectBinding.from_dict(binding_payload)
    if binding.project != proyecto:
        raise UserError('PROJECT_BINDING_PROJECT_MISMATCH: el informe nativo no '
                        'corresponde al proyecto importado.')
    try:
        anterior = vinculo_guardado(ws, proyecto)
        record_project_binding(ws, fusionar_caso_base(anterior, binding))
    except ProjectBindingError as exc:
        raise UserError(str(exc)) from exc


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
    from ..powerfactory_binding import ProjectBindingError, alimentadores_vinculados
    from ..powerfactory_binding import require_project_binding

    bound = alimentadores_vinculados(ws, project)
    pedidos = alimentadores_pedidos(ws, feeders) or list(bound)                     # 018:RF-14
    if not pedidos:
        raise UserError('Elija los alimentadores cuyo «Caso base» quiere verificar.')
    # Spec 018, RF-5: la exigencia va en el servidor, no solo en la interfaz. Sin vínculo se
    # verificaría un proyecto de procedencia desconocida, y la verificación graba un vínculo
    # nuevo con la fuente activa: justo el hueco que la aceptación existe para cerrar.
    try:
        binding = require_project_binding(ws, project, pedidos)
    except ProjectBindingError as exc:
        raise UserError(str(exc)) from exc
    aviso = usar_ejecucion_del_vinculo(ws, project, binding, pedidos)                  # 018:RF-15
    if aviso:
        ctx.log(aviso)
    jobs, missing = dgs_jobs(ws, pedidos)
    if not jobs:
        raise UserError('Para verificar hace falta el DGS convertido de cada alimentador. Faltan: '
                        + ', '.join(f'{f}.dgs' for f in missing[:12]))
    comprobar_dgs_vinculados(ws, binding.dgs_sha256, pedidos)
    # 018:RF-12: compara el DGS y su sidecar con el manifiesto en disco; la red en memoria
    # no hace falta, y exigirla obligaba a volver a cargarla tras reiniciar la web.
    source_evidence = check_powerfactory_source_run(ws, [f for f, _d, _g in jobs],
                                                    exigir_red_cargada=False)
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
    verificados = [r['feeder'] for r in resultados if r['status'] == 'VERIFICADO']
    if verificados:
        # 024:RF-1 / RF-29: el «Caso base» verificado es la red tal como está.
        from ..native_action import build_native_action_context

        contexto = build_native_action_context(binding, project, verificados, 'verificar_base')
        _gemelo(ws, ctx, {'project': project, 'folder': carpeta_pf(), 'feeders': verificados,
                          'native_action_context': contexto},
                {'status': 'OK', 'converged': True}, caso='caso_base',
                rutas={f'caso_base_{f}': ws.out_dir / f'{f}_caso_base.json' for f in verificados})
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
LIMITE_GEMELO_S = 300.0


def _gemelo(ws: Workspace, ctx: JobContext, plan: dict, informe: dict, *, caso: str,
            rutas: dict[str, Path | None], manual: bool = False) -> dict | None:
    """Episodio del gemelo digital tras una acción nativa ya terminada (024:RF-1).

    Relee el proyecto en otro proceso con ``tools/digital_twin_snapshot_pf.py`` y guarda el
    episodio en el búfer local. Lo que falle aquí queda como aviso en el Registro: la
    acción ya hecha no se repite ni se deshace.
    """
    from ..digital_twin.episode import Caso
    from ..digital_twin.integration import captura_activa, capturar_accion
    from ..perfil_empresa import datos_perfil, estructura_empresa

    try:
        perfil = datos_perfil()
    except Exception:  # noqa: BLE001 - sin perfil, el episodio de «Con proyecto» va a cuarentena
        perfil = {}
    ajustes = perfil.get('gemelo') or {}
    if not captura_activa() or ajustes.get('captura') is False:
        return None
    # La captura nunca retiene al operador: con PA217 (2026-10-22) la lectura esperó 26 min a
    # DIgSILENT con el límite de un estudio. Pasado el suyo, el episodio va a cuarentena.
    limite = float(ajustes.get('lectura_s') or LIMITE_GEMELO_S)
    contexto = plan.get('native_action_context') or {}
    firmados = list(contexto.get('feeders') or [])
    propios = [f for f in plan.get('feeders') or [] if f]
    plan_captura = {'project': plan.get('project'), 'folder': plan.get('folder'),
                    # El orden del plan expresa la orientación (RF-2); el contexto los ordena.
                    'feeders': propios if sorted(propios) == firmados else firmados,
                    'native_action_context': contexto or None,
                    'huellas_gps_esperadas': plan.get('huellas_gps_esperadas') or {}}

    def leer(plan_lectura: dict) -> dict:
        _rc, lectura, _report = _guion_pf(ws, ctx, 'digital_twin_snapshot_pf.py', plan_lectura,
                                          nombre='gemelo_lectura', cancelable=False,
                                          limite_s=limite)
        return lectura

    try:
        estructura = estructura_empresa()
    except Exception:  # noqa: BLE001 - sin estructura no hay norma por sistema
        estructura = None
    return capturar_accion(plan_captura, informe, caso=Caso(caso), rutas=rutas, base=ws.out_dir,
                           leer=leer, perfil=perfil, estructura=estructura, log=ctx.log,
                           manual=manual)


def pide_ejecutar(ws: Workspace, ctx: JobContext, project: str, feeders: list[str], *,
                  capex: str | None = None, implementar: bool = True) -> dict:
    """Metodología del PIDE sobre el proyecto, de punta a punta (spec 024, T13 y T14).

    Diagnostica cada año del horizonte en DIgSILENT (``tools/pide_pf.py``), arma las obras
    con el libro CAPEX y las prioriza por el art. 15; las que se construyen solas (bancos,
    ternas) del periodo del PIDE se simulan y, si funcionan, se aplican en «Con proyecto»
    sin esperar aprobación (RF-45 a RF-47, el usuario el 2026-10-21: «la implementa sola»).
    Deja los formatos 01 a 15 en Excel (RF-63).
    """
    from ..digital_twin.integration import limites_combinados, normas_de
    from ..perfil_empresa import bancos_kvar_por_tension, datos_perfil, estructura_empresa
    from ..pide import escribir_formatos
    from ..pide_economia import EconomiaPideError, costos_por_alternativa, leer_capex, propuesta_pide

    project = project.strip()
    if not project:
        raise UserError('Elija el proyecto de DIgSILENT.')
    contexto = native_action_context(ws, project, feeders, 'pide')
    perfil = datos_perfil()
    plan_pide = dict(perfil.get('planificacion') or {})
    if not plan_pide:
        raise UserError('El perfil de empresa no tiene «planificacion» (tasas, vida útil, horizonte).')
    feeders = list(contexto['feeders'])
    limites = limites_combinados(perfil, normas_de(estructura_empresa(), feeders))
    if limites is None:
        raise UserError('Faltan en el perfil los límites de la norma de estos alimentadores.')
    avisos: list[str] = []
    tasa = plan_pide.get('crecimiento_demanda_anual')
    anios = [0] + list(plan_pide.get('anios_horizonte') or []) if tasa is not None else [0]
    if tasa is None:
        avisos.append('sin tasa de crecimiento de la demanda en el perfil: solo el diagnóstico del '
                      'año 00 (RF-51)')
    plan = {'project': project, 'folder': carpeta_pf(), 'feeders': feeders, 'case': 'sin_proyecto',
            'tasa': tasa if tasa is not None else 0.0, 'anios': anios,
            'limites': {'tension_min_pu': limites.tension_min_pu, 'tension_max_pu': limites.tension_max_pu,
                        'cargabilidad_max_pct': limites.cargabilidad_max_pct,
                        'transformador_max_pct': limites.transformador_max_pct},
            'native_action_context': contexto}
    ctx.log(f'PIDE de {project}: diagnóstico de los años {anios} en DIgSILENT…')
    _rc, informe, report = _guion_pf(ws, ctx, 'pide_pf.py', plan, nombre='pide', cancelable=False,
                                     limite_s=LIMITE_ESTUDIO_S)
    if informe.get('error'):
        raise UserError(informe['error'])
    costos: dict = {}
    if capex:
        try:
            obras_capex, avisos_capex = leer_capex(Path(capex.strip().strip('"')), plan_pide.get('capex') or {})
        except (EconomiaPideError, OSError, ValueError) as exc:
            raise UserError(f'Libro CAPEX: {exc}') from exc
        costos = costos_por_alternativa(obras_capex)
        avisos += avisos_capex
    propuesta = propuesta_pide(informe, plan_pide, costos=costos,
                               bancos_kvar=bancos_kvar_por_tension(perfil),
                               factor_carga=plan_pide.get('factor_carga'),
                               precio_compra_kwh=plan_pide.get('precio_compra_kwh'))
    avisos += propuesta['avisos']
    avisos += _pide_optimizar(project, propuesta['obras'], limites, perfil, plan_pide, costos, ctx)
    implementadas: list[dict] = []
    if implementar:
        implementadas = _pide_implementar(ws, ctx, project, feeders, propuesta['obras'],
                                          set(plan_pide.get('anios_pide') or []))
    token = uuid.uuid4().hex[:8]
    libro = escribir_formatos(ws.out_dir / f'pide_{token}.xlsx', propuesta['formatos'])
    ctx.log(f"PIDE: {len(propuesta['obras'])} obra(s) propuesta(s), {len(implementadas)} aplicada(s) "
            f'solas en «Con proyecto»; formatos en {libro.name}.')
    return {'project': project, 'feeders': feeders, 'report': report.name, 'formatos': libro.name,
            'anios': [{k: v for k, v in a.items() if k != 'problemas'} | {'problemas': len(a.get('problemas') or [])}
                      for a in informe.get('anios') or []],
            'obras': propuesta['obras'], 'implementadas': implementadas, 'avisos': avisos}


def _pide_optimizar(project: str, obras: list[dict], limites, perfil: dict, plan_pide: dict,
                    costos: dict, ctx: JobContext) -> list[str]:
    """Ubicación y tamaño de los bancos del PIDE con el algoritmo genético y NSGA-II sobre la
    red del gemelo de este proyecto (024:RF-73). Sin red del gemelo, quedan los del
    diagnóstico; cada banco se simula después en DIgSILENT antes de aplicarse (RF-46)."""
    if not any((o.get('obra_011') or {}).get('clase') == 'condensador' for o in obras):
        return []
    try:
        from ..digital_twin.buffer import BuferEpisodios, Consulta
        from ..digital_twin.evolutivo import afinar_bancos_pide, red_del_gemelo
    except ImportError as exc:
        return [f'los bancos no se optimizan: falta {exc.name} (extra «ml»)']
    from ..perfil_empresa import bancos_kvar_por_tension
    from ..pide_economia import valor_kw_perdidas

    grafo = red_del_gemelo(BuferEpisodios().consultar(Consulta(proyecto=project, caso='sin_proyecto')))
    if grafo is None:
        return ['los bancos no se optimizan: el gemelo aún no tiene la red de este proyecto '
                '(«Aprender» en el paso del gemelo)']
    costo = (costos.get('bancos') or {}).get('costo_unitario')
    valor = valor_kw_perdidas(plan_pide, factor_carga=plan_pide.get('factor_carga'),
                              precio_compra_kwh=plan_pide.get('precio_compra_kwh'))
    ctx.log('PIDE: ubicación y tamaño de los bancos con el algoritmo genético y NSGA-II…')
    avisos = afinar_bancos_pide(obras, grafo, tension_min_pu=limites.tension_min_pu,
                                tension_max_pu=limites.tension_max_pu, bancos_kvar=bancos_kvar_por_tension(perfil),
                                tasa_demanda=float(plan_pide.get('crecimiento_demanda_anual') or 0.0),
                                costo_modulo=float(costo) if costo is not None else None,
                                valor_kw_perdidas=valor,
                                semilla=int((perfil.get('gemelo') or {}).get('semilla') or 0))
    if valor is None:
        avisos.append('sin factor de carga o precio de compra en el perfil, las pérdidas solo desempatan '
                      'entre bancos (024:RF-70)')
    return avisos


def _pide_implementar(ws: Workspace, ctx: JobContext, project: str, feeders: list[str],
                      obras: list[dict], anios_pide: set[int]) -> list[dict]:
    """Simula las obras propias que se construyen solas y aplica las que funcionan (RF-46,
    RF-47). Lo que choca con un cambio manual lo dice ``obras_pf`` y queda sin aplicar
    (RF-47b); cada aplicada se informa con su variación para deshacerla (RF-47c)."""
    elegibles = [o for o in obras if o.get('obra_011') and not o.get('descartada')
                 and not o.get('sobredimensionada') and (not anios_pide or o['anio'] <= max(anios_pide))]
    if not elegibles:
        return []
    ids = {}
    for o in elegibles:
        # El algoritmo genético puede repartir el banco de una obra en varias barras (024:RF-73).
        for obra in [o['obra_011'], *(o.get('obras_011_extra') or [])]:
            try:
                ids[obra_anadir(ws, obra)['id']] = o
            except UserError as exc:
                o['motivo_sin_obra'] = str(exc)
    if not ids:
        return []
    ctx.log(f'PIDE: simulando {len(ids)} obra(s) propia(s) antes de aplicarlas (RF-46)…')
    sim = obras_ejecutar(ws, ctx, project, feeders, list(ids), '', simular=True)
    filas = (sim.get('informe') or {}).get('obras') or []
    lista = list(ids)
    buenas = [lista[int(f['obra']) - 1] for f in filas
              if 1 <= int(f.get('obra') or 0) <= len(lista) and not f.get('error')]
    for i in set(lista) - set(buenas):
        ids[i]['motivo_sin_obra'] = 'la simulación en DIgSILENT no la dio por buena'
    with ws.lock:
        ws.obras = [o for o in ws.obras if o['id'] not in set(lista) - set(buenas)]
        ws.save()
    if not buenas:
        return []
    ctx.log(f'PIDE: aplicando {len(buenas)} obra(s) en «Con proyecto» (RF-47)…')
    hecho = obras_ejecutar(ws, ctx, project, feeders, buenas, '', simular=False)
    out = []
    for f in (hecho.get('informe') or {}).get('obras') or []:
        n = int(f.get('obra') or 0)
        if 1 <= n <= len(buenas) and f.get('variacion') and not f.get('error'):
            o = ids[buenas[n - 1]]
            o['variacion_autonoma'] = f['variacion']
            out.append({'codigo': o['codigo'], 'alternativa': o['alternativa'], 'variacion': f['variacion'],
                        'aviso': f"aplicada sola en «Con proyecto»; para deshacerla, desactive o borre "
                                 f"la variación {f['variacion']} (RF-47c)"})
    return out


def gemelo_aprender(ws: Workspace, ctx: JobContext, project: str, feeders: list[str], *,
                    n: int = 20, segundos: float | None = None, caso: str = 'sin_proyecto') -> dict:
    """Aprendizaje activo: escenarios simulados en una copia del proyecto (spec 024, T10).

    Lee los tramos, arma la matriz (demanda escalada y N-1), elige los que más enseñan
    (los de mayor incertidumbre del oráculo promovido o, sin él, los más distintos) entre
    los que aún no hay, los simula en DIgSILENT dentro del presupuesto de licencia del
    perfil y los guarda como ``counterfactual`` (RF-11, RF-40, RF-41). Después entrena si
    toca (RF-39).
    """
    from dataclasses import asdict
    from datetime import UTC, datetime

    from ..digital_twin.buffer import BuferEpisodios, Consulta
    from ..digital_twin.capture import artefacto_de, construir_episodio
    from ..digital_twin.episode import Caso
    from ..digital_twin.escenarios import Escenario, elegir, matriz
    from ..digital_twin.integration import limites_combinados, normas_de
    from ..perfil_empresa import datos_perfil, estructura_empresa

    project = project.strip()
    contexto = native_action_context(ws, project, feeders, 'gemelo_escenarios')
    perfil = datos_perfil()
    ajustes = dict(perfil.get('gemelo') or {})
    segundos = float(segundos or ajustes.get('licencia_s') or 600)
    feeders = list(contexto['feeders'])
    base = {'project': project, 'folder': carpeta_pf(), 'feeders': feeders, 'case': caso,
            'native_action_context': contexto}
    _rc, tramos, _r = _guion_pf(ws, ctx, 'escenarios_pf.py', {**base, 'solo_tramos': True},
                                nombre='gemelo_tramos', cancelable=False, limite_s=segundos)
    if tramos.get('error'):
        raise UserError(tramos['error'])
    bufer = BuferEpisodios()
    hechos = {Escenario(float(e.accion['escenario']['factor_carga']),
                        tuple(e.accion['escenario'].get('tramos_abiertos') or ())).clave
              for e in bufer.consultar(Consulta(proyecto=project)) if e.accion.get('escenario')}
    incertidumbre = None
    try:
        from ..digital_twin.oraculo import incertidumbre_de_escenarios

        incertidumbre = incertidumbre_de_escenarios(tramos.get('grafo') or {})
    except ImportError:
        pass
    elegidos = elegir(matriz(tramos.get('tramos') or [], semilla=int(ajustes.get('semilla') or 0)),
                      int(n), incertidumbre, hechos)
    if not elegidos:
        return {'project': project, 'simulados': 0, 'avisos': ['no quedan escenarios por simular']}
    ctx.log(f'Gemelo: {len(elegidos)} escenario(s) en una copia de {project} '
            f'({"por incertidumbre" if incertidumbre else "por diversidad"})…')
    _rc, informe, report = _guion_pf(
        ws, ctx, 'escenarios_pf.py', {**base, 'escenarios': [asdict(e) for e in elegidos],
                                      'limite_s': segundos},
        nombre='gemelo_escenarios', cancelable=True, limite_s=segundos + 300)
    if informe.get('error') and not informe.get('escenarios'):
        raise UserError(informe['error'])
    limites = limites_combinados(perfil, normas_de(estructura_empresa(), feeders))
    clases: dict[str, int] = {}
    for fila in informe.get('escenarios') or []:
        e = construir_episodio(base, {'status': 'OK' if fila['converge'] else 'NO_CONVERGE',
                                      'converged': fila['converge'], 'aplicada': False,
                                      'escenario': fila['escenario']},
                               fila.get('lectura'), [artefacto_de(report, 'escenarios', ws.out_dir)],
                               caso=Caso(caso), limites=limites, referencia=None, calibracion_cuadra=True,
                               creado=datetime.now(UTC).isoformat(timespec='seconds'))
        bufer.guardar(e)
        clases[e.clase.value] = clases.get(e.clase.value, 0) + 1
    out = {'project': project, 'simulados': sum(clases.values()), 'clases': clases,
           'avisos': list(informe.get('avisos') or [])}
    out['entrenamiento'] = gemelo_entrenar(ws, ctx)
    return out


def gemelo_entrenar(ws: Workspace, ctx: JobContext, *, forzar: bool = False) -> dict:
    """Entrena el oráculo en otro proceso (``tools/digital_twin_entrenar.py``, RF-39).

    Un fallo de memoria o de la GPU cae ese proceso, no la web: el 2026-10-22, entrenando
    dentro de la web con IN111–TA225 y 1,3 GB de RAM libre, la web se cayó.
    """
    import sys

    from ..digital_twin.buffer import raiz_buffer

    report = ws.out_dir / f'gemelo_entrenamiento_{uuid.uuid4().hex[:8]}.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(_script('digital_twin_entrenar.py')), '--output-json', str(report),
           '--raiz', str(raiz_buffer())]
    if forzar:
        cmd.append('--forzar')
    rc = ctx.run_process(cmd, cwd=str(project_root()))
    try:
        r = json.loads(report.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        r = {'entrenado': False, 'error': f'el entrenamiento terminó con el código {rc} sin informe'}
    if r.get('error'):
        ctx.log(f"Gemelo: el entrenamiento falló ({str(r['error'])[:200]}); la web sigue.")
    return {k: v for k, v in r.items() if k != 'traza'}


def gemelo_temporal(ws: Workspace, ctx: JobContext, job_id: str, alimentadores: dict[str, str], *,
                    barra: str | None = None, sin_medidor: dict[str, float] | None = None,
                    fijas_kw: dict[str, float] | None = None, perdidas_pct: float = 0.0,
                    umbral_pct: float = 10.0) -> dict:
    """Gemelo temporal del mes con las curvas de la última máxima buscada (spec 024, T12).

    ``alimentadores``: alimentador → medidor. Entrena una GRU por cabecera con el 70 % del
    mes y reproduce el resto (RF-20, RF-37), localiza las desviaciones (RF-21), da el
    instante crítico coincidente (RF-37) y, con la barra, las pseudo-medidas de los
    alimentadores sin medidor por su kVA (RF-22).
    """
    from ..digital_twin.temporal import (
        desviaciones,
        elegido,
        instante_critico,
        metricas,
        modelo_temporal,
        pseudo_medidas,
    )

    with ws.lock:
        curvas = ws.curvas_cabecera.get(job_id)
    if curvas is None:
        raise UserError('Las curvas no son de la última máxima buscada: vuelva a buscarla.')
    faltan = [m for m in [*alimentadores.values(), *([barra] if barra else [])] if m not in curvas]
    if faltan:
        raise UserError(f"No hay curva de {', '.join(faltan)} en la última máxima buscada.")
    series = {a: curvas[m]['curva'] for a, m in alimentadores.items()}
    largo = min(len(c) for c in series.values())
    instantes = [p[0] for p in next(iter(series.values()))[:largo]]
    medidas = {a: [p[1] for p in c[:largo]] for a, c in series.items()}
    reproducidas, resultado = {}, {}
    for a, s in medidas.items():
        corte = int(0.7 * len(s))
        modelo = elegido(modelo_temporal(), s[:corte])       # 027:RF-11
        r = modelo.reproducir(s)
        reproducidas[a] = r
        resultado[a] = {'modelo': modelo.nombre, **metricas(s[corte:], r[corte:])}
        ctx.log(f"Gemelo temporal {a}: {resultado[a]['modelo']}, error {resultado[a]['mape_pct']:.1f} %")
    out = {'alimentadores': resultado,
           'desviaciones': desviaciones(medidas, reproducidas, instantes, umbral_pct)[:200],
           'instante_critico': instante_critico(medidas, instantes)}
    if barra and sin_medidor:
        b = [p[1] for p in curvas[barra]['curva'][:largo]]
        est = pseudo_medidas(b, medidas, sin_medidor, fijas_kw=fijas_kw, perdidas_pct=perdidas_pct)
        out['pseudo_medidas'] = {a: {**e, 'kw_max': max(e['kw']) if e['kw'] else 0.0} for a, e in est.items()}
    return out


def pide_decision(ws: Workspace, project: str, codigo: str, decision: str, comentario: str = '') -> dict:
    """Lo que decidió el operador sobre una propuesta, para que el gemelo aprenda (RF-48)."""
    from ..digital_twin.buffer import BuferEpisodios

    if decision not in ('aceptada', 'rechazada', 'modificada'):
        raise UserError('La decisión es «aceptada», «rechazada» o «modificada».')
    return BuferEpisodios().registrar_decision({'project': project.strip(), 'codigo': codigo.strip(),
                                                'decision': decision, 'comentario': comentario.strip()})


def gemelo_episodios(ws: Workspace, filtros: dict[str, str | None]) -> list[dict]:
    """Episodios del búfer de los proyectos vinculados en este espacio (024:RF-8).

    Se ve lo de un proyecto que el espacio tiene vinculado, en el registro compartido de la
    spec 018: el mismo proyecto vinculado en otro espacio con la misma fuente también vale.
    """
    from ..digital_twin.buffer import BuferEpisodios, Consulta
    from ..powerfactory_binding import alimentadores_vinculados

    consulta = Consulta(**{k: v for k, v in filtros.items() if v})
    visibles: dict[str, bool] = {}
    out = []
    for e in BuferEpisodios().consultar(consulta):
        proyecto = e.nativo['project']
        if proyecto not in visibles:
            visibles[proyecto] = bool(alimentadores_vinculados(ws, proyecto))
        if visibles[proyecto]:
            out.append({'episode_id': e.episode_id, 'clase': e.clase.value, 'caso': e.caso.value,
                        'creado': e.creado, 'project': proyecto, 'feeders': e.nativo['feeders'],
                        'accion': e.accion.get('tipo'),
                        'bloqueos': list(e.aceptacion.get('bloqueos') or []),
                        'violaciones': list(e.aceptacion.get('violaciones') or [])})
    return out


def gemelo_episodio(ws: Workspace, episode_id: str) -> dict:
    """El manifiesto de un episodio, si su proyecto está vinculado aquí; si no, ``KeyError``.

    Solo huellas y rutas de la evidencia: nunca el contenido de los ficheros de la empresa.
    """
    from ..digital_twin.buffer import BuferEpisodios
    from ..digital_twin.episode import episodio_a_dict
    from ..powerfactory_binding import alimentadores_vinculados

    e = BuferEpisodios().leer(episode_id)
    if not alimentadores_vinculados(ws, e.nativo['project']):
        raise KeyError(episode_id)
    return episodio_a_dict(e)


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


# ------------------------------------------------------------------ escaneo (spec 028)
def escanear_alimentadores(ws: Workspace, ctx: JobContext, project: str, feeders: list[str],
                           anio: int | None = None) -> dict[str, Any]:
    """Lee en DIgSILENT, sin escribir, los generadores, bancos, variaciones y cargas cambiadas
    de los alimentadores (028:RF-1 a RF-10) y lo guarda en el espacio para la calibración."""
    from ..escaneo import resumen

    if not project.strip() or not feeders:
        raise UserError('Elija el proyecto y al menos un alimentador para escanear.')
    plan = {'project': project.strip(), 'folder': carpeta_pf(), 'feeders': list(feeders),
            'anio_casos': anio,
            'ultima_calibracion': ws.calibraciones.get(clave_calibracion(project.strip(), anio)) or {}}
    _rc, informe, _report = _guion_pf(ws, ctx, 'escanear_alimentador_pf.py', plan, nombre='escaneo',
                                      cancelable=False)
    if informe.get('error'):
        raise UserError(f"Escaneo de {project}: {informe['error']}")
    informe['resumen'] = resumen(informe)
    for f, r in informe['resumen'].items():
        ctx.log(f"Escaneo {f}: {r['generadores']} generador(es) ({r['generadores_del_operador']} del operador), "
                f"{r['bancos']} banco(s) ({r['bancos_de_calibracion']} de la calibración), "
                f"{r['cargas_cambiadas']} carga(s) cambiada(s)")
    with ws.lock:
        ws.escaneo[project.strip()] = informe
        ws.save()
    return informe


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


def _curva_del_anio(ws: Workspace, ctx: JobContext, anio: int, medidores: dict[str, str]) -> dict:
    """``{alimentador: [(instante, kW), …]}`` de la medición de cabecera del año (025:RF-51).

    Con sus propios libros del año, sin tocar la máxima que el operador buscó en la web.
    """
    from ..demanda_medida import DemandaError, maximas

    libros = _libros_de_cabecera(ws, str(anio))
    try:
        res = maximas(libros, list(medidores.items()), alias=demanda_alias(), periodo=str(anio),
                      cancelado=ctx.cancel.is_set)
    except DemandaError as exc:
        raise UserError(str(exc)) from exc
    por_medidor = {r.medidor: r for r in res}
    out = {}
    for f, medidor in medidores.items():
        r = por_medidor.get(medidor)
        if r is None or r.error or not r.curva:
            raise UserError(f'{f}: el medidor {medidor} no tiene curva de {anio} en la cabecera '
                            '(025:RF-51)' + (f': {r.error}' if r is not None and r.error else ''))
        out[f] = [(t, kw) for t, kw, *_ in r.curva if kw is not None]
    return out


def obras_escalera(ws: Workspace, ctx: JobContext, project: str, feeders: list[str], *,
                   anio_casos: int | None = None, tipo_cambio: float | None = None,
                   capex: str | None = None) -> dict:
    """Escalera optimizada de obras sobre «Con proyecto <año>» (025:RF-44, RF-49 a RF-60, RF-67).

    Usuario, 2026-10-24: «primero se debe probar bancos, después nueva terna, cambio de
    sección de cable, donde se debe iterar varias veces hasta obtener la mejor solución según
    la optimización y cálculos estocásticos». Por alimentador con cargas nuevas, uno tras
    otro: lee la troncal y sus corrientes (``obras_pf.py --escalera-datos``), arma las
    variantes (``escalera_optima.variantes``), las mide con la máxima y en los sorteos de la
    curva de cabecera del año (``--evaluar``, que no deja ninguna), las costea con el CAPEX
    en la moneda del perfil y aplica solo la de menor costo anual entre las que cumplen.
    """
    import re

    from ..demanda_medida import clave_codigo
    from .. import escalera_optima as eo
    from ..informes import factor_de_carga, factor_de_perdidas
    from ..pide_economia import EconomiaPideError, costos_por_alternativa, leer_capex
    from ..perfil_empresa import PerfilError, bancos_kvar_por_tension, datos_perfil

    # 025:RF-57, RF-67, RF-68: antes de tocar DIgSILENT, el perfil y el tipo de cambio que
    # escribió el operador tienen que bastar para costear.
    try:
        perfil = datos_perfil()
        p = eo.parametros(perfil, tipo_cambio)
    except (eo.EscaleraError, PerfilError) as exc:
        raise UserError(str(exc)) from exc
    base = ajuste_aplicado_en_disco(ws, project)
    if not base:
        raise UserError('El proyecto no tiene calibración: calibre antes de la escalera (paso 2).')
    objetivos = {str(i.get('feeder')): i.get('objetivo') or {} for i in base.get('informes') or []}
    if anio_casos is None:
        anio_casos = next((int(m.group(1)) for i in base.get('informes') or []
                           if (m := re.search(r'(\d{4})$', str(i.get('caso') or '')))), None)
    cargas = _cargas_nuevas_aplicadas(ws, project)
    con_cargas = [f for f in feeders if any(clave_codigo(c.get('alimentador')) == clave_codigo(f) for c in cargas)]
    if not con_cargas:
        raise UserError('Ningún alimentador marcado tiene cargas nuevas aplicadas: no hay escalera que hacer.')
    faltan = [f for f in feeders if not (objetivos.get(f) or {}).get('kw') or not (objetivos.get(f) or {}).get('medidor')]
    if faltan:
        raise UserError('Sin máxima ni medidor de su calibración: ' + ', '.join(faltan) + ' (025:RF-51)')
    anio_curva = anio_casos or datetime.now().year
    curvas = _curva_del_anio(ws, ctx, anio_curva, {f: str(objetivos[f]['medidor']) for f in feeders})
    instantes: dict[Any, dict[str, float]] = {}
    for f, curva in curvas.items():
        for t, kw in curva:
            instantes.setdefault(t, {})[f] = kw
    try:
        sorteos = eo.sorteos(sorted(instantes.items(), key=lambda x: x[0]),
                             {f: float(objetivos[f]['kw']) for f in feeders}, p.sorteos, p.semilla)
    except eo.EscaleraError as exc:
        raise UserError(str(exc)) from exc
    perdidas = {}
    for f, curva in curvas.items():
        fc = factor_de_carga([(t, kw, None) for t, kw in curva])
        perdidas[f] = factor_de_perdidas(fc) if fc else None
    ctx.log(f'Escalera de {project.strip()} en «Con proyecto{f" {anio_casos}" if anio_casos else ""}»: '
            f'{len(sorteos)} sorteos de la curva de {anio_curva}, costo en {p.moneda or "la moneda del perfil"}.')

    costos_capex, avisos = {}, []
    if capex and capex.strip():
        try:
            obras_capex, avisos_capex = leer_capex(Path(capex.strip().strip('"')),
                                                   (perfil.get('planificacion') or {}).get('capex') or {})
        except (EconomiaPideError, OSError) as exc:
            raise UserError(f'Libro CAPEX: {exc}') from exc
        costos_capex = costos_por_alternativa(obras_capex)
        avisos += avisos_capex
    else:
        avisos.append('Sin libro CAPEX: solo se costean las alternativas que da el perfil (025:RF-57).')
    costos = eo.costos_de_alternativas(costos_capex, p)
    try:
        kvar = bancos_kvar_por_tension(perfil) or {}
    except PerfilError:
        kvar = {}
    lectura = obras_bibliotecas(ws, ctx, project, feeders)['informe']

    resultado, resueltos = [], []
    for f in con_cargas:
        ctx.check_cancel()
        # El guion compara los alimentadores del plan con los del contexto firmado: cada
        # alimentador va con el suyo (Pisco, 2026-10-24: «BLOQUEADO_DATOS» con el de los dos).
        # 025:RF-69: activas solo sus cargas nuevas y las de los ya resueltos.
        comun = {'project': project.strip(), 'folder': carpeta_pf(), 'anio_casos': anio_casos,
                 'native_action_context': native_action_context(ws, project, [f], 'obras'),
                 'apartar_cargas_de': [g for g in con_cargas if g != f and g not in resueltos]}
        de_f = [c for c in cargas if clave_codigo(c.get('alimentador')) == clave_codigo(f)]
        barras = list(dict.fromkeys(str(c['barra']) for c in de_f if c.get('barra')))
        rc, datos, _rep = _guion_pf(ws, ctx, 'obras_pf.py', {
            **comun, 'feeders': [f], 'barras': {f: barras}, 'tension_min_pu': p.tension_min_pu},
            nombre='escalera_datos', args=('--escalera-datos',))
        d = (datos.get('alimentadores') or {}).get(f)
        fila: dict[str, Any] = {'alimentador': f, 'avisos': list(datos.get('avisos') or []),
                                'elegida': None, 'mas_cercana': None, 'tabla': [], 'aplicada': None}
        if rc or not d:
            fila['avisos'].append(datos.get('error') or f'{f}: no se pudo leer su troncal en DIgSILENT.')
            resultado.append(fila)
            continue
        kv = (lectura.get('alimentadores', {}).get(f) or {}).get('kv')
        banco = (min(kvar.items(), key=lambda par: abs(float(par[0]) - float(kv)))[1]
                 if kvar and kv else None)
        cargas_f = [{'barra': c['barra'], 'existe': str(c.get('criterio') or '').startswith('barra'),
                     'indice_troncal': d['indices'].get(str(c['barra']))} for c in de_f if c.get('barra')]
        vs, av = eo.variantes(f, float(kv or 0), d['troncal'], cargas_f, lectura.get('tipos') or [], p,
                              banco_kvar=banco, fuera_desde=d.get('fuera_desde'))
        fila['avisos'] += av
        if not vs:
            fila['avisos'].append(f'{f}: ninguna variante que probar.')
            resultado.append(fila)
            continue
        ctx.log(f'{f}: {len(vs)} variantes en el orden bancos, regulador, terna y sección…')
        # 025:RF-71: el guion sortea de la más barata a la más cara; para ordenar, el costo anual
        # sin pérdidas de cada variante y lo que cuesta al año cada kW perdido en la máxima.
        def costo_base(v):
            try:
                return eo.costo(v, costos, p, perdidas_kw=0.0, factor_perdidas=perdidas.get(f))['costo_anual']
            except eo.EscaleraError:
                return None

        por_kw = ((p.precio_perdidas_kwh or 0.0) * (perdidas.get(f) or 0.0) * eo.HORAS_ANIO
                  + 12 * (p.precio_perdidas_kw_mes or 0.0))
        plan_ev = {
            **comun, 'feeders': [f], 'costo_por_kw_perdido': por_kw,
            'variantes': [{'nombre': v.nombre, 'obras': v.obras, 'costo_base': costo_base(v)} for v in vs],
            'barras_cargas': barras, 'sorteos': sorteos, 'parametros': perfil, 'tipo_cambio': tipo_cambio,
            'otro_proyecto': eo.BIBLIOTECA_TIPOS,
            'estado_con_proyecto': datos.get('variaciones_activas')}
        # 025:RF-73: sin el estado de «Con proyecto» no se sabe si es la misma red: se mide.
        ev = _evaluacion_hecha(ws, plan_ev) if datos.get('variaciones_activas') is not None else None
        if ev is not None:
            ctx.log(f'{f}: se reutiliza su evaluación ya terminada con los mismos datos (025:RF-73).')
        else:
            rc, ev, _rep = _guion_pf(ws, ctx, 'obras_pf.py', plan_ev, nombre='escalera_evaluar',
                                     args=('--evaluar',))
        if ev.get('error'):
            raise UserError(ev['error'])
        if ev.get('ya_cumple'):                                                  # 025:RF-74
            fila['avisos'].append(f"{f}: «Con proyecto» ya cumple con lo que tiene (sorteos "
                                  f"{100 * float(ev['ya_cumple'].get('fraccion') or 0):.0f} %): no se aplica "
                                  'nada (025:RF-74).')
            resueltos.append(f)
            resultado.append(fila)
            continue
        por_nombre = {v.nombre: v for v in vs}
        evaluadas = []
        for x in ev.get('variantes') or []:
            v = por_nombre.get(x['nombre'])
            e = {**x, 'costo': None}
            if v is not None:
                try:
                    e['costo'] = eo.costo(v, costos, p, perdidas_kw=x.get('perdidas_kw'),
                                          factor_perdidas=perdidas.get(f))
                except eo.EscaleraError as exc:
                    e['sin_costo'] = str(exc)
            evaluadas.append(e)
        decision = eo.elegir(evaluadas, p)
        fila.update(elegida=decision['elegida'], mas_cercana=decision['mas_cercana'],
                    tabla=[{k: t.get(k) for k in ('nombre', 'maxima', 'fraccion', 'motivos', 'motivo',
                                                  'factible', 'perdidas_kw', 'error', 'sin_sortear')}
                           | {'inversion': (t.get('costo') or {}).get('inversion'),
                              'costo_anual': (t.get('costo') or {}).get('costo_anual')}
                           for t in decision['tabla']])
        if decision['elegida']:                                                  # RF-54
            ids = [obra_anadir(ws, o)['id'] for o in por_nombre[decision['elegida']].obras]
            ctx.log(f"{f}: se aplica «{decision['elegida']}» en «Con proyecto»…")
            hecho = obras_ejecutar(ws, ctx, project, feeders, ids, eo.BIBLIOTECA_TIPOS, simular=False,
                                   anio_casos=anio_casos, apartar_cargas_de=comun['apartar_cargas_de'])
            hechas = (hecho.get('informe') or {}).get('obras') or []
            fila['aplicada'] = [o.get('variacion') for o in hechas]
            # 025:RF-69: resuelto solo si su obra quedó activa en «Con proyecto <año>»; si no,
            # sus cargas siguen apartadas para los siguientes.
            if hechas and all(any(str(c).startswith('Con proyecto') for c in o.get('casos_activos') or [])
                              for o in hechas):
                resueltos.append(f)
            else:
                fila['avisos'].append(f"{f}: «{decision['elegida']}» se creó pero no quedó activa en "
                                      '«Con proyecto»: su flujo no converge al aplicarla (025:RF-69).')
        else:                                                                    # RF-56
            fila['avisos'].append(f"{f}: ninguna variante cumple; la más cercana es «{decision['mas_cercana']}», "
                                  'y no se aplica nada (025:RF-56).')
        resultado.append(fila)
    return {'project': project.strip(), 'anio_casos': anio_casos, 'moneda': p.moneda, 'tipo_cambio': tipo_cambio,
            'sorteos': len(sorteos), 'avisos': avisos, 'alimentadores': resultado}


VIGENCIA_EVALUACION_S = 24 * 3600


def _evaluacion_hecha(ws: Workspace, plan: dict) -> dict | None:
    """El informe de una evaluación de la escalera ya terminada con el mismo plan (025:RF-73).

    El contexto firmado cambia en cada petición y no cuenta; el resto del plan es lo que se
    midió, con las variaciones activas en «Con proyecto». Solo vale un informe terminado (sin
    error ni cancelación), con variantes y de las últimas 24 h. (Pisco, 2026-10-24: se
    reutilizó para PA217 una evaluación cancelada y medida con la obra de SI213 inactiva.)
    """
    def clave(p: dict) -> str:
        return json.dumps({k: v for k, v in p.items() if k != 'native_action_context'},
                          sort_keys=True, ensure_ascii=False, default=str)

    buscada = clave(json.loads(json.dumps(plan, ensure_ascii=False, default=str)))
    limite = time.time() - VIGENCIA_EVALUACION_S
    for ruta in sorted(ws.plans_dir.glob('escalera_evaluar_*.json'), key=lambda p: p.stat().st_mtime,
                       reverse=True):
        informe = ws.out_dir / ruta.name
        try:
            if informe.stat().st_mtime < limite or clave(json.loads(ruta.read_text(encoding='utf-8'))) != buscada:
                continue
            datos = json.loads(informe.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if (isinstance(datos, dict) and datos.get('variantes') and not datos.get('error')
                and not datos.get('cancelado')):
            return datos
    return None


def registrar_obra_aplicada(ws: Workspace, project: str, variacion: str, obra: dict) -> None:
    """Una obra aplicada en DIgSILENT, con su proyecto y su variación (017:RF-35).

    Al aplicarse sale de ``ws.obras``; sin este registro el informe de estudio no veía
    ninguna obra de «Con proyecto» (CA101, 2026-10-15: salió solo el estado actual).
    """
    ws.obras_aplicadas = [o for o in ws.obras_aplicadas
                          if not (o.get('project') == project.strip()
                                  and o.get('variacion') == variacion)]
    ws.obras_aplicadas.append({'project': project.strip(), 'variacion': variacion,
                               'obra': {k: v for k, v in obra.items() if k != 'id'},
                               'aplicada': time.time()})


def obras_ejecutar(ws: Workspace, ctx: JobContext, project: str, feeders: list[str],
                   ids: list[str] | None, otro_proyecto: str, *, simular: bool,
                   anio_casos: int | None = None,
                   apartar_cargas_de: list[str] | None = None) -> dict:
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
            'native_action_context': action_context,
            'anio_casos': anio_casos}                                   # 025:RF-41
    if apartar_cargas_de:
        plan['apartar_cargas_de'] = list(apartar_cargas_de)            # 025:RF-69
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
            # 017:RF-35: lo aplicado se recuerda con su variación para el informe de estudio.
            for fila in informe.get('obras') or []:
                n = int(fila.get('obra') or 0)
                if 1 <= n <= len(elegidas) and elegidas[n - 1]['id'] in aplicadas:
                    # 017:RF-127: con lo que dejó la obra (el largo y los extremos del enlace).
                    hecho = {'enlace': fila['enlace']} if fila.get('enlace') else {}
                    registrar_obra_aplicada(ws, plan['project'], fila['variacion'],
                                            {**elegidas[n - 1], **hecho})
            ws.obras = [o for o in ws.obras if o['id'] not in aplicadas]
            ws.save()
        # 024:RF-1 / RF-32: las obras pasan a «Con proyecto» con su alternativa del PIDE.
        from ..digital_twin.integration import obras_pide

        _gemelo(ws, ctx, plan, {**informe, 'obras': obras_pide(plan['obras'], informe.get('obras') or [])},
                caso='con_proyecto', rutas={'resultado': report})
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


def _alternativas_del_proyecto(ws: Workspace, project: str, feeders: list[str]) -> list[dict]:
    """Las alternativas del informe con las obras aplicadas del proyecto (017:RF-128)."""
    from ..informes import alternativas_de_obras

    marcados = set(feeders)
    return alternativas_de_obras([a for a in ws.obras_aplicadas if a.get('project') == project
                                  and a['obra'].get('alimentador') in marcados])


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
                if rol == 'con' and estudio in ('flujo', 'flujo_desequilibrado'):
                    # 017:RF-130: cada alternativa del informe medida en esta misma ejecución.
                    alternativas = _alternativas_del_proyecto(ws, plan['project'], feeders)
                    if len(alternativas) > 1:
                        sub['alternativas'] = alternativas
                rc, inf, report = _guion_pf(ws, ctx, 'estudios_pf.py', sub,
                                            nombre=f'estudio_{rol}_{estudio}', cancelable=False,
                                            limite_s=plan['limite_s'])
                if inf.get('no_terminado'):
                    ctx.log(f'{estudio} en «{nombres[rol]}»: {inf["error"]}; se sigue con el siguiente.')
                elif estudio == 'flujo' and not inf.get('error'):
                    # 024:RF-1 / RF-28: el estado de cada caso, observado con su flujo.
                    _gemelo(ws, ctx, sub, inf, caso={'base': 'caso_base', 'sin': 'sin_proyecto',
                                                     'con': 'con_proyecto'}[rol],
                            rutas={'resultado': report})
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
    from ..estudios_pf import CON_PROYECTO

    # 024:RF-1: la transferencia no cambia el proyecto; queda el estado del caso en que corrió.
    episodio = _gemelo(ws, ctx, plan, informe,
                       caso='con_proyecto' if CON_PROYECTO in casos else 'sin_proyecto',
                       rutas={'resultado': report})
    return {'returncode': rc, 'report': report.name, 'project': plan['project'],
            'fichero': fichero.name if fichero.is_file() else None, 'informe': informe,
            'digital_twin_episode': episodio}


# ------------------------------------------------------------------ guiones del operador
def guiones_listar(ws: Workspace, ctx: JobContext, project: str) -> dict:
    """Los guiones DPL y Python de los casos y de la carpeta de guiones (RF-27)."""
    if not project.strip():
        raise UserError('Elija el proyecto de DIgSILENT.')
    bound = alimentadores_vinculados(ws, project.strip())
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
    bound = alimentadores_vinculados(ws, project.strip())
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
            else:
                # 024:RF-1 / RF-29: lo que hace un guion del operador es intencional.
                _gemelo(ws, ctx, plan, inf, caso=f"{plan['caso']}_proyecto", rutas={'resultado': report},
                        manual=True)
            resultados.append({'caso': caso, 'returncode': rc, 'report': report.name,
                               'codigo_guion': inf.get('codigo_guion'), 'salida': inf.get('salida') or [],
                               'error': inf.get('error'), 'no_terminado': bool(inf.get('no_terminado'))})
    except JobCancelled:
        cancelado = True
    return {'project': project.strip(), 'guion': nombre.strip(), 'origen': origen,
            'resultados': resultados, 'cancelado': cancelado}


# ------------------------------------------------------------------ informes (spec 017)
def _ultimo_estudio(ws: Workspace, rol: str, project: str | None = None) -> dict | None:
    """El último informe de flujo que dejó el paso de estudios en ese caso.

    El informe se arma con lo que guardaron los estudios al ejecutar «Sin proyecto» y
    «Con proyecto» desde la web, no con otra ejecución de DIgSILENT (el usuario,
    2026-10-15). Se prefiere el flujo desequilibrado: da la tensión de cada fase (RF-17).
    Con ``project``, solo los de ese proyecto: un espacio puede haber estudiado otro antes.
    """
    for patron in (f'estudio_{rol}_flujo_desequilibrado_*.json', f'estudio_{rol}_flujo_*.json'):
        ficheros = sorted((p for p in ws.out_dir.glob(patron)
                           if patron.endswith('desequilibrado_*.json') or 'desequilibrado' not in p.name),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        for fichero in ficheros:
            datos = json.loads(fichero.read_text(encoding='utf-8'))
            if project and str(datos.get('project') or '').strip() not in ('', project.strip()):
                continue
            if datos.get('medidas'):
                if 'desequilibrado' not in fichero.name:
                    # En el flujo equilibrado DIgSILENT da las tres fases iguales: el informe
                    # lleva una sola tensión, la trifásica (RF-18).
                    datos['medidas'] = {f: {**m, 'vm_min_fases': None} for f, m in datos['medidas'].items()}
                return {**datos, '_fichero': fichero.name}
    return None


def _fijas_de_la_calibracion(ws: Workspace, estudio: dict, alimentador: str) -> list[dict]:
    """Los clientes fijos de la última calibración del alimentador (015:RF-65).

    Del proyecto del estudio si lo dice; si no, de la única calibración de ese alimentador.
    """
    proyecto = str(estudio.get('project') or '').strip()
    candidatas = ([ws.calibraciones.get(proyecto, {}).get(alimentador)] if proyecto else
                  [c.get(alimentador) for c in ws.calibraciones.values()])
    candidatas = [c for c in candidatas if c]
    if len(candidatas) != 1:
        return []
    return list(candidatas[0].get('fijas') or [])


def informe_estudio(ws: Workspace, ctx: JobContext | None, formulario: dict) -> dict:
    """Escribe el informe de estudio eléctrico de un alimentador (spec 017, RF-1b, RF-29, RF-30).

    Estado actual: el último flujo de «Sin proyecto»; proyectado: el de «Con proyecto» con
    las obras del espacio que están en ese caso. Los datos del cliente y del encabezado
    son los del formulario: del modelo solo se toma la forma.
    """
    from datetime import date as _date

    from ..estudios_pf import CON_PROYECTO, SIN_PROYECTO, Limites
    from ..informe_docx import DatosEstudio, escribir_informe_estudio
    from ..informes import (Caso, ConfigInforme, Encabezado, Etapa, InformeError, etapa_de_obras,
                            obra_para_informe)
    from ..perfil_empresa import datos_perfil

    alimentador = str(formulario.get('alimentador') or '').strip()
    if not alimentador:
        raise UserError('Indique el alimentador del informe.')
    try:
        config = ConfigInforme.de_perfil(datos_perfil(), project_root())
        limites = formulario.get('limites') or {}
        if limites:
            config = config.con_limites(**{k: limites.get(k) for k in
                                           ('tension_min_pu', 'tension_max_pu', 'cargabilidad_max_pct')})
        config.modelo('estudio')
    except InformeError as exc:
        raise UserError(str(exc)) from exc
    lim: Limites = config.limites

    proyecto = str(formulario.get('project') or '').strip() or None
    sin = _ultimo_estudio(ws, 'sin', proyecto)
    if sin is None or alimentador not in (sin.get('medidas') or {}):
        raise UserError(f'No hay un flujo de «{SIN_PROYECTO}» de {alimentador}: ejecute antes el '
                        'estudio de flujo en el paso de estudios.')
    actual = Caso.desde_medida(SIN_PROYECTO, sin['medidas'][alimentador], lim)
    etapas = []
    con = _ultimo_estudio(ws, 'con', proyecto)
    obras = [o for o in (ws.obras or []) if o.get('alimentador') == alimentador
             and CON_PROYECTO in (o.get('casos') or [])]
    # 017:RF-35: y las ya aplicadas cuya variación está activa en el flujo de «Con proyecto».
    activas = set((con or {}).get('obras_activas') or [])
    obras += [a['obra'] for a in ws.obras_aplicadas
              if a.get('variacion') in activas and a['obra'].get('alimentador') == alimentador
              and (proyecto is None or a.get('project') == proyecto)]
    clave = etapa_de_obras(obras)
    fuentes = [sin['_fichero']]
    geo_sin = (sin.get('geo') or {}).get(alimentador) or {}
    # 017:RF-128: con alternativas medidas, una etapa por alternativa con sus obras propias;
    # el plano de cada una resalta todas las obras que lleva (RF-133).
    alternativas = [a for a in (con or {}).get('alternativas') or []
                    if alimentador in (a.get('medidas') or {})]
    resaltar: dict[str, dict] = {}
    geo_de: dict[str, dict] = {}
    existentes = sin['medidas'][alimentador].get('bancos') or []
    if con is not None and len(alternativas) > 1:
        por_variacion = {a['variacion']: a['obra'] for a in ws.obras_aplicadas
                         if a['obra'].get('alimentador') == alimentador
                         and (proyecto is None or a.get('project') == proyecto)}
        previas: set[str] = set()
        for alt in alternativas:
            geo_alt = (alt.get('geo') or {}).get(alimentador) or {}
            propias = [por_variacion[v] for v in alt['variaciones']
                       if v in por_variacion and v not in previas]
            todas = [por_variacion[v] for v in alt['variaciones'] if v in por_variacion]
            previas |= set(alt['variaciones'])
            # La consigna de cabecera es un ajuste de operación: va detrás de las obras.
            propias.sort(key=lambda o: o.get('clase') == 'consigna')
            descritas = [_obra_con_trechos(obra_para_informe(o), geo_alt, geo_sin) for o in propias]
            etapas.append(Etapa(alt['clave'], caso=Caso.desde_medida(
                CON_PROYECTO, alt['medidas'][alimentador], lim), obras=tuple(descritas),
                anio=formulario.get('anio')))
            resaltar[alt['clave']] = _resaltar(todas, geo_alt, geo_sin, existentes)
            geo_de[alt['clave']] = geo_alt
        fuentes.append(con['_fichero'])
    elif con is not None and alimentador in (con.get('medidas') or {}) and clave:
        geo_con = (con.get('geo') or {}).get(alimentador) or {}
        etapas.append(Etapa(clave, caso=Caso.desde_medida(CON_PROYECTO, con['medidas'][alimentador], lim),
                            obras=tuple(_obra_con_trechos(obra_para_informe(o), geo_con, geo_sin)
                                        for o in obras),
                            anio=formulario.get('anio')))
        resaltar[clave] = _resaltar(obras, geo_con, geo_sin, existentes)
        geo_de[clave] = geo_con
        fuentes.append(con['_fichero'])

    def lineas(valor) -> list[str]:
        if isinstance(valor, list):
            return [str(x).strip() for x in valor if str(x).strip()]
        return [x.strip() for x in str(valor or '').split('\n\n') if x.strip()]

    fecha = formulario.get('fecha')
    encabezado = Encabezado(fecha=_date.fromisoformat(fecha) if fecha else _date.today(),
                            asunto=str(formulario.get('asunto') or ''),
                            destinatario=str(formulario.get('destinatario') or ''),
                            lugar=str(formulario.get('lugar') or ''))
    imagenes = formulario.get('imagenes') or {}
    # 017:RF-11b: sin imágenes del formulario, las dibuja la web con la geografía y los
    # resultados que guardó el flujo de cada caso (DIgSILENT sin ventana no dibuja).
    from ..mapa_informe import MapaError, imagenes_del_estado

    varias = len(etapas) > 1
    estados = [('actual', geo_sin, 'estado actual')] + [
        (e.clave, geo_de.get(e.clave), f'alternativa {i}' if varias else 'estado proyectado')
        for i, e in enumerate(etapas, 1)]
    for clave, geo, estado in estados:
        if clave in imagenes or not geo:
            continue
        try:
            rutas = imagenes_del_estado(
                geo, ws.out_dir / 'imagenes_informe', f'{nombre_seguro(alimentador)}_{clave}',
                estado=estado, alimentador=alimentador,
                bandas_tension=config.bandas_tension_pct, bandas_carga=config.bandas_cargabilidad_pct,
                obras=resaltar.get(clave))
        except MapaError as exc:
            if ctx is not None:
                ctx.log(f'Sin imágenes del {estado}: {exc}')
            continue
        imagenes[clave] = {k: str(v) for k, v in rutas.items()}
    datos = DatosEstudio(alimentadores=[alimentador], encabezado=encabezado, actual=actual, etapas=etapas,
                         imagenes={k: {i: Path(r) if r else None for i, r in v.items()}
                                   for k, v in imagenes.items()},
                         numero=formulario.get('numero') or None,
                         antecedentes=lineas(formulario.get('antecedentes')),
                         descripcion=lineas(formulario.get('descripcion')),
                         bancos=tuple({**b, 'utm': _utm(b.get('gps')),                    # RF-135
                                       'sed_cercana': _sed_cercana(b.get('gps'), geo_sin)}
                                      for b in sin['medidas'][alimentador].get('bancos') or ()),
                         fijas=tuple(_fijas_de_la_calibracion(ws, sin, alimentador)))
    destino = ws.out_dir / f'informe_estudio_{nombre_seguro(alimentador)}_{uuid.uuid4().hex[:8]}.docx'
    try:
        huecos = escribir_informe_estudio(config, destino, datos)
    except InformeError as exc:
        raise UserError(str(exc)) from exc
    if ctx is not None:
        ctx.log(f'Informe de estudio de {alimentador}: {destino.name} ({len(huecos)} hueco(s)).')
    return {'informe': destino.name, 'json': destino.with_suffix('.json').name, 'huecos': huecos,
            'estudios': fuentes, 'etapa': clave}


def _utm(lat_lon) -> list[float] | None:
    """Coordenadas en el CRS del perfil (UTM en Electro Dunas), para la cuadrilla; sin
    perfil o sin pyproj, nada (P13: no se supone un CRS)."""
    from ..perfil_empresa import datos_perfil

    from ..geography import make_transformer

    crs = (datos_perfil() or {}).get('crs_origen')
    if not crs or not lat_lon:
        return None
    try:
        este, norte = make_transformer('EPSG:4326', crs).transform(lat_lon[1], lat_lon[0])
    except (ImportError, ValueError):
        return None
    return [round(este, 1), round(norte, 1)]


def _sed_cercana(gps, geo: dict) -> list | None:
    """La SED más cercana a un banco y su distancia en m (017:RF-135).

    En CA101 dos bancos existentes están en el nodo «14717», un número de sección que no
    dice nada al lector: a 18 m está SE20730. Las SED son las barras de baja tensión de la
    geografía, con el nombre que les da el conversor («<SED>_BT»).
    """
    import math

    if not gps:
        return None
    mejor = None
    for nombre, lat, lon, _u, kv in geo.get('barras') or []:
        if lat is None or not kv or kv >= 1.0:
            continue
        dx = math.radians(lon - gps[1]) * math.cos(math.radians(lat))
        d = 6371000.0 * math.hypot(dx, math.radians(lat - gps[0]))
        if mejor is None or d < mejor[1]:
            mejor = [nombre.removesuffix('_BT'), round(d)]
    return mejor


def _obra_con_trechos(obra: dict, geo: dict, geo_sin: dict) -> dict:
    """La obra de conductor con sus trechos desde-hasta (017:RF-132)."""
    from dataclasses import asdict

    from ..informes import trechos_de_conductor

    if obra.get('tipo') != 'conductor' or not obra.get('tramos'):
        return obra
    trechos = (trechos_de_conductor(geo, obra['tramos'], geo_sin)
               or trechos_de_conductor(geo_sin, obra['tramos'], geo_sin))
    if not trechos:
        return obra
    filas = []
    for t in trechos:
        fila = asdict(t)
        fila['desde_utm'], fila['hasta_utm'] = _utm(t.desde_gps), _utm(t.hasta_gps)
        fila['desde_sed'], fila['hasta_sed'] = _sed_cercana(t.desde_gps, geo), _sed_cercana(t.hasta_gps, geo)
        filas.append(fila)
    return {**obra, 'trechos': filas}


def _resaltar(obras: list[dict], geo: dict, geo_sin: dict, existentes=()) -> dict:
    """Lo que el plano de una alternativa resalta: tramos cambiados, bancos nuevos y los
    existentes en su nodo (017:RF-133, RF-135)."""
    from ..informes import trechos_de_conductor

    tramos = [t for o in obras if o.get('clase') == 'seccion' for t in o.get('tramos') or []]
    trechos = trechos_de_conductor(geo, tramos, geo_sin) if tramos else []
    return {'tramos': tramos, 'trechos': [(t.desde, t.hasta) for t in trechos],
            'bancos': [(o.get('barra') or o.get('nodo') or '', float(o.get('q_kvar') or 0))
                       for o in obras if o.get('clase') == 'condensador'],
            'existentes': [(b.get('nodo') or b.get('barra') or '', float(b.get('kvar') or 0))
                           for b in existentes if b.get('en_servicio')]}


def _cargas_nuevas_aplicadas(ws: Workspace, project: str) -> list[dict]:
    """Las cargas nuevas que dejó en DIgSILENT la aplicación del paso 3 (spec 007), la
    última de cada una, con su kW y kvar del plan y si se ingresó sola o en bloque.

    El informe de factibilidad (017:RF-47, RF-53) sale de lo ya aplicado desde la web,
    no de otra ejecución: la barra donde se conectó es su punto de diseño.
    """
    from ..demanda_medida import clave_codigo

    vistas: dict[tuple[str, str], dict] = {}
    informes = sorted(ws.out_dir.glob('cargas_pf_aplicacion_*.json'), key=lambda p: p.stat().st_mtime)
    for fichero in informes:
        try:
            datos = json.loads(fichero.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if str(datos.get('project') or '').strip() != project.strip() or not datos.get('cargas'):
            continue
        token = fichero.stem.rsplit('_', 1)[-1]
        plan_path = ws.plans_dir / f'cargas_pf_{token}.json'
        try:
            plan = json.loads(plan_path.read_text(encoding='utf-8')) if plan_path.is_file() else {}
        except (OSError, ValueError):
            plan = {}
        filas = {clave_codigo(n.get('sed')): n for n in plan.get('nuevas') or []}
        for c in datos['cargas']:
            fila = filas.get(clave_codigo(c.get('sed')), {})
            vistas[(clave_codigo(c.get('alimentador')), clave_codigo(c.get('sed')))] = {
                'sed': c.get('sed'), 'alimentador': c.get('alimentador'), 'barra': c.get('barra'),
                # 025:RF-44: si la barra ya existía o la crea la variación de la carga.
                'criterio': c.get('criterio'),
                'variacion': c.get('variacion'), 'distancia_m': c.get('distancia_m'),
                'kw': fila.get('kw'), 'kvar': fila.get('kvar'), 'kva_instalado': fila.get('kva_instalado'),
                # 008:RF-24: la del formulario lleva la hoja «formulario»; las del libro, la suya.
                'sola': fila.get('hoja') == 'formulario', 'informe': fichero.name,
            }
    return list(vistas.values())


def _factor_de_carga_cabecera(ws: Workspace, job_id: str | None) -> dict[str, dict]:
    """Factor de carga de cada medidor de la última máxima buscada, en el mes de su máxima
    (017:RF-60). La curva solo vive en memoria: tras reiniciar la web hay que volver a
    buscar la máxima o escribir el factor a mano (RF-61)."""
    from ..informes import factor_de_carga

    with ws.lock:
        curvas = dict(ws.curvas_cabecera.get(job_id or '') or {})
    out = {}
    for medidor, entrada in curvas.items():
        curva = entrada.get('curva') or []
        if not curva:
            continue
        pico = max(curva, key=lambda p: p[1])[0]
        del_mes = [p for p in curva if (p[0].year, p[0].month) == (pico.year, pico.month)]
        fc = factor_de_carga(del_mes)
        if fc is not None:
            out[medidor] = {'fc': round(fc, 4), 'mes': f'{pico.year:04d}-{pico.month:02d}'}
    return out


def _informes_generados(ws: Workspace) -> list[dict]:
    """Los informes ya escritos en el espacio, el más reciente primero (017:RF-104)."""
    out = []
    for fichero in ws.out_dir.glob('informe_*.json'):
        docx_path = fichero.with_suffix('.docx')
        if not docx_path.is_file():
            continue
        try:
            datos = json.loads(fichero.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        alimentadores = datos.get('alimentadores') or (
            [datos['solicitud']['alimentador']] if datos.get('solicitud') else [])
        out.append({'tipo': datos.get('tipo'), 'docx': docx_path.name, 'json': fichero.name,
                    'alimentadores': alimentadores, 'numero': datos.get('numero'),
                    'fecha': (datos.get('encabezado') or {}).get('fecha'),
                    'huecos': datos.get('huecos') or [], 'factible': datos.get('factible'),
                    'creado': docx_path.stat().st_mtime})
    return sorted(out, key=lambda x: x['creado'], reverse=True)


def informes_contexto(ws: Workspace, project: str, feeders: list[str], job_id: str | None = None) -> dict:
    """Lo que la web ya tiene para los dos informes (spec 017, paso 4.4): qué falta en el
    perfil, los flujos guardados de 4.2, las obras de «Con proyecto», las cargas nuevas del
    paso 3, el factor de carga de la máxima de 2.2 y los informes ya escritos.

    Solo lee lo guardado, nada de DIgSILENT, para que el operador vea antes de generar de
    dónde sale cada dato (RF-75 a RF-78, RF-89 a RF-92, RF-104).
    """
    from ..demanda_medida import clave_codigo
    from ..estudios_pf import CON_PROYECTO
    from ..informes import TIPOS, ConfigInforme, InformeError
    from ..perfil_empresa import datos_perfil

    faltan: dict[str, list[str]] = {}
    limites: dict = {}
    try:
        config = ConfigInforme.de_perfil(datos_perfil(), project_root())
        for tipo in TIPOS:
            # La banda y el umbral que falten se piden en el formulario (RF-81).
            faltan[tipo] = [x for x in config.faltan(tipo) if x.startswith('informes.')]
            modelo = config.modelos.get(tipo)
            if modelo is not None and not modelo.is_file():
                faltan[tipo].append(f'el modelo {modelo.name} no existe')
        limites = dict(config.limites_parciales)
    except InformeError as exc:
        faltan = {tipo: [str(exc)] for tipo in TIPOS}
    claves = {clave_codigo(f) for f in feeders}
    estudios = {}
    for rol in ('sin', 'con'):
        datos = _ultimo_estudio(ws, rol, project)
        estudios[rol] = None if datos is None else {
            'fichero': datos['_fichero'],
            'alimentadores': {f: bool(m.get('converge')) for f, m in (datos.get('medidas') or {}).items()
                              if clave_codigo(f) in claves},
        }
    obras: dict[str, int] = {}
    for o in ws.obras or []:
        if clave_codigo(o.get('alimentador')) in claves and CON_PROYECTO in (o.get('casos') or []):
            obras[o['alimentador']] = obras.get(o['alimentador'], 0) + 1
    # 017:RF-35: y las ya aplicadas activas en el último flujo de «Con proyecto», como las
    # cuenta el informe: el formulario decía «0 obras» con cuatro aplicadas en TA225 e
    # IN111 (2026-10-15).
    con = _ultimo_estudio(ws, 'con', project)
    activas = set((con or {}).get('obras_activas') or [])
    for a in ws.obras_aplicadas or []:
        f = a['obra'].get('alimentador')
        if a.get('variacion') in activas and a.get('project') == project.strip()                 and clave_codigo(f) in claves:
            obras[f] = obras.get(f, 0) + 1
    cargas = [c for c in _cargas_nuevas_aplicadas(ws, project) if clave_codigo(c['alimentador']) in claves]
    return {'faltan': faltan, 'limites': limites, 'estudios': estudios, 'obras': obras,
            'cargas': cargas, 'factor_carga': _factor_de_carga_cabecera(ws, job_id),
            'generados': _informes_generados(ws),
            'formularios': dict((ws.informes.get('formularios') or {}).get(project.strip()) or {}),
            'libro_perdidas': _perdidas_del_libro(ws, list(feeders))}


#: Tope de lo que se guarda de un formulario de 4.4: textos de antecedentes, no ficheros.
MAX_FORMULARIO_BYTES = 200_000


def informes_formulario_guardar(ws: Workspace, project: str, tipo: str, datos: dict) -> dict:
    """Lo escrito en un formulario de 4.4, con el espacio y en el servidor (017:RF-82)."""
    from ..informes import TIPOS

    if tipo not in TIPOS:
        raise UserError(f'Tipo de informe desconocido: {tipo}.')
    if len(json.dumps(datos, ensure_ascii=False)) > MAX_FORMULARIO_BYTES:
        raise UserError('El formulario es demasiado grande para guardarlo.')
    with ws.lock:
        ws.informes.setdefault('formularios', {}).setdefault(project.strip(), {})[tipo] = datos
        ws.save()
    return {'guardado': True}


def informes_carpeta_perdidas(ws: Workspace) -> Path:
    return ws.root / 'informes' / 'perdidas'


def informes_perdidas_asignar(ws: Workspace, path: Path, origin: str) -> dict:
    """El libro de pérdidas de la empresa del informe de factibilidad (017:RF-93)."""
    if not path.is_file() or path.suffix.lower() not in ('.xlsx', '.xlsm'):
        raise UserError(f'{path.name}: el libro de pérdidas tiene que ser .xlsx o .xlsm.')
    with ws.lock:
        ws.informes['libro_perdidas'] = {'path': str(path), 'name': path.name, 'origin': origin}
        ws.save()
    return {'name': path.name, 'origin': origin}


def informes_perdidas_quitar(ws: Workspace) -> dict:
    import shutil

    with ws.lock:
        ws.informes.pop('libro_perdidas', None)
        ws.save()
    shutil.rmtree(informes_carpeta_perdidas(ws), ignore_errors=True)
    return {'quitado': True}


def _perdidas_del_libro(ws: Workspace, alimentadores: list[str]) -> dict | None:
    """Lo que el libro de pérdidas dice de cada alimentador, o por qué no se lee (RF-94).

    Las hojas y columnas las da el perfil de empresa (RF-63): sin ellas, el error nombra
    las claves que faltan.
    """
    from dataclasses import asdict

    from ..libros_informe import ColumnasPerdidas, LibroError, leer_libro_perdidas
    from ..perfil_empresa import datos_perfil

    meta = ws.informes.get('libro_perdidas')
    if not meta:
        return None
    out = {'name': meta['name'], 'origin': meta.get('origin'), 'lecturas': {}, 'error': None}
    try:
        columnas = ColumnasPerdidas.de_perfil(datos_perfil())
        for alimentador in alimentadores:
            out['lecturas'][alimentador] = asdict(leer_libro_perdidas(Path(meta['path']), alimentador, columnas))
    except LibroError as exc:
        out['error'] = str(exc)
    return out


def _proyecto_transmision(transmision: str | None) -> str:
    """El proyecto de transmisión pedido, o el del perfil de empresa (RF-65, RF-95)."""
    from ..informes import ConfigInforme, InformeError
    from ..perfil_empresa import datos_perfil

    if transmision and transmision.strip():
        return transmision.strip()
    try:
        proyecto = ConfigInforme.de_perfil(datos_perfil(), project_root()).proyecto_transmision
    except InformeError as exc:
        raise UserError(str(exc)) from exc
    if not proyecto:
        raise UserError('El perfil de empresa no indica el proyecto de transmisión '
                        '(informes.proyecto_transmision): escríbalo en 4.4.2.')
    return proyecto


def transformador_set_listar(ws: Workspace, ctx: JobContext, transmision: str | None = None) -> dict:
    """Cargas de barra del proyecto de transmisión con su transformador, y sus casos (T10).

    En AD08 no hay una carga por alimentador (sonda del 2026-10-15): el operador elige la
    de la barra de la SET de la que cuelga el alimentador.
    """
    proyecto = _proyecto_transmision(transmision)
    ctx.log(f'Proyecto de transmisión: {proyecto}  ·  cargas de barra y casos de estudio')
    _rc, informe, _report = _guion_pf(ws, ctx, 'transformador_set_pf.py',
                                      {'project': proyecto, 'folder': carpeta_pf()},
                                      nombre='trafo_set_listar', args=('--listar',), cancelable=False)
    if informe.get('error'):
        raise UserError(informe['error'])
    return {**informe, 'project': proyecto}


def transformador_set_calcular(ws: Workspace, ctx: JobContext, project: str, alimentador: str,
                               carga: str, caso: str, transmision: str | None = None) -> dict:
    """Cargabilidad del devanado de la SET sin y con proyecto (spec 017, RF-65 a RF-68).

    Decidido por el usuario el 2026-10-15: sin proyecto, el caso de transmisión tal cual;
    con proyecto, a la carga de la barra se le suma el Δ P/Q de cabecera «Con − Sin
    proyecto» del alimentador, de los flujos que ya guardó 4.2: nada se vuelve a simular
    en el proyecto del alimentador. Nada se guarda en el de transmisión (RF-68).
    """
    from ..estudios_pf import CON_PROYECTO, SIN_PROYECTO

    proyecto = _proyecto_transmision(transmision)
    sin, con = _ultimo_estudio(ws, 'sin', project), _ultimo_estudio(ws, 'con', project)
    medidas = []
    for rol, datos in ((SIN_PROYECTO, sin), (CON_PROYECTO, con)):
        medida = ((datos or {}).get('medidas') or {}).get(alimentador)
        if not medida or medida.get('cabecera_kw') is None or medida.get('cabecera_kvar') is None:
            raise UserError(f'No hay un flujo convergido de «{rol}» de {alimentador} en 4.2: sin él no '
                            'se sabe cuánto sube la cabecera.')
        medidas.append(medida)
    delta_kw = float(medidas[1]['cabecera_kw']) - float(medidas[0]['cabecera_kw'])
    delta_kvar = float(medidas[1]['cabecera_kvar']) - float(medidas[0]['cabecera_kvar'])
    ctx.log(f'{proyecto} · {caso or "caso activo"} · {carga}: Δ de {alimentador} '
            f'{delta_kw:+.1f} kW, {delta_kvar:+.1f} kvar (de {sin["_fichero"]} y {con["_fichero"]})')
    rc, informe, report = _guion_pf(
        ws, ctx, 'transformador_set_pf.py',
        {'project': proyecto, 'folder': carpeta_pf(), 'caso': caso, 'carga': carga,
         'delta_kw': delta_kw, 'delta_kvar': delta_kvar},
        nombre='trafo_set', cancelable=False)
    if informe.get('error'):
        raise UserError(informe['error'])
    t_sin = ((informe.get('sin') or {}).get('trafos') or [None])[0]
    t_con = ((informe.get('con') or {}).get('trafos') or [None])[0]
    if t_sin is None or t_con is None:
        raise UserError(f'La barra de {carga} no tiene transformador con resultados en {informe.get("caso")}.')
    return {'project': proyecto, 'caso': informe.get('caso'), 'carga': carga, 'report': report.name,
            'delta_kw': delta_kw, 'delta_kvar': delta_kvar, 'avisos': informe.get('avisos') or [],
            'transformador': t_sin['nombre'],
            'devanado': {'kv': t_sin['kv'], 'sin_pct': t_sin['devanado_pct'], 'con_pct': t_con['devanado_pct']}}


def carga_del_informe(ws: Workspace, project: str, alimentador: str, sed: str) -> dict:
    """La carga nueva del informe de factibilidad, que tiene que estar aplicada y sola (RF-47)."""
    from ..demanda_medida import clave_codigo

    carga = next((c for c in _cargas_nuevas_aplicadas(ws, project)
                  if clave_codigo(c['sed']) == clave_codigo(sed)
                  and clave_codigo(c['alimentador']) == clave_codigo(alimentador)), None)
    if carga is None:
        raise UserError(f'{sed} no es una carga nueva aplicada en {alimentador} de {project}: '
                        'intégrela antes en el paso 3.')
    if not carga['sola']:
        raise UserError(f'{sed} se ingresó en bloque con el libro de cargas nuevas: el informe de '
                        'factibilidad es de una carga ingresada sola (formulario «Una carga nueva»).')
    return carga


def informe_factibilidad(ws: Workspace, ctx: JobContext | None, formulario: dict) -> dict:
    """Escribe el informe de factibilidad y punto de diseño de una carga nueva (spec 017,
    RF-47 a RF-72) con lo que ya guardó la web.

    Estado actual: el último flujo de «Sin proyecto» del paso 4.2; proyectado: el de «Con
    proyecto». Punto de diseño: la barra donde el paso 3 conectó la carga, con su tensión
    en el flujo de «Con proyecto» (RF-52, RF-53). Factor de carga de la máxima de cabecera
    del paso 2.2 o del formulario (RF-60, RF-61). Las pérdidas reconocidas y el
    transformador de la SET, del formulario mientras no se lean del libro de la empresa
    y del proyecto de transmisión (T5 y T10 de la spec): lo que falte queda señalado.
    """
    import math
    from datetime import date as _date

    from ..estudios_pf import CON_PROYECTO, SIN_PROYECTO
    from ..informe_docx import DatosFactibilidad, escribir_informe_factibilidad
    from ..informes import (Caso, ConfigInforme, Devanado, Encabezado, InformeError, Solicitud,
                            perdidas_anuales)
    from ..libros_informe import DatosPerdidas
    from ..perfil_empresa import datos_perfil

    project = str(formulario.get('project') or '').strip()
    alimentador = str(formulario.get('alimentador') or '').strip()
    carga = carga_del_informe(ws, project, alimentador, str(formulario.get('sed') or ''))
    try:
        config = ConfigInforme.de_perfil(datos_perfil(), project_root())
        limites = formulario.get('limites') or {}
        if limites:
            config = config.con_limites(**{k: limites.get(k) for k in
                                           ('tension_min_pu', 'tension_max_pu', 'cargabilidad_max_pct')})
        config.modelo('factibilidad')
    except InformeError as exc:
        raise UserError(str(exc)) from exc
    lim = config.limites

    sin, con = _ultimo_estudio(ws, 'sin', project), _ultimo_estudio(ws, 'con', project)
    for rol, datos in ((SIN_PROYECTO, sin), (CON_PROYECTO, con)):
        if datos is None or alimentador not in (datos.get('medidas') or {}):
            raise UserError(f'No hay un flujo de «{rol}» de {alimentador}: ejecute antes el estudio de '
                            'flujo en 4.2 con los dos casos.')
    medida_sin, medida_con = sin['medidas'][alimentador], con['medidas'][alimentador]
    actual = Caso.desde_medida(SIN_PROYECTO, medida_sin, lim)
    proyectado = Caso.desde_medida(CON_PROYECTO, medida_con, lim)

    s = formulario.get('solicitud') or {}
    solicitud = Solicitud(
        cliente=str(s.get('cliente') or '').strip(), ubicacion=str(s.get('ubicacion') or '').strip(),
        tipo_solicitud=str(s.get('tipo_solicitud') or '').strip(), potencia_kw=float(s['potencia_kw']),
        fecha_solicitud=_date.fromisoformat(s['fecha_solicitud']), alimentador=alimentador,
        set_nombre=str(s.get('set_nombre') or '').strip(), tension_kv=float(s['tension_kv']),
        transformador=str(s.get('transformador') or '').strip(),
        expediente=str(s.get('expediente') or '').strip(), en_concesion=s.get('en_concesion'))

    # RF-52: tensión de la barra de conexión en «Con proyecto»; kW y kvar, los de la carga.
    u = next((u for nombre, u in medida_con.get('barras') or [] if nombre == carga['barra']), None)
    punto = None
    if u is not None and medida_con.get('converge'):
        kw, kvar = float(carga.get('kw') or solicitud.potencia_kw), float(carga.get('kvar') or 0.0)
        kva = math.hypot(kw, kvar)
        kv_ll = u * solicitud.tension_kv
        punto = {'u_pu': u, 'kv_ll': kv_ll, 'kv_ln': kv_ll / math.sqrt(3), 'kva': kva, 'kw': kw,
                 'kvar': kvar, 'i_a': kva / (math.sqrt(3) * kv_ll) if kv_ll else None}

    fc = formulario.get('factor_carga')
    reconocidas = formulario.get('perdidas_reconocidas') or {}
    libro = None
    if any(v not in (None, '') for v in reconocidas.values()):
        faltan = [n for k, n in (('reconocido_kw_pct', 'pérdidas reconocidas en potencia'),
                                 ('reconocido_kwh_pct', 'pérdidas reconocidas en energía'),
                                 ('precio_compra', 'precio de compra de la energía'))
                  if reconocidas.get(k) is None]
        libro = DatosPerdidas(alimentador, reconocidas.get('sistema_electrico') or None,
                              reconocidas.get('reconocido_kw_pct'), reconocidas.get('reconocido_kwh_pct'),
                              reconocidas.get('precio_compra'), tuple(faltan),
                              reconocidas.get('codigo_sistema') or None)
    else:
        # RF-62: sin nada escrito a mano, lo del libro de pérdidas subido en 4.4.2.
        leido = _perdidas_del_libro(ws, [alimentador])
        if leido and leido['error']:
            raise UserError(f'Libro de pérdidas: {leido["error"]}')
        if leido:
            libro = DatosPerdidas(**leido['lecturas'][alimentador])

    def perdidas(caso: Caso):
        if fc is None or not caso.converge or caso.fuente is None or caso.perdidas is None:
            return None
        try:
            return perdidas_anuales(caso.fuente.kw, caso.perdidas.kw, float(fc),
                                    libro.reconocido_kwh_pct if libro else None,
                                    libro.precio_compra if libro else None)
        except InformeError:
            return None

    t = formulario.get('transformador_set') or {}
    devanado = (Devanado(float(t['kv']), t.get('sin_pct'), t.get('con_pct'))
                if t.get('kv') and (t.get('sin_pct') is not None or t.get('con_pct') is not None) else None)
    # RF-50: otras cargas del alimentador ingresadas en bloque, que están en «Con proyecto».
    en_bloque = any(not c['sola'] for c in _cargas_nuevas_aplicadas(ws, project)
                    if c['alimentador'] == carga['alimentador'])
    fuentes = [f'el modelo de la red de media tensión del alimentador {alimentador} en DIgSILENT PowerFactory',
               'la máxima demanda medida en la cabecera del alimentador',
               f'la demanda de {solicitud.potencia_kw:g} kW solicitada por el interesado']
    fecha = formulario.get('fecha')
    encabezado = Encabezado(fecha=_date.fromisoformat(fecha) if fecha else _date.today(),
                            asunto=str(formulario.get('asunto') or ''),
                            destinatario=str(formulario.get('destinatario') or ''),
                            lugar=str(formulario.get('lugar') or ''))
    datos = DatosFactibilidad(
        encabezado=encabezado, actual=actual, proyectado=proyectado, solicitud=solicitud,
        punto_diseno=punto, codigo_punto=str(formulario.get('codigo_punto') or '').strip() or carga['barra'],
        solicitudes_vigentes=en_bloque, perdidas_actual=perdidas(actual),
        perdidas_proyectado=perdidas(proyectado), libro=libro, devanado=devanado,
        caso_transmision=str(t.get('caso') or ''), fuentes=fuentes,
        numero=formulario.get('numero') or None)
    destino = ws.out_dir / (f'informe_factibilidad_{nombre_seguro(alimentador)}_'
                            f'{nombre_seguro(str(carga["sed"]))}_{uuid.uuid4().hex[:8]}.docx')
    try:
        huecos = escribir_informe_factibilidad(config, destino, datos)
    except InformeError as exc:
        raise UserError(str(exc)) from exc
    resumen = json.loads(destino.with_suffix('.json').read_text(encoding='utf-8'))
    if ctx is not None:
        ctx.log(f'Informe de factibilidad de {carga["sed"]} en {alimentador}: {destino.name} '
                f'({len(huecos)} hueco(s)); {"factible" if resumen.get("factible") else "no factible"}.')
    return {'informe': destino.name, 'json': destino.with_suffix('.json').name, 'huecos': huecos,
            'estudios': [sin['_fichero'], con['_fichero']], 'factible': resumen.get('factible'),
            'excesos': resumen.get('excesos') or [], 'punto_diseno': punto, 'carga': carga}


# ---------------------------------------------------------------------------
# Asistente de órdenes (spec 026)
# ---------------------------------------------------------------------------

#: Planes a la espera de confirmación, por espacio: viven en memoria como los de cargas.
_ASISTENTE_PLANES: dict[str, dict[str, dict]] = {}
_ASISTENTE_CERROJO = threading.Lock()


def gemelo_evaluar(ws: Workspace, ctx: JobContext) -> dict:
    """Cuánto se apartan de DIgSILENT el modelo del gemelo y la física (024:RF-74), en otro proceso."""
    import sys

    from ..digital_twin.buffer import raiz_buffer

    report = ws.out_dir / f'gemelo_evaluacion_{uuid.uuid4().hex[:8]}.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    rc = ctx.run_process([sys.executable, str(_script('digital_twin_entrenar.py')), '--evaluar',
                          '--output-json', str(report), '--raiz', str(raiz_buffer())], cwd=str(project_root()))
    try:
        r = json.loads(report.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise UserError(f'La evaluación del gemelo terminó con el código {rc} sin informe.') from None
    return {'modelo': r.get('modelo'), 'por_particion': r.get('por_particion'), 'informe': report.name}


def asistente_vocabulario(ws: Workspace) -> dict[str, list[str]]:
    """Lo que existe y contra lo que se contrastan los datos de una orden (026:RF-6)."""
    vocab: dict[str, list[str]] = {
        'alimentadores': [r['network_id'] for r in feeder_rows(ws)],
        'proyecto': [str(p.get('name')) for p in pf_proyectos_guardados(ws).get('projects') or [] if p.get('name')],
    }
    try:
        e = estructura_del_espacio(ws)
    except (UserError, ValueError, OSError):
        e = None
    vocab['sistema'] = list(e.zonales) if e is not None else []
    if not vocab['alimentadores'] and e is not None:
        # Sin fuente cargada, los de la estructura de la empresa: tras reiniciar la web ningún
        # espacio tenía su inventario en memoria y el asistente no reconocía ni IN111 (2026-10-24).
        vocab['alimentadores'] = sorted(a.codigo for a in e.alimentadores.values())
    from ..asistente.clasificador import subtipos_del_perfil

    vocab['subtipo'] = subtipos_del_perfil()
    return vocab


def _asistente_modelos() -> tuple[Any, Any]:
    """El Transformer promovido y el cliente de Ollama, o ``None`` el que no esté (RNF «Compatible»)."""
    try:
        from ..asistente import transformer

        modelo = transformer.cargar()
    except (ImportError, RuntimeError, OSError, ValueError, KeyError):
        modelo = None
    from ..asistente.ollama import cliente_configurado

    return modelo, cliente_configurado()


def _asistente_clasificador():
    try:
        from ..asistente import clasificador

        return clasificador.cargar()
    except (ImportError, RuntimeError, OSError, ValueError, KeyError):
        return None


def _asistente_respuesta(ws: Workspace, plan, trabajos: list[dict]) -> dict:
    """Las consultas se responden en la misma petición con lo que ya hay (026:RF-9)."""
    t, datos = plan.tarea, plan.datos
    if t == 'estado':
        filas = feeder_rows(ws)
        salidas = [p for p in ws.out_dir.rglob('*') if p.is_file()] if ws.out_dir.is_dir() else []
        en_curso = [j for j in trabajos if j.get('status') not in ('done', 'failed', 'cancelled')]
        texto = (f"{'Fuente cargada' if ws.dataset is not None else 'Sin fuente cargada'}; {len(filas)} "
                 f'alimentador(es); {len(en_curso)} trabajo(s) en curso; {len(salidas)} fichero(s) de salida.')
        return {'texto': texto, 'trabajos': [{'titulo': j['title'], 'estado': j['status']} for j in en_curso]}
    if t == 'proyectos':
        nombres = [p.get('name') for p in pf_proyectos_guardados(ws).get('projects') or []]
        return {'texto': f'{len(nombres)} proyecto(s) conocidos.' if nombres else
                'La web aún no leyó los proyectos de DIgSILENT: pida «lee los proyectos de DIgSILENT».',
                'proyectos': nombres}
    if t == 'resultados_pide':
        hechos = [j for j in trabajos if j.get('kind') == 'pide' and j.get('status') == 'done'
                  and (not datos.get('proyecto') or (j.get('result') or {}).get('project') == datos['proyecto'])]
        if not hechos:
            return {'texto': 'No hay ningún PIDE terminado en este espacio' +
                    (f" para {datos['proyecto']}" if datos.get('proyecto') else '') + '.'}
        r = hechos[-1]['result']
        obras = [{k: o.get(k) for k in ('codigo', 'prioridad', 'anio', 'alternativa', 'alimentador', 'elemento',
                                        'ci', 'sobredimensionada', 'descartada')} for o in r.get('obras') or []]
        return {'texto': f"PIDE de {r.get('project')}: {len(obras)} obra(s), "
                         f"{len(r.get('implementadas') or [])} aplicada(s) solas; formatos en {r.get('formatos')}.",
                'obras': obras, 'entregables': [r.get('formatos')] if r.get('formatos') else [],
                'avisos': r.get('avisos') or []}
    if t == 'episodios':
        filas = gemelo_episodios(ws, {'proyecto': datos.get('proyecto')})
        cuenta: dict[str, int] = {}
        for f in filas:
            clave = f"{f.get('clase')} · {f.get('caso')}"
            cuenta[clave] = cuenta.get(clave, 0) + 1
        return {'texto': f'{len(filas)} episodio(s) en el búfer del gemelo.', 'por_clase': cuenta}
    if t == 'pregunta':
        return asistente_pregunta(str(datos.get('texto') or plan.texto))
    if t == 'clasificar_informe':
        # La orden entera: el trozo marcado se quedaba en «suministro para 800 kW» y perdía
        # «solicitud de factibilidad», que es lo que dice el tipo (2026-10-24).
        return asistente_clasificar(plan.texto)
    if t == 'buscar_internet':
        return asistente_buscar(ws, str(datos.get('texto') or plan.texto))
    raise UserError(f'La tarea {t} no es una consulta.')


def asistente_orden(ws: Workspace, texto: str, trabajos: list[dict] | None = None) -> dict:
    """Interpreta la orden, arma el plan y, si es una consulta, la responde (026:RF-2 a RF-9)."""
    from ..asistente import almacen
    from ..asistente.interprete import interpretar
    from ..asistente.plan import resolver

    texto = (texto or '').strip()
    if not texto:
        raise UserError('Escriba la orden.')
    if len(texto) > 2000:
        raise UserError('La orden es demasiado larga (máximo 2000 caracteres).')
    transformer, ollama = _asistente_modelos()
    interp = interpretar(texto, transformer=transformer, ollama=ollama)
    plan = resolver(interp, asistente_vocabulario(ws))
    extras = _asistente_extras(ws, plan, trabajos or [])
    _asistente_requisitos(ws, plan, extras)
    if plan.tarea in ('informe_estudio', 'informe_factibilidad'):
        if not plan.datos.get('subtipo'):
            c = _asistente_clasificador()
            if c is not None:
                r = c.clasificar(texto)
                plan.datos['subtipo'] = r['subtipo']
                plan.razonamiento.append(f"subtipo de estudio: {r['subtipo']} según el clasificador "
                                         f"({r['confianza_subtipo']:.0%}, 026:RF-14).")
        if not extras.get('formulario') and plan.datos.get('proyecto'):
            plan.faltan.append('el formulario del informe: rellénelo una vez en el paso 4.4 de la web')
    from ..asistente.ejecutor import describir

    publico = plan.publico()
    if plan.tarea and plan.modo == 'trabajo':
        publico['pasos'] = describir(plan.tarea, plan.datos, extras)
    with _ASISTENTE_CERROJO:
        _ASISTENTE_PLANES.setdefault(ws.id, {})[plan.id] = {'plan': plan, 'interp': interp, 'extras': extras}
    almacen.anotar('ordenes', {'espacio': ws.id, 'plan': plan.id, 'texto': texto, 'tarea': plan.tarea,
                               'modelo': plan.interpretado_por, 'confianza': plan.confianza, 'listo': plan.listo})
    out = {'plan': publico}
    if plan.listo and plan.modo == 'consulta':
        out['respuesta'] = _asistente_respuesta(ws, plan, trabajos or [])
    return out


#: Tareas que necesitan la fuente del espacio (RED, CARGA y EQUIPOS, una .mdb o un VNR-GIS).
_NECESITAN_FUENTE = ('cargar_fuente', 'convertir', 'unir', 'convertir_sistema', 'sistema_completo')


def _asistente_requisitos(ws: Workspace, plan, extras: dict) -> None:
    """Lo que la tarea necesita del espacio, comprobado con la misma validación de la web
    antes de ofrecer confirmar (026:RF-6).

    «carga la fuente» en un espacio sin entradas se ofrecía para confirmar y fallaba después
    en la ruta con «Faltan entradas: RED…» (2026-10-24): lo que falta se dice en el plan. Con
    las entradas puestas y la fuente sin cargar, convertir empieza por cargarla.
    """
    if plan.tarea not in _NECESITAN_FUENTE or (plan.tarea != 'cargar_fuente' and ws.dataset is not None):
        return
    try:
        check_ready(ws)
    except UserError as exc:
        plan.faltan.append(f'las entradas del espacio. {exc} Súbalas en «Entradas» (RED, CARGA y EQUIPOS, '
                           'una base .mdb o un paquete VNR-GIS) y repita la orden; para un proyecto ya '
                           'importado, use la fuente de su vínculo en «Cargas en DIgSILENT».')
        return
    if plan.tarea in ('convertir', 'unir', 'convertir_sistema'):
        extras['cargar_antes'] = True
        plan.razonamiento.append('La fuente del espacio no está cargada: primero se carga, con sus entradas.')


def _asistente_extras(ws: Workspace, plan, trabajos: list[dict]) -> dict:
    """Lo que la web sabe y la orden no dice: la última máxima y el formulario guardado del informe."""
    extras: dict[str, Any] = {}
    maximas = [j for j in trabajos if j.get('kind') == 'demanda_cabecera' and j.get('status') == 'done']
    if maximas:
        extras['ultima_maxima'] = maximas[-1]
    if plan.tarea in ('informe_estudio', 'informe_factibilidad') and plan.datos.get('proyecto'):
        tipo = 'estudio' if plan.tarea == 'informe_estudio' else 'factibilidad'
        extras['formulario'] = ((ws.informes.get('formularios') or {}).get(plan.datos['proyecto']) or {}).get(tipo)
    return extras


def asistente_plan(ws: Workspace, plan_id: str) -> dict:
    with _ASISTENTE_CERROJO:
        guardado = (_ASISTENTE_PLANES.get(ws.id) or {}).get(plan_id)
    if guardado is None:
        raise UserError('El plan ya no existe: vuelva a escribir la orden.')
    return guardado


def _ejemplo_de(texto: str, tarea: str, datos: dict) -> dict:
    """La orden como ejemplo de entrenamiento: cada dato con su posición en el texto (026:RF-19)."""
    from ..asistente.sinteticos import normalizar
    from ..asistente.tareas import TAREAS

    t = normalizar(texto)
    trozos = []
    for d in TAREAS[tarea].datos:
        valor = datos.get(d.nombre)
        for v in (valor if isinstance(valor, list) else [valor]):
            if v in (None, '') or not isinstance(v, (str, int)):
                continue
            i = t.find(normalizar(str(v)))
            if i >= 0 and not any(a < i + len(str(v)) and i < b for a, b, _ in trozos):
                trozos.append((i, i + len(str(v)), d.tipo))
    return {'texto': texto, 'tarea': tarea, 'datos': sorted(trozos)}


def asistente_ejecutar(ws: Workspace, ctx: JobContext, plan_id: str, base: str, http: Any = None) -> dict:
    """El plan confirmado, por las rutas y trabajos de la web (026:RF-10, RF-12); la orden queda
    como ejemplo confirmado (026:RF-19)."""
    from ..asistente import almacen
    from ..asistente.ejecutor import ClienteWeb, PasoFallido, ejecutar, entregables, pasos

    guardado = asistente_plan(ws, plan_id)
    plan = guardado['plan']
    if not plan.listo:
        raise UserError('El plan no está completo: ' + '; '.join(plan.faltan))
    almacen.anotar('ejemplos', {**_ejemplo_de(plan.texto, plan.tarea, plan.datos), 'origen': 'confirmado'})
    almacen.anotar('decisiones', {'plan': plan.id, 'tarea': plan.tarea, 'datos': plan.datos, 'decision': 'confirmada'})
    if plan.modo == 'proceso':
        return _asistente_proceso(ws, ctx, plan)
    if http is None:
        import requests

        http = requests.Session()
    cliente = ClienteWeb(http, base.rstrip('/'), ws.id, cancelado=ctx.cancel.is_set)
    try:
        resultado = ejecutar(pasos(plan.tarea, plan.datos, guardado['extras']), cliente, ctx.log)
    except PasoFallido as exc:
        raise UserError(f'El asistente paró: {exc}') from exc
    if plan.tarea in ('informe_estudio', 'informe_factibilidad'):
        resultado['clasificacion'] = _asistente_clasificar_generado(ws, plan, entregables(resultado.get('resultado')))
    ctx.log(f"Asistente: «{plan.tarea}» terminado; {len(resultado.get('entregables') or [])} entregable(s).")
    return {'plan': plan.id, 'tarea': plan.tarea, **resultado}


def _asistente_proceso(ws: Workspace, ctx: JobContext, plan) -> dict:
    """Las tareas que son herramientas de tools/ (sistema completo, reentrenar el asistente)."""
    import sys

    if plan.tarea == 'entrenar_asistente':
        return asistente_entrenar(ws, ctx)
    cmd = [sys.executable, str(_script('sistema_web.py')), '--espacio', ws.id, '--zonal', plan.datos['sistema'],
           '--periodo', plan.datos['periodo']]
    if plan.datos.get('ruta'):
        cmd += ['--demanda-dir', plan.datos['ruta']]
    rc = ctx.run_process(cmd, cwd=str(project_root()))
    if rc not in (0, 1):
        raise UserError(f'El sistema {plan.datos["sistema"]} no se pudo llevar hasta el final (código {rc}).')
    return {'plan': plan.id, 'tarea': plan.tarea, 'codigo': rc,
            'texto': 'calibrado y válido' if rc == 0 else 'calibrado con fallos: vea el registro'}


def _asistente_clasificar_generado(ws: Workspace, plan, nombres: list[str]) -> dict | None:
    """El informe recién escrito, clasificado y guardado como ejemplo (026:RF-14)."""
    from ..asistente import clasificador

    docx = next((ws.out_dir / n for n in nombres if n.endswith('.docx') and (ws.out_dir / n).is_file()), None)
    if docx is None:
        return None
    texto = clasificador.texto_de_docx(docx)
    if not texto:
        return None
    tipo = 'estudio' if plan.tarea == 'informe_estudio' else 'factibilidad'
    c = _asistente_clasificador()
    r = c.clasificar(texto) if c is not None else None
    subtipo = plan.datos.get('subtipo') or (r or {}).get('subtipo')
    if subtipo:
        clasificador.registrar(texto, tipo, subtipo, 'generado')
    return {'tipo': tipo, 'subtipo': subtipo, 'clasificador': r}


def asistente_corregir(ws: Workspace, plan_id: str, *, tarea: str | None = None, datos: dict | None = None,
                       tipo_informe: str | None = None, subtipo: str | None = None) -> dict:
    """La corrección del operador: un plan nuevo y un ejemplo corregido para aprender (026:RF-15, RF-19)."""
    from ..asistente import almacen
    from ..asistente.interprete import Interpretacion
    from ..asistente.plan import resolver
    from ..asistente.tareas import TAREAS

    guardado = asistente_plan(ws, plan_id)
    previo = guardado['plan']
    tarea = tarea or previo.tarea
    if tarea not in TAREAS:
        raise UserError(f'Tarea desconocida: {tarea}.')
    datos = {**previo.datos, **(datos or {})}
    por_tipo: dict[str, list[dict]] = {}
    for d in TAREAS[tarea].datos:
        v = datos.get(d.nombre)
        for x in (v if isinstance(v, list) else [v]):
            if x not in (None, ''):
                por_tipo.setdefault(d.tipo, []).append({'valor': str(x), 'confianza': 1.0})
    interp = Interpretacion(previo.texto, tarea, 1.0, 'operador', por_tipo, [], ['corrección del operador'])
    plan = resolver(interp, asistente_vocabulario(ws))
    if subtipo:
        plan.datos['subtipo'] = subtipo
    almacen.anotar('ejemplos', {**_ejemplo_de(previo.texto, tarea, plan.datos), 'origen': 'corregido'})
    almacen.anotar('decisiones', {'plan': previo.id, 'nuevo': plan.id, 'decision': 'corregida', 'tarea_antes':
                                  previo.tarea, 'tarea': tarea})
    if subtipo or tipo_informe:
        from ..asistente import clasificador

        tipo = tipo_informe or ('factibilidad' if tarea == 'informe_factibilidad' else 'estudio')
        clasificador.registrar(previo.texto, tipo, subtipo or plan.datos.get('subtipo') or '', 'corregido')
    extras = dict(guardado['extras']) if tarea == previo.tarea else {}
    _asistente_requisitos(ws, plan, extras)
    with _ASISTENTE_CERROJO:
        _ASISTENTE_PLANES.setdefault(ws.id, {})[plan.id] = {'plan': plan, 'interp': interp, 'extras': extras}
    return {'plan': plan.publico()}


def asistente_pregunta(texto: str) -> dict:
    """Cómo funciona el conversor, con cita de ficheros, funciones y RF (026:RF-17, RF-18)."""
    from ..asistente import indice
    from ..asistente.ollama import cliente_configurado

    ollama = cliente_configurado()
    if ollama.modelos() is None:
        ollama = None
    i = indice.cargar_o_construir(project_root(), ollama)
    r = indice.responder(i, texto, ollama)
    return {'texto': r['respuesta'], 'citas': r['citas'], 'sabe': r['sabe']}


def asistente_clasificar(texto: str) -> dict:
    """El tipo y el subtipo de estudio de un texto o un pedido (026:RF-14)."""
    c = _asistente_clasificador()
    if c is None:
        return {'texto': 'El clasificador de informes aún no está entrenado: pida «reentrena el asistente».'}
    r = c.clasificar(texto)
    return {'texto': f"{r['tipo']} · {r['subtipo']} ({r['confianza_subtipo']:.0%})", **r}


def asistente_buscar(ws: Workspace, texto: str) -> dict:
    """GitHub y arXiv con una consulta sin datos de la red (026:RF-29 a RF-31)."""
    from ..asistente.internet import Buscador

    vocab = asistente_vocabulario(ws)
    b = Buscador([*vocab['alimentadores'], *vocab['proyecto'], *vocab['sistema']])
    r = b.buscar(texto, motivo='orden del operador')
    if r['bloqueada']:
        return {'texto': f"No se buscó: la consulta {r['bloqueada']} (P9). Escríbala solo con términos técnicos.",
                **r}
    return {'texto': f"{len(r['github'])} repositorio(s) y {len(r['arxiv'])} artículo(s).", **r}


def asistente_proponer_libreria(ws: Workspace, ctx: JobContext, paquete: str, motivo: str) -> dict:
    """Ficha de una librería en una rama aparte, con su suite, para que el operador decida (026:RF-32)."""
    from ..asistente import mejoras
    from ..asistente.internet import Buscador

    vocab = asistente_vocabulario(ws)
    b = Buscador([*vocab['alimentadores'], *vocab['proyecto'], *vocab['sistema']])
    r = b.pypi(paquete.strip(), motivo)
    if r['bloqueada'] or not r['resultados']:
        raise UserError(f"No se pudo consultar {paquete}: {r['bloqueada'] or r.get('error') or 'no existe en PyPI'}.")
    ctx.log(f'Asistente: preparando la rama con la propuesta de {paquete}…')
    return mejoras.preparar_rama(project_root(), mejoras.propuesta_de_libreria(r['resultados'][0], motivo),
                                 suite=('-q', '-x', '-p', 'no:cacheprovider', 'tests/test_inventario.py'))


def asistente_decision_mejora(propuesta_id: str, decision: str, comentario: str = '') -> dict:
    from ..asistente import mejoras

    try:
        return mejoras.registrar_decision(propuesta_id, decision, comentario)
    except ValueError as exc:
        raise UserError(str(exc)) from exc


def asistente_registro() -> dict:
    """Lo que el asistente hizo y decidió, para auditarlo (026:RF-28, RF-31)."""
    from ..asistente import almacen, mejoras

    return {'ordenes': almacen.leer('ordenes', 50), 'decisiones': almacen.leer('decisiones', 50),
            'mejoras': mejoras.historial(), 'internet': almacen.leer('internet', 50),
            'suite': almacen.leer('suite', 10), 'avisos': almacen.leer('avisos', 50)}


def asistente_nuevos() -> tuple[int, int]:
    """Episodios del gemelo y órdenes del operador desde el último reentrenamiento que lanzó la
    vigilancia, contando ficheros y líneas sin abrir los episodios (026:RF-23)."""
    from ..asistente import almacen
    from ..digital_twin.buffer import raiz_buffer

    objetos = raiz_buffer() / 'objetos'
    episodios = sum(1 for _ in objetos.rglob('*.json')) if objetos.is_dir() else 0
    ordenes = len(almacen.leer('ejemplos'))
    antes = almacen.leer_json('vigilancia') or {}
    return episodios - int(antes.get('episodios', episodios)), ordenes - int(antes.get('ordenes', 0))


def asistente_marcar_entrenado(gemelo: bool) -> None:
    """Lo que ya se usó para reentrenar, para no volver a lanzarlo cada minuto."""
    from ..asistente import almacen
    from ..digital_twin.buffer import raiz_buffer

    antes = almacen.leer_json('vigilancia') or {}
    objetos = raiz_buffer() / 'objetos'
    if gemelo:
        antes['episodios'] = sum(1 for _ in objetos.rglob('*.json')) if objetos.is_dir() else 0
    else:
        antes['ordenes'] = len(almacen.leer('ejemplos'))
    almacen.guardar_json('vigilancia', antes)


def asistente_entrenar(ws: Workspace, ctx: JobContext) -> dict:
    """Reentrena el Transformer y el clasificador en otro proceso (026:RF-20), con el vocabulario del espacio."""
    import sys

    from ..asistente import almacen

    vocab = almacen.guardar_json('vocabulario', asistente_vocabulario(ws))
    report = ws.out_dir / f'asistente_entrenamiento_{uuid.uuid4().hex[:8]}.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    rc = ctx.run_process([sys.executable, str(_script('asistente_entrenar.py')), '--vocabulario', str(vocab),
                          '--output-json', str(report)], cwd=str(project_root()))
    try:
        return json.loads(report.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise UserError(f'El entrenamiento del asistente terminó con el código {rc} sin informe.') from None
