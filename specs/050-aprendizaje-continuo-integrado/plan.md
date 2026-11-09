# Plan — Spec 050

La petición del usuario autoriza continuar la implementación integral según SPEC.
Se conserva el trabajo de 047 T7: la memoria insuficiente no se resuelve declarando
un alumno ya entrenado. Primero se exige una ejecución generativa local válida.

## Arquitectura y situación comprobada

| Responsabilidad | Código existente | Brecha que debe cerrarse |
| --- | --- | --- |
| Evidencia nativa y captura | `digital_twin/episode.py`, `buffer.py`, `integration.py` | Instantánea común y trazabilidad entre familias |
| Planificación y lenguaje | `asistente/interprete.py`, `plan.py`, `ollama.py` | Alumno generativo entrenado y evaluación conjunta |
| Preparación desde referencia | `asistente/llm_destilacion.py` | Disparador por cambio validado, no por texto autogenerado |
| PINN/GNN y aprendizaje activo | `digital_twin/oraculo.py`, `escenarios.py`, servicios del gemelo | Coordinar dominio, revisión y publicación con las demás familias |
| RNN/GRU y series | `digital_twin/temporal.py`, `series_causales.py` | Misma instantánea, fecha de corte y evaluación causal |
| Evolutivos/PNL | `digital_twin/evolutivo.py`, spec 048 | Vincular propuestas a versiones y evidencia nativa |
| Recuperación | `asistente/indice.py`, spec 047 T2 | Benchmark real del reranker y versión de corpus |
| Entrenamiento y registro | `training_coordinator.py`, `model_registry.py`, `tools/reentrenar_modelos.py` | Incluir alumno T7 y publicación conjunta coherente |
| Disparador automático | `asistente/vigilancia.py`, spec 027 | Un ciclo idempotente común y cancelable, no entrenamientos independientes |

No duplicar estas piezas ni declarar resuelto un adaptador por mapear su nombre
a GRU. Mantener bloqueos explícitos de NHITS/TFT/PatchTST hasta su implementación
en 046. El coordinador actual ordena siete etapas; ordenar no demuestra que todas
compartan datos, contextos o versiones compatibles.

## Secuencia de implementación

### Conexión de productores y cola P19 (2026-11-08)

La fuente congelada `procedencia` es un JSON con esquema
`convertersmartgrid-learning-provenance-v1` y `referencias[fuente][record_id]`.
Cada referencia contiene `contexto`, `fuente_hash`, `registro_id`, `instante` y
`contenido_hash`. Se verifica el contenido real leído por el productor y que la
fuente de la observación esté custodiada en la captura. La identidad de observación
usa la referencia original, sin familia/etiqueta/partición. Los registros legacy
sin referencia no reciben fechas, identidades ni verdades físicas inventadas.
Dataset v2, episodios y ventanas temporales emiten Muestra usando sus lectores y
particiones vigentes. Preparación obligatoria en CLI, también al reanudar: las
particiones distintas bloquean antes de GPU. El corpus generativo reutiliza
`leer_particion_real`; embeddings comparte el lector real de consultas con su
trabajador y conserva maestro/humano por separado. `evolutivos_casos` declara
episodio, contexto043 completo, problema bancos/maniobras, partición, parámetros
y normalización. El trabajador usa las factories existentes sobre ese grafo y
registra una configuración/evaluación RECHAZADA, sin afirmar ajuste de pesos ni
reapertura de un modelo entrenado. Su flujo mallado no sustituye contraste nativo.
Sin esos datos concretos, cada adaptador deja un bloqueo visible.

El contexto documental tiene esquema y huella independientes; el agregado conserva
por separado los mapas físicos y documentales. Una muestra física exige pertenecer
al mapa físico. No se modifica ContextoExperimento043.

