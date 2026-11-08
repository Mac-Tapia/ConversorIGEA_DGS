# Harness integral para LLM y modelos eléctricos

Fecha: 2026-11-08, America/Lima. Responsable: Codex /root. Tarea: HARNESS-20261108.
Estado: diseño aprobado por el usuario el 2026-11-08; ejecución documentada en
[uso y entrega](2026-11-08-harness-integral-modelos-uso.md). Ganancias sin demostrar.
Base inspeccionada: `main`, `5617251012f39193297e19b299d8a179a8fe1f61`,
`D:/converter/ConversorIGEA_DGS`.

## 1. Decisión del usuario y resultado esperado

El usuario pidió reforzar los LLM y modelos entrenados mediante harness engineering
procedente de GitHub para aumentar precisión y recall. Seleccionó expresamente
«Ambos: LLM y modelos eléctricos». El alcance integral queda elegido; las decisiones
técnicas siguientes son propuestas del responsable, pendientes de aprobación.

El resultado será un ciclo reproducible de medir, localizar fallos, preparar una
mejora, entrenar cuando corresponda, comparar y decidir su promoción. El harness
no mejora pesos por sí solo. No se prometerá un porcentaje de mejora sin campaña
independiente. Las métricas de recuperación, extracción, clasificación, pronóstico
y flujo conservarán significados y denominadores distintos.

## 2. Enfoques y selección

| Enfoque | Ventaja | Coste o límite | Decisión |
| --- | --- | --- | --- |
| Solo lm-evaluation-harness | Benchmarks repetibles del LLM y adaptadores | No cubre pronóstico ni aceptación eléctrica | Insuficiente para el alcance elegido |
| Harness local integrado con adaptadores GitHub opcionales | Reutiliza las puertas del proyecto y cubre ambas áreas | Requiere contrato común de casos y resultados | Recomendado dentro del alcance integral elegido |
| Sustituir el entrenamiento por una plataforma externa completa | Centraliza herramientas | Migración, dependencias y duplicación de contratos existentes | Descartado para la primera versión |

El núcleo de evaluación seguirá siendo local. EleutherAI se usará para comparación
del modelo de lenguaje; Promptfoo, para suites de prompts/acciones; Ragas, como
evaluador auxiliar de respuestas sustentadas. No serán tres autoridades de promoción:
sus resultados se importarán y validarán contra el mismo protocolo local.
No se instalarán estas dependencias en el núcleo obligatorio del conversor.

## 3. Qué existe y qué falta conectar

Inspección de código, sin ejecutar una campaña ni acreditar su aceptación:

| Contrato existente | Archivo | Uso propuesto |
| --- | --- | --- |
| Cuatro particiones, grupos, políticas con huella y puertas por familia | `src/convertersmartgrid/evaluacion_modelos.py` | Reutilizar y añadir métricas nuevas mediante política versionada |
| Casos de órdenes con VP/FP/FN, acierto y F1 | `src/convertersmartgrid/asistente/aceptacion.py` | Publicar precision/recall con soporte y evaluar por tarea |
| Corpus y prueba del LLM condicionada a selección sellada | `src/convertersmartgrid/asistente/llm_destilacion.py` | Conservar selección, digest de modelo y custodia |
| Independencia por tarea y validación cruzada | `src/convertersmartgrid/asistente/validacion_cruzada.py` | Conservar separación por grupos y no convertir sintéticos en humanos |
| Evaluación temporal y política predeclarada | `src/convertersmartgrid/digital_twin/evaluacion_temporal.py` | Adaptar sus resultados, sin duplicar fórmulas ni cambiar sus puertas |
| Entrenamiento secuencial y bloqueo GPU | `src/convertersmartgrid/training_coordinator.py` | Usar un turno y el mecanismo de exclusión vigente en el corte de integración |
| Registro y promoción con reapertura | `src/convertersmartgrid/model_registry.py` | Mantenerlo como única vía de promoción y conservar candidato rechazado |
| Fuentes GitHub ya fijadas para modelos eléctricos | `docs/UPSTREAM_IA_LOCK.json` | Reutilizar PowerFlowNet, NeuralForecast y demás candidatos existentes |

