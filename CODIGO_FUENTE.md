# Índice del código fuente

Cada fichero de `src/` y de `tools/`, qué hace y qué spec lo rige. La suite comprueba
que no falta ninguno y que no sobra ninguno (`tests/test_inventario.py`, spec 009): un
fichero nuevo entra aquí en el mismo cambio que lo crea.

El motor anterior al desarrollo por specs, que aquí se marcaba «base», lo rige desde el
2026-10-29 la spec 034 (motor base y contrato universal de fuentes), además de la
constitución y 001:RF-14 (DGS idéntico byte a byte); su diseño histórico está en
`docs/superpowers/`. La spec 002 moverá estos módulos a capas.

## `src/convertersmartgrid/` — motor de conversión

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `src/convertersmartgrid/__init__.py` | Paquete del motor y su versión. | 034 (RF-1) |
| `src/convertersmartgrid/access.py` | Lector de la base Access de CYMDIST (`.mdb`), la segunda vía de entrada. | 034, 001 |
| `src/convertersmartgrid/ajuste_cabecera.py` | Reparto y cuadre de las demandas a la máxima de cabecera, sin DIgSILENT; por zonas con una central en el troncal; cuadre conjunto de los alimentadores de un proyecto en los mismos flujos; cuántos bancos faltan y dónde. | 006, 021 (RF-33, RF-40 a RF-45, RF-54 a RF-58, RF-64 a RF-66), 035 (RF-2 a RF-9), 035 (RF-28 a RF-30), 041 (RF-1 a RF-7) |
| `src/convertersmartgrid/batch.py` | Conversión de uno, varios o todos los alimentadores, en serie o en paralelo.; la red unida por zonal y SET con su informe, aperturas y oráculo | 034, 001, 022 (RF-7, RF-25, RF-34) |
| `src/convertersmartgrid/capacidades.py` | Capacidades, grupo de conexión y tensión de baja de transformadores y líneas del DGS original, y su comparación con lo leído en DIgSILENT. | 015 |
| `src/convertersmartgrid/cargas_pf.py` | Lectura de los libros de demandas y cargas nuevas, y plan para DIgSILENT. | 004, 007, 008, 016 (RF-73), 030 (RF-13, RF-14) |
| `src/convertersmartgrid/valle.py` | El valle de un alcance desde la medición: limpieza de lo dudoso con su motivo, energía de sus medidores, inicio y duración por búsqueda exacta, por año; punto para la escalera, plan de la calibración a valle y la frase del informe. | 073 |
| `src/convertersmartgrid/escalera_optima.py` | Escalera optimizada de obras: variantes en el orden bancos, regulador, terna y sección con sus combinaciones, criterio de «no empeorar» por sorteo, sorteos de la curva de cabecera con semilla, costo anual con el CAPEX y elección. | 025 (RF-44, RF-49 a RF-60), 073 (RF-17 a RF-20, RF-24) |
| `src/convertersmartgrid/catalogo_reguladores.py` | Reguladores de tensión de catálogo (Eaton VR-32, 50 Hz): unidad por tensión del sistema y por corriente, y los datos de su `TypVoltreg`. | 025 (RF-59, RF-60) |
| `src/convertersmartgrid/carpeta_pf.py` | Carpeta de DIgSILENT donde quedan los proyectos importados; buscar un proyecto sin activarlo. | 005, 011 (RF-91) |
| `src/convertersmartgrid/catalog.py` | Catálogo de parámetros eléctricos: tabla de entrada y auditoría del modelo. | 034 (RF-7), 053 |
| `src/convertersmartgrid/catalog_data.py` | Datos de fabricante y de norma para los parámetros eléctricos. | 034 (RF-7) |
| `src/convertersmartgrid/catalog_merge.py` | Completa el catálogo de equipos cuando el export llega incompleto. | 034, 001 |
| `src/convertersmartgrid/catalog_resolution.py` | Resolución de equipos por evidencia, sin renombrar los códigos de origen. | 001 (RF-18) |
| `src/convertersmartgrid/cli.py` | Orden `convertersmartgrid`: `list`, `convert` y `web`.; `--por-sistema [ZONAL]` y `--estructura`, aparte de `--unir` | 001 (RF-1, RF-2), 022 (RF-4, RF-7, RF-47 a RF-49) |
| `src/convertersmartgrid/combine.py` | Une todos los alimentadores en una sola red; con la estructura de la empresa, la cuelga de sus SET: barra por SET y tensión e interruptor de cabecera por alimentador. | 034, 022 (RF-10 a RF-13, RF-17 a RF-19, RF-21) |
| `src/convertersmartgrid/coordenadas.py` | Completa las coordenadas que faltan con el grafo de la red. | 034 (RF-11) |
| `src/convertersmartgrid/datos_empresa.py` | Libro de la empresa de la confiabilidad y la capacidad: hojas, columnas y unidades validadas con hoja, fila y columna; clases de elemento y fila por tipo; telemandados; bancos con su anualidad; hojas que faltan y los estudios que bloquean; plantilla sin cifras. | 012 (RF-6 a RF-18, RF-62 a RF-66) |
| `src/convertersmartgrid/dataset.py` | Lector de los TXT (RED, CARGA, BD_Equipo), en las dos disposiciones. | 034 (RF-1, RF-5) |
| `src/convertersmartgrid/demanda_medida.py` | Máxima de cabecera por medidor y clientes importantes con su SED; el registro de las 00:00 conserva su hora; máxima de demanda con una central en el troncal; la del mes de análisis o el registro de un instante coincidente; el nombre del cliente.; medidores de barra, sus barras de SET y la máxima de la suma de sus transformadores; periodo de un año entero, libros de cabecera y de clientes en subcarpetas de año y mes del nombre por una regla general | 004 (RF-22 a RF-45, RF-56, RF-57), 013 (RF-11), 021 (RF-28 a RF-34, RF-50, RF-51, RF-53), 022 (RF-37 a RF-46), 025 (RF-1, RF-3 a RF-7, RF-12, RF-13, RF-25b, RF-25c, RF-28 a RF-30), 038 (RF-1 a RF-4, RF-6), 039 (RF-3, RF-4), 060 (RF-5) |
| `src/convertersmartgrid/libros_por_anio.py` | Libros de demanda por año de medición: árbol de libros con su año (carpeta de cuatro cifras a cualquier altura) y su ruta relativa, años disponibles y libros de un periodo, sin abrirlos | 025 (RF-1 a RF-3, RF-7 a RF-9, RF-26, RF-27) |
| `src/convertersmartgrid/digital_twin/curva.py` | Episodios del gemelo por sistema eléctrico frente a los 30/10/10 (reparto fijo por la huella de cada episodio) y curva de aprendizaje que dice si un 20 % más mejora menos del 5 %. | 027 (RF-53) |
| `src/convertersmartgrid/digital_twin/hiperparametros.py` | Búsqueda de hiperparámetros del gemelo con Optuna (TPE y poda por mediana), con presupuesto de ensayos y tiempo, evaluada solo en validación; guarda todos los ensayos. | 027 (RF-7), 060 (RF-2) |
| `src/convertersmartgrid/digital_twin/__init__.py` | Paquete del gemelo digital: episodios, búfer y captura, sin PowerFactory ni PyTorch. | 024 |
| `src/convertersmartgrid/digital_twin/episode.py` | Contrato del episodio: clase y caso, fuente y proyecto, resultados del flujo (balance, pérdidas, cargabilidad, tensiones, confiabilidad, o el motivo de su ausencia), obras con su alternativa del PIDE e indicadores, artefactos; JSON canónico, huella SHA-256 y validación con la ruta del campo que falla. | 024 (RF-1, RF-2, RF-4, RF-6, RF-7, RF-9, RF-28, RF-32) |
| `src/convertersmartgrid/digital_twin/escenarios.py` | Matriz de escenarios (demanda escalada y N-1), familia topológica y partición fija, elección por incertidumbre o diversidad y presupuesto de licencia del aprendizaje activo. | 024 (RF-11, RF-12, RF-40, RF-41) |
| `src/convertersmartgrid/digital_twin/auditoria.py` | Auditoría del dataset de cada modelo antes de entrenar: muestras, redes distintas, nodos, columnas, fracción etiquetada, rangos, no finitos (no se entrena), tensiones fuera de rango (se marcan, no se excluyen), ramas en el tope de acoplador y parámetros frente a etiquetas; órdenes reales del asistente. | 027 (RF-29 a RF-34) |
| `src/convertersmartgrid/digital_twin/buffer.py` | Búfer local e inmutable de episodios: un JSON por huella, escritura atómica e idempotente, colisión detectada, índice SQLite reconstruible con consultas por proyecto, alimentador, caso, clase, acción, fuente y versión, cuarentena de manifiestos ilegibles; sin borrado. | 024 (RF-6 a RF-10) |
| `src/convertersmartgrid/digital_twin/capture.py` | Ensamblaje del episodio desde el contexto firmado, el resultado del guion y la lectura tras reabrir; lectura que falta, de otro proyecto o con el trazado manual cambiado, a cuarentena; simulación aceptada como contrafactual. | 024 (RF-1 a RF-4, RF-9) |
| `src/convertersmartgrid/digital_twin/evaluacion.py` | Evaluación por caso: «Caso base» y «Sin proyecto» con las violaciones como diagnóstico (y el cuadre de la calibración), «Con proyecto» contra la norma de su sistema del perfil (tensión, cargabilidad, transformadores NTP 370.400) y frente a «Sin proyecto» en pérdidas y confiabilidad. | 024 (RF-4, RF-5, RF-26, RF-29 a RF-31) |
| `src/convertersmartgrid/digital_twin/integration.py` | Captura tras cada acción nativa de la web: plan de lectura, norma de cada alimentador por su sistema y límites más estrictos, referencia del último «Sin proyecto» aceptado, obras al PIDE, aviso en el Registro y cuarentena sin repetir la acción; interruptor `CSG_TWIN_CAPTURA`. | 024 (RF-1, RF-27, RF-31, RF-32) |
| `src/convertersmartgrid/digital_twin/native_snapshot.py` | Identidad estable de un objeto de DIgSILENT, huella SHA-256 de un trazado e islas por tramos cerrados, sin suponer red radial. | 024 (RF-2, RF-3) |
| `src/convertersmartgrid/digital_twin/oraculo.py` | Oráculo PINN/GNN (PyTorch, GPU si la hay): grafo por unidad, red de grafos sobre la física mallada con pérdida física de balance por barra eléctrica, conjunto con incertidumbre, fuera de dominio, estado eléctrico (flujos, pérdidas, cargabilidad), registro de modelos con promoción por puertas, vuelta al anterior, deriva y reentreno, evaluación del aprendizaje por partición; flujo mallado y barrido radial con el mismo contrato; orden de obras candidatas. | 024 (RF-12 a RF-19, RF-23, RF-35, RF-36, RF-38 a RF-40, RF-42 a RF-44, RF-64 a RF-66, RF-74), 060 (RF-1, RF-2, RF-3) |
| `src/convertersmartgrid/digital_twin/flujo.py` | Flujo de carga físico por matriz de admitancias dispersa, con lazos: acopladores fusionados en una barra, factorización LU una sola vez, punto fijo Z-bus, consigna de las fuentes sin refactorizar, pérdidas y no convergencia dicha. | 024 (RF-64 a RF-66) |
| `src/convertersmartgrid/digital_twin/evolutivo.py` | Algoritmo genético, NSGA-II y evolución diferencial autoadaptativa (jDE), deterministas con su semilla; bancos de condensadores al menor coste con frente inversión–pérdidas y sobredimensionadas, reconfiguración radial por maniobras, consigna de cabecera y bancos del PIDE afinados con la red del gemelo. | 024 (RF-67 a RF-73), 044 (RF-6) |
| `src/convertersmartgrid/asistente/ordenes_fijas.py` | Las 200 órdenes fijas del asistente escritas por el maestro (Claude), de todas las tareas y distintas de las plantillas, con su huella y su reparto 160/40. | 027 (RF-65 a RF-67) |
| `src/convertersmartgrid/asistente/orquestador.py` | El proyecto entero desde el espacio, etapa por etapa por las rutas de la web (fuente, sistema, «Caso base», cargas nuevas, obras, estudios, PIDE, informe), con punto de control y reanudación sin repetir. | 027 (RF-43, RF-44), 061 (RF-5, RF-6, RF-7) |
| `src/convertersmartgrid/asistente/ejemplos_pide.py` | Ejemplos del agente desde el corpus PIDE entregado: por artículo sus evidencias en cada PIDE (por la ruta y el texto), por formato F01 a F15 sus hojas y columnas, y las secciones de los informes 4.1 y 4.2; contexto, no norma. | 027 (RF-47, RF-48, RF-50) |
| `src/convertersmartgrid/asistente/destilacion.py` | Destilación del modelo local de Ollama (maestro) al Transformer de órdenes: k votos con temperatura por orden sin etiqueta, filtro por acuerdo y registro. | 027 (RF-56, RF-57, RF-59, RF-61, RF-62) |
| `src/convertersmartgrid/asistente/__init__.py` | Paquete del asistente de órdenes en lenguaje natural. | 026 |
| `src/convertersmartgrid/asistente/almacen.py` | Dónde guarda el asistente lo suyo, en la máquina: registros JSONL de solo añadir (órdenes, ejemplos, decisiones, avisos, internet, suite) y JSON atómicos. | 026 (RF-28, RF-31) |
| `src/convertersmartgrid/asistente/tareas.py` | Catálogo de tareas: datos tipados, si escribe (confirmación), modo (consulta, trabajo, proceso), función de la web que lo hace y plantillas de frases; lista de herramientas para Ollama. | 026 (RF-2, RF-8 a RF-11) |
| `src/convertersmartgrid/asistente/senales.py` | Recompensas y penalizaciones de cada orden, pares de preferencia para DPO, memoria de reflexiones y contexto de órdenes parecidas para Ollama. | 027 (RF-35 a RF-37, RF-39) |
| `src/convertersmartgrid/asistente/sinteticos.py` | Órdenes sintéticas por plantilla con los nombres reales del espacio y erratas solo en las palabras de la plantilla; normalización sin tildes que conserva posiciones; subtipos de estudio por defecto. | 026 (RF-21) |
| `src/convertersmartgrid/asistente/transformer.py` | Transformer propio por caracteres: tarea y datos (etiquetas por carácter decididas por palabra), entrenamiento en GPU, prueba fija, registro, puertas, promoción y vuelta al anterior. | 026 (RF-2, RF-19, RF-20) |
| `src/convertersmartgrid/asistente/ollama.py` | Cliente del modelo local de Ollama: solo direcciones de la máquina, tareas como herramientas con respuesta JSON, respuestas con cita y embeddings; modelo elegido por la medida. | 026 (RF-3, RF-5, RF-17, RF-18) |
| `src/convertersmartgrid/asistente/interprete.py` | Intérprete híbrido: Transformer, si duda Ollama, si duda pregunta; reglas fijas de periodo, ruta y número. | 026 (RF-2 a RF-4) |
| `src/convertersmartgrid/asistente/plan.py` | Del texto interpretado al plan: datos contrastados con lo que existe (parecido, tomados del texto), lo que falta, dudas y razonamiento; un grupo ya convertido al importar. | 026 (RF-4, RF-6, RF-7, RF-8), 078 |
| `src/convertersmartgrid/web/asistente_operacion.py` | Lo que cada tarea del asistente necesita del espacio, comprobado antes de ofrecer confirmar: calibración, libros, costeo, formulario y las formas que se leen de la orden. | 070 (RF-2 a RF-15, RF-29, RF-30, RF-58) |
| `src/convertersmartgrid/web/asistente_consultas.py` | Las consultas del asistente sin escribir ni abrir DIgSILENT: qué dato se pide, su fuente, «no lo encuentro» y por qué un estudio no está disponible. | 070 (RF-40 a RF-49) |
| `src/convertersmartgrid/asistente/prueba_sellada.py` | La prueba sellada de las órdenes desde la 070: seis frases por tarea, un vocabulario propio y una huella fija; declara cómo se generó y no se ajusta mirándola. | 070 (RF-69 a RF-71) |
| `src/convertersmartgrid/asistente/ejecutor.py` | Ejecuta el plan confirmado por las rutas y trabajos de la web, paso a paso, esperando cada trabajo; entregables del resultado. | 026 (RF-10, RF-12) |
| `src/convertersmartgrid/asistente/clasificador.py` | Clasificador de informes en dos niveles (estudio o factibilidad, y subtipo del perfil) sobre el mismo codificador; aprende de los informes generados y de las correcciones. | 026 (RF-13 a RF-16) |
| `src/convertersmartgrid/asistente/indice.py` | Índice local del proyecto (CODIGO_FUENTE, RF de las specs, docstrings, manual, constitución), BM25 y vectores fusionados por posición, cálculo de vectores por lotes, reconstrucción por huella y respuestas con citas comprobadas, sus métodos o «No lo sé», con la abstención calibrada. | 026 (RF-17, RF-18), 047 (RF-3, RF-21 a RF-26, RF-28 a RF-33, RF-37) |
| `src/convertersmartgrid/asistente/vigilancia.py` | Vigilancia de trabajos (fallos, tiempos, colas, reintento del 4002), modelos, calidad de resultados y suite nocturna con el RF de cada fallo. | 026 (RF-22 a RF-25) |
| `src/convertersmartgrid/asistente/mejoras.py` | Mejoras en una rama aparte (git worktree) con spec y pruebas y su suite; nunca fusiona ni sube; decisiones auditables; fichas de librerías. | 026 (RF-26 a RF-28, RF-32) |
| `src/convertersmartgrid/asistente/internet.py` | Búsquedas en GitHub, PyPI y arXiv con el filtro de identificadores de la red y rutas; cada consulta registrada, las bloqueadas sin su texto. | 026 (RF-29 a RF-32) |
| `src/convertersmartgrid/digital_twin/temporal.py` | Gemelo temporal: GRU de las curvas de cabecera (estacional sin PyTorch), GRU multihorizonte para competir en el pronóstico, métricas, desviaciones por instante y alimentador, pseudo-medidas por kVA con intervalo e instante crítico coincidente. | 024 (RF-20 a RF-22, RF-37), 046 (RF-1, RF-13, RF-15), 060 (RF-6) |
| `src/convertersmartgrid/crecimiento.py` | Tasa anual de crecimiento de la demanda de cada alimentador desde la medición de cabecera: máximas de los meses comunes del primer y el último año, mediana para los demás. | 029 (RF-1 a RF-3, RF-5, RF-7) |
| `src/convertersmartgrid/dgs.py` | Escritor DGS: tablas, FID, cubículos, maniobras, capa gráfica y trazado GPS de las líneas; la barra de una SED sola va dentro de ella.; con la estructura, una red y un diagrama por zonal, la SET como subestación con sus barras, una red externa por barra y el ElmFeeder en el interruptor de cabecera | 034, 010 (RF-1 a RF-4), 011 (RF-128), 021 (RF-12), 022 (RF-6 a RF-16), 054 |
| `src/convertersmartgrid/economia.py` | Datos de la evaluación técnico-económica (`ComTececo`). | 004 |
| `src/convertersmartgrid/enlaces.py` | Puntos de enlace de la red unida con sus SET y caminos cerrados (entre SET, entre alimentadores, anillos): abre la maniobra más lejana de su fuente o, si no hay, un punto abierto en el tramo más lejano, hasta dejarla radial. | 022 (RF-26, RF-27, RF-29 a RF-31, RF-34) |
| `src/convertersmartgrid/escaneo.py` | Reglas del escaneo de un alimentador antes de recalibrar: de quién es cada generador, banco y variación por los prefijos del conversor, resumen y barra de la central. | 028 (RF-3 a RF-5, RF-7, RF-11, RF-12) |
| `src/convertersmartgrid/estructura.py` | La estructura de la empresa: zonales, SET (con sus siglas) y alimentadores con su sistema eléctrico, sector típico y norma; del perfil o de la tabla en Excel; qué SET tiene cada alimentador de la entrega, los «Sin SET», los que faltan y lo que se omite sin redes. | 022 (RF-1 a RF-6, RF-19, RF-20, RF-25b) |
| `src/convertersmartgrid/estudios_pf.py` | Estudios sobre los casos «Sin proyecto» y «Con proyecto», sin DIgSILENT: qué estudios se ofrecen (los de la 012 según el libro de la empresa y la licencia), límites del perfil, violaciones, diferencia y ficheros de resultados. | 011 (RF-23, RF-24, RF-32 a RF-35, RF-37), 012 (RF-1, RF-4, RF-19) |
| `src/convertersmartgrid/estudios_red_pf.py` | Resultados de confiabilidad y capacidad sin DIgSILENT: índices por alimentador y su comprobación por cargas, ENS total y diferencias, aportes, mejora de los reconectadores, capacidad por nodo con su motivo, margen PV de la ventana de salida, bancos con su coste, comprobación de estado y filas de los ficheros. | 012 (RF-25, RF-30 a RF-33, RF-39, RF-47 a RF-49, RF-52, RF-56, RF-57, RF-59 a RF-61, RF-66 a RF-68, RF-70 a RF-72) |
| `src/convertersmartgrid/export_tables.py` | DGS a Excel multihoja o TSV. | 034 (RF-14) |
| `src/convertersmartgrid/feeder_metadata.py` | Procedencia por alimentador de los objetos de una red conjunta.; la red externa de una barra de SET, una vez con sus alimentadores | 034, 022 (RF-11) |
| `src/convertersmartgrid/geography.py` | Del CRS de origen a WGS84; geometría de nodos y tramos y su validación. | 034, 001 (RF-6) |
| `src/convertersmartgrid/identify.py` | Reconoce cada TXT por su contenido, no por su nombre, y a qué fuente (TXT, Access o VNR-GIS) pertenece un fichero. | 034 (RF-2), 059 (RF-3) |
| `src/convertersmartgrid/informe_docx.py` | Escribe en Word los informes de estudio eléctrico y de factibilidad como esquemas generales sobre el modelo de la empresa: de él solo la forma (primera sección con su cabecera, pie y estilos; cuerpo vaciado; n.º, referencia y total de páginas fijos sustituidos); orden de Casa Blanca y de EMAPICA, datos de la fuente, tensión por fase o trifásica, leyendas, figuras de DIgSILENT, obras por etapa o por alternativa (tabla de trechos del conductor, cuadro comparativo, bancos existentes por nodo), punto de diseño, pérdidas, transformador de la SET y conclusiones, con coma decimal; lo que falta queda vacío y su motivo en el JSON; escritura atómica. Abre modelos que Word dejó con imágenes rotas. | 017 (RF-2 a RF-9, RF-13, RF-15 a RF-25, RF-27, RF-31, RF-44 a RF-46, RF-50, RF-52, RF-59, RF-62, RF-106, RF-113, RF-114, RF-118, RF-120, RF-122, RF-128, RF-132 a RF-135) |
| `src/convertersmartgrid/libro_informe.py` | El libro Excel de cada informe, relleno desde el modelo de la empresa con el plano de su perfil | 066 |
| `src/convertersmartgrid/libros_informe.py` | Libro de pérdidas de la empresa (sistema eléctrico, % reconocidos en potencia y energía, precio de compra), buscado por los nombres de hojas y columnas del perfil, con el hueco del alimentador que no está; tabla de costes de bancos, reguladores y precio de la energía, cada fila con fuente, fecha y marca «referencial», y lo que falta para las etapas 2 y 3. | 017 (RF-39b a RF-39e, RF-40c, RF-62 a RF-64) |
| `src/convertersmartgrid/documentos_solicitud.py` | PDF del solicitante (carta, oficio, ficha del punto de diseño): capa de texto por página y, en las escaneadas, OCR con Tesseract y la imagen binarizada con OpenCV o Pillow; fecha, asunto, cliente, ubicación, potencias, tensión, NIS, expediente, SET, alimentador y punto de diseño, la propuesta para la solicitud de 4.4.2 con el fichero de cada dato y los antecedentes de 4.4.1 en orden de fecha. | 017 (RF-136 a RF-141) |
| `src/convertersmartgrid/informes.py` | Informes de estudio eléctrico y de factibilidad sin DIgSILENT: qué toman del perfil de empresa (modelos, banda y umbral, bandas de coloreado, proyecto de transmisión) y qué falta para generar cada tipo; casos y etapas medidos (contrato JSON con el guion), etapa recomendada, alternativas de obras y trechos continuos del cambio de conductor, pérdidas anuales con las fórmulas del libro de la empresa, veredicto de factibilidad y redacción de análisis, antecedentes y conclusiones. | 017 (RF-4, RF-5, RF-13 a RF-22, RF-31, RF-33, RF-34, RF-43, RF-50, RF-54 a RF-60, RF-71, RF-72, RF-107, RF-108, RF-115, RF-121, RF-122, RF-128, RF-129, RF-132, RF-134) |
| `src/convertersmartgrid/inventory.py` | Inventario detallado de un dataset cargado. | 034 (RF-28) |
| `src/convertersmartgrid/loads.py` | Lector de libros de cargas por SED (columnas, potencia y FP), que usa `cargas_pf.py`. | 004 |
| `src/convertersmartgrid/model.py` | Modelo eléctrico de un alimentador; en modo estricto no inventa tipos. | 034 (RF-9, RF-10) |
| `src/convertersmartgrid/naming.py` | Nombres y selectores de alimentador; sufijo de tensión de los tipos, el mismo para el DGS y las obras. | 034, 011 (RF-61) |
| `src/convertersmartgrid/native_action.py` | Contexto firmado fuente–proyecto–alimentadores y vocabulario común de resultados para toda acción nativa. | 004, 006, 011 |
| `src/convertersmartgrid/obras_pf.py` | Obras de mejora sin DIgSILENT: modelo y validación de cada obra (lo de «Sin proyecto» pasa a «Con proyecto»; enlace y migración solo en «Con proyecto»), nombres de variación y de copias de tipo, datos e igualdad de tipos, resumen de cada tipo, plan de la simulación (sección de toda la troncal, enlace entre alimentadores, migración de lo que queda aguas abajo de un nodo) y comprobación de «Sin proyecto». | 011 (RF-56, RF-59, RF-61 a RF-65, RF-69, RF-85, RF-94); 016 (RF-6 a RF-9, RF-11, RF-13, RF-14, RF-23 a RF-25, RF-31, RF-38 a RF-41, RF-51 a RF-59, RF-61, RF-65, RF-66), 042 |
| `src/convertersmartgrid/oraculo.py` | Flujo independiente con pandapower antes de escribir el DGS; sobre la red unida entera, con una isla por barra de SET, su veredicto por SET y zonal y, si una no converge, su barra más débil y su transformador más cargado; si no converge por demanda de relleno o mayor que su SED, busca el factor por kVA con que converge. | 034, 022 (RF-28, RF-32, RF-33), 057 (RF-1, RF-3, RF-6) |
| `src/convertersmartgrid/optimizacion_oraculo.py` | «Con proyecto» optimizado con el flujo del gemelo: obras sobre el grafo, búsqueda bayesiana (Optuna), frente de Pareto (NSGA-II), sorteos de Markov y reparto de Shapley; DIgSILENT confirma. | 052, 073 (RF-19, RF-21 a RF-23) |
| `src/convertersmartgrid/pide.py` | Metodología del PIDE (RM 428-2017-MEM/DM): proyección y densidad de carga por cuadrículas de la Tabla N.º 2, diagnóstico con su causa (caída, FP, conductor, transformador, isla, sobretensión, pérdidas), año de incumplimiento, plan por etapas sin adelantar obras y formatos 01 a 15 en Excel. | 024 (RF-49 a RF-53, RF-60 a RF-63) |
| `src/convertersmartgrid/estudio_planeamiento.py` | Estudio de planeamiento: del año de presentación, cada 4 años, salen el año 00 y los años de largo plazo y del PIDE. | 072 |
| `src/convertersmartgrid/costos_fuentes.py` | Costos oficiales: contrato de fuente, lector del SICODI público y cruce por código, tensión, estructura y sector típico. | 072 |
| `src/convertersmartgrid/formatos_pide.py` | Los formatos 01 a 15 de un estudio con cada hueco nombrado y su motivo. | 072 |
| `src/convertersmartgrid/informes_planeamiento.py` | Los entregables de un estudio, un Word ligero por módulo, desde un mismo cálculo. | 072 |
| `src/convertersmartgrid/madrl_obras.py` | Entorno multiagente de obras, sus controles, su fidelidad contra DIgSILENT y la puerta del aprendizaje. | 074 |
| `src/convertersmartgrid/madrl_politica.py` | Política GATv2 compartida entre agentes, con crítico central y PPO, del piloto MADRL. | 074 |
| `src/convertersmartgrid/metrados.py` | Metrados por código desde el modelo de la red, y su valoración con costos oficiales. | 072 |
| `src/convertersmartgrid/proyeccion_mercado.py` | Proyección anual por sistema desde el Formato 01: métodos comparados contra lo ocurrido, sin mirar el futuro. | 072 |
| `src/convertersmartgrid/pide_economia.py` | Evaluación económica y priorización del PIDE: libro CAPEX por nombres del perfil (sin datos personales), anualidad, costo anual, VAN y TIR del art. 14, flujo privado con el pliego tarifario y la tasa privada, priorización del art. 15 con obras sobredimensionadas, y la propuesta con la obra de la spec 011 de lo que se construye solo. | 024 (RF-33, RF-34, RF-45 a RF-47, RF-54 a RF-59), 073 (RF-28, RF-29) |
| `src/convertersmartgrid/pide_dataset.py` | Corpus PIDE universal desde un expediente de la empresa en solo lectura: custodia, calidad y fragmentos de texto. | 024 (diseño `docs/superpowers/specs/2026-10-25-dataset-pide-universal-pideelor-design.md`) |
| `src/convertersmartgrid/perfil_empresa.py` | Perfil de empresa: CRS de origen, patrón de las SED de medición, escala del diagrama y forma de los alimentadores, fuera del código; hereda de `config/perfiles/`; fichas de transformadores de SED; tamaño de banco por tensión (021:RF-65); centrales térmicas por alimentador; uno o varios patrones de nombre de los libros de clientes. | 002 (RF-31 a RF-37), 020 (RF-29 a RF-31), 021 (RF-27), 025 (RF-6b) |
| `src/convertersmartgrid/mapa_informe.py` | Imágenes del informe de estudio (ubicación, tensión, cargabilidad y detalle de las obras) con el GPS y los resultados del flujo de DIgSILENT; conductor nuevo y bancos resaltados con rótulos que no se pisan. | 017 (RF-11b, RF-116, RF-133) |
| `src/convertersmartgrid/pf_arnes.py` | Arnés de DIgSILENT: turno del motor de la máquina, conexión común con reintento, caso restituido y proceso que se queda abierto. | 019, 064 |
| `src/convertersmartgrid/pf_estado.py` | Foto del estado de DIgSILENT antes de una orden del servidor (caso, hora, escenario, variaciones) y su restitución si la orden falla. | 064 |
| `src/convertersmartgrid/powerfactory_env.py` | Dónde está la API de PowerFactory y qué intérprete la carga; cierra los guiones de PowerFactory huérfanos y corta un guion con sus hijos. | 034 (RF-29) |
| `src/convertersmartgrid/powerfactory_binding.py` | Vínculo auditable entre ejecución fuente, DGS, inventario releído y proyecto nativo aceptado, con el estado del «Caso base» de cada alimentador. | 004, 006, 011, 015, 078 |
| `src/convertersmartgrid/powerfactory_metadata.py` | Procedencia del conversor en los objetos de PowerFactory, y la lectura única del flujo y su clasificación. | 034 (RF-21), 078 |
| `src/convertersmartgrid/preview.py` | Vista previa georreferenciada del modelo. | 034 (RF-14) |
| `src/convertersmartgrid/puentes.py` | Funde los tramos puente de CYMDIST en vez de modelarlos como líneas; su equipo pasa al extremo de la línea vecina si cabe. | 034, 021 |
| `src/convertersmartgrid/reconstruction.py` | Contrato de la reconstrucción auditable del dataset. | 001 (RF-17 a RF-22) |
| `src/convertersmartgrid/reconstruction_pipeline.py` | Reconstrucción de una selección de alimentadores, sin estado de la web. | 001 (RF-8, RF-9) |
| `src/convertersmartgrid/reconstruction_topology.py` | Reconstrucción determinista de la topología. | 001 (RF-17) |
| `src/convertersmartgrid/reglas.py` | Reglas que se aplican a todo alimentador, venga de TXT o de base; patrón de SED de medición y escala del perfil de empresa.; no cuenta como de la entrada los interruptores de cabecera ni los puntos abiertos; la corrección del oráculo, informada y cuadrada en la completitud | 034, constitución P5, 002 (RF-33), 021 (RF-9), 022 (RF-12, RF-31), 032 (RF-1, RF-2), 057 (RF-1, RF-4) |
| `src/convertersmartgrid/schema.py` | Perfiles de esquema DGS versionados. | 034 (RF-13), 054 |
| `src/convertersmartgrid/source_contract.py` | Contrato canónico y evidencia de auditoría compartidos por TXT, MDB y VNR-GIS. | 001, 004, 006 |
| `src/convertersmartgrid/schemas/digital_twin_episode_v1.schema.json` | Esquema JSON publicado del episodio del gemelo digital, igual al contrato de `digital_twin/episode.py`. | 024 (RF-7) |
| `src/convertersmartgrid/schemas/pf21_dgs_1_8_4.json` | Perfil DGS genérico de PowerFactory. | 034 (RF-13) |
| `src/convertersmartgrid/sed_potencia.py` | Lleva al tamaño normalizado las SED cuya carga supera su transformador; reconoce la demanda de relleno o fuera de escala y la lleva a kVA × factor con FP 0,98. | 034 (RF-32), 057 (RF-2, RF-3) |
| `src/convertersmartgrid/cabecera_ancha.py` | Medición de cabecera entregada a lo ancho (una columna por alimentador, fecha y hora en dos columnas, hojas de activa y reactiva) y tablas de máximas mensuales por salida, escritas en el formato que lee la calibración: un libro por año con una hoja por código y el libro de medidores. | 051 |
| `src/convertersmartgrid/set_nueva.py` | SET nueva para las cargas que la red existente no atiende: potencia de diseño a la vida útil con la tasa de la 029 y el factor de seguridad, módulo PIT del libro CAPEX que la cubre y ubicación de Weber con sorteos de crecimiento por zona. | 042 (RF-5, RF-7 a RF-9) |
| `src/convertersmartgrid/studies.py` | Qué estudios de PowerFactory se pueden correr y qué dato falta para cada uno. | 034 (RF-26), 012 (RF-1) |
| `src/convertersmartgrid/study.py` | Estudio de CYMDIST (`.zxst`/`.xst`), entrada opcional que filtra la selección. | 034 (RF-3) |
| `src/convertersmartgrid/trafomix.py` | Equipos de medición en MT que la base registra como SED, con el patrón del perfil de empresa; quita el fusible que solo llevaba a uno. | 034, 002 (RF-33), 021 (RF-7) |
| `src/convertersmartgrid/transferencia_pf.py` | Transferencia de carga sin DIgSILENT: pasos del camino y carga transferida, viabilidad y elemento que limita, máximo por seccionador y por nodo, fichero, factor máximo por bisección y margen del enlace. | 011 (RF-110 a RF-117, RF-121, RF-123, RF-125, RF-129) |
| `src/convertersmartgrid/trafos_sed.py` | Transformador nuevo para una SED fija sobrecargada: la menor potencia de la tabla de fichas del perfil (por tensión primaria) con la máxima en el umbral, o unidades en paralelo de la mayor. | 020 (RF-6 a RF-8, RF-10, RF-11) |
| `src/convertersmartgrid/troncal.py` | Troncal de las obras sin DIgSILENT: camino continuo más largo desde la cabecera sobre el árbol de caminos más cortos en metros (anillos cerrados avisados), lo que queda aguas abajo de un nodo, el punto de la troncal más cercano (partir el tramo o usar la barra según la distancia mínima), el corte del trazado y los dos extremos del enlace. | 016 (RF-1 a RF-5, RF-15, RF-18, RF-20, RF-27, RF-28, RF-45, RF-64, RF-65, RF-67) |
| `src/convertersmartgrid/vias.py` | Trazado de una línea nueva por la vía pública con un enrutador OSRM (OpenStreetMap): ruta con sus curvas, largo con los accesos, metros fuera de vía y recta si no hay enrutador o no responde; solo envía las dos coordenadas. | 016 (RF-81 a RF-87) |
| `src/convertersmartgrid/util.py` | SHA-256, JSON atómico y números: una sola implementación. | 001 (RF-4, RF-5) |
| `src/convertersmartgrid/validate.py` | Validación del DGS escrito, con el trazado GPS de cada línea.; reconoce la red por zonal y SET | 034, 010 (RF-5), 021 (RF-12), 022 (RF-8 a RF-14), 054 |

