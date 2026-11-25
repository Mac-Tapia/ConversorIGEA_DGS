# Estado de las specs

Generado por `tools/estado_specs.py --escribir` (spec 033, RF-14); no se edita a mano:
la suite falla si no coincide. Estados: borrador, aprobada (con trabajo de código
pendiente), implementada (solo faltan pruebas en DIgSILENT), cumplida, reservada y
retirada.

| Spec | Nombre | Estado | RF | RF con prueba | Tareas abiertas |
| --- | --- | --- | --- | --- | --- |
| [001](001-reorganizacion/spec.md) | Reorganización: una responsabilidad, un sitio | cumplida | 35 | 35 | — |
| [002](002-arquitectura-por-capas/spec.md) | Arquitectura por capas y módulos enchufables | cumplida | 39 | 39 | — |
| [003](003-integracion-web-retiro-gui/spec.md) | Integración web y retiro de la GUI (rama `feat/integracion-web-retiro-gui`) | retirada | 0 | 0 | — |
| [004](004-cargas-en-powerfactory/spec.md) | Cargas en un proyecto existente de DIgSILENT | cumplida | 118 | 118 | — |
| [005](005-carpeta-de-proyectos-pf/spec.md) | Carpeta de proyectos importados en DIgSILENT | cumplida | 24 | 24 | — |
| [006](006-ajuste-a-la-maxima-de-cabecera/spec.md) | Ajuste de las demandas a la máxima de cabecera | cumplida | 47 | 47 | — |
| [007](007-cargas-nuevas-sobre-el-ajuste/spec.md) | Cargas nuevas sobre el alimentador ajustado, una variación por carga | cumplida | 41 | 41 | — |
| [008](008-pestana-cargas-en-tres-pasos/spec.md) | Pestaña «Cargas en DIgSILENT» en tres pasos | cumplida | 31 | 31 | — |
| [009](009-inventario-del-repositorio/spec.md) | Inventario del repositorio: cada fichero con su módulo y su spec | cumplida | 16 | 16 | — |
| [010](010-trazado-gps-de-las-lineas/spec.md) | Trazado GPS de las líneas | cumplida | 8 | 8 | — |
| [011](011-estudios-sobre-la-red-calibrada/spec.md) | Estudios y obras de mejora sobre la red calibrada | cumplida | 138 | 138 | — |
| [012](012-confiabilidad-y-capacidad-de-la-red/spec.md) | Confiabilidad y capacidad de la red calibrada | cumplida | 98 | 98 | — |
| [013](013-mes-de-analisis-y-transferencia/spec.md) | Mes de análisis y transferencia entre dos alimentadores | cumplida | 32 | 32 | — |
| [014](014-calibracion-en-sin-proyecto/spec.md) | Calibración y cambios del operador en «Sin proyecto», cargas nuevas en «Con proyecto» | cumplida | 34 | 34 | — |
| [015](015-caso-base-verificado/spec.md) | «Caso base» verificado de una vez; «Sin proyecto» solo calibra cargas | cumplida | 75 | 75 | — |
| [016](016-troncal-y-enlace-entre-alimentadores/spec.md) | Troncal por el camino más largo, enlace entre alimentadores y conexión en un tramo | cumplida | 89 | 89 | — |
| [017](017-informes-de-estudio-y-factibilidad/spec.md) | Informes de estudio eléctrico y de factibilidad de suministro | cumplida | 148 | 148 | — |
| [018](018-vinculo-compartido-entre-espacios/spec.md) | Spec 018 - Vínculo de proyectos de DIgSILENT compartido entre espacios de trabajo | cumplida | 19 | 19 | — |
| [019](019-arnes-de-powerfactory/spec.md) | Arnés de DIgSILENT: acceso exclusivo, conexión única y obras enchufables | cumplida | 28 | 28 | — |
| [020](020-sed-sobrecargadas/spec.md) | SED fijas sobrecargadas: aviso y transformadores nuevos desde la web | cumplida | 37 | 37 | — |
| [021](021-maniobras-y-sed-en-el-diagrama/spec.md) | Maniobras en el extremo de la línea, SED unidas a su barra, curvas de todos los alimentadores y central térmica en la calibración | cumplida | 85 | 85 | — |
| [022](022-red-unida-por-zonal-y-set/spec.md) | Red unida por zonal y SET | cumplida | 95 | 95 | — |
| [023](023-vnrgis-copia-sql-server/spec.md) | VNR-GIS desde la copia de SQL Server de cualquier concesionaria | cumplida | 10 | 10 | — |
| [024](024-pinn-gemelo-digital/spec.md) | PINN como oráculo y gemelo digital de la red calibrada | cumplida | 80 | 80 | — |
| [025](025-calibracion-por-anio/spec.md) | Calibración por año de medición | cumplida | 93 | 93 | — |
| [026](026-asistente-ordenes/spec.md) | Asistente de órdenes en lenguaje natural que conoce, vigila y mejora el conversor | cumplida | 51 | 51 | — |
| [027](027-cierre-agente-en-produccion/spec.md) | Cierre del agente en producción: datos, entrenamiento robusto, verificación y operación | aprobada | 78 | 71 | T11 |
| [028](028-escaneo-del-alimentador/spec.md) | Escaneo del alimentador antes de recalibrar | cumplida | 44 | 44 | — |
| [029](029-crecimiento-por-alimentador/spec.md) | Crecimiento de la demanda por alimentador desde la medición de cabecera | cumplida | 7 | 7 | — |
| [030](030-pide-por-anios-en-digsilent/spec.md) | Los años del PIDE en casos y escenarios de DIgSILENT | cumplida | 15 | 15 | — |
| [031](031-proyeccion-econometrica-de-la-demanda/spec.md) | Proyección de la demanda para todos los años del PIDE, con el mejor modelo por métricas | cumplida | 30 | 30 | — |
| [032](032-caso-base-original-fichas-en-sin-proyecto/spec.md) | «Caso base» con los datos originales; fichas y potencias en «Sin proyecto» | cumplida | 29 | 29 | — |
| [033](033-trazabilidad-y-estado-de-las-specs/spec.md) | Trazabilidad y estado de las specs | cumplida | 22 | 22 | — |
| [034](034-motor-base-y-contrato-de-fuentes/spec.md) | Motor base de conversión y contrato universal de fuentes | cumplida | 42 | 42 | — |
| [035](035-fijas-de-la-tabla-q-con-bancos-y-unidades/spec.md) | Fijas de la tabla en el instante de la máxima, Q de cabecera con bancos y unidades de DIgSILENT | cumplida | 32 | 32 | — |
| [036](036-auditoria-raiz-y-arranque-fiable/spec.md) | Auditoría de raíz y correcciones del arranque | cumplida | 3 | 3 | — |
| [037](037-cargas-nuevas-en-estudios-web/spec.md) | Caso «Cargas nuevas» en los estudios de la web | cumplida | 8 | 8 | — |
| [038](038-pertenencia-de-sed-y-notas-en-web/spec.md) | Pertenencia de las SED en la fuente y notas de actualización | cumplida | 8 | 8 | — |
| [039](039-fijas-maximo-del-mes-o-coincidentes/spec.md) | Fijas del máximo del mes o coincidentes con la cabecera, elegidas y comparadas en la web | cumplida | 25 | 25 | — |
| [040](040-cargas-del-bloque-sin-duplicados-y-ampliaciones/spec.md) | Cargas del bloque sin duplicados, y ampliaciones de clientes existentes | cumplida | 12 | 12 | — |
| [041](041-reparto-probabilistico-de-las-escaladas/spec.md) | Reparto probabilístico de las SED escaladas | cumplida | 9 | 9 | — |
| [042](042-con-proyecto-escalera-por-cargas-y-set-nueva/spec.md) | «Con proyecto»: escalera de obras carga a carga y SET nueva para las que no caben | cumplida | 107 | 107 | — |
| [043](043-consolidacion-y-gobierno-de-modelos/spec.md) | Consolidación y gobierno de modelos | aprobada | 17 | 17 | T9 |
| [044](044-evaluacion-causal-y-verificacion-completa/spec.md) | Evaluación causal y verificación completa | cumplida | 12 | 12 | — |
| [045](045-gemelo-fisico-y-contratos-pinn-gnn/spec.md) | Gemelo físico y contratos PINN/GNN | cumplida | 18 | 18 | — |
| [046](046-pronostico-causal-multihorizonte/spec.md) | Pronóstico causal multihorizonte | cumplida | 26 | 26 | — |
| [047](047-asistente-estructurado-y-revision-por-roles/spec.md) | Asistente estructurado y revisión por roles | aprobada | 103 | 103 | T4, T7 |
| [048](048-optimizacion-mixta-evolutiva-y-pnl/spec.md) | Optimización mixta evolutiva y PNL | cumplida | 9 | 9 | — |
| [049](049-protecciones-nativas-y-coordinacion/spec.md) | Protecciones nativas y coordinación | cumplida | 10 | 10 | — |
| [050](050-aprendizaje-continuo-integrado/spec.md) | Aprendizaje continuo integrado | aprobada | 35 | 35 | T3b, T4b, T5b |
| [051](051-medicion-de-cabecera-en-libro-ancho/spec.md) | Medición de cabecera en libro ancho: una columna por alimentador | cumplida | 11 | 11 | — |
| [052](052-optimizacion-con-proyecto-con-el-oraculo/spec.md) | Optimización de «Con proyecto» con el oráculo y confirmación en DIgSILENT | cumplida | 19 | 19 | — |
| [053](053-catalogo-de-fichas-que-crece/spec.md) | El catálogo de fichas crece con cada código nuevo | cumplida | 9 | 9 | — |
| [054](054-fases-reales-en-el-dgs/spec.md) | Fases reales en el DGS: tramos y SED monofásicos y bifásicos | cumplida | 12 | 12 | — |
| [055](055-estructura-de-la-fuente-sistemas-y-set/spec.md) | Estructura de sistemas y SET desde la propia fuente, para cualquier empresa | cumplida | 7 | 7 | — |
| [056](056-nombres-y-mensajes-segun-la-fuente/spec.md) | Nombres y mensajes según la fuente: cada fuente con sus propias palabras | cumplida | 8 | 8 | — |
| [057](057-oraculo-corrige-antes-de-digsilent/spec.md) | El «Caso base» llega convergido: el oráculo corrige antes de importar | cumplida | 6 | 6 | — |
| [058](058-converter-smart-grid/spec.md) | ConverterSmartGrid: el proyecto sin el nombre de otra empresa | aprobada | 10 | 9 | T6 |
| [059](059-fuente-por-lo-que-se-carga/spec.md) | La fuente es la del fichero que se carga, sin valor por defecto | cumplida | 8 | 8 | — |
| [060](060-correcciones-del-aprendizaje/spec.md) | Correcciones verificables del aprendizaje | cumplida | 8 | 8 | — |
| [061](061-observacion-y-operacion-del-agente/spec.md) | Observación y operación integrada del agente | cumplida | 10 | 10 | — |
| [062](062-retencion-diaria-de-ejecuciones/spec.md) | Retención diaria de ejecuciones y temporales | cumplida | 10 | 10 | — |
| [063](063-informe-de-factibilidad-en-un-paso/spec.md) | Evaluación de conexión y operación comercial en un paso, para cualquier alimentador | cumplida | 57 | 57 | — |
| [064](064-arnes-sin-atajos/spec.md) | Arnés de DIgSILENT sin atajos: un turno para todos y estado restituido | cumplida | 11 | 11 | — |
| [065](065-cierre-de-auditoria-integral/spec.md) | Cierre verificable de la auditoría integral | cumplida | 26 | 26 | — |
| [066](066-libro-de-cada-informe/spec.md) | Cada informe con su libro Excel, según el perfil de la empresa | cumplida | 13 | 13 | — |
| [067](067-asistente-operativo/spec.md) | Asistente operativo: revisión, planes, modelos y tareas que funcionan desde la web | cumplida | 41 | 41 | — |
| [068](068-dataset-real-del-maestro/spec.md) | Dataset real del maestro: órdenes del operador, etiquetas de plata y currículo con su estilo | cumplida | 42 | 42 | — |
| [069](069-interprete-con-codificador-preentrenado/spec.md) | Intérprete de órdenes con codificador preentrenado y clase «ninguna» | aprobada | 41 | 41 | T7 |
| [070](070-asistente-de-punta-a-punta/spec.md) | El asistente opera el conversor de punta a punta | aprobada | 94 | 94 | T11 (DIgSILENT), T28 |
| [071](071-puertas-de-los-modelos/spec.md) | Puertas de los modelos antes de entrenar: PINN en su red, un puntero, sin autoentrenamiento y una guardia de GPU | cumplida | 8 | 8 | — |
| [072](072-pide-y-planeamiento-de-largo-plazo/spec.md) | PIDE y planeamiento de largo plazo: dos entregables desde un mismo estudio | aprobada | 68 | 68 | T9b |
| [073](073-bancos-limitados-por-valle/spec.md) | El número de bancos lo define la tensión en las ventanas de valle | cumplida | 41 | 41 | — |
| [074](074-piloto-madrl-en-obras/spec.md) | Piloto MADRL en obras: medir antes de aprender | aprobada | 14 | 14 | T8 |
| [075](075-validacion-cruzada-de-las-ordenes/spec.md) | Validación cruzada con las órdenes confirmadas, y Ollama no adivina cuando el modelo ve charla | cumplida | 46 | 46 | — |
| [076](076-preguntas-de-metodologia-por-entregable/spec.md) | Preguntas de metodología y criterios por entregable, del flujo, de la arquitectura y de la web | cumplida | 34 | 34 | — |
| [077](077-asistente-lee-el-proyecto/spec.md) | El asistente lee skills, documentos, código y API del proyecto, y un MCP local de solo lectura | cumplida | 80 | 80 | — |
| [078](078-senales-de-convergencia/spec.md) | Las señales de convergencia dicen lo que devolvió DIgSILENT, y el asistente importa un grupo ya convertido | cumplida | 35 | 35 | — |
| [079](079-afinado-del-interprete-de-ordenes/spec.md) | Afinado real del intérprete de órdenes: las últimas capas del codificador junto con sus cabezas | cumplida | 64 | 64 | — |
| [080](080-acceso-directo-a-paquetes-vnrgis/spec.md) | Acceso directo a los paquetes VNR-GIS de cada distribuidora | cumplida | 61 | 61 | — |
| [081](081-regresiones-permanentes/spec.md) | Los fallos reales no se repiten: comprobaciones permanentes, solución con los oráculos y mejora continua | cumplida | 86 | 86 | — |
| [082](082-oraculo-completo-y-por-fases/spec.md) | El oráculo calcula todo lo del modelo, y por fases | cumplida | 15 | 15 | — |
| [083](083-oraculo-antes-de-calibrar/spec.md) | El oráculo antes de calibrar y recalibrar | cumplida | 36 | 36 | — |
| [084](084-seis-reglas-con-requisito/spec.md) | Seis reglas del operador pasan de notas a requisitos con prueba | cumplida | 30 | 30 | — |
| [085](085-ordenes-del-maestro-con-grupos-apartados/spec.md) | Órdenes del maestro con grupos apartados, y la puerta de órdenes sin humanas suficientes | cumplida | 33 | 33 | — |
| [086](086-puesta-en-operacion-comercial/spec.md) | Puesta en operación comercial: versión 1.0 instalable, segura y probada de punta a punta | aprobada | 134 | 131 | T9 (DIgSILENT), T36 (DIgSILENT), T40 (DIgSILENT), T41, T79, T32 (DIgSILENT), T34, T105 (DIgSILENT), T113 |
| [087](087-seleccion-de-obras-con-metodos-y-medicion/spec.md) | Selección de obras con el oráculo, métodos probabilísticos y medición de la mejora | cumplida | 59 | 59 | — |
| [088](088-q-de-cabecera-desde-el-factor-de-potencia/spec.md) | Q negativa desde el factor de potencia | cumplida | 14 | 14 | — |
| [089](089-pronostico-de-demanda-en-un-modulo/spec.md) | Pronóstico de demanda en un módulo: datos vivos, limpieza, tres clases y backtest por método | aprobada | 108 | 107 | T7, T18, T19 |
| [090](090-arquitectura-generada/spec.md) | La arquitectura se cataloga sola: todos los módulos, el asistente y su equipo | cumplida | 19 | 19 | — |
| [091](091-flujo-calibracion-a-estudio/spec.md) | De la calibración al estudio, en su orden y sin avisos que engañen | cumplida | 34 | 34 | — |
| [092](092-caso-base-de-una-red-reconstruida/spec.md) | El «Caso base» de una red reconstruida se verifica con lo que hay en disco | cumplida | 4 | 4 | — |
| [093](093-siglas-de-carga-como-nombre/spec.md) | La sigla de la carga nombra la carga nueva y su variación | cumplida | 4 | 4 | — |
| [094](094-perfil-de-tension-y-bancos/spec.md) | Perfil de tensión en la calibración y bancos ubicados según el perfil | cumplida | 18 | 18 | — |
| [095](095-escaladas-proporcionales-a-su-kva/spec.md) | Escaladas proporcionales a su potencia instalada | cumplida | 3 | 3 | — |
| [096](096-retomar-tras-suspender-el-equipo/spec.md) | Tras suspender el equipo, la web vuelve sola al último trabajo pendiente | cumplida | 8 | 8 | — |
| [097](097-vectores-multilingues-del-rag/spec.md) | Vectores multilingües para la búsqueda del asistente | cumplida | 25 | 25 | — |
| [098](098-transferencia-del-operador-en-calibracion-y-obras/spec.md) | La transferencia de carga del operador, en la calibración y en las obras | cumplida | 51 | 51 | — |
| [099](099-cargas-del-libro-duplicadas-por-el-nombre-del-cliente/spec.md) | Cargas del libro duplicadas por el nombre del cliente | cumplida | 8 | 8 | — |
| [100](100-aceptacion-automatica-por-version/spec.md) | Aceptación automática por versión, sin tareas pendientes por proyecto | implementada | 13 | 13 | T4 (DIgSILENT) |
| [101](101-calibracion-cambia-los-transformadores-sola/spec.md) | La calibración cambia sola los transformadores que impiden converger | cumplida | 15 | 15 | — |
| [102](102-puerta-de-calidad-ci-cd/spec.md) | Puerta de calidad: ningún commit ni subida con la suite en rojo | aprobada | 35 | 35 | T20 |
| [103](103-digsilent-de-cualquier-version/spec.md) | DIgSILENT de cualquier versión instalada | cumplida | 7 | 7 | — |
| [104](104-libros-nuevos-se-reconocen-solos/spec.md) | Los libros nuevos de demanda se reconocen solos | cumplida | 48 | 48 | — |
| [105](105-evolucion-de-clientes-fijos-por-alimentador/spec.md) | Evolución de los clientes fijos de cualquier alimentador | cumplida | 40 | 40 | — |
| [106](106-un-turno-de-gpu-para-la-suite-y-los-entrenamientos/spec.md) | Un turno de GPU para la suite y los entrenamientos, con plazo y diciendo quién lo tiene | cumplida | 25 | 25 | — |
| [107](107-plan-de-inversiones-en-transmision/spec.md) | Plan de Inversiones en Transmisión (PIT) del sistema secundario y complementario | cumplida | 43 | 43 | — |
| [108](108-estudio-de-costos-del-vad/spec.md) | Estudio de costos del VAD con la empresa modelo eficiente | aprobada | 26 | 26 | T13 |
| [109](109-fuentes-y-expedientes-en-la-nube-desde-la-web/spec.md) | Fuentes y expedientes en la nube (Google Drive y OneDrive) desde la web | cumplida | 26 | 26 | — |
| [110](110-envio-de-informes-por-correo-desde-la-web/spec.md) | Envío de informes por correo (Gmail y Outlook) desde la web | cumplida | 14 | 14 | — |
| [111](111-editor-electrico-sobre-el-plano-gis/spec.md) | Editor eléctrico sobre el plano GIS, con los resultados en el mismo trazo | cumplida | 32 | 32 | — |
| [112](112-datasets-de-referencia-anonimizados-y-benchmarks/spec.md) | Datasets de referencia anonimizados y benchmarks reproducibles | aprobada | 23 | 23 | T16 |
