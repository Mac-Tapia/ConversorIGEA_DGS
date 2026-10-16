# Diagnóstico técnico y científico del conversor IGEA/CYMDIST → DGS

Fecha de revisión: 2026-09-21  
Alcance: código versionado en `src/igea_dgs`, pruebas, herramientas de aceptación, documentación y artefactos existentes en `output/production_all`.  
Tipo de revisión: lectura estática, ejecución local de pruebas y contraste bibliográfico. No se modificó el motor ni se volvió a ejecutar PowerFactory.

## Dictamen ejecutivo

El proyecto es un prototipo avanzado y útil para generar DGS estructuralmente consistentes, con buena separación entre ingestión, modelo, serialización, validación y presentación. No obstante, todavía no debe clasificarse como conversor universal ni como modelo eléctrico científicamente validado para estudios operativos sin una fase adicional de calibración y aceptación.

La razón central es que la validación actual demuestra principalmente consistencia interna y capacidad de importación, pero no equivalencia física respecto del sistema fuente. Los defectos de mayor riesgo son:

1. Las longitudes del modelo se reemplazan siempre por distancia euclidiana de coordenadas, aun con `--no-geography`, suponiendo implícitamente que la unidad del CRS es el metro.
2. El modelo DGS fuerza numerosos elementos a tres fases y no conserva de forma completa la fase original; esto compromete estudios desbalanceados.
3. Los transformadores SED se infieren mediante una expresión regular y reciben parámetros eléctricos sintetizados (0.22 kV, Dyn5, uk=4 %, pérdidas estimadas), no parámetros del catálogo.
4. Los tipos de línea ausentes pueden sustituirse automáticamente por similitud textual o `DEFAULT`; una conversión puede terminar “OK” con parámetros eléctricos distintos de los de origen.
5. B1/B0 se descartan, la fuente externa no tiene potencia/impedancia de cortocircuito y varios modos de carga distintos de `ValueType=2` terminan con Q=0.
6. El validador compara el DGS contra el mismo modelo intermedio que lo generó. Es una buena verificación, pero no una validación independiente contra CYMDIST, mediciones o un caso PowerFactory de referencia.

Clasificación recomendada hoy: **apto para generación, inspección y premodelado con excepciones explícitas; no apto todavía como gemelo eléctrico universal ni como fuente única para decisiones de protección, cortocircuito, regulación o planificación**.

## Evidencia ejecutada

- `46 passed in 10.39 s` en el subconjunto independiente de datos externos.
- `55 passed in 22.33 s` en la puerta técnica indicada por el propio proyecto.
- `ruff` no pudo ejecutarse porque no está instalado ni declarado en `requirements-dev.txt`.
- Una ejecución completa de `pytest -q` fue interrumpida tras más de 90 s sin progreso visible después de dos casos. La búsqueda de fixtures incluye la ruta UNC `\\mnt\data`, que puede introducir latencia de red en Windows.
- `compileall` no reportó errores.
- El artefacto existente `output/production_all/PRODUCTION_READINESS.json` declara 93/93 conversiones estáticas y 92/93 aceptaciones PowerFactory, con IC103 sin convergencia. Esta es evidencia histórica del 2026-09-21, no una nueva ejecución durante esta auditoría.

## Hallazgos priorizados

