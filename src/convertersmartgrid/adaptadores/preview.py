"""Vista previa georreferenciada del modelo (opengeos / Leaflet).

Construye capas de nodos y tramos a partir de ``FeederModel`` + ``GeographyManifest``
y escribe un HTML interactivo con popups de atributos DGS.

Backends:
1. HTML Leaflet autónomo, con Leaflet dentro del propio fichero (086:RF-21): el de siempre.
2. ``leafmap`` (+ ``geopandas``), solo si se pide por su nombre: su página trae todo de CDN.
"""

from __future__ import annotations

import html as html_std
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .geography import GeographyManifest
from ..dominio.model import FeederModel, LineType
from ..dominio.salidas_red import motivo_apagada, salida_permitida
from ..dominio.util import publicar_duradero, write_json_atomic

CARPETA_LEAFLET = Path(__file__).resolve().parents[1] / 'recursos' / 'leaflet'
#: 086:RF-21: la huella que publica Leaflet para su 1.9.4; la comprueba una prueba.
HUELLAS_LEAFLET = {'leaflet.js': 'sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=',
                   'leaflet.css': 'sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY='}
#: 086:RF-21: los servidores exactos que pide la página, sin comodín: los subdominios que ``L.tileLayer`` pone por defecto
#: en ``{s}`` («a», «b» y «c»).
SUBDOMINIOS_TESELAS = ('a', 'b', 'c')
#: 111:RF-27 (26-11): las calles las sirve la propia web. Cada página generada es aislada («sandbox allow-scripts») y en
#: un Chromium real su tesela salía sin «Referer» aunque pidiera «strict-origin-when-cross-origin»: OpenStreetMap
#: devolvía su imagen «403 Access blocked». La web la pide con el User-Agent del programa, como pide su política de uso,
#: y la guarda; la página la toma de su servidor («'self'»), sin cookie, por eso la ruta va fuera de ``/api/``.
ORIGEN_TESELAS = "'self'"
URL_TESELAS = '/teselas/calles/{z}/{x}/{y}.png'
#: El servidor al que pide la web, y con qué se presenta (sin datos del usuario).
SERVIDOR_TESELAS_OSM = 'https://tile.openstreetmap.org'
AGENTE_TESELAS = 'ConverterSmartGrid/1.0 (planificacion de redes de distribucion)'
#: Zoom más alto de las calles y días que una tesela guardada vale (la política de OSM pide guardarlas).
ZOOM_MAXIMO_CALLES = 19
DIAS_CACHE_TESELAS = 7
#: 086:RF-63: el fondo de satélite, el que pidió el usuario junto a las calles («como en Google Maps», 2026-11-12).
ORIGEN_SATELITE = 'https://server.arcgisonline.com'
URL_SATELITE = f'{ORIGEN_SATELITE}/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'
#: 111:RF-27 (086:RF-63): la web manda «Referrer-Policy: no-referrer» con todo (seguridad.py) y OpenStreetMap contesta a una tesela
#: sin «Referer» con su imagen «403 Access blocked» (política de uso de sus teselas; navegador, 19-11). Cada tesela pide
#: solo el origen de la web, nunca la ruta del espacio ni sus parámetros.
REFERER_TESELAS = 'strict-origin-when-cross-origin'
#: Cada fondo con su nombre en el selector, su dirección, su atribución y cómo se nombra en el aviso si no llega.
#: El primero es el que se ve al abrir. Las atribuciones son las que piden sus licencias (ODbL de OSM; Esri).
#: El último número es el zoom más alto que sirve cada uno: Esri no tiene imágenes de zoom 19 en todas partes
#: (navegador, 2026-11-12: vacías en un alimentador pequeño ajustado a zoom 19); por encima se amplía la de 18.
FONDOS_MAPA = (
    ('Calles', URL_TESELAS, '&copy; OpenStreetMap', 'OpenStreetMap (calles)', 19),
    ('Satélite', URL_SATELITE,
     'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
     'Esri World Imagery (satélite)', 18),
)