### `src/convertersmartgrid/sources/` — adaptadores de entrada

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `src/convertersmartgrid/sources/__init__.py` | Registro de adaptadores, común a la web y al CLI. | 001 (RF-1) |
| `src/convertersmartgrid/sources/base.py` | Contrato de los lectores de las tres procedencias. | 001 (RF-1) |
| `src/convertersmartgrid/sources/mdb.py` | Adaptador de base Access. | 001 (RF-1) |
| `src/convertersmartgrid/sources/snapshot.py` | Qué ficheros forman una lectura y su huella. | 001 (RF-1) |
| `src/convertersmartgrid/sources/txt.py` | Adaptador de los tres TXT. | 001 (RF-1) |
| `src/convertersmartgrid/sources/vnr.py` | Adaptador de un paquete VNR-GIS. | 001 (RF-1, RF-2), 053 |
### `src/convertersmartgrid/web/` — API web

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `src/convertersmartgrid/web/__init__.py` | Paquete de la interfaz web. | 001 |
| `src/convertersmartgrid/web/__main__.py` | Arranca la web: `python -m convertersmartgrid.web` o `convertersmartgrid-web`; con el puerto ocupado reutiliza, reemplaza o cambia de puerto. | 001 (RF-15, RF-27, RF-28 a RF-32) |
| `src/convertersmartgrid/web/app.py` | Rutas FastAPI sobre el motor.; conversión por sistema eléctrico (`/convert/sistema`, `/estructura`) y la tabla de la estructura | 001, 004 a 008, 011 (RF-12, RF-25, RF-27, RF-28, RF-95, RF-104), 017 (RF-96, RF-103, RF-104), 021 (RF-26, RF-28 a RF-34), 022 (RF-4, RF-7, RF-47 a RF-49), 025 (RF-7, RF-28, RF-32), 035 (RF-1), 039 (RF-1, RF-5), 042, 061 (RF-1, RF-3, RF-10) |
| `src/convertersmartgrid/web/jobs.py` | Trabajos largos en cola, con progreso, cancelación y límite de tiempo por guion (P7). | 001 (RF-8), 011 (RF-39, RF-40), 061 (RF-1, RF-10) |
| `src/convertersmartgrid/web/readiness.py` | Puertas por alimentador antes de producir DGS; quita la falta de conductor que la carga ya reconstruyó. | 001, 053 (RF-9) |
| `src/convertersmartgrid/web/reconstruction_service.py` | Diagnóstico y reconstrucción como trabajos de la web. | 001 (RF-8, RF-9) |
| `src/convertersmartgrid/web/runtime.py` | Comprobación del entorno que hace el lanzador de Windows y huella del código. | 001 (RF-27, RF-28) |
| `src/convertersmartgrid/web/services.py` | Las acciones de la interfaz, sin interfaz; conversión por sistema eléctrico (022:RF-47 a RF-51).; máxima por barra de SET y sus alimentadores en esa fecha; estructura del espacio | 001, 004 a 008, 011 (RF-12 a RF-16, RF-25, RF-27 a RF-30, RF-39 a RF-41, RF-68, RF-95, RF-121), 017 (RF-47 a RF-53, RF-59, RF-60, RF-65 a RF-67b, RF-71, RF-82, RF-93, RF-94, RF-104), 020 (RF-6, RF-13, RF-15, RF-25, RF-28), 021 (RF-26 a RF-34, RF-50, RF-51, RF-54, RF-57, RF-61, RF-64), 022 (RF-4, RF-37 a RF-44), 025 (RF-4, RF-8 a RF-11, RF-17, RF-20, RF-24, RF-28 a RF-33), 018 (RF-1 a RF-15), 030 (RF-10, RF-13, RF-14), 032 (RF-12, RF-29), 035 (RF-1 a RF-3, RF-17 a RF-22), 037 (RF-1 a RF-7), 038 (RF-1, RF-5, RF-8), 039 (RF-1 a RF-6), 041 (RF-7, RF-9), 042, 060 (RF-7), 061 (RF-2, RF-3, RF-5, RF-6, RF-7, RF-8, RF-9) |
| `src/convertersmartgrid/web/source_runs.py` | Custodia inmutable de los ficheros de cada ejecución. | 001 |
| `src/convertersmartgrid/web/source_scope.py` | Empresa y periodo de los paquetes VNR-GIS; la copia de SQL Server, por su `ConfigBD.config`. | 001 (RF-2), 059 (RF-8) |
| `src/convertersmartgrid/web/sources/__init__.py` | Reexportación temporal de `convertersmartgrid.sources`. | 002 (RF-21 la retira) |
| `src/convertersmartgrid/web/sources/vnr.py` | Reexportación temporal de `convertersmartgrid.sources.vnr`. | 002 (RF-21 la retira) |
| `src/convertersmartgrid/web/workspace.py` | Espacio de trabajo: entradas, opciones, salida de una sesión y obras de mejora sin aplicar. | 001, 011 (RF-95), 025 (RF-17), 018 (RF-1 a RF-4, RF-13), 035 (RF-21), 038 (RF-1) |

