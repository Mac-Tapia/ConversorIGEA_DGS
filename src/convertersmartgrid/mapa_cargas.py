"""El mapa de las cargas nuevas, su punto de diseño corregido en DIgSILENT y el fondo de la imagen del informe.

Usuario, 2026-11-13: «en la web se debe ver la ubicación en Google Maps o similar de dónde se conectó y la
ubicación de la carga nueva o de los bloques, y eso debe ir en el informe»; y «debe haber un botón para actualizar
la imagen de la ubicación y el punto de fijación de diseño cuando el usuario verificó en DIgSILENT, corrigió o
asignó otro punto».

- 017:RF-109, RF-124: :func:`datos_del_mapa` y :func:`pagina_del_mapa` dibujan cada carga nueva aplicada (sola o en
  bloque) en su punto, el nodo donde se conectó, la línea de enlace y la red del alimentador, con la geografía que
  guardó el último flujo de «Con proyecto». Sin DIgSILENT: se lee del espacio.
- 017:RF-124: :func:`comparar` dice qué cambió entre lo guardado y lo que leyó ``tools/ubicacion_cargas_pf.py`` en
  el proyecto; :func:`guardar_puntos` deja el punto que el operador eligió, y :func:`aplicar_puntos` lo pone en las
  cargas aplicadas para que la imagen, el mapa y el informe lo usen desde entonces.
- 017:RF-111, RF-112: :class:`ProveedorTeselas` trae las teselas de calles o satélite del mismo origen que la vista
  previa (086:RF-63), solo con la salida ``teselas`` encendida (086:RF-22), y las guarda en el espacio; sin red, sin
  fondo y con aviso, nunca un error.

Universal (constitución P13): las coordenadas UTM salen del CRS del perfil de empresa; sin él, solo el GPS.
"""
from __future__ import annotations

import html as html_std
import json
import re
import time
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from .dominio.numeros_medidos import clave_codigo
from .salidas_red import motivo_apagada, salida_permitida
from .util import nombre_seguro, write_json_atomic

#: Dentro del espacio de trabajo: un fichero por proyecto con los puntos de diseño confirmados.
CARPETA_PUNTOS = 'puntos_de_diseno'
#: Dentro del espacio de trabajo: las teselas ya traídas, por fondo y zoom.
CARPETA_TESELAS = 'cache_teselas'
#: Por debajo de esto, un punto no se ha movido: el GPS de DIgSILENT se guarda con 7 decimales (~1 cm), pero las
#: copias entre el plan, el informe y el flujo redondean distinto.
TOLERANCIA_M = 1.0
#: El largo de una línea de enlace que cambia menos que esto, no ha cambiado.
TOLERANCIA_KM = 0.001


def _nombre_pf(texto: str) -> str:
    """Como ``tools/cargas_pf.nombre_pf``: el nombre que DIgSILENT da a la SED, su nodo y su enlace."""
    return re.sub(r'[^A-Za-z0-9_\-]', '_', texto)[:40]


def clave(alimentador: Any, sed: Any) -> str:
    """La carga por su alimentador y su SED, comparables entre el plan, el informe y DIgSILENT."""
    return f'{clave_codigo(alimentador)}|{clave_codigo(sed)}'


def distancia_m(a: Iterable[float] | None, b: Iterable[float] | None) -> float | None:
    """Haversine entre dos (lat, lon); ``None`` si falta alguno."""
    from .vias import distancia_m as haversine

    if not a or not b:
        return None
    a, b = list(a), list(b)
    if a[0] is None or b[0] is None:
        return None
    return haversine((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))


# --------------------------------------------------------------------------- puntos de diseño (017:RF-124)
def ruta_puntos(raiz: Path, project: str) -> Path:
    return Path(raiz) / CARPETA_PUNTOS / f'{nombre_seguro(project.strip())}.json'


def leer_puntos(raiz: Path, project: str) -> dict[str, dict]:
    """Los puntos de diseño confirmados del proyecto, por :func:`clave`. Un fichero dañado no tumba el informe."""
    ruta = ruta_puntos(raiz, project)
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8')) if ruta.is_file() else {}
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in (datos.get('puntos') or {}).items() if isinstance(v, dict)}


