# Índice del código fuente

Cada fichero de `src/` y de `tools/`, qué hace y qué spec lo rige. La suite comprueba
que no falta ninguno y que no sobra ninguno (`tests/test_inventario.py`, spec 009): un
fichero nuevo entra aquí en el mismo cambio que lo crea.

«Base» indica el motor anterior al desarrollo por specs: lo rigen la constitución y la
spec 001, RF-14 (DGS idéntico byte a byte); su diseño histórico está en
`docs/superpowers/`. La spec 002 moverá estos módulos a capas.

## `src/igea_dgs/` — motor de conversión

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `src/igea_dgs/__init__.py` | Paquete del motor y su versión. | base |
| `src/igea_dgs/access.py` | Lector de la base Access de CYMDIST (`.mdb`), la segunda vía de entrada. | base, 001 |
| `src/igea_dgs/ajuste_cabecera.py` | Reparto y cuadre de las demandas a la máxima de cabecera, sin DIgSILENT. | 006 |
| `src/igea_dgs/batch.py` | Conversión de uno, varios o todos los alimentadores, en serie o en paralelo. | base, 001 |
| `src/igea_dgs/capacidades.py` | Capacidades, grupo de conexión y tensión de baja de transformadores y líneas del DGS original, y su comparación con lo leído en DIgSILENT. | 015 |
| `src/igea_dgs/cargas_pf.py` | Lectura de los libros de demandas y cargas nuevas, y plan para DIgSILENT. | 004, 007, 008 |
| `src/igea_dgs/carpeta_pf.py` | Carpeta de DIgSILENT donde quedan los proyectos importados; buscar un proyecto sin activarlo. | 005, 011 (RF-91) |
| `src/igea_dgs/catalog.py` | Catálogo de parámetros eléctricos: tabla de entrada y auditoría del modelo. | base |
| `src/igea_dgs/catalog_data.py` | Datos de fabricante y de norma para los parámetros eléctricos. | base |
| `src/igea_dgs/catalog_merge.py` | Completa el catálogo de equipos cuando el export llega incompleto. | base, 001 |
| `src/igea_dgs/catalog_resolution.py` | Resolución de equipos por evidencia, sin renombrar los códigos de origen. | 001 (RF-18) |
| `src/igea_dgs/cli.py` | Orden `igea-dgs`: `list`, `convert` y `web`. | 001 (RF-1, RF-2) |
| `src/igea_dgs/combine.py` | Une todos los alimentadores en una sola red. | base |
| `src/igea_dgs/coordenadas.py` | Completa las coordenadas que faltan con el grafo de la red. | base |
| `src/igea_dgs/dataset.py` | Lector de los TXT (RED, CARGA, BD_Equipo), en las dos disposiciones. | base |
| `src/igea_dgs/demanda_medida.py` | Máxima de cabecera por medidor y clientes importantes con su SED. | 004 (RF-22 a RF-45) |
| `src/igea_dgs/dgs.py` | Escritor DGS: tablas, FID, cubículos, maniobras, capa gráfica y trazado GPS de las líneas. | base, 010 (RF-1 a RF-4), 011 (RF-128) |
| `src/igea_dgs/economia.py` | Datos de la evaluación técnico-económica (`ComTececo`). | 004 |
| `src/igea_dgs/estudios_pf.py` | Estudios sobre los casos «Sin proyecto» y «Con proyecto», sin DIgSILENT: qué estudios se ofrecen, límites del perfil, violaciones, diferencia y ficheros de resultados. | 011 (RF-23, RF-24, RF-32 a RF-35, RF-37) |
| `src/igea_dgs/export_tables.py` | DGS a Excel multihoja o TSV. | base |
| `src/igea_dgs/feeder_metadata.py` | Procedencia por alimentador de los objetos de una red conjunta. | base |
| `src/igea_dgs/geography.py` | Del CRS de origen a WGS84; geometría de nodos y tramos y su validación. | base, 001 (RF-6) |
| `src/igea_dgs/huella.py` | Dice si dos entradas son la misma foto de la red. | base |
| `src/igea_dgs/identify.py` | Reconoce cada TXT por su contenido, no por su nombre. | base |
| `src/igea_dgs/inventory.py` | Inventario detallado de un dataset cargado. | base |
| `src/igea_dgs/loads.py` | Lector de libros de cargas por SED (columnas, potencia y FP), que usa `cargas_pf.py`. | 004 |
| `src/igea_dgs/model.py` | Modelo eléctrico de un alimentador; en modo estricto no inventa tipos. | base |
| `src/igea_dgs/naming.py` | Nombres y selectores de alimentador; sufijo de tensión de los tipos, el mismo para el DGS y las obras. | base, 011 (RF-61) |
| `src/igea_dgs/native_action.py` | Contexto firmado fuente–proyecto–alimentadores y vocabulario común de resultados para toda acción nativa. | 004, 006, 011 |
| `src/igea_dgs/obras_pf.py` | Obras de mejora sin DIgSILENT: modelo y validación de cada obra, nombres de variación y de copias de tipo, datos e igualdad de tipos, resumen de cada tipo, plan de la simulación y comprobación de «Sin proyecto». | 011 (RF-56, RF-59, RF-61 a RF-65, RF-69, RF-85, RF-94) |
| `src/igea_dgs/oraculo.py` | Flujo independiente con pandapower antes de escribir el DGS. | base |
| `src/igea_dgs/perfil_empresa.py` | Perfil de empresa: CRS de origen, patrón de las SED de medición, escala del diagrama y forma de los alimentadores, fuera del código; hereda de `config/perfiles/`. | 002 (RF-31 a RF-37) |
| `src/igea_dgs/powerfactory_env.py` | Dónde está la API de PowerFactory y qué intérprete la carga. | base |
| `src/igea_dgs/powerfactory_binding.py` | Vínculo auditable entre ejecución fuente, DGS, inventario releído y proyecto nativo aceptado, con el estado del «Caso base» de cada alimentador. | 004, 006, 011, 015 |
| `src/igea_dgs/powerfactory_metadata.py` | Procedencia IGEA en los objetos de PowerFactory. | base |
| `src/igea_dgs/preview.py` | Vista previa georreferenciada del modelo. | base |
| `src/igea_dgs/puentes.py` | Funde los tramos puente de CYMDIST en vez de modelarlos como líneas. | base |
| `src/igea_dgs/reconstruction.py` | Contrato de la reconstrucción auditable del dataset. | 001 (RF-17 a RF-22) |
| `src/igea_dgs/reconstruction_pipeline.py` | Reconstrucción de una selección de alimentadores, sin estado de la web. | 001 (RF-8, RF-9) |
| `src/igea_dgs/reconstruction_topology.py` | Reconstrucción determinista de la topología. | 001 (RF-17) |
| `src/igea_dgs/reglas.py` | Reglas que se aplican a todo alimentador, venga de TXT o de base; patrón de SED de medición y escala del perfil de empresa. | base (P5), 002 (RF-33) |
| `src/igea_dgs/schema.py` | Perfiles de esquema DGS versionados. | base |
| `src/igea_dgs/source_contract.py` | Contrato canónico y evidencia de auditoría compartidos por TXT, MDB y VNR-GIS. | 001, 004, 006 |
| `src/igea_dgs/schemas/pf21_dgs_1_8_4.json` | Perfil DGS genérico de PowerFactory. | base |
| `src/igea_dgs/sed_potencia.py` | Lleva al tamaño normalizado las SED cuya carga supera su transformador. | base |
| `src/igea_dgs/studies.py` | Qué estudios de PowerFactory se pueden correr y qué dato falta para cada uno. | base |
| `src/igea_dgs/study.py` | Estudio de CYMDIST (`.zxst`/`.xst`), entrada opcional que filtra la selección. | base |
| `src/igea_dgs/trafomix.py` | Equipos de medición en MT que la base registra como SED, con el patrón del perfil de empresa. | base, 002 (RF-33) |
| `src/igea_dgs/transferencia_pf.py` | Transferencia de carga sin DIgSILENT: pasos del camino y carga transferida, viabilidad y elemento que limita, máximo por seccionador y por nodo, fichero, factor máximo por bisección y margen del enlace. | 011 (RF-110 a RF-117, RF-121, RF-123, RF-125, RF-129) |
| `src/igea_dgs/util.py` | SHA-256, JSON atómico y números: una sola implementación. | 001 (RF-4, RF-5) |
| `src/igea_dgs/validate.py` | Validación del DGS escrito, con el trazado GPS de cada línea. | base, 010 (RF-5) |

