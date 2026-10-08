"""Adaptador de los tres TXT IGEA/CYMDIST custodiados."""

from __future__ import annotations

from pathlib import Path

from .base import SourceLoadResult, provenance, validate_snapshot
from .snapshot import SourceSnapshot

EXTRA = 'equipment_extra'


def extra_slot(index: int) -> str:
    """Casilla del BD_Equipo complementario número ``index`` (desde 1)."""
    return EXTRA if index == 1 else f'{EXTRA}_{index}'


def _extra_slots(snapshot: SourceSnapshot) -> list[str]:
    # Orden numérico, no alfabético: con texto «_10» iría antes que «_2», y el orden
    # decide qué catálogo rellena primero un hueco (lo cargado no se sobrescribe).
    def numero(slot: str) -> int:
        return 1 if slot == EXTRA else int(slot.rsplit('_', 1)[1])

    return sorted(
        (s for s in snapshot.files
         if s == EXTRA or (s.startswith(EXTRA + '_') and s.rsplit('_', 1)[1].isdigit())),
        key=numero,
    )


class TxtSourceAdapter:
    mode = 'txt'

    def load(self, snapshot: SourceSnapshot, *, aliases: dict[str, str]) -> SourceLoadResult:
        extras = _extra_slots(snapshot)
        validate_snapshot(
            snapshot,
            mode=self.mode,
            allowed={'red', 'loads', 'equipment', *extras},
            required={'red', 'loads', 'equipment'},
        )
        from ..catalog_merge import completar, diagnosticar
        from ..dataset import CymdistDataset

        dataset = CymdistDataset.from_files(
            snapshot.path_for('red'),
            snapshot.path_for('loads'),
            snapshot.path_for('equipment'),
        )
        rutas_extra = [snapshot.path_for(slot) for slot in extras]
        report_raw = (
            completar(dataset, rutas_extra, aliases=aliases)
            if rutas_extra else diagnosticar(dataset, aliases=aliases)
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
