# Plan — Spec 072

Lee: `docs/constitution.md` y `specs/072-pide-y-planeamiento-de-largo-plazo/spec.md`.

Se reutilizan `pide.py`, `pide_economia.py`, `tools/pide_pf.py`, `crecimiento.py`, 042/052, 046, 048, `informe_docx.py`,
`asistente/ejemplos_pide.py`, `pide_dataset.py`, `vnr_etl` y el perfil de empresa.

| Parte nueva | Cubre | Encaje |
| --- | --- | --- |
| Estudio de planeamiento: año de presentación, año 00, años | RF-1 a RF-4 | Contenedor sobre 030 |
| Contrato de fuentes de costos y adaptadores | RF-5 a RF-9 | Dentro de `pide_economia` |
| Metrados desde la red | RF-7, RF-15 | Alimenta F02, F08 y F13 |
| Proyección de mercado | RF-10, RF-11 | 031/046, puerta de entrada al escalado |
| Obras acumuladas por año | RF-12 | `tools/pide_pf.py`, en «Con proyecto» |
| Evaluación con y sin proyecto, F01 a F15 | RF-13, RF-14 | Amplía `pide_economia` |
| Generadores 4.1 y 4.2 | RF-13, RF-14, RF-16 | `informe_docx.py`, perfil de empresa |
| Herramientas y entrenamiento del asistente | RF-18, RF-19 | Coordinado con la spec 070 |
| COyM del perfil en la propuesta | RF-22 | `propuesta_pide(coym_pct_anual=)`, `formatos_pide._por_grupo`; lo pasa `web/services.py` |
| Tipo de análisis en la web (T17) | RF-29 a RF-38 | `estudio_planeamiento.tipos_de_analisis`, `GET /api/planeamiento/tipos`, `PideIn.plazo`, `TipoDeAnalisis.tsx` |
| SICODI en libro de cálculo (T18) | RF-39 a RF-41 | `costos_fuentes.leer_sicodi`, `_leer_libro_sicodi`, `HojaSicodi`, `TablaCostos.ambiguos` y `resolver`, `SUBFAMILIA_POR_TIPO`; `demanda_medida.iterar_filas_de_hoja`; `metrados.valorar_metrados` |
| Ratificación de la revisión C4 (T28) | RF-63 a RF-68 | `corpus_redaccion.tramos_de_documentos`, `_CODIGO_COMPUESTO`, `_PREFIJO_A_LA_VISTA`, `_patron_nombre`, `_LUGAR`, `catalogo_del_corpus`, `sin_encabezado`, `revisar_salida`, `_sellado_anterior` |
| Correcciones del rechazo del primer candidato (T27) | RF-58 a RF-62 | `corpus_redaccion.SISTEMA_REDACCION`, `SISTEMAS_REDACCION`, `DECODIFICACION`, `frase_repetida`, `repartir_documentos(fijos=)`, `sellar_corpus_redaccion(anterior=)`; `llm_runtime.texto_modelfile`; `llm_destilar.py publicar --redaccion`; `corpus_redaccion_pide.py --anterior` |
| Puertas del modelo de redacción (T26) | RF-53 a RF-57 | `corpus_redaccion.decidir_redaccion`, `revisar_salida`, `catalogo_sellado`, `puerta_interprete`; `llm_destilacion.medir_redaccion`; `ClienteOllama.redactar`; `tools/asistente_qlora.py evaluar` |

## Lo que halló la ratificación de la revisión C4 (T28, 2026-11-22)

El revisor independiente ratificó 922 de las 1 255 decisiones que propuso la revisión C4 repetida. Solo esas se
registran, con su revisor. Decisiones (las recomendadas):

- Códigos: se oculta entero un código con guion o subrayado que lleve una cifra o un subrayado. Las palabras compuestas
  («teórico-práctico») y los periodos («‹n›-‹n›») no son códigos. Lo que ya quedó a medias («YUS_‹n›») también se
  oculta, para que un segundo paso del anonimizado no deje la sigla a la vista.
- Nombres: en lugar de poner variantes en un catálogo (que tendría nombres reales), el patrón de cada nombre admite
  tildes, codificación rota y un final distinto. Además, los nombres que el propio corpus señala (tras «SET», una sede o
  un lugar) entran en el catálogo en cada sellado. Una palabra que el corpus escribe en minúscula no se recoge: así no se
  oculta «Distribución» por salir tras «zonal de». Ocultar de más es seguro; ocultar de menos filtra la red.
