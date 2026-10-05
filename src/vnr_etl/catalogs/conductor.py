"""Mapeo de catálogo de conductores (sección 12 de VNR-GIS.md).

``COD_COND → material, sección, R1/X1, R0/X0, ampacity, nominal_kv``. El catálogo
completa lo que falta; **nunca** se fabrican parámetros que no estén aprobados.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from vnr_etl.models import ConductorType


@dataclass
class ConductorCatalog:
    """Catálogo aprobado con consulta de cobertura y sin fabricación de valores."""

    entries: list[ConductorType] = field(default_factory=list)

    def by_code(self) -> dict[str, ConductorType]:
        return {c.conductor_code: c for c in self.entries}

    def coverage(self, codes: Sequence[str]) -> dict:
        """Fracción de códigos que el catálogo resuelve con parámetros completos."""
        by_code = self.by_code()
        total = len(set(codes))
        resolved = 0
        missing: list[str] = []
        for code in sorted(set(codes)):
            entry = by_code.get(code)
            if entry is not None and self._is_complete(entry):
                resolved += 1
            else:
                missing.append(code)
        return {
            'total': total,
            'resolved': resolved,
            'coverage': (resolved / total) if total else 1.0,
            'missing': missing,
        }

    @staticmethod
    def _is_complete(entry: ConductorType) -> bool:
        return all(
            v is not None for v in (
                entry.r1_ohm_km, entry.x1_ohm_km, entry.r0_ohm_km, entry.x0_ohm_km,
            )
        ) and entry.r1_ohm_km >= 0


def load_conductor_catalog(rows: Sequence[Mapping]) -> ConductorCatalog:
    """Construye el catálogo desde filas con los campos esperados (R1/X1/R0/X0/Amps)."""
    entries: list[ConductorType] = []
    for row in rows:
        code = row.get('ID') or row.get('conductor_code') or row.get('code') or ''
        if not code:
            continue
        entries.append(ConductorType(
            conductor_code=str(code),
            material=str(row.get('Material', '')),
            section_mm2=_float_or_none(row.get('Section')),
            r1_ohm_km=_float_or_none(row.get('R1')),
            x1_ohm_km=_float_or_none(row.get('X1')),
            r0_ohm_km=_float_or_none(row.get('R0')),
            x0_ohm_km=_float_or_none(row.get('X0')),
            ampacity_a=_float_or_none(row.get('Amps')),
            nominal_kv=_float_or_none(row.get('NominalKV')),
            source_layer=str(row.get('source_layer', '')),
            source_id=str(row.get('source_id', '')),
        ))
    return ConductorCatalog(entries=entries)


def _float_or_none(value) -> float | None:
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None