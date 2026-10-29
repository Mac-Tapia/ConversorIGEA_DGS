# Estado de las specs

Generado por `tools/estado_specs.py --escribir` (spec 033, RF-14); no se edita a mano:
la suite falla si no coincide. Estados: borrador, aprobada (con trabajo de código
pendiente), implementada (solo faltan pruebas en DIgSILENT), cumplida, reservada y
retirada.

| Spec | Nombre | Estado | RF | RF con prueba | Tareas abiertas |
| --- | --- | --- | --- | --- | --- |
| [001](001-reorganizacion/spec.md) | Reorganización: una responsabilidad, un sitio | cumplida | 34 | 34 | — |
| [002](002-arquitectura-por-capas/spec.md) | Arquitectura por capas y módulos enchufables | aprobada | 37 | 8 | T2, T3, T4, T6, T7, T8, T9, T10, T11, T12 |
| [003](003-integracion-web-retiro-gui/spec.md) | Integración web y retiro de la GUI (rama `feat/integracion-web-retiro-gui`) | reservada | 0 | 0 | — |
| [004](004-cargas-en-powerfactory/spec.md) | Cargas en un proyecto existente de DIgSILENT | cumplida | 67 | 67 | — |
| [005](005-carpeta-de-proyectos-pf/spec.md) | Carpeta de proyectos importados en DIgSILENT | implementada | 21 | 21 | T12 (DIgSILENT) |
| [006](006-ajuste-a-la-maxima-de-cabecera/spec.md) | Ajuste de las demandas a la máxima de cabecera | cumplida | 44 | 44 | — |
| [007](007-cargas-nuevas-sobre-el-ajuste/spec.md) | Cargas nuevas sobre el alimentador ajustado, una variación por carga | implementada | 40 | 40 | T11 (DIgSILENT) |
| [008](008-pestana-cargas-en-tres-pasos/spec.md) | Pestaña «Cargas en DIgSILENT» en tres pasos | implementada | 24 | 24 | T7 (DIgSILENT) |
| [009](009-inventario-del-repositorio/spec.md) | Inventario del repositorio: cada fichero con su módulo y su spec | cumplida | 15 | 15 | — |
| [010](010-trazado-gps-de-las-lineas/spec.md) | Trazado GPS de las líneas | cumplida | 7 | 7 | — |
| [011](011-estudios-sobre-la-red-calibrada/spec.md) | Estudios y obras de mejora sobre la red calibrada | implementada | 130 | 130 | T19 (DIgSILENT) |
| [012](012-confiabilidad-y-capacidad-de-la-red/spec.md) | Confiabilidad y capacidad de la red calibrada | aprobada | 72 | 12 | T3, T4, T5, T6, T7, T8, T9, T10, T11, T12, T13 (DIgSILENT) |
| [013](013-mes-de-analisis-y-transferencia/spec.md) | Mes de análisis y transferencia entre dos alimentadores | aprobada | 32 | 22 | T5, T6, T7 (DIgSILENT), T8 |
| [014](014-calibracion-en-sin-proyecto/spec.md) | Calibración y cambios del operador en «Sin proyecto», cargas nuevas en «Con proyecto» | cumplida | 34 | 34 | — |
| [015](015-caso-base-verificado/spec.md) | «Caso base» verificado de una vez; «Sin proyecto» solo calibra cargas | cumplida | 69 | 69 | — |
| [016](016-troncal-y-enlace-entre-alimentadores/spec.md) | Troncal por el camino más largo, enlace entre alimentadores y conexión en un tramo | implementada | 89 | 89 | T18 (DIgSILENT) |
| [017](017-informes-de-estudio-y-factibilidad/spec.md) | Informes de estudio eléctrico y de factibilidad de suministro | aprobada | 154 | 97 | T5, T7, T8, T9, T10, T11, T12, T13 (DIgSILENT), T14 (DIgSILENT), T15, T17 |
| [018](018-vinculo-compartido-entre-espacios/spec.md) | Spec 018 - Vínculo de proyectos de DIgSILENT compartido entre espacios de trabajo | cumplida | 15 | 15 | — |
| [019](019-arnes-de-powerfactory/spec.md) | Arnés de DIgSILENT: acceso exclusivo, conexión única y obras enchufables | cumplida | 25 | 25 | — |
| [020](020-sed-sobrecargadas/spec.md) | SED fijas sobrecargadas: aviso y transformadores nuevos desde la web | cumplida | 35 | 35 | — |
| [021](021-maniobras-y-sed-en-el-diagrama/spec.md) | Maniobras en el extremo de la línea, SED unidas a su barra, curvas de todos los alimentadores y central térmica en la calibración | cumplida | 70 | 70 | — |
| [022](022-red-unida-por-zonal-y-set/spec.md) | Red unida por zonal y SET | cumplida | 95 | 95 | — |
| [023](023-vnrgis-copia-sql-server/spec.md) | VNR-GIS desde la copia de SQL Server de cualquier concesionaria | cumplida | 10 | 10 | — |
| [024](024-pinn-gemelo-digital/spec.md) | PINN como oráculo y gemelo digital de la red calibrada | cumplida | 80 | 80 | — |
| [025](025-calibracion-por-anio/spec.md) | Calibración por año de medición | aprobada | 84 | 84 | T15, T21 (DIgSILENT), T22 |
| [026](026-asistente-ordenes/spec.md) | Asistente de órdenes en lenguaje natural que conoce, vigila y mejora el conversor | implementada | 32 | 32 | T12 (DIgSILENT) |
| [027](027-cierre-agente-en-produccion/spec.md) | Cierre del agente en producción: datos, entrenamiento robusto, verificación y operación | aprobada | 69 | 61 | T11, T22, T14 (DIgSILENT), T26, T29 (DIgSILENT), T30 (DIgSILENT), T31 (DIgSILENT) |
| [028](028-escaneo-del-alimentador/spec.md) | Escaneo del alimentador antes de recalibrar | implementada | 26 | 26 | T6 (DIgSILENT), T11 (DIgSILENT) |
| [029](029-crecimiento-por-alimentador/spec.md) | Crecimiento de la demanda por alimentador desde la medición de cabecera | cumplida | 7 | 7 | — |
| [030](030-pide-por-anios-en-digsilent/spec.md) | Los años del PIDE en casos y escenarios de DIgSILENT | cumplida | 15 | 15 | — |
| [031](031-proyeccion-econometrica-de-la-demanda/spec.md) | Proyección econométrica de la demanda con variables exógenas | reservada | 0 | 0 | — |
| [032](032-caso-base-original-fichas-en-sin-proyecto/spec.md) | «Caso base» con los datos originales; fichas y potencias en «Sin proyecto» | cumplida | 29 | 29 | — |
| [033](033-trazabilidad-y-estado-de-las-specs/spec.md) | Trazabilidad y estado de las specs | cumplida | 22 | 22 | — |
| [034](034-motor-base-y-contrato-de-fuentes/spec.md) | Motor base de conversión y contrato universal de fuentes | cumplida | 33 | 33 | — |