Las specs 043–048 y sus límites conservan autoridad. Este documento no cambia su
estado. Al integrar, se revalidará sobre la revisión final: hay otras sesiones y
worktrees activos; su evidencia no se atribuye a esta tarea.

## 4. Contratos del harness

### Entrada y procedencia

Cada ejecución declarará `schema_version`, `run_id`, revisión Git y diff propio,
tipo de ejecución (`contract`, `replay` o `runtime`), suite, partición,
identidad/digest de modelo, configuración y prompt, política y sus hashes.
Los datos tendrán manifiesto, SHA-256, custodia, unidades, zona horaria, ids de
caso y grupo. La inferencia registrará backend/dispositivo efectivos; no se
declarará CUDA por configuración. No se enviarán datos a proveedores remotos:
los adaptadores externos llamarán a los proveedores locales del proyecto.

Los registros de evaluación tendrán una referencia independiente de la predicción:
etiquetas de tarea/entidades; ids documentales relevantes para recuperación;
observaciones con instante de disponibilidad para pronóstico; resultados físicos
con identidad completa de proyecto, caso, escenario, topología y fuente para flujo.
Las etiquetas de violación eléctrica incluirán la política normativa aplicable.
Si faltan, esa evaluación queda bloqueada; no se inferirán etiquetas del candidato.

### Ejecución y salida

Los adaptadores normalizarán resultados individuales al contrato local y guardarán
también la salida original del upstream. Su versión y esquema se comprobarán;
un campo ausente, ids duplicados, salida truncada, timeout o denominador imposible
impedirán una decisión favorable. Los errores y casos cancelados formarán parte
del total programado, con cobertura y motivo, sin borrarlos del denominador.

Cada informe contendrá casos programados/completados/fallidos, soporte, métricas
globales y por familia, diferencias pareadas respecto de referencias, incertidumbre
cuando sea estimable, duración, política, bloqueos y enlaces de evidencia.
Los errores de infraestructura se separarán de errores predictivos; ambos
impiden cerrar una campaña obligatoria incompleta. Para precision/recall, solo
los casos evaluables aportan VP/FP/FN, y la cobertura incompleta bloquea promoción.
La publicación será por staging/reemplazo atómico y relectura con huella.

Estados de campaña: `COMPLETA`, `INCOMPLETA`, `BLOQUEADA_POR_DATOS`,
`ERROR_ENTORNO` o `CANCELADA`. Separadamente, el registro de modelos seguirá usando
sus estados actuales. Un informe completo puede rechazar al candidato; ejecutar
el harness no equivale a promoverlo. `replay` valida el cálculo sobre salidas
guardadas y no acredita inferencia actual; `contract` solo valida integración.

En la primera versión, `contract` y `replay` tienen prohibido registrar una decisión
de promoción o llamar a `promover()`, aunque relean evidencia runtime histórica.
Los informes históricos se podrán comparar como diagnóstico, pero no aprobar un
nuevo candidato. Solo una campaña `runtime` completa podrá solicitar promoción;
el adaptador comprobará en ese punto los digests exactos del candidato, referencia,
datos, configuración/prompt de cada modelo, política, manifiesto de suites y
evidencia de recarga. El registro actual no valida por sí solo este contrato nuevo:
la implementación incorporará y probará esa guarda en la frontera de promoción.
La comparación runtime del vigente y candidato se hará sobre el mismo conjunto
sellado, sin sustituir una referencia faltante por un informe antiguo.

## 5. Métricas y comparadores por familia

