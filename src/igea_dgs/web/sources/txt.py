"""Adaptador de los tres TXT IGEA/CYMDIST custodiados."""

from __future__ import annotations

from pathlib import Path

from .base import SourceLoadResult, provenance, validate_snapshot
from ..source_runs import SourceSnapshot


class TxtSourceAdapter:
    mode = 'txt'

    def load(self, snapshot: SourceSnapshot, *, aliases: dict[str, str]) -> SourceLoadResult:
        validate_snapshot(
            snapshot,
            mode=self.mode,
            allowed={'red', 'loads', 'equipment', 'equipment_extra'},
            required={'red', 'loads', 'equipment'},
        )
        from ...catalog_merge import completar, diagnosticar
        from ...dataset import CymdistDataset

        dataset = CymdistDataset.from_files(
            snapshot.path_for('red'),
            snapshot.path_for('loads'),
            snapshot.path_for('equipment'),
        )
        extra = snapshot.path_for('equipment_extra')
        report_raw = (
            completar(dataset, [extra], aliases=aliases)
            if extra else diagnosticar(dataset, aliases=aliases)
        )
        report = {
            'initial_coverage': report_raw.cobertura_inicial,
            'final_coverage': report_raw.cobertura_final,
            'types_in_network': len(report_raw.codigos_en_red),
            'added': {Path(key).name: value for key, value in report_raw.anadidos.items()},
            'unresolved': sorted(report_raw.sin_resolver),
            'text': report_raw.texto(),
            'critical': report_raw.cobertura_final < 0.5,
        }
        return SourceLoadResult(
            dataset=dataset,
            catalog_report=report,
            provenance=provenance(snapshot),
        )
