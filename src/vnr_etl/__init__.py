"""vnr_etl — módulo adicional del conversor IGEA-DGS.

ETL universal y auditable para llevar fuentes OSINERGMIN / VNRGIS / GIS de
empresa / bases de datos a un **modelo canónico** eléctrico y, de ahí, a
CYMDIST o DIgSILENT PowerFactory.

Es un módulo **independiente** que convive con ``igea_dgs`` sin tocarlo: se
implementa solo lo que ``igea_dgs`` no tiene (descubrimiento, adaptadores de
fuente, modelo canónico, CRS/snapping, topología, enriquecimiento y puertas de
validación) y, donde corresponde, se **reutiliza** el escritor DGS existente en
lugar de reescribirlo (ver AUDIT/integration_plan.md).

La especificación de referencia es ``VNR-GIS.md`` (raíz del repositorio).
"""

from __future__ import annotations

__version__ = '1.6.0'