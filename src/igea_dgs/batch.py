from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from pathlib import Path

from .dataset import CymdistDataset
from .dgs import write_dgs
from .export_tables import write_dgs_tsv, write_dgs_xlsx
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
from .validate import validate_dgs, write_validation_reports

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
) -> dict:
    """Convierte la selección y devuelve el manifiesto del lote.

    ``cancel`` permite abortar entre alimentadores: los ya publicados se conservan,
    el que estuviera en curso se descarta entero (nunca a medias) y el manifiesto se
    escribe igualmente con ``status='cancelled'``.

    ``catalog_corrections`` son los valores de ficha de :mod:`igea_dgs.catalog`. Se
    aplican **entre** construir el modelo y escribir el DGS, que es el único punto
    donde tienen sentido: el TXT ya dijo qué elemento es cada tramo y el DGS todavía
    no se ha escrito. Van aquí, y no en un guion aparte, para que la corrección
    ocurra en el mismo camino que la conversión normal —con su georreferenciación,
    su validación y su publicación atómica— en lugar de en una copia paralela que
    tarde o temprano se desviaría.
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

    networks = _selection(dataset, selectors, all_feeders)
    names = output_names(networks)
    disambiguated = {
        network_id: name for network_id, name in names.items()
        if name != feeder_short_name(network_id)
    }

    items: list[dict] = []
    total = len(networks)

    cancelled = False
    try:
        for index, network_id in enumerate(networks, start=1):
            if cancel is not None and cancel.is_set():
                cancelled = True
                break
            if on_progress is not None:
                on_progress(network_id, index, total)
            feeder = names[network_id]
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
            # Un FEEDER=/SOURCE sin filas SECTION ya no se omite: se convierte dibujando
            # la barra de cabecera, que es lo único que el export contiene. El manifiesto
            # lo marca como 'source_only' para que no se confunda con un alimentador
            # modelado (ver model.build_feeder_model).
            source_only = not dataset.feeders.get(network_id)
            try:
                model = build_feeder_model(
                    dataset, network_id, aliases=aliases, strict=strict,
                    include_geography=include_geography,
                )
                if catalog_corrections:
                    from .catalog import aplicar_correcciones

                    cambios = aplicar_correcciones(model, dict(catalog_corrections))
                    if cambios:
                        catalog_changes[feeder] = [c.linea() for c in cambios]
                geography = None
                geography_report = None
                if include_geography:
                    geography = build_geography(dataset, model, source_crs=source_crs, target_crs=target_crs)
                    geography_report = validate_geography(model, geography)
                    if geography_report['errors_total']:
                        raise ModelBuildError(f'{network_id}: geographic validation failed: {geography_report["errors"]}')
                    write_geography_manifest(geography, geo_path, model=model)
                    write_geography_validation(geography_report, geo_validation_path)

                if write_preview:
                    assert geography is not None
                    write_preview_html(
                        model, geography, preview_html_path, backend=preview_backend,
                    )
                    write_preview_geojson(model, geography, preview_geojson_path)

                write_dgs(model, dgs_path, schema_profile=schema_profile, geography=geography)

                if export_xlsx:
                    write_dgs_xlsx(dgs_path, xlsx_path)
                if export_tsv:
                    write_dgs_tsv(dgs_path, tsv_dir)

                report = validate_dgs(model, dgs_path, schema_profile=schema_profile, geography=geography)
                write_validation_reports(report, json_path, txt_path)
                ok = report['errors_total'] == 0
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

                item = {
                    'feeder': feeder,
                    'short_name': feeder_short_name(network_id),
                    'network_id': network_id,
                    'status': 'ok' if ok else 'failed',
                    'dgs': str(dgs_path) if ok else None,
                    'dgs_published': ok,
                    'validation_json': str(json_path),
                    'validation_txt': str(txt_path),
                    'errors_total': report['errors_total'],
                    'aliases': dict(model.line_type_aliases),
                    'unresolved_line_types': sorted(model.unresolved_line_types),
                    'counts': report['counts'],
                    'topology': 'source_only' if source_only else 'full',
                    'islands': model.islands or {},
                    'warnings': list(model.warnings),
                    'source_crs': source_crs if include_geography else None,
                    'target_crs': target_crs if include_geography else None,
                }
                if include_geography:
                    item['geography'] = str(geo_path)
                    item['geography_validation'] = str(geo_validation_path)
                    item['geography_coverage'] = {
                        'nodes_pct': geography_report['node_coverage_pct'],
                        'lines_pct': geography_report['line_coverage_pct'],
                        'intermediate_points': geography_report['intermediate_points'],
                    }
                if write_preview:
                    item['preview_html'] = str(preview_html_path)
                    item['preview_geojson'] = str(preview_geojson_path)
                if export_xlsx:
                    item['xlsx'] = str(xlsx_path)
                if export_tsv:
                    item['tsv_dir'] = str(tsv_dir)
                if not ok:
                    item['error'] = '; '.join(
                        report['schema_errors'] + report['structural_errors'] + report['connection_errors'] +
                        report.get('geographic_errors', []) + report.get('graphic_errors', [])
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
            items.append(item)

    finally:
        # El manifiesto se escribe pase lo que pase: un lote sin manifiesto
        # es un lote sin traza. Incluye lo procesado hasta el momento.
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
