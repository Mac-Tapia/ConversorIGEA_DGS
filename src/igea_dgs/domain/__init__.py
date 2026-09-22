"""Entidades de dominio estrictas del conversor."""

from .provenance import Provenanced, ProvenanceKind
from .phases import PhaseSet
from .equipment import (
    CircuitMultiplicity,
    ConductorArrangement,
    LoadSpec,
    OverheadLine,
    SolarPlantSpec,
    SourceSpec,
    ThermalGeneratorSpec,
    UndergroundCable,
)

__all__ = [
    "CircuitMultiplicity",
    "ConductorArrangement",
    "LoadSpec",
    "OverheadLine",
    "PhaseSet",
    "ProvenanceKind",
    "Provenanced",
    "SolarPlantSpec",
    "SourceSpec",
    "ThermalGeneratorSpec",
    "UndergroundCable",
]
