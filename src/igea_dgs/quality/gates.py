"""Puertas que impiden publicar una conversion electricamente incompleta."""

from collections.abc import Iterable
from dataclasses import dataclass

from .diagnostics import Diagnostic, Severity


class QualityGateError(RuntimeError):
    """Una puerta contiene al menos un diagnostico bloqueante."""


@dataclass(frozen=True, slots=True)
class GateResult:
    gate: str
    diagnostics: tuple[Diagnostic, ...]

    def __init__(self, gate: str, diagnostics: Iterable[Diagnostic] = ()) -> None:
        object.__setattr__(self, "gate", gate)
        object.__setattr__(self, "diagnostics", tuple(diagnostics))

    @property
    def blocked(self) -> bool:
        return any(item.severity is Severity.BLOCKING for item in self.diagnostics)

    def raise_if_blocked(self) -> None:
        blocking = [item for item in self.diagnostics if item.severity is Severity.BLOCKING]
        if blocking:
            summary = "; ".join(f"{item.code}: {item.message}" for item in blocking)
            raise QualityGateError(f"{self.gate} blocked: {summary}")
