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
| `src/igea_dgs/ajuste_cabecera.py` | Reparto y cuadre de las demandas a la máxima de cabecera, sin DIgSILENT; por zonas con una central en el troncal; cuadre conjunto de los alimentadores de un proyecto en los mismos flujos; cuántos bancos faltan y dónde. | 006, 021 (RF-33, RF-40 a RF-45, RF-54 a RF-58, RF-64 a RF-66) |
| `src/igea_dgs/batch.py` | Conversión de uno, varios o todos los alimentadores, en serie o en paralelo.; la red unida por zonal y SET con su informe, aperturas y oráculo | base, 001, 022 (RF-7, RF-25, RF-34) |
| `src/igea_dgs/capacidades.py` | Capacidades, grupo de conexión y tensión de baja de transformadores y líneas del DGS original, y su comparación con lo leído en DIgSILENT. | 015 |
| `src/igea_dgs/cargas_pf.py` | Lectura de los libros de demandas y cargas nuevas, y plan para DIgSILENT. | 004, 007, 008, 016 (RF-73) |
| `src/igea_dgs/catalogo_reguladores.py` | Reguladores de tensión de catálogo (Eaton VR-32, 50 Hz): unidad por tensión del sistema y por corriente, y los datos de su `TypVoltreg`. | 025 (RF-59, RF-60) |
| `src/igea_dgs/carpeta_pf.py` | Carpeta de DIgSILENT donde quedan los proyectos importados; buscar un proyecto sin activarlo. | 005, 011 (RF-91) |
| `src/igea_dgs/catalog.py` | Catálogo de parámetros eléctricos: tabla de entrada y auditoría del modelo. | base |
| `src/igea_dgs/catalog_data.py` | Datos de fabricante y de norma para los parámetros eléctricos. | base |
| `src/igea_dgs/catalog_merge.py` | Completa el catálogo de equipos cuando el export llega incompleto. | base, 001 |
| `src/igea_dgs/catalog_resolution.py` | Resolución de equipos por evidencia, sin renombrar los códigos de origen. | 001 (RF-18) |
| `src/igea_dgs/cli.py` | Orden `igea-dgs`: `list`, `convert` y `web`.; `--por-sistema [ZONAL]` y `--estructura`, aparte de `--unir` | 001 (RF-1, RF-2), 022 (RF-4, RF-7, RF-47 a RF-49) |
| `src/igea_dgs/combine.py` | Une todos los alimentadores en una sola red; con la estructura de la empresa, la cuelga de sus SET: barra por SET y tensión e interruptor de cabecera por alimentador. | base, 022 (RF-10 a RF-13, RF-17 a RF-19, RF-21) |
| `src/igea_dgs/coordenadas.py` | Completa las coordenadas que faltan con el grafo de la red. | base |
| `src/igea_dgs/dataset.py` | Lector de los TXT (RED, CARGA, BD_Equipo), en las dos disposiciones. | base |
| `src/igea_dgs/demanda_medida.py` | Máxima de cabecera por medidor y clientes importantes con su SED; el registro de las 00:00 conserva su hora; máxima de demanda con una central en el troncal; la del mes de análisis o el registro de un instante coincidente; el nombre del cliente.; medidores de barra, sus barras de SET y la máxima de la suma de sus transformadores; periodo de un año entero, libros de cabecera y de clientes en subcarpetas de año y mes del nombre por una regla general | 004 (RF-22 a RF-45, RF-56, RF-57), 013 (RF-11), 021 (RF-28 a RF-34, RF-50, RF-51, RF-53), 022 (RF-37 a RF-46), 025 (RF-1, RF-3 a RF-7, RF-12, RF-13, RF-25b, RF-25c, RF-28 a RF-30) |
| `src/igea_dgs/libros_por_anio.py` | Libros de demanda por año de medición: árbol de libros con su año (carpeta de cuatro cifras a cualquier altura) y su ruta relativa, años disponibles y libros de un periodo, sin abrirlos | 025 (RF-1 a RF-3, RF-7 a RF-9, RF-26, RF-27) |
| `src/igea_dgs/digital_twin/__init__.py` | Paquete del gemelo digital: episodios, búfer y captura, sin PowerFactory ni PyTorch. | 024 |
| `src/igea_dgs/digital_twin/episode.py` | Contrato del episodio: clase y caso, fuente y proyecto, resultados del flujo (balance, pérdidas, cargabilidad, tensiones, confiabilidad, o el motivo de su ausencia), obras con su alternativa del PIDE e indicadores, artefactos; JSON canónico, huella SHA-256 y validación con la ruta del campo que falla. | 024 (RF-1, RF-2, RF-4, RF-6, RF-7, RF-9, RF-28, RF-32) |
| `src/igea_dgs/digital_twin/escenarios.py` | Matriz de escenarios (demanda escalada y N-1), familia topológica y partición fija, elección por incertidumbre o diversidad y presupuesto de licencia del aprendizaje activo. | 024 (RF-11, RF-12, RF-40, RF-41) |
| `src/igea_dgs/digital_twin/buffer.py` | Búfer local e inmutable de episodios: un JSON por huella, escritura atómica e idempotente, colisión detectada, índice SQLite reconstruible con consultas por proyecto, alimentador, caso, clase, acción, fuente y versión, cuarentena de manifiestos ilegibles; sin borrado. | 024 (RF-6 a RF-10) |
| `src/igea_dgs/digital_twin/capture.py` | Ensamblaje del episodio desde el contexto firmado, el resultado del guion y la lectura tras reabrir; lectura que falta, de otro proyecto o con el trazado manual cambiado, a cuarentena; simulación aceptada como contrafactual. | 024 (RF-1 a RF-4, RF-9) |
| `src/igea_dgs/digital_twin/evaluacion.py` | Evaluación por caso: «Caso base» y «Sin proyecto» con las violaciones como diagnóstico (y el cuadre de la calibración), «Con proyecto» contra la norma de su sistema del perfil (tensión, cargabilidad, transformadores NTP 370.400) y frente a «Sin proyecto» en pérdidas y confiabilidad. | 024 (RF-4, RF-5, RF-26, RF-29 a RF-31) |
| `src/igea_dgs/digital_twin/integration.py` | Captura tras cada acción nativa de la web: plan de lectura, norma de cada alimentador por su sistema y límites más estrictos, referencia del último «Sin proyecto» aceptado, obras al PIDE, aviso en el Registro y cuarentena sin repetir la acción; interruptor `IGEA_TWIN_CAPTURA`. | 024 (RF-1, RF-27, RF-31, RF-32) |
| `src/igea_dgs/digital_twin/native_snapshot.py` | Identidad estable de un objeto de DIgSILENT, huella SHA-256 de un trazado e islas por tramos cerrados, sin suponer red radial. | 024 (RF-2, RF-3) |
| `src/igea_dgs/digital_twin/oraculo.py` | Oráculo PINN/GNN (PyTorch, GPU si la hay): grafo por unidad, red de grafos con pérdida física de balance nodal, conjunto con incertidumbre, fuera de dominio, estado eléctrico (flujos, pérdidas, cargabilidad), registro de modelos con promoción por puertas, vuelta al anterior, deriva y reentreno; barrido radial con el mismo contrato; orden de obras candidatas. | 024 (RF-12 a RF-19, RF-23, RF-35, RF-36, RF-38 a RF-40, RF-42 a RF-44) |
| `src/igea_dgs/digital_twin/temporal.py` | Gemelo temporal: GRU de las curvas de cabecera (estacional sin PyTorch), métricas, desviaciones por instante y alimentador, pseudo-medidas por kVA con intervalo e instante crítico coincidente. | 024 (RF-20 a RF-22, RF-37) |
| `src/igea_dgs/dgs.py` | Escritor DGS: tablas, FID, cubículos, maniobras, capa gráfica y trazado GPS de las líneas; la barra de una SED sola va dentro de ella.; con la estructura, una red y un diagrama por zonal, la SET como subestación con sus barras, una red externa por barra y el ElmFeeder en el interruptor de cabecera | base, 010 (RF-1 a RF-4), 011 (RF-128), 021 (RF-12), 022 (RF-6 a RF-16) |
| `src/igea_dgs/economia.py` | Datos de la evaluación técnico-económica (`ComTececo`). | 004 |
| `src/igea_dgs/enlaces.py` | Puntos de enlace de la red unida con sus SET y caminos cerrados (entre SET, entre alimentadores, anillos): abre la maniobra más lejana de su fuente o, si no hay, un punto abierto en el tramo más lejano, hasta dejarla radial. | 022 (RF-26, RF-27, RF-29 a RF-31, RF-34) |
| `src/igea_dgs/estructura.py` | La estructura de la empresa: zonales, SET (con sus siglas) y alimentadores con su sistema eléctrico, sector típico y norma; del perfil o de la tabla en Excel; qué SET tiene cada alimentador de la entrega, los «Sin SET», los que faltan y lo que se omite sin redes. | 022 (RF-1 a RF-6, RF-19, RF-20, RF-25b) |
| `src/igea_dgs/estudios_pf.py` | Estudios sobre los casos «Sin proyecto» y «Con proyecto», sin DIgSILENT: qué estudios se ofrecen, límites del perfil, violaciones, diferencia y ficheros de resultados. | 011 (RF-23, RF-24, RF-32 a RF-35, RF-37) |
| `src/igea_dgs/export_tables.py` | DGS a Excel multihoja o TSV. | base |
| `src/igea_dgs/feeder_metadata.py` | Procedencia por alimentador de los objetos de una red conjunta.; la red externa de una barra de SET, una vez con sus alimentadores | base, 022 (RF-11) |
| `src/igea_dgs/geography.py` | Del CRS de origen a WGS84; geometría de nodos y tramos y su validación. | base, 001 (RF-6) |
| `src/igea_dgs/identify.py` | Reconoce cada TXT por su contenido, no por su nombre. | base |
| `src/igea_dgs/informe_docx.py` | Escribe en Word los informes de estudio eléctrico y de factibilidad como esquemas generales sobre el modelo de la empresa: de él solo la forma (primera sección con su cabecera, pie y estilos; cuerpo vaciado; n.º, referencia y total de páginas fijos sustituidos); orden de Casa Blanca y de EMAPICA, datos de la fuente, tensión por fase o trifásica, leyendas, figuras de DIgSILENT, obras por etapa o por alternativa (tabla de trechos del conductor, cuadro comparativo, bancos existentes por nodo), punto de diseño, pérdidas, transformador de la SET y conclusiones, con coma decimal; lo que falta queda vacío y su motivo en el JSON; escritura atómica. Abre modelos que Word dejó con imágenes rotas. | 017 (RF-2 a RF-9, RF-13, RF-15 a RF-25, RF-27, RF-31, RF-44 a RF-46, RF-50, RF-52, RF-59, RF-62, RF-106, RF-113, RF-114, RF-118, RF-120, RF-122, RF-128, RF-132 a RF-135) |
| `src/igea_dgs/libros_informe.py` | Libro de pérdidas de la empresa (sistema eléctrico, % reconocidos en potencia y energía, precio de compra), buscado por los nombres de hojas y columnas del perfil, con el hueco del alimentador que no está; tabla de costes de bancos, reguladores y precio de la energía, cada fila con fuente, fecha y marca «referencial», y lo que falta para las etapas 2 y 3. | 017 (RF-39b a RF-39e, RF-40c, RF-62 a RF-64) |
| `src/igea_dgs/informes.py` | Informes de estudio eléctrico y de factibilidad sin DIgSILENT: qué toman del perfil de empresa (modelos, banda y umbral, bandas de coloreado, proyecto de transmisión) y qué falta para generar cada tipo; casos y etapas medidos (contrato JSON con el guion), etapa recomendada, alternativas de obras y trechos continuos del cambio de conductor, pérdidas anuales con las fórmulas del libro de la empresa, veredicto de factibilidad y redacción de análisis, antecedentes y conclusiones. | 017 (RF-4, RF-5, RF-13 a RF-22, RF-31, RF-33, RF-34, RF-43, RF-50, RF-54 a RF-60, RF-71, RF-72, RF-107, RF-108, RF-115, RF-121, RF-122, RF-128, RF-129, RF-132, RF-134) |
| `src/igea_dgs/inventory.py` | Inventario detallado de un dataset cargado. | base |
| `src/igea_dgs/loads.py` | Lector de libros de cargas por SED (columnas, potencia y FP), que usa `cargas_pf.py`. | 004 |
| `src/igea_dgs/model.py` | Modelo eléctrico de un alimentador; en modo estricto no inventa tipos. | base |
| `src/igea_dgs/naming.py` | Nombres y selectores de alimentador; sufijo de tensión de los tipos, el mismo para el DGS y las obras. | base, 011 (RF-61) |
| `src/igea_dgs/native_action.py` | Contexto firmado fuente–proyecto–alimentadores y vocabulario común de resultados para toda acción nativa. | 004, 006, 011 |
| `src/igea_dgs/obras_pf.py` | Obras de mejora sin DIgSILENT: modelo y validación de cada obra (lo de «Sin proyecto» pasa a «Con proyecto»; enlace y migración solo en «Con proyecto»), nombres de variación y de copias de tipo, datos e igualdad de tipos, resumen de cada tipo, plan de la simulación (sección de toda la troncal, enlace entre alimentadores, migración de lo que queda aguas abajo de un nodo) y comprobación de «Sin proyecto». | 011 (RF-56, RF-59, RF-61 a RF-65, RF-69, RF-85, RF-94); 016 (RF-6 a RF-9, RF-11, RF-13, RF-14, RF-23 a RF-25, RF-31, RF-38 a RF-41, RF-51 a RF-59, RF-61, RF-65, RF-66) |
| `src/igea_dgs/oraculo.py` | Flujo independiente con pandapower antes de escribir el DGS; sobre la red unida entera, con una isla por barra de SET, su veredicto por SET y zonal y, si una no converge, su barra más débil y su transformador más cargado. | base, 022 (RF-28, RF-32, RF-33) |
| `src/igea_dgs/pide.py` | Metodología del PIDE (RM 428-2017-MEM/DM): proyección y densidad de carga por cuadrículas de la Tabla N.º 2, diagnóstico con su causa (caída, FP, conductor, transformador, isla, sobretensión, pérdidas), año de incumplimiento, plan por etapas sin adelantar obras y formatos 01 a 15 en Excel. | 024 (RF-49 a RF-53, RF-60 a RF-63) |
| `src/igea_dgs/pide_economia.py` | Evaluación económica y priorización del PIDE: libro CAPEX por nombres del perfil (sin datos personales), anualidad, costo anual, VAN y TIR del art. 14, flujo privado con el pliego tarifario y la tasa privada, priorización del art. 15 con obras sobredimensionadas, y la propuesta con la obra de la spec 011 de lo que se construye solo. | 024 (RF-33, RF-34, RF-45 a RF-47, RF-54 a RF-59) |
| `src/igea_dgs/perfil_empresa.py` | Perfil de empresa: CRS de origen, patrón de las SED de medición, escala del diagrama y forma de los alimentadores, fuera del código; hereda de `config/perfiles/`; fichas de transformadores de SED; tamaño de banco por tensión (021:RF-65); centrales térmicas por alimentador; uno o varios patrones de nombre de los libros de clientes. | 002 (RF-31 a RF-37), 020 (RF-29 a RF-31), 021 (RF-27), 025 (RF-6b) |
| `src/igea_dgs/mapa_informe.py` | Imágenes del informe de estudio (ubicación, tensión, cargabilidad y detalle de las obras) con el GPS y los resultados del flujo de DIgSILENT; conductor nuevo y bancos resaltados con rótulos que no se pisan. | 017 (RF-11b, RF-116, RF-133) |
| `src/igea_dgs/pf_arnes.py` | Arnés de DIgSILENT: turno del motor de la máquina, conexión común con reintento, caso restituido y proceso que se queda abierto. | 019 |
| `src/igea_dgs/powerfactory_env.py` | Dónde está la API de PowerFactory y qué intérprete la carga; cierra los guiones de PowerFactory huérfanos y corta un guion con sus hijos. | base |
| `src/igea_dgs/powerfactory_binding.py` | Vínculo auditable entre ejecución fuente, DGS, inventario releído y proyecto nativo aceptado, con el estado del «Caso base» de cada alimentador. | 004, 006, 011, 015 |
| `src/igea_dgs/powerfactory_metadata.py` | Procedencia IGEA en los objetos de PowerFactory. | base |
| `src/igea_dgs/preview.py` | Vista previa georreferenciada del modelo. | base |
| `src/igea_dgs/puentes.py` | Funde los tramos puente de CYMDIST en vez de modelarlos como líneas; su equipo pasa al extremo de la línea vecina si cabe. | base, 021 |
| `src/igea_dgs/reconstruction.py` | Contrato de la reconstrucción auditable del dataset. | 001 (RF-17 a RF-22) |
| `src/igea_dgs/reconstruction_pipeline.py` | Reconstrucción de una selección de alimentadores, sin estado de la web. | 001 (RF-8, RF-9) |
| `src/igea_dgs/reconstruction_topology.py` | Reconstrucción determinista de la topología. | 001 (RF-17) |
| `src/igea_dgs/reglas.py` | Reglas que se aplican a todo alimentador, venga de TXT o de base; patrón de SED de medición y escala del perfil de empresa.; no cuenta como de la entrada los interruptores de cabecera ni los puntos abiertos | base (P5), 002 (RF-33), 021 (RF-9), 022 (RF-12, RF-31) |
| `src/igea_dgs/schema.py` | Perfiles de esquema DGS versionados. | base |
| `src/igea_dgs/source_contract.py` | Contrato canónico y evidencia de auditoría compartidos por TXT, MDB y VNR-GIS. | 001, 004, 006 |
| `src/igea_dgs/schemas/digital_twin_episode_v1.schema.json` | Esquema JSON publicado del episodio del gemelo digital, igual al contrato de `digital_twin/episode.py`. | 024 (RF-7) |
| `src/igea_dgs/schemas/pf21_dgs_1_8_4.json` | Perfil DGS genérico de PowerFactory. | base |
| `src/igea_dgs/sed_potencia.py` | Lleva al tamaño normalizado las SED cuya carga supera su transformador. | base |
| `src/igea_dgs/studies.py` | Qué estudios de PowerFactory se pueden correr y qué dato falta para cada uno. | base |
| `src/igea_dgs/study.py` | Estudio de CYMDIST (`.zxst`/`.xst`), entrada opcional que filtra la selección. | base |
| `src/igea_dgs/trafomix.py` | Equipos de medición en MT que la base registra como SED, con el patrón del perfil de empresa; quita el fusible que solo llevaba a uno. | base, 002 (RF-33), 021 (RF-7) |
| `src/igea_dgs/transferencia_pf.py` | Transferencia de carga sin DIgSILENT: pasos del camino y carga transferida, viabilidad y elemento que limita, máximo por seccionador y por nodo, fichero, factor máximo por bisección y margen del enlace. | 011 (RF-110 a RF-117, RF-121, RF-123, RF-125, RF-129) |
| `src/igea_dgs/trafos_sed.py` | Transformador nuevo para una SED fija sobrecargada: la menor potencia de la tabla de fichas del perfil (por tensión primaria) con la máxima en el umbral, o unidades en paralelo de la mayor. | 020 (RF-6 a RF-8, RF-10, RF-11) |
| `src/igea_dgs/troncal.py` | Troncal de las obras sin DIgSILENT: camino continuo más largo desde la cabecera sobre el árbol de caminos más cortos en metros (anillos cerrados avisados), lo que queda aguas abajo de un nodo, el punto de la troncal más cercano (partir el tramo o usar la barra según la distancia mínima), el corte del trazado y los dos extremos del enlace. | 016 (RF-1 a RF-5, RF-15, RF-18, RF-20, RF-27, RF-28, RF-45, RF-64, RF-65, RF-67) |
| `src/igea_dgs/vias.py` | Trazado de una línea nueva por la vía pública con un enrutador OSRM (OpenStreetMap): ruta con sus curvas, largo con los accesos, metros fuera de vía y recta si no hay enrutador o no responde; solo envía las dos coordenadas. | 016 (RF-81 a RF-87) |
| `src/igea_dgs/util.py` | SHA-256, JSON atómico y números: una sola implementación. | 001 (RF-4, RF-5) |
| `src/igea_dgs/validate.py` | Validación del DGS escrito, con el trazado GPS de cada línea.; reconoce la red por zonal y SET | base, 010 (RF-5), 021 (RF-12), 022 (RF-8 a RF-14) |

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
| `src/igea_dgs/web/__main__.py` | Arranca la web: `python -m igea_dgs.web` o `igea-dgs-web`; con el puerto ocupado reutiliza, reemplaza o cambia de puerto. | 001 (RF-15, RF-27, RF-28 a RF-32) |
| `src/igea_dgs/web/app.py` | Rutas FastAPI sobre el motor.; conversión por sistema eléctrico (`/convert/sistema`, `/estructura`) y la tabla de la estructura | 001, 004 a 008, 011 (RF-12, RF-25, RF-27, RF-28, RF-95, RF-104), 017 (RF-96, RF-103, RF-104), 021 (RF-26, RF-28 a RF-34), 022 (RF-4, RF-7, RF-47 a RF-49), 025 (RF-7, RF-28, RF-32) |
| `src/igea_dgs/web/jobs.py` | Trabajos largos en cola, con progreso, cancelación y límite de tiempo por guion (P7). | 001 (RF-8), 011 (RF-39, RF-40) |
| `src/igea_dgs/web/readiness.py` | Puertas por alimentador antes de producir DGS. | 001 |
| `src/igea_dgs/web/reconstruction_service.py` | Diagnóstico y reconstrucción como trabajos de la web. | 001 (RF-8, RF-9) |
| `src/igea_dgs/web/runtime.py` | Comprobación del entorno que hace el lanzador de Windows y huella del código. | 001 (RF-27, RF-28) |
| `src/igea_dgs/web/services.py` | Las acciones de la interfaz, sin interfaz; conversión por sistema eléctrico (022:RF-47 a RF-51).; máxima por barra de SET y sus alimentadores en esa fecha; estructura del espacio | 001, 004 a 008, 011 (RF-12 a RF-16, RF-25, RF-27 a RF-30, RF-39 a RF-41, RF-68, RF-95, RF-121), 017 (RF-47 a RF-53, RF-59, RF-60, RF-65 a RF-67b, RF-71, RF-82, RF-93, RF-94, RF-104), 020 (RF-6, RF-13, RF-15, RF-25, RF-28), 021 (RF-26 a RF-34, RF-50, RF-51, RF-54, RF-57, RF-61, RF-64), 022 (RF-4, RF-37 a RF-44), 025 (RF-4, RF-8 a RF-11, RF-17, RF-20, RF-24, RF-28 a RF-33) |
| `src/igea_dgs/web/source_runs.py` | Custodia inmutable de los ficheros de cada ejecución. | 001 |
| `src/igea_dgs/web/source_scope.py` | Empresa y periodo de los paquetes VNR-GIS. | 001 (RF-2) |
| `src/igea_dgs/web/sources/__init__.py` | Reexportación temporal de `igea_dgs.sources`. | 002 (RF-21 la retira) |
| `src/igea_dgs/web/sources/vnr.py` | Reexportación temporal de `igea_dgs.sources.vnr`. | 002 (RF-21 la retira) |
| `src/igea_dgs/web/workspace.py` | Espacio de trabajo: entradas, opciones, salida de una sesión y obras de mejora sin aplicar. | 001, 011 (RF-95), 025 (RF-17) |

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
| `src/vnr_etl/connectors/sqlserver_vnr.py` | Copia de SQL Server (`.bak`) de VNR-GIS de cualquier concesionaria: restaura con su huella, lee las tablas por sus campos y arma el modelo canónico (tramos por su padre, SED, maniobras, bancos, tensión y CRS de la propia copia). | 023 |
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
| `tools/accept_digital_twin_in111_ta225.py` | Aceptación nativa del caso dorado del gemelo digital: dos lecturas en procesos nuevos, hechos del JSON `--esperado`, comprobaciones y episodio en el búfer. | 024 (RF-24 a RF-27) |
| `tools/accept_three_sources.py` | Aceptación universal y separada de MDB, TXT y VNR-GIS hasta ajuste, relectura y estudio nativos. | 001, 004, 006, 011 |
| `tools/ajuste_cabecera_pf.py` | Guion de DIgSILENT: ajusta un alimentador a su máxima de cabecera, en el escenario de «Sin proyecto»; propone e implementa transformadores nuevos para las SED fijas sobrecargadas; con una central, la crea en «Sin proyecto» y calibra por zonas; con varios `--plan`, calibra a la vez todos los alimentadores del proyecto; tabla de cambios en la red, lo original y lo nuevo; consigna de tensión de la fuente; pone los bancos que faltan en la troncal y recalibra.; central de barra de SET y cabeceras de la barra frente a su medidor | 006, 008, 011 (RF-18, RF-19, RF-51, RF-54), 014, 015, 020 (RF-60, RF-61), 021 (RF-35 a RF-44, RF-54 a RF-69), 022 (RF-41b, RF-44), 025 (RF-18) |
| `tools/apply_catalog_to_model.py` | Corrige las características eléctricas del modelo con el catálogo de fichas. | base |
| `tools/base_scenario.py` | Escenario base (año 0): lo construye, lo hace converger y lo diagnostica. | 005 |
| `tools/build_input_catalog.py` | Tabla de parámetros eléctricos en `input/` y auditoría de alimentadores. | base |
| `tools/build_system_grid.py` | Todos los alimentadores en una sola red, importada en PowerFactory. | base |
| `tools/cargas_pf.py` | Guion de DIgSILENT: demandas y cargas nuevas en un proyecto existente; también el módulo común de los guiones: cabecera del alimentador, leer su red para la troncal y partir un tramo con `Application.SplitLine` en la variación que graba; las cargas nuevas se conectan en el punto más cercano de la troncal.; mide la cabecera en el interruptor de cabecera de una barra de SET compartida | 004, 007, 008, 011 (RF-52 a RF-55), 016 (RF-2, RF-4, RF-16 a RF-19, RF-21, RF-22, RF-45 a RF-50), 022 (RF-22, RF-23) |
| `tools/casos_pf.py` | Guion de DIgSILENT: los casos «Caso base», «Sin proyecto» y «Con proyecto», cada uno con su escenario y sus variaciones; «Sin proyecto» solo desde el «Caso base» verificado; «Con proyecto» como copia de «Sin proyecto», también para las obras; lo hecho a mano en «Sin proyecto» pasa a «Con proyecto». | 011 (RF-1 a RF-16, RF-46 a RF-50; casos para RF-51 a RF-54), 014, 015, 016 (RF-12), 025 (RF-14 a RF-17, RF-21) |
| `tools/digital_twin_buffer.py` | Búfer de episodios desde la consola: listar, mostrar, validar, registrar y rehacer el índice, sin DIgSILENT. | 024 (RF-6, RF-8, RF-9) |
| `tools/digital_twin_entrenar.py` | Entrena el oráculo PINN/GNN en su propio proceso (la web lo lanza): reentreno si toca o forzado, promoción por puertas, respaldo en CPU si la GPU falla; un fallo no tumba la web. | 024 (RF-16, RF-39, RF-42) |
| `tools/digital_twin_snapshot_pf.py` | Guion de DIgSILENT de solo lectura: reabre el proyecto, activa el caso, ejecuta el flujo y devuelve tensiones, cargabilidad, cabeceras, pérdidas, islas, frontera, estados pedidos y huellas del trazado. | 024 (RF-2, RF-3, RF-27, RF-28) |
| `tools/escenarios_pf.py` | Guion de DIgSILENT: escenarios del gemelo en una copia del proyecto (desactivado antes de copiar), demanda escalada y tramos abiertos, resultados y grafo eléctrico con R, X y corriente nominal; restituye cada cambio y borra la copia. | 024 (RF-11, RF-40, RF-41) |
| `tools/estudios_pf.py` | Guion de DIgSILENT: un estudio en un caso, sin escalado por alimentador y sin aplicar lo que proponen los optimizadores; mide cada alimentador. Con `--guion`, lista o ejecuta los guiones DPL y Python del operador. En «Con proyecto», mide cada alternativa del informe con solo sus obras; guarda la geografía con barras, tipo y largo de cada tramo y los acoples, y el nodo de la red de cada banco. | 011 (RF-17, RF-20 a RF-22, RF-26, RF-27 a RF-30, RF-31, RF-33, RF-36, RF-38, RF-43 a RF-45, RF-49), 017 (RF-130, RF-131, RF-135) |
| `tools/check_pf_license.py` | Qué módulos de PowerFactory permite la licencia. | 005, 011, 012 (RF-4) |
| `tools/compare_schema.py` | Cabeceras de un DGS externo frente a un perfil de esquema. | base |
| `tools/convertir_grupos_mdb.py` | Varios alimentadores de una base en un DGS, importado y con flujo, a escala real por defecto. | base, 021 |
| `tools/fidelidad_seleccion.py` | Comprueba que una selección pasa entera del TXT al DGS. | 009 |
| `tools/linea_base_dgs.py` | Línea base de DGS para comprobar que una reorganización no cambia nada. | 001 (RF-14), 002 (RF-20) |
| `tools/obras_pf.py` | Guion de DIgSILENT de las obras de mejora: con `--bibliotecas`, alimentadores y tipos de las tres bibliotecas; copia de un tipo al proyecto; simular y aplicar con las reglas comunes (variación por obra, activación por caso, flujo, comprobación de «Sin proyecto»); banco de condensadores, reconectador, regulador, sección de cable, terna en la troncal y migración del alimentador a otra tensión; la troncal de las obras es la del camino más largo, leída en el caso de cada obra, sin `ComBbone`; enlace entre dos alimentadores en «Con proyecto» (tramos dentro de los límites con el flujo de antes, los dos puntos, partir tramos, línea recta con su trazado y seccionador abierto); migración a otra tensión de lo que queda aguas abajo de un nodo, calculado al construirla. | 011 (RF-56 a RF-60, RF-64 a RF-67, RF-69, RF-71 a RF-94, RF-96, RF-97, RF-99 a RF-103), 016 (RF-1, RF-2, RF-10 a RF-12, RF-26, RF-29, RF-30, RF-32 a RF-38, RF-40, RF-42, RF-43, RF-54 a RF-58, RF-60, RF-62) |
| `tools/pf_proyectos.py` | Proyectos de la carpeta de importación de DIgSILENT y sus alimentadores. | 005 |
| `tools/powerfactory_acceptance.py` | Puerta de aceptación: importa un DGS en PowerFactory, o adopta un proyecto existente, y verifica su «Caso base» frente al archivo original. | base, 010 (RF-6, RF-7), 015 |
| `tools/prueba_representacion.py` | Red, cargas y SED del TXT en una hoja de PowerFactory. | base |
| `tools/run_one_study.py` | Trabajador de PowerFactory: importa y mide, o ejecuta un estudio. | 005 |
| `tools/run_powerfactory_gate.bat` | Lanza `powerfactory_acceptance.py` con el intérprete de PowerFactory. | base |
| `tools/show_pf_diagram.py` | Abre en DIgSILENT el diagrama de un alimentador. | 005 |
| `tools/sistema_web.py` | Un sistema eléctrico de punta a punta por la web: espera lo que corre, convierte por sistema, importa en DIgSILENT, busca la máxima por barra de SET y calibra el sistema entero; retoma lo hecho y reintenta si la web corta. | 022 (RF-56), 025 (RF-25, RF-25b, RF-25c) |
| `tools/suggest_line_type_aliases.py` | Propone alias para tipos de línea sin ficha en el catálogo. | base |
| `tools/transformador_set_pf.py` | Guion de DIgSILENT: cargabilidad del devanado de la SET en el proyecto de transmisión, sin proyecto (el caso tal cual) y con proyecto (la carga de la barra más el Δ de cabecera de 4.2), un flujo por estado, con la carga restituida y comprobada; `--listar` da las cargas de barra con su transformador y los casos. | 017 (RF-65 a RF-68, RF-70) |
| `tools/transferencia_pf.py` | Guion de DIgSILENT: transferencia de carga entre dos alimentadores por su enlace, paso a paso en los dos sentidos, con la capacidad y el margen del enlace (`ComTransfer` o flujos sucesivos), sin dejar nada en el proyecto; un enlace entre barras de distinta tensión no se cierra ni se calcula. | 011 (RF-104 a RF-129), 016 (RF-62, RF-63) |
| `tools/pide_pf.py` | Guion de DIgSILENT: cada año del horizonte del PIDE con la demanda escalada por el `ComLdf`, diagnóstico de la norma con el alimentador y la tensión de cada problema; restituye el factor. | 024 (RF-51 a RF-53) |
| `tools/pf_cliente.py` | Envía un guion de DIgSILENT al proceso que se queda abierto y reescribe su salida. | 019 |
| `tools/pf_servidor.py` | Proceso que mantiene DIgSILENT abierto y atiende las órdenes de los guiones; se cierra a los 2 minutos sin órdenes. | 019 |
| `tools/verificar_pf.py` | Guion de DIgSILENT: convergencia del proyecto con lo activo. | 008 |

