"""Capa de aplicación compartida por CLI y Web (sección E24 de VNR-GIS.md).

CLI y Web importan estas funciones; ninguno implementa lógica de negocio propia.
Usa los conectores, el descubrimiento, el GIS/snapping y los exportadores, y
coordina la secuencia fuente → modelo canónico → validación → export.
"""

from __future__ import annotations

import math
import json
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vnr_etl.connectors import resolve_adapter
from vnr_etl.discovery import compute_schema_fingerprint
from vnr_etl.discovery.schema import SchemaResolver, resolve_alias
from vnr_etl.gis.geometry import coords_from_geojson, polyline_length_m
from vnr_etl.gis.snapping import deterministic_node_id, snap_endpoints
from vnr_etl.models import CanonicalModel, Lineage, Node, Section


@dataclass
class ExtractReport:
    source: Path
    destination: Path
    format: str
    files: list[Path]
    total_bytes: int


def safe_extract_package(source: Path | str, destination: Path | str) -> ExtractReport:
    """Materializa un paquete en staging y lo publica solo tras extracción segura."""
    from vnr_etl.discovery.download import safe_extract_rar, safe_extract_zip

    source, destination = Path(source), Path(destination)
    staging = destination.with_name(destination.name + '.part')
    shutil.rmtree(staging, ignore_errors=True)
    if destination.exists():
        raise FileExistsError(f'La carpeta derivada ya existe: {destination}')
    staging.mkdir(parents=True)
    try:
        suffix = source.suffix.lower()
        if suffix == '.zip':
            files = safe_extract_zip(source, staging, uncompressed_limit_bytes=8 * 1024**3)
            package_format = 'zip'
        elif suffix == '.rar':
            files = safe_extract_rar(source, staging, uncompressed_limit_bytes=8 * 1024**3)
            package_format = 'rar'
        elif source.is_file():
            target = staging / source.name
            shutil.copy2(source, target)
            files = [target]
            package_format = source.suffix.lower().lstrip('.') or 'file'
        else:
            raise ValueError(f'Paquete VNR inexistente o no soportado: {source}')
        staging.replace(destination)
        published = [destination / path.relative_to(staging) for path in files]
        return ExtractReport(
            source=source,
            destination=destination,
            format=package_format,
            files=published,
            total_bytes=sum(path.stat().st_size for path in published),
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _geojson_rows(path: Path) -> tuple[list[dict], str]:
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    if payload.get('type') != 'FeatureCollection' or not isinstance(payload.get('features'), list):
        raise ValueError(f'{path.name} no es un FeatureCollection GeoJSON.')
    crs = 'EPSG:4326'
    crs_raw = payload.get('crs') or {}
    name = ((crs_raw.get('properties') or {}).get('name') if isinstance(crs_raw, Mapping) else '')
    if isinstance(name, str) and name:
        crs = name.rsplit(':', 1)[-1]
        crs = f'EPSG:{crs}' if crs.isdigit() else name
    return list(payload['features']), crs


def canonicalize_vnr_package(
    package_root: Path | str,
    *,
    company: str | None = 'ELDU',
    period: str | None = 'latest_available',
) -> tuple[CanonicalizeResult, dict[str, str]]:
    """Descubre capas de tramo por campos, no por nombre de archivo."""
    from vnr_etl.connectors.registry import iter_supported_sources

    candidates: list[tuple[list[dict], str, str, str, str, str, str]] = []
    errors: list[str] = []
    for path in iter_supported_sources(package_root):
        try:
            if path.suffix.lower() in ('.geojson', '.json'):
                rows, crs = _geojson_rows(path)
                layer_name = path.name
            else:
                adapter = resolve_adapter(str(path))
                layers = adapter.list_layers()
                if not layers:
                    continue
                for layer in layers:
                    rows = adapter.read_layer(layer.name)
                    fields = sorted({str(key) for row in rows for key in normalize_feature_record(row)})
                    section_field, _ = resolve_alias('section_id', fields)
                    feeder_field, _ = resolve_alias('feeder_id', fields)
                    if section_field and feeder_field:
                        conductor_field, _ = resolve_alias('standard_code', fields)
                        length_field, _ = resolve_alias('length_source', fields)
                        candidates.append((
                            rows, layer.crs or '', f'{path.name}:{layer.name}',
                            section_field, feeder_field, conductor_field or '', length_field or '',
                        ))
                continue
            fields = sorted({str(key) for row in rows for key in normalize_feature_record(row)})
            section_field, _ = resolve_alias('section_id', fields)
            feeder_field, _ = resolve_alias('feeder_id', fields)
            if section_field and feeder_field:
                conductor_field, _ = resolve_alias('standard_code', fields)
                length_field, _ = resolve_alias('length_source', fields)
                candidates.append((
                    rows, crs, layer_name, section_field, feeder_field,
                    conductor_field or '', length_field or '',
                ))
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f'{path.name}: {exc}')
    if not candidates:
        detail = '; '.join(errors[:5])
        raise ValueError(
            'El paquete no contiene una capa con section_id/CODTRAMOMT y '
            f'feeder_id/CODSALIDAMT.{" " + detail if detail else ""}'
        )
    if len(candidates) > 1:
        raise ValueError(
            'El paquete contiene varias capas de tramos candidatas; se requiere una '
            'selección explícita para no mezclarlas: ' + ', '.join(item[2] for item in candidates)
        )
    rows, crs, layer, section_field, feeder_field, conductor_field, length_field = candidates[0]
    scoped, scope = select_source_scope(rows, company=company, period=period)
    result = canonicalize_sections(
        scoped,
        section_id_field=section_field,
        feeder_field=feeder_field,
        conductor_field=conductor_field or None,
        length_field=length_field or None,
        source_crs=crs or None,
        source_layer=layer,
    )
    result.model.metadata.update({'company': scope['company'], 'period': scope['period']})
    return result, scope


