"""Entidades electricas con unidades explicitas y Decimal."""

from dataclasses import dataclass
from decimal import Decimal

from .phases import PhaseSet


@dataclass(frozen=True, slots=True)
class CircuitMultiplicity:
    count: int

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("Circuit count must be positive")


@dataclass(frozen=True, slots=True)
class ConductorArrangement:
    conductors_per_phase: int
    cross_section_mm2: Decimal


@dataclass(frozen=True, slots=True)
class OverheadLine:
    section_id: str
    from_node: str
    to_node: str
    phases: PhaseSet
    catalog_id: str
    length_km: Decimal
    circuits: CircuitMultiplicity
    conductors_per_phase: int
    cross_section_mm2: Decimal


@dataclass(frozen=True, slots=True)
class UndergroundCable(OverheadLine):
    pass


@dataclass(frozen=True, slots=True)
class LoadSpec:
    section_id: str
    device_number: str
    phases: PhaseSet
    p_mw: Decimal
    q_mvar: Decimal


@dataclass(frozen=True, slots=True)
class SourceSpec:
    source_id: str
    node_id: str
    nominal_kv: Decimal


@dataclass(frozen=True, slots=True)
class SolarPlantSpec(SourceSpec):
    rated_mw: Decimal
    power_factor: Decimal


@dataclass(frozen=True, slots=True)
class ThermalGeneratorSpec(SourceSpec):
    rated_mw: Decimal
    rated_mva: Decimal
    technology: str
