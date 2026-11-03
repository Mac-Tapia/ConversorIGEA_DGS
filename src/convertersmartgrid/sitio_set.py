"""Sitio de una SET nueva: ni sobre la calle ni encima de los alimentadores (spec 084, RF-1 a RF-11).

Usuario, 2026-11-02, al revisar una SET nueva: «debe quedar en un área libre». El punto de Weber
(042:RF-9) y el ajuste por tensiones (042:RF-10) solo miran la electricidad, y acercar la SET a la barra
que cae la lleva justo hacia el trazado de la red. Una subestación necesita un predio.

Lo que aquí se comprueba es lo que los datos propios permiten: la distancia al trazado de los
alimentadores y, si la empresa da su fichero local, a las calles. Sin ese fichero el punto queda «sin
verificar en plano»: ningún dato de calles se inventa ni se consulta fuera. Tampoco con el fichero se dice
que el área esté libre: el predio y las viviendas solo se ven en el plano (084:RF-7).
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .set_nueva import M_POR_GRADO

Punto = tuple[float, float]
Trazado = tuple[str, Sequence[Sequence[float]]]

#: Hasta cuántos retiros se busca un sitio, a medio retiro por anillo: es el alcance de la búsqueda, no
#: una distancia de la empresa; más lejos, las salidas ya no son las que se dimensionaron.
ALCANCE_RETIROS = 20
DIRECCIONES = 16
#: Por debajo de esto dos puntos son el mismo: redondeos del GPS guardado (084:RF-10).
MISMO_PUNTO_M = 1.0

SIN_VERIFICAR = 'sin_verificar_en_plano'
SOBRE_ALIMENTADOR = 'sobre_alimentador'
SOBRE_CALLE = 'sobre_calle'
APARTADO = 'apartado_de_red_y_calles'


@dataclass(frozen=True)
class ParametrosSitio:
    """De ``planificacion.sitio_set`` del perfil; sin él no se supone ninguna distancia (P13)."""

    retiro_m: float | None = None
    calles: tuple[Trazado, ...] = ()
    avisos: tuple[str, ...] = ()


def leer_calles(ruta: str | Path | None) -> tuple[tuple[Trazado, ...], tuple[str, ...]]:
    """Las calles de un GeoJSON local de la empresa (084:RF-4); solo se lee el disco (084:RF-5).

    Un fichero que falta o no se entiende no impide nada: el punto queda sin verificar y se dice.
    """
    if not ruta:
        return (), ()
    try:
        datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
        calles: list[Trazado] = []
        for i, f in enumerate(datos.get('features') or []):
            g = f.get('geometry') or {}
            lineas = {'LineString': [g.get('coordinates')], 'MultiLineString': g.get('coordinates')}.get(g.get('type'))
            for linea in lineas or []:
                # GeoJSON va en lon, lat; aquí, como el GPS de DIgSILENT, lat, lon.
                calles.append((str((f.get('properties') or {}).get('name') or f'calle {i + 1}'),
                               [(float(p[1]), float(p[0])) for p in linea]))
    except (OSError, ValueError, TypeError, AttributeError, IndexError) as exc:
        return (), (f'No se pudo leer el fichero de calles {ruta}: {exc}; el sitio queda sin verificar en plano '
                    '(084:RF-5).',)
    return tuple(calles), ()


def parametros(perfil: Mapping[str, Any] | None) -> ParametrosSitio:
    cfg = dict(((perfil or {}).get('planificacion') or {}).get('sitio_set') or {})
    calles, avisos = leer_calles(cfg.get('calles_geojson'))
    retiro = cfg.get('retiro_min_m')
    return ParametrosSitio(float(retiro) if retiro else None, calles, avisos)


def trazados_de_red(barras: Sequence[Mapping[str, Any]], tramos: Sequence[Mapping[str, Any]]) -> list[Trazado]:
    """Los trazados de una red leída: los puntos del tramo o, sin ellos, la recta entre sus dos barras."""
    gps = {b.get('nombre'): b.get('gps') for b in barras}
    out: list[Trazado] = []
    for t in tramos:
        puntos = t.get('puntos') or [p for p in (gps.get(t.get('desde')), gps.get(t.get('hasta'))) if p]
        if puntos:
            out.append((str(t.get('nombre')), puntos))
    return out


def _segmentos(trazados: Sequence[Trazado], origen: Punto) -> tuple[np.ndarray, list[str]]:
    """Cada trazado en metros alrededor de ``origen``: ``[ax, ay, bx, by]`` por segmento y su nombre."""
    coseno = math.cos(math.radians(origen[0]))
    filas, nombres = [], []
    for nombre, puntos in trazados:
        xy = [((float(p[1]) - origen[1]) * M_POR_GRADO * coseno, (float(p[0]) - origen[0]) * M_POR_GRADO)
              for p in puntos]
        for a, b in zip(xy, xy[1:] or xy):
            filas.append((*a, *b))
            nombres.append(nombre)
    return np.array(filas, dtype=float).reshape(-1, 4), nombres


def _distancias(x: float, y: float, seg: np.ndarray) -> np.ndarray:
    d = seg[:, 2:] - seg[:, :2]
    largo2 = (d * d).sum(axis=1)
    relativo = np.array([x, y]) - seg[:, :2]
    t = np.clip((relativo * d).sum(axis=1) / np.where(largo2 > 0, largo2, 1.0), 0.0, 1.0)
    resto = relativo - t[:, None] * d
    return np.hypot(resto[:, 0], resto[:, 1])


def distancia_a_trazados(punto: Punto, trazados: Sequence[Trazado]) -> tuple[float | None, str | None]:
    """Los metros al trazado más cercano y su nombre; sin trazados, ``None`` (084:RF-1)."""
    seg, nombres = _segmentos(trazados, punto)
    if not len(seg):
        return None, None
    d = _distancias(0.0, 0.0, seg)
    i = int(np.argmin(d))
    return float(d[i]), nombres[i]


def apartar(punto: Punto, trazados: Sequence[Trazado], calles: Sequence[Trazado], retiro_m: float) -> Punto | None:
    """El punto más cercano, por anillos, a ``retiro_m`` de la red y de las calles (084:RF-2).

    Determinista: mismo orden de anillos y direcciones. Devuelve el mismo punto si ya cumple y ``None`` si
    no hay ninguno al alcance: una red densa puede no dejar sitio, y eso se dice (084:RF-3).
    """
    seg, _ = _segmentos([*trazados, *calles], punto)
    if not len(seg) or float(_distancias(0.0, 0.0, seg).min()) >= retiro_m:
        return punto
    coseno = math.cos(math.radians(punto[0]))
    paso = retiro_m / 2
    for anillo in range(1, 2 * ALCANCE_RETIROS + 1):
        for k in range(DIRECCIONES):
            angulo = 2 * math.pi * k / DIRECCIONES
            x, y = anillo * paso * math.cos(angulo), anillo * paso * math.sin(angulo)
            if float(_distancias(x, y, seg).min()) >= retiro_m:
                return punto[0] + y / M_POR_GRADO, punto[1] + x / (M_POR_GRADO * coseno)
    return None


def revisar(punto: Punto, trazados: Sequence[Trazado], p: ParametrosSitio) -> dict[str, Any]:
    """El estado de un punto, con sus distancias y lo que queda sin comprobar (084:RF-1, RF-4 a RF-7)."""
    a_red, tramo = distancia_a_trazados(punto, trazados)
    a_calle, calle = distancia_a_trazados(punto, p.calles)
    avisos = list(p.avisos)
    if p.retiro_m is None:
        # 084:RF-6: la distancia se da igual; sin el dato de la empresa no se juzga.
        avisos.append('El perfil no da planificacion.sitio_set.retiro_min_m: se dice la distancia a la red y el '
                      'punto no se aparta (084:RF-6).')
    if a_red is None:
        avisos.append('No hay trazado de la red con GPS: no se pudo medir la distancia a los alimentadores '
                      '(084:RF-1).')
    if not p.calles:
        avisos.append('Sin datos locales de calles (planificacion.sitio_set.calles_geojson): el punto queda '
                      'sin verificar en plano (084:RF-5).')
    if p.retiro_m is not None and a_red is not None and a_red < p.retiro_m:
        estado = SOBRE_ALIMENTADOR
    elif p.retiro_m is not None and a_calle is not None and a_calle < p.retiro_m:
        estado = SOBRE_CALLE
    elif p.retiro_m is None or a_red is None or a_calle is None:
        estado = SIN_VERIFICAR
    else:
        estado = APARTADO
    return {'lat': punto[0], 'lon': punto[1], 'estado': estado, 'retiro_m': p.retiro_m,
            'a_alimentador_m': a_red, 'tramo_cercano': tramo, 'a_calle_m': a_calle, 'calle_cercana': calle,
            'avisos': avisos}


def situar(punto: Punto, trazados: Sequence[Trazado], p: ParametrosSitio) -> dict[str, Any]:
    """Aparta el punto si hace falta y dice el resultado, sin impedir nada (084:RF-2, RF-3)."""
    destino: Punto | None = punto
    if p.retiro_m is not None:
        destino = apartar(punto, trazados, p.calles, p.retiro_m)
    sin_sitio = destino is None
    final = punto if destino is None else destino
    r = revisar(final, trazados, p)
    r['movido'] = not mismo_punto(final, punto)
    r['original'] = {'lat': punto[0], 'lon': punto[1]}
    if sin_sitio:
        r['avisos'].append(f'Ningún punto a {ALCANCE_RETIROS} retiros deja {p.retiro_m:g} m libres de la red y de las '
                           'calles: queda el punto original, y hay que elegirlo en el plano (084:RF-3).')
    elif r['movido']:
        r['avisos'].append(f'El punto se apartó {_metros(final, punto):.0f} m para dejar {p.retiro_m:g} m libres de la '
                           'red y de las calles; los flujos se miden en el punto nuevo (084:RF-2, RF-8).')
    r['frase'] = frase(r)
    return r


def _metros(a: Punto, b: Punto) -> float:
    coseno = math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[0] - b[0]) * M_POR_GRADO, (a[1] - b[1]) * M_POR_GRADO * coseno)


def mismo_punto(a: Punto, b: Punto) -> bool:
    return _metros(a, b) <= MISMO_PUNTO_M


def flujos_al_dia(final: Punto, medidos: Mapping[str, Any] | None) -> bool:
    """Si los flujos guardados se midieron en el punto donde queda la SET (084:RF-10)."""
    if not medidos or medidos.get('lat') is None or medidos.get('lon') is None:
        return False
    return mismo_punto(final, (float(medidos['lat']), float(medidos['lon'])))


def frase(r: Mapping[str, Any]) -> str:
    """El sitio para el operador. Nunca dice «área libre»: eso solo se ve en el plano (084:RF-7)."""
    partes = []
    if r.get('a_alimentador_m') is not None:
        partes.append(f"a {r['a_alimentador_m']:.0f} m del alimentador más cercano ({r.get('tramo_cercano')})")
    if r.get('a_calle_m') is not None:
        partes.append(f"a {r['a_calle_m']:.0f} m de la calle más cercana ({r.get('calle_cercana')})")
    medido = ('Sitio ' + ' y '.join(partes) + '. ') if partes else ''
    if r.get('estado') == SOBRE_ALIMENTADOR:
        estado = 'Queda encima de la red: hay que elegirlo en el plano.'
    elif r.get('estado') == SOBRE_CALLE:
        estado = 'Queda sobre la calle: hay que elegirlo en el plano.'
    elif r.get('estado') == SIN_VERIFICAR:
        estado = 'Sin verificar en plano.'
    else:
        estado = 'Predio, accesos y viviendas: por revisar en el plano.'
    return medido + estado
