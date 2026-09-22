"""Tipos inmutables para comunicar fallos con ubicacion precisa."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    file: str
    section: str | None = None
    row: int | None = None
    field: str | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "file": self.file,
            "section": self.section,
            "row": self.row,
            "field": self.field,
        }


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    severity: Severity
    location: SourceLocation | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("Diagnostic code cannot be empty")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    @classmethod
    def blocking(
        cls,
        code: str,
        message: str,
        location: SourceLocation | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> "Diagnostic":
        return cls(code, message, Severity.BLOCKING, location, details or {})

    @classmethod
    def warning(
        cls,
        code: str,
        message: str,
        location: SourceLocation | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> "Diagnostic":
        return cls(code, message, Severity.WARNING, location, details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "location": self.location.to_dict() if self.location else None,
            "details": dict(self.details),
        }