@lru_cache(maxsize=2)
def recurso_leaflet(nombre: str) -> str:
    return (CARPETA_LEAFLET / nombre).read_text(encoding='utf-8')


#: 086:RF-63 (18-11, axe dentro del marco del mapa en la e2e F03): lo que Leaflet trae de serie no pasa WCAG 2.2: el
#: enlace de la atribución solo se distinguía por el color (2,55:1 frente al texto) y las casillas del control de capas
#: medían 13 px. Va después de leaflet.css, en cada página que lo incluye.
CSS_LEAFLET_ACCESIBLE = """/* f7-accesible */
    .leaflet-control-attribution a { color: #00557a; text-decoration: underline; }
    .leaflet-control-layers-selector { width: 24px; height: 24px; margin: 0 6px 0 0; vertical-align: middle; }
    .leaflet-control-layers label { display: block; min-height: 24px; margin: 2px 0; }"""


def politica_base() -> str:
    """Solo lo que va dentro del fichero, y las teselas si esa salida está encendida (086:RF-22)."""
    imagenes = f'data: {ORIGEN_TESELAS} {ORIGEN_SATELITE}' if salida_permitida('teselas') else 'data:'
    return (f"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src {imagenes}; "
            "base-uri 'none'; form-action 'none'")


def politica_pagina_generada() -> str:
    """La que sirve la web con cada página generada: aislada, sin origen propio ni cookies.

    Sus textos (nombres de la red, popups) vienen de la entrega. Con ``sandbox`` y sin
    ``connect-src``, un nombre con código dentro corre, pero sin alcance a la API de la web.
    """
    return 'sandbox allow-scripts; ' + politica_base()


class TeselaError(RuntimeError):
    """La tesela no se pudo traer de OpenStreetMap (sin red o rechazada)."""


def descargar_tesela(url: str, cabeceras: dict[str, str]) -> bytes:
    """La tesela de ``url``; se cambia en las pruebas para no salir a la red."""
    import urllib.request

    pedido = urllib.request.Request(url, headers=cabeceras)
    with urllib.request.urlopen(pedido, timeout=20) as r:            # noqa: S310 - servidor fijo, ruta numérica
        return r.read()