- Encabezado: se quitan las líneas «… – Mes ‹n›» y «Página ‹n› de ‹n›» del texto anonimizado. Un fragmento que solo
  traía eso no entra.
- Las reglas del maestro sobre el texto con las cifras ocultas (`MEJ31c_REDACCION/revisar_c4_maestro.py`) no sirven para
  decidir: su regla de «menos de 12 palabras» cuenta las cifras como palabras y rechaza las tablas al ocultarlas. Quedan
  como medida; lo registrado es lo ratificado.
- Con las particiones fijas del sellado anterior, selección y prueba se quedaban en 23 y 22 ejemplos: dos informes
  traen 1 227 de los 1 295. Decisión del coordinador: el sellado nuevo va sin `--anterior` (el candidato v1 ya está
  rechazado y no hace falta compararlo en las mismas particiones), y un documento mayor que la décima parte se parte en
  tramos seguidos de la centésima parte (RF-68). Cada tramo es un trozo seguido de una sección y va entero a su
  partición; los repetidos ya se quitaron en todo el corpus, así que un tramo de examen no repite un texto que entrena.
  Quedan 129 ejemplos en cada apartada.

## Correcciones del rechazo del primer candidato de redacción (T27, 2026-11-22)

El examen real rechazó el primer candidato por un caso de prueba: cifras y la misma frase encadenada. Decisiones (las
recomendadas):

- La causa del bucle está en el corpus: al ocultar los códigos, filas distintas de una tabla («Remodelación de troncal
  y ramales por antigüedad del alimentador A101», «… A102») quedan iguales y seguidas; 15 de las 704 respuestas selladas
  eran así, y es la frase que repitió el candidato. Se dejan fuera al sellar (RF-61) y se rechazan en las salidas
  (RF-60). Solo cuenta la repetición seguida: las filas parecidas de una tabla no se repiten enteras a continuación.
- Las respuestas selladas ya no traen dígitos (las 704 usan los marcadores; 526 llevan ‹n›), pero el prompt solo
  describía los marcadores: el nuevo los exige (RF-58). Cambia su huella, así que el corpus se sella de nuevo; el
  prompt anterior sigue leyéndose para examinar el candidato que ya se entrenó con él.
- Decodificación: `repeat_penalty` 1,15 sobre las últimas 256 fichas en Ollama (petición y Modelfile) y, con
  transformers, `repetition_penalty` 1,15 y `no_repeat_ngram_size` 8 (RF-59). Prohibir los dígitos al decodificar no es
  posible en Ollama y escondería el fallo del modelo, así que no se hace: la puerta de RF-54 sigue siendo la que decide.
- Más ejemplos: 1 901 decisiones del maestro eran «corregir C4» solo porque los nombres no se ocultaban. RF-49 ya los
  oculta; la revisión del maestro, repetida sobre el texto con los nombres ocultos y con sus mismas reglas
  (`MEJ31b_REDACCION/revisar_c4_maestro.py`), aprueba 1 255 (origen «maestro», fecha 2026-11-22). Se registran como
  decisiones nuevas del maestro, no como cambio del código, y entran en un sellado nuevo que conserva las particiones del
  anterior (RF-62): lo que examinaba sigue examinando.

## Puertas del modelo de redacción (T26, 2026-11-21)

Decisión (la recomendada, de ingeniería): de las puertas de 070 y 071 aplican a un modelo de redacción las que miden lo
que ese modelo hace, con su corpus y sobre la misma partición:

- 071:RF-4 (no empeorar al modelo en uso en la misma prueba) se traduce en la pérdida por token de la respuesta frente a
  la base NF4, que es lo que hoy redacta: en selección y en prueba, sin holgura (RF-53). Se mide con el adaptador porque
  Ollama no devuelve la verosimilitud de un texto dado; con el modelo de Ollama solo se examinan sus salidas.
