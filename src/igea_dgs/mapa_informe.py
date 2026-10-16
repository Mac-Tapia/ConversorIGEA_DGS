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
#: Obras resaltadas en el plano de una alternativa (017:RF-133).
COLOR_CONDUCTOR = (200, 0, 160)
COLOR_BANCO = (0, 150, 170)
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
            marcar: Sequence[str] = (), obras: Mapping[str, Any] | None = None) -> Path:
    """La imagen ``modo`` (``ubicacion``, ``tension`` o ``cargabilidad``) en ``destino``.

    ``marcar``: barras que se señalan con su nombre (la cabecera y la de menor tensión).
    ``obras`` (017:RF-133), en la vista de ubicación y en ``detalle``: ``tramos`` con el
    conductor nuevo, ``trechos`` como ``[(desde, hasta), ...]``, ``bancos`` nuevos y
    ``existentes`` como ``[(barra, kvar), ...]``. ``detalle`` es la vista de ubicación
    ampliada sobre la zona de las obras: en CA101 el cambio de 6,6 km quedaba en una
    esquina del alimentador entero, con los rótulos unos encima de otros.
    """
    from PIL import Image, ImageDraw

    barras = [b for b in geo.get('barras') or [] if b[1] is not None and b[2] is not None]
    tramos = [t for t in geo.get('tramos') or [] if len(t[1] or []) >= 2]
    puntos = [(b[1], b[2]) for b in barras] + [tuple(p) for t in tramos for p in t[1]]
    if not puntos:
        raise MapaError('El estudio no guardó la geografía del alimentador: vuelva a ejecutar '
                        'el estudio de flujo.')
    obras = obras or {}
    if modo == 'detalle':
        zona = _zona_de_obras(barras, tramos, obras)
        if zona:
            puntos = zona
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
            color, ancho = (GRIS, 3) if modo not in PLANOS else ((60, 60, 60), 3)
        d.line([a_px(*p) for p in pts], fill=color, width=ancho, joint='curve')
    if modo in PLANOS:
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
    if modo in PLANOS:
        trechos = list(obras.get('trechos') or ())
        for i, (desde, hasta) in enumerate(trechos, 1):
            n = f' {i}' if len(trechos) > 1 else ''
            rotulos += [(desde, f'Inicio{n}: {desde}', COLOR_CONDUCTOR, 'cuadro'),
                        (hasta, f'Fin{n}: {hasta}', COLOR_CONDUCTOR, 'cuadro')]
        for barra, kvar in _por_barra(obras.get('existentes') or ()):
            rotulos.append((barra, f'Banco existente {kvar:g} kvar', COLOR_BANCO, 'hueco'))
        for barra, kvar in _por_barra(obras.get('bancos') or ()):
            rotulos.append((barra, f'Banco nuevo {kvar:g} kvar · {barra}', COLOR_BANCO, 'lleno'))
    rotulos += [(n, '', (0, 0, 0), 'circulo') for n in marcar]
    posicion = {b[0]: b for b in barras}
    ocupados: list[tuple[float, float, float, float]] = []
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

    d.rectangle([0, 0, ANCHO_PX, MARGEN_PX + 10], fill='white')
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
    d.text((x0, y), cabeza, fill=(0, 0, 0), font=f_texto)
    y += 34
    for color, rotulo in filas:
        if color == 'hueco':
            d.rectangle([x0, y, x0 + 28, y + 18], fill='white', outline=COLOR_BANCO, width=4)
        else:
            d.rectangle([x0, y, x0 + 28, y + 18], fill=color)
        d.text((x0 + 38, y - 2), rotulo, fill=(0, 0, 0), font=f_texto)
        y += 30
    d.text((x0, ALTO_PX - 40), 'Resultados del flujo de DIgSILENT', fill=(90, 90, 90),
           font=_fuente(16))
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, 'PNG', dpi=(250, 250))
    return destino


#: Vistas de ubicación: la del alimentador entero y la ampliada sobre las obras.
PLANOS = ('ubicacion', 'detalle')
#: Margen de la vista de detalle alrededor de las obras, en grados (unos 300 m).
MARGEN_DETALLE_GRADOS = 0.003


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
    pts = [tuple(p) for t in tramos if t[0] in cambiados for p in t[1]]
    pts += [(b[1], b[2]) for b in barras if b[0] in marcadas]
    if not pts:
        return []
    m = MARGEN_DETALLE_GRADOS
    lats, lons = [p[0] for p in pts], [p[1] for p in pts]
    return [(min(lats) - m, min(lons) - m), (max(lats) + m, max(lons) + m)]


def _rotular(d, x: float, y: float, texto: str, color, fuente, ocupados: list) -> None:
    """Rótulo junto al punto, en el primer hueco libre a la derecha o a la izquierda, más
    arriba o más abajo, con una línea guía si se aparta del punto."""
    if not texto:
        return
    ancho = d.textlength(texto, font=fuente)
    for dy in (0, -30, 30, -60, 60, -90, 90, -120, 120, -150, 150):
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
    if dy:
        d.line([(x, y), (tx if lado == 1 else tx + ancho, y + dy)], fill=color, width=2)
    d.rectangle(caja, fill='white', outline=color)
    d.text((tx, y + dy - 12), texto, fill=(0, 0, 0), font=fuente)
    ocupados.append(caja)


def imagenes_del_estado(geo: Mapping[str, Any], carpeta: Path, prefijo: str, *, estado: str,
                        alimentador: str, bandas_tension=None, bandas_carga=None,
                        obras: Mapping[str, Any] | None = None) -> dict[str, Path]:
    """Las tres imágenes de un estado del informe: ubicación, tensión y cargabilidad.

    ``obras``: lo que se resalta en el plano de una alternativa (RF-133, ver :func:`dibujar`).
    """
    barras = [b for b in geo.get('barras') or [] if b[3] is not None]
    marcar = []
    if geo.get('cabecera'):
        marcar.append(geo['cabecera'])
    if barras:
        marcar.append(min(barras, key=lambda b: b[3])[0])
    out = {}
    modos = [('ubicacion', 'Vista del alimentador'), ('tension', 'Coloreado por tensión'),
             ('cargabilidad', 'Coloreado por cargabilidad')]
    if obras and (obras.get('tramos') or obras.get('bancos')):
        modos.append(('detalle', 'Detalle de las obras'))                       # RF-133
    for modo, que in modos:
        out[modo] = dibujar(geo, modo, carpeta / f'{prefijo}_{modo}.png',
                            titulo=f'{que} · {alimentador} · {estado}',
                            bandas_tension=bandas_tension, bandas_carga=bandas_carga,
                            marcar=marcar, obras=obras)
    return out
