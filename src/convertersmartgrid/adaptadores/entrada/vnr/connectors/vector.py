"""Adaptador de archivos GIS (GeoJSON/Shapefile/GeoPackage) con ``geopandas`` opcional.

Si ``geopandas`` no está instalado, el adaptador devuelve un error claro en lugar
de fallar en silencio (sección E3, MODE B).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .base import AdapterUnavailable, LayerInfo, SourceProbe, VNRSourceAdapter, filtrar_filas


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

    def _capas(self) -> list[str] | None:
        """Las capas de un fichero multicapa (GeoPackage, GDB); None si el formato tiene una sola."""
        if Path(self.path).suffix.lower() not in ('.gpkg', '.gdb'):
            return None
        self._gpd()
        import pyogrio

        return [str(fila[0]) for fila in pyogrio.list_layers(self.path)]

    def list_layers(self) -> list[LayerInfo]:
        """080:RF-55: TODAS las capas del fichero, con sus campos, su recuento y su CRS.

        Antes devolvía una sola, con el nombre del fichero, y en un GeoPackage corporativo
        (Tramo_MT, Tramo_BT, Sed, equipos…) se perdía todo menos la primera.
        """
        capas = self._capas()
        if capas is None:
            gpd = self._gpd()
            gdf = gpd.read_file(self.path)
            fields = [{'name': name, 'type': str(gdf[name].dtype)} for name in gdf.columns if name != 'geometry']
            return [LayerInfo(
                name=Path(self.path).stem,
                fields=fields,
                geometry_type=str(gdf.geom_type.iloc[0]) if len(gdf) else '',
                record_count=len(gdf),
                crs=str(gdf.crs) if gdf.crs is not None else '',
            )]
        import pyogrio

        infos: list[LayerInfo] = []
        for nombre in capas:
            info = pyogrio.read_info(self.path, layer=nombre)
            # pyogrio (0.13) da «fields» y «dtypes» como arrays de numpy: «x or []» los evaluaba como booleano y fallaba
            # con «The truth value of an array… is ambiguous» (la primera corrida real de estas pruebas, 2026-11-14).
            tipos = [] if info.get('dtypes') is None else list(info['dtypes'])
            nombres = [] if info.get('fields') is None else list(info['fields'])
            campos = [{'name': str(c), 'type': str(tipos[i]) if i < len(tipos) else ''}
                      for i, c in enumerate(nombres)]
            crs = info.get('crs') or ''
            infos.append(LayerInfo(name=nombre, fields=campos, layer_id=nombre,
                                   geometry_type=str(info.get('geometry_type') or ''),
                                   record_count=int(info.get('features') or 0), crs=str(crs)))
        return infos

    def read_layer(self, layer, filters=None) -> list[dict]:
        """080:RF-55: lee ESA capa (antes, siempre la de por defecto) y aplica ``filters``."""
        gpd = self._gpd()
        capas = self._capas()
        if capas is None:
            gdf = gpd.read_file(self.path)
        else:
            if layer not in capas:
                raise ValueError(f'El fichero {Path(self.path).name} no tiene la capa {layer!r}: {capas}.')
            gdf = gpd.read_file(self.path, layer=layer)
        rows: list[dict] = []
        for _, row in gdf.iterrows():
            record = {k: v for k, v in row.items()}
            geom = record.pop('geometry', None)
            if geom is not None:
                record['__geometry__'] = _geometry_to_geojson(geom)
            rows.append(record)
        return filtrar_filas(rows, filters, conector='El fichero GIS')


def _geometry_to_geojson(geom) -> dict | None:
    """Serializa una geometría de shapely/geopandas a GeoJSON."""
    try:
        import shapely
        import shapely.geometry

        return shapely.geometry.mapping(geom)
    except Exception:  # noqa: BLE001 - geometría opcional
        return None
