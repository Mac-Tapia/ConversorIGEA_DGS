# Estado de las specs

Generado por `tools/estado_specs.py --escribir` (spec 033, RF-14); no se edita a mano:
la suite falla si no coincide. Estados: borrador, aprobada (con trabajo de código
pendiente), implementada (solo faltan pruebas en DIgSILENT), cumplida, reservada y
retirada.

| Spec | Nombre | Estado | RF | RF con prueba | Tareas abiertas |
| --- | --- | --- | --- | --- | --- |
| [001](001-reorganizacion/spec.md) | Reorganización: una responsabilidad, un sitio | cumplida | 35 | 35 | — |
| [002](002-arquitectura-por-capas/spec.md) | Arquitectura por capas y módulos enchufables | aprobada | 37 | 36 | T7, T8, T9, T11, T12 |
| [003](003-integracion-web-retiro-gui/spec.md) | Integración web y retiro de la GUI (rama `feat/integracion-web-retiro-gui`) | retirada | 0 | 0 | — |
| [004](004-cargas-en-powerfactory/spec.md) | Cargas en un proyecto existente de DIgSILENT | cumplida | 80 | 80 | — |
| [005](005-carpeta-de-proyectos-pf/spec.md) | Carpeta de proyectos importados en DIgSILENT | cumplida | 23 | 23 | — |
| [006](006-ajuste-a-la-maxima-de-cabecera/spec.md) | Ajuste de las demandas a la máxima de cabecera | cumplida | 44 | 44 | — |
| [007](007-cargas-nuevas-sobre-el-ajuste/spec.md) | Cargas nuevas sobre el alimentador ajustado, una variación por carga | cumplida | 41 | 41 | — |
| [008](008-pestana-cargas-en-tres-pasos/spec.md) | Pestaña «Cargas en DIgSILENT» en tres pasos | cumplida | 28 | 28 | — |
| [009](009-inventario-del-repositorio/spec.md) | Inventario del repositorio: cada fichero con su módulo y su spec | cumplida | 15 | 15 | — |
| [010](010-trazado-gps-de-las-lineas/spec.md) | Trazado GPS de las líneas | cumplida | 7 | 7 | — |
| [011](011-estudios-sobre-la-red-calibrada/spec.md) | Estudios y obras de mejora sobre la red calibrada | cumplida | 130 | 130 | — |
| [012](012-confiabilidad-y-capacidad-de-la-red/spec.md) | Confiabilidad y capacidad de la red calibrada | cumplida | 72 | 72 | — |
| [013](013-mes-de-analisis-y-transferencia/spec.md) | Mes de análisis y transferencia entre dos alimentadores | cumplida | 32 | 32 | — |
| [014](014-calibracion-en-sin-proyecto/spec.md) | Calibración y cambios del operador en «Sin proyecto», cargas nuevas en «Con proyecto» | cumplida | 34 | 34 | — |
| [015](015-caso-base-verificado/spec.md) | «Caso base» verificado de una vez; «Sin proyecto» solo calibra cargas | cumplida | 69 | 69 | — |
| [016](016-troncal-y-enlace-entre-alimentadores/spec.md) | Troncal por el camino más largo, enlace entre alimentadores y conexión en un tramo | cumplida | 89 | 89 | — |
| [017](017-informes-de-estudio-y-factibilidad/spec.md) | Informes de estudio eléctrico y de factibilidad de suministro | cumplida | 145 | 145 | — |
| [018](018-vinculo-compartido-entre-espacios/spec.md) | Spec 018 - Vínculo de proyectos de DIgSILENT compartido entre espacios de trabajo | cumplida | 17 | 17 | — |
| [019](019-arnes-de-powerfactory/spec.md) | Arnés de DIgSILENT: acceso exclusivo, conexión única y obras enchufables | cumplida | 28 | 28 | — |
| [020](020-sed-sobrecargadas/spec.md) | SED fijas sobrecargadas: aviso y transformadores nuevos desde la web | cumplida | 36 | 36 | — |
| [021](021-maniobras-y-sed-en-el-diagrama/spec.md) | Maniobras en el extremo de la línea, SED unidas a su barra, curvas de todos los alimentadores y central térmica en la calibración | cumplida | 70 | 70 | — |
| [022](022-red-unida-por-zonal-y-set/spec.md) | Red unida por zonal y SET | cumplida | 95 | 95 | — |
| [023](023-vnrgis-copia-sql-server/spec.md) | VNR-GIS desde la copia de SQL Server de cualquier concesionaria | cumplida | 10 | 10 | — |
| [024](024-pinn-gemelo-digital/spec.md) | PINN como oráculo y gemelo digital de la red calibrada | cumplida | 80 | 80 | — |
| [025](025-calibracion-por-anio/spec.md) | Calibración por año de medición | cumplida | 85 | 85 | — |
| [026](026-asistente-ordenes/spec.md) | Asistente de órdenes en lenguaje natural que conoce, vigila y mejora el conversor | cumplida | 41 | 41 | — |
| [027](027-cierre-agente-en-produccion/spec.md) | Cierre del agente en producción: datos, entrenamiento robusto, verificación y operación | aprobada | 69 | 61 | T11, T26 |
| [028](028-escaneo-del-alimentador/spec.md) | Escaneo del alimentador antes de recalibrar | cumplida | 42 | 42 | — |
| [029](029-crecimiento-por-alimentador/spec.md) | Crecimiento de la demanda por alimentador desde la medición de cabecera | cumplida | 7 | 7 | — |
| [030](030-pide-por-anios-en-digsilent/spec.md) | Los años del PIDE en casos y escenarios de DIgSILENT | cumplida | 15 | 15 | — |
| [031](031-proyeccion-econometrica-de-la-demanda/spec.md) | Proyección de la demanda para todos los años del PIDE, con el mejor modelo por métricas | aprobada | 18 | 17 | T4, T5 |
| [032](032-caso-base-original-fichas-en-sin-proyecto/spec.md) | «Caso base» con los datos originales; fichas y potencias en «Sin proyecto» | cumplida | 29 | 29 | — |
| [033](033-trazabilidad-y-estado-de-las-specs/spec.md) | Trazabilidad y estado de las specs | cumplida | 22 | 22 | — |
| [034](034-motor-base-y-contrato-de-fuentes/spec.md) | Motor base de conversión y contrato universal de fuentes | cumplida | 33 | 33 | — |
| [035](035-fijas-de-la-tabla-q-con-bancos-y-unidades/spec.md) | Fijas de la tabla en el instante de la máxima, Q de cabecera con bancos y unidades de DIgSILENT | cumplida | 31 | 31 | — |
| [036](036-auditoria-raiz-y-arranque-fiable/spec.md) | Auditoría de raíz y correcciones del arranque | cumplida | 3 | 3 | — |
| [037](037-cargas-nuevas-en-estudios-web/spec.md) | Caso «Cargas nuevas» en los estudios de la web | cumplida | 8 | 8 | — |
| [038](038-pertenencia-de-sed-y-notas-en-web/spec.md) | Pertenencia de las SED en la fuente y notas de actualización | cumplida | 8 | 8 | — |
| [039](039-fijas-maximo-del-mes-o-coincidentes/spec.md) | Fijas del máximo del mes o coincidentes con la cabecera, elegidas y comparadas en la web | cumplida | 22 | 22 | — |
| [040](040-cargas-del-bloque-sin-duplicados-y-ampliaciones/spec.md) | Cargas del bloque sin duplicados, y ampliaciones de clientes existentes | cumplida | 12 | 12 | — |
| [041](041-reparto-probabilistico-de-las-escaladas/spec.md) | Reparto probabilístico de las SED escaladas | cumplida | 9 | 9 | — |
| [042](042-con-proyecto-escalera-por-cargas-y-set-nueva/spec.md) | «Con proyecto»: escalera de obras carga a carga y SET nueva para las que no caben | cumplida | 106 | 106 | — |
| [043](043-consolidacion-y-gobierno-de-modelos/spec.md) | Consolidación y gobierno de modelos | aprobada | 15 | 15 | T9 |
| [044](044-evaluacion-causal-y-verificacion-completa/spec.md) | Evaluación causal y verificación completa | cumplida | 9 | 9 | — |
| [045](045-gemelo-fisico-y-contratos-pinn-gnn/spec.md) | Gemelo físico y contratos PINN/GNN | aprobada | 14 | 14 | T3 |
| [046](046-pronostico-causal-multihorizonte/spec.md) | Pronóstico causal multihorizonte | cumplida | 26 | 26 | — |
| [047](047-asistente-estructurado-y-revision-por-roles/spec.md) | Asistente estructurado y revisión por roles | aprobada | 42 | 42 | T4, T8, T7 |
| [048](048-optimizacion-mixta-evolutiva-y-pnl/spec.md) | Optimización mixta evolutiva y PNL | cumplida | 9 | 9 | — |
| [049](049-protecciones-nativas-y-coordinacion/spec.md) | Protecciones nativas y coordinación | cumplida | 10 | 10 | — |
| [050](050-aprendizaje-continuo-integrado/spec.md) | Aprendizaje continuo integrado | aprobada | 31 | 31 | T3b, T4b, T5b |
| [051](051-medicion-de-cabecera-en-libro-ancho/spec.md) | Medición de cabecera en libro ancho: una columna por alimentador | cumplida | 11 | 11 | — |
| [052](052-optimizacion-con-proyecto-con-el-oraculo/spec.md) | Optimización de «Con proyecto» con el oráculo y confirmación en DIgSILENT | cumplida | 19 | 19 | — |
| [053](053-catalogo-de-fichas-que-crece/spec.md) | El catálogo de fichas crece con cada código nuevo | cumplida | 9 | 9 | — |
| [054](054-fases-reales-en-el-dgs/spec.md) | Fases reales en el DGS: tramos y SED monofásicos y bifásicos | cumplida | 12 | 12 | — |
| [055](055-estructura-de-la-fuente-sistemas-y-set/spec.md) | Estructura de sistemas y SET desde la propia fuente, para cualquier empresa | cumplida | 7 | 7 | — |
| [056](056-nombres-y-mensajes-segun-la-fuente/spec.md) | Nombres y mensajes según la fuente: cada fuente con sus propias palabras | cumplida | 7 | 7 | — |
| [057](057-oraculo-corrige-antes-de-digsilent/spec.md) | El «Caso base» llega convergido: el oráculo corrige antes de importar | cumplida | 6 | 6 | — |
| [058](058-converter-smart-grid/spec.md) | ConverterSmartGrid: el proyecto sin el nombre de otra empresa | aprobada | 10 | 9 | T6 |
| [059](059-fuente-por-lo-que-se-carga/spec.md) | La fuente es la del fichero que se carga, sin valor por defecto | cumplida | 8 | 8 | — |
| [060](060-correcciones-del-aprendizaje/spec.md) | Correcciones verificables del aprendizaje | cumplida | 8 | 8 | — |
| [061](061-observacion-y-operacion-del-agente/spec.md) | Observación y operación integrada del agente | cumplida | 10 | 10 | — |
| [062](062-retencion-diaria-de-ejecuciones/spec.md) | Retención diaria de ejecuciones y temporales | cumplida | 8 | 8 | — |
| [063](063-informe-de-factibilidad-en-un-paso/spec.md) | Evaluación de conexión y operación comercial en un paso, para cualquier alimentador | cumplida | 57 | 57 | — |
| [064](064-arnes-sin-atajos/spec.md) | Arnés de DIgSILENT sin atajos: un turno para todos y estado restituido | cumplida | 10 | 10 | — |
| [065](065-cierre-de-auditoria-integral/spec.md) | Cierre verificable de la auditoría integral | cumplida | 26 | 26 | — |
| [066](066-libro-de-cada-informe/spec.md) | Cada informe con su libro Excel, según el perfil de la empresa | cumplida | 13 | 13 | — |
| [067](067-asistente-operativo/spec.md) | Asistente operativo: revisión, planes, modelos y tareas que funcionan desde la web | cumplida | 40 | 40 | — |
| [068](068-dataset-real-del-maestro/spec.md) | Dataset real del maestro: órdenes del operador, etiquetas de plata y currículo con su estilo | cumplida | 42 | 42 | — |
| [069](069-interprete-con-codificador-preentrenado/spec.md) | Intérprete de órdenes con codificador preentrenado y clase «ninguna» | aprobada | 37 | 37 | T7 |
| [070](070-asistente-de-punta-a-punta/spec.md) | El asistente opera el conversor de punta a punta | implementada | 77 | 77 | T11 (DIgSILENT) |
| [071](071-puertas-de-los-modelos/spec.md) | Puertas de los modelos antes de entrenar: PINN en su red, un puntero, sin autoentrenamiento y una guardia de GPU | aprobada | 8 | 8 | T5 |
| [072](072-pide-y-planeamiento-de-largo-plazo/spec.md) | PIDE y planeamiento de largo plazo: dos entregables desde un mismo estudio | aprobada | 38 | 38 | T9b, T11, T13, T14 |
| [073](073-bancos-limitados-por-valle/spec.md) | El número de bancos lo define la tensión en las ventanas de valle | cumplida | 41 | 41 | — |
| [074](074-piloto-madrl-en-obras/spec.md) | Piloto MADRL en obras: medir antes de aprender | aprobada | 12 | 11 | T5, T7, T8 |
| [075](075-validacion-cruzada-de-las-ordenes/spec.md) | Validación cruzada con las órdenes confirmadas, y Ollama no adivina cuando el modelo ve charla | cumplida | 46 | 46 | — |
| [076](076-preguntas-de-metodologia-por-entregable/spec.md) | Preguntas de metodología y criterios por entregable, del flujo, de la arquitectura y de la web | cumplida | 34 | 34 | — |
| [077](077-asistente-lee-el-proyecto/spec.md) | El asistente lee skills, documentos, código y API del proyecto, y un MCP local de solo lectura | cumplida | 74 | 74 | — |
| [078](078-senales-de-convergencia/spec.md) | Las señales de convergencia dicen lo que devolvió DIgSILENT, y el asistente importa un grupo ya convertido | cumplida | 35 | 35 | — |
| [079](079-afinado-del-interprete-de-ordenes/spec.md) | Afinado real del intérprete de órdenes: las últimas capas del codificador junto con sus cabezas | cumplida | 64 | 64 | — |
| [080](080-acceso-directo-a-paquetes-vnrgis/spec.md) | Acceso directo a los paquetes VNR-GIS de cada distribuidora | cumplida | 52 | 52 | — |
| [081](081-regresiones-permanentes/spec.md) | Los fallos reales no se repiten: comprobaciones permanentes, solución con los oráculos y mejora continua | cumplida | 85 | 85 | — |
| [082](082-oraculo-completo-y-por-fases/spec.md) | El oráculo calcula todo lo del modelo, y por fases | cumplida | 15 | 15 | — |
| [083](083-oraculo-antes-de-calibrar/spec.md) | El oráculo antes de calibrar y recalibrar | cumplida | 31 | 31 | — |
| [084](084-seis-reglas-con-requisito/spec.md) | Seis reglas del operador pasan de notas a requisitos con prueba | cumplida | 30 | 30 | — |
| [085](085-ordenes-del-maestro-con-grupos-apartados/spec.md) | Órdenes del maestro con grupos apartados, y la puerta de órdenes sin humanas suficientes | cumplida | 33 | 33 | — |
| [086](086-puesta-en-operacion-comercial/spec.md) | Puesta en operación comercial: versión 1.0 instalable, segura y probada de punta a punta | aprobada | 75 | 72 | T9 (DIgSILENT), T36 (DIgSILENT), T40 (DIgSILENT), T41, T32 (DIgSILENT), T33 (DIgSILENT), T34 |
| [087](087-seleccion-de-obras-con-metodos-y-medicion/spec.md) | Selección de obras con el oráculo, métodos probabilísticos y medición de la mejora | cumplida | 57 | 57 | — |
| [088](088-q-de-cabecera-desde-el-factor-de-potencia/spec.md) | Q negativa desde el factor de potencia | cumplida | 12 | 12 | — |
| [089](089-pronostico-de-demanda-en-un-modulo/spec.md) | Pronóstico de demanda en un módulo: datos vivos, limpieza, tres clases y backtest por método | aprobada | 93 | 93 | T7 |
| [090](090-arquitectura-generada/spec.md) | La arquitectura se cataloga sola: todos los módulos, el asistente y su equipo | cumplida | 16 | 16 | — |
| [091](091-flujo-calibracion-a-estudio/spec.md) | De la calibración al estudio, en su orden y sin avisos que engañen | cumplida | 33 | 33 | — |
| [092](092-caso-base-de-una-red-reconstruida/spec.md) | El «Caso base» de una red reconstruida se verifica con lo que hay en disco | cumplida | 4 | 4 | — |
| [093](093-siglas-de-carga-como-nombre/spec.md) | La sigla de la carga nombra la carga nueva y su variación | cumplida | 4 | 4 | — |
| [094](094-perfil-de-tension-y-bancos/spec.md) | Perfil de tensión en la calibración y bancos ubicados según el perfil | cumplida | 18 | 18 | — |
| [095](095-escaladas-proporcionales-a-su-kva/spec.md) | Escaladas proporcionales a su potencia instalada | cumplida | 3 | 3 | — |
| [096](096-retomar-tras-suspender-el-equipo/spec.md) | Tras suspender el equipo, la web vuelve sola al último trabajo pendiente | cumplida | 8 | 8 | — |
| [097](097-vectores-multilingues-del-rag/spec.md) | Vectores multilingües para la búsqueda del asistente | aprobada | 8 | 5 | T3 |
| [098](098-transferencia-del-operador-en-calibracion-y-obras/spec.md) | La transferencia de carga del operador, en la calibración y en las obras | cumplida | 50 | 50 | — |
| [099](099-cargas-del-libro-duplicadas-por-el-nombre-del-cliente/spec.md) | Cargas del libro duplicadas por el nombre del cliente | cumplida | 8 | 8 | — |
| [100](100-aceptacion-automatica-por-version/spec.md) | Aceptación automática por versión, sin tareas pendientes por proyecto | aprobada | 7 | 0 | T1, T2, T3, T4 (DIgSILENT) |
| [101](101-calibracion-cambia-los-transformadores-sola/spec.md) | La calibración cambia sola los transformadores que impiden converger | cumplida | 14 | 14 | — |
| [102](102-puerta-de-calidad-ci-cd/spec.md) | Puerta de calidad: ningún commit ni subida con la suite en rojo | cumplida | 23 | 23 | — |
| [103](103-digsilent-de-cualquier-version/spec.md) | DIgSILENT de cualquier versión instalada | cumplida | 7 | 7 | — |
| [104](104-libros-nuevos-se-reconocen-solos/spec.md) | Los libros nuevos de demanda se reconocen solos | aprobada | 41 | 41 | T6 |
| [105](105-evolucion-de-clientes-fijos-por-alimentador/spec.md) | Evolución de los clientes fijos de cualquier alimentador | cumplida | 40 | 40 | — |
