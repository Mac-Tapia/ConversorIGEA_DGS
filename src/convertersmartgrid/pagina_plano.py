"""La página del plano de la red (spec 111), generada por el servidor con el Leaflet propio.

- Lienzo (``preferCanvas``) y capas por vista: tramos, barras, SED, maniobras y resultados, cada una encendible
  (111:RF-1, RF-10). Los vértices son los de la fuente, enteros; el nivel de detalle solo cambia el dibujo
  (``smoothFactor`` según el zoom) y vuelve al acercarse (RF-1).
- Cada trazo lleva el código de la fuente; al seleccionarlo, la página se lo dice a la pestaña (RF-2).
- La leyenda dice la magnitud, la unidad, el umbral, el caso y el motor; un incumplimiento lleva icono y texto además
  del color, y cada resultado pintado dice qué motor lo calculó (RF-10, RF-13, RF-18).
- Tokens claro y oscuro con ``prefers-color-scheme`` (RF-14).
- Sin la salida «teselas», ningún fondo: el plano se dibuja igual y lo dice (086:RF-22, RF-65).
- Aislada como toda página generada (``preview.politica_pagina_generada``, 086:RF-21): los datos van en un bloque JSON
  escapado, nunca en el guion, y la página solo habla con la pestaña por ``postMessage`` con un esquema cerrado:
  acepta del padre :data:`MENSAJES_ENTRADA` y le manda :data:`MENSAJES_SALIDA` (RF-14). Envía solo a
  ``window.location.origin`` (la web que la sirve, que es la del padre) y solo atiende lo que llega del padre con ese
  origen. Como el marco no tiene ``allow-same-origin``, su origen es opaco: la pestaña recibe ``event.origin ===
  'null'`` y lo comprueba junto con ``contentWindow``. No pide nada a la red salvo las teselas, si su salida está
  encendida.
"""
from __future__ import annotations

import html as html_std
import json
from collections.abc import Mapping, Sequence
from typing import Any

#: Lo que la pestaña puede pedir a la página: seleccionar o resaltar un código, encender o apagar una capa y mostrar
#: una propuesta de ajuste (punto y nodo). Cualquier otro mensaje se ignora.
MENSAJES_ENTRADA = ('seleccionar', 'resaltar', 'capa', 'propuesta')
#: Lo que la página manda a la pestaña: que ya está lista, y el elemento que el operador seleccionó en el plano.
MENSAJES_SALIDA = ('listo', 'seleccionado')
#: Las capas por vista, con su nombre en el selector.
CAPAS = (('tramos', 'Tramos'), ('barras', 'Barras'), ('sed', 'SED'), ('maniobras', 'Maniobras'),
         ('resultados', 'Resultados'))
#: Nivel de detalle solo gráfico: desde ese zoom hacia abajo, ese ``smoothFactor`` de Leaflet. Acercarse lo devuelve
#: a 0 (todos los vértices dibujados); los datos no cambian nunca.
DETALLE_POR_ZOOM = ((17, 0.0), (15, 1.0), (13, 2.0), (0, 4.0))


def _json(valor: Any) -> str:
    """JSON que no puede cerrar el bloque que lo contiene: ``<`` y ``>`` van escapados."""
    return (json.dumps(valor, ensure_ascii=False, default=str)
            .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))


def _fondo() -> tuple[str, str]:
    """El guion de los fondos y el aviso: sin la salida de teselas, ninguno, y se dice en una frase."""
    from .preview import guion_de_fondos
    from .salidas_red import salida_permitida

    if salida_permitida('teselas'):
        return guion_de_fondos()[0], ''
    return '', 'Sin mapa base: la salida de teselas está apagada. La red se dibuja igual.'


