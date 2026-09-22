"""Estudios de flujo sin alterar el caso original."""

from dataclasses import dataclass
from typing import Any

from igea_dgs.domain.feeder import StrictFeederModel


@dataclass(frozen=True, slots=True)
class LoadFlowResult:
    converged: bool
    case: str
    copy_name: str | None = None
    changes: tuple[str, ...] = ()


def run_original_load_flow(port: Any, feeder: StrictFeederModel) -> LoadFlowResult:
    """Ejecuta ComLdf sin aplicar correcciones ni mutar objetos del caso base."""
    before = port.snapshot()
    converged = bool(port.run_load_flow())
    if port.snapshot() != before:
        raise RuntimeError("ORIGINAL_CASE_MUTATED")
    return LoadFlowResult(converged, "original")


def run_diagnostic_copy(port: Any, feeder: StrictFeederModel, run_id: str) -> LoadFlowResult:
    """Crea una copia identificable; cualquier corrección pertenece solo a ella."""
    copy_name = f"{feeder.feeder_id}__diagnostic__{run_id}"
    diagnostic = port.create_diagnostic_copy(copy_name)
    converged = bool(diagnostic.run_load_flow())
    return LoadFlowResult(converged, "diagnostic", copy_name, ())