- 071:RF-7 y RF-8 (turno de GPU común) aplican tal cual: la medida y la redacción van dentro de `turno_gpu`.
- 047:RF-8 (sin promover): el informe nunca promueve ni activa; publicar en Ollama no es activar.
- 071:RF-1 a RF-3, RF-5 y RF-6 son de la PINN y del reentreno automático: no aplican.
- 070 T22 (la prueba sellada del intérprete, 085) mide al modelo de órdenes. El modelo de redacción no lo sustituye: el
  puntero del intérprete no cambia y su prueba sellada no puede bajar por este ajuste. No se repite: si alguna vez se
  quisiera usar el candidato también como intérprete, se comparan los informes de `llm_destilar.py evaluar --parte
  prueba` del candidato y del modelo en uso (RF-56); sin ellos, no es activable como intérprete.
- Lo propio de la redacción (RF-54): ninguna salida deja nombres de empresa, sede o instalación (el anonimizador de RF-49
  con el catálogo del sellado, comprobado por su huella) ni códigos o cifras que no estén en la entrada
  (`contradicciones.cifras_sin_respaldo`, la lectura de cifras de 047:RF-52 y RF-53). Como las entradas son la
  instrucción fija de su uso, cualquier cifra de la salida es inventada.

Las salidas se generan con muestreo (temperatura 0,7, top-p 0,9) y la semilla de cada ejemplo: con instrucciones fijas,
la decodificación voraz daría una sola salida por uso y no examinaría nada.

## SICODI en libro de cálculo (T18, 2026-11-14)

- **El contenido decide.** `leer_sicodi` mira los bytes: OLE2 (.xls) o un zip con `xl/workbook.*` (.xlsx, .xlsm, .xlsb) es
  un libro; un zip con `Instalacion.txt` sigue por la lectura de siempre. El libro se abre con el lector común
  `demanda_medida.abrir_libro` (python-calamine) y se recorre con `iterar_filas_de_hoja`, que da las filas de
  `filas_de_hoja` una a una: una hoja del libro puede tener cientos de miles de filas. Descartado: openpyxl, que no lee
  .xls ni .xlsb, y un segundo lector de libros.
- **Cada hoja por sus cabeceras.** En las 30 primeras filas se busca una fila con los campos requeridos de una clase, con
  sinónimos normalizados (sin tildes, minúsculas y sin signos: `COSTO_MAT` = `COSTO MAT`). Clases, en orden: detalle de
  costos de inversión, costos de inversión, armados, materiales, recursos, mantenimiento, transformadores y rangos de
  corriente; sin cabecera, parámetros («etiqueta: | número»). Lo que no encaja va a `avisos` con su nombre y sus cabeceras;
  una tabla dinámica declara sus filtros (`HojaSicodi.filtros`). Descartado: reconocer las hojas por su nombre.
- **Ambigüedad, no elección.** En el libro del SICODI la clave de `Instalacion.txt` (código, tensión, secundario y
  sector) puede repetirse con costos distintos, porque un código vale en dos subfamilias (red aérea y red
  aérea de alumbrado público). Esas claves van a `TablaCostos.ambiguos` y solo las separa la subfamilia declarada o la
  que deduce el tipo. Descartado: quedarse con la última fila, que daba el costo de otra subfamilia sin avisar.
- **El tipo deduce la subfamilia (aclaración de RF-41).** Ninguna red declara la subfamilia del SICODI, así que
  `TablaCostos.resolver` usa la del tipo del elemento con la tabla universal `costos_fuentes.SUBFAMILIA_POR_TIPO`
  (palabras que la subfamilia lleva y no lleva: `tramo_aereo` → «red aérea» sin «alumbrado», `luminaria` → «alumbrado
  público» sin «red», `sed_aerea` → «sed aérea»…) y lo anota en `anotacion`. `valorar_obra` toma el `tipo` del elemento;
  `valorar_metrados`, `tramo_aereo` o `tramo_subterraneo` si el código solo tiene tramos de una clase. Si más de una
  candidata cumple, o el tipo no está en la tabla, queda la ambigüedad nombrada. Descartado: un `if` por empresa o por
  código, y elegir la primera candidata.
- **Pruebas.** Libro sintético con columnas sorteadas (`CSG_SICODI_SEED`), en .xlsx y .xlsm; .xls y .xlsb leen las
  muestras de `tests/fixtures/sicodi/`, que son el mismo libro sintético guardado por COM en los formatos 56 y 50, con
  autor, último en guardar, empresa, título e ICV vacíos y fechas fijas (`test_las_muestras_no_llevan_metadatos`); y
  `test_sicodi_real_en_libro` con `CSG_SICODI`, solo por el carril.

