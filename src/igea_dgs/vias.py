"""Trazado de una línea nueva por las vías públicas (spec 016, RF-81 a RF-87).

El enlace entre alimentadores iba en recta entre sus dos extremos, cruzando terrenos, y
la línea real tiene que ir por la vía para cumplir las distancias mínimas de seguridad
(usuario, 2026-10-16, Procedimiento 228 de Osinergmin). Un servidor OSRM sobre
OpenStreetMap da la ruta por la vía, con sus curvas, y lo lejos que queda cada extremo de
ella. Solo salen las coordenadas de los dos extremos (constitución P9, RF-83), y solo si
el perfil de empresa habilita el enrutador (RF-86).

Este módulo no importa ``powerfactory``: lo usa el guion de obras dentro de DIgSILENT.
"""
from __future__ import annotations

import json
import math
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

Punto = tuple[float, float]
RADIO_TIERRA_M = 6_371_008.8
TIEMPO_POR_DEFECTO_S = 10.0


def distancia_m(a: Punto, b: Punto) -> float:
    """Haversine entre dos (lat, lon)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(math.sqrt(h))


@dataclass
class Ruta:
    """Los puntos de la línea (lat, lon), de un extremo al otro, y cómo se obtuvieron."""

    puntos: list[Punto]
    largo_m: float
    recta_m: float
    por_via: bool
    servicio: str = ''
    fuera_de_via_m: float = 0.0
    avisos: list[str] = field(default_factory=list)

    def resumen(self) -> dict[str, Any]:
        """Lo que va al informe de la obra (RF-87)."""
        return {'por_via': self.por_via, 'largo_m': round(self.largo_m, 1),
                'recta_m': round(self.recta_m, 1), 'fuera_de_via_m': round(self.fuera_de_via_m, 1),
                'servicio': self.servicio, 'puntos': len(self.puntos)}


def _pedir(url: str, tiempo_s: float) -> bytes:
    pedido = urllib.request.Request(url, headers={'User-Agent': 'igea-dgs (enlace por la via)'})
    with urllib.request.urlopen(pedido, timeout=tiempo_s) as r:  # noqa: S310 - URL del perfil
        return r.read()


def _recta(a: Punto, b: Punto, avisos: list[str] | None = None, servicio: str = '') -> Ruta:
    d = distancia_m(a, b)
    return Ruta([a, b], d, d, False, servicio, 0.0, list(avisos or []))


def ruta_por_vias(a: Punto, b: Punto, config: Mapping[str, Any] | None, *,
                  pedir: Callable[[str, float], bytes] = _pedir) -> Ruta:
    """La ruta de ``a`` a ``b`` por la vía, o la recta si no hay enrutador o no responde."""
    config = config or {}
    servicio = str(config.get('servicio') or '').strip().lower()
    if not servicio:                                                   # RF-86
        return _recta(a, b)
    if servicio != 'osrm':
        return _recta(a, b, [f'Enrutador de vías {servicio!r} desconocido: el enlace va en recta.'])
    url = str(config.get('url') or '').rstrip('/')
    perfil = str(config.get('perfil') or 'driving')
    tiempo = float(config.get('tiempo_max_s') or TIEMPO_POR_DEFECTO_S)
    # RF-83: solo las dos coordenadas, lon,lat como pide OSRM.
    consulta = (f'{url}/route/v1/{perfil}/{a[1]:.6f},{a[0]:.6f};{b[1]:.6f},{b[0]:.6f}'
                f'?overview=full&geometries=geojson')
    try:
        datos = json.loads(pedir(consulta, tiempo).decode('utf-8'))
        ruta = datos['routes'][0]
        tramo = [(float(lat), float(lon)) for lon, lat in ruta['geometry']['coordinates']]
        accesos = [float(w.get('distance') or 0.0) for w in datos.get('waypoints') or []][:2]
        por_la_via = float(ruta['distance'])
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:     # RF-85
        motivo = 'no halló ruta' if isinstance(exc, (KeyError, IndexError)) else f'no respondió ({exc})'
        return _recta(a, b, [f'El enrutador de vías {motivo}: el enlace va en recta.'], servicio)
    accesos += [0.0] * (2 - len(accesos))
    puntos = [a] + [p for p in tramo if p not in (a, b)] + [b]
    avisos = []
    maximo = float(config.get('fuera_de_via_max_m') or 0.0)
    for extremo, metros in zip(('origen', 'destino'), accesos):            # RF-84
        if maximo and metros > maximo:
            avisos.append(f'El {extremo} del enlace queda a {metros:.0f} m de la vía más cercana '
                          f'(máximo {maximo:g} m): revise las distancias mínimas de seguridad.')
    return Ruta(puntos, por_la_via + sum(accesos), distancia_m(a, b), True, servicio,
                sum(accesos), avisos)