`CSG_AUTOENTRENAMIENTO=1` requiere además `CSG_APRENDIZAJE_PLAN`. El plan tipado
declara espacio, fuentes, contexto, familias, política y presupuesto; no contiene
código ejecutable. El callback común usa JobManager.submit en engine y deduplica
solicitudes vivas. La cancelación de JobContext llega al ciclo mediante un marcador
propio, comprobado entre etapas. No mata procesos ni toma una licencia nativa.
La ausencia de plan/datos se registra como bloqueo, sin caer a entrenamiento individual.
El callback devuelve False cuando no se admite la solicitud: vigilancia permite
reintentar ese mismo lote tras corregir el plan. Los avisos piden preparar un ciclo;
no anuncian un entrenamiento que aún no empezó. `--solo-preparar` genera diagnóstico
CPU de cada familia y contraste de las particiones comunes, sin crear trabajadores.
La admisión se pospone mientras haya trabajos del operador vivos en cualquier carril;
la cola engine por sí sola no cubría el carril PowerFactory. Se vuelve a solicitar
con los mismos datos después de liberarse, sin ejecutar un motor nativo en la prueba.

Captura PINN: `twin` debe ser una vista de datos declarada con únicamente `objetos/`
y episodios JSON. `--forzar` consume esos objetos; el índice SQLite se genera en su
carpeta de trabajo. Una raíz viva con modelos, model_registry, SQLite/WAL, decisiones
u otros extras se rechaza ANTES de copiar: no se excluyen silenciosamente. La misma
guardia protege la copia de trabajo de snapshots previos; su verificación histórica
conserva identidad y bytes. La referencia del modelo anterior es responsabilidad
explícita del conjunto/plan de captura: no se presenta ausencia de pesos en la vista
como prueba de retención ni aceptación de un primer modelo. No publicar sin T4b.
Un primer candidato sin modelo previo conserva `retencion_acreditada=false`. Si hay
conjunto previo, `referencia_pinn` debe sellar esquema `convertersmartgrid-pinn-reference-v1`,
candidate_id y conjunto_id exactos; el lector verifica artefactos y compara esa
referencia antes/después de la etapa. Una ausencia o cambio bloquea. Un modelo
individual previo sin adaptación conjunta explícita también bloquea, sin presentarlo
como un arranque desde cero. Verificar referencia no equivale a medir retención.

El plan JSON usa esquema `convertersmartgrid-learning-plan-v1` y declara exactamente
`workspace_id`, `raiz`, `contexto`, `fuentes`, `familias`, `politica_hash`, `tiempo_s`,
`memoria_gib`, `usa_gpu`, `parametros`, además de `schema`. Rutas relativas se resuelven
contra su carpeta. Las únicas opciones de parámetros son semillas, zona_horaria,
cadencia_min, horizontes y embedding_model. No admite comandos. La orden revisable es
`python tools/aprendizaje_continuo.py plan --archivo <plan.json> --plan-hash <sha256> --solo-preparar`.
Quitar `--solo-preparar` ejecuta entrenamiento solo después de las puertas y presupuesto.

### Manifiestos reales de procedencia y contexto (T6, RF-11 a RF-21)

`tools/preparar_ciclo_aprendizaje.py` escribe en `--salida`, que debe ser nueva o estar vacía:
`procedencia.json`, `contexto_ciclo.json`, `cuarentena.json`, `vista_twin/objetos/` y
`preparacion.json` con las órdenes `congelar` y `ciclo --solo-preparar`. Las dos órdenes llevan
los mismos parámetros, de modo que `congelar` y `ciclo` resuelven la misma instantánea y no
duplican la copia (`huella_parametros_ciclo`). Descartado escribir junto a las fuentes: son
almacenes reales. Descartado un módulo nuevo de `src/`: la composición es del borde; las reglas
de lectura siguen en los productores, que exponen lo que la herramienta y ellos comparten
(`consultas_recuperacion`, `series_de_aprendizaje`, `ventanas_de_aprendizaje`, `contenido_de_ventana`).

