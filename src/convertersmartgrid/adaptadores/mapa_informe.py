"""Imágenes del informe de estudio con los resultados de DIgSILENT (spec 017, RF-10, RF-11).

El informe pide la vista del alimentador y su coloreado por tensión y por cargabilidad. Con
DIgSILENT sin ventana, que es como trabajan los guiones, ``WriteWMF`` deja un fichero de
1 KB sin dibujo (comprobado en la aceptación): no hay imagen que exportar. Se dibujan aquí
con lo mismo que mostraría DIgSILENT: la posición GPS de cada barra y el trazado GPS de
cada tramo, verificados en el «Caso base» (spec 015), y la tensión y la cargabilidad que
dio el flujo del caso, con las bandas del perfil de empresa (RF-115, RF-116).

``geo`` es lo que guarda ``tools/estudios_pf.py`` por alimentador: ``barras`` como
``[nombre, lat, lon, u_pu, kv]`` y ``tramos`` como ``[nombre, [[lat, lon], ...], carga_%]``.
"""

from __future__ import annotations

import json
import math
import textwrap
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

#: Tamaño de la imagen: a 16 cm de ancho en el Word quedan unos 250 ppp.
ANCHO_PX, ALTO_PX = 1600, 1150
MARGEN_PX = 60
LEYENDA_PX = 330
#: Colores de las bandas, de la peor a la mejor tensión y de menos a más cargabilidad.
COLORES_TENSION = ((200, 30, 30), (240, 130, 20), (230, 200, 20), (40, 150, 60), (40, 90, 200))
COLORES_CARGA = ((40, 150, 60), (150, 200, 40), (230, 200, 20), (240, 130, 20), (200, 30, 30),
                 (110, 0, 0))
GRIS = (150, 150, 150)
#: Obras resaltadas en el plano de una alternativa (017:RF-133).
COLOR_CONDUCTOR = (200, 0, 160)
COLOR_BANCO = (0, 150, 170)
COLOR_PROBLEMA_TENSION = (235, 110, 0)
COLOR_SOBRECARGA = (190, 20, 20)
COLOR_SET = (95, 45, 170)
COLOR_TRANSFORMADOR = (115, 55, 150)
COLOR_CARGA_NUEVA = (0, 110, 75)
COLOR_TRANSFERENCIA = (85, 95, 110)
#: 086:RF-35: de referencia, para quien dibuja sin dar bandas: las que salen de ±5 % y de un umbral del 100 %
#: (``informes.bandas_de_limites``). El informe no llega aquí sin las suyas: las saca de sus propios límites.
BANDAS_TENSION = (85.0, 90.0, 95.0, 105.0)
BANDAS_CARGA = (80.0, 90.0, 95.0, 105.0, 150.0)


class MapaError(ValueError):
    """No hay datos de geografía con los que dibujar."""


def _banda(valor: float, bandas: Sequence[float]) -> int:
    return sum(1 for b in bandas if valor >= b)


def _color(i: int, bandas: Sequence[float], paleta: Sequence[tuple[int, int, int]]):
    """El color de la banda ``i`` con cualquier número de bandas del perfil."""
    n = len(bandas)
    if n + 1 == len(paleta) or n == 0:
        return paleta[min(i, len(paleta) - 1)]
    return paleta[round(i * (len(paleta) - 1) / n)]


def _rotulos(bandas: Sequence[float], unidad: str = '%') -> list[str]:
    b = [f'{x:g}' for x in bandas]
    return ([f'menos de {b[0]} {unidad}']
            + [f'de {b[i]} a {b[i + 1]} {unidad}' for i in range(len(b) - 1)]
            + [f'más de {b[-1]} {unidad}'])


def _proyeccion(puntos: list[tuple[float, float]]):
    """(lat, lon) → píxel, misma escala en los dos ejes (equirectangular local)."""
    lats = [p[0] for p in puntos]
    lons = [p[1] for p in puntos]
    lat0 = (min(lats) + max(lats)) / 2
    kx = math.cos(math.radians(lat0))
    ancho = (max(lons) - min(lons)) * kx or 1e-9
    alto = (max(lats) - min(lats)) or 1e-9
    util_x = ANCHO_PX - LEYENDA_PX - 2 * MARGEN_PX
    util_y = ALTO_PX - 2 * MARGEN_PX - 40
    escala = min(util_x / ancho, util_y / alto)
    x0 = MARGEN_PX + (util_x - ancho * escala) / 2
    y0 = MARGEN_PX + 40 + (util_y - alto * escala) / 2

    def a_px(lat: float, lon: float) -> tuple[float, float]:
        return (x0 + (lon - min(lons)) * kx * escala, y0 + (max(lats) - lat) * escala)
    return a_px, escala


#: Pie de la vista de ubicación, que se dibuja sin mapa de fondo (017:RF-112).
PIE_SIN_FONDO = 'Sin mapa de fondo: dibujado con las coordenadas de la red'
#: Pie de la imagen de un alimentador sin coordenadas (017:RF-12).
PIE_ESQUEMATICO = 'Esquemático: el alimentador no tiene coordenadas GPS'
#: Paso del esquemático entre niveles y entre filas, en «grados» ficticios.
_PASO_ESQUEMA = 0.001


