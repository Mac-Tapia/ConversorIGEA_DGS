"""Puertas de validación A–H (sección 17 de VNR-GIS.md).

En modo estricto, el export se bloquea ante un fallo de puerta obligatoria. Las
puertas G (import) y H (flujo de carga) requieren el simulador y, si no está
disponible, se reportan como «pendiente», no como superadas.
"""

from .gates import (  # noqa: F401
    GateResult,
    run_gates,
)