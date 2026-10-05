"""Gestión de CRS (sección 9 y U7 de VNR-GIS.md).

Reglas: rechazar CRS desconocido en modo estricto; usar un CRS proyectado para
longitudes métricas y snapping; no hacer nunca snapping en grados; conservar las
coordenadas originales y su CRS.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence


class CRSError(RuntimeError):
    pass


def _require_pyproj():
    try:
        import pyproj  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise CRSError('La reproyección necesita «pyproj» (ver vnr_requirements.txt).') from exc
    return __import__('pyproj')


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
        pyproj = _require_pyproj()
        if not self.source_crs or not self.working_crs or self.source_crs == self.working_crs:
            return None
        return pyproj.Transformer.from_crs(self.source_crs, self.working_crs, always_xy=True).transform

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