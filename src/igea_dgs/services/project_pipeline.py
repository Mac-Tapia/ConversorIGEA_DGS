"""Pipeline del cockpit: TXT custodiado -> G1/G2/G3/G4 -> publicación atómica."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from igea_dgs.dataset import CymdistDataset
from igea_dgs.dgsio import build_dgs_document, write_dgs_document
from igea_dgs.domain.feeder import StrictFeederModel, build_strict_feeder_model
from igea_dgs.projects import InputManifest, ProjectStore
from igea_dgs.quality.diagnostics import Diagnostic, Severity
from igea_dgs.quality.inventory import build_strict_inventory
from igea_dgs.reporting.atomic import AtomicRunPublisher
from igea_dgs.revisions import RevisionStore
from igea_dgs.rules.trafomix import apply_trafomix_rule
from igea_dgs.validation.model_dgs import validate_model_dgs
from igea_dgs.validation.source_model import validate_source_model


@dataclass(frozen=True, slots=True)
class ProjectPipelineResult:
    last_gate: str
    diagnostics: tuple[Diagnostic, ...]
    context: dict[str, Any]
    artifacts: tuple[str, ...] = ()

    @property
    def exit_code(self) -> int:
        return 2 if any(item.severity is Severity.BLOCKING for item in self.diagnostics) else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_gate": self.last_gate,
            "exit_code": self.exit_code,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "context": self.context,
            "artifacts": list(self.artifacts),
        }


class ProjectPipeline:
    def __init__(self, projects: ProjectStore, revisions: RevisionStore):
        self.projects = projects
        self.revisions = revisions

    @staticmethod
    def _paths(manifest: InputManifest) -> dict[str, Path]:
        return {item.kind: Path(item.path) for item in manifest.files}

    @staticmethod
    def _custody_diagnostics(manifest: InputManifest) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for item in manifest.files:
            path = Path(item.path)
            if not path.is_file():
                diagnostics.append(Diagnostic.blocking("INPUT_FILE_MISSING", item.path))
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != item.sha256:
                diagnostics.append(
                    Diagnostic.blocking(
                        "INPUT_HASH_CHANGED",
                        f"El TXT cambió después de registrarse: {item.path}",
                        details={"registered": item.sha256, "current": digest},
                    )
                )
        return diagnostics

    def _load(self, project_id: str) -> tuple[InputManifest, CymdistDataset, list[Diagnostic]]:
        manifest = self.projects.get_manifest(project_id)
        custody = self._custody_diagnostics(manifest)
        paths = self._paths(manifest)
        dataset = CymdistDataset.from_files(paths["red"], paths["carga"], paths["equipment"])
        return manifest, dataset, custody

    def inspect(self, project_id: str) -> ProjectPipelineResult:
        manifest, dataset, custody = self._load(project_id)
        inventory = build_strict_inventory(dataset)
        diagnostics = tuple(custody) + inventory.gate.diagnostics
        return ProjectPipelineResult(
            "G1",
            diagnostics,
            {
                "project_id": project_id,
                "coverage_percent": inventory.coverage_percent,
                "metrics": dict(inventory.metrics),
                "registered_at": manifest.registered_at,
            },
        )

    @staticmethod
    def _catalog_diagnostics(dataset: CymdistDataset) -> list[Diagnostic]:
        observed_values = {
            value.strip()
            for rows in dataset.equipment_tables.values()
            for row in rows
            for value in row.values()
            if value.strip()
        }
        diagnostics: list[Diagnostic] = []
        for section_id, config in dataset.line_configurations.items():
            code = config.get("LineCableID", "").strip()
            if not code or code not in observed_values:
                diagnostics.append(
                    Diagnostic.blocking(
                        "EQUIPMENT_NOT_FOUND",
                        f"Sin coincidencia exacta en BD_Equipo para {section_id}: {code or '<vacío>'}",
                    )
                )
        return diagnostics

    def validate_revision(self, project_id: str, revision_id: str) -> ProjectPipelineResult:
        snapshot = self.revisions.snapshot(revision_id)
        manifest, dataset, custody = self._load(project_id)
        inventory = build_strict_inventory(dataset)
        g1 = tuple(custody) + inventory.gate.diagnostics
        if any(item.severity is Severity.BLOCKING for item in g1):
            return ProjectPipelineResult("G1", g1, {"revision_version": snapshot.version})

        diagnostics = self._catalog_diagnostics(dataset)
        trafomix = apply_trafomix_rule(dataset)
        diagnostics.extend(trafomix.gate.diagnostics)
        models: list[StrictFeederModel] = []
        for feeder_id in dataset.feeder_ids():
            try:
                model = build_strict_feeder_model(dataset, feeder_id)
                retained = set(trafomix.retained_load_keys)
                model = StrictFeederModel(
                    model.feeder_id,
                    model.source,
                    model.lines,
                    tuple(
                        load
                        for load in model.loads
                        if (load.section_id, load.device_number) in retained
                    ),
                )
                models.append(model)
            except (KeyError, TypeError, ValueError) as exc:
                diagnostics.append(Diagnostic.blocking("MODEL_BUILD_FAILED", str(exc)))
        if any(item.severity is Severity.BLOCKING for item in diagnostics):
            return ProjectPipelineResult("G2", tuple(diagnostics), {"revision_version": snapshot.version})

        for model in models:
            diagnostics.extend(validate_source_model(dataset, model).diagnostics)
        if any(item.severity is Severity.BLOCKING for item in diagnostics):
            return ProjectPipelineResult("G3", tuple(diagnostics), {"revision_version": snapshot.version})

        documents = {model.feeder_id: build_dgs_document(model) for model in models}
        for model in models:
            diagnostics.extend(validate_model_dgs(model, documents[model.feeder_id].tables).diagnostics)
        return ProjectPipelineResult(
            "G4",
            tuple(diagnostics),
            {
                "revision_version": snapshot.version,
                "feeders": [model.feeder_id for model in models],
                "output_dir": manifest.output_dir,
            },
        )

    def publish_revision(self, project_id: str, revision_id: str) -> ProjectPipelineResult:
        result = self.validate_revision(project_id, revision_id)
        if result.exit_code:
            return result
        manifest, dataset, _custody = self._load(project_id)
        output = Path(manifest.output_dir)
        artifacts: list[str] = []
        with AtomicRunPublisher(output, str(uuid.uuid4()), revision_id) as publisher:
            for feeder_id in dataset.feeder_ids():
                model = build_strict_feeder_model(dataset, feeder_id)
                target = publisher.staging / f"{feeder_id}.dgs"
                write_dgs_document(build_dgs_document(model), target)
                artifacts.append(str(output / target.name))
            publisher.stage_text(
                "publication-manifest.json",
                json.dumps(
                    {
                        "project_id": project_id,
                        "revision_id": revision_id,
                        "inputs": [item.to_dict() for item in manifest.files],
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
            )
            publisher.commit()
        return ProjectPipelineResult("G4", (), result.context, tuple(artifacts))
