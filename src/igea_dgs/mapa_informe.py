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

import math
from collections.abc import Mapping, Sequence
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
#: Bandas por defecto si el perfil no las trae: las del modelo EMAPICA (017:RF-115).
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
            marcar: Sequence[str] = ()) -> Path:
    """La imagen ``modo`` (``ubicacion``, ``tension`` o ``cargabilidad``) en ``destino``.

    ``marcar``: barras que se señalan con su nombre (la cabecera y la de menor tensión).
    """
    from PIL import Image, ImageDraw

    barras = [b for b in geo.get('barras') or [] if b[1] is not None and b[2] is not None]
    tramos = [t for t in geo.get('tramos') or [] if len(t[1] or []) >= 2]
    puntos = [(b[1], b[2]) for b in barras] + [tuple(p) for t in tramos for p in t[1]]
    if not puntos:
        raise MapaError('El estudio no guardó la geografía del alimentador: vuelva a ejecutar '
                        'el estudio de flujo.')
    a_px, _ = _proyeccion(puntos)
    bt = tuple(bandas_tension or BANDAS_TENSION)
    bc = tuple(bandas_carga or BANDAS_CARGA)
    img = Image.new('RGB', (ANCHO_PX, ALTO_PX), 'white')
    d = ImageDraw.Draw(img)
    u_de = {b[0]: b[3] for b in barras}

    for nombre, pts, carga in ((t[0], t[1], t[2]) for t in tramos):
        if modo == 'cargabilidad' and carga is not None:
            color = _color(_banda(carga, bc), bc, COLORES_CARGA)
            ancho = 5 if carga > 100.0 else 3
        else:
            color, ancho = (GRIS, 3) if modo != 'ubicacion' else ((60, 60, 60), 3)
        d.line([a_px(*p) for p in pts], fill=color, width=ancho, joint='curve')
    if modo in ('tension', 'ubicacion'):
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
    for nombre in marcar:
        b = next((b for b in barras if b[0] == nombre), None)
        if b is None:
            continue
        x, y = a_px(b[1], b[2])
        d.ellipse([x - 11, y - 11, x + 11, y + 11], outline=(0, 0, 0), width=3)
        texto = nombre if b[3] is None else f'{nombre} · {b[3]:.3f} p.u.'
        ancho_texto = d.textlength(texto, font=f_texto)
        # Si no cabe a la derecha sin pisar la leyenda, el rótulo va a la izquierda.
        tx = x + 14 if x + 14 + ancho_texto < ANCHO_PX - LEYENDA_PX else x - 14 - ancho_texto
        d.rectangle([tx - 3, y - 13, tx + ancho_texto + 3, y + 12], fill='white')
        d.text((tx, y - 12), texto, fill=(0, 0, 0), font=f_texto)

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
        cabeza = 'Alimentador'
    d.text((x0, y), cabeza, fill=(0, 0, 0), font=f_texto)
    y += 34
    for color, rotulo in filas:
        d.rectangle([x0, y, x0 + 28, y + 18], fill=color)
        d.text((x0 + 38, y - 2), rotulo, fill=(0, 0, 0), font=f_texto)
        y += 30
    d.text((x0, ALTO_PX - 40), 'Resultados del flujo de DIgSILENT', fill=(90, 90, 90),
           font=_fuente(16))
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, 'PNG', dpi=(250, 250))
    return destino


def imagenes_del_estado(geo: Mapping[str, Any], carpeta: Path, prefijo: str, *, estado: str,
                        alimentador: str, bandas_tension=None, bandas_carga=None) -> dict[str, Path]:
    """Las tres imágenes de un estado del informe: ubicación, tensión y cargabilidad."""
    barras = [b for b in geo.get('barras') or [] if b[3] is not None]
    marcar = []
    if geo.get('cabecera'):
        marcar.append(geo['cabecera'])
    if barras:
        marcar.append(min(barras, key=lambda b: b[3])[0])
    out = {}
    for modo, que in (('ubicacion', 'Vista del alimentador'), ('tension', 'Coloreado por tensión'),
                      ('cargabilidad', 'Coloreado por cargabilidad')):
        out[modo] = dibujar(geo, modo, carpeta / f'{prefijo}_{modo}.png',
                            titulo=f'{que} · {alimentador} · {estado}',
                            bandas_tension=bandas_tension, bandas_carga=bandas_carga,
                            marcar=marcar)
    return out
