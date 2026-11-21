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
MENSAJES_ENTRADA = ('seleccionar', 'resaltar', 'deseleccionar', 'capa', 'propuesta')
#: Lo que la página manda a la pestaña: que ya está lista, y el elemento que el operador seleccionó en el plano.
MENSAJES_SALIDA = ('listo', 'seleccionado')
#: Las capas por vista, con su nombre en el selector y si se ven al abrir. Las etiquetas empiezan apagadas y solo se
#: dibujan desde :data:`ZOOM_ETIQUETAS` (111:RF-26); los puntos de transferencia, encendidos (111:RF-25).
CAPAS = (('tramos', 'Tramos', True), ('barras', 'Barras', True), ('sed', 'SED', True), ('maniobras', 'Maniobras', True),
         ('transferencias', 'Puntos de transferencia', True),
         ('etiqueta_sed', 'Etiquetas: código de la SED', False),
         ('etiqueta_kva', 'Etiquetas: potencia instalada de la SED (kVA)', False),
         ('etiqueta_seccion', 'Etiquetas: sección del conductor (mm²)', False),
         ('resultados', 'Resultados', True))
#: 111:RF-26: por debajo de este zoom las etiquetas se taparían unas a otras; se dice y se dibujan al acercarse.
ZOOM_ETIQUETAS = 15
#: 111:RF-24: un color por alimentador, distinto del de las maniobras, los resaltes y los puntos de transferencia;
#: claro y oscuro. Con un solo alimentador, el color de siempre (``--plano-tramo``).
COLORES_ALIMENTADOR = (('#1d4ed8', '#60a5fa'), ('#c2410c', '#fb923c'), ('#7e22ce', '#c084fc'), ('#0e7490', '#22d3ee'),
                       ('#a21caf', '#f0abfc'), ('#4d7c0f', '#a3e635'), ('#9f1239', '#fb7185'), ('#854d0e', '#facc15'),
                       ('#334155', '#cbd5e1'), ('#065f46', '#34d399'))
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
    from ..dominio.salidas_red import salida_permitida

    if salida_permitida('teselas'):
        return guion_de_fondos()[0], ''
    return '', 'Sin mapa base: la salida de teselas está apagada. La red se dibuja igual.'