def guardar_puntos(raiz: Path, project: str, filas: Iterable[Mapping[str, Any]], *, lectura: str = '') -> list[dict]:
    """Guarda el punto de diseño de cada fila (lo leído en DIgSILENT) y devuelve lo guardado.

    Cada fila es una de ``cargas`` del informe de ``tools/ubicacion_cargas_pf.py``, con ``nodo`` y, si la hay, la
    línea de enlace. Solo lo leído del proyecto: el navegador elige qué filas, no manda coordenadas.
    """
    puntos = leer_puntos(raiz, project)
    guardados = []
    cuando = time.strftime('%Y-%m-%d %H:%M:%S')
    for f in filas:
        nodo = f.get('nodo') or {}
        if not nodo.get('nombre'):
            continue
        enlace = f.get('enlace') or None
        punto = {'sed': f.get('sed'), 'alimentador': f.get('alimentador'), 'variacion': f.get('variacion'),
                 'barra': nodo['nombre'], 'nodo_gps': nodo.get('gps'), 'punto': f.get('punto'),
                 'enlace': ({'nombre': enlace.get('nombre'), 'km': enlace.get('km'), 'gps': enlace.get('gps') or []}
                            if enlace else None),
                 'confirmado': cuando, 'epoca': time.time(), 'lectura': lectura, 'origen': 'digsilent'}
        puntos[clave(f.get('alimentador'), f.get('sed'))] = punto
        guardados.append(punto)
    ruta = ruta_puntos(raiz, project)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(ruta, {'project': project.strip(), 'puntos': puntos})
    return guardados


def aplicar_puntos(raiz: Path, project: str, cargas: list[dict]) -> list[dict]:
    """Las cargas aplicadas con el punto de diseño confirmado en DIgSILENT, si lo hay (017:RF-124).

    La barra pasa a ser el nodo leído, y ``nodo_gps`` lleva su GPS por si el último flujo aún no lo tiene; la de la
    aplicación se queda en ``barra_aplicada``. Lo que no tiene punto confirmado, como estaba.
    """
    puntos = leer_puntos(raiz, project)
    if not puntos:
        return cargas
    out = []
    for c in cargas:
        p = puntos.get(clave(c.get('alimentador'), c.get('sed')))
        # Dos veces no cambia nada: la web la aplica en ``_cargas_nuevas_aplicadas`` y el mapa también.
        if not p or c.get('punto_de_diseno'):
            out.append(c)
            continue
        nuevo = {**c, 'barra_aplicada': c.get('barra'), 'barra': p['barra'], 'nodo_gps': p.get('nodo_gps'),
                 'punto_de_diseno': p}
        if p.get('punto'):
            nuevo['lat'], nuevo['lon'] = p['punto'][0], p['punto'][1]
        if p.get('enlace') and p['enlace'].get('km') is not None:
            nuevo['distancia_m'] = float(p['enlace']['km']) * 1000.0
        out.append(nuevo)
    return out


# --------------------------------------------------------------------------- diferencias (017:RF-124)
#: Lo que la carga dada de alta dice de dónde sale, en su plan y en su informe de aplicación.
ORIGEN_ALTA = 'leída en DIgSILENT'


def registros_de_alta(project: str, filas: Iterable[Mapping[str, Any]], token: str) -> tuple[dict, dict]:
    """(plan, informe de aplicación) de las cargas que solo están en DIgSILENT, para darlas de alta (017:RF-124).

    Usuario (2026-11-13): SECA0001 estaba en DIgSILENT (aplicada desde otro espacio) y la web no la tenía como aplicada;
    su informe de factibilidad decía «no es una carga nueva aplicada». Se da de alta como carga sola, con lo que DIgSILENT
    guarda de ella: su punto, su nodo, su enlace y su potencia. Tienen la misma forma que los de «Aplicar», para que la
    lean igual el informe, el mapa y el diagnóstico; nada se escribe en DIgSILENT.
    """
    nuevas, cargas = [], []
    for f in filas:
        if not f.get('solo_en_digsilent') or not f.get('nodo') or f.get('kw') is None:
            raise ValueError(f"{f.get('sed')}: solo se da de alta una carga que está en DIgSILENT con su nodo y su potencia.")
        punto = f.get('punto') or [None, None]
        nuevas.append({'sed': f['sed'], 'hoja': 'formulario', 'alimentador': f.get('alimentador'),
                       'lat': punto[0], 'lon': punto[1], 'kw': float(f['kw']), 'kvar': float(f.get('kvar') or 0.0),
                       'kva_instalado': None, 'descripcion': str(f['sed']), 'origen': ORIGEN_ALTA})
        enlace = f.get('enlace') or {}
        cargas.append({'sed': f['sed'], 'alimentador': f.get('alimentador'), 'barra': f['nodo'].get('nombre'),
                       'variacion': f.get('variacion'), 'criterio': ORIGEN_ALTA,
                       'distancia_m': round(float(enlace['km']) * 1000.0, 1) if enlace.get('km') is not None else None})
    plan = {'project': project.strip(), 'nuevas': nuevas, 'origen': ORIGEN_ALTA, 'token': token}
    aplicacion = {'project': project.strip(), 'modo': 'aplicar', 'cargas': cargas, 'feeders': [],
                  'origen': ORIGEN_ALTA, 'avisos': []}
    return plan, aplicacion