## `src/vnr_etl/` — módulo VNR-GIS

Diseño completo en `VNR-GIS.md` (las «secciones» que citan los docstrings); operación en
`docs/VNR_GIS_PRODUCTION.md`. La spec 002 (RF-6) lo integrará en `convertersmartgrid`.

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
| `src/vnr_etl/connectors/sqlserver_vnr.py` | Copia de SQL Server (`.bak`) de VNR-GIS de cualquier concesionaria: restaura con su huella, lee las tablas por sus campos y arma el modelo canónico (tramos por su padre, SED, maniobras, bancos, tensión y CRS de la propia copia). | 023, 054 |
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
| `tools/ajuste_cabecera_pf.py` | Guion de DIgSILENT: ajusta un alimentador a su máxima de cabecera, en el escenario de «Sin proyecto»; propone e implementa transformadores nuevos para las SED fijas sobrecargadas; con una central, la crea en «Sin proyecto» y calibra por zonas; con varios `--plan`, calibra a la vez todos los alimentadores del proyecto; tabla de cambios en la red, lo original y lo nuevo; consigna de tensión de la fuente; pone los bancos que faltan en la troncal y recalibra.; central de barra de SET y cabeceras de la barra frente a su medidor | 006, 008, 011 (RF-18, RF-19, RF-51, RF-54), 014, 015, 020 (RF-60, RF-61), 021 (RF-35 a RF-44, RF-54 a RF-69), 022 (RF-41b, RF-44), 025 (RF-18), 032 (RF-14 a RF-28), 035 (RF-5 a RF-16, RF-20, RF-22, RF-23), 039 (RF-6), 035 (RF-28 a RF-31), 039 (RF-6), 041 (RF-4 a RF-9) |
| `tools/apply_catalog_to_model.py` | Corrige las características eléctricas del modelo con el catálogo de fichas. | 034 (RF-33), 032 (RF-2) |
| `tools/base_scenario.py` | Escenario base (año 0): lo construye, lo hace converger y lo diagnostica. | 005 |
| `tools/build_input_catalog.py` | Tabla de parámetros eléctricos en `input/` y auditoría de alimentadores. | 034 (RF-33) |
| `tools/build_system_grid.py` | Todos los alimentadores en una sola red, importada en PowerFactory. | 034 (RF-33) |
| `tools/build_interactive_architecture.py` | Página distribuible de la arquitectura C4 interactiva desde su fuente en `docs/architecture/`. | 009 (diseño `docs/superpowers/specs/2026-10-25-arquitectura-c4-interactiva-design.md`) |
| `tools/cargas_pf.py` | Guion de DIgSILENT: demandas y cargas nuevas en un proyecto existente; también el módulo común de los guiones: cabecera del alimentador, leer su red para la troncal y partir un tramo con `Application.SplitLine` en la variación que graba; las cargas nuevas se conectan en el punto más cercano de la troncal.; mide la cabecera en el interruptor de cabecera de una barra de SET compartida | 004, 007, 008, 011 (RF-52 a RF-55), 016 (RF-2, RF-4, RF-16 a RF-19, RF-21, RF-22, RF-45 a RF-50), 022 (RF-22, RF-23), 035 (RF-14, RF-15), 040, 054 |
| `tools/casos_pf.py` | Guion de DIgSILENT: los casos «Caso base», «Sin proyecto» y «Con proyecto», cada uno con su escenario y sus variaciones; «Sin proyecto» solo desde el «Caso base» verificado; «Con proyecto» como copia de «Sin proyecto», también para las obras; lo hecho a mano en «Sin proyecto» pasa a «Con proyecto». | 011 (RF-1 a RF-16, RF-46 a RF-50; casos para RF-51 a RF-54), 014, 015, 016 (RF-12), 025 (RF-14 a RF-17, RF-21), 037 (RF-2, RF-4, RF-5, RF-7), 073 (RF-13 a RF-15) |
| `tools/digital_twin_auditar.py` | Informe de la auditoría del dataset del gemelo y del asistente, sin GPU ni DIgSILENT. | 027 (RF-29 a RF-34) |
| `tools/digital_twin_buffer.py` | Búfer de episodios desde la consola: listar, mostrar, validar, registrar y rehacer el índice, sin DIgSILENT. | 024 (RF-6, RF-8, RF-9) |
| `tools/digital_twin_entrenar.py` | Entrena el oráculo PINN/GNN en su propio proceso (la web lo lanza): reentreno si toca o forzado, promoción por puertas, respaldo en CPU si la GPU falla; un fallo no tumba la web; con `--evaluar`, cuánto se apartan de DIgSILENT el modelo y la física por partición. | 024 (RF-16, RF-39, RF-42, RF-74) |
| `tools/asistente_entrenar.py` | Entrena el Transformer de órdenes y el clasificador de informes en su propio proceso, en la GPU; promoción por puertas; `--evaluar` mide los modelos en uso con la prueba fija. | 026 (RF-14, RF-20) |
| `tools/asistente_medir_ollama.py` | Mide los modelos locales de Ollama con las mismas órdenes (acierto, segundos, sin respuesta) y guarda el elegido para la web. | 026 (RF-3) |
| `tools/digital_twin_snapshot_pf.py` | Guion de DIgSILENT de solo lectura: reabre el proyecto, activa el caso, ejecuta el flujo y devuelve tensiones, cargabilidad, cabeceras, pérdidas, islas, frontera, estados pedidos y huellas del trazado. | 024 (RF-2, RF-3, RF-27, RF-28) |
| `tools/escenarios_pf.py` | Guion de DIgSILENT: escenarios del gemelo en una copia del proyecto (desactivado antes de copiar), demanda escalada y tramos abiertos, resultados y grafo eléctrico con R, X y corriente nominal; restituye cada cambio y borra la copia. | 024 (RF-11, RF-40, RF-41) |
| `tools/capacidad_pf.py` | Guion de DIgSILENT de la capacidad de alojamiento nodo a nodo y conjunta (`ComHostcap`), las curvas PV por alimentador con o sin contingencias (`ComPvcurves`) y la ubicación de condensadores en una variación temporal (`ComCapo`); lo llama `tools/estudios_pf.py`. | 012 (RF-3, RF-41 a RF-57) |
| `tools/confiabilidad_pf.py` | Guion de DIgSILENT: con `--aplicar-datos`, el libro de la empresa en la variación «Datos de confiabilidad» (modelos `Sto*` por clase y tipo, equipos que despejan y aíslan, tiempos, interruptor de cabecera, bloqueo sin clase); la confiabilidad (`ComRel3`) y la ubicación de reconectadores (`ComOpri`) que llama `tools/estudios_pf.py`. | 012 (RF-4, RF-12, RF-13, RF-17, RF-20 a RF-39, RF-69 a RF-71) |
| `tools/estudios_pf.py` | Guion de DIgSILENT: un estudio en un caso, sin escalado por alimentador y sin aplicar lo que proponen los optimizadores; mide cada alimentador. Con `--guion`, lista o ejecuta los guiones DPL y Python del operador. En «Con proyecto», mide cada alternativa del informe con solo sus obras; guarda la geografía con barras, tipo y largo de cada tramo y los acoples, y el nodo de la red de cada banco. Los estudios de la 012 con sus guiones y la comprobación de estado al terminar. | 011 (RF-17, RF-20 a RF-22, RF-26, RF-27 a RF-30, RF-31, RF-33, RF-36, RF-38, RF-43 a RF-45, RF-49), 017 (RF-130, RF-131, RF-135), 012 (RF-2, RF-60, RF-61), 037 (RF-4, RF-7) |
| `tools/check_pf_license.py` | Qué módulos de PowerFactory permite la licencia. | 005, 011, 012 (RF-4) |
| `tools/compare_schema.py` | Cabeceras de un DGS externo frente a un perfil de esquema. | 034 (RF-33) |
| `tools/cabecera_ancha.py` | Herramienta de la spec 051: pasa la medición de cabecera a lo ancho o las máximas mensuales al formato de la calibración, con `NOMBRE_EN_DIGSILENT=CODIGO`. | 051 (RF-8) |
| `tools/estado_specs.py` | Estado de las specs: lee numeración, tareas, estado y citas de las pruebas, y escribe `specs/README.md`. | 033 (RF-1 a RF-22) |
| `tools/construir_dataset_entrenamiento.py` | Construye el dataset de entrenamiento en una carpeta nueva y dice si está completo con los umbrales de la spec 027. | 043 |
| `tools/construir_dataset_pide.py` | Construye el corpus PIDE universal de una empresa con `pide_dataset`. | 024 |
| `tools/convertir_grupos_mdb.py` | Varios alimentadores de una base en un DGS, importado y con flujo, a escala real por defecto. | 034, 021 |
| `tools/fidelidad_seleccion.py` | Comprueba que una selección pasa entera del TXT al DGS. | 009 |
| `tools/linea_base_dgs.py` | Línea base de DGS para comprobar que una reorganización no cambia nada. | 001 (RF-14), 002 (RF-20) |
| `tools/obras_pf.py` | Guion de DIgSILENT de las obras de mejora: con `--bibliotecas`, alimentadores y tipos de las tres bibliotecas; copia de un tipo al proyecto; simular y aplicar con las reglas comunes (variación por obra, activación por caso, flujo, comprobación de «Sin proyecto»); banco de condensadores, reconectador, regulador, sección de cable, terna en la troncal y migración del alimentador a otra tensión; la troncal de las obras es la del camino más largo, leída en el caso de cada obra, sin `ComBbone`; enlace entre dos alimentadores en «Con proyecto» (tramos dentro de los límites con el flujo de antes, los dos puntos, partir tramos, línea recta con su trazado y seccionador abierto); migración a otra tensión de lo que queda aguas abajo de un nodo, calculado al construirla. | 011 (RF-56 a RF-60, RF-64 a RF-67, RF-69, RF-71 a RF-94, RF-96, RF-97, RF-99 a RF-103), 016 (RF-1, RF-2, RF-10 a RF-12, RF-26, RF-29, RF-30, RF-32 a RF-38, RF-40, RF-42, RF-43, RF-54 a RF-58, RF-60, RF-62), 042, 073 (RF-25, RF-26) |
| `tools/escanear_alimentador_pf.py` | Escaneo de solo lectura de alimentadores en DIgSILENT: generadores con su barra, bancos, variaciones y cargas cambiadas a mano. | 028 (RF-1, RF-2, RF-4 a RF-6, RF-8) |
| `tools/informe_web.py` | Un informe de la spec 017 desde la línea de órdenes: lee el `.plan.json` que la web guardó junto al Word (o un formulario con `--tipo`), lo envía a la misma API como trabajo, lo espera con el cliente de `sistema_web.py` y descarga el Word y su plan. | 017 (RF-105) |
| `tools/informe_casos_guardados.py` | Reproduce la evaluación Word con tres casos y sus seis flujos guardados por la web; exige un solo proyecto y cobertura completa de las ramas trasladadas, conserva hashes y exporta barras/equipos a CSV. Reutiliza el escritor existente, sin ejecutar DIgSILENT. | 063 (RF-6 a RF-14) |
| `tools/set_nueva_operacion_pf.py` | Diagnóstico físico de conexiones y tipos de una SET existente; evalúa refuerzos y nuevas salidas en variaciones propias con copia del escenario. La conciliación explícita de fases conserva P/Q totales y su reparto relativo. Admite aplicación solo con ambos flujos aceptados y relectura; captura también los cuatro flujos de referencia. No recrea ni desplaza la SET. | 063 (RF-36 a RF-38) |
| `tools/hojas_diagrama_pf.py` | Hoja de cada diagrama de un proyecto de DIgSILENT frente a sus gráficos y conectores, de solo lectura. | 022 (RF-93) |
| `tools/pf_proyectos.py` | Proyectos de la carpeta de importación de DIgSILENT y sus alimentadores. | 005 |
| `tools/powerfactory_acceptance.py` | Puerta de aceptación: importa un DGS en PowerFactory, o adopta un proyecto existente, y verifica su «Caso base» frente al archivo original. | 034, 010 (RF-6, RF-7), 015, 054, 078 |
| `tools/prueba_representacion.py` | Red, cargas y SED del TXT en una hoja de PowerFactory. | 034 (RF-33) |
| `tools/run_one_study.py` | Trabajador de PowerFactory: importa y mide, o ejecuta un estudio. | 005 |
| `tools/run_powerfactory_gate.bat` | Lanza `powerfactory_acceptance.py` con el intérprete de PowerFactory. | 034 (RF-33) |
| `tools/show_pf_diagram.py` | Abre en DIgSILENT el diagrama de un alimentador. | 005 |
| `tools/sistema_web.py` | Un sistema eléctrico de punta a punta por la web: espera lo que corre, convierte por sistema, importa en DIgSILENT, busca la máxima por barra de SET y calibra el sistema entero; retoma lo hecho y reintenta si la web corta. | 022 (RF-56), 025 (RF-25, RF-25b, RF-25c), 039 (RF-1) |
| `tools/suggest_line_type_aliases.py` | Propone alias para tipos de línea sin ficha en el catálogo. | 034 (RF-33) |
| `tools/transformador_set_pf.py` | Guion de DIgSILENT: cargabilidad del devanado de la SET en el proyecto de transmisión, sin proyecto (el caso tal cual) y con proyecto (la carga de la barra más el Δ de cabecera de 4.2), un flujo por estado, con la carga restituida y comprobada; `--listar` da las cargas de barra con su transformador y los casos. | 017 (RF-65 a RF-68, RF-70) |
| `tools/transferencia_pf.py` | Guion de DIgSILENT: transferencia de carga entre dos alimentadores por su enlace, paso a paso en los dos sentidos, con la capacidad y el margen del enlace (`ComTransfer` o flujos sucesivos), sin dejar nada en el proyecto; un enlace entre barras de distinta tensión no se cierra ni se calcula. | 011 (RF-104 a RF-129), 016 (RF-62, RF-63) |
| `tools/costos_cruce.py` | Mide cuánto de una red convertida encuentra costo en el SICODI público, y nombra lo que no. | 072 |
| `tools/madrl_entrenar.py` | Entrena el control MaskablePPO del piloto y lo compara con sus referencias. | 074 |
| `tools/madrl_obras.py` | Mide la escalera y NSGA-II y la fidelidad del entorno sobre una red del búfer de episodios. | 074 |
| `tools/proyeccion_mercado.py` | Compara métodos de proyección anual contra lo ocurrido con el Formato 01. | 072 |
| `tools/pide_pf.py` | Guion de DIgSILENT: cada año del horizonte del PIDE con la demanda escalada por el `ComLdf`, diagnóstico de la norma con el alimentador y la tensión de cada problema; restituye el factor. | 024 (RF-51 a RF-53), 029 (RF-4), 030 (RF-1 a RF-9, RF-11, RF-12, RF-15) |
| `tools/pf_cliente.py` | Envía un guion de DIgSILENT al proceso que se queda abierto y reescribe su salida. | 019 |
| `tools/pf_servidor.py` | Proceso que mantiene DIgSILENT abierto y atiende las órdenes de los guiones; se cierra a los 2 minutos sin órdenes; repone el estado tras una orden fallida. | 019, 064 |
| `tools/restitucion_pf.py` | Órdenes de aceptación de la restitución del servidor: copiar, alterar y fallar, leer y borrar una copia `PRUEBA064_*`. | 064 |
| `tools/aceptar_restitucion_pf.py` | Aceptación nativa de la restitución por el camino de la web y el servidor, con evidencia en JSON. | 064 |
| `tools/verify_interactive_architecture.mjs` | Comprobación en navegador de la página de la arquitectura C4 interactiva (Node.js). | 009 (diseño `docs/superpowers/specs/2026-10-25-arquitectura-c4-interactiva-design.md`) |
| `tools/verify_architecture_links.py` | Comprueba los enlaces públicos y locales del espacio Structurizr de la arquitectura. | 009 |
| `tools/verificar_pf.py` | Guion de DIgSILENT: convergencia del proyecto con lo activo. | 008 |

