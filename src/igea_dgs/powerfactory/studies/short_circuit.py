"""Preflight y ejecución segura de cortocircuito IEC 60909."""

from dataclasses import dataclass
from typing import Any, Mapping


REQUIRED_SOURCE_FIELDS = (
    "r0_ohm",
    "x0_ohm",
    "r1_ohm",
    "x1_ohm",
    "short_circuit_mva",
)


@dataclass(frozen=True, slots=True)
class StudyResult:
    status: str
    error_codes: frozenset[str] = frozenset()


def _value(source: object, field: str) -> object | None:
    if isinstance(source, Mapping):
        return source.get(field)
    return getattr(source, field, None)


def run_short_circuit_if_complete(port: Any, source: object) -> StudyResult:
    missing = [field for field in REQUIRED_SOURCE_FIELDS if _value(source, field) in (None, "")]
    if missing:
        return StudyResult("blocked", frozenset({"SOURCE_SHORT_CIRCUIT_DATA_MISSING"}))
    try:
        passed = bool(port.run_short_circuit())
    except (PermissionError, ModuleNotFoundError):
        return StudyResult(
            "unavailable",
            frozenset({"POWERFACTORY_SHORT_CIRCUIT_LICENCE_UNAVAILABLE"}),
        )
    if not passed:
        return StudyResult("failed", frozenset({"SHORT_CIRCUIT_EXECUTION_FAILED"}))
    return StudyResult("passed")
