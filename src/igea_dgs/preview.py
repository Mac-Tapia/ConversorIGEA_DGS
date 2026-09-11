"""Vista previa georreferenciada del modelo (opengeos / Leaflet).

Construye capas de nodos y tramos a partir de ``FeederModel`` + ``GeographyManifest``
y escribe un HTML interactivo con popups de atributos DGS.

Backends (en orden):
1. ``leafmap`` (+ ``geopandas`` si está disponible) — preferido (@opengeos)
2. HTML Leaflet autónomo (sin dependencias opcionales) — fallback de tests/CI
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .geography import GeographyManifest
from .model import FeederModel, LineType


class PreviewError(ValueError):
    """Faltan coordenadas o datos técnicos obligatorios para el preview."""


@dataclass(frozen=True)
class PreviewNode:
    node_id: str
    lat: float
    lon: float
    uknom_kv: float
    is_source: bool
    degree: int


@dataclass(frozen=True)
class PreviewLine:
    section_id: str
    from_node: str
    to_node: str
    length_km: float
    length_m: float
    overhead: bool
    type_code: str
    r1_ohm_km: float
    x1_ohm_km: float
    r0_ohm_km: float
    x0_ohm_km: float
    b1_source: float
    ampacity_a: float
    uknom_kv: float
    # (lon, lat) pairs — GeoJSON order
    path: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class PreviewLayers:
    feeder: str
    network_id: str
    nominal_kv: float
    source_crs: str
    target_crs: str
    nodes: tuple[PreviewNode, ...]
    lines: tuple[PreviewLine, ...]

    @property
    def center(self) -> tuple[float, float]:
        if not self.nodes:
            return (0.0, 0.0)
        lat = sum(n.lat for n in self.nodes) / len(self.nodes)
        lon = sum(n.lon for n in self.nodes) / len(self.nodes)
        return (lat, lon)


def _degree_map(model: FeederModel) -> dict[str, int]:
    degrees: dict[str, int] = {node_id: 0 for node_id in model.nodes}
    for line in model.lines:
        degrees[line.from_node] = degrees.get(line.from_node, 0) + 1
        degrees[line.to_node] = degrees.get(line.to_node, 0) + 1
    return degrees


def _type_or_raise(model: FeederModel, type_key: str) -> LineType:
    try:
        return model.line_types[type_key]
    except KeyError as exc:
        raise PreviewError(f'{model.name}: falta TypLne para type_key={type_key!r}') from exc


def build_preview_layers(model: FeederModel, geography: GeographyManifest) -> PreviewLayers:
    """Ensambla atributos DGS + geometría WGS84 para el mapa interactivo."""
    if not geography.nodes:
        raise PreviewError(f'{model.name}: geography sin nodos (coordenadas ausentes)')
    missing_nodes = set(model.nodes) - set(geography.nodes)
    if missing_nodes:
        sample = ', '.join(sorted(missing_nodes)[:10])
        raise PreviewError(f'{model.name}: nodos sin coordenadas: {sample}')
    missing_lines = {line.section_id for line in model.lines} - set(geography.lines)
    if missing_lines:
        sample = ', '.join(sorted(missing_lines)[:10])
        raise PreviewError(f'{model.name}: tramos sin geometría: {sample}')

    degrees = _degree_map(model)
    nodes = tuple(
        PreviewNode(
            node_id=node_id,
            lat=geography.nodes[node_id].lat,
            lon=geography.nodes[node_id].lon,
            uknom_kv=model.nominal_kv,
            is_source=(node_id == model.source_node),
            degree=degrees.get(node_id, 0),
        )
        for node_id in sorted(model.nodes)
    )

    lines: list[PreviewLine] = []
    for line in sorted(model.lines, key=lambda x: x.section_id):
        typ = _type_or_raise(model, line.type_key)
        gline = geography.lines[line.section_id]
        if len(gline.path) < 2:
            raise PreviewError(f'{model.name}: tramo {line.section_id} con path incompleto')
        path = tuple((p.lon, p.lat) for p in gline.path)
        for lon, lat in path:
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise PreviewError(
                    f'{model.name}: coordenada inválida en {line.section_id} ({lat}, {lon})'
                )
        lines.append(
            PreviewLine(
                section_id=line.section_id,
                from_node=line.from_node,
                to_node=line.to_node,
                length_km=line.length_km,
                length_m=line.length_m,
                overhead=line.overhead,
                type_code=typ.code,
                r1_ohm_km=typ.r1_ohm_km,
                x1_ohm_km=typ.x1_ohm_km,
                r0_ohm_km=typ.r0_ohm_km,
                x0_ohm_km=typ.x0_ohm_km,
                b1_source=typ.b1_source,
                ampacity_a=typ.ampacity_a,
                uknom_kv=model.nominal_kv,
                path=path,
            )
        )

    return PreviewLayers(
        feeder=model.name,
        network_id=model.network_id,
        nominal_kv=model.nominal_kv,
        source_crs=geography.source_crs,
        target_crs=geography.target_crs,
        nodes=nodes,
        lines=tuple(lines),
    )


def layers_to_geojson(layers: PreviewLayers) -> dict[str, Any]:
    """FeatureCollection con nodos (Point) y tramos (LineString) + propiedades DGS."""
    features: list[dict[str, Any]] = []
    for node in layers.nodes:
        features.append(
            {
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [node.lon, node.lat]},
                'properties': {
                    'kind': 'ElmTerm',
                    'name': node.node_id,
                    'uknom_kv': node.uknom_kv,
                    'is_source': node.is_source,
                    'degree': node.degree,
                    'popup': (
                        f'<b>ElmTerm</b> {node.node_id}<br>'
                        f'Unom: {node.uknom_kv:g} kV<br>'
                        f'Fuente: {"sí" if node.is_source else "no"}<br>'
                        f'Grado: {node.degree}'
                    ),
                },
            }
        )
    for line in layers.lines:
        features.append(
            {
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[lon, lat] for lon, lat in line.path],
                },
                'properties': {
                    'kind': 'ElmLne',
                    'name': line.section_id,
                    'bus1': line.from_node,
                    'bus2': line.to_node,
                    'dline_km': line.length_km,
                    'length_m': line.length_m,
                    'typ_lne': line.type_code,
                    'r1_ohm_km': line.r1_ohm_km,
                    'x1_ohm_km': line.x1_ohm_km,
                    'r0_ohm_km': line.r0_ohm_km,
                    'x0_ohm_km': line.x0_ohm_km,
                    'b1': line.b1_source,
                    'In_A': line.ampacity_a,
                    'uknom_kv': line.uknom_kv,
                    'inAir': line.overhead,
                    'popup': (
                        f'<b>ElmLne</b> {line.section_id}<br>'
                        f'bus1→bus2: {line.from_node} → {line.to_node}<br>'
                        f'Unom: {line.uknom_kv:g} kV<br>'
                        f'Longitud: {line.length_km:.6g} km ({line.length_m:.3g} m)<br>'
                        f'TypLne: {line.type_code}<br>'
                        f'{"Aéreo" if line.overhead else "Subterráneo (inAir=0)"}<br>'
                        f'r1/x1: {line.r1_ohm_km:g} / {line.x1_ohm_km:g} Ω/km<br>'
                        f'In: {line.ampacity_a:g} A'
                    ),
                },
            }
        )
    return {
        'type': 'FeatureCollection',
        'properties': {
            'feeder': layers.feeder,
            'network_id': layers.network_id,
            'nominal_kv': layers.nominal_kv,
            'source_crs': layers.source_crs,
            'target_crs': layers.target_crs,
        },
        'features': features,
    }


def to_geodataframes(layers: PreviewLayers):
    """Convierte capas a GeoDataFrames (requiere geopandas)."""
    try:
        import geopandas as gpd
        from shapely.geometry import LineString, Point
    except ImportError as exc:  # pragma: no cover - optional extra
        raise ImportError(
            'geopandas (y shapely) son obligatorios para to_geodataframes. '
            'Instale con: pip install "igea-dgs[preview]"'
        ) from exc

    node_rows = [
        {
            'name': n.node_id,
            'kind': 'ElmTerm',
            'uknom_kv': n.uknom_kv,
            'is_source': n.is_source,
            'degree': n.degree,
            'geometry': Point(n.lon, n.lat),
        }
        for n in layers.nodes
    ]
    line_rows = [
        {
            'name': line.section_id,
            'kind': 'ElmLne',
            'bus1': line.from_node,
            'bus2': line.to_node,
            'dline_km': line.length_km,
            'length_m': line.length_m,
            'typ_lne': line.type_code,
            'r1_ohm_km': line.r1_ohm_km,
            'x1_ohm_km': line.x1_ohm_km,
            'r0_ohm_km': line.r0_ohm_km,
            'x0_ohm_km': line.x0_ohm_km,
            'b1': line.b1_source,
            'In_A': line.ampacity_a,
            'uknom_kv': line.uknom_kv,
            'inAir': line.overhead,
            'geometry': LineString(line.path),
        }
        for line in layers.lines
    ]
    nodes_gdf = gpd.GeoDataFrame(node_rows, crs=layers.target_crs or 'EPSG:4326')
    lines_gdf = gpd.GeoDataFrame(line_rows, crs=layers.target_crs or 'EPSG:4326')
    return nodes_gdf, lines_gdf


def _write_leaflet_html(layers: PreviewLayers, path: Path) -> Path:
    """HTML autónomo con Leaflet CDN (sin leafmap)."""
    geojson = layers_to_geojson(layers)
    lat, lon = layers.center
    payload = json.dumps(geojson, ensure_ascii=False)
    title = f'Preview DGS — {layers.feeder}'
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    html, body, #map {{ height: 100%; margin: 0; }}
    .info {{
      position: absolute; z-index: 1000; top: 10px; left: 50px;
      background: rgba(255,255,255,0.92); padding: 8px 12px; border-radius: 4px;
      font: 13px/1.35 system-ui, sans-serif; box-shadow: 0 1px 4px rgba(0,0,0,.25);
    }}
  </style>
</head>
<body>
  <div class="info"><b>{layers.feeder}</b> · {layers.nominal_kv:g} kV ·
    nodos={len(layers.nodes)} · tramos={len(layers.lines)} · CRS {layers.target_crs}</div>
  <div id="map"></div>
  <script>
    const data = {payload};
    const map = L.map('map').setView([{lat}, {lon}], 14);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap'
    }}).addTo(map);
    const layer = L.geoJSON(data, {{
      style: function (feature) {{
        if (feature.geometry.type === 'LineString') {{
          const ug = feature.properties.inAir === false || feature.properties.inAir === 0;
          return {{
            color: ug ? '#0f172a' : '#1d4ed8',
            weight: ug ? 2 : 3,
            opacity: 0.9
          }};
        }}
        return {{}};
      }},
      pointToLayer: function (feature, latlng) {{
        const src = feature.properties.is_source;
        return L.circleMarker(latlng, {{
          radius: src ? 8 : 5,
          color: src ? '#b45309' : '#0f766e',
          fillColor: src ? '#f59e0b' : '#14b8a6',
          fillOpacity: 0.9,
          weight: 2
        }});
      }},
      onEachFeature: function (feature, lyr) {{
        const html = feature.properties.popup || feature.properties.name || '';
        if (html) lyr.bindPopup(html);
      }}
    }}).addTo(map);
    try {{ map.fitBounds(layer.getBounds(), {{ padding: [24, 24] }}); }} catch (e) {{}}
  </script>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding='utf-8')
    return path


def _write_leafmap_html(layers: PreviewLayers, path: Path) -> Path:
    """Render con leafmap (@opengeos); requiere el extra [preview]."""
    try:
        import leafmap
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            'leafmap es obligatorio para el backend leafmap. '
            'Instale con: pip install "igea-dgs[preview]"'
        ) from exc

    lat, lon = layers.center
    m = leafmap.Map(center=(lat, lon), zoom=14)
    try:
        nodes_gdf, lines_gdf = to_geodataframes(layers)
        if len(lines_gdf):
            m.add_gdf(lines_gdf, layer_name='ElmLne', style={'color': '#1d4ed8', 'weight': 3})
        if len(nodes_gdf):
            m.add_gdf(nodes_gdf, layer_name='ElmTerm')
    except ImportError:
        # leafmap sin geopandas: GeoJSON temporal
        geojson_path = path.with_suffix('.geojson')
        geojson_path.write_text(
            json.dumps(layers_to_geojson(layers), ensure_ascii=False),
            encoding='utf-8',
        )
        m.add_geojson(str(geojson_path), layer_name=layers.feeder)

    path.parent.mkdir(parents=True, exist_ok=True)
    m.to_html(outfile=str(path))
    return path


def write_preview_html(
    model: FeederModel,
    geography: GeographyManifest,
    path: Path | str,
    *,
    backend: str = 'auto',
) -> Path:
    """Escribe el mapa interactivo HTML.

    ``backend``: ``auto`` | ``leafmap`` | ``leaflet``.
    En ``auto`` usa leafmap si está instalado; si no, Leaflet CDN.
    """
    layers = build_preview_layers(model, geography)
    out = Path(path)
    choice = backend.lower().strip()
    if choice == 'auto':
        try:
            import leafmap  # noqa: F401
            choice = 'leafmap'
        except ImportError:
            choice = 'leaflet'

    if choice == 'leafmap':
        return _write_leafmap_html(layers, out)
    if choice == 'leaflet':
        return _write_leaflet_html(layers, out)
    raise ValueError(f'backend de preview desconocido: {backend!r} (use auto|leafmap|leaflet)')


def write_preview_geojson(
    model: FeederModel,
    geography: GeographyManifest,
    path: Path | str,
) -> Path:
    """Sidecar GeoJSON con las mismas propiedades del popup DGS."""
    layers = build_preview_layers(model, geography)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(layers_to_geojson(layers), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return out