def comparar(guardadas: list[dict], leidas: list[dict]) -> list[dict]:
    """Por carga, qué cambió en DIgSILENT frente a lo que guarda la web.

    ``estado``: ``igual``, ``cambiada``, ``solo_en_digsilent`` (una variación ``Carga_…`` activa que la web no
    tiene) o ``no_leida`` (la web la tiene y en DIgSILENT no está o no se pudo leer). ``cambios``: textos para el
    operador, en el orden nodo, enlace, punto.
    """
    por_clave = {clave(c.get('alimentador'), c.get('sed')): c for c in guardadas}
    vistas = set()
    out = []
    for l in leidas:
        k = clave(l.get('alimentador'), l.get('sed'))
        g = por_clave.get(k)
        vistas.add(k)
        fila = {'sed': l.get('sed'), 'alimentador': l.get('alimentador'), 'variacion': l.get('variacion'),
                'guardado': None, 'leido': None, 'cambios': [], 'error': l.get('error')}
        if l.get('nodo'):
            fila['leido'] = {'barra': l['nodo'].get('nombre'), 'nodo_gps': l['nodo'].get('gps'),
                             'punto': l.get('punto'), 'enlace': l.get('enlace'), 'kw': l.get('kw')}
        if g is not None:
            fila['guardado'] = {'barra': g.get('barra'), 'nodo_gps': g.get('nodo_gps'),
                                'punto': [g['lat'], g['lon']] if g.get('lat') is not None else None,
                                'distancia_m': g.get('distancia_m'), 'kw': g.get('kw')}
        if l.get('error') or not l.get('nodo'):
            fila['estado'] = 'no_leida' if g is not None else 'solo_en_digsilent'
            out.append(fila)
            continue
        if g is None:
            fila['estado'] = 'solo_en_digsilent'
            fila['cambios'].append('no está entre las cargas aplicadas desde esta web')
            out.append(fila)
            continue
        leido, guardado = fila['leido'], fila['guardado']
        if str(leido['barra']) != str(guardado['barra']):
            fila['cambios'].append(f"nodo de conexión {guardado['barra']} → {leido['barra']}")
        km_leido = (leido.get('enlace') or {}).get('km')
        km_guardado = None if guardado.get('distancia_m') is None else float(guardado['distancia_m']) / 1000.0
        if (leido.get('enlace') is None) != (km_guardado is None or km_guardado < TOLERANCIA_KM):
            fila['cambios'].append('con línea de enlace' if leido.get('enlace') else 'sin línea de enlace')
        elif km_leido is not None and km_guardado is not None and abs(km_leido - km_guardado) > TOLERANCIA_KM:
            fila['cambios'].append(f'enlace de {km_guardado:.3f} km → {km_leido:.3f} km')
        movido = distancia_m(guardado.get('punto'), leido.get('punto'))
        if movido is not None and movido > TOLERANCIA_M:
            fila['cambios'].append(f'punto de la carga movido {movido:.0f} m')
        fila['estado'] = 'cambiada' if fila['cambios'] else 'igual'
        out.append(fila)
    for k, g in por_clave.items():
        if k not in vistas:
            out.append({'sed': g.get('sed'), 'alimentador': g.get('alimentador'), 'variacion': g.get('variacion'),
                        'estado': 'no_leida', 'guardado': {'barra': g.get('barra')}, 'leido': None,
                        'cambios': [], 'error': 'no se leyó en DIgSILENT'})
    return out


# --------------------------------------------------------------------------- datos del mapa (017:RF-109, RF-124)
def _gps_de_barra(geo: Mapping[str, Any], nombre: str) -> list[float] | None:
    for b in geo.get('barras') or []:
        if b[0] == nombre and b[1] is not None and b[2] is not None:
            return [float(b[1]), float(b[2])]
    return None


