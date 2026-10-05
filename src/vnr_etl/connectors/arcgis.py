"""Conector ArcGIS REST real (apartado C y U11 de VNR-GIS.md).

Lee metadatos, pagina por ``maxRecordCount``, reconcilia el conteo por
``returnCountOnly`` y devuelve las geometrías como GeoJSON. No asume que una
consulta única devuelve toda la red.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .base import LayerInfo, SourceProbe, VNRSourceAdapter


class ArcGISError(RuntimeError):
    pass


def _require_requests():
    try:
        import requests  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ArcGISError(
            'El conector ArcGIS necesita «requests» (ver vnr_requirements.txt).'
        ) from exc
    return __import__('requests')


@dataclass
class ArcGISLayer:
    url: str
    timeout: int = 60
    retries: int = 3

    def metadata(self) -> dict:
        requests = _require_requests()
        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.get(self.url, params={'f': 'json'}, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                if 'error' in data:
                    raise ArcGISError(data['error'])
                return data
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(2 ** attempt)
        raise ArcGISError(f'No se pudo leer la metadatos de {self.url}: {last}')

    def field_names(self) -> set[str]:
        return {f['name'] for f in self.metadata().get('fields', [])}

    def object_id_field(self) -> str:
        meta = self.metadata()
        return meta.get('objectIdField') or meta.get('objectIdFieldName') or 'OBJECTID'

    def max_record_count(self) -> int:
        return int(self.metadata().get('maxRecordCount', 1000))

    def count(self, where: str = '1=1') -> int:
        requests = _require_requests()
        params = {'f': 'json', 'where': where, 'returnCountOnly': 'true'}
        response = requests.get(f'{self.url}/query', params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if 'error' in data:
            raise ArcGISError(data['error'])
        return int(data.get('count', 0))

    def distinct_values(self, field: str, where: str = '1=1') -> list[Any]:
        """Consulta valores distintos sin descargar geometrías ni toda la capa."""
        requests = _require_requests()
        params = {
            'f': 'json',
            'where': where,
            'outFields': field,
            'returnDistinctValues': 'true',
            'returnGeometry': 'false',
            'orderByFields': f'{field} ASC',
        }
        response = requests.get(f'{self.url}/query', params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if 'error' in data:
            raise ArcGISError(data['error'])
        values = []
        for feature in data.get('features', []):
            attributes = feature.get('attributes') or feature.get('properties') or {}
            value = attributes.get(field)
            if value not in (None, ''):
                values.append(value)
        return values

    def query_geojson(self, where: str = '1=1', out_fields: str = '*',
                      page_size: int | None = None,
                      max_features: int | None = None) -> tuple[list[dict], int]:
        """Devuelve ``(features, crs)``. Cada feature es un GeoJSON ``Feature``."""
        requests = _require_requests()
        oid = self.object_id_field()
        limit = int(page_size or self.max_record_count())
        offset = 0
        features: list[dict] = []
        while True:
            request_count = limit
            if max_features is not None:
                remaining = max_features - len(features)
                if remaining <= 0:
                    break
                request_count = min(limit, remaining)
            params = {
                'f': 'geojson',
                'where': where,
                'outFields': out_fields,
                'returnGeometry': 'true',
                'outSR': 4326,
                'resultOffset': offset,
                'resultRecordCount': request_count,
                'orderByFields': f'{oid} ASC',
            }
            response = requests.get(f'{self.url}/query', params=params, timeout=self.timeout)
            response.raise_for_status()
            page = response.json()
            if 'error' in page:
                raise ArcGISError(page['error'])
            batch = page.get('features', [])
            features.extend(batch)
            if max_features is not None and len(features) >= max_features:
                features = features[:max_features]
                break
            if len(batch) < request_count:
                break
            offset += len(batch)
        crs = 4326
        return features, crs


@dataclass
class ArcGISRestAdapter(VNRSourceAdapter):
    url: str
    timeout: int = 60
    _metadata: dict | None = field(default=None, repr=False)

    family = 'ARCGIS_PUBLIC_REFERENCE'

    def probe(self, source) -> SourceProbe:
        try:
            meta = self.metadata_of()
            layers = [str(l.get('id', '')) for l in meta.get('layers', [])]
            return SourceProbe(family=self.family, ok=True, layers=layers)
        except ArcGISError as exc:
            return SourceProbe(family=self.family, ok=False, reason=str(exc))

    def metadata_of(self) -> dict:
        if self._metadata is None:
            layer = ArcGISLayer(self.url, timeout=self.timeout)
            self._metadata = layer.metadata()
        return self._metadata

    def metadata(self) -> dict:
        return self.metadata_of()

    def list_layers(self) -> list[LayerInfo]:
        meta = self.metadata_of()
        infos: list[LayerInfo] = []
        for layer in meta.get('layers', []):
            layer_url = f"{self.url.rstrip('/')}/{layer.get('id')}"
            arc = ArcGISLayer(layer_url, timeout=self.timeout)
            layer_meta = arc.metadata() if layer.get('id') is not None else {}
            infos.append(LayerInfo(
                name=str(layer.get('name', '')),
                fields=[{'name': f['name'], 'type': f.get('type', '')}
                        for f in layer_meta.get('fields', [])],
                geometry_type=str(layer_meta.get('geometryType', '')),
                layer_id=str(layer.get('id', '')),
                record_count=arc.count() if layer.get('id') is not None else 0,
                crs='EPSG:4326',  # query_geojson solicita outSR=4326 explícitamente
            ))
        return infos

    def available_companies(self) -> list[str]:
        return self._arcgis_distinct(('CODEMP', 'EMPRESA', 'COD_EMPRESA'))

    def available_periods(self, company: str | None = None) -> list[str]:
        return self._arcgis_distinct(
            ('ANIO', 'AÑO', 'PERIODO', 'YEAR'),
            company=company,
        )

    def _arcgis_distinct(self, candidates: tuple[str, ...], *,
                         company: str | None = None) -> list[str]:
        values: set[str] = set()
        for layer_def in self.metadata_of().get('layers', []):
            if layer_def.get('id') is None:
                continue
            arc = ArcGISLayer(
                f"{self.url.rstrip('/')}/{layer_def['id']}",
                timeout=self.timeout,
            )
            fields = arc.field_names()
            field = next((name for name in candidates if name in fields), None)
            if field is None:
                continue
            where = '1=1'
            if company:
                company_field = next(
                    (name for name in ('CODEMP', 'EMPRESA', 'COD_EMPRESA') if name in fields),
                    None,
                )
                if company_field is None:
                    continue
                escaped = company.replace("'", "''")
                where = f"{company_field} = '{escaped}'"
            values.update(
                str(value).strip()
                for value in arc.distinct_values(field, where=where)
                if value not in (None, '')
            )
        return sorted(values)

    def read_layer(self, layer, filters: Mapping[str, Any] | None = None) -> list[dict]:
        """Lee una capa por ID o nombre, con reconciliación de conteo (U11)."""
        filters = filters or {}
        where = filters.get('where', '1=1')
        layer_def = self._find_layer(layer)
        if layer_def is None:
            raise ArcGISError(f'Capa no encontrada: {layer}')
        layer_url = f"{self.url.rstrip('/')}/{layer_def['id']}"
        arc = ArcGISLayer(layer_url, timeout=self.timeout)
        expected = arc.count(where=where)
        features, _crs = arc.query_geojson(where=where, out_fields=filters.get('out_fields', '*'))
        deduped = self._dedupe(features, arc.object_id_field())
        if len(deduped) != expected:
            raise ArcGISError(
                f'Conteo incoherente en {layer_def["name"]}: el servidor declara '
                f'{expected} registros pero se obtuvieron {len(deduped)} únicos.'
            )
        return deduped

    def _find_layer(self, reference) -> dict | None:
        for layer in self.metadata_of().get('layers', []):
            if str(layer.get('id')) == str(reference) or layer.get('name') == reference:
                return layer
        return None

    @staticmethod
    def _dedupe(features: list[dict], oid_field: str) -> list[dict]:
        seen: set = set()
        out: list[dict] = []
        for feature in features:
            attrs = feature.get('properties') or {}
            oid = attrs.get(oid_field, id(feature))
            if oid in seen:
                continue
            seen.add(oid)
            out.append(feature)
        return out