def probe_source(source: str) -> dict:
    adapter = resolve_adapter(source)
    return adapter.probe(source).as_dict()


def discover_layers(source: str) -> list[dict]:
    adapter = resolve_adapter(source)
    return [layer.as_dict() for layer in adapter.list_layers()]


def read_layer(source: str, layer, filters: Mapping[str, Any] | None = None) -> list[dict]:
    adapter = resolve_adapter(source)
    return adapter.read_layer(layer, filters=filters)


def list_companies(source: str) -> list[str]:
    adapter = resolve_adapter(source)
    try:
        return adapter.available_companies()
    finally:
        adapter.close()


def list_periods(source: str, company: str | None = None) -> list[str]:
    adapter = resolve_adapter(source)
    try:
        return adapter.available_periods(company=company)
    finally:
        adapter.close()


def resolve_schema(fields: Sequence[str], *, layer: str = '',
                   aliases: Mapping[str, Sequence[str]] | None = None) -> dict:
    resolver = SchemaResolver(aliases=aliases)
    return {k: v.as_dict() for k, v in resolver.resolve_fields(fields, layer=layer).items()}


def fingerprint_layers(layers: Sequence[dict]) -> str:
    return compute_schema_fingerprint(layers)


def suggest_utm_crs(lon: float, lat: float) -> str:
    """CRS UTM WGS84 para un punto, como CRS de **trabajo** métrico.

    No deduce el *datum* de la empresa (PSAD56/SIRGAS), solo una zona UTM WGS84
    coherente con las coordenadas, que es lo único que el snapping métrico necesita
    y lo único que estas coordenadas permiten deducir sin adivinar.
    """
    zone = math.floor((lon + 180.0) / 6.0) + 1
    zone = max(1, min(60, zone))
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return f'EPSG:{epsg}'


def _transform_points(points, source_crs, working_crs):
    """Reproyecta puntos; devuelve la misma lista si no hay pyproj o ya coinciden."""
    if not source_crs or not working_crs or source_crs == working_crs:
        return points
    try:
        import pyproj

        transformer = pyproj.Transformer.from_crs(source_crs, working_crs, always_xy=True)
        return [transformer.transform(x, y) for x, y in points]
    except ImportError:  # pragma: no cover
        raise RuntimeError('Reproyección requiere «pyproj».') from None


@dataclass
class CanonicalizeResult:
    model: CanonicalModel
    warnings: list[str] = field(default_factory=list)
    length_report: list[dict] = field(default_factory=list)
    snap_report: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            'counts': self.model.counts(),
            'warnings': self.warnings,
            'length_report': self.length_report,
            'snap_report': self.snap_report,
        }