def datos_del_mapa(project: str, cargas: list[dict], geos: Mapping[str, Mapping[str, Any]], *,
                   utm: Callable[[Any], Any], flujo_epoca: Mapping[str, float] | None = None,
                   alimentadores: Iterable[str] = ()) -> dict:
    """Lo que dibuja el mapa de la web: la red de cada alimentador y cada carga nueva con su nodo y su enlace.

    ``cargas``: las aplicadas, ya con :func:`aplicar_puntos`. ``geos``: la geografía del último flujo de «Con
    proyecto» por alimentador. ``utm``: (lat, lon) → [este, norte] en el CRS del perfil, o ``None`` (P13).
    ``flujo_epoca``: cuándo se guardó ese flujo, por alimentador; un punto confirmado después pide repetir 4.2.
    """
    pedidos = [a for a in alimentadores if a]
    feeders = sorted({*pedidos, *(str(c.get('alimentador')) for c in cargas if c.get('alimentador'))})
    avisos: list[str] = []
    red = {}
    for f in feeders:
        geo = geos.get(f) or {}
        if not geo:
            avisos.append(f'{f}: no hay un flujo de «Con proyecto» con su geografía; ejecútelo en 4.2 para ver su red.')
            continue
        red[f] = {'tramos': [[t[0], t[1]] for t in geo.get('tramos') or [] if len(t[1] or []) >= 2],
                  'cabecera': _gps_de_barra(geo, str(geo.get('cabecera') or ''))}
    filas = []
    repetir = set()
    for c in cargas:
        f = str(c.get('alimentador') or '')
        if pedidos and f not in pedidos:
            continue
        geo = geos.get(f) or {}
        sed = str(c.get('sed') or '')
        punto = [float(c['lat']), float(c['lon'])] if c.get('lat') is not None and c.get('lon') is not None else None
        gps_nodo = _gps_de_barra(geo, str(c.get('barra') or '')) or c.get('nodo_gps')
        p = c.get('punto_de_diseno') or {}
        enlace = None
        tramo = next((t for t in geo.get('tramos') or [] if t[0] == _nombre_pf(f'LNE_{sed}')), None)
        if p.get('enlace'):
            enlace = {'nombre': p['enlace'].get('nombre'), 'km': p['enlace'].get('km'),
                      'coords': p['enlace'].get('gps') or ([gps_nodo, punto] if gps_nodo and punto else [])}
        elif tramo is not None and not p:
            enlace = {'nombre': tramo[0], 'km': tramo[6] if len(tramo) > 6 else None, 'coords': tramo[1]}
        elif gps_nodo and punto and distancia_m(gps_nodo, punto) and distancia_m(gps_nodo, punto) > TOLERANCIA_M:
            km = c.get('distancia_m')
            enlace = {'nombre': None, 'km': None if km is None else float(km) / 1000.0, 'coords': [gps_nodo, punto]}
        if p and (p.get('epoca') or 0) > (flujo_epoca or {}).get(f, 0.0):
            repetir.add(f)
        filas.append({
            'sed': sed, 'alimentador': f, 'kw': c.get('kw'), 'sola': bool(c.get('sola')),
            'variacion': c.get('variacion'),
            'punto': {'lat': punto[0], 'lon': punto[1], 'utm': utm(punto)} if punto else None,
            'nodo': {'nombre': c.get('barra'), 'lat': gps_nodo[0] if gps_nodo else None,
                     'lon': gps_nodo[1] if gps_nodo else None, 'utm': utm(gps_nodo) if gps_nodo else None},
            'enlace': enlace, 'corregida': bool(p), 'barra_aplicada': c.get('barra_aplicada'),
            'confirmado': p.get('confirmado'),
        })
        if not gps_nodo and not punto:
            avisos.append(f'{sed}: ni su punto ni su nodo {c.get("barra")} tienen GPS; no sale en el mapa.')
    if repetir:
        avisos.append('Hay puntos de diseño corregidos después del último flujo de «Con proyecto» de '
                      f'{", ".join(sorted(repetir))}: repita los flujos de 4.2 para que el informe los mida.')
    return {'project': project, 'alimentadores': red, 'cargas': filas, 'repetir_flujos': sorted(repetir),
            'fondo': {'encendido': salida_permitida('teselas'),
                      'motivo': '' if salida_permitida('teselas') else motivo_apagada('teselas')},
            'avisos': avisos}