## Tipo de análisis (T17, 2026-11-11)

- **Una fuente para los tres tipos.** `estudio_planeamiento.tipos_de_analisis` arma horizonte, artículos, formatos, módulos y
  obras de cada tipo con la metodología (`config/pide_universal_2017.json`: `horizonte`, la `etapa` de cada artículo y su
  estado jurídico), los módulos de `informes_planeamiento.MODULOS` (qué módulo y qué formatos son de cada entregable),
  `escalera_optima.OBRAS_DE_LARGO_PLAZO` (098:RF-50) y `escalera_optima.periodo_de_corto_plazo(perfil)` (098:RF-37). La
  ruta `GET /api/planeamiento/tipos` lo sirve; la web no copia ninguna de esas reglas. Descartado: escribir los años y
  formatos en el TypeScript, que se desfasaría con la metodología.
- **Un solo «Planificar».** `PideIn.plazo` (`pide` o `largo_plazo`; sin él, lo de siempre) va a `services.pide_ejecutar`.
  Con `largo_plazo` se escriben solo los módulos del entregable «Plan de largo plazo» (`escribir_modulos(entregables=)`) y
  la petición con `implementar` se rechaza con 422. Con `pide` se escriben los dos, porque el PIDE consume el plan (RF-4).
  Sin año de presentación en la petición ni en el perfil, 422 antes de encolar. Descartado: una ruta por tipo, que
  duplicaría el diagnóstico y la cola.
- **La web guía, no sustituye.** `TipoDeAnalisis.tsx` va al principio de «Cargas en DIgSILENT»: el selector de los tres
  tipos, su ficha (norma, horizonte, obras, entregables) y sus pasos con estado y un botón «Ir al paso» que lleva a la
  sección existente (1 a 5). El tipo se pasa a `GemeloPIDE` (paso 5), que manda `plazo` y en largo plazo no aplica obras.
  Ningún paso se quita ni se oculta (regla del usuario: la web solo se mejora).
- Pruebas: `tests/test_tipos_de_analisis.py` (función pura y API, con dos años de presentación) y las de la web en
  `frontend/test/tiposDeAnalisis.test.mjs` (selector, pasos y cuerpo de la petición).

Fuentes públicas ubicadas el 2026-11-02, en Procesos Regulatorios de Osinergmin: SICODI y VNR al 31-12-2025 (Res. 184-2026-OS/CD);
VNR de Empresa B, fijación 2022 (Res. 186-2023-OS/CD). Falta el fichero de módulos estándar (Res. 152-2026-OS/CD; su base la sustituyó la Res. 181-2026-OS/CD, 2026-11-06): el
adaptador `costos_fuentes.leer_modulos_transmision` pide sus columnas declaradas y `valorar_obra` separa los ámbitos (T3); el
fichero real es T13. La base de la 152 trae una hoja por tipo de módulo y no dice la unidad: se leen las hojas declaradas, con la
unidad de cada una declarada (T13).

Asistente (T9): la tarea `pide` comprueba en `web/asistente_operacion._pide` el año de presentación y los libros que nombra la
orden antes de confirmar; el corpus de redacción (`asistente/corpus_redaccion.py`) solo admite revisiones humanas con uso
`redaccion` o `formato`, y exporta sin cifras.

Coordinación: `pide_economia` y `escalera_optima` también los toca la 073; se avisa la zona antes de escribir.

## P17: continuación anual autorizada (2026-11-08)

RF-23 a RF-28 se implementan en `pide.py` (contrato puro de proyección anual) y
el modo `anual` del guion existente `tools/pide_pf.py`. El modo de diagnóstico
por tasa existente se conserva y nunca sirve de alternativa silenciosa al anual.
El perfil materializado de demanda contiene P/Q por carga, alimentador, clase,
objetivo y año relativo; se verifica el archivo y la evaluación de aceptación
por sus huellas y por cobertura anual. No se entrena otro modelo ni se convierte
una predicción de 28 días de 089 en veinte años. La materialización científica
del horizonte anual sigue dependiendo de P16/031.