| ID | Severidad | Módulo | Hallazgo | Consecuencia |
|---|---|---|---|---|
| C-01 | Crítica | `model.py` | `apply_georeferenced_lengths` calcula `hypot(Δx,Δy)` y lo interpreta como metros, sin consultar unidades del CRS; se invoca siempre al construir el modelo. | Longitud, impedancia total, caída de tensión y pérdidas pueden quedar escaladas incorrectamente; `--no-geography` no evita la mutación. |
| C-02 | Crítica | `dgs.py` / `model.py` | Se fuerza `nlnph=3`, cubículos 0/1/2, transformadores trifásicos y cargas sin mapeo eléctrico explícito de `Phase`. | Se pierde fidelidad monofásica/bifásica y de desbalance; un flujo convergente puede representar otro circuito. |
| C-03 | Crítica | `dgs.py` | Los `TypTr2` se fabrican con BT=0.22 kV, grupo Dyn5, uk=4 %, pérdidas y potencia mínima de 1 kVA. | Resultados de flujo, pérdidas y cortocircuito no son trazables al catálogo IGEA. |
| C-04 | Crítica | `model.py` | Un tipo ausente se reemplaza por distancia de edición/prefijo o por `DEFAULT`; la selección usa texto del código, no equivalencia eléctrica. | Sustitución silenciosa de R/X/ampacidad; riesgo de decisiones erróneas de carga y caída de tensión. |
| A-01 | Alta | `model.py` | `_float` y `_int` convierten texto inválido en cero/default; `_calc_p_q` solo modela plenamente `ValueType=2`. | Corrupción de entrada puede transformarse en parámetros físicamente válidos en apariencia; Q puede quedar en cero. |
| A-02 | Alta | `dgs.py` / `validate.py` | B1/B0 se conservan en memoria pero DGS escribe `bline=bline0=0`; `ElmXnet` deja vacíos los campos de cortocircuito. | Flujo capacitivo y estudios de falla incompletos; el corto circuito no es defendible científicamente. |
| A-03 | Alta | `model.py` | Las SED se detectan por sufijo regex de identificadores y cada carga coincidente crea una SED/transformador. | Falsos positivos, duplicación de transformadores y asociación semántica no demostrada. |
| A-04 | Alta | `batch.py` | La escritura no es transaccional. Se sobrescribe el DGS final antes de validar; ante excepción se elimina todo lo listado en `written`, incluso si reemplazó un artefacto previo exitoso. | Pérdida de un resultado bueno y exposición de salidas parciales/fallidas. |
| A-05 | Alta | `validate.py` | La referencia del validador es el mismo `FeederModel`; no existe comparación independiente de P/Q, impedancias por tramo, estados, fases y resultados CYMDIST↔PowerFactory. | Riesgo de validación circular: productor y oráculo comparten los mismos supuestos/errores. |
| A-06 | Alta | aceptación PF | 92/93 casos históricos pasan; IC103 diverge incluso tras ocho correcciones que incluyen desconectar cargas flotantes y escalarlas. | No hay aceptación completa; además, “hacer converger” cambiando el caso no equivale a validar el caso original. |
| A-07 | Alta | `dataset.py` | Nodos, fuentes, headnodes y cargas duplicadas se sobrescriben en diccionarios; filas con columnas extra se truncan; UTF-8 inválido se reemplaza. | Pérdida silenciosa de registros y baja trazabilidad de calidad de datos. |
| M-01 | Media | `model.py` | La conectividad ignora el estado de interruptores al buscar islas: todas las líneas se consideran conectadas. | Falsos “conectado” en topologías normalmente abiertas. |
| M-02 | Media | `inventory.py` | Cuenta “issues” por categoría, no número de filas afectadas; faltan rangos físicos, duplicados, NaN, unidades, fase y consistencia energética. | El resumen puede minimizar un problema masivo dentro de una sola categoría. |
| M-03 | Media | `geography.py` | Se valida cobertura y rango WGS84, pero no plausibilidad espacial, CRS correcto, outliers, orden de polilínea o discrepancia TXT/GIS. | Un CRS equivocado puede producir geometría plausible pero falsa. |
| M-04 | Media | `preview.py` | Identificadores de entrada se insertan en HTML/popups sin escape y el JSON se embebe dentro de `<script>` sin neutralizar `</script>`. | Riesgo de HTML/JS injection al abrir un export no confiable. |
| M-05 | Media | `batch.py` / `naming.py` | Los nombres de salida usan el nombre corto del alimentador; dos `NetworkID` distintos pueden colisionar. | Sobrescritura y manifiesto ambiguo en lotes multiempresa. |
| M-06 | Media | `gui.py` | Archivo monolítico de ~48 kB, rutas PowerFactory 2024/3.12 predeterminadas y manejo amplio de `Exception`. | Baja mantenibilidad y diagnóstico pobre ante variantes de instalación. |
| M-07 | Media | `tools/powerfactory_acceptance.py` | Herramienta crítica de ~2,400 líneas fuera del paquete y con numerosas capturas amplias de excepción. | La puerta de producción tiene alta complejidad ciclomática y puede degradar fallos a avisos. |
| M-08 | Media | empaquetado | Dependencias con límites inferiores, sin lock/hash; `ruff`, cobertura y tipado no forman parte del entorno de desarrollo. | Construcciones no reproducibles y regresiones estáticas no detectadas. |
| M-09 | Media | pruebas | No hay CI versionada visible, cobertura cuantitativa, fuzz/property tests, pruebas de archivos malformados ni matriz Python/PF/Windows. | Buena suite funcional, pero cobertura de fronteras y portabilidad insuficiente. |
| B-01 | Baja | `export_tables.py` | Excel/TSV son proyecciones del DGS, no una fuente independiente; tablas vacías pierden cabeceras porque `_ordered_fields([])` retorna vacío. | Menor utilidad de auditoría y contratos tabulares ambiguos. |
| B-02 | Baja | `schema.py` | El perfil JSON asegura nombres/campos, pero no contiene restricciones semánticas, unidades, cardinalidades ni migraciones. | “Schema válido” no implica objeto PowerFactory físicamente válido. |

