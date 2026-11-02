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
import json
import textwrap
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
COLOR_PROBLEMA_TENSION = (235, 110, 0)
COLOR_SOBRECARGA = (190, 20, 20)
COLOR_SET = (95, 45, 170)
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

    barras = [b for b in geo.get('barras') or [] if b[1] is not None and b[2] is not None]
    tramos = [t for t in geo.get('tramos') or [] if len(t[1] or []) >= 2]
    puntos = [(b[1], b[2]) for b in barras] + [tuple(p) for t in tramos for p in t[1]]
    if not puntos:
        raise MapaError('El estudio no guardó la geografía del alimentador: vuelva a ejecutar '
                        'el estudio de flujo.')
    obras = obras or {}
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
    u_de = {b[0]: b[3] for b in barras}

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
        # Dos canales: la alarma nunca se sustituye por el color de una obra aplicada.
        sobre = {e[0]: e[2] for e in resaltar['carga']}
        for t in tramos:
            if t[0] in sobre:
                _linea_discontinua(d, [a_px(*p) for p in t[1]], COLOR_SOBRECARGA, 13)
                if t[0] in cambiados:
                    d.line([a_px(*p) for p in t[1]], fill=COLOR_CONDUCTOR, width=4)
        for n, _, _ in resaltar['carga']:
            b = posicion.get(resaltar['vinculos'].get(n, n))
            if b is not None:
                x, y = a_px(b[1], b[2])
                d.rectangle([x - 10, y - 10, x + 10, y + 10], outline=COLOR_SOBRECARGA, width=4)
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
    while d.textlength(titulo, font=f_titulo) > ANCHO_PX - 2 * MARGEN_PX:
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
        filas += [(COLOR_PROBLEMA_TENSION, 'tensión fuera (círculo)'),
                  ('discontinua', 'sobrecarga (guion/cuadro)'),
                  (COLOR_CLIENTE, 'punto cliente (rombo)')]
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
    d.text((x0, ALTO_PX - 40), 'Resultados del flujo de DIgSILENT', fill=(90, 90, 90),
           font=_fuente(16))
    destino.parent.mkdir(parents=True, exist_ok=True)
    from PIL.PngImagePlugin import PngInfo
    info = PngInfo()
    if resaltar is not None:
        evidencia = {'tension_fuera': [x[0] for x in resaltar['tension']],
                     'sobrecargas': [x[0] for x in resaltar['carga']],
                     'sin_localizar': resaltar['sin_localizar'], 'obras_tramos': list(obras.get('tramos') or ()),
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
    for (x1, y1), (x2, y2) in zip(puntos, puntos[1:]):
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


def ubicacion_del_cliente(geos: Mapping[str, Mapping[str, Any]], alimentador: str, barra: str,
                          texto: str, destino: Path, *, titulo: str) -> Path:
    """La ubicación del cliente nuevo (017:RF-109, RF-112): su punto de conexión marcado y
    rotulado, y los alimentadores cercanos, cada uno en su color y con su nombre.

    No hay mapa de fondo: dibujarlo pediría las coordenadas a un servicio de teselas, y el
    informe se arma sin enviar la red fuera (RF-111); el pie lo dice.
    """
    from PIL import Image, ImageDraw

    propia = geos.get(alimentador) or {}
    punto = next(((b[1], b[2]) for b in propia.get('barras') or [] if b[0] == barra
                  and b[1] is not None and b[2] is not None), None)
    if punto is None:
        raise MapaError(f'La barra {barra} de la carga no tiene coordenadas en la geografía de {alimentador}.')

    def puntos(g):
        return ([(b[1], b[2]) for b in g.get('barras') or [] if b[1] is not None and b[2] is not None]
                + [tuple(p) for t in g.get('tramos') or [] for p in t[1] or []])

    cercanos = [alimentador] + sorted(
        f for f, g in geos.items() if f != alimentador
        and any(_km(punto, p) <= RADIO_CERCANOS_KM for p in puntos(g)))
    todos = [p for f in cercanos for p in puntos(geos[f])]
    a_px, _ = _proyeccion(todos)
    img = Image.new('RGB', (ANCHO_PX, ALTO_PX), 'white')
    d = ImageDraw.Draw(img)
    f_titulo, f_texto = _fuente(30), _fuente(20)
    ocupados: list = []
    for i, f in enumerate(cercanos):
        color = COLORES_ALIMENTADOR[i % len(COLORES_ALIMENTADOR)]
        for t in geos[f].get('tramos') or []:
            if len(t[1] or []) >= 2:
                d.line([a_px(*p) for p in t[1]], fill=color, width=4 if f == alimentador else 3, joint='curve')
        # El nombre, junto a la cabecera o, sin ella, junto a su primera barra.
        cab = next((b for b in geos[f].get('barras') or [] if b[0] == geos[f].get('cabecera')), None)
        ref = cab or next((b for b in geos[f].get('barras') or [] if b[1] is not None), None)
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
    d.text((x0, ALTO_PX - 60), 'Sin mapa de fondo: dibujado con las', fill=(90, 90, 90), font=_fuente(16))
    d.text((x0, ALTO_PX - 40), 'coordenadas de la red (RF-112)', fill=(90, 90, 90), font=_fuente(16))
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino, 'PNG', dpi=(250, 250))
    return destino