Referencias por fuente. `dataset`: las órdenes y los informes se cotejan por texto y fecha exactos
con las observaciones declaradas (`--observaciones`); la fuente es ese fichero y el contexto, su
huella documental. Consultas de recuperación: la parte del dataset y su fecha de sellado.
`twin`: el fichero inmutable del episodio es la fuente congelada, porque la huella de la fuente
(`source_fingerprint`) combina varios TXT y no es la de un fichero custodiable. `llm_dataset`: la
parte sellada y su fecha de sellado. `cabeceras`: el libro, con la identidad 043 vinculada a la
serie. `evolutivos_casos`: el episodio del caso, con el `contexto_043` que declara el caso.

Identidad 043. Se compone con `ContextoExperimento`, nunca con un subconjunto de campos. El mapa
usa la clave `<proyecto>#<huella corta>` porque un proyecto tiene varios casos y escenarios, cada
uno con su contexto. Un periodo de forma `{clientes, maxima, status}` toma `maxima`, que es el mes
de la cabecera. Descartado un contexto físico parcial con esquema propio: pasaría la comprobación
«falta contexto físico 043» con algo que no lo es. Queda como decisión del integrador si la
captura debe empezar a guardar `profile_hash` y el periodo.

Vínculo serie-contexto: el complemento declara `series` o se usa el único contexto de rol
`caso_base` cuyo alimentador coincide con la hoja según `hojas_del_alimentador`. Varios o ninguno
van a cuarentena. La guarda «objetivos apartados» de `muestras_aprendizaje` no se toca; la
herramienta la reproduce con los motivos del lector.

### Decisiones del integrador para las siete familias (T7, RF-22 a RF-30)

GRU: `objetivos_del_ciclo` pregunta a `cargar_cabeceras` qué series y qué tramo valen y toma las curvas de
`objetivos_de_cabecera`; el trabajador recibe `--tramo-comun` para consumir lo mismo. Descartado copiar sus reglas: serían
dos criterios otra vez. Con `pares`, la guarda sigue dura. Captura: `identidad_de_captura` da periodo, criterio y huella del
perfil al plan de acciones y de escenarios; `construir_episodio` los pone en la lectura de escenarios, que no los trae.
Lenguaje: `tools/unir_dataset_lenguaje.py` usa `particionar_dataset` y bloquea si algo cambia de partición. Evolutivos:
barras de `banco_en` y `enlaces` de la escalera, módulo y costo del perfil, banda de la norma; normalización con ideal cero y
nadir medido o inversión máxima, y un caso por proyecto, problema y partición de la observación en la vista PINN.

### Contratos de integración concretados el 2026-11-07

RF-1/T1b: un ciclo de varios proyectos usa un mapa ordenado de identidad de proyecto
a huella de su contexto 043. `ContextoExperimento` conserva su contrato individual.
`crear_contexto_ciclo(proyectos)` devuelve un manifiesto con esquema, mapa y huella
agregada; se conserva en la instantánea y se comprueba al releerla. No se inventa un
proyecto único. Cada muestra conserva su contexto individual, que debe pertenecer
al mapa declarado. Cambiar un miembro cambia la identidad de la instantánea.
Las capturas de varios proyectos usan esquema de instantánea v2: quitar el mapa
se detecta; las capturas v1 conservan su identidad y lectura originales.

RF-2/T2b: `crear_observacion_id(contexto_hash, fuente_hash, registro_id, instante)`
calcula la identidad sin familia, partición ni snapshot. El instante exige zona
horaria explícita y se normaliza a UTC; no se presume la zona de la máquina.
Los productores usan la misma referencia a la observación fuente, nunca el hash
de su etiqueta o representación como sustituto. Una repetición idéntica de un
registro no aumenta su peso. Una identidad de registro con contenido incompatible
bloquea y se conserva para revisión; el replay no incorpora pruebas al entrenamiento.
Estos contratos no cierran T1b/T2b sin la preparación sobre fuentes reales.