def pagina_del_mapa(datos: Mapping[str, Any]) -> str:
    """El HTML del mapa, con Leaflet dentro, como la vista previa (086:RF-21, RF-63 a RF-65).

    La web lo muestra en un marco aislado (``politica_pagina_generada``): los nombres vienen de la entrega y de
    DIgSILENT, así que se escapan y el guion no alcanza la API.
    """
    from .preview import _politica_base, _recurso_leaflet, guion_de_fondos

    carga = json.dumps(datos, ensure_ascii=False, default=str).replace('<', '\\u003c')
    teselas, aviso = guion_de_fondos()
    titulo = html_std.escape(f"Cargas nuevas · {datos.get('project') or ''}")
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta http-equiv="Content-Security-Policy" content="{_politica_base()}"/>
  <title>{titulo}</title>
  <style>
{_recurso_leaflet('leaflet.css')}
  </style>
  <script>
{_recurso_leaflet('leaflet.js')}
  </script>
  <style>
    html, body, #map {{ height: 100%; margin: 0; }}
    .info {{ position: absolute; z-index: 1000; bottom: 18px; left: 10px; max-width: 60%;
      background: rgba(255,255,255,0.92); padding: 6px 10px; border-radius: 4px;
      font: 12px/1.35 system-ui, sans-serif; box-shadow: 0 1px 4px rgba(0,0,0,.25); }}
    #sin-fondo {{ display: block; color: #92400e; }}
    #sin-fondo[hidden] {{ display: none; }}
    .rotulo {{ font: 600 12px system-ui, sans-serif; color: #b91c1c; background: rgba(255,255,255,.85);
      border: 0; box-shadow: none; padding: 1px 4px; }}
  </style>
</head>
<body>
  <div class="info"><b>{titulo}</b>
    <span>Rombo rojo: carga nueva · círculo azul: nodo de conexión · discontinua: línea de enlace</span>
    <span id="sin-fondo"{'' if aviso else ' hidden'}>{aviso}</span></div>
  <div id="map"></div>
  <script>
    const datos = {carga};
    const map = L.map('map');
    {teselas}
    const colores = ['#1d4ed8', '#15803d', '#c2410c', '#7e22ce', '#0e7490', '#a16207', '#be185d', '#525252'];
    const capas = [];
    const texto = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}})[c]);
    Object.keys(datos.alimentadores).sort().forEach(function (f, i) {{
      const red = datos.alimentadores[f];
      red.tramos.forEach(function (t) {{
        capas.push(L.polyline(t[1], {{ color: colores[i % colores.length], weight: 2, opacity: 0.85 }})
          .bindPopup(texto(f) + ' · ' + texto(t[0])).addTo(map));
      }});
      if (red.cabecera) capas.push(L.circleMarker(red.cabecera, {{ radius: 7, color: '#b45309', fillColor: '#f59e0b',
        fillOpacity: 0.9 }}).bindTooltip(texto(f), {{ permanent: true, direction: 'right' }}).addTo(map));
    }});
    datos.cargas.forEach(function (c) {{
      const nodo = c.nodo && c.nodo.lat != null ? [c.nodo.lat, c.nodo.lon] : null;
      const punto = c.punto ? [c.punto.lat, c.punto.lon] : null;
      const kw = c.kw == null ? '' : ' · ' + Number(c.kw).toLocaleString('es-PE') + ' kW';
      if (c.enlace && c.enlace.coords && c.enlace.coords.length >= 2) capas.push(L.polyline(c.enlace.coords,
        {{ color: '#dc2626', weight: 3, dashArray: '6 5' }}).bindPopup('Enlace ' + texto(c.enlace.nombre || '')
        + (c.enlace.km == null ? '' : ' · ' + Number(c.enlace.km).toFixed(3) + ' km')).addTo(map));
      if (nodo) capas.push(L.circleMarker(nodo, {{ radius: 6, color: '#1e3a8a', fillColor: '#3b82f6', fillOpacity: 1 }})
        .bindPopup('Nodo de conexión ' + texto(c.nodo.nombre) + (c.corregida ? ' (corregido en DIgSILENT)' : ''))
        .addTo(map));
      const donde = punto || nodo;
      if (donde) {{
        const rombo = L.divIcon({{ className: '', iconSize: [16, 16], iconAnchor: [8, 8],
          html: '<div style="width:12px;height:12px;background:#dc2626;border:1px solid #000;transform:rotate(45deg)"></div>' }});
        capas.push(L.marker(donde, {{ icon: rombo }})
          .bindTooltip(texto(c.sed) + kw + (c.sola ? '' : ' · en bloque'), {{ permanent: true, direction: 'top',
            className: 'rotulo', offset: [0, -8] }}).addTo(map));
      }}
    }});
    const grupo = L.featureGroup(capas);
    try {{ map.fitBounds(grupo.getBounds(), {{ padding: [28, 28], maxZoom: 17 }}); }} catch (e) {{ map.setView([0, 0], 2); }}
  </script>
