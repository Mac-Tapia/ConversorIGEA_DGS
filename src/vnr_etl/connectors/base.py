"""Abstracción de conectores de fuente.

Los conectores existentes se **envuelven** en lugar de reemplazarse (sección 8).
El adaptador único `VNRSourceAdapter` (sección U10) presenta una API uniforme para
todas las fuentes: ArcGIS REST, archivos, bases de datos, etc.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class LayerInfo:
    """Descripción de una capa/tabla, lista para la huella de esquema."""

    name: str
    fields: list[dict] = field(default_factory=list)
    geometry_type: str = ''
    layer_id: str = ''
    record_count: int = 0
    crs: str = ''

    def as_dict(self) -> dict:
        return {
            'name': self.name,
            'fields': self.fields,
            'geometry_type': self.geometry_type,
            'layer_id': self.layer_id,
            'record_count': self.record_count,
            'crs': self.crs,
        }


@runtime_checkable
class NetworkSource(Protocol):
    """Contrato mínimo de un conector de red (sección 8)."""

    def load_sections(self) -> Any: ...
    def load_loads(self) -> Any: ...
    def load_transformers(self) -> Any: ...
    def load_switches(self) -> Any: ...
    def load_sources(self) -> Any: ...


class VNRSourceAdapter:
    """Adaptador uniforme de fuente (sección U10).

    Una subclase implementa lo que soporte y lanza un error claro (``AdapterUnavailable``)
    cuando el driver/opción que le corresponde no está instalado.
    """

    family: str = 'UNKNOWN'

    def probe(self, source) -> SourceProbe:
        raise NotImplementedError

    def metadata(self) -> dict:
        raise NotImplementedError

    def list_layers(self) -> list[LayerInfo]:
        raise NotImplementedError

    def read_layer(self, layer, filters: Mapping[str, Any] | None = None) -> list[dict]:
        raise NotImplementedError

    def available_companies(self) -> list[str]:
        return self._distinct_values(('CODEMP', 'EMPRESA', 'COD_EMPRESA', 'company'))

    def available_periods(self, company: str | None = None) -> list[str]:
        company_fields = ('CODEMP', 'EMPRESA', 'COD_EMPRESA', 'company')
        period_fields = ('ANIO', 'AÑO', 'PERIODO', 'YEAR', 'period')
        values: set[str] = set()
        for layer in self.list_layers():
            fields = {str(item.get('name', '')) for item in layer.fields}
            period_field = next((name for name in period_fields if name in fields), None)
            if period_field is None:
                continue
            company_field = next((name for name in company_fields if name in fields), None)
            for row in self.read_layer(layer.name):
                if company and company_field and str(row.get(company_field, '')).strip() != company:
                    continue
                value = row.get(period_field)
                if value not in (None, ''):
                    values.add(str(value).strip())
        return sorted(values)

    def _distinct_values(self, candidates: tuple[str, ...]) -> list[str]:
        values: set[str] = set()
        for layer in self.list_layers():
            fields = {str(item.get('name', '')) for item in layer.fields}
            field = next((name for name in candidates if name in fields), None)
            if field is None:
                continue
            for row in self.read_layer(layer.name):
                value = row.get(field)
                if value not in (None, ''):
                    values.add(str(value).strip())
        return sorted(values)

    def close(self) -> None:
        return None


@dataclass
class SourceProbe:
    """Resultado de ``probe``: qué fuente es y si el adaptador puede leerla."""

    family: str
    ok: bool
    reason: str = ''
    layers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {'family': self.family, 'ok': self.ok, 'reason': self.reason, 'layers': self.layers}


class AdapterUnavailable(RuntimeError):
    """El adaptador existe pero su driver opcional no está instalado."""

    def __init__(self, adapter: str, requirement: str) -> None:
        super().__init__(
            f'El adaptador {adapter} necesita {requirement}; no está disponible '
            f'(ver requirements-drivers.txt y `python -m vnr_etl doctor`).'
        )
        self.adapter = adapter
        self.requirement = requirement
