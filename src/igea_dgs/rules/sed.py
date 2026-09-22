"""Separacion conceptual entre emplazamiento SED y transformador demostrado."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SedSite:
    code: str
    node_id: str
    load_key: tuple[str, str]


@dataclass(frozen=True, slots=True)
class TransformerSpec:
    catalog_id: str
    rated_kva: float
    primary_kv: float
    secondary_kv: float
    uk_percent: float
    copper_loss_kw: float
