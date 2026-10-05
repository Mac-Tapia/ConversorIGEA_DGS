"""Huella de fuente y de esquema (sección U3 de VNR-GIS.md).

La ``schema_fingerprint`` es un hash determinista de capas/tablas, nombres y
tipos de campos y tipos de geometría. Sirve para detectar un cambio de esquema
trimestral/anual sin suponer un calendario de publicación fijo.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field


def _stable_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode('utf-8')


def compute_schema_fingerprint(layers: Sequence[dict]) -> str:
    """Hash determinista de la descripción normalizada de las capas/tablas.

    Cada capa debe ser un dict con, al menos, ``name``, ``fields`` (lista de
    ``{name, type}``) y opcionalmente ``geometry_type``.
    """
    normalized = []
    for layer in sorted(layers, key=lambda l: str(l.get('name', ''))):
        fields = sorted(
            (dict(f) for f in layer.get('fields', [])),
            key=lambda f: str(f.get('name', '')),
        )
        normalized.append({
            'name': str(layer.get('name', '')),
            'geometry_type': str(layer.get('geometry_type', '')),
            'fields': fields,
        })
    digest = hashlib.sha256(_stable_bytes(normalized)).hexdigest()
    return digest[:16]


@dataclass
class SourceFingerprint:
    """Huella de una fuente (sección U3)."""

    source_family: str | None = None
    source_uri_hash: str | None = None
    company_field: str | None = None
    company_values: list[str] = field(default_factory=list)
    period_field: str | None = None
    period_values: list[str] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    crs: str | None = None
    schema_fingerprint: str | None = None
    adapter_version: str = '1.6.0'

    def as_dict(self) -> dict:
        return {
            'source_family': self.source_family,
            'source_uri_hash': self.source_uri_hash,
            'company_field': self.company_field,
            'company_values': sorted(set(self.company_values)),
            'period_field': self.period_field,
            'period_values': sorted(set(self.period_values)),
            'layers': list(self.layers),
            'crs': self.crs,
            'schema_fingerprint': self.schema_fingerprint,
            'adapter_version': self.adapter_version,
        }


def hash_uri(uri: str) -> str:
    return hashlib.sha256(uri.encode('utf-8')).hexdigest()[:20]


def compute_source_fingerprint(
    *,
    source_family: str | None = None,
    uri: str | None = None,
    company_field: str | None = None,
    company_values: Sequence[str] = (),
    period_field: str | None = None,
    period_values: Sequence[str] = (),
    layers: Sequence[str] = (),
    crs: str | None = None,
    schema_fingerprint: str | None = None,
) -> SourceFingerprint:
    return SourceFingerprint(
        source_family=source_family,
        source_uri_hash=hash_uri(uri) if uri else None,
        company_field=company_field,
        company_values=sorted(set(company_values)),
        period_field=period_field,
        period_values=sorted(set(period_values)),
        layers=list(layers),
        crs=crs,
        schema_fingerprint=schema_fingerprint,
    )