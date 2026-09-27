from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from pathlib import Path

from .dataset import CymdistDataset
from .dgs import write_dgs
from .export_tables import write_dgs_tsv, write_dgs_xlsx
from .feeder_metadata import write_feeder_metadata
from .geography import (
    assert_metre_source_crs,
    build_geography,
    validate_geography,
    write_geography_manifest,
    write_geography_validation,
)
from .model import ModelBuildError, build_feeder_model
from .naming import feeder_short_name, sort_key_feeder
from .preview import write_preview_geojson, write_preview_html
from .reglas import REGLAS_PROYECTO, Reglas, aplicar_reglas, auditar_completitud, preparar_dataset
from .validate import parse_dgs, validate_dgs, write_validation_reports

ProgressCallback = Callable[[str, int, int], None]

STAGE_PREFIX = '.igea-stage-'


class BatchCancelled(Exception):
    """El operador canceló el lote; los alimentadores ya publicados se conservan."""


def _clear_stage(stage: Path) -> None:
    shutil.rmtree(stage, ignore_errors=True)


def _publish(stage: Path, out_dir: Path, *, only: set[str] | None = None) -> list[Path]:
    """Mueve los artefactos ya completos del área de preparación a su sitio final.

    La conversión escribe en ``stage`` y solo al final, con todo verificado, cada
    artefacto se mueve con ``os.replace`` (atómico dentro del mismo volumen). Así un
    corte de luz, un cierre de ventana o una cancelación no pueden dejar un ``.dgs``
    truncado indistinguible de uno válido, y el resultado bueno anterior sigue en pie
    hasta el instante del reemplazo.
    """
    published: list[Path] = []
    for item in sorted(stage.iterdir()):
        if only is not None and item.name not in only:
            continue
        final = out_dir / item.name
        if item.is_dir():
            # os.replace no sustituye un directorio existente: hay que vaciarlo antes.
            shutil.rmtree(final, ignore_errors=True)
        os.replace(item, final)
        published.append(final)
    return published


