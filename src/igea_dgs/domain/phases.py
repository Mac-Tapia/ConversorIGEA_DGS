"""Conjuntos de fases sin degradacion a trifasico por defecto."""

from enum import StrEnum


class PhaseSet(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    AB = "AB"
    AC = "AC"
    BC = "BC"
    ABC = "ABC"

    @classmethod
    def parse(cls, value: str) -> "PhaseSet":
        normalized = "".join(phase for phase in "ABC" if phase in value.upper())
        if not normalized:
            raise ValueError(f"Invalid or empty phase set: {value!r}")
        return cls(normalized)
