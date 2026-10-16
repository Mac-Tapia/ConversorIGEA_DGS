"""Una sola forma de construir el transformador de coordenadas (spec 001, T4).

Había cinco, y cada una trataba distinto un CRS inválido: una lo callaba y dejaba todas
las coordenadas vacías, las demás soltaban el error de pyproj sin decir qué CRS era.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip('pyproj')

from igea_dgs.geography import make_transformer  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / 'src'


def test_transforma_utm_a_wgs84():
    """001:RF-6 — orden x/y (lon, lat), como esperan todos los llamadores."""
    lon, lat = make_transformer('EPSG:32718', 'EPSG:4326').transform(500000.0, 8450000.0)
    assert lat == pytest.approx(-14.0, abs=0.1)
    assert lon == pytest.approx(-75.0, abs=0.1)


@pytest.mark.parametrize('origen, destino', [('EPSG:999999', 'EPSG:4326'),
                                             ('EPSG:32718', 'EPSG:999999')])
def test_crs_invalido_da_error_que_lo_nombra(origen, destino):
    """001:RF-6, 001:RF-7 — ValueError con el CRS, no el error crudo de pyproj."""
    with pytest.raises(ValueError, match='EPSG:999999'):
        make_transformer(origen, destino)


def test_vnr_reproyecta_con_el_mismo_transformador():
    """001:RF-6 — VNR-GIS da el mismo error con el mismo mensaje."""
    from vnr_etl.gis.crs import CRSManager
    from vnr_etl.pipeline import _transform_points

    with pytest.raises(ValueError, match='EPSG:999999'):
        CRSManager('EPSG:999999', 'EPSG:32718', strict=False).transformer_to_working()
    with pytest.raises(ValueError, match='EPSG:999999'):
        _transform_points([(500000.0, 8450000.0)], 'EPSG:999999', 'EPSG:32718')


def test_solo_geography_construye_transformadores():
    """001:RF-6 — ``Transformer.from_crs`` aparece en un único sitio de ``src/``."""
    sitios = sorted(
        f'{ruta.relative_to(SRC).as_posix()}:{n}'
        for ruta in SRC.rglob('*.py')
        for n, linea in enumerate(ruta.read_text(encoding='utf-8').splitlines(), 1)
        if 'Transformer.from_crs' in linea
    )
    assert len(sitios) == 1 and sitios[0].startswith('igea_dgs/geography.py:'), sitios