def transformador_de_la_set(nombre: str, set_nombre: str, devanados: Sequence[tuple[float, float | None]],
                            destino: Path, *, titulo: str) -> Path:
    """Unifilar del transformador de la SET con la cargabilidad de cada devanado (017:RF-69,
    RF-119): «Cargabilidad devanado {kV} kV {x} %».

    Se dibuja con los números que dio el flujo del proyecto de transmisión: DIgSILENT sin
    ventana no exporta el diagrama (``WriteWMF`` deja el fichero vacío, RF-11b).
    """
    from PIL import Image, ImageDraw

    if not devanados:
        raise MapaError('Sin la cargabilidad de ningún devanado del transformador de la SET.')
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
        color = (0, 0, 0) if pct is None else _color(_banda(pct, BANDAS_CARGA), BANDAS_CARGA, COLORES_CARGA)
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
    if obras and (obras.get('tramos') or obras.get('bancos') or obras.get('sets')):
        modos.append(('detalle', 'Detalle de las obras'))                       # RF-133
    for modo, que in modos:
        out[modo] = dibujar(geo, modo, carpeta / f'{prefijo}_{modo}.png',
                            titulo=f'{que} · {alimentador} · {estado}',
                            bandas_tension=bandas_tension, bandas_carga=bandas_carga,
                            marcar=marcar if resaltar is None else (), obras=obras, cliente=cliente,
                            resaltar=resaltar, encuadre=encuadre)
    return out


def _capas_del_estado(geo, red, limites, referencia, registros, activas, obras, vinculos):
    """Capas derivadas de evidencia guardada; no cambia ni redondea el dictamen nativo."""
    capas = {k: list(v) for k, v in (obras or {}).items()}
    for clave in ('tramos', 'bancos', 'existentes', 'sets'):
        capas.setdefault(clave, [])
    anterior = (referencia or {}).get('geo_proyecto') or {}
    tramos_antes = {t[0]: t for t in anterior.get('tramos', ())}
    barras = {b[0]: b for b in geo.get('barras', ()) if b[1] is not None and b[2] is not None}
    tramos = {t[0]: t for t in geo.get('tramos', ()) if len(t[1] or ()) >= 2}
    vinculos = {n: dato['barra'] for n, dato in vinculos.items() if dato.get('barra') in barras}
    if referencia is not None and activas:
        for nombre, tramo in tramos.items():
            previo = tramos_antes.get(nombre)
            if previo is None or (len(tramo) > 5 and len(previo) > 5 and tramo[5] != previo[5]):
                capas['tramos'].append(nombre)
    for registro in registros:
        if registro.get('variacion') not in activas:
            continue
        obra = registro.get('obra') or {}
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
        nuevo = referencia is not None and banco['nombre'] not in bancos_antes and bool(activas)
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
    sin_localizar = [n for n, _, _ in tensiones if n not in barras]
    sin_localizar += [n for n, _, _ in sobre if n not in barras and n not in tramos and n not in vinculos]
    peores_u = sorted((t for t in tensiones if t[0] in barras), key=lambda t: min(t[1] - umin, umax - t[2]))[:2]
    peores_c = sorted((t for t in sobre if t[0] in tramos or t[0] in barras or t[0] in vinculos), key=lambda t: -t[2])[:3]
    rotulos = [('U', n, f'{lo:.4f}–{hi:.4f} p.u.') for n, lo, hi in peores_u]
    rotulos += [('C', n, f'{c:.2f} %') for n, _, c in peores_c]
    resumen = [f'Límites: {umin:g}–{umax:g} p.u.; carga ≤ {carga_max:g} %.',
               f'Fuera: {len(tensiones)} barras; {len(sobre)} equipos.',
               f'Sin GPS/vínculo: {len(sin_localizar)} (ver CSV).']
    resumen += [f'P{i}: {n} / {valor}' for i, (_, n, valor) in enumerate(rotulos, 1)]
    return capas, {'tension': tensiones, 'carga': sobre, 'sin_localizar': sin_localizar,
                   'rotulos': rotulos, 'resumen': resumen, 'vinculos': vinculos}
