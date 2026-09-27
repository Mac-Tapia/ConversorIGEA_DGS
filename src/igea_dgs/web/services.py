"""Las acciones de la interfaz, sin interfaz.

Cada función recibe el espacio de trabajo y un :class:`JobContext`, escribe en el
Registro y devuelve un resultado serializable. Las rutas de la API solo validan,
encolan y responden.

Dos defectos de la implementación anterior se corrigen aquí:

* «Cargar fichero y actualizar» llamaba a ``loads.read_template``, que no existe; el
  botón fallaba siempre. Aquí se usa ``loads.read_workbook``.
* «Aplicar catálogo corregido» corregía un modelo en memoria que se tiraba a
  continuación: ninguna conversión posterior lo usaba. Aquí el catálogo aplicado queda
  en el espacio y **toda conversión siguiente** lo pasa a ``convert_selection`` como
  ``catalog_corrections``, que es por donde el motor lo espera.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
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

    def __init__(
        self,
        message: str,
        *,
        code: str = 'USER_ERROR',
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


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
        raise UserError(
            'Primero cargue y liste los alimentadores (paso 2).',
            code='WORKSPACE_NOT_LOADED',
            context={'workspace_id': ws.id},
        )


def _read_dataset(ws: Workspace, ctx: JobContext):
    if ws.options.get('input_mode') == 'mdb':
        from ..access import read_access_dataset

        networks = None
        study = ws.input_path('study')
        if study:
            from ..study import study_networks

            networks = study_networks(study)
        return read_access_dataset(
            ws.input_path('mdb'),
            equipment_db=ws.input_path('equipment_mdb') or None,
            networks=networks,
        ), None

    from ..catalog_merge import completar, diagnosticar
    from ..dataset import CymdistDataset

    dataset = CymdistDataset.from_files(
        ws.input_path('red'), ws.input_path('loads'), ws.input_path('equipment'),
    )
    # Catálogo incompleto: se completa si se indicó otro, y en todo caso se dice
    # cuánta red quedaría con la impedancia de DEFAULT. Un catálogo que no
    # corresponde con la red produce un modelo que converge igual, así que si no se
    # avisa aquí no se avisa en ninguna parte.
    extra = ws.input_path('equipment_extra')
    informe = completar(dataset, [extra]) if extra else diagnosticar(dataset)
    report = {
        'initial_coverage': informe.cobertura_inicial,
        'final_coverage': informe.cobertura_final,
        'types_in_network': len(informe.codigos_en_red),
        'added': {Path(k).name: v for k, v in informe.anadidos.items()},
        'unresolved': sorted(informe.sin_resolver),
        'text': informe.texto(),
        'critical': informe.cobertura_final < 0.5,
    }
    if extra or informe.cobertura_final < 1.0:
        ctx.log('--- Catálogo de conductores ---')
        ctx.log(informe.texto())
    return dataset, report


def load_dataset(ws: Workspace, ctx: JobContext) -> dict:
    from ..inventory import build_dataset_inventory, format_inventory_report, write_inventory

    ctx.log('--- Carga e inventario de alimentadores ---')
    mode = ws.options.get('input_mode')
    slots = ('mdb', 'equipment_mdb', 'study') if mode == 'mdb' else (
        'red', 'loads', 'equipment', 'equipment_extra')
    for slot in slots:
        if ws.input_path(slot):
            ctx.log(f'{slot}: {Path(ws.input_path(slot)).name}')

    dataset, catalog_report = _read_dataset(ws, ctx)
    ctx.check_cancel()
    # Reglas de entrada del proyecto: coordenadas por el grafo y catálogo Excel.
    from ..reglas import catalogo_del_proyecto, preparar_dataset

    entrada = preparar_dataset(dataset, catalogo=catalogo_del_proyecto())
    ctx.log(entrada.texto())
    inventory = build_dataset_inventory(dataset)
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    inv_path = write_inventory(inventory, ws.out_dir / 'dataset_inventory.json')
    ctx.log(format_inventory_report(inventory))
    ctx.log(f'Inventario JSON: {inv_path.name}')

    import time

    with ws.lock:
        ws.dataset = dataset
        ws.inventory = inventory
        ws.catalog_report = catalog_report
        ws.loaded_at = time.time()
        ws.plans.clear()
    return {
        'totals': inventory['totals'],
        'conversion': inventory['conversion'],
        'integrity': inventory['integrity'],
        'catalog_report': catalog_report,
    }


def feeder_rows(ws: Workspace) -> list[dict]:
    """Filas de la tabla: inventario + último resultado de conversión de cada una."""
    if not ws.inventory:
        return []
    rows = []
    for row in ws.inventory['feeders']:
        conv = ws.conversions.get(row['network_id']) or {}
        dgs = conv.get('dgs')
        rows.append({
            **row,
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


def convert(ws: Workspace, ctx: JobContext, feeders: list[str] | None, all_feeders: bool) -> dict:
    from ..batch import convert_selection, load_aliases

    opts = ws.options
    aliases = load_aliases(ws.input_path('aliases') or None)
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

    total = len(ws.inventory['feeders']) if all_feeders and ws.inventory else len(feeders or [])
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


def dgs_jobs(
    ws: Workspace,
    feeders: list[str],
) -> tuple[list[tuple[str, Path, Path | None, Path]], list[str]]:
    jobs, missing = [], []
    for feeder in feeders:
        dgs = ws.out_dir / f'{feeder}.dgs'
        if not dgs.is_file():
            missing.append(f'{feeder}: falta {feeder}.dgs')
            continue
        geo = ws.out_dir / f'{feeder}_geography.json'
        metadata = ws.out_dir / f'{feeder}_feeder_metadata.json'
        if not metadata.is_file():
            missing.append(
                f'{feeder}: falta {metadata.name}; reconvierta el DGS para generar la metadata'
            )
            continue
        jobs.append((feeder, dgs, geo if geo.is_file() else None, metadata))
    return jobs, missing


def check_powerfactory_flow(ws: Workspace, feeders: list[str]) -> None:
    if not feeders:
        raise UserError('Seleccione al menos un alimentador ya convertido.')
    jobs, missing = dgs_jobs(ws, feeders)
    if not jobs:
        raise UserError('No hay una conversión lista para PowerFactory. ' + '; '.join(missing[:12]))
    _script('powerfactory_acceptance.py')
    _require_pf()


def powerfactory_flow(ws: Workspace, ctx: JobContext, feeders: list[str]) -> dict:
    pf_dir, interpreter = _require_pf()
    script = _script('powerfactory_acceptance.py')
    jobs, missing = dgs_jobs(ws, feeders)
    ctx.log('--- Inicio DigSILENT: import + escenario + flujo ---')
    ctx.log(f'Intérprete para la API: {interpreter}  [{powerfactory_status()["interpreter_reason"]}]')
    for reason in missing:
        ctx.log(f'  (se omite) {reason}')
    env = pf_subprocess_env(pf_dir)
    lines, ok_n, fail_n = [], 0, 0
    feeder_acceptance: dict[str, dict[str, Any]] = {}
    for index, (feeder, dgs, geo, metadata) in enumerate(jobs, start=1):
        ctx.check_cancel()
        ctx.progress(index - 1, len(jobs), feeder)
        ctx.log(f'[{index}/{len(jobs)}] Import + escenario + flujo {feeder}…')
        # Importar, activar escenario y correr el flujo: segundos. Sin --run-studies
        # (el cortocircuito de una red unida tardaba más de 20 min y 7 GB de RAM en
        # cada clic) y sin --fix-until-converge, que ante un flujo que no converge
        # modifica el modelo (escala cargas) sin pedirlo. Los estudios se lanzan aparte.
        cmd = [str(interpreter), str(script), '--import-dgs', str(dgs),
               '--feeder-metadata', str(metadata),
               '--ensure-scenario', '--run-load-flow']
        if geo is not None:
            cmd += ['--manifest', str(geo)]
        cmd += ['--output-json', str(ws.out_dir / f'{feeder}_powerfactory_acceptance.json'),
                '--output-txt', str(ws.out_dir / f'{feeder}_powerfactory_acceptance.txt')]
        rc = ctx.run_process(cmd, env=env, cwd=str(project_root()))
        acceptance_path = ws.out_dir / f'{feeder}_powerfactory_acceptance.json'
        proyecto = _proyecto_importado(acceptance_path)
        summary = _resumen_alimentador(acceptance_path)
        if summary is not None:
            feeder_acceptance[feeder] = summary
            ws.record_feeder_acceptance(
                feeder,
                metadata_file=metadata.name,
                summary=summary,
            )
            ctx.log(
                '  Alimentador: asignado '
                f'{summary["loads"]["assigned"]}/{summary["loads"]["expected"]} cargas, '
                f'{summary["sources"]["assigned"]}/{summary["sources"]["expected"]} fuentes'
            )
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
            'missing_dgs': missing, 'lines': lines,
            'feeder_acceptance': feeder_acceptance}


# ---------------------------------------------------------------------------
# Modelos de un alimentador (cargas, SED nuevas, catálogo)
# ---------------------------------------------------------------------------


def reglas_de(ws: Workspace):
    """Reglas del proyecto con lienzo adaptativo o la hoja explícita elegida."""
    from dataclasses import replace

    from ..reglas import REGLAS_PROYECTO, normalizar_hoja

    return replace(REGLAS_PROYECTO, hoja=normalizar_hoja(ws.options.get('hoja')))


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


def load_inventory_rows(
    ws: Workspace,
    feeders: list[str] | None = None,
    *,
    grid_name: str | None = None,
):
    """Devuelve el inventario vigente sin reconstruir un alimentador dos veces."""
    require_loaded(ws)
    from ..load_inventory import rows_from_models

    requested = feeders or [feeder_short_name(net) for net in ws.dataset.feeder_ids()]
    networks = tuple(ws.dataset.resolve_feeder(feeder) for feeder in requested)
    names = tuple(feeder_short_name(network) for network in networks)
    effective_grid = grid_name or (names[0] if len(names) == 1 else None)
    catalog_signature: tuple[str, int] | None = None
    if ws.catalog_file:
        catalog_path = Path(ws.catalog_file)
        if catalog_path.is_file():
            catalog_signature = (str(catalog_path), catalog_path.stat().st_mtime_ns)
    key = (id(ws.dataset), networks, effective_grid, catalog_signature)
    with ws.lock:
        cached = ws.load_inventory_cache.get(key)
    if cached is not None:
        return cached

    models = [build_model(ws, network, geography=False) for network in networks]
    rows = rows_from_models(models, grid_name=effective_grid)
    with ws.lock:
        ws.load_inventory_cache[key] = rows
    return rows


def electrical_inventory(
    ws: Workspace,
    *,
    feeder: str | None,
    status: str | None,
    search: str | None,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    from ..load_inventory import query_load_inventory

    rows = load_inventory_rows(ws, [feeder] if feeder else None)
    page = query_load_inventory(
        rows, feeder=feeder, status=status, search=search,
        offset=offset, limit=limit,
    )
    return {
        'total': page.total,
        'offset': page.offset,
        'limit': page.limit,
        'filters': {'feeder': feeder, 'status': status, 'search': search},
        'rows': [row.public() for row in page.rows],
    }


def _all_filtered_inventory_rows(
    ws: Workspace,
    *,
    feeder: str | None,
    status: str | None,
    search: str | None,
) -> list[dict[str, Any]]:
    from ..load_inventory import query_load_inventory

    rows = load_inventory_rows(ws, [feeder] if feeder else None)
    result: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = query_load_inventory(
            rows, feeder=feeder, status=status, search=search,
            offset=offset, limit=500,
        )
        result.extend(row.public() for row in page.rows)
        offset += len(page.rows)
        if offset >= page.total or not page.rows:
            return result


def export_electrical_inventory(
    ws: Workspace,
    *,
    fmt: str,
    feeder: str | None,
    status: str | None,
    search: str | None,
) -> Path:
    if fmt not in {'csv', 'json'}:
        raise UserError('El inventario solo se exporta como csv o json.')
    filters = {'feeder': feeder, 'status': status, 'search': search}
    rows = _all_filtered_inventory_rows(ws, **filters)
    signature = hashlib.sha256(
        json.dumps(filters, sort_keys=True, ensure_ascii=False).encode('utf-8')
    ).hexdigest()[:12]
    folder = ws.out_dir / 'inventario'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'cargas_{signature}.{fmt}'
    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8-sig' if fmt == 'csv' else 'utf-8',
        newline='', suffix=f'.{fmt}.tmp', dir=folder, delete=False,
    ) as stream:
        temporary = Path(stream.name)
        if fmt == 'json':
            json.dump({'filters': filters, 'rows': rows}, stream, ensure_ascii=False, indent=2)
        else:
            fields = list(rows[0]) if rows else [
                'name', 'class_name', 'grid', 'alimentador', 'network_id', 'sed',
                'terminal_substation', 'terminal', 'status', 'diagnostic',
            ]
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
            writer.writeheader()
            for row in rows:
                serializable = dict(row)
                serializable['provenance'] = json.dumps(
                    row.get('provenance') or {}, ensure_ascii=False, sort_keys=True,
                )
                writer.writerow(serializable)
    temporary.replace(target)
    return target


# ---------------------------------------------------------------------------
# Varios alimentadores en un solo DGS
# ---------------------------------------------------------------------------


def group_selection(ws: Workspace, feeders: list[str], all_feeders: bool) -> list[str]:
    require_loaded(ws)
    if all_feeders:
        feeders = [r['feeder'] for r in ws.inventory['feeders'] if r.get('convertible')]
    if len(feeders) < 2:
        raise UserError('Para unir en un solo DGS seleccione al menos dos alimentadores.')
    return list(feeders)


def group_name(nombre: str, feeders: list[str]) -> str:
    base = (nombre or '').strip() or '_'.join(feeders[:4]) + ('_ETC' if len(feeders) > 4 else '')
    limpio = ''.join(c if c.isalnum() or c in '-_' else '_' for c in base)[:60]
    return limpio or 'GRUPO'


def convert_group(ws: Workspace, ctx: JobContext, feeders: list[str], nombre: str) -> dict:
    from ..batch import convert_group as convertir_grupo
    from ..batch import load_aliases
    from ..reglas import catalogo_del_proyecto

    opts = ws.options
    ctx.log(f'--- Red unida {nombre}: {", ".join(feeders)} ---')
    from ..batch import resolve_workers

    workers = int(opts.get('workers') or 0)
    n_workers = resolve_workers(workers, len(feeders))
    ctx.log(f'Preparación con {n_workers} proceso(s); exportación eléctrica completa habilitada.')

    def on_progress(network_id: str, index: int, total: int) -> None:
        name = feeder_short_name(network_id)
        ctx.progress(index, total, name)
        ctx.log(f'[{index}/{total}] {name} listo' if n_workers > 1 else f'[{index}/{total}] {name}…')

    man = convertir_grupo(
        ws.dataset, feeders, ws.out_dir, name=nombre,
        aliases=load_aliases(ws.input_path('aliases') or None),
        strict=bool(opts['strict']),
        source_crs=opts['source_crs'] or 'EPSG:32718',
        target_crs=opts['target_crs'] or 'EPSG:4326',
        catalog_corrections=ws.catalog_corrections() or None,
        reglas=reglas_de(ws), catalogo=catalogo_del_proyecto(),
        on_progress=on_progress, cancel=ctx.cancel, workers=workers,
        export_electrical=True,
    )
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
        formato = (f"hoja {hoja.get('formato')} {hoja.get('orientacion')}"
                   if hoja else 'lienzo adaptativo 2,08 u/m')
        ctx.log(f"OK {nombre}.dgs — {man['counts'].get('dgs_lines', '?')} líneas; "
                f"{formato}; "
                f"completitud: {'OK' if not man['completitud']['fallos'] else man['completitud']['fallos']}")
    else:
        ctx.log(f"FAIL {nombre}: {man.get('error')}")
    with ws.lock:
        ws.groups[nombre] = {k: man.get(k) for k in (
            'name', 'feeders', 'status', 'error', 'dgs', 'feeder_metadata',
            'name_feeder_mapping', 'workers', 'electrical_tables',
            'electrical_export_manifest', 'dgs_tables',
            'hoja', 'ties', 'completitud')}
        ws.save()
    return {'group': nombre, 'status': man['status'], 'error': man.get('error'),
            'dgs': f'{nombre}.dgs' if man['status'] == 'ok' else None,
            'feeders': feeders, 'completitud': man.get('completitud'),
            'hoja': man.get('hoja'), 'manifest': f'{nombre}_manifest.json',
            'workers': man.get('workers', 1),
            'electrical_tables': man.get('electrical_tables'),
            'electrical_export_manifest': man.get('electrical_export_manifest'),
            'dgs_tables': man.get('dgs_tables')}


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


def _resumen_alimentador(informe: Path) -> dict[str, Any] | None:
    """Extrae el resultado serializable de ``p:alimentador`` del informe PF."""

    try:
        datos = json.loads(informe.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    assignment = ((datos.get('feeder_metadata') or {}).get('assignment') or {})
    if not assignment:
        return None
    counts = assignment.get('counts_by_class') or {}
    loads = int(counts.get('ElmLod') or 0)
    sources = int(counts.get('ElmXnet') or 0) + int(counts.get('ElmSym') or 0)
    ok = bool(assignment.get('ok'))
    return {
        'ok': ok,
        'loads': {'assigned': loads if ok else 0, 'expected': loads},
        'sources': {'assigned': sources if ok else 0, 'expected': sources},
        'counts_by_feeder': dict(assignment.get('counts_by_feeder') or {}),
        'unresolved': len(assignment.get('unresolved') or []),
        'ambiguous': len(assignment.get('ambiguous') or []),
    }


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
