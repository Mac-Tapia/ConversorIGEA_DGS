"""Ficha oficial verificable; no admite fuentes web arbitrarias."""

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class DatasheetRecord:
    manufacturer: str
    model: str
    revision: str
    official_url: str
    retrieved_at: date
    sha256: str
    units: Mapping[str, str]
    parameters: Mapping[str, Any]

    def __post_init__(self) -> None:
        required = (self.manufacturer, self.model, self.revision, self.sha256)
        if any(not value.strip() for value in required):
            raise ValueError("Datasheet identity and SHA-256 are mandatory")
        if len(self.sha256) != 64:
            raise ValueError("Datasheet SHA-256 must contain 64 hexadecimal characters")
        host = (urlparse(self.official_url).hostname or "").lower()
        manufacturer_token = "".join(ch for ch in self.manufacturer.lower() if ch.isalnum())
        host_token = "".join(ch for ch in host if ch.isalnum())
        if not host or manufacturer_token not in host_token:
            raise ValueError("Datasheet URL must belong to the manufacturer domain")
        object.__setattr__(self, "units", MappingProxyType(dict(self.units)))
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
