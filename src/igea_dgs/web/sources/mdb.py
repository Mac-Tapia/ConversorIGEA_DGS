"""Adaptador de base Access/CYMDIST custodiada."""

from __future__ import annotations

from .base import SourceLoadResult, provenance, validate_snapshot
from ..source_runs import SourceSnapshot


class MdbSourceAdapter:
    mode = 'mdb'

    def load(self, snapshot: SourceSnapshot, *, aliases: dict[str, str]) -> SourceLoadResult:
        del aliases
        validate_snapshot(
            snapshot,
            mode=self.mode,
            allowed={'mdb', 'equipment_mdb', 'study'},
            required={'mdb'},
        )
        from ...access import read_access_dataset

        networks = None
        study = snapshot.path_for('study')
        if study:
            from ...study import study_networks

            networks = study_networks(study)
        dataset = read_access_dataset(
            snapshot.path_for('mdb'),
            equipment_db=snapshot.path_for('equipment_mdb') or None,
            networks=networks,
        )
        return SourceLoadResult(dataset=dataset, provenance=provenance(snapshot))
