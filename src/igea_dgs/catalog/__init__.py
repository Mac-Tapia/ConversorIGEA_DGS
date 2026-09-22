"""Catalogo electrico estricto y trazable."""

from .datasheets import DatasheetRecord
from .models import ApprovedMapping, ResolvedEquipment
from .resolver import EquipmentCatalog, UnresolvedEquipmentError

__all__ = [
    "ApprovedMapping",
    "DatasheetRecord",
    "EquipmentCatalog",
    "ResolvedEquipment",
    "UnresolvedEquipmentError",
]