| Familia | Unidad de evaluación | Métricas | Comparador |
| --- | --- | --- | --- |
| Clasificación de órdenes | Una orden con tarea esperada | Matriz de confusión, precision/recall/F1 por clase, macro y micro, acierto | Modelo vigente con los mismos casos |
| Extracción de entidades | Conjunto normalizado de entidades de una orden | VP/FP/FN, precision/recall/F1 global y por tipo/tarea | Evaluador de órdenes existente |
| Recuperación RAG | Consulta con conjunto de ids documentales relevantes | Precision@k, Recall@k, MRR y nDCG si existe relevancia graduada | Recuperador vigente y BM25 sobre el mismo corpus |
| Respuesta fundamentada | Respuesta, fuentes y referencia experta | Corrección, cobertura de hechos, soporte de citas, afirmaciones sin respaldo; juicio automático separado | Respuesta vigente con iguales entradas |
| Pronóstico | Objetivo, emisión y horizonte | MAE, RMSE, pinball, cobertura, error de máxima e instante y habilidad frente a referencia | Ingenuo/estacional y activo, según política 046 |
| PINN/GNN | Caso eléctrico, barra/rama y familia topológica | Errores de tensión/pérdidas/cargabilidad, residuales físicos, latencia y cobertura del dominio | Flujo físico y activo, según políticas 044/045/071 |
| Detección de violaciones | Barra/rama/caso con etiqueta física y límite normativo | VP/FP/FN, precision/recall/F1 de violaciones y falsos negativos por gravedad | Etiqueta física independiente |
| Optimización | Alternativa con obras/CAPEX y restricciones definidos | Factibilidad nativa, coste comparable, mejora de objetivo, violaciones y tiempo | Referencia física/alternativa vigente de igual alcance |

Precision = VP/(VP+FP); recall = VP/(VP+FN). Si el denominador es cero, se
publicará `null`, soporte y motivo, nunca un 1 artificial. El F1 nuevo se derivará
de 2VP/(2VP+FP+FN), y será `null` si ese denominador es cero. No se sustituirá
silenciosamente el F1 histórico del evaluador: se conservará con su versión para
comparabilidad y se publicará la nueva convención bajo un esquema explícito.

La matriz de tareas incluirá abstención/salida inválida. La precisión de entidades
no sustituye la precisión de clasificación. Para Recall@k se exigirá anotación
documental suficientemente completa y versionada; si solo se conocen algunos
positivos se publicará el alcance parcial y no recall total. Se fijarán k, unidad
documento/chunk y deduplicación antes de medir. Las consultas sin respuesta se
evaluarán por abstención correcta y recuperación indebida, aparte del recall.

Los juicios de Ragas/LLM llevarán juez, prompt, versión, repeticiones y calibración
contra una muestra experta. No serán por sí solos una prueba de verdad ni de
aceptación eléctrica. Las pruebas de acciones no ejecutarán escrituras físicas;
esas acciones tendrán una campaña nativa separada con las guardas actuales.

## 6. Prevención de fuga y ciclo de mejora

1. Inventariar modelos, datos y referencias realmente disponibles. Ausencias
   producen bloqueo explícito por familia; no una métrica inventada.
2. Sellar entrenamiento, selección, calibración y prueba con grupos de custodia.
   Las variantes hermanas de texto, proyecto y topología no cruzarán particiones.
   Generalización a otra red se medirá reteniendo redes completas.
3. Medir vigente y candidatos con los mismos ids, ventanas y contexto.
   Transformaciones temporales se ajustan solo con pasado disponible al emitir.
4. Usar fallos de entrenamiento/selección para corregir prompts, herramientas,
   recuperación o datos: comparar BM25, denso e híbrido; después reranking,
   negativos difíciles y ajuste LoRA/QLoRA solo si esos errores lo justifican.
   Las etiquetas generadas por un maestro seguirán siendo sintéticas.
5. Ejecutar ablaciones que separen el efecto de recuperación, prompt, ajuste de
   pesos y validadores. Para modelos eléctricos separar modelo, datos y pérdida
   física; para pronóstico, arquitectura, covariables y referencia estacional.
6. Elegir en selección, calibrar en calibración y evaluar el candidato congelado
   en prueba una vez por campaña. La prueba consultada no alimentará nuevos ajustes
   como si siguiera siendo desconocida; una nueva campaña tendrá su reserva.

## 7. Puertas de aceptación y evidencia de mejora