Los casos y escenarios se guardan bajo un identificador de estudio nuevo. Se
reutiliza `casos_del_anio` para copiar el estado previo con sus obras y se
reutilizan los escritores de carga del proyecto, con unidades y relectura. Las
obras son variaciones físicas identificadas por ruta, ya definidas por la vía
de obras existente; no se construye una red supuesta si falta su diseño.
La demanda por fases exige cobertura física compatible: un modo no representable
por el perfil materializado se bloquea, sin modificar la topología de origen.

Pruebas primero con `fake_pf`: continuación mayor que cuatro, acumulación sobre
copias anteriores, primera recaída, proyección P/Q distinta y relectura,
huellas/aceptación/cobertura ausentes, NaN, identidad ambigua, obra ausente o
insuficiente, error de guardado, interrupción y restitución de origen. Ninguna
de estas pruebas abre PowerFactory ni acredita la aceptación nativa de T14.

T13 se comprueba contra la carpeta exacta de la Res. 181-2026-OS/CD: se custodian
capturas y respuestas primarias actuales. La base antigua de la 152 se conserva
como antecedente y no se renombra como la 181. T9b y T11 mantienen su revisión
humana pendiente; P17 prepara un paquete de revisión con huecos y procedencia.

## Conexión anual web P17 (2026-11-08)

La ruta PIDE conserva el diagnóstico histórico por defecto y añade `modo=anual`
con DTO explícito. La carga de tres JSON (perfil anual, evaluación y evidencia de
corto plazo) conserva sus bytes y huellas en custodia del espacio; un perfil
derivado únicamente sustituye la referencia de evaluación por la custodiada y
registra esa transformación. Ninguna ruta anidada del cliente se abre.
Antes de encolar se verifican identidad completa, huellas, aceptación documental,
cobertura anual P/Q y obras físicas explícitas. El trabajo vuelve a verificarlas
antes del mismo `tools/pide_pf.py`, en el carril PowerFactory. Cancelar transmite
el protocolo cooperativo antes de conectar y siempre pasa por restitución.
La interfaz muestra fuentes, bloqueos, años, obras acumuladas y restitución;
no concede aceptación científica mediante un control. Las pruebas son API real
sin motor y render React, contrato generado, typecheck y build. La verificación
visual y la corrida nativa permanecen pendientes.

## Corrección de integridad de P17 tras revisión independiente (2026-11-08)

Sin ampliar la API ni cambiar RF-23 a RF-28: `tools/pide_pf.py` comprueba el
destino nuevo de AddCopy (clase, carpeta e identidad distinta del origen), los
retornos de activación/desactivación y el caso/escenario activos antes de escribir
o guardar. El escenario esperado acompaña internamente a cada copia; una
activación aparentemente correcta no permite escribir contra el original. El
finally del consumidor sigue restituyendo ambos contextos aunque falle crear.

El inventario de medición se relee con `Alimentadores`, incluyendo el terminal
conectado de cada carga. Se exige cobertura de las mismas cargas del alcance,
P/Q/fases/modos y escala del perfil; una maniobra dentro del alcance puede cambiar
su ruta si mantiene el servicio. Tensión y cargabilidad requieren unidad y medida
finita de cada elemento esperado; una clase vacía solo es válida si el inventario
no contiene esa clase. La lectura se limita al alcance elegido y admite Tr3 por su
atributo nativo, sin omitirlos por el lector histórico de Tr2. El dictamen de BT y
consumo reutiliza `comprobacion_flujo`; se añaden las guardias de conexión, consumo
P/Q disponible y tensión de cada fase con demanda explícita. Una falta de servicio
real es incumplimiento; un dato desconocido bloquea, sin convertirlo en cero válido.

La custodia anual usa `runtime_paths.staging_publicacion`: prepara los tres JSON,
perfil derivado y procedencia en privado, con referencias al destino final; publica
el directorio completo por rename. Un fallo de escritura/publicación no devuelve
un token utilizable ni afecta custodias anteriores. La cancelación se consulta
también después de preparar demanda y antes de cada obra/flujo posterior.
Si falla también el recibo de cierre de staging, se retiran solo los cinco JSON
propios antes de salir del intento fallido. Si rename ya publicó el conjunto
íntegro, un fallo posterior de ese recibo se registra y se entrega el token válido,
sin anunciar que no existe una publicación que sí terminó. Una obstrucción física
que impida retirar un fichero sigue siendo error de E/S y conservación administrada,
no una garantía de borrado ante un sistema de archivos inaccesible.

