"""Modelo canónico universal del VNRGIS.

Ningún exportador de simulador consume tablas específicas de una empresa; todos
consumen este modelo (sección U9 de VNR-GIS.md). Los campos están en inglés
porque son el contrato entre capas; los comentarios y mensajes, en español.

Las geometrías se guardan en una estructura JSON-izable (listas de coordenadas)
para que el módulo funcione sin ``shapely``: la capa ``gis`` es la única que
materializa objetos geométricos cuando hace falta.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any


def _dict(value: Any) -> dict:
    """``asdict`` profundo y determinista para la serialización del modelo."""
    return asdict(value)


@dataclass
class Lineage:
    """Procedencia de un objeto canónico: de qué fuente y registro viene."""

    source_layer: str = ''
    source_id: str = ''
    source_field: str = ''
    resolution_method: str = ''
    """Cómo se resolvió el campo: SOURCE, DERIVED, CATALOG, MISSING."""
    confidence: float = 1.0


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: str = 'warning'
    object_type: str = ''
    source_id: str = ''
    stage: str = ''


@dataclass
class Node:
    node_id: str
    x: float | None = None
    y: float | None = None
    nominal_kv: float | None = None
    phases: str = ''
    source_layer: str = ''
    source_id: str = ''
    lineage: Lineage | None = None


@dataclass
class Section:
    section_id: str
    from_node: str
    to_node: str
    conductor_code: str = ''
    phases: str = ''
    nominal_kv: float | None = None
    length_m: float | None = None
    status: str = 'in_service'
    geometry: Any = None
    """LineString (o MultiLineString) en el CRS de trabajo, como lista de puntos."""
    source_layer: str = ''
    source_id: str = ''
    feeder_id: str = ''
    lineage: Lineage | None = None


@dataclass
class Load:
    load_id: str
    connection_node: str
    kw: float = 0.0
    kvar: float = 0.0
    phases: str = ''
    nominal_kv: float | None = None
    geometry: Any = None
    source_layer: str = ''
    source_id: str = ''
    feeder_id: str = ''
    lineage: Lineage | None = None


@dataclass
class Transformer:
    transformer_id: str
    connection_node: str
    hv_kv: float | None = None
    lv_kv: float | None = None
    sn_kva: float | None = None
    vector_group: str = ''
    uk_pct: float | None = None
    source_layer: str = ''
    source_id: str = ''


@dataclass
class Switch:
    switch_id: str
    connection_node: str
    kind: str = ''
    on_off: int = 1
    source_layer: str = ''
    source_id: str = ''


@dataclass
class Source:
    source_id: str
    node_id: str
    nominal_kv: float | None = None
    feeder_id: str = ''
    source_layer: str = ''
    source_sid: str = ''


@dataclass
class Regulator:
    regulator_id: str
    connection_node: str
    source_layer: str = ''
    source_id: str = ''


@dataclass
class Capacitor:
    capacitor_id: str
    connection_node: str
    kvar: float = 0.0
    source_layer: str = ''
    source_id: str = ''


@dataclass
class Structure:
    structure_id: str
    x: float | None = None
    y: float | None = None
    source_layer: str = ''
    source_id: str = ''


@dataclass
class ConductorType:
    conductor_code: str
    material: str = ''
    section_mm2: float | None = None
    r1_ohm_km: float | None = None
    x1_ohm_km: float | None = None
    r0_ohm_km: float | None = None
    x0_ohm_km: float | None = None
    ampacity_a: float | None = None
    nominal_kv: float | None = None
    source_layer: str = ''
    source_id: str = ''


@dataclass
class EquipmentType:
    equipment_id: str
    kind: str = ''
    source_layer: str = ''
    source_id: str = ''


@dataclass
class Company:
    company_id: str
    codes: list[str] = field(default_factory=list)
    official_name: str = ''
    aliases: list[str] = field(default_factory=list)


@dataclass
class Period:
    period_id: str
    company_id: str = ''
    year: int | None = None
    label: str = ''


@dataclass
class Feeder:
    feeder_id: str
    company_id: str = ''
    system_id: str = ''
    name: str = ''
    source_id: str = ''


@dataclass
class System:
    system_id: str
    name: str = ''
    company_id: str = ''


@dataclass
class CanonicalModel:
    """Agregado de todos los objetos canónicos de una fuente normalizada."""

    metadata: dict = field(default_factory=dict)
    """Huella de fuente, CRS, versión del adaptador y del modelo (sección U3/D19)."""
    companies: list[Company] = field(default_factory=list)
    periods: list[Period] = field(default_factory=list)
    systems: list[System] = field(default_factory=list)
    feeders: list[Feeder] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    nodes: list[Node] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    structures: list[Structure] = field(default_factory=list)
    transformers: list[Transformer] = field(default_factory=list)
    switches: list[Switch] = field(default_factory=list)
    regulators: list[Regulator] = field(default_factory=list)
    capacitors: list[Capacitor] = field(default_factory=list)
    loads: list[Load] = field(default_factory=list)
    conductor_types: list[ConductorType] = field(default_factory=list)
    equipment_types: list[EquipmentType] = field(default_factory=list)
    lineage: list[Lineage] = field(default_factory=list)
    validation_issues: list[ValidationIssue] = field(default_factory=list)

    # --- índices de conveniencia, reconstruidos bajo demanda -------------------
    def nodes_by_id(self) -> dict[str, Node]:
        return {n.node_id: n for n in self.nodes}

    def sections_by_id(self) -> dict[str, Section]:
        return {s.section_id: s for s in self.sections}

    def conductor_by_code(self) -> dict[str, ConductorType]:
        return {c.conductor_code: c for c in self.conductor_types}

    def to_dict(self) -> dict:
        return _dict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CanonicalModel:
        """Reconstruye el modelo desde su serialización JSON."""
        def many(cls_, key):
            return [cls_(**item) for item in (data.get(key) or [])]

        m = cls()
        m.metadata = dict(data.get('metadata') or {})
        m.companies = many(Company, 'companies')
        m.periods = many(Period, 'periods')
        m.systems = many(System, 'systems')
        m.feeders = many(Feeder, 'feeders')
        m.sources = many(Source, 'sources')
        m.nodes = many(Node, 'nodes')
        m.sections = many(Section, 'sections')
        m.structures = many(Structure, 'structures')
        m.transformers = many(Transformer, 'transformers')
        m.switches = many(Switch, 'switches')
        m.regulators = many(Regulator, 'regulators')
        m.capacitors = many(Capacitor, 'capacitors')
        m.loads = many(Load, 'loads')
        m.conductor_types = many(ConductorType, 'conductor_types')
        m.equipment_types = many(EquipmentType, 'equipment_types')
        m.lineage = [(Lineage(**i) if isinstance(i, dict) else i) for i in (data.get('lineage') or [])]
        m.validation_issues = many(ValidationIssue, 'validation_issues')
        return m

    def counts(self) -> dict[str, int]:
        """Conteos por tipo, para los informes de auditoría y de calidad."""
        return {
            'companies': len(self.companies),
            'feeders': len(self.feeders),
            'sources': len(self.sources),
            'nodes': len(self.nodes),
            'sections': len(self.sections),
            'loads': len(self.loads),
            'transformers': len(self.transformers),
            'switches': len(self.switches),
        }


def iter_named_collections(model: CanonicalModel) -> Iterator[tuple[str, list]]:
    """Recorre las colecciones de objetos canónicos por su nombre."""
    for name in (
        'companies', 'periods', 'systems', 'feeders', 'sources', 'nodes',
        'sections', 'structures', 'transformers', 'switches', 'regulators',
        'capacitors', 'loads', 'conductor_types', 'equipment_types',
    ):
        yield name, getattr(model, name)