### `src/igea_dgs/sources/` — adaptadores de entrada

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `src/igea_dgs/sources/__init__.py` | Registro de adaptadores, común a la web y al CLI. | 001 (RF-1) |
| `src/igea_dgs/sources/base.py` | Contrato de los lectores de las tres procedencias. | 001 (RF-1) |
| `src/igea_dgs/sources/mdb.py` | Adaptador de base Access. | 001 (RF-1) |
| `src/igea_dgs/sources/snapshot.py` | Qué ficheros forman una lectura y su huella. | 001 (RF-1) |
| `src/igea_dgs/sources/txt.py` | Adaptador de los tres TXT. | 001 (RF-1) |
| `src/igea_dgs/sources/vnr.py` | Adaptador de un paquete VNR-GIS. | 001 (RF-1, RF-2) |

### `src/igea_dgs/web/` — API web

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `src/igea_dgs/web/__init__.py` | Paquete de la interfaz web. | 001 |
| `src/igea_dgs/web/__main__.py` | Arranca la web: `python -m igea_dgs.web` o `igea-dgs-web`. | 001 (RF-15, RF-27) |
| `src/igea_dgs/web/app.py` | Rutas FastAPI sobre el motor. | 001, 004 a 008, 011 (RF-12, RF-25, RF-27, RF-28, RF-95, RF-104) |
| `src/igea_dgs/web/jobs.py` | Trabajos largos en cola, con progreso, cancelación y límite de tiempo por guion (P7). | 001 (RF-8), 011 (RF-39, RF-40) |
| `src/igea_dgs/web/readiness.py` | Puertas por alimentador antes de producir DGS. | 001 |
| `src/igea_dgs/web/reconstruction_service.py` | Diagnóstico y reconstrucción como trabajos de la web. | 001 (RF-8, RF-9) |
| `src/igea_dgs/web/runtime.py` | Comprobación del entorno que hace el lanzador de Windows. | 001 (RF-27) |
| `src/igea_dgs/web/services.py` | Las acciones de la interfaz, sin interfaz. | 001, 004 a 008, 011 (RF-12 a RF-16, RF-25, RF-27 a RF-30, RF-39 a RF-41, RF-68, RF-95, RF-121) |
| `src/igea_dgs/web/source_runs.py` | Custodia inmutable de los ficheros de cada ejecución. | 001 |
| `src/igea_dgs/web/source_scope.py` | Empresa y periodo de los paquetes VNR-GIS. | 001 (RF-2) |
| `src/igea_dgs/web/sources/__init__.py` | Reexportación temporal de `igea_dgs.sources`. | 002 (RF-21 la retira) |
| `src/igea_dgs/web/sources/vnr.py` | Reexportación temporal de `igea_dgs.sources.vnr`. | 002 (RF-21 la retira) |
| `src/igea_dgs/web/workspace.py` | Espacio de trabajo: entradas, opciones, salida de una sesión y obras de mejora sin aplicar. | 001, 011 (RF-95) |

