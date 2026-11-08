"""GIS: CRS, snapping y reconstrucción de nodos (secciones 9–10, 7 y B)."""

from .crs import (  # noqa: F401
    CRSManager,
)
from .geometry import (  # noqa: F401
    coords_from_geojson,
    line_endpoints,
    polyline_length_m,
)
from .snapping import (  # noqa: F401
    SnapRecord,
    SnapResult,
    rebuild_nodes,
    snap_endpoints,
)
