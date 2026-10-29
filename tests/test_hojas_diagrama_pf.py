"""Spec 022, RF-93: la hoja de cada diagrama frente a sus gráficos, con ``fake_pf``.

DIgSILENT no se ejecuta en la suite (P11). En Nasca por SET (2026-10-29) DIgSILENT dio hoja
vertical a la SET 52, la 53 y la 56, más altas que anchas, y los vectores de los conectores
traen −1 en los puntos sin usar.
"""
from __future__ import annotations

import importlib
import random

import fake_pf
import pytest
from apoyo import cargar_herramienta

SEMILLA = random.randrange(1 << 30)


@pytest.fixture(scope='module')
def hojas():
    return cargar_herramienta('hojas_diagrama_pf.py', 'hojas_diagrama_guion', tools_en_path=True)


def _diagrama(app, nombre: str, ancho: float, alto: float, rnd: random.Random, *,
              orientacion: int, holgura: float = 1.05):
    """Un ``IntGrfnet`` con gráficos en [45, ancho]×[45, alto], un conector con sus puntos sin
    usar en −1 y la hoja a la medida, como la deja DIgSILENT al importar."""
    d = app.proyecto.CreateObject('IntGrfnet', nombre)
    puntos = [(45.0, 45.0), (ancho, alto)] + [(rnd.uniform(45, ancho), rnd.uniform(45, alto))
                                               for _ in range(rnd.randint(3, 20))]
    for i, (x, y) in enumerate(puntos):
        g = d.CreateObject('IntGrf', f'G_{i}')
        g.rCenterX, g.rCenterY = x, y
        c = g.CreateObject('IntGrfcon', f'GCO_{i}')
        c.rX = [x, 45.0] + [-1.0] * rnd.randint(2, 18)
        c.rY = [y, 45.0] + [-1.0] * (len(c.rX) - 2)
    mayor, menor = max(ancho, alto) * holgura, min(ancho, alto) * holgura
    d.cDrawFormat = f'{nombre} ({mayor:.0f}x{menor:.0f})'
    d.cDrawOrient = orientacion
    return d


def test_los_puntos_sin_usar_del_conector_no_son_del_dibujo(hojas):
    """022:RF-93 — el vector del conector se lee hasta el primer (−1, −1)."""
    assert hojas.puntos_del_conector([5.0, 7.0, -1.0, -1.0], [3.0, 4.0, -1.0, -1.0]) == [(5.0, 3.0), (7.0, 4.0)]
    assert hojas.puntos_del_conector([], []) == []
    assert hojas.hoja_efectiva((203840.0, 112100.0), hojas.VERTICAL) == (112100.0, 203840.0)
    assert hojas.hoja_efectiva((203840.0, 112100.0), hojas.HORIZONTAL) == (203840.0, 112100.0)
    assert hojas.tamano_del_formato('Nasca SET 53 Puquio (203840x112100)', {}) == (203840.0, 112100.0)
    assert hojas.tamano_del_formato('A0', {'A0': (1188.0, 840.0)}) == (1188.0, 840.0)
    assert hojas.tamano_del_formato('sin tamaño', {}) is None


def test_la_herramienta_da_cada_hoja_con_sus_graficos(hojas, monkeypatch):
    """022:RF-93 — una SET alta en hoja vertical y una ancha en horizontal, con todo dentro
    (código 0); una hoja más chica que su dibujo sale FUERA (código 1). No escribe nada."""
    rnd = random.Random(SEMILLA)
    app = fake_pf.proyecto(alimentadores=('F1',))
    monkeypatch.setattr(importlib.import_module('cargas_pf'), 'activar_proyecto',
                        lambda app, nombre, carpeta=None: app.proyecto)
    for d in app.proyecto.GetContents('*.IntGrfnet', 1):
        d.Delete()
    _diagrama(app, 'Nasca SET 53 Puquio', rnd.uniform(1e4, 1e5), rnd.uniform(1.5e5, 2e5), rnd,
              orientacion=hojas.VERTICAL)
    _diagrama(app, 'Nasca SET 51 Nasca', rnd.uniform(1e5, 2e5), rnd.uniform(1e4, 5e4), rnd,
              orientacion=hojas.HORIZONTAL)
    escrituras = len(app.escrituras)

    informe, rc = hojas.ejecutar(app, {'project': 'P'})

    assert rc == 0 and informe['todas_dentro'], informe
    assert {d['diagrama']: d['orientacion'] for d in informe['diagramas']} == {
        'Nasca SET 51 Nasca': 'horizontal', 'Nasca SET 53 Puquio': 'vertical'}
    assert all(d['recuadro'][0] >= 0 for d in informe['diagramas']), 'sin los −1 del conector'
    assert len(app.escrituras) == escrituras, 'de solo lectura'

    _diagrama(app, 'Nasca SET 56', rnd.uniform(1e3, 2e3), rnd.uniform(5e3, 7e3), rnd,
              orientacion=hojas.HORIZONTAL)
    informe, rc = hojas.ejecutar(app, {'project': 'P'})
    fuera = [d['diagrama'] for d in informe['diagramas'] if not d['dentro']]
    assert rc == 1 and fuera == ['Nasca SET 56']