## `src/vnr_etl/` — módulo VNR-GIS

Diseño completo en `VNR-GIS.md` (las «secciones» que citan los docstrings); operación en
`docs/VNR_GIS_PRODUCTION.md`. La spec 002 (RF-6) lo integrará en `igea_dgs`.

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `src/vnr_etl/__init__.py` | Paquete del módulo VNR-GIS. | 001 |
| `src/vnr_etl/__main__.py` | `python -m vnr_etl`. | 001 |
| `src/vnr_etl/application/__init__.py` | Servicios compartidos por el CLI y la API. | 001 |
| `src/vnr_etl/application/cymdist_bridge.py` | Del modelo canónico VNR al contrato del motor. | 001 (RF-10) |
| `src/vnr_etl/application/reconstruccion.py` | Reconstruye el modelo canónico antes del motor. | 001 (RF-17 a RF-22) |
| `src/vnr_etl/application/services.py` | Validación y exportación VNR en un solo sitio. | 001 (RF-10) |
| `src/vnr_etl/audit/__init__.py` | Auditoría de solo lectura. | 001 |
| `src/vnr_etl/audit/project.py` | Auditoría del proyecto anfitrión. | 001 |
| `src/vnr_etl/catalogs/__init__.py` | Catálogos aprobados de conductores y equipos. | 001 |
| `src/vnr_etl/catalogs/conductor.py` | Mapeo del catálogo de conductores. | 001 (RF-18) |
| `src/vnr_etl/cli.py` | Orden `vnr-etl`. | 001 |
| `src/vnr_etl/config.py` | Configuración del ETL. | 001 |
| `src/vnr_etl/connectors/__init__.py` | Conectores de fuente. | 001 |
| `src/vnr_etl/connectors/arcgis.py` | Conector ArcGIS REST. | 001 |
| `src/vnr_etl/connectors/base.py` | Contrato de los conectores. | 001 |
| `src/vnr_etl/connectors/databases.py` | Bases de datos y volcados SQL. | 001 |
| `src/vnr_etl/connectors/delimited.py` | Texto delimitado (CSV/TXT) con codificación y separador deducidos. | 001 (RF-26) |
| `src/vnr_etl/connectors/registry.py` | Registro de adaptadores de fuente. | 001 (RF-26) |
| `src/vnr_etl/connectors/vector.py` | GeoJSON, Shapefile y GeoPackage. | 001 (RF-26) |
| `src/vnr_etl/discovery/__init__.py` | Descubrimiento, huella, catálogo y descarga de fuentes. | 001 |
| `src/vnr_etl/discovery/catalog.py` | Catálogo de publicaciones y empresas. | 001 |
| `src/vnr_etl/discovery/download.py` | Descargas y manejo seguro de archivos. | 001 |
| `src/vnr_etl/discovery/fingerprint.py` | Huella de fuente y de esquema. | 001 |
| `src/vnr_etl/discovery/freshness.py` | La publicación más nueva por fecha autoritativa. | 001 |
| `src/vnr_etl/discovery/official.py` | Publicaciones oficiales de OSINERGMIN. | 001 |
| `src/vnr_etl/discovery/schema.py` | Descubrimiento semántico del esquema. | 001 |
| `src/vnr_etl/doctor.py` | Dependencias y capacidades (`vnr-etl doctor`). | 001 |
| `src/vnr_etl/electrical/__init__.py` | Enriquecimiento eléctrico. | 001 |
| `src/vnr_etl/electrical/enrich.py` | Completa los datos eléctricos del modelo. | 001 (RF-18, RF-19) |
| `src/vnr_etl/exporters/__init__.py` | Exportadores de simulador. | 001 |
| `src/vnr_etl/exporters/base.py` | Contrato del exportador y perfil de destino. | 001 (RF-23) |
| `src/vnr_etl/exporters/cymdist.py` | Exportador CYMDIST. | 001 |
| `src/vnr_etl/exporters/dgs.py` | Exportador DIgSILENT: delega en el motor. | 001 (RF-10) |
| `src/vnr_etl/gis/__init__.py` | CRS, snapping y reconstrucción de nodos. | 001 |
| `src/vnr_etl/gis/crs.py` | CRS de las capas y su deducción. | 001 (RF-20, RF-25) |
| `src/vnr_etl/gis/geometry.py` | Geometría auxiliar, sin `shapely`. | 001 |
| `src/vnr_etl/gis/snapping.py` | Snapping y reconstrucción de nodos. | 001 |
| `src/vnr_etl/logging.py` | Registro estructurado de eventos. | 001 |
| `src/vnr_etl/models/__init__.py` | Modelo canónico VNR-GIS. | 001 |
| `src/vnr_etl/models/canonical.py` | Clases del modelo canónico. | 001 |
| `src/vnr_etl/pipeline.py` | Capa de aplicación compartida por el CLI y la web. | 001 (RF-2) |
| `src/vnr_etl/reconciliation/__init__.py` | Reconciliación y comparación de periodos. | 001 |
| `src/vnr_etl/reconciliation/diff.py` | Comparación incremental por ID estable. | 001 |
| `src/vnr_etl/topology/__init__.py` | Topología y validación del grafo. | 001 |
| `src/vnr_etl/topology/graph.py` | Validación de topología con NetworkX. | 001 |
| `src/vnr_etl/validation/__init__.py` | Puertas de validación A–H. | 001 (RF-22 a RF-24) |
| `src/vnr_etl/validation/gates.py` | Las puertas A–H. | 001 (RF-22 a RF-24) |
| `src/vnr_etl/web/__init__.py` | Rutas web VNR-GIS, montadas en la API principal. | 001 (RF-11) |
| `src/vnr_etl/web/app.py` | `APIRouter` bajo `/api/vnr`. | 001 (RF-11) |