Antes de ejecutar se sellará una matriz modelo→suites→puertas. Los mínimos de la
primera versión serán los siguientes; una configuración puede añadir requisitos,
pero no retirar estos mínimos. Las suites compuestas deben expandirse en esa
matriz, sin depender de nombres de paquetes externos.

| Candidato que se pretende promover | Suites runtime obligatorias | Evaluadores externos auxiliares por defecto |
| --- | --- | --- |
| LLM/clasificador/extractor del asistente | Clasificación y entidades de todas las tareas en su dominio; corpus humano y propuesta asistida según las puertas vigentes; guardas/confirmación de acciones; recarga | Benchmark general de EleutherAI, runner Promptfoo |
| Recuperador/embeddings/reranker | Recuperación con corpus y consultas gold; consultas sin respuesta; respuesta fundamentada de la cadena resultante; recarga | Juez Ragas |
| Cadena LLM con recuperación, prompt o herramientas modificados | Unión de suites del asistente y de recuperación; contratos de las herramientas que cambian y recarga/configuración rereída | EleutherAI, Promptfoo y Ragas |
| Pronóstico | Todos los objetivos/horizontes declarados, referencias y puertas 046, disponibilidad causal de entradas y recarga | Cualquier benchmark genérico adicional |
| PINN/GNN | Todos los grupos/topologías del dominio declarado, referencias y puertas físicas 044/045/071, detección de violaciones con etiquetas físicas, contraste nativo y recarga | Benchmark público adicional |
| Optimizador aprendido/ajustado | Alternativas, CAPEX y restricciones del alcance sellado, contraste y factibilidad nativa por 048, conservación y reapertura si escribe | Benchmark público adicional |

No disponer de una suite obligatoria deja sin promoción a esa familia; no bloquea
un diagnóstico de otras familias. Una campaña integral solo será completa si
están completas todas las familias incluidas antes de comenzar. Toda suite marcada
como auxiliar conserva su fallo/no disponibilidad en el informe, pero no cambia
por sí sola la decisión. Si se hace obligatoria por política de campaña, queda
sellada como tal antes de medir. Instalar un paquete no lo convierte en obligatorio;
usar otro runner no elimina el requisito semántico de la suite. No se puede
reclasificar una suite fallida como auxiliar ni reducir el dominio después de medir.

Las puertas existentes de 044/045/046/047 no se relajan. No se reescriben sus hashes.
La nueva política añadirá mínimos de soporte, precision y recall por familia,
margen de mejora y tolerancia de regresión con versión propia, antes de abrir
prueba. El implementador expondrá estos valores como configuración obligatoria,
validada y sellada; no necesita inventar límites para programar el harness.
Mientras no estén declarados para una campaña, podrá producir diagnóstico pero
no aprobación. Son criterios de rendimiento, separados de límites normativos.

Para afirmar «mejoraron precision y recall», ambas diferencias deberán superar
sus márgenes predeclarados en la misma prueba independiente, con los intervalos
pareados exigidos por la política y sin incumplir las puertas por familia.
Una mejora de F1 con caída de recall no se presentará como mejora de ambos.
Una no inferioridad aceptada tampoco se llamará aumento. Ninguna media compensará
una regresión en familia crítica o falsos negativos eléctricos fuera de política.

La incertidumbre se estimará con unidades compatibles con la dependencia de los
datos: grupos de órdenes/proyectos y bloques temporales o familias topológicas,
no barras ni ventanas correlacionadas como observaciones independientes.
Se reutilizará el remuestreo por día de la política temporal donde corresponda.
El protocolo sellará nivel de confianza, semillas, remuestras, unidad de agrupación
y corrección de comparaciones múltiples. Con grupos insuficientes no se afirmará
significancia ni mejora demostrada. No se aplicará automáticamente un test de
clasificadores sobre varios datasets a un único alimentador correlacionado.

La aceptación eléctrica exigirá convergencia y comprobación de tensiones,
cargabilidad, pérdidas y restricciones en el motor real, con fuente, caso,
escenario y norma coincidentes. Persistencia y reapertura se exigirán cuando haya
escritura. El pronóstico conservará la prohibición de escribir predicciones como
mediciones en DIgSILENT. Un benchmark LLM o una prueba con dobles no sustituye esto.