## Diagnóstico por módulo

### `dataset.py` — ingestión

Fortaleza: lectura única y estructura simple, determinista y fácil de probar.  
Vacíos: no hay contrato formal por tabla, validación de encabezados obligatorios, detección global de duplicados, control de columnas sobrantes, registro de líneas rechazadas, detección de delimitador/codificación ni hashes de entrada. El uso de `errors='replace'` y diccionarios con asignación directa oculta anomalías. Debe producir un informe de ingestión con archivo, sección, línea, columna, valor, regla y severidad.

### `naming.py` — resolución de nombres

Fortaleza: resuelve nombre completo, nombre corto y tokens, detectando ambigüedad en la selección.  
Vacío: esa protección no llega al nombre de archivo. Se necesita un identificador de salida estable y único, por ejemplo `<short>__<hash-network-id-8>` cuando exista colisión.

### `inventory.py` — perfilado de datos

Fortaleza: buen primer control de completitud referencial.  
Vacíos científicos: distribuciones de R/X/B/ampacidad/longitud/P/Q/factor de potencia; detección robusta de outliers; porcentajes de faltantes por campo; fases; componentes conexas considerando maniobras; balance entre demanda total, kVA conectado y energía; catálogo realmente usado; sensibilidad de cada fallback.

### `model.py` — modelo de dominio

Es el módulo de mayor riesgo. Mezcla normalización, imputación, inferencia semántica y creación física. Debe separar:

- dato observado;
- dato derivado con fórmula y unidades;
- dato imputado con método/confianza;
- supuesto del usuario;
- valor predeterminado de visualización;
- error bloqueante.

La sustitución textual de conductor y la síntesis de transformador no deben ser rutas de producción automáticas. Deben requerir aprobación o ejecutarse en un modo exploratorio marcado como no apto para estudios.

### `geography.py` — transformación espacial

Fortaleza: usa `pyproj` con `always_xy=True` y valida cobertura básica.  
Vacíos: verificar que el CRS fuente tenga unidades lineales compatibles o transformar a un CRS métrico antes de medir; usar distancia geodésica cuando corresponda; contrastar longitud GIS/TXT mediante razón, mediana, MAD y umbrales por clase; detectar coordenadas (0,0), duplicadas, saltos y cruces improbables.

### `dgs.py` — serialización y representación PowerFactory

Fortaleza: FID determinista, referencias explícitas, perfil versionado y capa gráfica reproducible.  
Vacíos: preservar fases, modelos de carga, parámetros de secuencia y shunt con unidades verificadas; importar transformadores reales; fuente de cortocircuito; frecuencia configurable; BT configurable; equipos reguladores/capacitores cuando existan placements. Constantes `NA205_*` y supuestos eléctricos impiden la universalidad declarada.

### `validate.py` — verificación estática

Fortaleza: controles amplios de FID, punteros, cardinalidades, cubículos, gráfica y conteos.  
Vacíos: independencia del oráculo; tolerancias/criterios eléctricos; conservación por fase; suma P/Q por alimentador; comparación de impedancia total; estados abiertos; validación dimensional; severidad diferenciada. `errors_total=0` debería significar “DGS estructuralmente consistente”, no “modelo validado”.

### `batch.py` — orquestación

Fortaleza: procesa alimentadores independientemente y genera manifiesto.  
Vacíos: transacciones por carpeta temporal + `os.replace`, hashes, versiones de Python/dependencias/esquema, tiempos, semilla/configuración, política de reanudación, colisiones, bloqueo concurrente y conservación segura del último resultado bueno.

### `cli.py` — interfaz backend

Fortaleza: comandos claros y códigos de salida 0/2.  
Vacíos: comando `validate` independiente, `--dry-run`, `--fail-on-warning`, exportación JSON de errores estable, selección de políticas de imputación y prohibición predeterminada de fallback físico. El valor CRS predeterminado es un ejemplo regional que puede utilizarse accidentalmente.

### `gui.py` — interfaz de escritorio

Fortaleza: flujo operativo completo y trabajo pesado fuera del hilo visual.  
Vacíos: separar controlador/servicios/vista, mostrar explícitamente supuestos críticos antes de convertir, tabla de anomalías por alimentador, no ofrecer “flujo corregido” como equivalente al caso original, detectar versiones PF/Python de forma robusta y probar cancelación/cierre.

### `preview.py` — inspección visual

