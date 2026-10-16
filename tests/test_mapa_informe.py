"""Spec 017, RF-11b — imágenes del informe con el GPS y los resultados del flujo."""
from __future__ import annotations

import pytest
from PIL import Image

from igea_dgs.mapa_informe import MapaError, dibujar, imagenes_del_estado

GEO = {'cabecera': 'CAB',
       'barras': [['CAB', -14.0, -75.70, 1.0, 10.0], ['N1', -14.01, -75.69, 0.97, 10.0],
                  ['SED1_BT', -14.02, -75.68, 0.80, 0.22]],
       'tramos': [['L1', [[-14.0, -75.70], [-14.01, -75.69]], 40.0],
                  ['L2', [[-14.01, -75.69], [-14.015, -75.685], [-14.02, -75.68]], 112.0]]}


def test_tres_imagenes_de_un_estado(tmp_path):
    """017:RF-11b / 017:RF-116 — ubicación, tensión y cargabilidad en PNG, con las bandas."""
    rutas = imagenes_del_estado(GEO, tmp_path, 'CA', estado='estado actual', alimentador='AL01',
                                bandas_tension=(85, 90, 95, 105), bandas_carga=(80, 90, 95, 105, 150))
    assert set(rutas) == {'ubicacion', 'tension', 'cargabilidad'}
    for ruta in rutas.values():
        with Image.open(ruta) as img:
            assert img.format == 'PNG' and img.size == (1600, 1150)
            colores = {c for _, c in img.getcolors(1 << 20)}
            assert len(colores) > 3, 'la imagen tiene dibujo, no solo fondo'


def test_la_tension_baja_sale_en_rojo_y_la_sobrecarga_tambien(tmp_path):
    """017:RF-116 — la barra a 0,80 p.u. (banda < 85 %) y el tramo al 112 % (105–150 %)."""
    for modo in ('tension', 'cargabilidad'):
        ruta = dibujar(GEO, modo, tmp_path / f'{modo}.png', titulo=modo)
        with Image.open(ruta) as img:
            colores = {c for _, c in img.getcolors(1 << 20)}
        assert (200, 30, 30) in colores


def test_sin_geografia_lo_dice(tmp_path):
    """017:RF-11b — sin GPS guardado no se inventa una imagen."""
    with pytest.raises(MapaError, match='geografía'):
        dibujar({'barras': [], 'tramos': []}, 'tension', tmp_path / 'x.png', titulo='x')