## 8. Reutilización GitHub y límites de ejecución

El anexo [fuentes verificadas](2026-11-08-harness-integral-modelos-design-fuentes.json)
registra commits completos, licencias y SHA-256 de sus archivos, consultados por
la API oficial de GitHub el 2026-11-08. Es inventario del diseño, no lock instalado.
Antes de ejecutar cada adaptador se revisarán su código, configuración y licencia
en esa revisión y se fijarán sus dependencias. No se descargaron repositorios,
pesos ni paquetes para redactar este documento. Se reusará el lock eléctrico
existente; no se actualizarán sus revisiones como efecto lateral.

Se conservarán datos y pesos locales; no se incrustarán en Git ni CI. Las suites
CPU de contratos podrán correr en CI; los trabajos de inferencia/entrenamiento
reales usarán el coordinador y exclusión GPU existentes, los presupuestos de
memoria y cancelación vigentes. PF tendrá turno exclusivo independiente.
Una reserva GPU local a un worktree no se considerará exclusión global suficiente.
Se resolverá el mecanismo vigente al integrar con la otra rama de coordinación.

## 9. Superficies propuestas y comprobaciones necesarias

El implementador decidirá nombres definitivos y tamaño de módulos. Superficies
propuestas: paquete `src/convertersmartgrid/evaluacion_harness/`, CLI
`tools/evaluar_harness.py`, configuración versionada, adaptadores opcionales,
extensión aditiva de informes y conexión al registro/coordinador existentes.
No se duplicará el cálculo temporal o el registro de modelos.

| Requisito | Superficie existente a conectar | Comprobación requerida y evidencia |
| --- | --- | --- |
| Precision/recall con soporte y ceros | `asistente/aceptacion.py` | Casos calculables a mano; abstenciones, FP, FN y denominador cero; informe rereído |
| Particiones/custodia | `evaluacion_modelos.py`, `asistente/llm_destilacion.py` | Solape de grupos, digest distinto y prueba sin selección bloquean |
| Recuperación/respuesta | Adaptadores y recuperador local por identificar al planificar | Corpus anotado, ids duplicados y consultas sin respuesta; salida upstream conservada |
| Pronóstico causal | `digital_twin/evaluacion_temporal.py` | Ventanas idénticas, covariable futura rechazada, referencias y puertas preservadas |
| Gemelo/violaciones | `digital_twin/oraculo.py`, `evaluacion_modelos.py` | Etiqueta física, unidades, NaN, contexto distinto y familia crítica; ejecución nativa separada |
| Optimización | `digital_twin/evolutivo.py`, `optimizacion_oraculo.py` | Obra/CAPEX reales, restricciones y referencia equivalente; evidencia nativa |
| Corridas canceladas/parciales | `training_coordinator.py` | Sin promoción, informe parcial recuperable y liberación del turno propio |
| Publicación/promoción | `model_registry.py`, adaptador del harness | Huella verificada, relectura/recarga, fallo conserva activo; no bypass de puertas |

Se conservarán las pruebas afectadas, incluyendo `tests/test_aceptacion_agente.py`,
`tests/test_llm_destilacion.py`, `tests/test_evaluacion_modelos.py`,
`tests/test_evaluacion_temporal.py`, `tests/test_model_registry.py` y
`tests/test_training_coordinator.py`. El plan posterior asignará cada requisito a
archivo, prueba y evidencia, y distinguirá contratos, replay, runtime, suite
completa, persistencia y aceptación del dominio. La revisión independiente de este
diseño no sustituye una revisión de implementación ni aceptación científica.

## 10. Fundamento académico consultado en la web