def load_aliases(path: Path | str | None) -> dict[str, str]:
    if path is None:
        return {}
    alias_path = Path(path)
    if not alias_path.is_file():
        raise FileNotFoundError(f'Alias file not found: {alias_path}')
    data = json.loads(alias_path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError('Alias file must be a JSON object of string -> string mappings')
    return {
        k.strip(): v.strip()
        for k, v in data.items()
        if k.strip() and v.strip() and not k.strip().startswith('_')
    }


def _selection(dataset: CymdistDataset, selectors: Sequence[str] | None, all_feeders: bool) -> list[str]:
    if all_feeders:
        networks = sorted(dataset.feeder_ids(), key=sort_key_feeder)
    elif not selectors:
        raise ValueError('At least one feeder selector is required unless all_feeders=True')
    else:
        networks = []
        seen: set[str] = set()
        for selector in selectors:
            network = dataset.resolve_feeder(selector)
            if network not in seen:
                seen.add(network)
                networks.append(network)

    return networks


def output_names(networks: Sequence[str]) -> dict[str, str]:
    """NetworkID → nombre de fichero, único dentro de la selección.

    Dos ``NetworkID`` distintos pueden compartir nombre corto (lotes multiempresa:
    ``NET_2030_150_NA999`` y ``NET_9000_77_NA999`` → ``NA999``). Antes esa colisión
    lanzaba un error **antes** del bucle y tumbaba el lote entero: no se convertía
    ni un alimentador, en contra de la regla de independencia por alimentador.

    Ahora solo los nombres que colisionan llevan un sufijo determinista derivado del
    ``NetworkID`` completo, de modo que los demás conservan su nombre habitual y el
    resultado sigue siendo reproducible entre ejecuciones.
    """
    counts = Counter(feeder_short_name(n) for n in networks)
    names: dict[str, str] = {}
    for network_id in networks:
        short = feeder_short_name(network_id)
        if counts[short] == 1:
            names[network_id] = short
        else:
            digest = hashlib.sha256(network_id.encode('utf-8')).hexdigest()[:8]
            names[network_id] = f'{short}__{digest}'
    return names



@dataclass(frozen=True)
class _FeederOptions:
    """Lo que necesita un alimentador para convertirse, igual para todo el lote."""

    aliases: Mapping[str, str]
    strict: bool
    schema_profile: str
    include_geography: bool
    source_crs: str
    target_crs: str
    export_xlsx: bool
    export_tsv: bool
    write_preview: bool
    preview_backend: str
    catalog_corrections: Mapping[str, Any] | None
    reglas: Reglas = REGLAS_PROYECTO
    trafos: Mapping[float, Mapping[str, float]] | None = None


def _convert_feeder(
    dataset: CymdistDataset, network_id: str, feeder: str, out_dir: Path, opts: _FeederOptions,
) -> tuple[dict, list[str]]:
    """Convierte un alimentador y devuelve (entrada del manifiesto, cambios de catálogo).

    Solo lee el dataset y escribe en su propia área de preparación, así que se puede
    ejecutar en serie o en un proceso aparte sin que un alimentador vea a otro.
    """
    changes: list[str] = []
    # Todo se escribe primero aquí; solo se publica cuando el alimentador está
    # completo y validado (ver _publish).
    stage = out_dir / f'{STAGE_PREFIX}{feeder}'
    _clear_stage(stage)
    stage.mkdir(parents=True, exist_ok=True)
    dgs_path = stage / f'{feeder}.dgs'
    json_path = stage / f'{feeder}_validation.json'
    txt_path = stage / f'{feeder}_validation.txt'
    geo_path = stage / f'{feeder}_geography.json'
    geo_validation_path = stage / f'{feeder}_geography_validation.txt'
    xlsx_path = stage / f'{feeder}.xlsx'
    tsv_dir = stage / f'{feeder}_dgs_tables'
    preview_html_path = stage / f'{feeder}_preview.html'
    preview_geojson_path = stage / f'{feeder}_preview.geojson'
    feeder_metadata_path = stage / f'{feeder}_feeder_metadata.json'
    # Un FEEDER=/SOURCE sin filas SECTION ya no se omite: se convierte dibujando
    # la barra de cabecera, que es lo único que el export contiene. El manifiesto
    # lo marca como 'source_only' para que no se confunda con un alimentador
    # modelado (ver model.build_feeder_model).
    source_only = not dataset.feeders.get(network_id)
    try:
        model = build_feeder_model(
            dataset, network_id, aliases=opts.aliases, strict=opts.strict,
            include_geography=opts.include_geography,
        )
        # Reglas del proyecto (igea_dgs.reglas): catálogo de ficha, puentes, trafomix,
        # SED sobrecargadas y hoja A0. El mismo camino en serie y en paralelo.
        informe_reglas = aplicar_reglas(model, opts.reglas, correcciones=opts.catalog_corrections)
        changes = list(informe_reglas.get('catalogo', []))
        geography = None
        geography_report = None
        if opts.include_geography:
            geography = build_geography(dataset, model, source_crs=opts.source_crs, target_crs=opts.target_crs)
            geography_report = validate_geography(model, geography)
            if geography_report['errors_total']:
                raise ModelBuildError(f'{network_id}: geographic validation failed: {geography_report["errors"]}')
            write_geography_manifest(geography, geo_path, model=model)
            write_geography_validation(geography_report, geo_validation_path)

        if opts.write_preview:
            assert geography is not None
            write_preview_html(
                model, geography, preview_html_path, backend=opts.preview_backend,
            )
            write_preview_geojson(model, geography, preview_geojson_path)

        manifiesto_dgs = write_dgs(model, dgs_path, schema_profile=opts.schema_profile,
                                   geography=geography, trafos=opts.trafos)
        write_feeder_metadata(
            manifiesto_dgs.feeder_assignments, dgs_path, feeder_metadata_path)

        if opts.export_xlsx:
            write_dgs_xlsx(dgs_path, xlsx_path)
        if opts.export_tsv:
            write_dgs_tsv(dgs_path, tsv_dir)

        report = validate_dgs(model, dgs_path, schema_profile=opts.schema_profile, geography=geography)
        write_validation_reports(report, json_path, txt_path)
        # Completitud contra la entrada: un alimentador que pierde un tramo, una carga
        # o una maniobra no es «ok», aunque el DGS sea válido.
        completitud = auditar_completitud(
            dataset, [network_id], model, parse_dgs(dgs_path), [informe_reglas])
        ok = report['errors_total'] == 0 and not completitud['fallos']
        # Publicación atómica. Si la validación falló, solo se publican los
        # informes (el diagnóstico); el .dgs se descarta y el último resultado
        # bueno que hubiera en la carpeta permanece intacto.
        if ok:
            _publish(stage, out_dir)
        else:
            _publish(stage, out_dir, only={json_path.name, txt_path.name})
        _clear_stage(stage)
        dgs_path = out_dir / dgs_path.name
        json_path = out_dir / json_path.name
        txt_path = out_dir / txt_path.name
        geo_path = out_dir / geo_path.name
        geo_validation_path = out_dir / geo_validation_path.name
        xlsx_path = out_dir / xlsx_path.name
        tsv_dir = out_dir / tsv_dir.name
        preview_html_path = out_dir / preview_html_path.name
        preview_geojson_path = out_dir / preview_geojson_path.name
        feeder_metadata_path = out_dir / feeder_metadata_path.name

        item = {
            'feeder': feeder,
            'short_name': feeder_short_name(network_id),
            'network_id': network_id,
            'status': 'ok' if ok else 'failed',
            'dgs': str(dgs_path) if ok else None,
            'dgs_published': ok,
            'feeder_metadata': str(feeder_metadata_path) if ok else None,
            'validation_json': str(json_path),
            'validation_txt': str(txt_path),
            'errors_total': report['errors_total'],
            'aliases': dict(model.line_type_aliases),
            'unresolved_line_types': sorted(model.unresolved_line_types),
            'counts': report['counts'],
            'topology': 'source_only' if source_only else 'full',
            'islands': model.islands or {},
            'warnings': list(model.warnings),
            'source_crs': opts.source_crs if opts.include_geography else None,
            'target_crs': opts.target_crs if opts.include_geography else None,
            'reglas': informe_reglas,
            'completitud': completitud,
        }
        hoja = manifiesto_dgs.diagram_sheet
        if hoja is not None and hoja.formato:
            item['hoja'] = {'formato': hoja.formato, 'orientacion': hoja.orientacion,
                            'escala_1_a': round(1000.0 / hoja.scale),
                            'cuadricula_mm': manifiesto_dgs.diagram_grid_mm}
        if opts.include_geography:
            item['geography'] = str(geo_path)
            item['geography_validation'] = str(geo_validation_path)
            item['geography_coverage'] = {
                'nodes_pct': geography_report['node_coverage_pct'],
                'lines_pct': geography_report['line_coverage_pct'],
                'intermediate_points': geography_report['intermediate_points'],
            }
        if opts.write_preview:
            item['preview_html'] = str(preview_html_path)
            item['preview_geojson'] = str(preview_geojson_path)
        if opts.export_xlsx:
            item['xlsx'] = str(xlsx_path)
        if opts.export_tsv:
            item['tsv_dir'] = str(tsv_dir)
        if not ok:
            item['error'] = '; '.join(
                report['schema_errors'] + report['structural_errors'] + report['connection_errors'] +
                report.get('geographic_errors', []) + report.get('graphic_errors', [])
                + [f'completitud: {f}' for f in completitud['fallos']]
            )
    except (ModelBuildError, KeyError, ValueError, OSError, ImportError) as exc:
        # Nada se publicó: basta con descartar el área de preparación. Los
        # artefactos buenos de una ejecución anterior siguen intactos.
        _clear_stage(stage)
        item = {
            'feeder': feeder,
            'short_name': feeder_short_name(network_id),
            'network_id': network_id,
            'status': 'failed',
            'error': str(exc),
            'islands': getattr(exc, 'islands', {}),
            'dgs_published': False,
            'topology': 'source_only' if source_only else 'full',
            'aliases': {},
            'unresolved_line_types': sorted(getattr(exc, 'types', [])),
        }
    finally:
        _clear_stage(stage)
    return item, changes


# El dataset se envía una vez a cada proceso, no una vez por alimentador: en una red
# real ocupa cientos de MB y serializarlo 200 veces costaría más que convertir.
_WORKER_STATE: tuple[CymdistDataset, _FeederOptions] | None = None


def _init_worker(dataset: CymdistDataset, opts: _FeederOptions) -> None:
    global _WORKER_STATE
    _WORKER_STATE = (dataset, opts)


def _convert_in_worker(network_id: str, feeder: str, out_dir: Path) -> tuple[dict, list[str]]:
    assert _WORKER_STATE is not None, 'proceso sin inicializar'
    dataset, opts = _WORKER_STATE
    return _convert_feeder(dataset, network_id, feeder, out_dir, opts)


#: Tope del modo automático. Medido con el export de referencia (96 alimentadores,
#: 32 núcleos): 1 proceso 13,7 s, 4 procesos 4,8 s, 8 procesos 8,0 s, 16 procesos
#: 11,1 s. Pasado este punto cuesta más arrancar procesos y copiarles el dataset, y
#: pelean por el disco, que lo que se gana convirtiendo a la vez.
AUTO_WORKERS_MAX = 4


def resolve_workers(workers: int | None, total: int) -> int:
    """``None``/``1`` → en serie; ``N`` → hasta N; ``0`` o negativo → automático.

    Nunca más procesos que alimentadores: sobrarían.
    """
    if workers is None:
        return 1
    if workers <= 0:
        workers = min(AUTO_WORKERS_MAX, os.cpu_count() or 1)
    return max(1, min(workers, total))



def _convert_parallel(
    dataset: CymdistDataset,
    networks: Sequence[str],
    names: Mapping[str, str],
    out_dir: Path,
    opts: _FeederOptions,
    n_workers: int,
    results: dict[str, tuple[dict, list[str]]],
    *,
    on_progress: ProgressCallback | None,
    cancel: threading.Event | None,
) -> bool:
    """Reparte los alimentadores entre procesos. Devuelve ``True`` si se canceló.

    Al cancelar no se empieza ningún alimentador más; los que ya están en marcha
    terminan y se publican enteros, igual que en serie termina el que está en curso.
    Nada queda a medias: cada uno publica de forma atómica desde su propia área.
    """
    total = len(networks)
    done = 0
    with ProcessPoolExecutor(
        max_workers=n_workers, initializer=_init_worker, initargs=(dataset, opts),
    ) as pool:
        pending = {
            pool.submit(_convert_in_worker, network_id, names[network_id], out_dir): network_id
            for network_id in networks
        }
        cancelled = False
        while pending:
            finished, _ = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
            for future in finished:
                network_id = pending.pop(future)
                if future.cancelled():
                    continue
                results[network_id] = future.result()
                done += 1
                if on_progress is not None:
                    on_progress(network_id, done, total)
            if not cancelled and cancel is not None and cancel.is_set():
                cancelled = True
                for future in pending:
                    future.cancel()
        return cancelled

def convert_selection(
    dataset: CymdistDataset,
    selectors: Sequence[str] | None,
    out_dir: Path | str,
    *,
    all_feeders: bool = False,
    aliases: Mapping[str, str] | None = None,
    strict: bool = True,
    schema_profile: str = 'pf21_dgs_1_8_4',
    include_geography: bool = True,
    source_crs: str = 'EPSG:32718',
    target_crs: str = 'EPSG:4326',
    export_xlsx: bool = False,
    export_tsv: bool = False,
    write_preview: bool = False,
    preview_backend: str = 'auto',
    on_progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
    catalog_corrections: Mapping[str, Any] | None = None,
    workers: int | None = None,
    reglas: Reglas = REGLAS_PROYECTO,
    catalogo: Path | str | None = None,
) -> dict:
    """Convierte la selección y devuelve el manifiesto del lote.

    ``reglas`` son las del proyecto (:mod:`igea_dgs.reglas`) salvo que se pida otra
    cosa. ``catalogo`` es el Excel de parámetros: completa los códigos de conductor que
    falten, da los transformadores de SED y, si no se pasan ``catalog_corrections``,
    sus filas de ficha corrigen los conductores. Las entradas (web, CLI, GUI) pasan el
    del proyecto.

    ``cancel`` se comprueba **entre** alimentadores: no se empieza ninguno más, el que
    está en marcha termina y se publica entero (en paralelo, todos los que estén en
    marcha), y el manifiesto se escribe igualmente con ``status='cancelled'``. Nada
    queda a medias: cada alimentador se publica de forma atómica o no se publica.

    ``catalog_corrections`` son los valores de ficha de :mod:`igea_dgs.catalog`. Se
    aplican **entre** construir el modelo y escribir el DGS, que es el único punto
    donde tienen sentido: el TXT ya dijo qué elemento es cada tramo y el DGS todavía
    no se ha escrito. Van aquí, y no en un guion aparte, para que la corrección
    ocurra en el mismo camino que la conversión normal —con su georreferenciación,
    su validación y su publicación atómica— en lugar de en una copia paralela que
    tarde o temprano se desviaría.

    ``workers`` convierte varios alimentadores a la vez, cada uno en su proceso:
    ``None`` o ``1`` en serie (lo de siempre), ``N`` hasta N procesos, ``0`` automático
    (ver :data:`AUTO_WORKERS_MAX`). Los alimentadores son independientes por diseño, así que el resultado es
    el mismo byte a byte; solo cambia cuándo llega ``on_progress``: en serie antes de
    empezar cada alimentador, en paralelo al terminar cada uno. Cada proceso guarda
    una copia del dataset en memoria.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    aliases = dict(aliases or {})
    if write_preview and not include_geography:
        raise ValueError('write_preview=True requiere include_geography=True')
    if include_geography:
        # Fail before writing anything: a non-metre source CRS scales every line
        # length silently and the validator cannot detect it (C-01).
        assert_metre_source_crs(source_crs)
    # Avisos de ingestión: un CARGA vacío convertía sin una sola carga y el lote
    # salía «ok». Ahora queda registrado en el manifiesto y visible para la GUI.
    input_warnings: list[str] = []
    # Qué características cambió el catálogo, por alimentador. Va al manifiesto: un
    # DGS con impedancias distintas a las del TXT debe decir de dónde salieron.
    catalog_changes: dict[str, list[str]] = {}
    if not dataset.customer_loads:
        input_warnings.append(
            f'{Path(dataset.loads_path).name}: 0 filas en [CUSTOMER LOADS]. Los DGS '
            'saldrán sin cargas ni SED, y el flujo de potencia convergerá trivialmente. '
            'Verifique que es el CARGA correcto y que está completo.'
        )
    elif not dataset.load_placements:
        input_warnings.append(
            f'{Path(dataset.loads_path).name}: hay CUSTOMER LOADS pero 0 filas en '
            '[LOADS]. Sin ubicación no se puede conectar ninguna carga.'
        )
    if not dataset.switch_settings and not dataset.sectionalizer_settings:
        input_warnings.append(
            f'{Path(dataset.red_path).name}: 0 maniobras (SWITCH/SECTIONALIZER). '
            'Los DGS no tendrán StaSwitch.'
        )

    # Reglas de entrada, una vez para todo el lote y antes de repartir el dataset entre
    # procesos: coordenadas por el grafo y catálogo del proyecto.
    informe_entrada = preparar_dataset(dataset, catalogo=catalogo)
    trafos = None
    if catalogo:
        from .catalog import leer_catalogo, leer_trafos

        trafos = leer_trafos(catalogo)
        if catalog_corrections is None:
            catalog_corrections = leer_catalogo(catalogo)

    networks = _selection(dataset, selectors, all_feeders)
    names = output_names(networks)
    disambiguated = {
        network_id: name for network_id, name in names.items()
        if name != feeder_short_name(network_id)
    }

    total = len(networks)
    opts = _FeederOptions(
        aliases=aliases, strict=strict, schema_profile=schema_profile,
        include_geography=include_geography, source_crs=source_crs, target_crs=target_crs,
        export_xlsx=export_xlsx, export_tsv=export_tsv, write_preview=write_preview,
        preview_backend=preview_backend,
        catalog_corrections=dict(catalog_corrections) if catalog_corrections else None,
        reglas=reglas, trafos=trafos,
    )
    n_workers = resolve_workers(workers, total)
    results: dict[str, tuple[dict, list[str]]] = {}

    cancelled = False
    try:
        if n_workers == 1:
            for index, network_id in enumerate(networks, start=1):
                if cancel is not None and cancel.is_set():
                    cancelled = True
                    break
                if on_progress is not None:
                    on_progress(network_id, index, total)
                results[network_id] = _convert_feeder(
                    dataset, network_id, names[network_id], out_dir, opts)
        else:
            cancelled = _convert_parallel(
                dataset, networks, names, out_dir, opts, n_workers, results,
                on_progress=on_progress, cancel=cancel,
            )

    finally:
        # El manifiesto se escribe pase lo que pase: un lote sin manifiesto
        # es un lote sin traza. Incluye lo procesado hasta el momento.
        # Siempre en el orden de la selección, acaben los procesos en el orden que
        # acaben: el manifiesto también es salida y debe ser determinista.
        items = [results[n][0] for n in networks if n in results]
        for network_id in networks:
            if network_id in results and results[network_id][1]:
                catalog_changes[names[network_id]] = results[network_id][1]
        ok_count = sum(item['status'] == 'ok' for item in items)
        skipped_count = sum(item['status'] == 'skipped' for item in items)
        failed_count = sum(item['status'] == 'failed' for item in items)
        manifest = {
            'schema_profile': schema_profile,
            'strict': strict,
            'include_geography': include_geography,
            'export_xlsx': export_xlsx,
            'export_tsv': export_tsv,
            'write_preview': write_preview,
            'source_crs': source_crs if include_geography else None,
            'target_crs': target_crs if include_geography else None,
            'runtime_reference_dependency': False,
            'disambiguated_output_names': disambiguated,
            # Un DGS con impedancias distintas a las del TXT tiene que decir de dónde
            # salieron, o dentro de seis meses nadie sabrá por qué el resultado del
            # estudio cambió.
            'catalog_applied': bool(catalog_corrections),
            'catalog_changes': catalog_changes,
            # Resumen de lo leído: hace visible de un vistazo un CARGA vacío o un
            # export sin maniobras, que antes producían un lote «ok» sin esos
            # elementos y sin ningún aviso.
            'inputs': {
                'red': str(dataset.red_path),
                'loads': str(dataset.loads_path),
                'equipment': str(dataset.equipment_path),
                'feeders_read': len(dataset.feeders),
                'nodes_read': len(dataset.nodes),
                'sections_read': len(dataset.sections),
                'customer_loads_read': len(dataset.customer_loads),
                'load_placements_read': len(dataset.load_placements),
                'switches_read': len(dataset.switch_settings),
                'sectionalizers_read': len(dataset.sectionalizer_settings),
                'intermediate_nodes_read': len(dataset.intermediate_nodes),
            },
            'input_warnings': input_warnings,
            'reglas': reglas.__dict__,
            'entrada': informe_entrada.texto(),
            'catalogo': str(catalogo) if catalogo else None,
            'workers': n_workers,
            'summary': {
                'status': 'cancelled' if cancelled else 'completed',
                'selected': total,
                'requested': len(items),
                'ok': ok_count,
                'skipped': skipped_count,
                'failed': failed_count,
                'not_processed': total - len(items),
            },
            'feeders': items,
        }
        (out_dir / 'batch_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return manifest


# ---------------------------------------------------------------------------
# Varios alimentadores en UN solo DGS
# ---------------------------------------------------------------------------

def convert_group(
    dataset: CymdistDataset,
    selectors: Sequence[str],
    out_dir: Path | str,
    *,
    name: str,
    aliases: Mapping[str, str] | None = None,
    strict: bool = True,
    schema_profile: str = 'pf21_dgs_1_8_4',
    source_crs: str = 'EPSG:32718',
    target_crs: str = 'EPSG:4326',
    catalog_corrections: Mapping[str, Any] | None = None,
    reglas: Reglas = REGLAS_PROYECTO,
    catalogo: Path | str | None = None,
    on_progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> dict:
    """Une los alimentadores elegidos en una sola red y escribe **un** DGS.

    Cada alimentador conserva su tensión y su fuente; los nodos que comparten quedan
    unidos por un interruptor normalmente abierto (:mod:`igea_dgs.combine`). Se aplican
    las mismas reglas que a un alimentador suelto, se valida, se audita la completitud
    del grupo contra la entrada y se publica de forma atómica. Escribe
    ``<name>_manifest.json`` pase lo que pase.
    """
    from .combine import combine_models

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    assert_metre_source_crs(source_crs)
    informe_entrada = preparar_dataset(dataset, catalogo=catalogo)
    trafos = None
    if catalogo:
        from .catalog import leer_catalogo, leer_trafos

        trafos = leer_trafos(catalogo)
        if catalog_corrections is None:
            catalog_corrections = leer_catalogo(catalogo)

    nombre = ''.join(c if c.isalnum() or c in '-_' else '_' for c in name.strip()) or 'GRUPO'
    stage = out_dir / f'{STAGE_PREFIX}{nombre}'
    manifest: dict[str, Any] = {
        'name': nombre, 'feeders': list(selectors), 'network_ids': [],
        'reglas': reglas.__dict__, 'entrada': informe_entrada.texto(), 'status': 'failed',
    }
    try:
        # Dentro del try: un nombre que no existe también deja manifiesto.
        networks = _selection(dataset, selectors, False)
        manifest['feeders'] = [feeder_short_name(n) for n in networks]
        manifest['network_ids'] = networks
        modelos, informes = [], {}
        for index, net in enumerate(networks, start=1):
            if cancel is not None and cancel.is_set():
                manifest['status'] = 'cancelled'
                return manifest
            if on_progress is not None:
                on_progress(net, index, len(networks))
            m = build_feeder_model(dataset, net, aliases=dict(aliases or {}), strict=strict,
                                   include_geography=True)
            informes[m.name] = aplicar_reglas(m, reglas, correcciones=catalog_corrections)
            modelos.append(m)
        combinado, informe_union = combine_models(modelos, name=nombre)
        geography = build_geography(dataset, combinado, source_crs=source_crs, target_crs=target_crs)
        _clear_stage(stage)
        stage.mkdir(parents=True, exist_ok=True)
        dgs_path = stage / f'{nombre}.dgs'
        feeder_metadata_path = stage / f'{nombre}_feeder_metadata.json'
        man = write_dgs(combinado, dgs_path, schema_profile=schema_profile,
                        geography=geography, trafos=trafos)
        write_feeder_metadata(man.feeder_assignments, dgs_path, feeder_metadata_path)
        report = validate_dgs(combinado, dgs_path, schema_profile=schema_profile, geography=geography)
        write_validation_reports(report, stage / f'{nombre}_validation.json',
                                 stage / f'{nombre}_validation.txt')
        write_geography_manifest(geography, stage / f'{nombre}_geography.json', model=combinado)
        completitud = auditar_completitud(dataset, networks, combinado, parse_dgs(dgs_path),
                                          informes.values())
        ok = report['errors_total'] == 0 and not completitud['fallos']
        if ok:
            _publish(stage, out_dir)
        else:
            _publish(stage, out_dir, only={f'{nombre}_validation.json', f'{nombre}_validation.txt'})
        hoja = man.diagram_sheet
        manifest.update({
            'status': 'ok' if ok else 'failed',
            'dgs': str(out_dir / f'{nombre}.dgs') if ok else None,
            'feeder_metadata': (str(out_dir / feeder_metadata_path.name) if ok else None),
            'errors_total': report['errors_total'],
            'counts': report['counts'],
            'union': informe_union.text(),
            'ties': len(getattr(combinado.combined, 'ties', ()) or ()),
            'de_energised_nodes': sorted(getattr(combinado.combined, 'de_energised', ()) or ()),
            'reglas_por_alimentador': informes,
            'completitud': completitud,
            'hoja': ({'formato': hoja.formato, 'orientacion': hoja.orientacion,
                      'escala_1_a': round(1000.0 / hoja.scale),
                      'cuadricula_mm': man.diagram_grid_mm} if hoja is not None and hoja.formato else None),
            'warnings': list(combinado.warnings),
        })
        if not ok:
            manifest['error'] = '; '.join(
                report['schema_errors'] + report['structural_errors'] + report['connection_errors']
                + report.get('geographic_errors', []) + report.get('graphic_errors', [])
                + [f'completitud: {f}' for f in completitud['fallos']])
    except (ModelBuildError, KeyError, ValueError, OSError, ImportError) as exc:
        manifest['error'] = str(exc)
        manifest['islands'] = getattr(exc, 'islands', {})
    finally:
        _clear_stage(stage)
        (out_dir / f'{nombre}_manifest.json').write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    return manifest