</body>
</html>
"""


# --------------------------------------------------------------------------- fondo de la imagen (017:RF-111)
class ProveedorTeselas:
    """Teselas de un fondo de la vista previa (086:RF-63), con caché en disco del espacio de trabajo.

    Solo se pide al mismo origen que ya pide el navegador para la vista previa, y solo con la salida ``teselas``
    encendida. Nunca lanza: una tesela que no llega es ``None`` y la imagen se dibuja con lo que haya (RF-112).
    """

    def __init__(self, nombre: str, url: str, atribucion: str, zoom_max: int, cache: Path | None, *,
                 pedir: Callable[[str, float], bytes] | None = None, tiempo_s: float = 8.0):
        self.nombre, self.url, self.atribucion, self.zoom_max = nombre, url, atribucion, zoom_max
        self.cache, self.tiempo_s = cache, tiempo_s
        self._pedir = pedir or _pedir
        self.fallos: list[str] = []
        #: Tras el primer fallo de red no se insiste: 25 teselas con 8 s cada una serían 3 minutos sin red.
        self._sin_red = False

    def tesela(self, z: int, x: int, y: int) -> bytes | None:
        ruta = self.cache / str(z) / str(x) / f'{y}.png' if self.cache is not None else None
        if ruta is not None and ruta.is_file():
            try:
                return ruta.read_bytes()
            except OSError:
                pass
        if self._sin_red or not salida_permitida('teselas'):                       # 086:RF-22
            return None
        url = self.url.replace('{s}', 'a').replace('{z}', str(z)).replace('{x}', str(x)).replace('{y}', str(y))
        try:
            datos = self._pedir(url, self.tiempo_s)
        except Exception as exc:  # noqa: BLE001 - sin red, sin fondo (017:RF-112); nunca un error del informe
            self._sin_red = True
            self.fallos.append(f'{type(exc).__name__}: {exc}')
            return None
        if ruta is not None and datos:
            try:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_bytes(datos)
            except OSError:
                pass
        return datos


def _pedir(url: str, tiempo_s: float) -> bytes:
    # Nombre genérico del programa: las políticas de OSM piden identificarse, sin datos de quien lo usa.
    pedido = urllib.request.Request(url, headers={'User-Agent': 'ConverterSmartGrid (imagen de ubicacion)'})
    with urllib.request.urlopen(pedido, timeout=tiempo_s) as r:  # noqa: S310 - origen fijo de la vista previa
        return r.read()


#: Los fondos que admite la imagen, por su nombre en la web: los mismos de la vista previa (086:RF-63).
FONDOS = ('calles', 'satelite')


def fondo_del_informe(raiz: Path | None, cual: str = 'calles', *,
                      pedir: Callable[[str, float], bytes] | None = None) -> tuple[ProveedorTeselas | None, str]:
    """El proveedor de teselas para la imagen de ubicación, o ``None`` y por qué (lo dice el pie, 017:RF-112)."""
    from .preview import FONDOS_MAPA

    if cual not in FONDOS:
        raise ValueError(f'Fondo de mapa desconocido: {cual!r} (calles o satelite).')
    if not salida_permitida('teselas'):
        return None, motivo_apagada('teselas')
    nombre, url, atribucion, aviso, zoom = FONDOS_MAPA[FONDOS.index(cual)]
    del nombre
    texto = re.sub(r'<[^>]+>', '', atribucion).replace('&copy;', '©').replace('&mdash;', '—')
    cache = Path(raiz) / CARPETA_TESELAS / cual if raiz is not None else None
    return ProveedorTeselas(aviso, url, texto, int(zoom), cache, pedir=pedir), ''

