"""Coordenadas: del CRS de origen a WGS84, geometría de nodos y tramos y su validación.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math

from .dataset import CymdistDataset
from .model import FeederModel


class CrsOrigenFaltaError(ValueError):
    """Se pidió georreferenciar sin CRS de origen (spec 002, RF-32)."""


MENSAJE_FALTA_CRS = (
    'Falta el CRS de origen de las coordenadas. Elíjalo (un código EPSG en metros, por '
    'ejemplo el UTM de su zona) o póngalo como «crs_origen» en config/perfil_empresa.json '
    '(puede heredar uno de config/perfiles/ con «"perfil": "<nombre>"»). Sin CRS, '
    'convierta sin georreferenciación.'
)


def exigir_crs_origen(source_crs: str | None) -> str:
    """El CRS de origen, o :class:`CrsOrigenFaltaError` si no se eligió ninguno.

    Antes se suponía el UTM 18S de Ica: con datos de otra zona la red salía desplazada
    cientos de kilómetros, sin aviso (constitución P13). Ahora se pregunta.
    """
    if not source_crs or not str(source_crs).strip():
        raise CrsOrigenFaltaError(MENSAJE_FALTA_CRS)
    return str(source_crs).strip()


def assert_metre_source_crs(source_crs: str) -> None:
    """Reject a source CRS whose axes are not in metres.

    Electrical lengths are measured as euclidean distance over raw CoordX/CoordY
    and stored as metres (``model.apply_georeferenced_lengths``). A CRS in degrees
    or feet therefore scales every length silently — with EPSG:4326 by a factor of
    ~1e5 — and no validation catches it, because the validator compares the DGS
    against the very model that produced it.

    See docs/DIAGNOSTICO_BACKEND_FRONTEND_2026-09-22.md (C-01).
    """
    try:
        from pyproj import CRS
    except ImportError:  # pragma: no cover - geography path already requires pyproj
        return
    try:
        crs = CRS.from_user_input(source_crs)
    except Exception as exc:
        raise ValueError(f'CRS de origen no reconocido: {source_crs!r} ({exc})') from exc
    axis = crs.axis_info[0] if crs.axis_info else None
    if axis is None:
        raise ValueError(f'CRS de origen sin información de ejes: {source_crs!r}')
    factor = getattr(axis, 'unit_conversion_factor', None)
    if crs.is_geographic or factor is None or abs(factor - 1.0) > 1e-9:
        unit = getattr(axis, 'unit_name', 'desconocida')
        raise ValueError(
            f'CRS de origen {source_crs!r} usa unidades {unit!r}, no metros. '
            'Las longitudes de línea se miden en las unidades del CRS y se escriben '
            'como metros, de modo que este CRS produciría un modelo eléctrico '
            'silenciosamente falso. Indique el CRS proyectado en metros de su export '
            '(por ejemplo un UTM regional), o convierta con --no-geography.'
        )


def make_transformer(source_crs: str, target_crs: str):
    """El único constructor de transformadores del proyecto, siempre en orden x/y.

    Había cinco y cada uno trataba distinto un CRS inválido: el lector de SED nuevas,
    ya retirado, lo callaba y todas las SED nuevas salían sin GPS, sin aviso; los demás soltaban el
    ``CRSError`` de pyproj sin decir qué CRS fallaba. Aquí es un ``ValueError`` con los
    dos CRS, el mismo tipo que ``assert_metre_source_crs`` y que el CLI ya informa.
    """
    try:
        from pyproj import Transformer
        from pyproj.exceptions import CRSError
    except ImportError as exc:  # pragma: no cover - depends on local install
        raise ImportError(
            'pyproj es obligatorio para georreferenciación. '
            'Instale con: pip install -r requirements.txt  '
            '(o desactive geografía con --no-geography / la GUI).'
        ) from exc
    try:
        return Transformer.from_crs(source_crs, target_crs, always_xy=True)
    except CRSError as exc:
        raise ValueError(
            f'No se puede reproyectar de {source_crs!r} a {target_crs!r}: '
            f'CRS no reconocido ({exc})'
        ) from exc


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float
    x: float | None = None
    y: float | None = None


@dataclass(frozen=True)
class GeoLine:
    section_id: str
    from_node: str
    to_node: str
    path: tuple[GeoPoint, ...]


@dataclass(frozen=True)
class GeographyManifest:
    feeder: str
    network_id: str
    source_node: str
    source_crs: str
    target_crs: str
    nodes: dict[str, GeoPoint]
    lines: dict[str, GeoLine]
    source_xy_bounds: tuple[float, float, float, float]
    target_bounds: tuple[float, float, float, float]
    intermediate_point_count: int
    intermediate_section_count: int

    @property
    def expected_counts(self) -> dict[str, int]:
        return {
            'nodes': len(self.nodes),
            'lines': len(self.lines),
            'loads': 0,
            'switches': 0,
            'sources': 1,
            'intermediate_points': self.intermediate_point_count,
        }


def _as_float(value: str | float | int | None, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid coordinate {field}={value!r}') from exc
    if not math.isfinite(result):
        raise ValueError(f'Invalid coordinate {field}={value!r}')
    return result


def _seq(value: str | None) -> tuple[int, str]:
    try:
        return int(value or '0'), value or ''
    except ValueError:
        return 10**9, value or ''


def build_geography(
    dataset: CymdistDataset,
    model: FeederModel,
    *,
    source_crs: str | None,
    target_crs: str = 'EPSG:4326',
) -> GeographyManifest:
    """Build WGS84/geographic geometry for one feeder from IGEA/CYMDIST coordinates.

    The TXT data are the only source of topology and geometry. ``source_crs`` is
    deliberately configurable because exported GIS databases may use a different
    projected coordinate reference system.
    """
    transformer = make_transformer(exigir_crs_origen(source_crs), target_crs)

    nodes: dict[str, GeoPoint] = {}
    xs: list[float] = []
    ys: list[float] = []
    lons: list[float] = []
    lats: list[float] = []

    for node_id, node in model.nodes.items():
        if node.x is None or node.y is None:
            raise ValueError(f'{model.name}: node {node_id} has no source coordinates')
        x = _as_float(node.x, field=f'{node_id}.CoordX')
        y = _as_float(node.y, field=f'{node_id}.CoordY')
        lon, lat = transformer.transform(x, y)
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f'{model.name}: node {node_id} transformed to invalid WGS84 coordinates')
        nodes[node_id] = GeoPoint(lat=lat, lon=lon, x=x, y=y)
        xs.append(x); ys.append(y); lons.append(lon); lats.append(lat)

    # Índice del dataset, construido una vez para todo el lote (ver CymdistDataset).
    intermediate_by_section = {
        sid: rows for sid in model.section_by_id
        if (rows := dataset.intermediate_by_section.get(sid))
    }

    lines: dict[str, GeoLine] = {}
    intermediate_point_count = 0
    for line in model.lines:
        path: list[GeoPoint] = [nodes[line.from_node]]
        rows = sorted(intermediate_by_section.get(line.section_id, ()), key=lambda r: _seq(r.get('SeqNumber')))
        for row in rows:
            x = _as_float(row.get('CoordX'), field=f'{line.section_id}.CoordX')
            y = _as_float(row.get('CoordY'), field=f'{line.section_id}.CoordY')
            lon, lat = transformer.transform(x, y)
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f'{model.name}: intermediate point on {line.section_id} transformed outside WGS84 range')
            point = GeoPoint(lat=lat, lon=lon, x=x, y=y)
            path.append(point)
            xs.append(x); ys.append(y); lons.append(lon); lats.append(lat)
        intermediate_point_count += len(rows)
        path.append(nodes[line.to_node])
        lines[line.section_id] = GeoLine(
            section_id=line.section_id,
            from_node=line.from_node,
            to_node=line.to_node,
            path=tuple(path),
        )

    if not nodes:
        raise ValueError(f'{model.name}: no nodes available for geography')

    return GeographyManifest(
        feeder=model.name,
        network_id=model.network_id,
        source_node=model.source_node,
        source_crs=source_crs,
        target_crs=target_crs,
        nodes=nodes,
        lines=lines,
        source_xy_bounds=(min(xs), min(ys), max(xs), max(ys)),
        target_bounds=(min(lons), min(lats), max(lons), max(lats)),
        intermediate_point_count=intermediate_point_count,
        intermediate_section_count=len(intermediate_by_section),
    )


def _point_dict(point: GeoPoint) -> dict[str, float]:
    result = {'lat': point.lat, 'lon': point.lon}
    if point.x is not None:
        result['x'] = point.x
    if point.y is not None:
        result['y'] = point.y
    return result


def geography_to_dict(geo: GeographyManifest, model: FeederModel | None = None) -> dict:
    sed_n = len(model.seds) if model is not None else 0
    # Una fuente por alimentador: en una red unida (combine) hay tantas como alimentadores.
    combinado = getattr(model, 'combined', None) if model is not None else None
    fuentes = len(getattr(combinado, 'feeders', None) or ()) or 1
    # Spec 022: una por barra de SET y una por alimentador «Sin SET»; y una red por zonal,
    # o por SET en un zonal dividido (RF-64).
    barras_set = list(getattr(combinado, 'barras_set', None) or []) if combinado is not None else []
    redes: list[str] = []
    if barras_set:
        fuentes = len(barras_set) + len(combinado.sin_set)
        from .combine import redes_en_orden

        redes = redes_en_orden(model)
    from .model import capacitor_resolution_issue, resolve_capacitor_capacity

    combined_node_kv = getattr(combinado, 'node_kv', {}) if combinado is not None else {}
    resolved_capacitors = [
        (bank, resolve_capacitor_capacity(
            bank, combined_node_kv.get(bank.node_id, model.nominal_kv),
        ))
        for bank in (model.capacitors if model is not None else ())
    ]
    expected = {
        'nodes': len(geo.nodes),
        'lines': len(geo.lines),
        'loads': len(model.loads) if model is not None else 0,
        'switches': len(model.devices) if model is not None else 0,
        'sources': fuentes,
        'intermediate_points': geo.intermediate_point_count,
        # SED distribution transformers (ElmTr2 inside ElmSubstat).
        'transformers': sed_n,
        'substations_sed': sed_n,
        'capacitors': sum(
            1 for bank, capacity in resolved_capacitors
            if capacity.kvar_per_step is not None and capacity.total_kvar is not None
            and bank.node_id in geo.nodes
        ),
        'regulators': 0,
    }
    return {
        'format': 'igea-dgs-geography-v1',
        'feeder': geo.feeder,
        **({'redes': redes} if redes else {}),
        'network_id': geo.network_id,
        'source_node': geo.source_node,
        'expected_counts': expected,
        'capacitor_banks': [{
            'loc_name': bank.capacitor_id[:40],
            'terminal': bank.node_id[:40],
            'feeder': bank.feeder,
            'network_id': bank.network_id,
            'grid': model.name,
            'ctech': 1 if bank.phases == 'ABC' else (3 if len(bank.phases) == 2 else 6),
            'shtype': 2,
            'qcapn': capacity.kvar_per_step / 1000.0,
            'ncapx': bank.steps,
            'ncapa': bank.steps,
            'ushnm': capacity.nominal_kv,
            'outserv': 0 if bank.in_service else 1,
            'total_source_mvar': (
                bank.total_kvar / 1000.0 if bank.total_kvar is not None else None
            ),
            'total_effective_mvar': capacity.total_kvar / 1000.0,
            'phases': bank.phases,
            'capacity_origin': capacity.origin,
            'correction': capacity.correction,
        } for bank, capacity in resolved_capacitors
            if capacity.kvar_per_step is not None and capacity.total_kvar is not None
            and bank.node_id in geo.nodes],
        'capacitor_issues': [issue for bank, capacity in resolved_capacitors
            if (issue := capacitor_resolution_issue(
                bank, capacity, node_exists=bank.node_id in geo.nodes,
            )) is not None],
        'source_crs': geo.source_crs,
        'target_crs': geo.target_crs,
        'source_xy_bounds': list(geo.source_xy_bounds),
        'target_bounds': list(geo.target_bounds),
        'intermediate_sections': geo.intermediate_section_count,
        'equipment_scope_note': (
            'Transformers = SED ElmTr2 from CARGA. Capacitors come from [SHUNT CAPACITOR '
            'SETTING] in RED or CYMSHUNTCAPACITOR in the .mdb; regulators from REGULATOR '
            'SETTING. The BD_Equipo catalog alone is not placed on the network.'
        ),
        'nodes': {node_id: _point_dict(point) for node_id, point in geo.nodes.items()},
        'lines': {
            sid: {
                'from_node': line.from_node,
                'to_node': line.to_node,
                'path': [_point_dict(point) for point in line.path],
            }
            for sid, line in geo.lines.items()
        },
    }


def write_geography_manifest(
    geo: GeographyManifest,
    path: Path | str,
    *,
    model: FeederModel | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(geography_to_dict(geo, model), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def validate_geography(model: FeederModel, geo: GeographyManifest) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if set(geo.nodes) != set(model.nodes):
        missing = set(model.nodes) - set(geo.nodes)
        extra = set(geo.nodes) - set(model.nodes)
        if missing:
            errors.append(f'Missing geographic nodes: {sorted(missing)[:20]}')
        if extra:
            errors.append(f'Unexpected geographic nodes: {sorted(extra)[:20]}')
    if set(geo.lines) != {line.section_id for line in model.lines}:
        errors.append('Geographic line set differs from electrical line set')

    for node_id, point in geo.nodes.items():
        if not (math.isfinite(point.lat) and math.isfinite(point.lon) and -90 <= point.lat <= 90 and -180 <= point.lon <= 180):
            errors.append(f'{node_id}: invalid WGS84 coordinates')
    for line in model.lines:
        gline = geo.lines.get(line.section_id)
        if gline is None:
            continue
        if not gline.path:
            errors.append(f'{line.section_id}: empty geographic path')
            continue
        if gline.path[0] != geo.nodes[line.from_node]:
            errors.append(f'{line.section_id}: geographic path does not start at FromNode')
        if gline.path[-1] != geo.nodes[line.to_node]:
            errors.append(f'{line.section_id}: geographic path does not end at ToNode')
        if gline.from_node != line.from_node or gline.to_node != line.to_node:
            errors.append(
                f'{line.section_id}: GeoLine From/To ({gline.from_node}->{gline.to_node}) '
                f'differs from model ({line.from_node}->{line.to_node})'
            )

    node_cov = 100.0 * len(geo.nodes) / len(model.nodes) if model.nodes else 0.0
    line_cov = 100.0 * len(geo.lines) / len(model.lines) if model.lines else 0.0
    return {
        'feeder': model.name,
        'source_crs': geo.source_crs,
        'target_crs': geo.target_crs,
        'node_coverage_pct': node_cov,
        'line_coverage_pct': line_cov,
        'nodes': {'source': len(model.nodes), 'geographic': len(geo.nodes)},
        'lines': {'source': len(model.lines), 'geographic': len(geo.lines)},
        'intermediate_points': geo.intermediate_point_count,
        'intermediate_sections': geo.intermediate_section_count,
        'errors': errors,
        'warnings': warnings,
        'errors_total': len(errors),
    }


def write_geography_validation(report: dict, path: Path | str) -> None:
    path = Path(path)
    lines = [
        f"GEOGRAPHIC VALIDATION: {report['feeder']}",
        '=' * 72,
        f"Source CRS: {report['source_crs']}",
        f"Target CRS: {report['target_crs']}",
        f"Node coverage: {report['node_coverage_pct']} % ({report['nodes']['geographic']}/{report['nodes']['source']})",
        f"Line coverage: {report['line_coverage_pct']} % ({report['lines']['geographic']}/{report['lines']['source']})",
        f"Intermediate points: {report['intermediate_points']}/{report['intermediate_points']}",
        f"Intermediate sections: {report['intermediate_sections']}",
        f"ERRORS: {len(report['errors'])}",
    ]
    lines.extend(f'  - {x}' for x in report['errors'])
    lines.append(f"WARNINGS: {len(report['warnings'])}")
    lines.extend(f'  - {x}' for x in report['warnings'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