## `frontend/src/` — interfaz web

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `frontend/src/main.tsx` | Arranque de React. | 001 |
| `frontend/src/App.tsx` | Marco de la página: paneles, pestañas, resúmenes de trabajos. | 001, 008 (RF-1, RF-2) |
| `frontend/src/api.ts` | Cliente tipado de la API.; conversión por sistema eléctrico y máxima por barra | 001 (RF-12, RF-13), 011 (RF-42), 021 (RF-26, RF-34), 022 (RF-7, RF-39), 025 (RF-28) |
| `frontend/src/types.ts` | Tipos de las respuestas de la API. | 001, 011, 021, 025 (RF-4, RF-24, RF-28) |
| `frontend/src/clientesCatalogo.ts` | Estado del catálogo mensual de clientes: un solo libro activo e índice vigente antes de cruzar. | 004, 008, 025 (RF-10, RF-23) |
| `frontend/src/projectBinding.ts` | Vínculo del proyecto de DIgSILENT con su ejecución de origen: separa los bloqueos de las advertencias por cambios manuales. | 005 |
| `frontend/src/context.tsx` | Contexto común de la aplicación. | 001 |
| `frontend/src/useWorkspace.ts` | Espacio de trabajo, Registro en vivo y trabajos por WebSocket. | 001 |
| `frontend/src/styles.css` | Tokens y estilos, modo claro y oscuro; paleta de las series de la curva. | 001, 021 |
| `frontend/src/components/InputsPanel.tsx` | Entrada de datos: TXT, MDB y VNR-GIS. | 001 (RF-26) |
| `frontend/src/components/OptionsPanel.tsx` | Opciones de conversión. | 001 |
| `frontend/src/components/FeedersPanel.tsx` | Tabla de alimentadores y conversión.; conversión por sistema eléctrico con su zonal, aparte de unir, y el tipo de cada DGS unido | 001, 022 (RF-7) |
| `frontend/src/components/ReconstructionPanel.tsx` | Diagnóstico y reconstrucción. | 001 (RF-8, RF-9) |
| `frontend/src/components/Modules.tsx` | Pestañas de resultados, catálogo y sistema completo. | 001 |
| `frontend/src/components/CargasTab.tsx` | Pestaña «Cargas en DIgSILENT» en cuatro pasos; la distancia mínima de las cargas nuevas. | 004, 005, 008, 011 (RF-42, RF-98), 016 (RF-73) |
| `frontend/src/components/DemandaMedida.tsx` | Paso 2: libros de medición, máxima de cabecera (con la central térmica de un alimentador, en el mes de análisis o en un instante coincidente) y clientes con su nombre.; máxima por barra de SET | 004 (RF-57), 008, 013 (RF-11), 021 (RF-25 a RF-27, RF-50, RF-52), 022 (RF-39, RF-41), 025 (RF-22, RF-23, RF-34, RF-35) |
| `frontend/src/components/EstudiosPF.tsx` | Paso 4.2: estudios sobre la red calibrada, límites y resultados. | 011 (RF-24, RF-25, RF-35, RF-39, RF-68) |
| `frontend/src/components/GemeloPIDE.tsx` | Paso 5 de «Cargas en DIgSILENT»: planificar con el PIDE (CAPEX opcional, aplicar solas las obras que funcionan), tabla de obras con prioridad, estado y decisión del operador, formatos 01 a 15, aprendizaje activo del gemelo y episodios del proyecto. | 024 (RF-8, RF-45 a RF-48) |
| `frontend/src/components/GuionesPF.tsx` | Paso 4.2: guiones DPL y Python del operador, sus parámetros y su salida por caso. | 011 (RF-27 a RF-30) |
| `frontend/src/components/ObrasPF.tsx` | Paso 4.1: formulario de obras de mejora (también enlace, migración desde un nodo y sección de toda la troncal), bibliotecas de tipos, obras guardadas, simular y aplicar. | 011 (RF-56 a RF-95), 016 (RF-68 a RF-72) |
| `frontend/src/components/TransferenciaPF.tsx` | Paso 4.3: transferencia de carga entre dos alimentadores. | 011 (RF-104 a RF-123) |
| `frontend/src/components/InformesPF.tsx` | Paso 4.4: informe de estudio eléctrico y de factibilidad y punto de diseño con lo ya guardado por la web (flujos de 4.2, obras, cargas nuevas aplicadas, máxima de 2.2); formularios guardados en el servidor; libro de pérdidas subido o a mano; transformador de la SET a mano; huecos, descarga e informes generados. | 017 (RF-73 cambiado, RF-74 a RF-82, RF-89 a RF-94, RF-96, RF-100, RF-102 a RF-104, RF-125) |
| `frontend/src/components/AjusteCabecera.tsx` | Paso 2.4: ajuste a la máxima de uno o varios alimentadores; SED fijas sobrecargadas con su propuesta y el botón de transformadores nuevos; tabla de cambios en la red; tensión en la fuente; bancos que falten. | 006, 008, 020 (RF-62), 021, 025 (RF-24) |
| `frontend/src/components/CurvaCabecera.tsx` | Paso 2.4: curva del registro del medidor de cabecera, con el mes de la máxima sombreado y zoom por tramo; con varios alimentadores, una curva por cada uno en la misma gráfica; con central, sus curvas y la de la demanda. | 006 (RF-32 a RF-38), 021 (RF-17 a RF-24, RF-47 a RF-49) |
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
| `docs/ARQUITECTURA.md` | Arquitectura actual: capas de hecho, flujos, casos de PowerFactory, carriles y mapa de specs. | vigente |
| `docs/VERIFICACION_SPECS_2026-10-14.md` | Verificación de cada spec, RF por RF y tarea por tarea. | histórico |
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