## `frontend/src/` — interfaz web

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `frontend/src/main.tsx` | Arranque de React. | 001 |
| `frontend/src/App.tsx` | Marco de la página: paneles, pestañas, resúmenes de trabajos. | 001, 008 (RF-1, RF-2), 061 (RF-4) |
| `frontend/src/operacionSet.ts` | Valida el formulario de la operación de una SET y arma el cuerpo de la orden. | 063 |
| `frontend/src/solicitudLeida.ts` | Acumula por documento lo leído de los PDF del solicitante y detecta un alimentador distinto del de la carga. | 063 |
| `frontend/src/api.ts` | Cliente tipado de la API.; conversión por sistema eléctrico y máxima por barra | 001 (RF-12, RF-13), 011 (RF-42), 021 (RF-26, RF-34), 022 (RF-7, RF-39), 025 (RF-28), 039 (RF-1, RF-5), 061 (RF-2, RF-5) |
| `frontend/src/types.ts` | Tipos de las respuestas de la API. | 001, 011, 021, 025 (RF-4, RF-24, RF-28), 037 (RF-1, RF-5), 039 (RF-1, RF-5), 041 (RF-6, RF-9), 061 (RF-2, RF-9) |
| `frontend/src/clientesCatalogo.ts` | Estado del catálogo mensual de clientes: un solo libro activo e índice vigente antes de cruzar. | 004, 008, 025 (RF-10, RF-23) |
| `frontend/src/projectBinding.ts` | Vínculo del proyecto de DIgSILENT con su ejecución de origen: separa los bloqueos de las advertencias por cambios manuales. | 005, 018 (RF-9 a RF-12), 034 (RF-21) |
| `frontend/src/context.tsx` | Contexto común de la aplicación. | 001 |
| `frontend/src/useWorkspace.ts` | Espacio de trabajo, Registro en vivo y trabajos por WebSocket; `?espacio=` y la clave anterior del navegador. | 001, 059 (RF-6) |
| `frontend/src/styles.css` | Tokens y estilos, modo claro y oscuro; paleta de las series de la curva. | 001, 021 |
| `frontend/src/components/InputsPanel.tsx` | Entrada de datos: TXT, MDB y VNR-GIS. | 001 (RF-26) |
| `frontend/src/components/OptionsPanel.tsx` | Opciones de conversión. | 001 |
| `frontend/src/components/FeedersPanel.tsx` | Tabla de alimentadores y conversión.; conversión por sistema eléctrico con su zonal, aparte de unir, y el tipo de cada DGS unido | 001, 022 (RF-7) |
| `frontend/src/components/ReconstructionPanel.tsx` | Diagnóstico y reconstrucción. | 001 (RF-8, RF-9) |
| `frontend/src/components/Modules.tsx` | Pestañas de resultados, catálogo y sistema completo. | 001 |
| `frontend/src/components/CargasTab.tsx` | Pestaña «Cargas en DIgSILENT» en cuatro pasos; la distancia mínima de las cargas nuevas. | 004, 005, 008, 011 (RF-42, RF-98), 016 (RF-73), 042 |
| `frontend/src/components/DemandaMedida.tsx` | Paso 2: libros de medición, máxima de cabecera (con la central térmica de un alimentador, en el mes de análisis o en un instante coincidente) y clientes con su nombre.; máxima por barra de SET | 004 (RF-57), 008, 013 (RF-11), 021 (RF-25 a RF-27, RF-50, RF-52), 022 (RF-39, RF-41), 025 (RF-22, RF-23, RF-34, RF-35, RF-78), 035 (RF-1, RF-2), 038 (RF-2, RF-6, RF-7), 039 (RF-1, RF-4, RF-5) |
| `frontend/src/components/DatosEmpresaPF.tsx` | Paso 4.2: libro de la empresa del proyecto (subir, plantilla, lo que trae, aplicar en DIgSILENT). | 012 (RF-6, RF-7, RF-16, RF-20, RF-21) |
| `frontend/src/components/EstudiosPF.tsx` | Paso 4.2: estudios sobre la red calibrada, límites y resultados; los de la 012 con sus opciones, su tabla y aceptar un reconectador o un banco como obra. | 011 (RF-24, RF-25, RF-35, RF-39, RF-68), 012 (RF-1, RF-19, RF-37, RF-40, RF-45, RF-53, RF-58), 037 (RF-1, RF-5) |
| `frontend/src/components/Asistente.tsx` | Pestaña «Asistente»: consola de órdenes, plan con datos, pasos, lo que falta, dudas y razonamiento, confirmar y ejecutar, corregir la tarea, respuestas con cita, entregables y reentrenar. | 026 (RF-1, RF-7, RF-8, RF-12, RF-15), 043 (RF-8), 061 (RF-4) |
| `frontend/src/components/GemeloPIDE.tsx` | Paso 5 de «Cargas en DIgSILENT»: planificar con el PIDE (CAPEX opcional, aplicar solas las obras que funcionan), tabla de obras con prioridad, estado y decisión del operador, formatos 01 a 15, aprendizaje activo del gemelo y episodios del proyecto. | 024 (RF-8, RF-45 a RF-48) |
| `frontend/src/components/GuionesPF.tsx` | Paso 4.2: guiones DPL y Python del operador, sus parámetros y su salida por caso. | 011 (RF-27 a RF-30) |
| `frontend/src/components/ObrasPF.tsx` | Paso 4.1: formulario de obras de mejora (también enlace, migración desde un nodo y sección de toda la troncal), bibliotecas de tipos, obras guardadas, simular y aplicar. | 011 (RF-56 a RF-95), 016 (RF-68 a RF-72) |
| `frontend/src/components/TransferenciaPF.tsx` | Paso 4.3: transferencia de carga entre dos alimentadores. | 011 (RF-104 a RF-123) |
| `frontend/src/components/OperacionSet.tsx` | Panel para diagnosticar, evaluar o reforzar una SET existente, sin recrearla. | 063 |
| `frontend/src/components/InformesPF.tsx` | Paso 4.4: informe de estudio eléctrico y de factibilidad y punto de diseño con lo ya guardado por la web (flujos de 4.2, obras, cargas nuevas aplicadas, máxima de 2.2); formularios guardados en el servidor; libro de pérdidas subido o a mano; transformador de la SET a mano; huecos, descarga e informes generados. | 017 (RF-73 cambiado, RF-74 a RF-82, RF-89 a RF-94, RF-96, RF-100, RF-102 a RF-104, RF-125) |
| `frontend/src/components/AjusteCabecera.tsx` | Paso 2.4: ajuste a la máxima de uno o varios alimentadores; SED fijas sobrecargadas con su propuesta y el botón de transformadores nuevos; tabla de cambios en la red; tensión en la fuente; bancos que falten. | 006, 008, 020 (RF-62), 021, 025 (RF-24), 035 (RF-11, RF-16, RF-21, RF-22), 039 (RF-1), 035 (RF-30), 039 (RF-1), 041 (RF-6, RF-9) |
| `frontend/src/components/CurvaCabecera.tsx` | Paso 2.4: curva del registro del medidor de cabecera, con el mes de la máxima sombreado y zoom por tramo; con varios alimentadores, una curva por cada uno en la misma gráfica; con central, sus curvas y la de la demanda. | 006 (RF-32 a RF-38), 021 (RF-17 a RF-24, RF-47 a RF-49) |
| `frontend/src/components/JobBar.tsx` | Barra de trabajos en curso. | 001 |
| `frontend/src/components/LogPanel.tsx` | Registro. | 001 |
| `frontend/src/components/ui.tsx` | Piezas comunes: modal, avisos, casillas, ficheros. | 001 |