def normalize_feature_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normaliza un registro plano o una entidad GeoJSON a un único contrato.

    ArcGIS ``f=geojson`` guarda los atributos en ``properties`` y la geometría
    en el nivel superior. Los demás conectores ya entregan registros planos.
    Conservar ambos formatos aquí evita que la capa canónica dependa del origen.
    """
    if not isinstance(row, Mapping):
        raise TypeError('Cada registro de la fuente debe ser un objeto/mapping.')
    properties = row.get('properties')
    if properties is None:
        return dict(row)
    if not isinstance(properties, Mapping):
        raise TypeError('Entidad GeoJSON inválida: «properties» debe ser un objeto.')
    record = dict(properties)
    for key, value in row.items():
        if key not in ('properties', 'type'):
            record[key] = value
    return record


def select_source_scope(
    rows: Sequence[Mapping[str, Any]],
    *,
    company: str | None = None,
    period: str | None = 'latest_available',
) -> tuple[list[dict], dict[str, str]]:
    """Selecciona una sola empresa/periodo sin mezclar entregas silenciosamente."""
    normalized = [normalize_feature_record(row) for row in rows]
    fields = sorted({str(key) for row in normalized for key in row})
    company_field, _ = resolve_alias('company', fields)
    period_field, _ = resolve_alias('period', fields)

    companies = sorted({
        str(row.get(company_field)).strip() for row in normalized
        if company_field and row.get(company_field) not in (None, '')
    })
    selected_company = (company or '').strip()
    if not selected_company:
        if len(companies) > 1:
            raise ValueError(
                'La fuente contiene múltiples empresas; indique --company para evitar mezclarlas.'
            )
        selected_company = companies[0] if companies else ''
    if companies and selected_company not in companies:
        raise ValueError(f'Empresa no encontrada en la fuente: {selected_company}')
    selected = [
        row for row in normalized
        if not company_field or not selected_company
        or str(row.get(company_field, '')).strip() == selected_company
    ]

    periods = sorted({
        str(row.get(period_field)).strip() for row in selected
        if period_field and row.get(period_field) not in (None, '')
    }, key=_period_key)
    requested_period = (period or '').strip()
    selected_period = periods[-1] if requested_period == 'latest_available' and periods else requested_period
    if requested_period not in ('', 'latest_available') and periods and requested_period not in periods:
        raise ValueError(f'Periodo no encontrado para {selected_company or "la fuente"}: {requested_period}')
    if selected_period:
        selected = [
            row for row in selected
            if not period_field or str(row.get(period_field, '')).strip() == selected_period
        ]
    if not selected:
        raise ValueError('La selección empresa/periodo no produjo registros.')
    return selected, {'company': selected_company, 'period': selected_period}


def _period_key(value: str) -> tuple:
    numbers = tuple(int(item) for item in re.findall(r'\d+', value))
    return (*numbers, value)


def canonicalize_sections(
    section_rows: Sequence[Mapping[str, Any]],
    *,
    section_id_field: str = 'CODTRAMOMT',
    feeder_field: str | None = 'CODSALIDAMT',
    conductor_field: str | None = 'CODNORMA',
    length_field: str | None = 'LONGITUD',
    source_crs: str | None = 'EPSG:4326',
    working_crs: str | None = None,
    snap_tolerance_m: float = 0.5,
    source_layer: str = 'sections',
) -> CanonicalizeResult:
    """Convierte tramos polilínea en nodos + tramos canónicos (secciones E y G).

    Reconstruye los nodos desde los extremos de la geometría, rellena longitudes
    métricas y las cruza con ``LONGITUD`` cuando es parseable. La geometría se
    guarda en el CRS de trabajo (metros) y se conservan el CRS de origen y el
    origen de cada tramo.
    """
    normalized_rows = [normalize_feature_record(row) for row in section_rows]
    # Auto-elegir CRS de trabajo métrico si venía en grados.
    resolved_working = working_crs
    if source_crs == 'EPSG:4326' and not resolved_working:
        first = normalized_rows[0].get('geometry') if normalized_rows else None
        pts = coords_from_geojson(first) if first else []
        if pts:
            resolved_working = suggest_utm_crs(pts[0][0], pts[0][1])
    resolved_working = resolved_working or source_crs
    model = CanonicalModel(metadata={
        'source_crs': source_crs,
        'working_crs': resolved_working,
        'working_crs_is_projected': _is_projected_crs(resolved_working),
        'source_layer': source_layer,
        'input_section_count': len(normalized_rows),
    })

    anchors: list[tuple[str, float, float]] = []
    sections: list[Section] = []
    warnings: list[str] = []
    length_report: list[dict] = []

    prepared: list[dict] = []
    seen_section_ids: set[str] = set()
    for row in normalized_rows:
        section_id = str(row.get(section_id_field) or '').strip()
        if not section_id:
            raise ValueError(
                f'Tramo sin identificador obligatorio «{section_id_field}»; '
                'la ingestión se bloquea para evitar pérdida o colisión de datos.'
            )
        if section_id in seen_section_ids:
            raise ValueError(f'Identificador de tramo duplicado: {section_id}')
        seen_section_ids.add(section_id)
        geometry = row.get('geometry') or row.get('__geometry__')
        if not geometry:
            warnings.append(f'Tramo sin geometría, se omite: {section_id}')
            continue
        raw_coords = coords_from_geojson(geometry)
        if len(raw_coords) < 2:
            warnings.append(f'Tramo sin geometría de línea, se omite: {section_id}')
            continue
        prepared.append({'row': row, 'raw_coords': raw_coords, 'section_id': section_id})

    for item in prepared:
        row = item['row']
        raw_coords = item['raw_coords']
        section_id = item['section_id']
        # Reproyectar a metros.
        coords = _transform_points(raw_coords, source_crs, resolved_working)
        geom = [[x, y] for x, y in coords]
        length_m = polyline_length_m(coords)
        source_length = _parse_float(row.get(length_field)) if length_field else None
        if source_length is not None and source_length > 0:
            length_report.append({
                'section_id': section_id,
                'gis_m': round(length_m, 3),
                'source_m': round(source_length, 3),
                'delta_pct': round(100.0 * abs(length_m - source_length) / source_length, 3),
            })
        start, end = coords[0], coords[-1]
        anchors.append((f'{section_id}:from', start[0], start[1]))
        anchors.append((f'{section_id}:to', end[0], end[1]))
        sections.append(Section(
            section_id=section_id,
            from_node='',  # se rellena tras el snapping
            to_node='',
            conductor_code=str(row.get(conductor_field) or '') if conductor_field else '',
            phases='',
            nominal_kv=None,
            length_m=length_m,
            geometry=geom,
            source_layer=source_layer,
            source_id=section_id,
            feeder_id=str(row.get(feeder_field) or '') if feeder_field else '',
            lineage=Lineage(
                source_layer=source_layer,
                source_id=section_id,
                source_field=section_id_field,
                resolution_method='SOURCE',
            ),
        ))

    snap = snap_endpoints(anchors, snap_tolerance_m)
    # Re-mapear IDs de tramo → nodo de origen/destino.
    anchor_index = 0
    for section in sections:
        from_key = (round(anchors[anchor_index][1], 9), round(anchors[anchor_index][2], 9))
        to_key = (round(anchors[anchor_index + 1][1], 9), round(anchors[anchor_index + 1][2], 9))
        section.from_node = snap.node_ids.get(from_key, deterministic_node_id([from_key]))
        section.to_node = snap.node_ids.get(to_key, deterministic_node_id([to_key]))
        anchor_index += 2

    for node_id, (x, y) in snap.node_coords.items():
        model.nodes.append(Node(
            node_id=node_id, x=x, y=y, source_layer='topology', source_id=node_id,
        ))
    model.sections = sections
    model.metadata['output_section_count'] = len(sections)
    return CanonicalizeResult(
        model=model,
        warnings=warnings,
        length_report=length_report,
        snap_report=snap.displacement_report(),
    )


def add_loads(
    result: CanonicalizeResult,
    load_rows: Sequence[Mapping[str, Any]],
    *,
    load_id_field: str = 'COD_SED',
    node_field: str = 'NODO_CONEX',
    kw_field: str = 'KW_MEDIDO',
    kvar_field: str = 'KVAR_MEDID',
    phases_field: str = 'FASES',
) -> CanonicalizeResult:
    """Añade cargas al modelo canónico, referidas a nodos ya reconstruidos."""
    from vnr_etl.models import Load

    nodes = result.model.nodes_by_id()
    for row in load_rows:
        node_id = str(row.get(node_field) or '')
        if node_id not in nodes:
            result.warnings.append(f'Carga en nodo inexistente, se omite: {row.get(load_id_field, "?")}')
            continue
        result.model.loads.append(Load(
            load_id=str(row.get(load_id_field) or ''),
            connection_node=node_id,
            kw=_parse_float(row.get(kw_field)) or 0.0,
            kvar=_parse_float(row.get(kvar_field)) or 0.0,
            phases=str(row.get(phases_field) or ''),
            source_layer='loads',
            source_id=str(row.get(load_id_field) or ''),
        ))
    return result


def _parse_float(value) -> float | None:
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_projected_crs(crs: str | None) -> bool:
    if not crs:
        return False
    try:
        import pyproj

        return bool(pyproj.CRS.from_user_input(crs).is_projected)
    except (ImportError, ValueError):
        return False
