"""Adaptador de base Access/CYMDIST custodiada."""

from __future__ import annotations

from .base import SourceLoadResult, provenance, validate_snapshot
from .snapshot import SourceSnapshot


class MdbSourceAdapter:
    mode = 'mdb'

    def __init__(self, *, load_year: int | None = None) -> None:
        self.load_year = load_year

    def load(self, snapshot: SourceSnapshot, *, aliases: dict[str, str]) -> SourceLoadResult:
        del aliases
        validate_snapshot(
            snapshot,
            mode=self.mode,
            allowed={'mdb', 'equipment_mdb', 'study'},
            required={'mdb'},
        )
        from ..access import read_access_dataset

        networks = None
        study = snapshot.path_for('study')
        if study:
            from ..study import study_networks

            networks = study_networks(study)
        # El año solo se pasa si se pidió: sin él, el lector toma el escenario más
        # reciente de cada dispositivo, como el export TXT.
        anio = {'load_year': self.load_year} if self.load_year is not None else {}
        dataset = read_access_dataset(
            snapshot.path_for('mdb'),
            equipment_db=snapshot.path_for('equipment_mdb') or None,
            networks=networks,
            **anio,
        )
        return SourceLoadResult(dataset=dataset, provenance=provenance(snapshot))