def esquematico(geo: Mapping[str, Any]) -> Mapping[str, Any]:
    """La geografía de un alimentador sin GPS, con posiciones de esquema (017:RF-12).

    ``tools/estudios_pf.py`` guarda en ``esquema`` las barras y los tramos de un alimentador
    sin ninguna coordenada. Se dibuja como un árbol desde la cabecera: cada barra a la
    derecha de la que la alimenta y cada rama en su fila, con el mismo coloreado por
    tensión y por cargabilidad. Una geografía con coordenadas se devuelve tal cual.
    """
    esquema = geo.get('esquema')
    tiene_gps = any(b[1] is not None and b[2] is not None for b in geo.get('barras') or [])
    if not esquema or tiene_gps or any(len(t[1] or []) >= 2 for t in geo.get('tramos') or []):
        return geo
    datos = {b[0]: b for b in esquema.get('barras') or []}
    vecinos: dict[str, list[str]] = {}
    for _n, a, b, _c in esquema.get('tramos') or []:
        vecinos.setdefault(a, []).append(b)
        vecinos.setdefault(b, []).append(a)
    for _n, a, b in geo.get('acoples') or []:
        vecinos.setdefault(a, []).append(b)
        vecinos.setdefault(b, []).append(a)
    for v in vecinos.values():
        v.sort()
    posicion: dict[str, tuple[int, float]] = {}
    fila = 0.0
    raices = [geo['cabecera']] if geo.get('cabecera') in vecinos else []
    raices += sorted(set(vecinos) | set(datos))
    for raiz in raices:
        if raiz in posicion:
            continue
        # Recorrido en profundidad sin recursión: un alimentador real tiene miles de barras.
        # El primer hijo sigue en la fila de su padre; cada rama nueva abre una fila.
        nivel, padre, hijos = {raiz: 0}, {raiz: None}, {}
        orden: list[str] = []
        pila = [raiz]
        while pila:
            n = pila.pop()
            orden.append(n)
            hijos[n] = [h for h in vecinos.get(n, []) if h not in nivel]
            for h in hijos[n]:
                nivel[h], padre[h] = nivel[n] + 1, n
            pila.extend(reversed(hijos[n]))
        fila_de: dict[str, float] = {}
        for n in orden:
            p = padre[n]
            if p is not None and hijos[p][0] != n:
                fila += 1
            fila_de[n] = fila if p is None or hijos[p][0] != n else fila_de[p]
            posicion[n] = (nivel[n], fila_de[n])
        fila += 1

    def coord(n):
        x, y = posicion[n]
        return [round(-y * _PASO_ESQUEMA, 7), round(x * _PASO_ESQUEMA, 7)]

    barras = [[n, *coord(n), (datos.get(n) or [n, None, 0.0])[1], (datos.get(n) or [n, None, 0.0])[2]]
              for n in sorted(posicion)]
    tramos = [[n, [coord(a), coord(b)], c, a, b, None, None]
              for n, a, b, c in esquema.get('tramos') or [] if a in posicion and b in posicion]
    return {**geo, 'barras': barras, 'tramos': tramos, 'pie': PIE_ESQUEMATICO}


