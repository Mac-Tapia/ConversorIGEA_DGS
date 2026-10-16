"""Gestión de CRS (sección 9 y U7 de VNR-GIS.md).

Reglas: rechazar CRS desconocido en modo estricto; usar un CRS proyectado para
longitudes métricas y snapping; no hacer nunca snapping en grados; conservar las
coordenadas originales y su CRS.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from igea_dgs.geography import make_transformer
from igea_dgs.util import importar_opcional


class CRSError(RuntimeError):
    pass


def _require_pyproj():
    return importar_opcional('pyproj', CRSError(
        'La reproyección necesita «pyproj» (ver requirements.txt).'))


def _is_projected(crs: str) -> bool:
    pyproj = _require_pyproj()
    try:
        crs_obj = pyproj.CRS.from_user_input(crs)
    except Exception as exc:
        raise CRSError(f'CRS no reconocido: {crs!r}') from exc
    return bool(crs_obj.is_projected)


class CRSManager:
    """Normaliza y reproyecta coordenadas conservando el CRS original."""

    def __init__(self, source_crs: str | None, working_crs: str | None = None,
                 *, strict: bool = True) -> None:
        self.source_crs = source_crs
        self.working_crs = working_crs
        self.strict = strict

    def inspect(self) -> dict:
        if not self.source_crs:
            if self.strict:
                raise CRSError(
                    'CRS de origen desconocido y modo estricto activo: indíquelo en la '
                    'configuración (gis.source_crs).'
                )
            return {'source_crs': None, 'working_crs': None, 'projected': False}
        if not _is_projected(self.source_crs):
            if self.strict:
                raise CRSError(
                    f'El CRS de origen {self.source_crs} no es proyectado: no se puede '
                    'medir ni hacer snapping en grados.'
                )
            projected = False
        else:
            projected = True
        working = self.working_crs or self.source_crs
        return {'source_crs': self.source_crs, 'working_crs': working, 'projected': projected}

    def transformer_to_working(self) -> Callable | None:
        """Devuelve un transformador source→working si difieren; si no, ``None``."""
        _require_pyproj()
        if not self.source_crs or not self.working_crs or self.source_crs == self.working_crs:
            return None
        return make_transformer(self.source_crs, self.working_crs).transform

    def transform_points(
        self, points: Sequence[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        transformer = self.transformer_to_working()
        if transformer is None:
            return list(points)
        return [transformer(x, y) for x, y in points]

    def ensure_metre_crs(self) -> str:
        """Devuelve el CRS de trabajo en metros, o lanza en modo estricto."""
        info = self.inspect()
        if not info.get('projected'):
            raise CRSError('Se necesita un CRS proyectado (metros) para topología.')
        return info['working_crs']


def parecen_grados(puntos: Sequence[tuple[float, float]]) -> bool:
    """Si unas coordenadas sin CRS declarado están, con toda probabilidad, en grados.

    Una red de distribución cabe holgada en dos grados. Unas coordenadas proyectadas
    pequeñas (un modelo de prueba en 0..20 m) también caben en el rango de lon/lat, por
    eso se exige además que alguna tenga decimales, como toda coordenada en grados real.
    """
    if not puntos:
        return False
    xs = [float(p[0]) for p in puntos]
    ys = [float(p[1]) for p in puntos]
    en_rango = all(-180 <= x <= 180 for x in xs) and all(-90 <= y <= 90 for y in ys)
    extension = max(max(xs) - min(xs), max(ys) - min(ys))
    con_decimales = any(v != int(v) for v in xs + ys)
    return en_rango and extension <= 2.0 and con_decimales


def deducir_crs(puntos: Sequence[tuple[float, float]]) -> tuple[str | None, str]:
    """CRS de origen para una capa que no lo declara, y por qué.

    Antes se rechazaba la conversión («no se asumirá EPSG:4326») y el usuario se quedaba
    sin red por un dato que las propias coordenadas suelen delatar (spec 001, RF-25).
    En grados se toma EPSG:4326 (el CRS de trabajo será su zona UTM). Si no, ``None``:
    se lee sin reproyectar, las longitudes se toman en las unidades de la capa y la red
    se exporta sin georreferenciación.
    """
    if parecen_grados(puntos):
        return 'EPSG:4326', ('La capa no declara CRS y sus coordenadas están en grados: '
                             'se toma EPSG:4326 y se trabaja en su zona UTM.')
    return None, ('La capa no declara CRS y no se puede deducir: se lee sin reproyectar '
                  '(longitudes en sus unidades) y se exporta sin georreferenciación.')

