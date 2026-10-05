"""Puertas de validación (sección 17 de VNR-GIS.md).

A: fuente/esquema; B: GIS/CRS; C: topología/snapping; D: eléctrico;
E: mapeo de simulador; F: serialización/round-trip; G: import en simulador;
H: convergencia de flujo de carga. G y H solo se pueden superar con el simulador.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vnr_etl.models import CanonicalModel

GATES = ('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H')


@dataclass
class GateResult:
    gate: str
    label: str
    passed: bool
    mandatory: bool = True
    detail: str = ''
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            'gate': self.gate,
            'label': self.label,
            'passed': self.passed,
            'mandatory': self.mandatory,
            'detail': self.detail,
            'evidence': self.evidence,
        }


@dataclass
class GateVerdict:
    results: list[GateResult] = field(default_factory=list)
    blocked: bool = False
    missing_simulator: list[str] = field(default_factory=list)

    def all_passed(self) -> bool:
        return all(r.passed for r in self.results if r.mandatory)

    def as_dict(self) -> dict:
        return {
            'blocked': self.blocked,
            'missing_simulator': list(self.missing_simulator),
            'results': [r.as_dict() for r in self.results],
        }


def run_gates(
    model: CanonicalModel,
    *,
    strict: bool = True,
    crs_report: Mapping[str, Any] | None = None,
    topology_report: Mapping[str, Any] | None = None,
    enrichment: Mapping[str, Any] | None = None,
    exporter_errors: list[str] | None = None,
    export_profile_verified: bool | None = None,
    roundtrip_ok: bool | None = None,
    simulator_import_ok: bool | None = None,
    load_flow_ok: bool | None = None,
    require_simulator: bool = False,
) -> GateVerdict:
    verdict = GateVerdict()
    source_evidence = bool(
        model.metadata.get('schema_fingerprint')
        and model.metadata.get('source_fingerprint')
    )
    verdict.results.append(GateResult(
        'A', 'Fuente / esquema',
        passed=source_evidence,
        detail=('Huellas de fuente y esquema presentes.' if source_evidence
                else 'Falta huella de fuente o esquema.'),
    ))

    crs_ok = bool(
        crs_report
        and crs_report.get('ok') is True
        and crs_report.get('projected') is True
        and crs_report.get('working_crs')
    )
    verdict.results.append(GateResult(
        'B', 'GIS / CRS',
        passed=crs_ok,
        detail=(crs_report or {}).get('error', '') if not crs_ok else 'CRS proyectado.',
    ))

    topo_ok = bool(topology_report and topology_report.get('ok') is True)
    topology_detail = ''
    if not topo_ok:
        issues = (topology_report or {}).get('issues') or []
        if issues:
            topology_detail = (
                str(issues[0].get('message', ''))
                if isinstance(issues[0], Mapping)
                else str(issues[0])
            )
        else:
            topology_detail = 'Falta evidencia topológica.'
    verdict.results.append(GateResult(
        'C', 'Topología / snapping',
        passed=topo_ok,
        detail=topology_detail,
    ))

    enriched = bool(enrichment and enrichment.get('ready'))
    verdict.results.append(GateResult(
        'D', 'Eléctrico',
        passed=enriched,
        detail='Datos eléctricos incompletos.' if not enriched else 'Enriquecido.',
    ))

    mapping_ok = bool(
        exporter_errors is not None
        and not exporter_errors
        and export_profile_verified is True
    )
    verdict.results.append(GateResult(
        'E', 'Mapeo de simulador',
        passed=mapping_ok,
        detail=(
            '; '.join((exporter_errors or [])[:3])
            if exporter_errors
            else ('Perfil objetivo no verificado.' if export_profile_verified is not True else '')
        ),
    ))

    roundtrip = roundtrip_ok is True
    verdict.results.append(GateResult(
        'F', 'Serialización / round-trip',
        passed=roundtrip,
        detail='Round-trip falló.' if not roundtrip else '',
    ))

    import_ok = simulator_import_ok is True
    load_flow_passed = load_flow_ok is True
    verdict.results.append(GateResult(
        'G', 'Import en simulador', passed=import_ok, mandatory=require_simulator,
        detail='' if import_ok else 'Falta evidencia de importación en el simulador.',
    ))
    verdict.results.append(GateResult(
        'H', 'Flujo de carga', passed=load_flow_passed, mandatory=require_simulator,
        detail='' if load_flow_passed else 'Falta evidencia de convergencia y chequeo eléctrico.',
    ))
    verdict.missing_simulator = [
        gate for gate, passed in (('G', import_ok), ('H', load_flow_passed))
        if not passed
    ]

    if strict:
        verdict.blocked = not verdict.all_passed()
    return verdict
