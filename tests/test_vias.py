"""Trazado del enlace por la vía con un enrutador OSRM (spec 016, RF-81 a RF-87).

Ninguna prueba sale a la red: la respuesta del servidor se inyecta con ``pedir``.
"""
from __future__ import annotations

import json
import random

import pytest

from igea_dgs import vias

A = (-14.0128, -75.7293)
B = (-14.0222, -75.7615)
CONFIG = {'servicio': 'osrm', 'url': 'https://enrutador.prueba', 'perfil': 'driving',
          'fuera_de_via_max_m': 50, 'tiempo_max_s': 5}


def _respuesta(puntos, distancia_m, accesos=(3.0, 4.0)):
    return json.dumps({
        'code': 'Ok',
        'routes': [{'distance': distancia_m,
                    'geometry': {'coordinates': [[lon, lat] for lat, lon in puntos]}}],
        'waypoints': [{'distance': accesos[0]}, {'distance': accesos[1]}],
    }).encode('utf-8')


def _curva(rng, n):
    """Una vía con curvas entre A y B, de ``n`` vértices sorteados."""
    pts = [A]
    for i in range(1, n - 1):
        t = i / (n - 1)
        pts.append((A[0] + (B[0] - A[0]) * t + rng.uniform(-0.002, 0.002),
                    A[1] + (B[1] - A[1]) * t + rng.uniform(-0.002, 0.002)))
    return pts + [B]


@pytest.mark.parametrize('semilla', [3, 17, 41])
def test_traza_por_la_via_con_sus_curvas(semilla):
    """016:RF-81, 016:RF-82 — la línea sigue la vía, vértice a vértice, y su largo es el de
    la ruta más los accesos de cada extremo."""
    rng = random.Random(semilla)
    curva = _curva(rng, rng.randint(5, 30))
    pedidas = []

    def pedir(url, tiempo):
        pedidas.append((url, tiempo))
        return _respuesta(curva, 4210.5)

    r = vias.ruta_por_vias(A, B, CONFIG, pedir=pedir)
    assert r.por_via and r.servicio == 'osrm'
    assert r.puntos[0] == A and r.puntos[-1] == B and len(r.puntos) >= len(curva)
    assert r.largo_m == pytest.approx(4210.5 + 3.0 + 4.0)
    assert r.recta_m == pytest.approx(vias.distancia_m(A, B))
    assert r.fuera_de_via_m == pytest.approx(7.0) and r.avisos == []
    assert pedidas[0][1] == 5


def test_solo_envia_las_coordenadas_de_los_extremos():
    """016:RF-83 — la petición lleva las dos coordenadas y nada más de la red."""
    pedidas = []

    def pedir(url, _tiempo):
        pedidas.append(url)
        return _respuesta([A, B], 3500.0)

    vias.ruta_por_vias(A, B, CONFIG, pedir=pedir)
    (url,) = pedidas
    assert url.startswith('https://enrutador.prueba/route/v1/driving/')
    camino = url.split('/route/v1/driving/')[1].split('?')[0]
    assert camino == f'{A[1]:.6f},{A[0]:.6f};{B[1]:.6f},{B[0]:.6f}'
    assert set(url.split('?')[1].split('&')) == {'overview=full', 'geometries=geojson'}


def test_extremo_lejos_de_la_via_avisa():
    """016:RF-84 — un extremo a más de la distancia máxima de la vía se avisa con sus
    metros, para revisar las distancias mínimas de seguridad."""
    r = vias.ruta_por_vias(A, B, CONFIG, pedir=lambda *_: _respuesta([A, B], 3500.0, (180.0, 2.0)))
    assert r.por_via
    assert len(r.avisos) == 1 and 'origen' in r.avisos[0] and '180' in r.avisos[0]


@pytest.mark.parametrize('falla', ['error', 'sin_ruta', 'basura'])
def test_sin_respuesta_traza_en_recta(falla):
    """016:RF-85 — si el enrutador no responde o no halla ruta, recta y aviso."""
    def pedir(*_):
        if falla == 'error':
            raise OSError('sin red')
        if falla == 'sin_ruta':
            return json.dumps({'code': 'NoRoute', 'routes': []}).encode()
        return b'<html>'

    r = vias.ruta_por_vias(A, B, CONFIG, pedir=pedir)
    assert not r.por_via and r.puntos == [A, B]
    assert r.largo_m == pytest.approx(vias.distancia_m(A, B))
    assert len(r.avisos) == 1 and 'recta' in r.avisos[0]


@pytest.mark.parametrize('config', [None, {}, {'servicio': ''}])
def test_sin_enrutador_en_el_perfil_no_sale_nada(config):
    """016:RF-86 — sin enrutador en el perfil, recta y ninguna petición."""
    def pedir(*_):
        raise AssertionError('no debía pedir nada')

    r = vias.ruta_por_vias(A, B, config, pedir=pedir)
    assert not r.por_via and r.servicio == '' and r.avisos == []
    assert r.puntos == [A, B]


def test_resumen_para_el_informe():
    """016:RF-87 — el informe de la obra lleva el largo por la vía, la recta, los metros
    fuera de vía y el servicio."""
    r = vias.ruta_por_vias(A, B, CONFIG, pedir=lambda *_: _respuesta([A, B], 3500.0))
    d = r.resumen()
    assert set(d) == {'por_via', 'largo_m', 'recta_m', 'fuera_de_via_m', 'servicio', 'puntos'}
    assert d['largo_m'] == pytest.approx(3507.0) and d['servicio'] == 'osrm'