def tesela_calles(z: int, x: int, y: int, cache: Path) -> bytes:
    """111:RF-27: la tesela de calles ``z/x/y`` desde la caché o de OpenStreetMap, con el User-Agent del programa.

    Solo números en rango (``ValueError`` si no): la ruta no puede pedir nada más que una tesela.
    """
    import time

    if not (0 <= z <= ZOOM_MAXIMO_CALLES and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise ValueError(f'tesela fuera de rango: {z}/{x}/{y}')
    fichero = Path(cache) / str(z) / str(x) / f'{y}.png'
    if fichero.is_file() and time.time() - fichero.stat().st_mtime < DIAS_CACHE_TESELAS * 86400:
        return fichero.read_bytes()
    try:
        datos = descargar_tesela(f'{SERVIDOR_TESELAS_OSM}/{z}/{x}/{y}.png', {'User-Agent': AGENTE_TESELAS})
    except OSError as exc:
        raise TeselaError(str(exc)) from exc
    fichero.parent.mkdir(parents=True, exist_ok=True)
    temporal = fichero.with_suffix('.tmp')
    temporal.write_bytes(datos)
    temporal.replace(fichero)
    return datos


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
            'Instale con: pip install "convertersmartgrid[preview]"'
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


def guion_de_fondos() -> tuple[str, str]:
    """El guion de los fondos de calles y satélite para un mapa Leaflet con ``map`` ya creado, y el aviso si no hay.

    086:RF-22: sin la salida no se pide ninguna tesela; si está encendida y no hay red, también se dice.
    086:RF-63, RF-64: calles y satélite con su selector, como en Google Maps. Las teselas van en el «tilePane» de
    Leaflet, por debajo del de los tramos y nodos: la red queda siempre encima, con el fondo que se elija. Lo usan la
    vista previa y el mapa de las cargas nuevas (017:RF-124), para que los dos digan y pidan lo mismo.
    """
    if salida_permitida('teselas'):
        fondos = json.dumps([{'nombre': n, 'url': u, 'atribucion': a, 'aviso': s, 'zoom': z}
                             for n, u, a, s, z in FONDOS_MAPA],
                            ensure_ascii=False).replace('<', '\\u003c')
        politica = json.dumps(REFERER_TESELAS)
        return f"""const fondos = {{}};
    const sinFondo = [];
    {fondos}.forEach(function (f, i) {{
      const capa = L.tileLayer(f.url, {{ maxZoom: 19, maxNativeZoom: f.zoom, attribution: f.atribucion,
        referrerPolicy: {politica} }});
      capa.once('tileerror', function () {{
        sinFondo.push(f.aviso);
        const aviso = document.getElementById('sin-fondo');
        aviso.textContent = 'Sin fondo de mapa: no se pudo llegar a ' + sinFondo.join(' ni a ') + '. La red se dibuja igual.';
        aviso.hidden = false;
      }});
      fondos[f.nombre] = capa;
      if (i === 0) capa.addTo(map);
    }});
    L.control.layers(fondos, null, {{ position: 'topright', collapsed: false }}).addTo(map);""", ''
    return '', html_std.escape(f'Sin fondo de mapa. {motivo_apagada("teselas")}')


def _write_leaflet_html(layers: PreviewLayers, path: Path) -> Path:
    """HTML autónomo, con Leaflet dentro: abre igual desde la web, desde el disco y sin red (086:RF-21)."""
    geojson = layers_to_geojson(layers)
    lat, lon = layers.center
    # Un nombre de la entrega con «</script>» cerraba el guion y lo que siguiera se ejecutaba.
    payload = json.dumps(geojson, ensure_ascii=False).replace('<', '\\u003c')
    feeder = html_std.escape(str(layers.feeder))
    title = f'Preview DGS — {feeder}'
    teselas, aviso_fondo = guion_de_fondos()
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta http-equiv="Content-Security-Policy" content="{politica_base()}"/>
  <title>{title}</title>
  <style>
{recurso_leaflet('leaflet.css')}
  </style>
  <script>
{recurso_leaflet('leaflet.js')}
  </script>
  <style>
{CSS_LEAFLET_ACCESIBLE}
    html, body, #map {{ height: 100%; margin: 0; }}
    .info {{
      position: absolute; z-index: 1000; top: 10px; left: 50px;
      background: rgba(255,255,255,0.92); padding: 8px 12px; border-radius: 4px;
      font: 13px/1.35 system-ui, sans-serif; box-shadow: 0 1px 4px rgba(0,0,0,.25);
    }}
    #sin-fondo {{ display: block; margin-top: 4px; color: #92400e; }}
    #sin-fondo[hidden] {{ display: none; }}
  </style>
</head>
<body>
  <div class="info"><b>{feeder}</b> · {layers.nominal_kv:g} kV ·
    nodos={len(layers.nodes)} · tramos={len(layers.lines)} · CRS {html_std.escape(str(layers.target_crs))}
    <span id="sin-fondo"{'' if aviso_fondo else ' hidden'}>{aviso_fondo}</span></div>
  <div id="map"></div>
  <script>
    const data = {payload};
    const map = L.map('map').setView([{lat}, {lon}], 14);
    {teselas}
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
            'Instale con: pip install "convertersmartgrid[preview]"'
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
        publicar_duradero(geojson_path, json.dumps(layers_to_geojson(layers), ensure_ascii=False))   # 001:RF-5
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
    ``auto`` es Leaflet propio: con leafmap instalado, la página salía a CDN de terceros y sin
    red quedaba en blanco (086:RF-21). leafmap solo si se pide por su nombre.
    """
    layers = build_preview_layers(model, geography)
    out = Path(path)
    choice = backend.lower().strip()
    if choice == 'auto':
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
    write_json_atomic(out, layers_to_geojson(layers))
    return out
