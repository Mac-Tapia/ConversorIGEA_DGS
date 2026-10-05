"""Enriquecimiento eléctrico (secciones 12 y F de VNR-GIS.md).

La capa GIS por sí sola no basta para un flujo CYMDIST/PowerFactory: falta R/X,
ampacidad, fase, tensión nominal y cargas P/Q. Aquí se comprueba qué falta y se
emite ``missing_electrical_data`` sin inventar nada.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from vnr_etl.models import CanonicalModel


def apparent_power(kw: float, kvar: float) -> float:
    return math.hypot(kw, kvar)


def power_factor(kw: float, kvar: float) -> float:
    s = apparent_power(kw, kvar)
    return kw / s if s else 1.0


@dataclass
class EnrichmentReport:
    missing: dict[str, list[str]] = field(default_factory=dict)
    ready: bool = False
    readiness: str = 'DISCOVERED'
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            'missing': {k: list(v) for k, v in self.missing.items()},
            'ready': self.ready,
            'readiness': self.readiness,
            'notes': list(self.notes),
        }


def enrich_electrical(
    model: CanonicalModel,
    *,
    require_catalog_mapping: bool = True,
) -> EnrichmentReport:
    """Comprueba la cobertura eléctrica y asigna S/pf a las cargas.

    No muta parámetros que falten: los reporta. ``oraculo`` de S/pf se calcula a
    partir de P/Q (sección 12): `S = √(P²+Q²)`, `pf = P/S`.
    """
    report = EnrichmentReport()
    conductor = model.conductor_by_code()
    used_codes = {s.conductor_code for s in model.sections if s.conductor_code}
    missing_codes = sorted(
        code for code in used_codes
        if code not in conductor
        or conductor[code].r1_ohm_km is None
        or conductor[code].x1_ohm_km is None
    )
    if missing_codes:
        report.missing['conductors'] = missing_codes
        if require_catalog_mapping:
            report.notes.append(
                f'{len(missing_codes)} conductor(es) sin parámetros R/X aprobados.'
            )

    sin_tension = sorted(
        {n.node_id for n in model.nodes if n.nominal_kv in (None, 0)}
    )
    if sin_tension:
        report.missing['nominal_kv'] = sin_tension

    sin_fase = sorted(
        {s.section_id for s in model.sections if not s.phases}
    )
    if sin_fase:
        report.missing['phases'] = sin_fase

    sin_carga = sorted(
        l.load_id for l in model.loads if l.kw == 0.0 and l.kvar == 0.0
    )
    if sin_carga:
        report.notes.append(f'{len(sin_carga)} carga(s) sin P/Q medida (kw=kvar=0).')

    # Secuencia de disponibilidad (U17): sin tensión no se puede ni emplazar la red
    # (NORMALIZED); con tensión pero con conductores/fases sin resolver la topología
    # ya es válida pero el modelo no está eléctricamente completo (TOPOLOGY_VALID).
    if report.missing.get('nominal_kv'):
        report.readiness = 'NORMALIZED'
    elif report.missing:
        report.readiness = 'TOPOLOGY_VALID'
    else:
        report.readiness = 'ELECTRICALLY_ENRICHED'

    report.ready = not report.missing
    return report