## `tools/` — herramientas

Todas aceptan `--help` sin DIgSILENT ni datos (spec 009, RF-7). Las que hablan con
DIgSILENT se ejecutan con su intérprete; ver `docs/MANUAL_COMANDOS.md`.

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `tools/accept_three_sources.py` | Aceptación universal y separada de MDB, TXT y VNR-GIS hasta ajuste, relectura y estudio nativos. | 001, 004, 006, 011 |
| `tools/ajuste_cabecera_pf.py` | Guion de DIgSILENT: ajusta un alimentador a su máxima de cabecera, en el escenario de «Sin proyecto». | 006, 008, 011 (RF-18, RF-19, RF-51, RF-54), 014, 015 |
| `tools/apply_catalog_to_model.py` | Corrige las características eléctricas del modelo con el catálogo de fichas. | base |
| `tools/base_scenario.py` | Escenario base (año 0): lo construye, lo hace converger y lo diagnostica. | 005 |
| `tools/build_input_catalog.py` | Tabla de parámetros eléctricos en `input/` y auditoría de alimentadores. | base |
| `tools/build_system_grid.py` | Todos los alimentadores en una sola red, importada en PowerFactory. | base |
| `tools/cargas_pf.py` | Guion de DIgSILENT: demandas y cargas nuevas en un proyecto existente. | 004, 007, 008, 011 (RF-52 a RF-55) |
| `tools/casos_pf.py` | Guion de DIgSILENT: los casos «Caso base», «Sin proyecto» y «Con proyecto», cada uno con su escenario y sus variaciones; «Sin proyecto» solo desde el «Caso base» verificado. | 011 (RF-1 a RF-16, RF-46 a RF-50; casos para RF-51 a RF-54), 014, 015 |
| `tools/estudios_pf.py` | Guion de DIgSILENT: un estudio en un caso, sin escalado por alimentador y sin aplicar lo que proponen los optimizadores; mide cada alimentador. Con `--guion`, lista o ejecuta los guiones DPL y Python del operador. | 011 (RF-17, RF-20 a RF-22, RF-26, RF-27 a RF-30, RF-31, RF-33, RF-36, RF-38, RF-43 a RF-45, RF-49) |
| `tools/check_pf_license.py` | Qué módulos de PowerFactory permite la licencia. | 005, 011, 012 (RF-4) |
| `tools/compare_schema.py` | Cabeceras de un DGS externo frente a un perfil de esquema. | base |
| `tools/convertir_grupos_mdb.py` | Varios alimentadores de una base en un DGS, importado y con flujo. | base |
| `tools/emparejar_entradas.py` | Empareja TXT y bases Access que son la misma foto de la red. | base |
| `tools/fidelidad_seleccion.py` | Comprueba que una selección pasa entera del TXT al DGS. | 009 |
| `tools/linea_base_dgs.py` | Línea base de DGS para comprobar que una reorganización no cambia nada. | 001 (RF-14), 002 (RF-20) |
| `tools/obras_pf.py` | Guion de DIgSILENT de las obras de mejora: con `--bibliotecas`, alimentadores y tipos de las tres bibliotecas; copia de un tipo al proyecto; simular y aplicar con las reglas comunes (variación por obra, activación por caso, flujo, comprobación de «Sin proyecto»); banco de condensadores, reconectador, regulador, sección de cable, terna en la troncal y migración del alimentador a otra tensión. | 011 (RF-56 a RF-60, RF-64 a RF-67, RF-69, RF-71 a RF-94, RF-96, RF-97, RF-99 a RF-103) |
| `tools/pf_proyectos.py` | Proyectos de la carpeta de importación de DIgSILENT y sus alimentadores. | 005 |
| `tools/powerfactory_acceptance.py` | Puerta de aceptación: importa un DGS en PowerFactory, o adopta un proyecto existente, y verifica su «Caso base» frente al archivo original. | base, 010 (RF-6, RF-7), 015 |
| `tools/prueba_representacion.py` | Red, cargas y SED del TXT en una hoja de PowerFactory. | base |
| `tools/run_one_study.py` | Trabajador de PowerFactory: importa y mide, o ejecuta un estudio. | 005 |
| `tools/run_powerfactory_gate.bat` | Lanza `powerfactory_acceptance.py` con el intérprete de PowerFactory. | base |
| `tools/show_pf_diagram.py` | Abre en DIgSILENT el diagrama de un alimentador. | 005 |
| `tools/suggest_line_type_aliases.py` | Propone alias para tipos de línea sin ficha en el catálogo. | base |
| `tools/transferencia_pf.py` | Guion de DIgSILENT: transferencia de carga entre dos alimentadores por su enlace, paso a paso en los dos sentidos, con la capacidad y el margen del enlace (`ComTransfer` o flujos sucesivos), sin dejar nada en el proyecto. | 011 (RF-104 a RF-129) |
| `tools/verificar_pf.py` | Guion de DIgSILENT: convergencia del proyecto con lo activo. | 008 |