## Gobierno de modelos y preparación causal

| Fichero | Responsabilidad | Spec |
| --- | --- | --- |
| `src/convertersmartgrid/model_registry.py` | Candidatos inmutables, integridad, promoción atómica y reapertura en subproceso. | 043 (RF-1, RF-5), 060 (RF-7) |
| `src/convertersmartgrid/training_coordinator.py` | Etapas reanudables, bloqueo GPU mediante guardia OS compartida y memoria física/comprometible antes de cargar pesos. | 043 (RF-6, RF-7, RF-12) |
| `src/convertersmartgrid/trabajadores_ml.py` | Informes atómicos, dataset v2 verificado y herencia comprobada de la guardia GPU en procesos hijos. | 043 (RF-6, RF-7, RF-13) |
| `src/convertersmartgrid/digital_twin/temporal_entrenamiento.py` | Lectura de series mediante lectores existentes, ajuste causal GRU, objetivos de cabecera y clientes, competición de pronósticos con ganador por objetivo, candidatos y recarga verificable. | 043 (RF-13), 046 (RF-1, RF-3, RF-7 a RF-19), 060 (RF-5, RF-6, RF-8) |
| `src/convertersmartgrid/asistente/embeddings.py` | Pares contrastivos, métricas de recuperación, encoder CUDA local y persistencia de índices con hashes. | 043 (RF-13), 047 (RF-3, RF-4) |
| `src/convertersmartgrid/asistente/entrenamiento_dataset.py` | Ajuste de clasificadores pequeños sobre particiones v2 explícitas; conserva candidatos sin promoción. | 043 (RF-7, RF-13) |
| `tools/digital_twin_temporal_entrenar.py` | Trabajador de entrenamiento y recarga GRU, inventario de la medición y competición de pronósticos de cabecera o clientes fijos. | 043 (RF-13), 046 (RF-3, RF-7, RF-12, RF-13, RF-15, RF-24), 060 (RF-8) |
| `tools/evaluar_evolutivos.py` | Benchmark analítico calculado de GA, NSGA-II y DE con al menos 30 semillas, separado de aceptación eléctrica. | 043 (RF-13), 048 (RF-3, RF-6) |
| `tools/asistente_embeddings.py` | Ajuste solo con train y evaluación sobre consultas reservadas del recuperador local; sin cambiar índice activo. | 043 (RF-13), 047 (RF-3, RF-4) |
| `src/convertersmartgrid/asistente/reranker.py` | Reranker por cross-encoder en CUDA, con revisión fijada, la política que lee la decisión de la evaluación sellada y los umbrales de abstención guardados. | 047 (RF-4, RF-27, RF-30, RF-33, RF-34) |
| `src/convertersmartgrid/asistente/evaluacion_rag.py` | Conjunto sintético sellado, medición de BM25, híbrido y rerankers, decisión según la política declarada, calibración de la abstención y su puerta en el conjunto sellado. | 047 (RF-4, RF-27, RF-28, RF-34, RF-36) |
| `tools/asistente_evaluar_rag.py` | Medición real de la recuperación en la GPU, comprobación del conjunto sin ella con `--solo-conjunto`, calibración de la abstención y su medición sellada única. | 047 (RF-4, RF-27, RF-34, RF-35) |
| `tools/asistente_qlora.py` | Adaptador del coordinador al ajuste generativo NF4 existente y su corpus sellado; conserva pesos candidatos. | 043 (RF-13), 047 (RF-19, RF-20) |
| `src/convertersmartgrid/experimentos.py` | Contexto exacto y contratos inmutables de configuración, con SHA-256 canónico. | 043 (RF-2) |
| `src/convertersmartgrid/asistente/dataset_entrenamiento.py` | Custodia de datos reales, sintéticos y de contexto; agrupación de registros. | 043 (RF-3, RF-4) |
| `src/convertersmartgrid/asistente/calidad_datos.py` | Calidad y contaminación entre particiones sin inflar el conjunto humano. | 043 (RF-3, RF-4) |
| `src/convertersmartgrid/digital_twin/series_causales.py` | Cadencia, unidades, huecos, disponibilidad de covariables, particiones por día y ventanas causales. | 046 (RF-1 a RF-3, RF-5) |
| `src/convertersmartgrid/digital_twin/pronostico.py` | Contrato multihorizonte: objetivos, conjunto en rejilla común, referencias ingenuo y estacional semanal, calibración de intervalos y filas con la marca `pronostico`. | 046 (RF-1 a RF-5, RF-12 a RF-15, RF-19) |
| `src/convertersmartgrid/digital_twin/adaptador_neuralforecast.py` | N-HiTS, TFT y PatchTST de neuralforecast, opcionales y solo en CUDA, con la interfaz común. | 046 (RF-13 a RF-15) |
| `src/convertersmartgrid/digital_twin/evaluacion_temporal.py` | Política predeclarada, pinball y cobertura por horizonte, error de la máxima y de su instante y familias para las puertas. | 046 (RF-5, RF-6, RF-8, RF-18) |
| `tools/reentrenar_modelos.py` | CLI de coordinación, validación de configuración y rechazo de resultados incompletos. | 043 (RF-2, RF-5, RF-7), 060 (RF-8) |
| `src/convertersmartgrid/upstream_ia.py` | Verifica origen, commit, licencia y árbol limpio de repositorios reutilizados; conserva copias existentes. | 043 (RF-9 a RF-11) |
| `tools/preparar_upstream_ia.py` | Prepara o verifica clones fijados sin instalar ni ejecutar sus programas. | 043 (RF-9 a RF-11) |
| `src/convertersmartgrid/digital_twin/adaptador_pyg.py` | Adapta el MPN de PowerFlowNet a correcciones físicas de tensión y ángulo, mediante carga opcional. | 045 (RF-8) |
| `src/convertersmartgrid/evaluacion_modelos.py` | Política previa y validación de cuatro particiones por grupos; puertas independientes por familia. | 044 (RF-1 a RF-5, RF-8) |
| `src/convertersmartgrid/asistente/curriculo_maestro.py` | Familias sintéticas de órdenes escritas por el maestro de sesión, separadas antes del entrenamiento, y frases de estilo real solo de entrenamiento. | 047 (RF-11, RF-12), 068 (RF-35 a RF-37) |
| `src/convertersmartgrid/asistente/destilacion_integral.py` | Comparación supervisado/destilado, calibración, prueba sellada, recarga y registro del alumno. | 047 (RF-11 a RF-15) |
| `src/convertersmartgrid/asistente/contratos_salida.py` | Esquema de órdenes y validación de tareas, campos, confianza y entidades del contexto. | 047 (RF-1, RF-2, RF-10) |
| `src/convertersmartgrid/schemas/asistente_orden_v1.schema.json` | Contrato base de salida estructurada para el intérprete local. | 047 (RF-1) |
| `tools/asistente_destilar.py` | Prepara el currículo, entrena con exclusión GPU y verifica el alumno en proceso nuevo. | 047 (RF-11 a RF-15) |
| `src/convertersmartgrid/asistente/llm_destilacion.py` | Custodia de referencia, corpus del LLM con entidades reales y objetivos causales de respuesta. | 047 (RF-19, RF-20), 060 (RF-4) |
| `src/convertersmartgrid/asistente/llm_runtime.py` | Verifica checkpoints y publica exportación, GGUF e importación local secuencial con hashes y readback; no activa. | 047 (RF-19) |
| `src/convertersmartgrid/asistente/curriculo_llm_real.py` | Solicitudes nuevas de prueba redactadas por el maestro; valores procedentes de fuentes reales. | 047 (RF-19, RF-20) |
| `tools/llm_destilar.py` | Prepara el corpus del alumno LLM a partir de fuentes verificadas de este proyecto. | 047 (RF-19, RF-20), 060 (RF-4) |
| `src/convertersmartgrid/asistente/propuestas_maestro.py` | Corpus separado de 200 propuestas únicas, con anotaciones y procedencia del maestro. | 047 (RF-16) |
| `src/convertersmartgrid/asistente/aceptacion.py` | Auditoría, evaluación del intérprete/plan y puertas de aceptación por alcance; cuenta observaciones humanas únicas. | 047 (RF-13, RF-16 a RF-18) |
| `tools/aceptar_agente.py` | Materializa propuestas, selecciona configuración local y evalúa las 200 sin ejecutar acciones nativas. | 047 (RF-16 a RF-18) |
| `frontend/src/asistenteAceptacion.ts` | Contrato web de propuestas, observaciones humanas y aceptación del agente. | 047 (RF-17) |
| `tools/preparar_modelos_ia.py` | Descarga explícita y auditoría de pesos fijados, sin activación. | 043 (RF-12) |
| `docs/MODELOS_IA_LOCK.json` | Revisiones, licencias, tamaños y hashes de los modelos locales seleccionados. | 043 (RF-12) |
| `docs/DEPENDENCIAS_IA_LOCK.json` | Versiones, fuentes, hashes de bibliotecas y ejecutable Ipopt del entorno IA instalado. | 043 (RF-12) |


