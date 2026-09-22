"""Resultados comunes para validadores independientes."""

from dataclasses import dataclass

from igea_dgs.quality.diagnostics import Diagnostic, Severity


@dataclass(frozen=True, slots=True)
class FidelityResult:
    diagnostics: tuple[Diagnostic, ...]

    @property
    def blocked(self) -> bool:
        return any(item.severity is Severity.BLOCKING for item in self.diagnostics)

    @property
    def error_codes(self) -> frozenset[str]:
        return frozenset(item.code for item in self.diagnostics if item.severity is Severity.BLOCKING)