RF-4/RF-7: `publicar_individual=False` en PINN y competición temporal registra el
candidato y su aprobación individual sin cambiar punteros. Los CLI admiten
`--sin-publicar`. El estado terminal de la decisión conserva el vocabulario 043;
`promovido=False` y `publicacion_pendiente=True` distinguen la activación pendiente.
El ciclo GRU usa la competición actual, con cadencia y horizontes declarados,
sin repetir algoritmos. Sus modelos salen a una carpeta de ejecución; la PINN
recibe una copia verificada del búfer para escribir índice/modelos sin alterar la
instantánea. También se comprueba la instantánea al terminar las etapas.
Semillas, zona horaria, cadencia, horizontes y modelo de embeddings entran en la
identidad de la captura mediante `parametros_ciclo`. Un preflight sin memoria
permanece bloqueado y reintentable antes de entrenar; no sella como hecho el ciclo.

El ajuste de lenguaje sobre dataset v2 registra ahora candidatos aislados y reabre
sus pesos en un proceso nuevo, usando el mismo contrato del consumidor. Selecciona
solo con validation; test queda reservado para evaluación. Las órdenes humanas se
miden solo con gold_human: un episodio gold_native no cuenta como una orden del
operador. Informes y órdenes tienen vistas separadas. Exige las puertas de órdenes (tarea, F1 y reales) o de
ambos niveles de informes (tipo y subtipo, 0,90 en cada uno), y no retroceder frente
al modelo en uso sobre la misma prueba. El clasificador elige semilla por el menor
acierto de sus dos niveles en validation, antes de abrir test. Las rutas heredada,
gobernada y v2 comparten METRICAS_INFORME; ninguna ignora un tipo incorrecto.
Sin prueba real, medida válida o recarga correcta se conserva un candidato rechazado.
En órdenes reutiliza además decidir_promocion del protocolo integral: cobertura
de todas las tareas, referencia por tarea y rechazo de mensajes reservados; los
promedios no sustituyen esas puertas. El constructor incorpora informes.jsonl:
confirmados/corregidos son humanos; generados son contexto y maestro queda en
cuarentena. Etiquetas humanas contradictorias del mismo texto se conservan en
cuarentena con motivo, sin elegir según el orden de llegada.
El adaptador de órdenes traduce también las anotaciones históricas
`[inicio,fin,tipo]` a pares literales sin reinterpretar la etiqueta. Conserva una
huella de las anotaciones originales. Un rango, tipo o valor inválido deja la
orden en cuarentena; no se borra el dato y se presenta como ausencia de entidades.
Una revisión humana posterior conserva origen inicial, IDs y hashes del registro
y archivo revisados; confirmar R1–R5 no aprueba otras filas del archivo. El control
de rutas recorre los textos estructurados antes de serializar: un encabezado con
salto de línea no se confunde con una ruta por el escape JSON.
El runner pasa el registro común explícitamente; `PROMOVIDO` en la decisión del
registro acredita puertas, mientras `promovido=false` y `publicacion_pendiente`
conservan la activación para el conjunto. La corrida individual de órdenes del
2026-11-07 entrenó y reabrió en CUDA, pero quedó RECHAZADA por calidad/cobertura;
no acredita la campaña conjunta ni aceptación funcional del asistente.

RF-4/RF-10, control web: GET `/api/asistente/aprendizaje` conserva las siete fases.
POST `/api/asistente/aprendizaje/{clave}/cancelar` reutiliza `cancelar_ciclo`; la clave
es SHA-256 canónico validado también en la función compartida y CLI. Escribe un
marcador atómico solo si el ciclo está en curso; repetir conserva el primer pedido.
La respuesta tipada distingue `solicitada` de la terminación del ciclo. El panel
ofrece cancelar al consultar un ciclo en curso y muestra que termina su etapa,
sin declarar cancelado el entrenamiento antes de que el coordinador lo confirme.
El ciclo publica su diario en curso antes de ejecutar la primera etapa para que
la consulta y la cancelación usen su identidad real. La CLI devuelve `solicitada`
en lugar de anunciar `cancelado` al escribir el marcador.
No inicia ciclos, no cambia modelos y no cancela procesos de otros proyectos.