# 111:RF-14: la página va aislada y su política no deja cargar images/layers.png de leaflet.css; el botón del control
# de capas plegado salía invisible, así que su icono va en la página como data: (prueba: test_pagina_plano).
def pagina(vistas: Sequence[Mapping[str, Any]], *, capas: Mapping[str, Any] | None = None,
           titulo: str = 'Plano de la red') -> str:
    """El HTML del plano de esas vistas (``plano_red.vista``) y, si se dan, las capas de un resultado pintable."""
    from .preview import politica_base, recurso_leaflet

    datos = {'vistas': list(vistas), 'capas': dict(capas) if capas and capas.get('pintable') else None}
    teselas, aviso = _fondo()
    nombre = html_std.escape(titulo)
    capas_js = _json([{'clave': c, 'nombre': n} for c, n in CAPAS])
    detalle_js = _json([list(x) for x in DETALLE_POR_ZOOM])
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta http-equiv="Content-Security-Policy" content="{politica_base()}"/>
  <title>{nombre}</title>
  <style>
{recurso_leaflet('leaflet.css')}
  </style>
  <script>
{recurso_leaflet('leaflet.js')}
  </script>
  <style>
    /* Icono del control de capas en línea: la política de la página no deja cargar images/layers.png. */
    .leaflet-control-layers-toggle {{ background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 26 26'%3E%3Cg fill='none' stroke='%230f172a' stroke-width='2' stroke-linejoin='round'%3E%3Cpath d='M13 4 23 9 13 14 3 9Z' fill='%23e2e8f0'/%3E%3Cpath d='M3 13l10 5 10-5'/%3E%3Cpath d='M3 17l10 5 10-5'/%3E%3C/g%3E%3C/svg%3E"); background-size: 26px 26px; }}
    .leaflet-retina .leaflet-control-layers-toggle {{ background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 26 26'%3E%3Cg fill='none' stroke='%230f172a' stroke-width='2' stroke-linejoin='round'%3E%3Cpath d='M13 4 23 9 13 14 3 9Z' fill='%23e2e8f0'/%3E%3Cpath d='M3 13l10 5 10-5'/%3E%3Cpath d='M3 17l10 5 10-5'/%3E%3C/g%3E%3C/svg%3E"); }}
    :root {{ --plano-fondo: #f8fafc; --plano-texto: #0f172a; --plano-panel: rgba(255,255,255,.94);
      --plano-tramo: #1d4ed8; --plano-barra: #0f766e; --plano-sed: #7c3aed; --plano-abierto: #b91c1c;
      --plano-cerrado: #15803d; --plano-resalte: #f59e0b; --plano-normal: #15803d; --plano-alerta: #b91c1c;
      --plano-borde: #334155; }}
    @media (prefers-color-scheme: dark) {{
      :root {{ --plano-fondo: #0b1220; --plano-texto: #e2e8f0; --plano-panel: rgba(15,23,42,.94);
        --plano-tramo: #60a5fa; --plano-barra: #2dd4bf; --plano-sed: #c4b5fd; --plano-abierto: #f87171;
        --plano-cerrado: #4ade80; --plano-resalte: #fbbf24; --plano-normal: #4ade80; --plano-alerta: #f87171;
        --plano-borde: #94a3b8; }}
    }}
    html, body, #mapa {{ height: 100%; margin: 0; background: var(--plano-fondo); color: var(--plano-texto); }}
    .panel {{ position: absolute; z-index: 1000; left: 10px; bottom: 18px; max-width: min(60%, 420px);
      background: var(--plano-panel); color: var(--plano-texto); padding: 6px 10px; border-radius: 4px;
      font: 13px/1.4 system-ui, sans-serif; box-shadow: 0 1px 4px rgba(0,0,0,.3); }}
    .panel[hidden] {{ display: none; }}
    #aviso {{ position: absolute; z-index: 1000; top: 10px; left: 50px; }}
    .icono-incumple {{ width: 16px; height: 16px; line-height: 16px; text-align: center; border-radius: 50%;
      background: var(--plano-alerta); color: #fff; font: 700 12px system-ui, sans-serif;
      border: 1px solid var(--plano-borde); }}
    .leaflet-container:focus-visible {{ outline: 3px solid var(--plano-resalte); outline-offset: -3px; }}
  </style>
</head>
<body>
  <div id="mapa" role="application" aria-label="{nombre}"></div>
  <div id="aviso" class="panel" role="status"{'' if aviso else ' hidden'}>{html_std.escape(aviso)}</div>
  <div id="leyenda" class="panel" aria-live="polite" hidden></div>
  <script type="application/json" id="datos-plano">{_json(datos)}</script>
  <script>
    const ENTRADA = {_json(list(MENSAJES_ENTRADA))};
    const CAPAS = {capas_js};
    const DETALLE = {detalle_js};
    const datos = JSON.parse(document.getElementById('datos-plano').textContent);
    const css = getComputedStyle(document.documentElement);
    const token = (n) => css.getPropertyValue('--plano-' + n).trim();
    const texto = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}})[c]);
    const map = L.map('mapa', {{ preferCanvas: true, keyboard: true, zoomControl: true }});
    {teselas}
    const grupos = {{}};
    CAPAS.forEach(function (c) {{ grupos[c.clave] = L.layerGroup().addTo(map); }});
    const porCodigo = {{}};
    const lineas = [];
    function avisar(clase, codigo, alimentador) {{
      window.parent.postMessage({{ tipo: 'seleccionado', clase: clase, codigo: codigo, alimentador: alimentador }}, window.location.origin);
    }}
    datos.vistas.forEach(function (v) {{
      v.tramos.forEach(function (t) {{
        if (t.vertices.length < 2) return;
        const capa = L.polyline(t.vertices, {{ color: token('tramo'), weight: 3, smoothFactor: 0 }})
          .bindTooltip(texto(t.codigo)).on('click', function () {{ avisar('tramo', t.codigo, v.alimentador); }});
        capa.addTo(grupos.tramos);
        lineas.push(capa);
        porCodigo[t.codigo] = capa;
      }});
      v.barras.forEach(function (b) {{
        if (b.lat == null) return;
        const capa = L.circleMarker([b.lat, b.lon], {{ radius: 3, color: token('barra'), weight: 1, fillOpacity: 0.8 }})
          .bindTooltip(texto(b.codigo)).on('click', function () {{ avisar('barra', b.codigo, v.alimentador); }});
        capa.addTo(grupos.barras);
        porCodigo[b.codigo] = porCodigo[b.codigo] || capa;
      }});
      const punto = {{}};
      v.barras.forEach(function (b) {{ if (b.lat != null) punto[b.codigo] = [b.lat, b.lon]; }});
      v.sed.forEach(function (s) {{
        if (!punto[s.barra]) return;
        L.circleMarker(punto[s.barra], {{ radius: 5, color: token('sed'), weight: 2, fillOpacity: 0.3 }})
          .bindTooltip('SED ' + texto(s.codigo)).on('click', function () {{ avisar('sed', s.codigo, v.alimentador); }})
          .addTo(grupos.sed);
      }});
      v.maniobras.forEach(function (m) {{
        if (!punto[m.barra]) return;
        const color = m.estado === 'abierto' ? token('abierto') : token('cerrado');
        L.circleMarker(punto[m.barra], {{ radius: 6, color: color, weight: 3, fill: m.estado !== 'abierto' }})
          .bindTooltip(texto(m.codigo) + ' · ' + (m.estado === 'abierto' ? 'abierto' : 'cerrado'))
          .on('click', function () {{ avisar('maniobra', m.codigo, v.alimentador); }}).addTo(grupos.maniobras);
      }});
    }});
    function pintarResultados() {{
      const c = datos.capas;
      const leyenda = document.getElementById('leyenda');
      if (!c) {{ leyenda.hidden = true; return; }}
      const filas = [];
      Object.keys(c.capas).forEach(function (clave) {{
        const capa = c.capas[clave];
        const l = capa.leyenda;
        const umbral = l.umbral ? Object.keys(l.umbral).map((k) => k + ' ' + l.umbral[k]).join(' · ') : '';
        filas.push('<div><b>' + texto(l.magnitud) + '</b>' + (l.unidad ? ' (' + texto(l.unidad) + ')' : '')
          + (umbral ? ' · ' + texto(umbral) : '') + '</div>');
        capa.elementos.forEach(function (e) {{
          const trazo = porCodigo[e.codigo];
          if (!trazo || e.valor == null || typeof trazo.getLatLngs !== 'function' && typeof trazo.getLatLng !== 'function') return;
          const donde = trazo.getLatLng ? trazo.getLatLng() : trazo.getBounds().getCenter();
          const valor = texto(e.valor) + (l.unidad ? ' ' + texto(l.unidad) : '');
          const incumple = e.incumple;
          if (incumple) {{
            L.marker(donde, {{ icon: L.divIcon({{ className: '', html: '<div class="icono-incumple" aria-hidden="true">!</div>',
              iconSize: [16, 16] }}), keyboard: false }})
              .bindTooltip(texto(incumple.texto) + ' · ' + texto(l.motor_texto)).addTo(grupos.resultados);
          }} else {{
            L.circleMarker(donde, {{ radius: 2, color: token('normal'), weight: 1 }})
              .bindTooltip(texto(e.codigo) + ': ' + valor + ' · ' + texto(l.motor_texto)).addTo(grupos.resultados);
          }}
        }});
      }});
      leyenda.innerHTML = filas.join('') + '<div>Caso ' + texto(c.caso) + ' · ' + texto(c.motor_texto)
        + ' · umbral ' + texto(c.origen_umbral) + '</div>';
      leyenda.hidden = false;
    }}
    pintarResultados();
    const capasControl = {{}};
    CAPAS.forEach(function (c) {{ capasControl[c.nombre] = grupos[c.clave]; }});
    L.control.layers(null, capasControl, {{ position: 'topright', collapsed: true }}).addTo(map);
    // Nivel de detalle solo gráfico: el lienzo simplifica el dibujo al alejarse; los vértices no cambian.
    function detalle() {{
      const z = map.getZoom();
      const factor = (DETALLE.find((d) => z >= d[0]) || [0, 0])[1];
      lineas.forEach(function (l) {{ l.options.smoothFactor = factor; l.redraw(); }});
    }}
    map.on('zoomend', detalle);
    const todo = L.featureGroup(lineas);
    try {{ map.fitBounds(todo.getBounds(), {{ padding: [24, 24], maxZoom: 18 }}); }} catch (e) {{ map.setView([0, 0], 2); }}
    let resaltado = null;
    function resaltar(codigo) {{
      if (resaltado && resaltado.setStyle) resaltado.setStyle({{ color: token('tramo'), weight: 3 }});
      resaltado = porCodigo[codigo] || null;
      if (resaltado && resaltado.setStyle) resaltado.setStyle({{ color: token('resalte'), weight: 6 }});
      return resaltado;
    }}
    // Esquema cerrado: solo del padre y con el origen de la web que sirve la página, solo los tipos de ENTRADA y con
    // sus campos; lo demás se ignora.
    window.addEventListener('message', function (event) {{
      if (event.source !== window.parent || event.origin !== window.location.origin) return;
      const m = event.data;
      if (!m || typeof m !== 'object' || ENTRADA.indexOf(m.tipo) < 0) return;
      if ((m.tipo === 'seleccionar' || m.tipo === 'resaltar') && typeof m.codigo === 'string') {{
        const capa = resaltar(m.codigo);
        if (capa && m.tipo === 'seleccionar') {{
          if (capa.getBounds) map.fitBounds(capa.getBounds(), {{ maxZoom: 18 }}); else map.setView(capa.getLatLng(), 18);
        }}
      }} else if (m.tipo === 'capa' && typeof m.clave === 'string' && grupos[m.clave] && typeof m.visible === 'boolean') {{
        if (m.visible) grupos[m.clave].addTo(map); else map.removeLayer(grupos[m.clave]);
      }} else if (m.tipo === 'propuesta' && Array.isArray(m.punto) && m.punto.length === 2
                 && m.punto.every((x) => typeof x === 'number' && isFinite(x))) {{
        L.circleMarker(m.punto, {{ radius: 7, color: token('resalte'), weight: 3, dashArray: '4 3' }})
          .bindTooltip('Propuesta' + (typeof m.nodo === 'string' ? ' · ' + texto(m.nodo) : '')).addTo(grupos.tramos);
      }}
    }});
    window.parent.postMessage({{ tipo: 'listo' }}, window.location.origin);
  </script>
</body>
</html>
"""
