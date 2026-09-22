"""Orquestador único de puertas del flujo TXT -> DGS -> PowerFactory."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Exclusion:
    source_key: str
    reason: str


@dataclass(frozen=True, slots=True)
class PipelineSummary:
    gate: str = "G0"
    exclusions: tuple[Exclusion, ...] = ()
    provenance: tuple[str, ...] = ()
    original_case: str = "not-run"
    diagnostic_case: str = "not-created"


@dataclass(frozen=True, slots=True)
class StageOutcome:
    stage: str
    blocked: bool = False
    unavailable: bool = False
    context: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    @property
    def exit_code(self) -> int:
        return 3 if self.unavailable else 2 if self.blocked else 0

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "blocked": self.blocked,
                "unavailable": self.unavailable, "exit_code": self.exit_code,
                "diagnostics": list(self.diagnostics)}


Stage = Callable[[Mapping[str, Any]], StageOutcome]


class PipelineService:
    STAGES = ("inspect", "validate_input", "convert", "import_pf", "validate_pf", "study")

    def __init__(self, **stages: Stage) -> None:
        self._stages = stages

    def _invoke(self, name: str, context: Mapping[str, Any]) -> StageOutcome:
        operation = self._stages.get(name)
        if operation is None:
            return StageOutcome(name, unavailable=True, diagnostics=("STAGE_NOT_CONFIGURED",))
        return operation(context)

    def inspect(self, context: Mapping[str, Any]) -> StageOutcome: return self._invoke("inspect", context)
    def validate_input(self, context: Mapping[str, Any]) -> StageOutcome: return self._invoke("validate_input", context)
    def convert(self, context: Mapping[str, Any]) -> StageOutcome: return self._invoke("convert", context)
    def import_pf(self, context: Mapping[str, Any]) -> StageOutcome: return self._invoke("import_pf", context)
    def validate_pf(self, context: Mapping[str, Any]) -> StageOutcome: return self._invoke("validate_pf", context)
    def study(self, context: Mapping[str, Any]) -> StageOutcome: return self._invoke("study", context)
    def catalog(self, context: Mapping[str, Any]) -> StageOutcome: return self._invoke("catalog", context)

    def run(self, context: Mapping[str, Any]) -> StageOutcome:
        current = StageOutcome("run", context=context)
        for name in self.STAGES:
            current = self._invoke(name, context)
            if current.exit_code:
                return current
        return current