## Documentación

| Documento | Para qué | Vigencia |
| --- | --- | --- |
| `README.md` | Qué es, instalación y uso. | vigente |
| `CLAUDE.md` | Reglas para trabajar en el repositorio. | vigente |
| `CODIGO_FUENTE.md` | Este índice. | vigente |
| `docs/constitution.md` | Principios innegociables. | vigente |
| `docs/ARQUITECTURA.md` | Arquitectura actual: capas de hecho, flujos, casos de PowerFactory, carriles y mapa de specs. | vigente |
| `docs/VERIFICACION_SPECS_2026-10-14.md` | Verificación de cada spec, RF por RF y tarea por tarea. | histórico |
| `docs/REVISION_SPECS_2026-10-29.md` | Revisión de numeración, estado y trazabilidad spec ↔ tareas ↔ pruebas ↔ código, con el plan de saneamiento (futura spec 033). | vigente |
| `docs/MANUAL_COMANDOS.md` | Cada orden del CLI y cada herramienta. | vigente |
| `docs/POWERFACTORY_ACCEPTANCE.md` | Aceptación en PowerFactory. | vigente |
| `docs/INVESTIGACION_IA_GEMELO_CONVERSOR_2026-10-31.md` | Investigación de mejoras de gemelo, PINN/GNN, pronóstico, LLM/PLN y optimización evolutiva/PNL sobre el código existente, con repositorios y bibliografía. | propuesta, 2026-10-31 |
| `docs/VERIFICACION_PUBLICACIONES_IA_PF_2026-10-31.md` | Contraste de los enlaces PINN, TradingAgents y protecciones DIgSILENT con código local y brechas reproducidas. | 043–049, borrador |
| `docs/superpowers/plans/2026-10-31-mejora-integral-ia-conversor.md` | Plan maestro SDD con dependencias, contratos, paquetes de implementación y aceptación independiente/nativa. | 043–049, borrador |
| `docs/VNR_GIS_PRODUCTION.md` | Operación del módulo VNR-GIS. | vigente |
| `docs/runbooks/three-source-production-acceptance.md` | Aceptación de las tres fuentes. | vigente |
| `docs/runbooks/universal-native-load-acceptance.md` | Aceptación universal hasta carga, relectura y estudio nativos. | vigente |
| `VNR-GIS.md` | Diseño completo de VNR-GIS, citado por secciones en el código. | vigente |
| `input/README.md` | Qué va en `input/`. | vigente |
| `specs/NNN-*/` | Specs, planes y tareas. | vigente |
| `docs/DIAGNOSTICO_*.md` | Diagnósticos fechados que dieron origen a specs. | histórico |
| `docs/EJECUCION_IA_2026-10-31.md` | Evidencia de implementación, revisión independiente y pendientes reales por spec. | 043, 044, 046 |
| `docs/UPSTREAM_IA_LOCK.json` | URLs, commits y hashes de licencias de los proyectos GitHub seleccionados. | 043 (RF-9) |
| `docs/REUSO_GITHUB_IA_2026-10-31.md` | Selección de proyectos, reproducción de clones, adaptador comprobado y límites pendientes. | 043, 045–048 |
| `docs/DESTILACION_AGENTE_2026-10-31.md` | Metodología, currículo del maestro, comparación real y límites de aceptación del alumno del agente. | 043, 044, 047 |
| `docs/ACEPTACION_INTEGRAL_AGENTE_2026-10-31.md` | Auditoría de las 200 propuestas, medición real, instalación de dependencias y pendientes de aceptación integral. | 043, 047 |
| `docs/superpowers/` | Diseños y planes anteriores a las specs. | histórico |