Regresiones CPU en `tests/test_pide_integridad.py`: escenarios originales de 50 kW
sin escritura/Save anual ante fallo/alias/proyecto ajeno; retirada de servicio,
cambio de demanda/representación y consumo ausente; mapas parciales/unidad y fase
sin tensión; custodia IO/rename fallidos y API 422; cancelación sin flujo adicional.
Positivas: ruta alternativa que mantiene servicio y grupo vacío de transformadores
cuando no existen. El doble anual declara medidas sintéticas de línea/BT/fases que
antes omitía: estas fixtures no acreditan resultados ni persistencia de PowerFactory.
T14/T13/T11/T9b y la aceptación científica/nativa permanecen abiertas.

## Procedencia de nuevas lecturas CAPEX (P04, 2026-11-08)

El adaptador `adaptadores/entrada/capex.py` usa la guarda pública
`adaptadores.fuentes_estables.abrir_fuente_estable` y entrega el mismo descriptor
readonly protegido al lector canónico `pide_economia.leer_capex`. El SHA sale de ese
descriptor; no se copia el libro ni se reabre una ruta entre huella y parsing. La
configuración y contexto de unidades se fijan antes del lector. El retorno histórico
de leer_capex y los cuerpos económicos quedan intactos.

Los tres bloques económicos de services (PIDE, escalera y costo expreso) transportan
el recibo junto con sus resultados. El memo conserva costos/recibo juntos y distingue
ruta/configuración/contexto; reutilizar costos no sella retrospectivamente otra
lectura. Los guiones pasan metadata a sus informes sin cambiar física o guardias.
DatosPlaneamiento añade solo un campo opcional en su flujo documental actual.

Pruebas CPU: controles con libros propios, escritor/reemplazo hijos durante lectura,
fuentes distintas, snapshot de configuración mutable, error de hoja y conservación
SHA/mtime; planes/resultados/JSON y documento real releídos. Comparación de valores
y funciones económicas contra base. Sin PF ni recálculo de elecciones reales.
Evidencia: `p04_procedencia_capex_20261108/HANDOFF.md` externo. No cierra
T14/T13/T11/T9b ni aceptación nativa, científica o económica del presupuesto.

## Segundo contraste de integridad anual (2026-11-08)

La revisión independiente reprodujo dos dictámenes inválidos: un terminal de la
carga fuera de servicio con resultados finitos antiguos, y una fase NaN del corto
plazo sin filas de proyección aunque los agregados fuesen finitos. El primero daba
completo en el ciclo CPU; el segundo podía iniciar flujo/copias antes de bloquear,
sin demostrar que terminase completo. `_comprobar_demanda_anual` valida antes de
modificar ComLdf o iniciar flujo P/Q, escala y las seis entradas por fase, sus
unidades MW/Mvar y la finitud de la demanda efectiva. Las fases cero siguen siendo
válidas. `_servicio_anual` añade incumplimiento por terminal conectado fuera de
servicio aunque sus medidas almacenadas parezcan servir la carga.

La misma revisión encontró una cancelación conocida tras la lectura interior que
no impedía el flujo corto. Se consulta después de las lecturas y antes de esa
medición. Todas las mediciones del ciclo reciben además el callback interno
`comprobar_cancelacion`, invocado justo antes de flujo tras la validación nativa.
La cancelación no interrumpe el motor ya iniciado y conserva el finally original.
No cambian la API/JSON públicos, los umbrales, los originales ni los dobles globales.
Pruebas negativas y control con demanda pequeña en r, Q cero y s/t cero en
`tests/test_pide_integridad.py`; las maniobras legítimas y la restitución anteriores
siguen verificándose. La falta de finitud inicial no se disimula con cero ni se
convierte en una restitución válida si su readback no puede confirmarse.

La evidencia CPU de `correccion_p17_segunda_revision_20261108` registra rojo/verde,
revisión exacta y límites; no acredita PowerFactory real, aceptación eléctrica,
ciencia ni T14/T13/T11/T9b. El fundamento académico del primer contraste se mantiene:
perfil servido, cobertura y conservación son criterios distintos de convergencia.
