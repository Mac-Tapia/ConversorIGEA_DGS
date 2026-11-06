# Estado de las specs

Generado por `tools/estado_specs.py --escribir` (spec 033, RF-14); no se edita a mano:
la suite falla si no coincide. Estados: borrador, aprobada (con trabajo de código
pendiente), implementada (solo faltan pruebas en DIgSILENT), cumplida, reservada y
retirada.

| Spec | Nombre | Estado | RF | RF con prueba | Tareas abiertas |
| --- | --- | --- | --- | --- | --- |
| [001](001-reorganizacion/spec.md) | Reorganización: una responsabilidad, un sitio | cumplida | 35 | 35 | — |
| [002](002-arquitectura-por-capas/spec.md) | Arquitectura por capas y módulos enchufables | aprobada | 37 | 31 | T7, T8, T9, T11, T12 |
| [003](003-integracion-web-retiro-gui/spec.md) | Integración web y retiro de la GUI (rama `feat/integracion-web-retiro-gui`) | reservada | 0 | 0 | — |
| [004](004-cargas-en-powerfactory/spec.md) | Cargas en un proyecto existente de DIgSILENT | cumplida | 67 | 67 | — |
| [005](005-carpeta-de-proyectos-pf/spec.md) | Carpeta de proyectos importados en DIgSILENT | cumplida | 22 | 22 | — |
| [006](006-ajuste-a-la-maxima-de-cabecera/spec.md) | Ajuste de las demandas a la máxima de cabecera | cumplida | 44 | 44 | — |
| [007](007-cargas-nuevas-sobre-el-ajuste/spec.md) | Cargas nuevas sobre el alimentador ajustado, una variación por carga | cumplida | 41 | 41 | — |
| [008](008-pestana-cargas-en-tres-pasos/spec.md) | Pestaña «Cargas en DIgSILENT» en tres pasos | implementada | 28 | 28 | T7 (DIgSILENT) |
| [009](009-inventario-del-repositorio/spec.md) | Inventario del repositorio: cada fichero con su módulo y su spec | cumplida | 15 | 15 | — |
| [010](010-trazado-gps-de-las-lineas/spec.md) | Trazado GPS de las líneas | cumplida | 7 | 7 | — |
| [011](011-estudios-sobre-la-red-calibrada/spec.md) | Estudios y obras de mejora sobre la red calibrada | implementada | 130 | 130 | T19 (DIgSILENT) |
| [012](012-confiabilidad-y-capacidad-de-la-red/spec.md) | Confiabilidad y capacidad de la red calibrada | implementada | 72 | 72 | T13 (DIgSILENT) |
| [013](013-mes-de-analisis-y-transferencia/spec.md) | Mes de análisis y transferencia entre dos alimentadores | implementada | 32 | 32 | T7 (DIgSILENT) |
| [014](014-calibracion-en-sin-proyecto/spec.md) | Calibración y cambios del operador en «Sin proyecto», cargas nuevas en «Con proyecto» | cumplida | 34 | 34 | — |
| [015](015-caso-base-verificado/spec.md) | «Caso base» verificado de una vez; «Sin proyecto» solo calibra cargas | cumplida | 69 | 69 | — |
| [016](016-troncal-y-enlace-entre-alimentadores/spec.md) | Troncal por el camino más largo, enlace entre alimentadores y conexión en un tramo | implementada | 89 | 89 | T18 (DIgSILENT) |
| [017](017-informes-de-estudio-y-factibilidad/spec.md) | Informes de estudio eléctrico y de factibilidad de suministro | implementada | 145 | 145 | T13 (DIgSILENT), T14 (DIgSILENT), T19 (DIgSILENT) |
| [018](018-vinculo-compartido-entre-espacios/spec.md) | Spec 018 - Vínculo de proyectos de DIgSILENT compartido entre espacios de trabajo | cumplida | 15 | 15 | — |
| [019](019-arnes-de-powerfactory/spec.md) | Arnés de DIgSILENT: acceso exclusivo, conexión única y obras enchufables | cumplida | 28 | 28 | — |
| [020](020-sed-sobrecargadas/spec.md) | SED fijas sobrecargadas: aviso y transformadores nuevos desde la web | cumplida | 35 | 35 | — |
| [021](021-maniobras-y-sed-en-el-diagrama/spec.md) | Maniobras en el extremo de la línea, SED unidas a su barra, curvas de todos los alimentadores y central térmica en la calibración | cumplida | 70 | 70 | — |
| [022](022-red-unida-por-zonal-y-set/spec.md) | Red unida por zonal y SET | cumplida | 95 | 95 | — |
| [023](023-vnrgis-copia-sql-server/spec.md) | VNR-GIS desde la copia de SQL Server de cualquier concesionaria | cumplida | 10 | 10 | — |
| [024](024-pinn-gemelo-digital/spec.md) | PINN como oráculo y gemelo digital de la red calibrada | cumplida | 80 | 80 | — |
| [025](025-calibracion-por-anio/spec.md) | Calibración por año de medición | aprobada | 85 | 85 | T21 (DIgSILENT), T22 |
| [026](026-asistente-ordenes/spec.md) | Asistente de órdenes en lenguaje natural que conoce, vigila y mejora el conversor | implementada | 32 | 32 | T12 (DIgSILENT) |
| [027](027-cierre-agente-en-produccion/spec.md) | Cierre del agente en producción: datos, entrenamiento robusto, verificación y operación | aprobada | 69 | 61 | T11, T22 (DIgSILENT), T14 (DIgSILENT), T26, T29 (DIgSILENT), T30 (DIgSILENT), T31 (DIgSILENT) |
| [028](028-escaneo-del-alimentador/spec.md) | Escaneo del alimentador antes de recalibrar | implementada | 42 | 42 | T6 (DIgSILENT), T11 (DIgSILENT), T15 (DIgSILENT) |
| [029](029-crecimiento-por-alimentador/spec.md) | Crecimiento de la demanda por alimentador desde la medición de cabecera | cumplida | 7 | 7 | — |
| [030](030-pide-por-anios-en-digsilent/spec.md) | Los años del PIDE en casos y escenarios de DIgSILENT | cumplida | 15 | 15 | — |
| [031](031-proyeccion-econometrica-de-la-demanda/spec.md) | Proyección econométrica de la demanda con variables exógenas | reservada | 0 | 0 | — |
| [032](032-caso-base-original-fichas-en-sin-proyecto/spec.md) | «Caso base» con los datos originales; fichas y potencias en «Sin proyecto» | cumplida | 29 | 29 | — |
| [033](033-trazabilidad-y-estado-de-las-specs/spec.md) | Trazabilidad y estado de las specs | cumplida | 22 | 22 | — |
| [034](034-motor-base-y-contrato-de-fuentes/spec.md) | Motor base de conversión y contrato universal de fuentes | cumplida | 33 | 33 | — |
| [035](035-fijas-de-la-tabla-q-con-bancos-y-unidades/spec.md) | Fijas de la tabla en el instante de la máxima, Q de cabecera con bancos y unidades de DIgSILENT | cumplida | 31 | 31 | — |
| [036](036-auditoria-raiz-y-arranque-fiable/spec.md) | Auditoría de raíz y correcciones del arranque | cumplida | 3 | 3 | — |
| [037](037-cargas-nuevas-en-estudios-web/spec.md) | Caso «Cargas nuevas» en los estudios de la web | implementada | 8 | 8 | T4 (DIgSILENT) |
| [038](038-pertenencia-de-sed-y-notas-en-web/spec.md) | Pertenencia de las SED en la fuente y notas de actualización | cumplida | 8 | 8 | — |
| [039](039-fijas-maximo-del-mes-o-coincidentes/spec.md) | Fijas del máximo del mes o coincidentes con la cabecera, elegidas y comparadas en la web | implementada | 8 | 8 | T4 (DIgSILENT) |
| [040](040-cargas-del-bloque-sin-duplicados-y-ampliaciones/spec.md) | Cargas del bloque sin duplicados, y ampliaciones de clientes existentes | cumplida | 12 | 12 | — |
| [041](041-reparto-probabilistico-de-las-escaladas/spec.md) | Reparto probabilístico de las SED escaladas | cumplida | 9 | 9 | — |
| [042](042-con-proyecto-escalera-por-cargas-y-set-nueva/spec.md) | «Con proyecto»: escalera de obras carga a carga y SET nueva para las que no caben | implementada | 93 | 93 | T29 (DIgSILENT), T42 (DIgSILENT), T50 (DIgSILENT), T48 (DIgSILENT), T44 (DIgSILENT), T37 (DIgSILENT), T6 (DIgSILENT) |
| [043](043-consolidacion-y-gobierno-de-modelos/spec.md) | Consolidación y gobierno de modelos | aprobada | 15 | 15 | T9 |
| [044](044-evaluacion-causal-y-verificacion-completa/spec.md) | Evaluación causal y verificación completa | implementada | 9 | 9 | T4 (DIgSILENT) |
| [045](045-gemelo-fisico-y-contratos-pinn-gnn/spec.md) | Gemelo físico y contratos PINN/GNN | aprobada | 11 | 10 | T3, T4 (DIgSILENT) |
| [046](046-pronostico-causal-multihorizonte/spec.md) | Pronóstico causal multihorizonte | cumplida | 25 | 25 | — |
| [047](047-asistente-estructurado-y-revision-por-roles/spec.md) | Asistente estructurado y revisión por roles | aprobada | 41 | 41 | T4, T8, T7 |
| [048](048-optimizacion-mixta-evolutiva-y-pnl/spec.md) | Optimización mixta evolutiva y PNL | implementada | 9 | 9 | T4 (DIgSILENT) |
| [049](049-protecciones-nativas-y-coordinacion/spec.md) | Protecciones nativas y coordinación | aprobada | 10 | 0 | T1, T2, T3, T4 (DIgSILENT) |
| [050](050-aprendizaje-continuo-integrado/spec.md) | Aprendizaje continuo integrado | aprobada | 10 | 10 | T1b, T2b, T3b, T4b, T5b |
| [051](051-medicion-de-cabecera-en-libro-ancho/spec.md) | Medición de cabecera en libro ancho: una columna por alimentador | implementada | 11 | 11 | T3 (DIgSILENT) |
| [052](052-optimizacion-con-proyecto-con-el-oraculo/spec.md) | Optimización de «Con proyecto» con el oráculo y confirmación en DIgSILENT | implementada | 19 | 19 | T4 (DIgSILENT) |
| [053](053-catalogo-de-fichas-que-crece/spec.md) | El catálogo de fichas crece con cada código nuevo | cumplida | 9 | 9 | — |
| [054](054-fases-reales-en-el-dgs/spec.md) | Fases reales en el DGS: tramos y SED monofásicos y bifásicos | cumplida | 12 | 12 | — |
| [055](055-estructura-de-la-fuente-sistemas-y-set/spec.md) | Estructura de sistemas y SET desde la propia fuente, para cualquier empresa | implementada | 7 | 7 | T2 (DIgSILENT) |
| [056](056-nombres-y-mensajes-segun-la-fuente/spec.md) | Nombres y mensajes según la fuente: cada fuente con sus propias palabras | implementada | 7 | 7 | T3 (DIgSILENT) |
| [057](057-oraculo-corrige-antes-de-digsilent/spec.md) | El «Caso base» llega convergido: el oráculo corrige antes de importar | cumplida | 6 | 6 | — |
| [058](058-converter-smart-grid/spec.md) | ConverterSmartGrid: el proyecto sin el nombre de otra empresa | aprobada | 10 | 9 | T5, T6, T7 (DIgSILENT) |
| [059](059-fuente-por-lo-que-se-carga/spec.md) | La fuente es la del fichero que se carga, sin valor por defecto | cumplida | 8 | 8 | — |
| [060](060-correcciones-del-aprendizaje/spec.md) | Correcciones verificables del aprendizaje | cumplida | 8 | 8 | — |
| [061](061-observacion-y-operacion-del-agente/spec.md) | Observación y operación integrada del agente | cumplida | 10 | 10 | — |
| [062](062-retencion-diaria-de-ejecuciones/spec.md) | Retención diaria de ejecuciones y temporales | cumplida | 8 | 8 | — |
| [063](063-informe-de-factibilidad-en-un-paso/spec.md) | Evaluación de conexión y operación comercial en un paso, para cualquier alimentador | cumplida | 57 | 57 | — |
| [064](064-arnes-sin-atajos/spec.md) | Arnés de DIgSILENT sin atajos: un turno para todos y estado restituido | cumplida | 10 | 10 | — |
| [065](065-cierre-de-auditoria-integral/spec.md) | Cierre verificable de la auditoría integral | aprobada | 26 | 26 | T12 (DIgSILENT), T13 |
| [066](066-libro-de-cada-informe/spec.md) | Cada informe con su libro Excel, según el perfil de la empresa | cumplida | 13 | 13 | — |
| [067](067-asistente-operativo/spec.md) | Asistente operativo: revisión, planes, modelos y tareas que funcionan desde la web | implementada | 40 | 40 | T9 (DIgSILENT) |
| [068](068-dataset-real-del-maestro/spec.md) | Dataset real del maestro: órdenes del operador, etiquetas de plata y currículo con su estilo | aprobada | 42 | 42 | T7 |
| [069](069-interprete-con-codificador-preentrenado/spec.md) | Intérprete de órdenes con codificador preentrenado y clase «ninguna» | aprobada | 32 | 32 | T7 |
| [070](070-asistente-de-punta-a-punta/spec.md) | El asistente opera el conversor de punta a punta | implementada | 77 | 77 | T9 (DIgSILENT), T10 (DIgSILENT), T11 (DIgSILENT) |
| [071](071-puertas-de-los-modelos/spec.md) | Puertas de los modelos antes de entrenar: PINN en su red, un puntero, sin autoentrenamiento y una guardia de GPU | aprobada | 8 | 8 | T5 |
| [072](072-pide-y-planeamiento-de-largo-plazo/spec.md) | PIDE y planeamiento de largo plazo: dos entregables desde un mismo estudio | aprobada | 22 | 22 | T9b, T11, T13 |
| [073](073-bancos-limitados-por-valle/spec.md) | El número de bancos lo define la tensión en las ventanas de valle | implementada | 41 | 41 | T8 (DIgSILENT), T12 (DIgSILENT) |
| [074](074-piloto-madrl-en-obras/spec.md) | Piloto MADRL en obras: medir antes de aprender | aprobada | 12 | 11 | T5, T7, T8 |
| [075](075-validacion-cruzada-de-las-ordenes/spec.md) | Validación cruzada con las órdenes confirmadas, y Ollama no adivina cuando el modelo ve charla | implementada | 46 | 46 | T6 (DIgSILENT) |
| [076](076-preguntas-de-metodologia-por-entregable/spec.md) | Preguntas de metodología y criterios por entregable, del flujo, de la arquitectura y de la web | cumplida | 34 | 34 | — |
| [077](077-asistente-lee-el-proyecto/spec.md) | El asistente lee skills, documentos, código y API del proyecto, y un MCP local de solo lectura | cumplida | 74 | 74 | — |
| [078](078-senales-de-convergencia/spec.md) | Las señales de convergencia dicen lo que devolvió DIgSILENT, y el asistente importa un grupo ya convertido | implementada | 35 | 35 | T6 (DIgSILENT), T7 (DIgSILENT) |
| [079](079-afinado-del-interprete-de-ordenes/spec.md) | Afinado real del intérprete de órdenes: las últimas capas del codificador junto con sus cabezas | implementada | 64 | 64 | T7 (DIgSILENT) |
| [080](080-acceso-directo-a-paquetes-vnrgis/spec.md) | Acceso directo a los paquetes VNR-GIS de cada distribuidora | cumplida | 52 | 52 | — |
| [081](081-regresiones-permanentes/spec.md) | Los fallos reales no se repiten: comprobaciones permanentes, solución con los oráculos y mejora continua | implementada | 79 | 79 | T22 (DIgSILENT), T20 (DIgSILENT), T10 (DIgSILENT), T11 (DIgSILENT), T12 (DIgSILENT), T13 (DIgSILENT), T14 (DIgSILENT), T16 (DIgSILENT), T24 (DIgSILENT) |
| [082](082-oraculo-completo-y-por-fases/spec.md) | El oráculo calcula todo lo del modelo, y por fases | cumplida | 15 | 15 | — |
| [083](083-oraculo-antes-de-calibrar/spec.md) | El oráculo antes de calibrar y recalibrar | implementada | 31 | 31 | T3 (DIgSILENT) |
| [084](084-seis-reglas-con-requisito/spec.md) | Seis reglas del operador pasan de notas a requisitos con prueba | implementada | 30 | 30 | T8 (DIgSILENT), T9 (DIgSILENT) |
| [085](085-ordenes-del-maestro-con-grupos-apartados/spec.md) | Órdenes del maestro con grupos apartados, y la puerta de órdenes sin humanas suficientes | aprobada | 33 | 25 | T6 |
| [086](086-puesta-en-operacion-comercial/spec.md) | Puesta en operación comercial: versión 1.0 instalable, segura y probada de punta a punta | aprobada | 53 | 49 | T1, T5, T39, T38, T9 (DIgSILENT), T36 (DIgSILENT), T40 (DIgSILENT), T41, T24 (DIgSILENT), T25 (DIgSILENT), T26 (DIgSILENT), T27 (DIgSILENT), T28 (DIgSILENT), T29, T30 (DIgSILENT), T31, T32 (DIgSILENT), T33 (DIgSILENT), T34 |
| [087](087-seleccion-de-obras-con-metodos-y-medicion/spec.md) | Selección de obras con el oráculo, métodos probabilísticos y medición de la mejora | implementada | 57 | 57 | T27 (DIgSILENT), T12 (DIgSILENT), T13 (DIgSILENT), T14 (DIgSILENT) |
| [088](088-q-de-cabecera-desde-el-factor-de-potencia/spec.md) | Q negativa desde el factor de potencia | cumplida | 12 | 12 | — |
| [089](089-pronostico-de-demanda-en-un-modulo/spec.md) | Pronóstico de demanda en un módulo: datos vivos, limpieza, tres clases y backtest por método | aprobada | 88 | 88 | T5, T7 |
| [090](090-arquitectura-generada/spec.md) | La arquitectura se cataloga sola: todos los módulos, el asistente y su equipo | cumplida | 16 | 16 | — |
| [091](091-flujo-calibracion-a-estudio/spec.md) | Flujo de la calibración al estudio | reservada | 0 | 0 | — |
| [092](092-caso-base-de-una-red-reconstruida/spec.md) | El «Caso base» de una red reconstruida se verifica con lo que hay en disco | implementada | 4 | 4 | T2 (DIgSILENT) |
| [093](093-siglas-de-carga-como-nombre/spec.md) | La sigla de la carga nombra la carga nueva y su variación | implementada | 3 | 3 | T2 (DIgSILENT) |
| [094](094-perfil-de-tension-y-bancos/spec.md) | Perfil de tensión en la calibración y bancos ubicados según el perfil | aprobada | 18 | 9 | T4, T6, T7, T5 (DIgSILENT) |
| [095](095-escaladas-proporcionales-a-su-kva/spec.md) | Escaladas proporcionales a su potencia instalada | cumplida | 3 | 3 | — |