def _fuente(tam: int):
    from PIL import ImageFont

    for nombre in ('arial.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(nombre, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def dibujar(geo: Mapping[str, Any], modo: str, destino: Path, *, titulo: str,
            bandas_tension: Sequence[float] | None = None,
            bandas_carga: Sequence[float] | None = None,
            marcar: Sequence[str] = (), obras: Mapping[str, Any] | None = None,
            cliente: tuple[str, str] | None = None,
            resaltar: Mapping[str, Any] | None = None,
            encuadre: Mapping[str, Any] | None = None) -> Path:
    """La imagen ``modo`` (``ubicacion``, ``tension`` o ``cargabilidad``) en ``destino``.

    ``marcar``: barras que se señalan con su nombre (la cabecera y la de menor tensión).
    ``obras`` (017:RF-133), en la vista de ubicación y en ``detalle``: ``tramos`` con el
    conductor nuevo, ``trechos`` como ``[(desde, hasta), ...]``, ``bancos`` nuevos y
    ``existentes`` como ``[(barra, kvar), ...]``. ``detalle`` es la vista de ubicación
    ampliada sobre la zona de las obras: en CA101 el cambio de 6,6 km quedaba en una
    esquina del alimentador entero, con los rótulos unos encima de otros.
    """
    from PIL import Image, ImageDraw

    geo = esquematico(geo)                                                       # RF-12
    barras = [b for b in geo.get('barras') or [] if b[1] is not None and b[2] is not None]
    tramos = [t for t in geo.get('tramos') or [] if len(t[1] or []) >= 2]
    puntos = [(b[1], b[2]) for b in barras] + [tuple(p) for t in tramos for p in t[1]]
    if not puntos:
        raise MapaError('El estudio no guardó la geografía del alimentador: vuelva a ejecutar '
                        'el estudio de flujo.')
    obras = obras or {}
    abiertos = {o['elemento'] for o in obras.get('transferencias', ())}
    tramos = [t for t in tramos if t[0] not in abiertos]
    if encuadre and modo != 'detalle':
        puntos = [(b[1], b[2]) for b in encuadre.get('barras', ())
                  if b[1] is not None and b[2] is not None]
        puntos += [tuple(p) for t in encuadre.get('tramos', ()) for p in t[1] or ()]
    if modo == 'detalle':
        zona = _zona_de_obras(barras, tramos, obras)
        if zona:
            puntos = zona
    a_px, _ = _proyeccion(puntos)
    bt = tuple(bandas_tension or BANDAS_TENSION)
    bc = tuple(bandas_carga or BANDAS_CARGA)
    img = Image.new('RGB', (ANCHO_PX, ALTO_PX), 'white')
    d = ImageDraw.Draw(img)

    for nombre, pts, carga in ((t[0], t[1], t[2]) for t in tramos):
        if modo == 'cargabilidad' and carga is not None:
            color = _color(_banda(carga, bc), bc, COLORES_CARGA)
            ancho = 5 if carga > 100.0 else 3
        else:
            color, ancho = (GRIS, 3) if modo not in PLANOS else ((60, 60, 60), 3)
        d.line([a_px(*p) for p in pts], fill=color, width=ancho, joint='curve')
    if modo in PLANOS or resaltar is not None:
        cambiados = set(obras.get('tramos') or ())
        for t in tramos:
            if t[0] in cambiados:
                d.line([a_px(*p) for p in t[1]], fill=COLOR_CONDUCTOR, width=9, joint='curve')
    if modo in ('tension', *PLANOS):
        for nombre, lat, lon, u, kv in barras:
            if u is None:
                continue
            x, y = a_px(lat, lon)
            if modo == 'tension':
                banda = _banda(100.0 * u, bt)
                color = _color(banda, bt, COLORES_TENSION)
                r = 3 if banda == _banda(100.0, bt) else 5
            else:
                color, r = ((0, 90, 180), 2) if (kv or 0) < 1 else ((60, 60, 60), 1)
            d.ellipse([x - r, y - r, x + r, y + r], fill=color)
    f_titulo, f_texto = _fuente(30), _fuente(20)
    # (barra, texto, color, símbolo): los símbolos primero y los rótulos después, cada uno
    # donde no pise a otro (RF-133).
    rotulos: list[tuple[str, str, tuple[int, int, int], str]] = []
    if modo in PLANOS or resaltar is not None:
        trechos = list(obras.get('trechos') or ())
        for i, (desde, hasta) in enumerate(trechos, 1):
            n = f' {i}' if len(trechos) > 1 else ''
            rotulos += [(desde, f'Inicio{n}: {desde}', COLOR_CONDUCTOR, 'cuadro'),
                        (hasta, f'Fin{n}: {hasta}', COLOR_CONDUCTOR, 'cuadro')]
        for barra, kvar in _por_barra(obras.get('existentes') or ()):
            rotulos.append((barra, f'Banco existente {kvar:g} kvar', COLOR_BANCO, 'hueco'))
        for barra, kvar in _por_barra(obras.get('bancos') or ()):
            texto = f'Banco nuevo {kvar:g} kvar' + (f' · {barra}' if resaltar is None else '')
            rotulos.append((barra, texto, COLOR_BANCO, 'lleno'))
    rotulos += [(n, '', (0, 0, 0), 'circulo') for n in marcar]
    posicion = {b[0]: b for b in barras}
    ocupados: list[tuple[float, float, float, float]] = []
    if resaltar is not None:
        for i, transferencia in enumerate(obras.get('transferencias') or (), 1):
            pts = transferencia['geometria']
            if pts:
                _linea_discontinua(d, [a_px(*p) for p in pts], COLOR_TRANSFERENCIA, 5)
                x, y = a_px(*pts[len(pts) // 2])
                d.line([(x - 7, y - 7), (x + 7, y + 7)], fill=COLOR_TRANSFERENCIA, width=3)
                d.line([(x - 7, y + 7), (x + 7, y - 7)], fill=COLOR_TRANSFERENCIA, width=3)
                _rotular(d, x, y, f'A{i}', COLOR_TRANSFERENCIA, f_texto, ocupados)
        # Dos canales: la alarma nunca se sustituye por el color de una obra aplicada.
        sobre = {e[0]: e[2] for e in resaltar['carga']}
        for t in tramos:
            if t[0] in sobre:
                _linea_discontinua(d, [a_px(*p) for p in t[1]], COLOR_SOBRECARGA, 13)
                if t[0] in cambiados:
                    d.line([a_px(*p) for p in t[1]], fill=COLOR_CONDUCTOR, width=4)
        reforzados = {n for n, _ in obras.get('transformadores', ())}
        for n, _, _ in resaltar['carga']:
            b = posicion.get(resaltar['vinculos'].get(n, n))
            if b is not None:
                x, y = a_px(b[1], b[2])
                r = 18 if n in reforzados else 10
                d.rectangle([x - r, y - r, x + r, y + r], outline=COLOR_SOBRECARGA, width=4)
        for n, minimo, maximo in resaltar['tension']:
            if n in posicion:
                b = posicion[n]
                x, y = a_px(b[1], b[2])
                d.ellipse([x - 6, y - 6, x + 6, y + 6], outline=COLOR_PROBLEMA_TENSION, width=3)
        for barra, nombre in obras.get('sets') or ():
            if barra in posicion:
                b = posicion[barra]
                x, y = a_px(b[1], b[2])
                d.rectangle([x - 13, y - 13, x + 13, y + 13], outline=COLOR_SET, width=5)
                _rotular(d, x, y, nombre, COLOR_SET, f_texto, ocupados)
        for i, (nombre, barra) in enumerate(obras.get('transformadores') or (), 1):
            b = posicion[barra]
            x, y = a_px(b[1], b[2])
            for dx in (-6, 6):
                d.ellipse([x + dx - 7, y - 7, x + dx + 7, y + 7],
                          fill='white', outline=COLOR_TRANSFORMADOR, width=3)
            _rotular(d, x, y, f'R{i}', COLOR_TRANSFORMADOR, f_texto, ocupados)
        for i, (nombre, barra) in enumerate(obras.get('cargas_nuevas') or (), 1):
            b = posicion[barra]
            x, y = a_px(b[1], b[2])
            # El desplazamiento con guía conserva el rombo del cliente y la alarma en
            # su coordenada nativa, aunque la carga esté conectada en esa misma barra.
            d.line([(x, y), (x + 12, y + 12)], fill=COLOR_CARGA_NUEVA, width=1)
            d.rectangle([x + 8, y + 8, x + 16, y + 16], fill=COLOR_CARGA_NUEVA)
            _rotular(d, x + 12, y + 12, f'C{i}', COLOR_CARGA_NUEVA, _fuente(12), ocupados)
        # Identificadores cortos en el plano; nombres y medidas en la leyenda.
        for i, (tipo, n, valor) in enumerate(resaltar['rotulos'], 1):
            b = posicion.get(resaltar['vinculos'].get(n, n))
            pts = next((t[1] for t in tramos if t[0] == n), None) if b is None else None
            punto = (b[1], b[2]) if b is not None else (pts[len(pts) // 2] if pts else None)
            if punto:
                _rotular(d, *a_px(*punto), f'P{i}', COLOR_SOBRECARGA if tipo == 'C' else COLOR_PROBLEMA_TENSION,
                         f_texto, ocupados)
    for barra, texto, color, simbolo in rotulos:
        b = posicion.get(barra)
        if b is None:
            continue
        x, y = a_px(b[1], b[2])
        if simbolo == 'lleno':
            d.polygon([(x, y - 14), (x - 12, y + 9), (x + 12, y + 9)], fill=color, outline=(0, 0, 0))
        elif simbolo == 'hueco':
            d.polygon([(x, y - 14), (x - 12, y + 9), (x + 12, y + 9)], fill='white', outline=color, width=4)
        elif simbolo == 'cuadro':
            d.rectangle([x - 9, y - 9, x + 9, y + 9], fill=color, outline=(0, 0, 0))
        else:
            d.ellipse([x - 11, y - 11, x + 11, y + 11], outline=(0, 0, 0), width=3)
            texto = barra if b[3] is None else f'{barra} · {b[3]:.3f} p.u.'
        _rotular(d, x, y, texto, color, f_texto, ocupados)
    if cliente is not None and posicion.get(cliente[0]) is not None:
        b = posicion[cliente[0]]
        _marcar_cliente(d, *a_px(b[1], b[2]), cliente[1], f_texto, ocupados)

    d.rectangle([0, 0, ANCHO_PX, MARGEN_PX + 10], fill='white')
    while d.textlength(titulo, font=f_titulo) > ANCHO_PX - LEYENDA_PX - 2 * MARGEN_PX:
        f_titulo = _fuente(max(12, f_titulo.size - 1))
        if f_titulo.size == 12:
            break
    d.text((MARGEN_PX, 18), titulo, fill=(0, 0, 0), font=f_titulo)
    x0 = ANCHO_PX - LEYENDA_PX + 10
    y = MARGEN_PX + 50
    d.rectangle([x0 - 10, 0, ANCHO_PX, ALTO_PX], fill='white')
    if modo == 'tension':
        filas = [(_color(i, bt, COLORES_TENSION), r)
                 for i, r in enumerate(_rotulos(bt, '% de la nominal'))]
        cabeza = 'Tensión'
    elif modo == 'cargabilidad':
        filas = [(_color(i, bc, COLORES_CARGA), r) for i, r in enumerate(_rotulos(bc))]
        cabeza = 'Cargabilidad'
    else:
        filas = [((60, 60, 60), 'red de media tensión'), ((0, 90, 180), 'SED (baja tensión)')]
        if obras.get('tramos'):
            filas.append((COLOR_CONDUCTOR, 'conductor nuevo'))
        if obras.get('bancos'):
            filas.append((COLOR_BANCO, 'banco nuevo'))
        if obras.get('existentes'):
            filas.append(('hueco', 'banco existente'))
        cabeza = 'Alimentador' if modo == 'ubicacion' else 'Zona de las obras'
    if resaltar is not None:
        filas = [((60, 60, 60), 'red existente')] + filas if modo not in PLANOS else filas
        if modo not in PLANOS:
            if obras.get('tramos'):
                filas.append((COLOR_CONDUCTOR, 'salida / terna / refuerzo'))
            if obras.get('bancos'):
                filas.append((COLOR_BANCO, 'banco nuevo (triángulo)'))
            if obras.get('existentes'):
                filas.append(('hueco', 'banco existente (vacío)'))
        if obras.get('sets'):
            filas.append((COLOR_SET, 'SET nueva (cuadro)'))
        if obras.get('transformadores'):
            filas.append((COLOR_TRANSFORMADOR, 'TR reforzado (doble círculo)'))
        if obras.get('cargas_nuevas'):
            filas.append((COLOR_CARGA_NUEVA, f'cargas nuevas: {len(obras["cargas_nuevas"])} (C#)'))
        if obras.get('transferencias'):
            filas.append((COLOR_TRANSFERENCIA, 'abierto por transferencia'))
        if not resaltar.get('sin_resultados'):
            filas += [(COLOR_PROBLEMA_TENSION, 'tensión fuera (círculo)'),
                      ('discontinua', 'sobrecarga (guion/cuadro)')]
        filas.append((COLOR_CLIENTE, 'punto cliente (rombo)'))
        if modo in PLANOS:
            filas = [(c, 'salida / terna / refuerzo' if r == 'conductor nuevo' else r) for c, r in filas]
        f_texto = _fuente(17)
    d.text((x0, y), cabeza, fill=(0, 0, 0), font=f_texto)
    y += 34
    for color, rotulo in filas:
        if color == 'discontinua':
            _linea_discontinua(d, [(x0, y + 8), (x0 + 28, y + 8)], COLOR_SOBRECARGA, 5)
        elif color == 'hueco':
            d.rectangle([x0, y, x0 + 28, y + 18], fill='white', outline=COLOR_BANCO, width=4)
        else:
            d.rectangle([x0, y, x0 + 28, y + 18], fill=color)
        d.text((x0 + 38, y - 2), rotulo, fill=(0, 0, 0), font=f_texto)
        y += 30
    if resaltar is not None:
        for texto in resaltar['resumen']:
            for linea in textwrap.wrap(texto, width=31, break_long_words=True):
                d.text((x0, y), linea, fill=(0, 0, 0), font=_fuente(16))
                y += 20
            y += 6
    pie = ('Topología nativa; sin solución de flujo' if (resaltar or {}).get('sin_resultados')
           else 'Resultados del flujo de DIgSILENT')
    if geo.get('pie'):                                                           # RF-12
        for i, linea in enumerate(textwrap.wrap(geo['pie'], width=36)):
            d.text((x0, ALTO_PX - 90 + 20 * i), linea, fill=(90, 90, 90), font=_fuente(16))
    d.text((x0, ALTO_PX - 40), pie, fill=(90, 90, 90),
           font=_fuente(16))
    destino.parent.mkdir(parents=True, exist_ok=True)
    from PIL.PngImagePlugin import PngInfo
    info = PngInfo()
    info.add_text('pie', geo.get('pie') or pie)
    if resaltar is not None:
        evidencia = {'tension_fuera': (None if resaltar.get('sin_resultados') else [x[0] for x in resaltar['tension']]),
                     'sobrecargas': (None if resaltar.get('sin_resultados') else [x[0] for x in resaltar['carga']]),
                     'sin_resultados': bool(resaltar.get('sin_resultados')),
                     'sin_localizar': resaltar['sin_localizar'], 'obras_tramos': list(obras.get('tramos') or ()),
                     'obras_transformadores': [n for n, _ in obras.get('transformadores', ())],
                     'obras_sin_localizar': list(obras.get('sin_localizar') or ()),
                     'cargas_nuevas': [n for n, _ in obras.get('cargas_nuevas', ())],
                     'transferencias': [{'elemento': o['elemento'], 'dibujada': bool(o['geometria'])}
                                       for o in obras.get('transferencias', ())],
                     'cliente': cliente[0] if cliente else None, 'leyenda': [r for _, r in filas],
                     'encuadre': [min(p[0] for p in puntos), min(p[1] for p in puntos),
                                  max(p[0] for p in puntos), max(p[1] for p in puntos)]}
        info.add_text('evidencia_plano', json.dumps(evidencia, ensure_ascii=False))
    img.save(destino, 'PNG', dpi=(250, 250), pnginfo=info)
    return destino


#: Vistas de ubicación: la del alimentador entero y la ampliada sobre las obras.
PLANOS = ('ubicacion', 'detalle')
#: Margen de la vista de detalle alrededor de las obras, en grados (unos 300 m).
MARGEN_DETALLE_GRADOS = 0.003


def _linea_discontinua(d, puntos, color, ancho):
    """Trazo de alarma sobre el conductor: deja visible su color entre segmentos."""
    recorrido = 0.0
    for (x1, y1), (x2, y2) in pairwise(puntos):
        largo = math.hypot(x2 - x1, y2 - y1)
        if largo == 0:
            continue
        fin = recorrido + largo
        indice = math.floor(recorrido / 12)
        while indice * 12 < fin:
            s = max(recorrido, indice * 12) - recorrido
            hasta = min(fin, (indice + 1) * 12) - recorrido
            if indice % 2 == 0:
                d.line([(x1 + (x2 - x1) * s / largo, y1 + (y2 - y1) * s / largo),
                        (x1 + (x2 - x1) * hasta / largo, y1 + (y2 - y1) * hasta / largo)],
                       fill=color, width=ancho)
            indice += 1
        recorrido = fin


def _por_barra(bancos) -> list[tuple[str, float]]:
    """Bancos de la misma barra sumados: dos de 300 kvar en «14717» son uno de 600."""
    suma: dict[str, float] = {}
    for barra, kvar in bancos:
        suma[barra] = suma.get(barra, 0.0) + float(kvar or 0)
    return list(suma.items())


def _zona_de_obras(barras, tramos, obras) -> list[tuple[float, float]]:
    """Esquinas de la zona de las obras con su margen, para la vista de detalle."""
    cambiados = set(obras.get('tramos') or ())
    marcadas = {b for par in obras.get('trechos') or () for b in par}
    marcadas |= {b for b, _ in [*(obras.get('bancos') or ()), *(obras.get('existentes') or ())]}
    marcadas |= {b for _, b in obras.get('transformadores') or ()}
    marcadas |= {b for b, _ in obras.get('sets') or ()}
    pts = [tuple(p) for t in tramos if t[0] in cambiados for p in t[1]]
    pts += [(b[1], b[2]) for b in barras if b[0] in marcadas]
    if not pts:
        return []
    m = MARGEN_DETALLE_GRADOS
    lats, lons = [p[0] for p in pts], [p[1] for p in pts]
    return [(min(lats) - m, min(lons) - m), (max(lats) + m, max(lons) + m)]


def _rotular(d, x: float, y: float, texto: str, color, fuente, ocupados: list, *,
             apartar: bool = False):
    """Rótulo junto al punto, en el primer hueco libre a la derecha o a la izquierda, más
    arriba o más abajo, con una línea guía si se aparta del punto. Con ``apartar`` nunca a
    su misma altura, para que quepa una flecha (RF-117). Devuelve su caja."""
    if not texto:
        return None
    ancho = d.textlength(texto, font=fuente)
    for dy in ((-60, 60, -90, 90, -120, 120, -150, 150) if apartar
               else (0, -30, 30, -60, 60, -90, 90, -120, 120, -150, 150)):
        for lado in (1, -1):
            tx = x + 16 if lado == 1 else x - 16 - ancho
            caja = (tx - 3, y + dy - 13, tx + ancho + 3, y + dy + 12)
            dentro = caja[0] >= 0 and caja[2] <= ANCHO_PX - LEYENDA_PX and caja[1] >= MARGEN_PX + 10
            if dentro and not any(caja[0] < o[2] and o[0] < caja[2] and caja[1] < o[3] and o[1] < caja[3]
                                  for o in ocupados):
                break
        else:
            continue
        break
    if dy and not apartar:
        d.line([(x, y), (tx if lado == 1 else tx + ancho, y + dy)], fill=color, width=2)
    d.rectangle(caja, fill='white', outline=color)
    d.text((tx, y + dy - 12), texto, fill=(0, 0, 0), font=fuente)
    ocupados.append(caja)
    return caja


#: Color de la carga nueva y de su rótulo (017:RF-117).
COLOR_CLIENTE = (220, 0, 0)


def rotulo_de_carga(nombre: str, kw: float, codigo: str) -> str:
    """«Carga-{nombre}-{kW} kW-Cod {código del punto de diseño}» (017:RF-117)."""
    return f'Carga-{nombre}-{kw:g} kW-Cod {codigo}'


def _marcar_cliente(d, x: float, y: float, texto: str, fuente, ocupados: list) -> None:
    """Rombo rojo en el punto de conexión y el rótulo apartado con una flecha hacia él."""
    d.polygon([(x, y - 13), (x + 13, y), (x, y + 13), (x - 13, y)], fill=COLOR_CLIENTE, outline=(0, 0, 0))
    caja = _rotular(d, x, y, texto, COLOR_CLIENTE, fuente, ocupados, apartar=True)
    if caja is None:
        return
    # La flecha va del rótulo al punto: la punta, un triángulo sobre el rombo.
    cx = caja[0] if caja[0] > x else caja[2]
    cy = (caja[1] + caja[3]) / 2
    ang = math.atan2(y - cy, x - cx)
    punta = (x - 14 * math.cos(ang), y - 14 * math.sin(ang))
    d.line([(cx, cy), punta], fill=COLOR_CLIENTE, width=3)
    for giro in (2.6, -2.6):
        d.line([punta, (punta[0] + 14 * math.cos(ang + giro), punta[1] + 14 * math.sin(ang + giro))],
               fill=COLOR_CLIENTE, width=3)


#: Paleta de los alimentadores en la vista de ubicación del cliente (017:RF-109).
COLORES_ALIMENTADOR = ((40, 90, 200), (40, 150, 60), (240, 130, 20), (130, 60, 180), (0, 150, 170),
                       (160, 110, 40), (200, 30, 120), (90, 90, 90))
#: Un alimentador es «cercano» si alguna de sus barras está a menos de esto del cliente: a
#: más distancia no es una alternativa de conexión en media tensión.
RADIO_CERCANOS_KM = 3.0


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat = math.radians((a[0] + b[0]) / 2)
    return 111.32 * math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(lat))


def _mercator(lat: float, lon: float) -> tuple[float, float]:
    """(lat, lon) → coordenadas del mundo de las teselas, de 0 a 1 (Web Mercator, EPSG:3857)."""
    lat = max(min(lat, 85.05112878), -85.05112878)
    s = math.sin(math.radians(lat))
    return (lon + 180.0) / 360.0, 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)


def _proyeccion_mercator(puntos: list[tuple[float, float]]):
    """Como :func:`_proyeccion`, en Web Mercator: así cada tesela del fondo es un rectángulo de la imagen.

    En el área de un alimentador las dos coinciden a menos de un píxel; la equirectangular se queda para las
    imágenes sin fondo, que ya tienen sus pruebas.
    """
    mundo = [_mercator(*p) for p in puntos]
    xs, ys = [m[0] for m in mundo], [m[1] for m in mundo]
    ancho, alto = (max(xs) - min(xs)) or 1e-12, (max(ys) - min(ys)) or 1e-12
    util_x = ANCHO_PX - LEYENDA_PX - 2 * MARGEN_PX
    util_y = ALTO_PX - 2 * MARGEN_PX - 40
    escala = min(util_x / ancho, util_y / alto)
    # Un solo punto (una carga sin red cerca) no daría escala: unos 2 km de lado.
    escala = min(escala, util_x / 5e-5)
    x0 = MARGEN_PX + (util_x - ancho * escala) / 2 - min(xs) * escala
    y0 = MARGEN_PX + 40 + (util_y - alto * escala) / 2 - min(ys) * escala

    def a_px(lat: float, lon: float) -> tuple[float, float]:
        mx, my = _mercator(lat, lon)
        return x0 + mx * escala, y0 + my * escala

    def de_px(x: float, y: float) -> tuple[float, float]:
        return (x - x0) / escala, (y - y0) / escala
    return a_px, de_px, escala


#: Teselas como mucho en un fondo: con el zoom elegido caben unas 25; más es un área que no es de un alimentador.
MAX_TESELAS = 64


def _pintar_fondo(img, fondo, de_px, escala: float) -> tuple[int, int]:
    """Pega en ``img`` las teselas de ``fondo`` que caen en la zona del mapa. Devuelve (pegadas, fallidas).

    ``fondo.tesela(z, x, y)`` da los bytes de la imagen o ``None``; nunca lanza: una red caída deja el mapa sin
    fondo, no sin informe (017:RF-112).
    """
    import io

    from PIL import Image

    z = max(0, min(int(getattr(fondo, 'zoom_max', 18)), math.ceil(math.log2(max(escala / 256.0, 1.0)))))
    izq, arr = de_px(0, MARGEN_PX + 10)
    der, aba = de_px(ANCHO_PX - LEYENDA_PX, ALTO_PX)
    while z > 0:
        n = 2 ** z
        cols = range(max(0, math.floor(izq * n)), min(n - 1, math.floor(der * n)) + 1)
        filas = range(max(0, math.floor(arr * n)), min(n - 1, math.floor(aba * n)) + 1)
        if len(cols) * len(filas) <= MAX_TESELAS:
            break
        z -= 1
    n = 2 ** z
    cols = range(max(0, math.floor(izq * n)), min(n - 1, math.floor(der * n)) + 1)
    filas = range(max(0, math.floor(arr * n)), min(n - 1, math.floor(aba * n)) + 1)
    pegadas = fallidas = 0
    ox, oy = de_px(0, 0)
    for tx in cols:
        for ty in filas:
            datos = fondo.tesela(z, tx, ty)
            if not datos:
                fallidas += 1
                continue
            # Las esquinas de la tesela en píxeles (la inversa de ``de_px``), redondeadas cada una: con el lado
            # redondeado aparte quedaban rayas blancas de un píxel entre teselas (Lima, prueba del 2026-11-13).
            x0, y0 = round((tx / n - ox) * escala), round((ty / n - oy) * escala)
            x1, y1 = round(((tx + 1) / n - ox) * escala), round(((ty + 1) / n - oy) * escala)
            try:
                with Image.open(io.BytesIO(datos)) as t:
                    pieza = t.convert('RGB').resize((max(1, x1 - x0), max(1, y1 - y0)))
            except (OSError, ValueError):
                fallidas += 1
                continue
            img.paste(pieza, (x0, y0))
            pegadas += 1
    return pegadas, fallidas


def ubicacion_del_cliente(geos: Mapping[str, Mapping[str, Any]], alimentador: str, barra: str,
                          texto: str, destino: Path, *, titulo: str, punto: Sequence[float] | None = None,
                          fondo=None, sin_fondo: str = '') -> Path:
    """La ubicación del cliente nuevo (017:RF-109, RF-112): su punto de conexión marcado y
    rotulado, y los alimentadores cercanos, cada uno en su color y con su nombre.

    017:RF-111 (2026-11-13, «la ubicación en Google Maps o similar … y eso debe ir en el informe»): con ``fondo``
    (un proveedor de teselas, ``mapa_cargas.fondo_del_informe``) se dibuja sobre calles o satélite, en Web
    Mercator para que cada tesela case con la red; sin él, o si no llega ninguna tesela, sin fondo como hasta
    ahora, y el pie lo dice con ``sin_fondo`` (por qué no hay fondo).

    ``punto``: el GPS del nodo cuando la barra no está en la geografía guardada: el punto de diseño corregido en
    DIgSILENT (017:RF-124) puede ser un nodo que el último flujo de «Con proyecto» todavía no tiene.
    """
    from PIL import Image, ImageDraw

    propia = geos.get(alimentador) or {}
    en_geo = next(((b[1], b[2]) for b in propia.get('barras') or [] if b[0] == barra
                   and b[1] is not None and b[2] is not None), None)
    punto = en_geo or (tuple(float(v) for v in punto[:2]) if punto else None)
    if punto is None:
        raise MapaError(f'La barra {barra} de la carga no tiene coordenadas en la geografía de {alimentador}.')

    def puntos(g):
        return ([(b[1], b[2]) for b in g.get('barras') or [] if b[1] is not None and b[2] is not None]
                + [tuple(p) for t in g.get('tramos') or [] for p in t[1] or []])

    cercanos = [alimentador] + sorted(
        f for f, g in geos.items() if f != alimentador
        and any(_km(punto, p) <= RADIO_CERCANOS_KM for p in puntos(g)))
    todos = [p for f in cercanos for p in puntos(geos.get(f) or {})] + [punto]
    img = Image.new('RGB', (ANCHO_PX, ALTO_PX), 'white')
    pie = PIE_SIN_FONDO + (f'. {sin_fondo}' if sin_fondo else '')
    if fondo is not None:
        a_px, de_px, escala = _proyeccion_mercator(todos)
        pegadas, fallidas = _pintar_fondo(img, fondo, de_px, escala)
        if pegadas:
            pie = f'Fondo de mapa: {fondo.nombre} ({fondo.atribucion})'
            if fallidas:
                pie += f'; faltan {fallidas} teselas que no llegaron'
        else:
            pie = f'{PIE_SIN_FONDO}. No se pudo llegar a {fondo.nombre}: la red se dibuja igual'
    else:
        a_px, _ = _proyeccion(todos)
    d = ImageDraw.Draw(img)
    f_titulo, f_texto = _fuente(30), _fuente(20)
    ocupados: list = []
    for i, f in enumerate(cercanos):
        color = COLORES_ALIMENTADOR[i % len(COLORES_ALIMENTADOR)]
        for t in (geos.get(f) or {}).get('tramos') or []:
            if len(t[1] or []) >= 2:
                d.line([a_px(*p) for p in t[1]], fill=color, width=4 if f == alimentador else 3, joint='curve')
        # El nombre, junto a la cabecera o, sin ella, junto a su primera barra.
        g = geos.get(f) or {}
        cab = next((b for b in g.get('barras') or [] if b[0] == g.get('cabecera')), None)
        ref = cab or next((b for b in g.get('barras') or [] if b[1] is not None), None)
        if ref is not None:
            _rotular(d, *a_px(ref[1], ref[2]), f, color, f_texto, ocupados)
    _marcar_cliente(d, *a_px(*punto), texto, f_texto, ocupados)
    d.rectangle([0, 0, ANCHO_PX, MARGEN_PX + 10], fill='white')
    d.text((MARGEN_PX, 18), titulo, fill=(0, 0, 0), font=f_titulo)
    x0, y = ANCHO_PX - LEYENDA_PX + 10, MARGEN_PX + 50
    d.rectangle([x0 - 10, 0, ANCHO_PX, ALTO_PX], fill='white')
    d.text((x0, y), 'Alimentadores', fill=(0, 0, 0), font=f_texto)
    for i, f in enumerate(cercanos):
        y += 30
        d.rectangle([x0, y, x0 + 28, y + 18], fill=COLORES_ALIMENTADOR[i % len(COLORES_ALIMENTADOR)])
        d.text((x0 + 38, y - 2), f, fill=(0, 0, 0), font=f_texto)
    y += 30
    d.polygon([(x0 + 14, y), (x0 + 28, y + 9), (x0 + 14, y + 18), (x0, y + 9)], fill=COLOR_CLIENTE)
    d.text((x0 + 38, y - 2), 'cliente nuevo', fill=(0, 0, 0), font=f_texto)
    # El pie al pie de la leyenda, en las líneas que hagan falta (RF-112: dice si hay fondo y por qué no).
    lineas = textwrap.wrap(pie + ' (017:RF-112)', width=36)
    for i, linea in enumerate(lineas):
        d.text((x0, ALTO_PX - 20 - 20 * (len(lineas) - i)), linea, fill=(90, 90, 90), font=_fuente(16))
    destino.parent.mkdir(parents=True, exist_ok=True)
    from PIL.PngImagePlugin import PngInfo
    info = PngInfo()
    info.add_text('pie', pie)
    img.save(destino, 'PNG', dpi=(250, 250), pnginfo=info)
    return destino


def transformador_de_la_set(nombre: str, set_nombre: str, devanados: Sequence[tuple[float, float | None]],
                            destino: Path, *, titulo: str, bandas_carga: Sequence[float] | None = None) -> Path:
    """Unifilar del transformador de la SET con la cargabilidad de cada devanado (017:RF-69,
    RF-119): «Cargabilidad devanado {kV} kV {x} %».

    Se dibuja con los números que dio el flujo del proyecto de transmisión: DIgSILENT sin
    ventana no exporta el diagrama (``WriteWMF`` deja el fichero vacío, RF-11b).
    """
    from PIL import Image, ImageDraw

    if not devanados:
        raise MapaError('Sin la cargabilidad de ningún devanado del transformador de la SET.')
    # 086:RF-35: este dibujo ignoraba las bandas del perfil y usaba siempre las constantes.
    bandas = tuple(bandas_carga or BANDAS_CARGA)
    img = Image.new('RGB', (ANCHO_PX, 900), 'white')
    d = ImageDraw.Draw(img)
    f_titulo, f_texto = _fuente(30), _fuente(24)
    d.text((MARGEN_PX, 18), titulo, fill=(0, 0, 0), font=f_titulo)
    cx = ANCHO_PX // 2
    d.line([(cx - 300, 150), (cx + 300, 150)], fill=(0, 0, 0), width=8)            # barra de alta
    d.text((cx + 320, 135), f'SET {set_nombre}', fill=(0, 0, 0), font=f_texto)
    d.line([(cx, 150), (cx, 260)], fill=(0, 0, 0), width=4)
    d.ellipse([cx - 70, 260, cx + 70, 400], outline=(0, 0, 0), width=5)              # primario
    d.text((cx + 170, 300), nombre, fill=(0, 0, 0), font=f_texto)
    n = len(devanados)
    for i, (kv, pct) in enumerate(devanados):
        x = cx + (i - (n - 1) / 2) * 420
        color = (0, 0, 0) if pct is None else _color(_banda(pct, bandas), bandas, COLORES_CARGA)
        d.ellipse([x - 70, 360, x + 70, 500], outline=color, width=5)                # secundario
        d.line([(x, 500), (x, 600)], fill=(0, 0, 0), width=4)
        d.line([(x - 170, 600), (x + 170, 600)], fill=(0, 0, 0), width=8)
        kv_txt = f'{kv:g}'.replace('.', ',')
        texto = (f'Cargabilidad devanado {kv_txt} kV '
                 + ('sin dato' if pct is None else f'{pct:.2f} %'.replace('.', ',')))
        ancho = d.textlength(texto, font=f_texto)
        d.rectangle([x - ancho / 2 - 8, 630, x + ancho / 2 + 8, 670], fill='white', outline=color, width=3)
        d.text((x - ancho / 2, 636), texto, fill=(0, 0, 0), font=f_texto)
    d.text((MARGEN_PX, 860), 'Resultados del flujo del proyecto de transmisión en DIgSILENT',
           fill=(90, 90, 90), font=_fuente(16))
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, 'PNG', dpi=(250, 250))
    return destino


def imagenes_del_estado(geo: Mapping[str, Any], carpeta: Path, prefijo: str, *, estado: str,
                        alimentador: str, bandas_tension=None, bandas_carga=None,
                        obras: Mapping[str, Any] | None = None,
                        cliente: tuple[str, str] | None = None,
                        red: Mapping[str, Any] | None = None,
                        limites: tuple[float, float, float] | None = None,
                        referencia: Mapping[str, Any] | None = None,
                        obras_aplicadas: Sequence[Mapping[str, Any]] = (),
                        obras_activas: Sequence[str] = (),
                        vinculos_equipos: Mapping[str, Mapping[str, str]] | None = None,
                        encuadre: Mapping[str, Any] | None = None) -> dict[str, Path]:
    """Las tres imágenes de un estado del informe: ubicación, tensión y cargabilidad.

    ``obras``: lo que se resalta en el plano de una alternativa (RF-133, ver :func:`dibujar`).
    ``cliente``: ``(barra, rótulo)`` de la carga nueva en el estado proyectado (RF-117).
    ``limites`` activa el plano diagnóstico (063:RF-35): límites explícitos de tensión
    mínima/máxima y cargabilidad. ``red`` conserva la precisión y las tres fases del flujo.
    ``referencia`` es el caso con cargas sin obras, para distinguir sus elementos de los
    refuerzos; los registros de obras se filtran por sus variaciones activas.
    """
    resaltar = None
    geo = esquematico(geo)                                                       # RF-12
    if limites is not None:
        obras, resaltar = _capas_del_estado(geo, red or {}, limites, referencia,
                                          obras_aplicadas, obras_activas, obras, vinculos_equipos or {})
    barras = [b for b in geo.get('barras') or [] if b[3] is not None]
    marcar = []
    if geo.get('cabecera'):
        marcar.append(geo['cabecera'])
    if barras:
        marcar.append(min(barras, key=lambda b: b[3])[0])
    out = {}
    modos = [('ubicacion', 'Vista del alimentador'), ('tension', 'Coloreado por tensión'),
             ('cargabilidad', 'Coloreado por cargabilidad')]
    if obras and any(obras.get(k) for k in ('tramos', 'bancos', 'sets', 'transformadores')):
        modos.append(('detalle', 'Detalle de las obras'))                       # RF-133
    if (resaltar or {}).get('sin_resultados'):
        modos = [('ubicacion', 'Esquema de conexiones: sin resultados eléctricos')]
    for modo, que in modos:
        out[modo] = dibujar(geo, modo, carpeta / f'{prefijo}_{modo}.png',
                            titulo=f'{que} · {alimentador} · {estado}',
                            bandas_tension=bandas_tension, bandas_carga=bandas_carga,
                            marcar=marcar if resaltar is None else (), obras=obras, cliente=cliente,
                            resaltar=resaltar, encuadre=encuadre)
    return out


def _capas_del_estado(geo, red, limites, referencia, registros, activas, obras, vinculos):
    """Capas derivadas de evidencia guardada; no cambia ni redondea el dictamen nativo."""
    sin_resultados = bool(red.get('sin_resultados') or red.get('medida', {}).get('converge') is False)
    capas = {k: list(v) for k, v in (obras or {}).items()}
    for clave in ('tramos', 'bancos', 'existentes', 'sets', 'transformadores', 'sin_localizar',
                  'cargas_nuevas', 'transferencias'):
        capas.setdefault(clave, [])
    anterior = (referencia or {}).get('geo_proyecto') or {}
    tramos_antes = {t[0]: t for t in anterior.get('tramos', ())}
    barras = {b[0]: b for b in geo.get('barras', ()) if b[1] is not None and b[2] is not None}
    tramos = {t[0]: t for t in geo.get('tramos', ()) if len(t[1] or ()) >= 2}
    vinculos = {n: dato['barra'] for n, dato in vinculos.items() if dato.get('barra') in barras}
    hay_obras = (any(r.get('variacion') in activas and (r.get('obra') or {}).get('clase') != 'carga_nueva'
                     for r in registros) if registros else bool(activas))
    if referencia is not None and hay_obras:
        for nombre, tramo in tramos.items():
            previo = tramos_antes.get(nombre)
            if previo is None or (len(tramo) > 5 and len(previo) > 5 and tramo[5] != previo[5]):
                capas['tramos'].append(nombre)
    for registro in registros:
        if registro.get('variacion') not in activas:
            continue
        obra = registro.get('obra') or {}
        if obra.get('clase') in ('transformador', 'carga_nueva') and obra.get('elemento'):
            nombre = obra['elemento']
            if nombre in vinculos:
                clave = 'transformadores' if obra['clase'] == 'transformador' else 'cargas_nuevas'
                capas[clave].append((nombre, vinculos[nombre]))
            else:
                capas['sin_localizar'].append(nombre)
        if obra.get('clase') == 'transferencia' and obra.get('outserv') == 1 and obra.get('elemento'):
            pts = obra.get('geometria') or []
            if len(pts) < 2 or not all(isinstance(p, (list, tuple)) and len(p) == 2
                                          and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p)
                                          for p in pts):
                pts = []
            capas['transferencias'].append({'elemento': obra['elemento'], 'geometria': pts})
        if obra.get('clase') in ('terna', 'seccion', 'conductor'):
            capas['tramos'].extend(n for n in obra.get('tramos', ()) if n in tramos)
        if obra.get('clase') == 'set_nueva':
            # El destino explícito vincula la SET a sus barras; no se adivina por prefijo.
            destino = obra.get('destino', '')
            try:
                lat, lon = (float(x.strip()) for x in destino.split(','))
            except (ValueError, AttributeError):
                continue
            candidatas = [b for b in barras.values() if abs(b[1] - lat) < 1e-6 and abs(b[2] - lon) < 1e-6]
            if candidatas:
                barra = min(candidatas, key=lambda b: b[4] or float('inf'))
                capas['sets'].append((barra[0], obra.get('nombre_set') or 'SET nueva'))
    bancos_antes = {b['nombre'] for b in ((referencia or {}).get('red_proyecto') or {}).get('medida', {}).get('bancos', ())}
    for banco in red.get('medida', {}).get('bancos', ()):
        if banco.get('en_servicio') is False:
            continue
        nuevo = referencia is not None and banco['nombre'] not in bancos_antes and hay_obras
        capas['bancos' if nuevo else 'existentes'].append(
            (banco['barra'], banco['kvar'] * (banco.get('escalones') or 1)))
    capas['tramos'] = list(dict.fromkeys(capas['tramos']))
    umin, umax, carga_max = limites
    tensiones = []
    exactas = [b for filas in red.get('tensiones_por_nivel', {}).values() for b in filas]
    if exactas:
        for b in exactas:
            valores = [u for u in b.get('fases', {}).values() if u is not None]
            valores = valores or ([b['u_pu']] if b.get('u_pu') is not None else [])
            if valores and (min(valores) < umin or max(valores) > umax):
                tensiones.append((b['nombre'], min(valores), max(valores)))
    else:
        tensiones = [(b[0], b[3], b[3]) for b in geo.get('barras', ())
                     if b[3] is not None and not umin <= b[3] <= umax]
    elementos = red.get('medida', {}).get('elementos')
    if elementos is None:
        elementos = [(t[0], 'ElmLne', t[2]) for t in tramos.values()]
    sobre = [(n, cl, c) for n, cl, c in elementos if c is not None and c > carga_max]
    if sin_resultados:
        tensiones, sobre = [], []
    sin_localizar = [n for n, _, _ in tensiones if n not in barras]
    sin_localizar += [n for n, _, _ in sobre if n not in barras and n not in tramos and n not in vinculos]
    peores_u = sorted((t for t in tensiones if t[0] in barras), key=lambda t: min(t[1] - umin, umax - t[2]))[:2]
    peores_c = sorted((t for t in sobre if t[0] in tramos or t[0] in barras or t[0] in vinculos), key=lambda t: -t[2])[:3]
    rotulos = [('U', n, f'{lo:.4f}–{hi:.4f} p.u.') for n, lo, hi in peores_u]
    rotulos += [('C', n, f'{c:.2f} %') for n, _, c in peores_c]
    resumen = [f'Límites: {umin:g}–{umax:g} p.u.; carga ≤ {carga_max:g} %.',
               f'Fuera: {len(tensiones)} barras; {len(sobre)} equipos.',
               f'Sin GPS/vínculo: {len(sin_localizar)} (ver CSV).']
    if sin_resultados:
        resumen = ['No converge: sin resultados eléctricos.',
                   'Solo conexiones y demandas nominales identificadas.']
    resumen += [f'P{i}: {n} / {valor}' for i, (_, n, valor) in enumerate(rotulos, 1)]
    resumen += [f'R{i}: TR reforzado {n}' for i, (n, _) in enumerate(capas['transformadores'], 1)]
    resumen += [f'A{i}: {o["elemento"]}, abierto por transferencia'
                + (' (sin geometría)' if not o['geometria'] else '')
                for i, o in enumerate(capas['transferencias'], 1)]
    if capas['sin_localizar']:
        resumen.append('Obras sin vínculo GPS: ' + ', '.join(capas['sin_localizar']))
    return capas, {'tension': tensiones, 'carga': sobre, 'sin_localizar': sin_localizar,
                   'rotulos': rotulos, 'resumen': resumen, 'vinculos': vinculos,
                   'sin_resultados': sin_resultados}
