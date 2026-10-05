"""Orquestación única y fail-closed de validación y exportación VNR.

La interfaz de línea de comandos y la API web deben pasar por este módulo. Así
no pueden divergir en las reglas de CRS, topología, enriquecimiento, perfil de
destino ni round-trip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vnr_etl.config import Settings
from vnr_etl.electrical import enrich_electrical
from vnr_etl.exporters import CymdistExporter, DgsExporter, TargetProfile
from vnr_etl.exporters.base import ExportBlocked
from vnr_etl.models import CanonicalModel
from vnr_etl.topology import validate_topology
from vnr_etl.validation import run_gates
from vnr_etl.validation.gates import GateVerdict


@dataclass
class Assessment:
    verdict: GateVerdict
    topology: dict
    enrichment: dict
    exporter_errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            'counts': self.counts,
            'topology': self.topology,
            'enrichment': self.enrichment,
            'exporter_errors': list(self.exporter_errors),
            'gates': self.verdict.as_dict(),
            'readiness': self.readiness,
        }

    counts: dict = field(default_factory=dict)

    @property
    def readiness(self) -> str:
        passed = {result.gate: result.passed for result in self.verdict.results}
        if all(passed.get(gate, False) for gate in 'ABCDEFGH'):
            return 'SIMULATOR_VERIFIED'
        if all(passed.get(gate, False) for gate in 'ABCDEF'):
            return 'EXPORT_READY'
        if all(passed.get(gate, False) for gate in 'ABCD'):
            return 'ELECTRICALLY_ENRICHED'
        if all(passed.get(gate, False) for gate in 'ABC'):
            return 'TOPOLOGY_VALID'
        return 'BLOCKED'


@dataclass
class ExportResult:
    paths: list[Path]
    assessment: Assessment

    @property
    def verdict(self) -> GateVerdict:
        return self.assessment.verdict

    @property
    def readiness(self) -> str:
        return self.assessment.readiness

    def as_dict(self) -> dict:
        return {
            'paths': [str(path) for path in self.paths],
            **self.assessment.as_dict(),
        }


class VnrApplicationService:
    """Evalúa y exporta modelos con el mismo contrato en todas las interfaces."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def _profile(self, target: str) -> TargetProfile | None:
        configured = self.settings.templates.get(target)
        return TargetProfile.load(configured) if configured else None

    def _exporter(self, target: str):
        profile = self._profile(target)
        if target == 'dgs':
            return DgsExporter(profile=profile), profile
        if target == 'cymdist':
            return CymdistExporter(profile=profile), profile
        raise ValueError(f'Destino de exportación desconocido: {target}')

    def assess(
        self,
        model: CanonicalModel,
        target: str = 'dgs',
        *,
        roundtrip_ok: bool | None = None,
        simulator_import_ok: bool | None = None,
        load_flow_ok: bool | None = None,
        require_simulator: bool = False,
    ) -> Assessment:
        topology = validate_topology(
            model,
            allow_islands=bool(self.settings.validation.get('allow_islands', False)),
            allow_self_loops=bool(self.settings.validation.get('allow_self_loops', False)),
            require_source=bool(self.settings.validation.get('require_source', True)),
        )
        enrichment = enrich_electrical(
            model,
            require_catalog_mapping=bool(
                self.settings.validation.get('require_catalog_mapping', True)
            ),
        )
        exporter, profile = self._exporter(target)
        exporter_errors = exporter.validate_mapping(model)
        working_crs = model.metadata.get('working_crs')
        projected = model.metadata.get('working_crs_is_projected') is True
        verdict = run_gates(
            model,
            strict=self.settings.strict,
            crs_report={
                'ok': bool(working_crs and projected),
                'projected': projected,
                'working_crs': working_crs,
                'error': '' if projected else 'Falta evidencia de CRS proyectado.',
            },
            topology_report={
                'ok': topology.ok(),
                'issues': [issue.as_dict() for issue in topology.issues],
            },
            enrichment=enrichment.as_dict(),
            exporter_errors=exporter_errors,
            export_profile_verified=bool(profile and profile.verified),
            roundtrip_ok=roundtrip_ok,
            simulator_import_ok=simulator_import_ok,
            load_flow_ok=load_flow_ok,
            require_simulator=require_simulator,
        )
        return Assessment(
            verdict=verdict,
            topology=topology.as_dict(),
            enrichment=enrichment.as_dict(),
            exporter_errors=exporter_errors,
            counts=model.counts(),
        )

    def export(
        self,
        model: CanonicalModel,
        target: str,
        output_dir: Path,
        *,
        simulator_import_ok: bool | None = None,
        load_flow_ok: bool | None = None,
        require_simulator: bool = False,
    ) -> ExportResult:
        if require_simulator and (
            simulator_import_ok is not True or load_flow_ok is not True
        ):
            raise ExportBlocked(
                'Export de producción bloqueado: G/H requieren evidencia explícita '
                'de importación y flujo de carga.'
            )
        exporter, _profile = self._exporter(target)
        preflight = self.assess(model, target)
        failed = [
            result for result in preflight.verdict.results
            if result.gate in 'ABCDE' and not result.passed
        ]
        if failed:
            detail = '; '.join(f'{item.gate}: {item.detail}' for item in failed)
            raise ExportBlocked(f'Export {target.upper()} bloqueado antes de escribir: {detail}')

        paths = exporter.export(model, Path(output_dir))
        roundtrip_ok = bool(paths) and all(path.is_file() and path.stat().st_size > 0 for path in paths)
        if target == 'dgs':
            dgs_paths = [path for path in paths if path.suffix.lower() == '.dgs']
            roundtrip_ok = len(dgs_paths) == 1 and not exporter.roundtrip_errors(dgs_paths[0])
        final = self.assess(
            model,
            target,
            roundtrip_ok=roundtrip_ok,
            simulator_import_ok=simulator_import_ok,
            load_flow_ok=load_flow_ok,
            require_simulator=require_simulator,
        )
        if final.verdict.blocked:
            raise ExportBlocked(
                f'Export {target.upper()} generado pero no cumple las puertas obligatorias.'
            )
        return ExportResult(paths=paths, assessment=final)