Fortaleza: GeoJSON y mapa interactivo útiles para control humano.  
Vacíos: escapar HTML, serializar JSON seguro para contexto `<script>`, fijar integridad/versiones CDN o permitir modo offline, y mostrar capas de errores/outliers/fallbacks en lugar de solo la red final.

### `export_tables.py` — exportación analítica

Fortaleza: reutiliza el parser DGS y mantiene orden estable.  
Vacíos: diccionario de datos, tipos/unidades, hojas vacías con encabezados, límites Excel, protección frente a fórmulas al abrir CSV/Excel y un libro de control con resumen de calidad.

### `schema.py` y perfil JSON — contrato DGS

Fortaleza: desacopla encabezados del código.  
Vacíos: JSON Schema/metamodelo con tipos, unidades, nulos, referencias, cardinalidades, compatibilidad de versiones y pruebas reales por versión de PowerFactory.

### `tools/powerfactory_acceptance.py` — aceptación propietaria

Fortaleza: es una puerta real y supera ampliamente una prueba simulada; los artefactos históricos registran conectividad, GPS y convergencia.  
Vacíos: dividir adaptador PF, importación, estudios, correcciones y reportes; categorizar excepciones; registrar versión/licencia/caso activo; validar el caso original antes de correcciones; comparar KPIs antes/después. Cortocircuito, contingencia, OPF, RMS, armónicos y confiabilidad siguen incompletos o dependientes de licencia.

### pruebas y empaquetado

Fortalezas: 85 pruebas colectadas; buena cobertura funcional de estructura, geografía, DGS y dobles circuitos; pruebas unitarias del adaptador PF.  
Vacíos: CI, cobertura, type checking, lint, mutación, fuzz del parser, golden files independientes, escenarios desbalanceados, encoding/delimitadores, duplicados, CRS no métrico, colisiones y atomicidad. El fixture `\\mnt\data` debe evitarse o tener timeout/opt-in en Windows.

## Evaluación de los artefactos PowerFactory existentes

El resumen histórico reporta:

- 96 alimentadores solicitados: 93 convertidos y 3 stubs omitidos.
- 93/93 validaciones estáticas sin error.
- 93/93 importados/evaluados por la puerta PowerFactory.
- 92/93 con convergencia; IC103 no converge.

Esto demuestra compatibilidad operacional importante, pero no prueba equivalencia física. Además, varias correcciones de convergencia cambian el problema (poner cargas fuera de servicio o escalarlas). Deben reportarse dos métricas separadas:

1. `converges_original_case`;
2. `converges_after_modification`, con diff completo de objetos/atributos.

## Plan de cierre recomendado

### P0 — antes de usar resultados eléctricos

1. Corregir longitud: pasar `source_crs` al modelo, medir en unidades CRS verificadas o geodésicamente, y no reemplazar TXT salvo política explícita.
2. Implementar modelo por fase extremo a extremo y casos de prueba mono/bi/trifásicos desbalanceados.
3. Desactivar por defecto el auto-mapeo por texto y `DEFAULT`; exigir alias aprobado con R/X/B/ampacidad comparados.
4. Eliminar transformadores sintetizados de modo producción; leer catálogo/placement real o marcar SED solo gráfica.
5. Definir todos los `ValueType` con especificación CYMDIST y pruebas; valores inválidos deben fallar con ubicación exacta.
6. Hacer la salida transaccional y conservar el último resultado bueno.

### P1 — validación científica

1. Crear un conjunto dorado de 5–10 alimentadores con export CYMDIST y modelo PowerFactory revisado por ingeniero.
2. Comparar por elemento: fases, estado, longitud, R/X/B, ampacidad, P/Q, tensión, transformador y conectividad.
3. Comparar resultados: tensión por barra, corriente por tramo, pérdidas P/Q y cargabilidad; definir tolerancias antes de observar resultados.
4. Ejecutar análisis de sensibilidad de supuestos y cuantificación de incertidumbre.
5. Mantener validación independiente: no derivar esperado y observado de la misma función.

### P2 — ingeniería backend y datos

1. Contratos de ingestión, errores con procedencia y métricas de calidad.
2. CI Windows con Python soportados; lockfile; Ruff, Pyright/Mypy, cobertura y pruebas de mutación.
3. Separar GUI y puerta PF en servicios pequeños; logging estructurado con `run_id`.
4. Sanitizar preview y exportaciones; pruebas de seguridad con identificadores hostiles.
5. Versionar esquema, política de transformación y hashes de entradas/salidas en el manifiesto.

## Criterios de aceptación propuestos