## `frontend/src/` — interfaz web

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `frontend/src/main.tsx` | Arranque de React. | 001 |
| `frontend/src/App.tsx` | Marco de la página: paneles, pestañas, resúmenes de trabajos. | 001, 008 (RF-1, RF-2) |
| `frontend/src/api.ts` | Cliente tipado de la API. | 001 (RF-12, RF-13), 011 (RF-42) |
| `frontend/src/types.ts` | Tipos de las respuestas de la API. | 001, 011 |
| `frontend/src/clientesCatalogo.ts` | Estado del catálogo mensual de clientes: un solo libro activo e índice vigente antes de cruzar. | 004, 008 |
| `frontend/src/projectBinding.ts` | Vínculo del proyecto de DIgSILENT con su ejecución de origen: separa los bloqueos de las advertencias por cambios manuales. | 005 |
| `frontend/src/context.tsx` | Contexto común de la aplicación. | 001 |
| `frontend/src/useWorkspace.ts` | Espacio de trabajo, Registro en vivo y trabajos por WebSocket. | 001 |
| `frontend/src/styles.css` | Tokens y estilos, modo claro y oscuro. | 001 |
| `frontend/src/components/InputsPanel.tsx` | Entrada de datos: TXT, MDB y VNR-GIS. | 001 (RF-26) |
| `frontend/src/components/OptionsPanel.tsx` | Opciones de conversión. | 001 |
| `frontend/src/components/FeedersPanel.tsx` | Tabla de alimentadores y conversión. | 001 |
| `frontend/src/components/ReconstructionPanel.tsx` | Diagnóstico y reconstrucción. | 001 (RF-8, RF-9) |
| `frontend/src/components/Modules.tsx` | Pestañas de resultados, catálogo y sistema completo. | 001 |
| `frontend/src/components/CargasTab.tsx` | Pestaña «Cargas en DIgSILENT» en cuatro pasos. | 004, 005, 008, 011 (RF-42, RF-98) |
| `frontend/src/components/DemandaMedida.tsx` | Paso 2: libros de medición, máxima de cabecera y clientes. | 004, 008 |
| `frontend/src/components/EstudiosPF.tsx` | Paso 4.2: estudios sobre la red calibrada, límites y resultados. | 011 (RF-24, RF-25, RF-35, RF-39, RF-68) |
| `frontend/src/components/GuionesPF.tsx` | Paso 4.2: guiones DPL y Python del operador, sus parámetros y su salida por caso. | 011 (RF-27 a RF-30) |
| `frontend/src/components/ObrasPF.tsx` | Paso 4.1: formulario de obras de mejora, bibliotecas de tipos, obras guardadas, simular y aplicar. | 011 (RF-56 a RF-95) |
| `frontend/src/components/TransferenciaPF.tsx` | Paso 4.3: transferencia de carga entre dos alimentadores. | 011 (RF-104 a RF-123) |
| `frontend/src/components/AjusteCabecera.tsx` | Paso 2.4: ajuste a la máxima de uno o varios alimentadores. | 006, 008 |
| `frontend/src/components/CurvaCabecera.tsx` | Paso 2.4: curva del registro del medidor de cabecera, con el mes de la máxima sombreado y zoom por tramo. | 006 (RF-32 a RF-38) |
| `frontend/src/components/JobBar.tsx` | Barra de trabajos en curso. | 001 |
| `frontend/src/components/LogPanel.tsx` | Registro. | 001 |
| `frontend/src/components/ui.tsx` | Piezas comunes: modal, avisos, casillas, ficheros. | 001 |