# 111:RF-14: la página va aislada y su política no deja cargar images/layers.png de leaflet.css; el botón del control
# de capas plegado salía invisible, así que su icono va en la página como data: (prueba: test_pagina_plano).
def pagina(vistas: Sequence[Mapping[str, Any]], *, capas: Mapping[str, Any] | None = None,
           titulo: str = 'Plano de la red') -> str:
    """El HTML del plano de esas vistas (``plano_red.vista``) y, si se dan, las capas de un resultado pintable."""
    from .preview import politica_base, recurso_leaflet

    from .plano_red import transferencias

    vistas = list(vistas)
    datos = {'vistas': vistas, 'capas': dict(capas) if capas and capas.get('pintable') else None,
             'transferencias': transferencias(vistas)}
    teselas, aviso = _fondo()
    nombre = html_std.escape(titulo)
    capas_js = _json([{'clave': c, 'nombre': n, 'visible': v} for c, n, v in CAPAS])
    claros = '; '.join(f'--plano-a{i}: {c}' for i, (c, _o) in enumerate(COLORES_ALIMENTADOR))
    oscuros = '; '.join(f'--plano-a{i}: {o}' for i, (_c, o) in enumerate(COLORES_ALIMENTADOR))
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
      --plano-borde: #334155; --plano-transferencia: #000000; {claros}; }}
    @media (prefers-color-scheme: dark) {{
      :root {{ --plano-fondo: #0b1220; --plano-texto: #e2e8f0; --plano-panel: rgba(15,23,42,.94);
        --plano-tramo: #60a5fa; --plano-barra: #2dd4bf; --plano-sed: #c4b5fd; --plano-abierto: #f87171;
        --plano-cerrado: #4ade80; --plano-resalte: #fbbf24; --plano-normal: #4ade80; --plano-alerta: #f87171;
        --plano-borde: #94a3b8; --plano-transferencia: #ffffff; {oscuros}; }}
    }}
    html, body, #mapa {{ height: 100%; margin: 0; background: var(--plano-fondo); color: var(--plano-texto); }}
    .panel {{ position: absolute; z-index: 1000; left: 10px; bottom: 18px; max-width: min(60%, 420px);
      background: var(--plano-panel); color: var(--plano-texto); padding: 6px 10px; border-radius: 4px;
      font: 13px/1.4 system-ui, sans-serif; box-shadow: 0 1px 4px rgba(0,0,0,.3); }}
    .panel[hidden] {{ display: none; }}
    /* Sin «bottom: auto», el «bottom» de .panel estiraba el aviso de arriba abajo
       (358×618 px en un mapa de 564×646) y tapaba el dibujo de la red con su fondo casi opaco. */
    #aviso {{ position: absolute; z-index: 1000; top: 10px; left: 50px; bottom: auto; }}
    .icono-incumple {{ width: 16px; height: 16px; line-height: 16px; text-align: center; border-radius: 50%;
      background: var(--plano-alerta); color: #fff; font: 700 12px system-ui, sans-serif;
      border: 1px solid var(--plano-borde); }}
    #alimentadores {{ left: auto; right: 10px; bottom: 18px; }}
    #alimentadores span.muestra {{ display: inline-block; width: 18px; height: 4px; margin-right: 6px; vertical-align: middle; }}
    .etiqueta {{ background: var(--plano-panel); color: var(--plano-texto); border: 1px solid var(--plano-borde);
      padding: 0 3px; font: 11px/1.3 system-ui, sans-serif; box-shadow: none; }}
    .etiqueta::before {{ display: none; }}
    .sin-etiquetas .etiqueta {{ display: none; }}
    #aviso-etiquetas {{ top: 10px; left: auto; right: 60px; bottom: auto; }}
    .icono-transferencia {{ width: 14px; height: 14px; transform: rotate(45deg); background: var(--plano-fondo);
      border: 3px solid var(--plano-transferencia); box-sizing: border-box; }}
    .leaflet-container:focus-visible {{ outline: 3px solid var(--plano-resalte); outline-offset: -3px; }}
  </style>
</head>
<body>
  <div id="mapa" role="application" aria-label="{nombre}"></div>
  <div id="aviso" class="panel" role="status"{'' if aviso else ' hidden'}>{html_std.escape(aviso)}</div>
  <div id="leyenda" class="panel" aria-live="polite" hidden></div>
  <div id="alimentadores" class="panel" hidden></div>
  <div id="aviso-etiquetas" class="panel" role="status" hidden>Acerque el plano para ver las etiquetas.</div>
  <script type="application/json" id="datos-plano">{_json(datos)}</script>
  <script>
    const ENTRADA = {_json(list(MENSAJES_ENTRADA))};
    const CAPAS = {capas_js};
    const DETALLE = {detalle_js};
    const ZOOM_ETIQUETAS = {ZOOM_ETIQUETAS};
    const N_COLORES = {len(COLORES_ALIMENTADOR)};
    const datos = JSON.parse(document.getElementById('datos-plano').textContent);
    const css = getComputedStyle(document.documentElement);
    const token = (n) => css.getPropertyValue('--plano-' + n).trim();
    const texto = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}})[c]);
    // Los controles de Leaflet salían en inglés («Zoom in», «Layers») dentro de una página
    // en español, y el prefijo de la atribución era un enlace a internet en una web que trabaja sin red.
    const map = L.map('mapa', {{ preferCanvas: true, keyboard: true, zoomControl: false }});
    L.control.zoom({{ zoomInTitle: 'Acercar', zoomOutTitle: 'Alejar' }}).addTo(map);
    map.attributionControl.setPrefix(false);
    {teselas}
    const grupos = {{}};
    CAPAS.forEach(function (c) {{ grupos[c.clave] = L.layerGroup(); if (c.visible) grupos[c.clave].addTo(map); }});
    // con varios alimentadores, cada uno con su color y su capa encendible; con uno, el color de siempre.
    const varios = datos.vistas.length > 1;
    const colorDe = {{}};
    const porAlimentador = {{}};
    datos.vistas.forEach(function (v, i) {{
      colorDe[v.alimentador] = varios ? token('a' + (i % N_COLORES)) : token('tramo');
      porAlimentador[v.alimentador] = L.layerGroup().addTo(grupos.tramos);
    }});
    const etiqueta = (donde, contenido, lado) => L.tooltip({{ permanent: true, direction: lado, className: 'etiqueta',
      offset: lado === 'left' ? [-6, 0] : [6, 0], interactive: false }}).setLatLng(donde).setContent(texto(contenido));
    const numero = (x, d) => Number(x).toLocaleString('es-PE', {{ maximumFractionDigits: d }});
    const porCodigo = {{}};
    const lineas = [];
    function avisar(clase, codigo, alimentador) {{
      window.parent.postMessage({{ tipo: 'seleccionado', clase: clase, codigo: codigo, alimentador: alimentador }}, window.location.origin);
    }}
    datos.vistas.forEach(function (v) {{
      v.tramos.forEach(function (t) {{
        if (t.vertices.length < 2) return;
        const color = colorDe[v.alimentador];
        const capa = L.polyline(t.vertices, {{ color: color, colorBase: color, weight: 3, smoothFactor: 0 }})
          .bindTooltip(texto(t.codigo) + (varios ? ' · ' + texto(v.alimentador) : ''))
          .on('click', function () {{ avisar('tramo', t.codigo, v.alimentador); }});
        capa.addTo(porAlimentador[v.alimentador]);
        if (t.seccion_mm2 != null) {{
          const medio = t.vertices[Math.floor((t.vertices.length - 1) / 2)];
          etiqueta(medio, numero(t.seccion_mm2, 1) + ' mm²', 'right').addTo(grupos.etiqueta_seccion);
        }}
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
          .bindTooltip('SED ' + texto(s.codigo) + (s.kva != null ? ' · ' + numero(s.kva, 1) + ' kVA' : ''))
          .on('click', function () {{ avisar('sed', s.codigo, v.alimentador); }})
          .addTo(grupos.sed);
        // el código a la derecha y la potencia instalada a la izquierda, para que no se tapen.
        etiqueta(punto[s.barra], s.codigo, 'right').addTo(grupos.etiqueta_sed);
        if (s.kva != null) etiqueta(punto[s.barra], numero(s.kva, 1) + ' kVA', 'left').addTo(grupos.etiqueta_kva);
      }});
      v.maniobras.forEach(function (m) {{
        if (!punto[m.barra]) return;
        const color = m.estado === 'abierto' ? token('abierto') : token('cerrado');
        L.circleMarker(punto[m.barra], {{ radius: 6, color: color, weight: 3, fill: m.estado !== 'abierto' }})
          .bindTooltip(texto(m.codigo) + ' · ' + (m.estado === 'abierto' ? 'abierto' : 'cerrado'))
          .on('click', function () {{ avisar('maniobra', m.codigo, v.alimentador); }}).addTo(grupos.maniobras);
      }});
    }});
    // los puntos donde se tocan los alimentadores del plano, con sus maniobras de la fuente.
    (datos.transferencias || []).forEach(function (p) {{
      if (p.lat == null) return;
      const maniobras = p.maniobras.map((m) => texto(m.codigo) + ' ' + texto(m.estado)).join(', ');
      L.marker([p.lat, p.lon], {{ icon: L.divIcon({{ className: '', html: '<div class="icono-transferencia" aria-hidden="true"></div>',
        iconSize: [14, 14] }}), keyboard: false, zIndexOffset: 500 }})
        .bindTooltip('Transferencia ' + p.alimentadores.map(texto).join(' ↔ ') + ' · barra ' + texto(p.barra)
          + (maniobras ? ' · ' + maniobras : ' · sin maniobra en la fuente'))
        .on('click', function () {{ avisar('barra', p.barra, p.alimentadores[0]); }}).addTo(grupos.transferencias);
    }});
    if (varios) {{
      const caja = document.getElementById('alimentadores');
      const n = (datos.transferencias || []).length;
      caja.innerHTML = datos.vistas.map((v) => '<div><span class="muestra" style="background:' + colorDe[v.alimentador]
        + '"></span>' + texto(v.alimentador) + '</div>').join('')
        + '<div><span class="muestra" style="background:' + token('transferencia') + '"></span>'
        + (n === 0 ? 'ningún punto de transferencia' : n + (n === 1 ? ' punto' : ' puntos') + ' de transferencia') + '</div>';
      caja.hidden = false;
    }}
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
    if (varios) datos.vistas.forEach(function (v) {{
      capasControl['<span style="color:' + colorDe[v.alimentador] + '">■</span> ' + texto(v.alimentador)] = porAlimentador[v.alimentador];
    }});
    const controlCapas = L.control.layers(null, capasControl, {{ position: 'topright', collapsed: true }}).addTo(map);
    const botonCapas = controlCapas.getContainer().querySelector('.leaflet-control-layers-toggle');
    if (botonCapas) {{ botonCapas.title = 'Capas'; botonCapas.setAttribute('aria-label', 'Capas'); }}
    // Nivel de detalle solo gráfico: el lienzo simplifica el dibujo al alejarse; los vértices no cambian.
    function detalle() {{
      const z = map.getZoom();
      const factor = (DETALLE.find((d) => z >= d[0]) || [0, 0])[1];
      lineas.forEach(function (l) {{ l.options.smoothFactor = factor; l.redraw(); }});
    }}
    map.on('zoomend', detalle);
    // las etiquetas encendidas se dibujan desde ZOOM_ETIQUETAS; más lejos se dice que hay que acercarse.
    function etiquetas() {{
      const lejos = map.getZoom() < ZOOM_ETIQUETAS;
      const alguna = ['etiqueta_sed', 'etiqueta_kva', 'etiqueta_seccion'].some((k) => map.hasLayer(grupos[k]));
      map.getContainer().classList.toggle('sin-etiquetas', lejos);
      document.getElementById('aviso-etiquetas').hidden = !(lejos && alguna);
    }}
    map.on('zoomend overlayadd overlayremove', etiquetas);
    const todo = L.featureGroup(lineas);
    try {{ map.fitBounds(todo.getBounds(), {{ padding: [24, 24], maxZoom: 18 }}); }} catch (e) {{ map.setView([0, 0], 2); }}
    etiquetas();
    let resaltado = null;
    function resaltar(codigo) {{
      if (resaltado && resaltado.setStyle) resaltado.setStyle({{ color: resaltado.options.colorBase || token('tramo'), weight: 3 }});
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
          // Encuadre con un zoom que deja el elemento visible entero, con margen alrededor.
          if (capa.getBounds) map.fitBounds(capa.getBounds(), {{ padding: [48, 48], maxZoom: 18 }});
          else map.setView(capa.getLatLng(), 18);
        }}
      }} else if (m.tipo === 'deseleccionar') {{
        resaltar(null);
      }} else if (m.tipo === 'capa' && typeof m.clave === 'string' && grupos[m.clave] && typeof m.visible === 'boolean') {{
        if (m.visible) grupos[m.clave].addTo(map); else map.removeLayer(grupos[m.clave]);
        etiquetas();
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