RF-7: los nuevos conjuntos usan esquema v2 y su identidad cubre miembros,
instantánea, ciclo, retención y evaluación conjunta. Los v1 conservan su lectura
y bytes, con el alcance de integridad anterior. Una familia ausente de un conjunto
configurado bloquea, sin recurrir a un puntero individual. `miembro_del_conjunto`
resuelve el candidato por su SHA-256 exacto entre los registros declarados de la
familia 043 y verifica sus artefactos; así GRU puede referenciar
`pronostico_cabecera` sin fingir otro registro. No se publica un conjunto vacío.
La reversión comprueba el manifiesto destino antes de cambiar el puntero vigente.

Consumidores: lenguaje y PINN consultan el miembro del conjunto antes del puntero
individual. La materialización común del registro verifica todos los artefactos,
incluida una copia ya existente; no reescribe el puntero heredado ni mueve el
original. PINN conserva una carpeta local identificada por el SHA-256 del candidato
para que la carga y sus metadatos de herencia usen la misma identidad. Las acciones
individuales de lenguaje/provisional/reversión y la promoción PINN se bloquean
cuando hay conjunto activo: no pueden anunciar un cambio sobre un puntero ignorado.
Sin conjunto configurado se conserva el comportamiento anterior, incluido el
provisional autorizado por 085. La competición temporal compara contra el miembro
GRU verificado y su clase; no se intercambia un pronóstico multihorizonte por la
reconstrucción histórica a un paso de 024/046. Falta la campaña conjunta real.

### Ejecución

1. Auditar fuentes, series, episodios y modelos reales disponibles. Congelar los
   archivos necesarios en el directorio del ciclo y registrar hash de contexto 043.
   Copiar datos, no punteros activos; verificar copia y detectar cambios de origen.
2. Preparar vistas por familia con IDs de observación comunes: lenguaje anotado,
   ventanas causales y grafos nativos. Cuarentena para contradicciones, ausencias
   o etiquetas procedentes únicamente de una predicción. Mantener pruebas reservadas.
3. Ampliar el coordinador y la vigilancia existentes. Cada etapa consume la misma
   instantánea inmutable y escribe candidatos aislados del modelo activo. Ejecutar
   familias en secuencia de recursos, con lock GPU y turno nativo existentes.
4. Evaluar candidato y versión vigente con el mismo conjunto reservado y casos
   históricos. Exigir umbrales, retención, confirmaciones y reapertura. No transferir
   acierto lingüístico a aceptación física ni mezclar métricas de familias distintas.
5. Publicar un manifiesto de conjunto compatible referenciando candidatos del
   registro único. Cambio atómico del conjunto tras aprobación; conservar anterior.
   Los consumidores deben resolver sus versiones desde ese manifiesto, no tomar
   arbitrariamente el último modelo individual.
6. Cerrar el ciclo con readback web/CLI y una segunda captura real. Confirmar
   deduplicación, actualización por datos nuevos, rechazo de regresión, cancelación
   y reversión. Documentar coste, latencia y decisiones verificables, sin simular éxito.

## Pruebas requeridas antes del cierre

