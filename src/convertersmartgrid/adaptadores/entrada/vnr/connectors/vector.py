"""Adaptador de archivos GIS (GeoJSON/Shapefile/GeoPackage) con ``geopandas`` opcional.

Si ``geopandas`` no está instalado, el adaptador devuelve un error claro en lugar
de fallar en silencio (sección E3, MODE B).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .base import AdapterUnavailable, LayerInfo, SourceProbe, VNRSourceAdapter


@dataclass
class VectorFileAdapter(VNRSourceAdapter):
    path: str = ''

    def _gpd(self):
        try:
            import geopandas as gpd  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise AdapterUnavailable('archivos GIS', 'geopandas') from exc
        return __import__('geopandas')

    def probe(self, source) -> SourceProbe:
        path = Path(self.path or source)
        suffix = path.suffix.lower()
        if suffix not in ('.shp', '.gpkg', '.geojson', '.json', '.zip'):
            return SourceProbe(family='VECTOR_FILE', ok=False, reason=f'Formato no soportado: {suffix}')
        if not path.is_file():
            return SourceProbe(family='VECTOR_FILE', ok=False, reason=f'No existe {path}')
        return SourceProbe(family='VECTOR_FILE', ok=True)

    def metadata(self) -> dict:
        return {'path': self.path, 'family': 'VECTOR_FILE'}

    def list_layers(self) -> list[LayerInfo]:
        gpd = self._gpd()
        gdf = gpd.read_file(self.path)
        infos: list[LayerInfo] = []
        for _, row in gdf.iterrows():  # un solo DataFrame en la mayoría de casos
            break
        fields = [{'name': name, 'type': str(gdf[name].dtype)} for name in gdf.columns if name != 'geometry']
        infos.append(LayerInfo(
            name=Path(self.path).stem,
            fields=fields,
            geometry_type=str(gdf.geom_type.iloc[0]) if len(gdf) else '',
            record_count=len(gdf),
            crs=str(gdf.crs) if gdf.crs is not None else '',
        ))
        return infos

    def read_layer(self, layer, filters=None) -> list[dict]:
        del layer, filters
        gpd = self._gpd()
        gdf = gpd.read_file(self.path)
        rows: list[dict] = []
        for _, row in gdf.iterrows():
            record = {k: v for k, v in row.items()}
            geom = record.pop('geometry', None)
            if geom is not None:
                record['__geometry__'] = _geometry_to_geojson(geom)
            rows.append(record)
        return rows


def _geometry_to_geojson(geom) -> dict | None:
    """Serializa una geometría de shapely/geopandas a GeoJSON."""
    try:
        import shapely
        import shapely.geometry

        return shapely.geometry.mapping(geom)
    except Exception:  # noqa: BLE001 - geometría opcional
        return None
