"""Las acciones de la interfaz, sin interfaz.

Cada función de aquí es lo que hacía un botón de la GUI de escritorio, pero sin Tk y
sin diálogos: recibe el espacio de trabajo y un :class:`JobContext`, escribe en el
Registro y devuelve un resultado serializable. Las rutas de la API solo validan,
encolan y responden.

Dos defectos de la GUI de escritorio se corrigen aquí en lugar de copiarse:

* «Cargar fichero y actualizar» llamaba a ``loads.read_template``, que no existe; el
  botón fallaba siempre. Aquí se usa ``loads.read_workbook``.
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
    from .source_runs import create_source_run
    from .sources import adapter_for

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
        state = 'DGS_READY' if conv.get('status') == 'ok' else readiness['status']
        rows.append({
            **row,
            'readiness': state,
            'blocking_codes': list(readiness.get('blocking_codes') or []),
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


def _write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8',
    )
    temporary.replace(path)


def _stamp_source_manifest(ws: Workspace, manifest: dict, snapshot) -> None:
    """Liga el manifiesto y la metadata DGS a la ejecución que los produjo."""
    source = {
        'source_run_id': snapshot.run_id,
        'source_mode': snapshot.mode,
        'source_fingerprint': snapshot.fingerprint,
    }
    manifest.update(source)
    for item in manifest.get('feeders') or []:
        item.update(source)
        metadata_path = item.get('feeder_metadata')
        if not metadata_path:
            continue
        path = Path(metadata_path)
        if not path.is_file():
            continue
        metadata = json.loads(path.read_text(encoding='utf-8'))
        metadata.update(source)
        _write_json_atomic(path, metadata)
    _write_json_atomic(ws.out_dir / 'batch_manifest.json', manifest)


def check_convert_options(ws: Workspace) -> None:
    """Lo que la GUI comprobaba con diálogos antes de lanzar el lote."""
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

    snapshot = require_active_source_run(ws)
    selected = check_selection_readiness(ws, feeders, all_feeders)
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
        ws.dataset, None if all_feeders else feeders, ws.out_dir,
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
        catalogo=catalogo_del_proyecto(),
    )
    _stamp_source_manifest(ws, manifest, snapshot)
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
        evidence.append({
            'target': feeder,
            'dgs': dgs.name,
            'dgs_sha256': metadata['dgs_sha256'],
            'metadata': metadata_path.name,
        })
    return {
        'source_run_id': snapshot.run_id,
        'source_mode': snapshot.mode,
        'source_fingerprint': snapshot.fingerprint,
        'targets': evidence,
    }


def check_powerfactory_flow(ws: Workspace, feeders: list[str]) -> None:
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

    pf_dir, interpreter = _require_pf()
    ctx.log(f'Intérprete para la API: {interpreter}  [{powerfactory_status()["interpreter_reason"]}]')
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
               '--ensure-scenario', '--run-load-flow']
        metadata_path = dgs.with_name(f'{dgs.stem}_feeder_metadata.json')
        cmd += ['--feeder-metadata', str(metadata_path)]
        if source_evidence is not None:
            cmd += [
                '--source-run-id', source_evidence['source_run_id'],
                '--source-mode', source_evidence['source_mode'],
                '--source-fingerprint', source_evidence['source_fingerprint'],
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

    try:
        modelo = build_feeder_model(
            ws.dataset, feeder, strict=False,
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


# ---------------------------------------------------------------------------
# Varios alimentadores en un solo DGS
# ---------------------------------------------------------------------------


def group_selection(ws: Workspace, feeders: list[str], all_feeders: bool) -> list[str]:
    require_loaded(ws)
    feeders = check_selection_readiness(ws, feeders, all_feeders)
    if len(feeders) < 2:
        raise UserError('Para unir en un solo DGS seleccione al menos dos alimentadores.')
    from ..batch import expand_connected_feeders

    expanded = [feeder_short_name(n) for n in expand_connected_feeders(ws.dataset, feeders)]
    return check_selection_readiness(ws, expanded, False)


def group_name(nombre: str, feeders: list[str]) -> str:
    base = (nombre or '').strip() or '_'.join(feeders[:4]) + ('_ETC' if len(feeders) > 4 else '')
    limpio = ''.join(c if c.isalnum() or c in '-_' else '_' for c in base)[:60]
    return limpio or 'GRUPO'


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

    snapshot = require_active_source_run(ws)
    check_selection_readiness(ws, feeders, False)
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
        ws.dataset, feeders, ws.out_dir, name=nombre,
        aliases=load_aliases(snapshot.path_for('aliases') or None),
        strict=bool(opts['strict']),
        source_crs=opts['source_crs'] or 'EPSG:32718',
        target_crs=opts['target_crs'] or 'EPSG:4326',
        catalog_corrections=ws.catalog_corrections() or None,
        reglas=reglas_de(ws), catalogo=catalogo_del_proyecto(),
        on_progress=on_progress, cancel=ctx.cancel,
    )
    source = {
        'source_run_id': snapshot.run_id,
        'source_mode': snapshot.mode,
        'source_fingerprint': snapshot.fingerprint,
    }
    man.update(source)
    metadata_path = man.get('feeder_metadata')
    if metadata_path and Path(metadata_path).is_file():
        metadata = json.loads(Path(metadata_path).read_text(encoding='utf-8'))
        metadata.update(source)
        _write_json_atomic(Path(metadata_path), metadata)
    _write_json_atomic(ws.out_dir / f'{nombre}_manifest.json', man)
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
            'source_fingerprint')}
        ws.groups[nombre]['requested_feeders'] = list(requested_feeders or feeders)
        ws.groups[nombre]['converted_at'] = time.time() if man['status'] == 'ok' else None
        ws.save()
    return {'group': nombre, 'status': man['status'], 'error': man.get('error'),
            'dgs': f'{nombre}.dgs' if man['status'] == 'ok' else None,
            'feeder_metadata': f'{nombre}_feeder_metadata.json' if man['status'] == 'ok' else None,
            'feeders': feeders, 'completitud': man.get('completitud'),
            'hoja': man.get('hoja'), 'manifest': f'{nombre}_manifest.json'}


def load_template(ws: Workspace, feeder: str, fmt: str) -> Path:
    from ..loads import LoadTemplateError, model_sed_loads, write_template

    model = build_model(ws, feeder)
    if not model.seds:
        raise UserError(f'{model.name} no tiene SED en el export: no hay cargas que actualizar.')
    out = ws.out_dir / 'plantillas' / f'{model.name}_cargas.{fmt}'
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        return write_template(model_sed_loads(model), out)
    except LoadTemplateError as exc:
        raise UserError(str(exc)) from exc


def _store_plan(ws: Workspace, kind: str, feeder: str, payload: dict, extra: dict) -> dict:
    token = uuid.uuid4().hex[:12]
    ws.plans_dir.mkdir(parents=True, exist_ok=True)
    path = ws.plans_dir / f'{feeder}_{kind}_{token}.json'
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    ws.plans[token] = {'kind': kind, 'feeder': feeder, 'path': str(path), **extra}
    return {'token': token, 'kind': kind, 'feeder': feeder, 'plan_file': path.name, **extra}


def load_update_plan(ws: Workspace, feeder: str, upload: Path) -> dict:
    from ..loads import LoadTemplateError, build_plan, plan_to_payload, read_workbook

    model = build_model(ws, feeder)
    try:
        sheets = read_workbook(upload)
    except LoadTemplateError as exc:
        raise UserError(str(exc)) from exc
    # Una hoja por alimentador en .xlsx; en .csv puede venir todo en una sola clave.
    sheet = sheets.get(model.name) or sheets.get(feeder)
    if sheet is None and len(sheets) == 1:
        sheet = next(iter(sheets.values()))
    if sheet is None:
        raise UserError(f'El fichero no trae una hoja para {model.name}. '
                        f'Hojas encontradas: {", ".join(sheets) or "ninguna"}.')
    plan = build_plan(model, sheet)
    summary = plan.summary()
    info = {
        'summary': summary,
        'report': plan.report(),
        'row_errors': list(plan.row_errors),
        'unknown': [r.sed_code for r in plan.unknown],
        'updates': [
            {'sed': new.sed_code, 'kw_before': old.kw, 'kvar_before': old.kvar,
             'kw_after': new.kw, 'kvar_after': new.kvar}
            for old, new in plan.updates[:500]
        ],
        'applicable': plan.is_applicable,
    }
    return _store_plan(ws, 'cargas', model.name, plan_to_payload(plan), info)


def create_template(ws: Workspace, feeder: str, fmt: str) -> Path:
    from ..loads import LoadTemplateError
    from ..loads_create import write_create_template

    model = build_model(ws, feeder)
    out = ws.out_dir / 'plantillas' / f'{model.name}_sed_nuevas.{fmt}'
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        return write_create_template([], out, feeder=model.name, node_choices=sorted(model.nodes))
    except LoadTemplateError as exc:
        raise UserError(str(exc)) from exc


def _create_plan_response(ws: Workspace, model, plan) -> dict:
    from ..loads_create import create_plan_to_payload

    info = {
        'summary': plan.summary(),
        'report': plan.report(),
        'row_errors': list(plan.row_errors),
        'already_exists': list(plan.already_exists),
        'create': [
            {'sed': i.load.sed_code, 'installed_kva': i.load.installed_kva,
             'node_id': i.node_id, 'distance_m': i.distance_m,
             'conductor': i.conductor.code, 'binding': i.conductor.binding,
             'voltage_drop_pct': i.conductor.voltage_drop_pct,
             'kw': i.load.kw, 'kvar': i.load.kvar}
            for i in plan.create
        ],
        'applicable': plan.is_applicable,
    }
    payload = create_plan_to_payload(plan, nominal_kv=model.nominal_kv,
                                     source_crs=ws.options['source_crs'])
    return _store_plan(ws, 'sed_nuevas', model.name, payload, info)


def create_plan_from_file(ws: Workspace, feeder: str, upload: Path) -> dict:
    from ..loads import LoadTemplateError
    from ..loads_create import build_create_plan, read_create_workbook

    model = build_model(ws, feeder)
    try:
        sheets = read_create_workbook(upload)
    except LoadTemplateError as exc:
        raise UserError(str(exc)) from exc
    rows = [r for rows, _ in sheets.values() for r in rows]
    errors = [e for _, errs in sheets.values() for e in errs]
    return _create_plan_response(ws, model, build_create_plan(model, rows, errors))


def create_plan_single(ws: Workspace, feeder: str, data: dict) -> dict:
    """Formulario de una SED. **No valida nada aquí**: comparte reglas con la plantilla."""
    from ..loads_create import build_create_plan, single_new_load

    model = build_model(ws, feeder)
    rows, errors = single_new_load(feeder=model.name, **data)
    return _create_plan_response(ws, model, build_create_plan(model, rows, errors))


def check_plan(ws: Workspace, token: str) -> dict:
    plan = ws.plans.get(token)
    if plan is None:
        raise UserError('El plan ya no existe: vuelva a generarlo (cambiaron las entradas '
                        'o se reinició el servidor).')
    if not plan.get('applicable'):
        raise UserError('El plan no es aplicable: tiene filas con error o no cambia nada.')
    if proyecto_pf_de(ws, plan['feeder']) is None:
        raise UserError(
            f"{plan['feeder']} no se ha cargado todavía en DigSILENT desde este espacio. "
            'Pulse «Cargar en DigSILENT» (del alimentador o del DGS unido que lo contiene) '
            'antes de aplicar el plan.')
    _require_pf()
    return plan


def _proyecto_importado(informe: Path) -> str | None:
    """Nombre del proyecto que creó la importación, leído del informe de aceptación."""
    import json

    try:
        datos = json.loads(informe.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return ((datos.get('import') or {}).get('project_name')) or None


def proyecto_pf_de(ws: Workspace, feeder: str) -> str | None:
    """Proyecto de PowerFactory donde está el alimentador: el suyo, o el de un DGS
    unido que lo contiene (el último importado)."""
    if feeder in ws.pf_projects:
        return ws.pf_projects[feeder]
    candidatos = [ws.pf_projects[g] for g, info in ws.groups.items()
                  if g in ws.pf_projects and feeder in (info.get('feeders') or [])]
    return sorted(candidatos)[-1] if candidatos else None


def apply_plan(ws: Workspace, ctx: JobContext, token: str) -> dict:
    plan = check_plan(ws, token)
    pf_dir, interpreter = _require_pf()
    if plan['kind'] == 'cargas':
        script, suffix = _script('apply_sed_loads.py'), 'cargas_aplicadas'
    else:
        script, suffix = _script('create_sed_loads.py'), 'sed_creadas'
    report = ws.out_dir / f"{plan['feeder']}_{suffix}.json"
    proyecto = proyecto_pf_de(ws, plan['feeder'])
    if proyecto is None:
        raise UserError(
            f"{plan['feeder']} no se ha cargado todavía en DigSILENT desde este espacio. "
            'Conviértalo (solo o en un DGS unido) y pulse «Cargar en DigSILENT» antes de '
            'actualizar sus cargas: el plan se aplica sobre ese proyecto.')
    ctx.log(f'Proyecto de PowerFactory: {proyecto}')
    rc = ctx.run_process(
        [str(interpreter), str(script), '--plan', plan['path'], '--project', proyecto,
         '--run-load-flow', '--output-json', str(report)],
        env=pf_subprocess_env(pf_dir), cwd=str(project_root()),
    )
    if rc == 0:
        ctx.log(f'Aplicado sobre el proyecto. Informe: {report.name}')
    elif rc == 3:
        ctx.log('No se pudo conectar con PowerFactory. Ábralo y reintente.')
    else:
        ctx.log(f'El proceso devolvió el código {rc}: puede haber SED no encontradas o ambiguas.')
    return {'returncode': rc, 'report': report.name if report.is_file() else None,
            'feeder': plan['feeder'], 'kind': plan['kind']}


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
                '--importar', '--run-load-flow']
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