RF-4/RF-10, exclusión y propietario (2026-11-08): la guardia OS por clave de ciclo
se adquiere antes de leer el diario y ejecutar el preflight, también con etapas CPU.
Reutiliza la misma operación de bloqueo de archivo que la GPU; su archivo permanece
y cerrar el descriptor o morir el proceso libera el turno. La marca nueva contiene
PID, fecha real de creación y token propio; solo se retira la marca del mismo
arranque. Los PID heredados siguen leyéndose de forma conservadora. Una identidad
con fecha distinta se trata como interrumpida; una marca ilegible se conserva y
bloquea, sin anunciar entrenamiento activo. La consulta no reescribe el diario.
La exclusión se prueba con dos clientes concurrentes antes de escribir la marca,
un proceso real que termina sin finally, recuperación y conservación de sus datos.
Esto no acredita la campaña conjunta ni la calidad de sus modelos.

La ruta GPU por defecto se resuelve en un único sitio, fuera del TEMP particular
del trabajo: conserva el nombre histórico en Temp estándar del perfil Windows
(y /tmp en POSIX). CSG_ML_GPU_LOCK explícito sigue teniendo prioridad y los hijos
reciben su ruta absoluta para que cambiar de directorio o temporal no cree otro
turno. El coordinador, trabajadores y todos los lanzadores usan esa resolución.
Dos procesos reales con TEMP distintos deben competir por la misma guardia;
la prueba usa un perfil local aislado y no ejecuta CUDA. Una versión anterior que
personalice TEMP necesita la misma ruta explícita si comparte el recurso durante
la transición.

Contrato: `tests/test_aprendizaje_continuo.py`, con citas `050:RF-n`.
Integración real: `tests_ml/test_aprendizaje_continuo_real.py` y evidencia local de
los trabajadores; no usar mocks ni skips para acreditar operaciones de modelos.
Regresiones: coordinador, registro, vigilancia, series causales, gemelo y asistente.
No ejecutar dos trabajos CUDA simultáneos para intentar acelerar la aceptación.

Casos de rechazo: fuente/contexto distintos; cambios durante preparación; prueba
reciclada como entrenamiento; etiqueta eléctrica inventada; adaptador ausente;
etapa que termina sin informe; regresión histórica; promoción individual antes del
conjunto; reinicio o cancelación entre publicación y readback.

## U0: fronteras antes de la migración 002 (2026-11-08)

La integración de productores introdujo 38 violaciones no registradas: 4 cruces de
capa, 32 aristas de ciclo y 2 accesos privados. La guarda real test_capas lo reproduce;
no se amplía su lista de 37 excepciones históricas ni se oculta un import calculándolo.

Se extraen los contratos puros (Muestra, CicloBloqueado, familias, esquemas e identidad)
a contratos_aprendizaje, con un único dueño. TrainingCoordinator solo importa desde
allí el orden de familias; sus guardias OS/PID/GPU no cambian. Los consumidores ML
leen el conjunto mediante conjuntos_aprendizaje, que conserva verificación de
punteros/candidatos/artefactos, sin depender del módulo que prepara los productores.

La aplicación recibe ProductoresMuestras; ProductoresReales compone por imports
literales los mismos productores y lector v2. El CLI, las etapas y la entrada de plan
usada por vigilancia inyectan esa composición, sin cambiar planes, presupuesto,
autoentrenamiento apagado por defecto, cola ni puertas. Las llamadas Python directas
a preparar_fuentes/preflight_ciclo deben aportar el puerto explícito. La vista PINN
sale del búfer a un productor independiente y usa muestras_y_particiones del oráculo:
hay una sola regla de partición y SQLite no se inicializa al leer la captura.

Las pruebas caracterizan las dos entradas operativas, la identidad observacional,
contratos de etiquetas/particiones/contexto y lectura independiente del conjunto en
otro proceso; se comprueba también resolución de la clase Muestra de pickles previos.
Las reexportaciones puntuales de tipos/lectores públicos en aprendizaje_continuo
mantienen consumidores existentes; su retirada física pertenece a 002 T9, no se
declara terminada aquí. No se cierran 002 T7/T9/T12 ni 050 T1b–T5b por el AST o las
pruebas CPU; las aceptaciones nativas/científicas y campañas siguen pendientes.