- **Maestría:** Simon König (2025), [Automated evaluation and parameter optimisation
  for retrieval augmented generation systems](https://publications.ait.ac.at/de/publications/automated-evaluation-and-parameter-optimisation-for-retrieval-aug/),
  TU Wien. El resumen institucional describe evaluación con métricas automáticas y
  juez LLM. Justifica comparar componentes y evaluadores; no valida nuestras etiquetas.
- **Doctorado:** Yushi Sun (2025), [Innovative Approaches to Data Curation and
  Retrieval-Augmented Generation](https://calendar.hkust.edu.hk/events/phd-computer-science-engg-innovative-approaches-data-curation-and-retrieval-augmented),
  HKUST. La defensa y descripción institucional vinculan curación y recuperación.
  Se consultó la ficha/resultado institucional; el PDF dio bucle de redirección en
  la consulta directa. No se afirma revisión íntegra de la tesis.
- **Doctorado eléctrico:** Jochen B. Stiasny (2023), [Physics-Informed Neural
  Networks for Power System Dynamics](https://orbit.dtu.dk/en/publications/physics-informed-neural-networks-for-power-system-dynamics/),
  DTU, DOI 10.11581/DTU.00000277. Su resumen analiza escalabilidad y confianza en
  modelos físicos aprendidos. Su dominio dinámico no prueba nuestro flujo estático.
- **Artículo de congreso:** Es et al. (2024), [RAGAs: Automated Evaluation of
  Retrieval Augmented Generation](https://aclanthology.org/2024.eacl-demo.16/),
  EACL System Demonstrations, DOI 10.18653/v1/2024.eacl-demo.16. Sustenta descomponer
  recuperación/generación; su evaluación automática no reemplaza el gold experto.
- **Artículo de revista:** Lin et al. (2024), [PowerFlowNet: Power flow approximation
  using message passing Graph Neural Networks](https://publications.tno.nl/publication/34643410/FBJD74Um/lin-2024-powerflownet.pdf),
  International Journal of Electrical Power & Energy Systems 160, 110112.
  Sustenta comparar error y velocidad frente a cálculo físico; no se trasladan
  sus cifras de otras redes a este proyecto.
- **Artículo de revista indexado en DBLP:** Demšar (2006), [Statistical Comparisons
  of Classifiers over Multiple Data Sets](https://www.jmlr.org/papers/volume7/demsar06a/demsar06a.pdf),
  JMLR 7, 1–30; [registro DBLP](https://dblp.org/rec/journals/jmlr/Demsar06.html).
  Justifica controlar el protocolo comparativo; no legitima tratar muestras
  correlacionadas como datasets independientes.

Estas fuentes fundamentan elecciones metodológicas. Los umbrales, el remuestreo
y el protocolo específico de este diseño son propuestas locales; las fuentes no
certifican su implementación, una mejora local, ni cumplimiento normativo.

## 11. Verificación de esta entrega documental

El anexo se releyó con `ConvertFrom-Json`; sus tres commits tienen 40 caracteres
hexadecimales y las tres huellas de licencia, 64. Se comprobaron las 14 rutas
existentes referidas con formato de código en el documento, excluyendo el paquete
propuesto que todavía no existe. La revisión independiente fue solo lectura y
señaló la matriz obligatoria de suites y la admisibilidad de replay: ambas se
resolvieron en las secciones 4 y 7. No se ejecutaron pruebas de producto ni campañas
para validar un cambio de documentación. La segunda revisión independiente no
encontró preguntas importantes pendientes para planificar. Se revalidaron JSON,
identidades y rutas, y `git diff --check` salió 0 para el diff rastreado; los dos
documentos nuevos se releyeron por separado. El estado Git conserva el cambio
ajeno en `web/services.py` y los planes previos. No se añadió nada al índice Git.

## 12. Estado al entregar el diseño

En la entrega inicial: diseño integral y procedencia de candidatos GitHub. Pendientes entonces:
aprobación del diseño, plan de implementación, código, contratos, campañas reales,
entrenamiento que corresponda y evidencia de mejora/aceptación eléctrica.
En esa fase no se ejecutó GPU, PF ni suite completa. No se modificaron corpus, modelos,
entornos, fuentes de producto ni cambios ajenos. El diseño se deja sin commit en
main para que el integrador conserve el control del árbol compartido.