## Observación integrada del agente

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `src/convertersmartgrid/asistente/observacion.py` | Diario SQLite por espacio, contexto inmutable, informes custodiados y control de identidad de reanudación, sin promoción. | 061 (RF-1, RF-2, RF-3, RF-7, RF-8, RF-9) |
| `frontend/src/components/MonitorAgente.tsx` | Monitor del asistente conectado al contexto WebSocket, etapas, operaciones, evidencia real y retención diaria. | 061 (RF-2, RF-3, RF-4, RF-5, RF-9), 062 (RF-8) |
| `tools/asistente_observar.py` | Incorpora y verifica informes locales del aprendizaje sin activar modelos. | 061 (RF-8) |
| `src/convertersmartgrid/web/retencion.py` | Revisión diaria de ejecuciones y temporales sin referencias, de más de siete días, con protección de datos y resumen persistido. | 062 (RF-1, RF-2, RF-3, RF-4, RF-5, RF-6, RF-7, RF-8) |

## Cierre de auditoría integral — spec 065

| Fichero | Qué hace | Spec |
| --- | --- | --- |
| `src/convertersmartgrid/asistente/custodia_corpus.py` | Resolución explícita y verificable de fuentes custodiadas tras su traslado, sin alterar ejemplos ni particiones. | 047, 065 |
| `src/convertersmartgrid/asistente/reubicacion_corpus.py` | Nueva custodia externa del corpus LLM con cuotas, hashes, preflight y conservación del original. | 047, 065 |
| `tools/reubicar_corpus_llm.py` | Valida o publica una nueva versión custodiada del corpus tras un traslado exacto de datos. | 047, 065 |
| `tools/aceptar_dominio.py` | Preaceptación de fuente, vínculo, caso, evidencia y recursos sin conectar ni modificar el motor nativo. | 065 |
| `tools/verificar_candidato.py` | Regresión de un candidato con hashes antes/después, JUnit y matriz de trazabilidad. | 065 |
| `frontend/src/api/esquema.ts` | Tipos generados desde OpenAPI; no se editan a mano. | 065, 002 |
| `frontend/src/components/DescargaZip.tsx` | Descarga ZIP preparada como trabajo con progreso y cancelación. | 065 |
| `frontend/src/components/EquipoAsistente.tsx` | Roles, permisos y revisión de propuestas en la consola del asistente. | 065 |
| `frontend/src/equipoAsistente.ts` | Cliente tipado de permisos, acciones y revisiones del equipo. | 065 |
| `src/convertersmartgrid/asistente/equipo.py` | Gobierno de herramientas y permisos sellados por plan, rol y fuente. | 065 |
| `src/convertersmartgrid/asistente/codificador_ordenes.py` | Intérprete de órdenes con codificador preentrenado congelado, cabezas de tarea y de datos, clase «ninguna» y el lugar en que el modelo la ve. | 069 (RF-1 a RF-9), 075 (RF-37) |
| `src/convertersmartgrid/asistente/validacion_cruzada.py` | Validación cruzada con las órdenes confirmadas: familias de frases casi iguales, reparto en 5 vueltas estratificado por tarea, cabezas por vuelta sobre la caché del codificador, medida fuera de grupo y modelo final. | 075 (RF-1 a RF-28) |
| `src/convertersmartgrid/asistente/datos_por_palabra.py` | Etiquetas de los datos de una orden y su decisión por palabra, comunes a los dos modelos de órdenes. | 026 (RF-2), 069 (RF-1, RF-31) |
| `src/convertersmartgrid/asistente/maestro_real.py` | Lee y valida las etiquetas de plata del maestro sobre textos reales, dice cuándo dos textos son la misma frase o familia y añade las erratas observadas. | 068 (RF-21 a RF-27, RF-38, RF-39) |
| `tools/asistente_ordenes_reales.py` | Reúne las órdenes reales de las sesiones y del almacén, crea el libro de revisión e importa solo lo que el operador marque. | 068 (RF-1 a RF-20) |
| `src/convertersmartgrid/asistente/evidencias_web.py` | Custodia como evidencia del espacio el resultado de los informes y estudios que terminan bien, con su proyecto y su fuente verdaderos, para la revisión por roles. | 067 (RF-1 a RF-7) |
| `src/convertersmartgrid/asistente/planes_guardados.py` | Planes que escriben guardados por espacio con escritura atómica: sobreviven a un reinicio, sin confirmación y sin reanudarse. | 067 (RF-12 a RF-19) |
| `src/convertersmartgrid/asistente/modelos_en_uso.py` | Pone en uso lo que el registro aprobó con un único puntero atómico, conserva el anterior y vuelve a él con el registro de acuerdo. | 067 (RF-20 a RF-24) |
| `src/convertersmartgrid/asistente/revision_roles.py` | Revisión local por roles sin autorización de escrituras nativas. | 065 |
| `src/convertersmartgrid/preflight_contract.py` | Contrato JSON del modelo efectivo, fijado al DGS antes de su importación. | 065 |
| `src/convertersmartgrid/runtime_paths.py` | Raíces externas, staging por volumen, custodia y reconciliación de temporales. | 065 |
| `src/convertersmartgrid/web/api_contract.py` | Modelos públicos Pydantic y contratos OpenAPI del frontend. | 065, 002 |
| `src/convertersmartgrid/web/equipo_api.py` | API del equipo LLM: permisos por plan y revisiones locales en cola. | 065 |
| `src/convertersmartgrid/web/operaciones_lentas.py` | ZIP cancelable, cuotas y entrega de archivos por trabajo. | 065 |
| `tools/arquitectura.py` | Guarda AST de capas, ciclos y accesos privados con deuda explícita. | 065, 002 |
| `tools/fijar_entorno.py` | Cierre reproducible de dependencias para CPython 3.12/Windows. | 065 |
| `tools/generar_contrato_api.py` | Generación y comprobación determinista del contrato OpenAPI a TypeScript. | 065, 002 |
| `tools/trazabilidad_candidato.py` | Matriz de requisitos, código, pruebas y ejecuciones vinculadas al candidato. | 065 |