## Documentación

| Documento | Para qué | Vigencia |
| --- | --- | --- |
| `README.md` | Qué es, instalación y uso. | vigente |
| `CLAUDE.md` | Reglas para trabajar en el repositorio. | vigente |
| `CODIGO_FUENTE.md` | Este índice. | vigente |
| `docs/constitution.md` | Principios innegociables. | vigente |
| `docs/MANUAL_COMANDOS.md` | Cada orden del CLI y cada herramienta. | vigente |
| `docs/POWERFACTORY_ACCEPTANCE.md` | Aceptación en PowerFactory. | vigente |
| `docs/VNR_GIS_PRODUCTION.md` | Operación del módulo VNR-GIS. | vigente |
| `docs/runbooks/three-source-production-acceptance.md` | Aceptación de las tres fuentes. | vigente |
| `docs/runbooks/universal-native-load-acceptance.md` | Aceptación universal hasta carga, relectura y estudio nativos. | vigente |
| `VNR-GIS.md` | Diseño completo de VNR-GIS, citado por secciones en el código. | vigente |
| `input/README.md` | Qué va en `input/`. | vigente |
| `specs/NNN-*/` | Specs, planes y tareas. | vigente |
| `docs/DIAGNOSTICO_*.md` | Diagnósticos fechados que dieron origen a specs. | histórico |
| `docs/superpowers/` | Diseños y planes anteriores a las specs. | histórico |