- 0 sustituciones físicas no aprobadas.
- 100 % de elementos con fase preservada.
- 100 % de parámetros imputados acompañados de fuente, método, confianza y aprobación.
- Diferencia de conteos y conectividad = 0 contra oráculo independiente.
- Tensión, corriente y pérdidas dentro de tolerancias predefinidas frente a CYMDIST/PowerFactory de referencia.
- 100 % de casos originales convergentes o excepción técnica aprobada; no mezclar con casos corregidos.
- CI reproducible, cobertura de ramas crítica ≥90 % y cero fallos de lint/tipado en módulos de producción.
- Escritura atómica y recuperación probada ante fallo en cada etapa.

## Fundamento académico y técnico

La separación entre verificación (“construimos correctamente el software”) y validación (“construimos el modelo correcto para la realidad”) sigue el marco de Fisher y de Oberkampf & Roy. En este proyecto, las pruebas estáticas actuales son principalmente verificación; la validación requiere comparación independiente, datos reales y cuantificación de incertidumbre.

Kersting muestra que una red de distribución exige representar líneas, transformadores y cargas —incluido el comportamiento desbalanceado— con parámetros físicamente consistentes. Por ello, conservar solo conteos/topología no basta. La revisión de Dalavi et al. destaca que la calidad de datos y la ubicación de medidas afectan directamente la identificación topológica. Los trabajos de generación GIS revisados validan topología y viabilidad mediante flujo de potencia, precisamente la combinación que aquí debe ampliarse con equivalencia paramétrica y por fase.

### Tesis de maestría

- R. A. Chacón Correa, *Automated Generation of Synthetic Distribution Grids Based on Open GIS Data*, TU Darmstadt, 2024. Valida parámetros topológicos contra redes comparables y viabilidad mediante flujo de potencia. https://elib.dlr.de/210786/
- B. Özdamar, *GIS based modelling and analysis of unbalanced LV distribution networks with distributed energy resources*, Middle East Technical University, tesis M.S. Extrae datos GIS y construye el modelo mediante teoría de grafos para flujo desbalanceado. https://open.metu.edu.tr/handle/11511/44535

### Tesis doctoral

- *Predicting power distribution network characteristics and load profiles with limited operational data*, University of Strathclyde, tesis doctoral. Construye un modelo GIS con datos operativos reales y trata explícitamente redes con datos escasos. https://pureportal.strath.ac.uk/en/studentTheses/predicting-power-distribution-network-characteristics-and-load-pr/
- *Data driven modelling of distribution systems*, University of Sheffield, tesis doctoral. Estudia sistemas desbalanceados bajo conocimiento y medición limitados. https://etheses.whiterose.ac.uk/id/eprint/33810/

### Artículos científicos indexados

- F. Dalavi, M. E. H. Golshan y N. D. Hatziargyriou, “A review on topology identification methods and applications in distribution networks”, *Electric Power Systems Research*, vol. 234, 2024, art. 110538. DOI: https://doi.org/10.1016/j.epsr.2024.110538
- D. Sehloff et al., “PowerModelsDistribution.jl: An Open-Source Framework for Exploring Distribution Power Flow Formulations”, trabajo sobre formulaciones multifásicas y desbalanceadas. https://arxiv.org/abs/2004.10081
- “Automated generation of large-scale distribution grid models based on open data and open source software using an optimization approach”, transferencia de modelos a DIgSILENT y evaluación mediante escenarios de flujo. https://arxiv.org/abs/2202.13692
- D. H. Bailey, J. M. Borwein y V. Stodden, “Facilitating Reproducibility in Scientific Computing: Principles and Practice”. https://escholarship.org/uc/item/3xr3j874

### Libros

- W. H. Kersting, *Distribution System Modeling and Analysis*, 4.ª ed., CRC Press, 2018. https://www.routledge.com/Distribution-System-Modeling-and-Analysis/Kersting/p/book/9781498772136
- W. L. Oberkampf y C. J. Roy, *Verification, Validation, and Uncertainty Quantification in Scientific Computing*, Cambridge University Press, 2025. https://www.cambridge.org/core/books/verification-validation-and-uncertainty-quantification-in-scientific-computing/475235AB4076DC5F1F4FBE96D9671AF7
- M. S. Fisher, *Software Verification and Validation: An Engineering and Scientific Approach*, Springer, 2007. https://doi.org/10.1007/978-0-387-47939-2

## Conclusión

La base de ingeniería es valiosa y la aceptación real en PowerFactory es un activo poco común. El cuello de botella ya no es “generar un DGS”, sino demostrar que cada objeto eléctrico conserva significado, unidades, fase y parámetros del sistema fuente. La prioridad debe pasar de aumentar conteos de importación a construir trazabilidad física, oráculos independientes y manejo explícito de incertidumbre.
