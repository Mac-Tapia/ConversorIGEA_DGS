"""Conectores de fuente (secciones 8 y U10 de VNR-GIS.md)."""

from .arcgis import ArcGISLayer, ArcGISRestAdapter  # noqa: F401
from .base import (  # noqa: F401
    LayerInfo,
    NetworkSource,
    VNRSourceAdapter,
)
from .delimited import DelimitedTextAdapter  # noqa: F401
from .registry import (  # noqa: F401
    ADAPTERS,
    resolve_adapter,
)
from .vector import VectorFileAdapter  # noqa: F401
