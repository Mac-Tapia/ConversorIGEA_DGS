# Auditoría de IA y aprendizaje del proyecto local

Inspección iniciada: 2026-11-01, 09:57, America/Lima.
Repositorio: `D:/converter/ConversorIGEA_DGS`; nombre actual: ConverterSmartGrid. <!-- legado-058: ruta real del checkout existente -->
Commit leído: `e307889c2f448e68398387799f4d656948295246` más modificaciones
concurrentes, inventariadas en la evidencia. No se revirtieron ni incorporaron.

**Dictamen: hay componentes operativos, pero el entrenamiento y el aprendizaje
automático integral aún no cumplen aceptación. La GPU funciona; faltan conexiones,
datos vigentes, espacio de exportación y verificaciones conjuntas.**

Seguimiento tras la petición de crear los cuatro trabajadores: se implementaron
los CLI y se repararon los argumentos del runner. A2 describe el hallazgo inicial;
su ausencia de archivos queda corregida. Ver [implementación y verificaciones](TRABAJADORES_COORDINADOR_2026-11-01.md).
Los bloqueos de datos/recursos y la aceptación integral siguen siendo condiciones
independientes; el diagnóstico inicial no se reescribe como si nunca hubieran existido.

## Alcance y método

Se contrastaron código, specs 043–050, herramientas y argumentos reales, paquetes,
pesos locales, corpus sellado, manifiestos del búfer, registro de modelos y API.
Se ejecutaron pruebas focalizadas y una operación CUDA pequeña en proceso separado.
La inspección no ejecutó un nuevo ajuste de LLM, estudios PowerFactory ni maniobras.
No modificó entradas, fuentes, modelos activos, paginación ni procesos ajenos.

Las observaciones nuevas de esta auditoría prevalecen como diagnóstico actual;
los errores 1455 y resultados antiguos se conservan como evidencia histórica.
No se utiliza un porcentaje global de «implementación»: casillas, dependencias,
pruebas unitarias y aceptación nativa miden cosas distintas.

## Resultados ejecutados ahora

| Comprobación | Resultado | Qué acredita |
| --- | --- | --- |
| Pruebas de contratos e integración focalizada | 129 aprobadas, 0 fallos/errores/omisiones | LLM, intérprete, esquema, tareas, web, aceptación, particiones, registro y coordinador en el alcance probado |
| Prueba con corpus local real | 1 fallo, 0 omisiones | El corpus ya no cumple la custodia de una fuente; no se oculta el fallo |
| CUDA real | Producto matricial correcto en RTX 4060 Laptop, PyTorch 2.14.1+cu126 | Importación, dispositivo, ejecución y transferencia reales; no capacidad de entrenar un LLM completo |
| Auditoría de pesos | 5 modelos del catálogo completos y verificados; 0 activaciones | Qwen3 NF4, BGE, E5, Qwen3:8b y nomic; descargar/verificar no es entrenar |
| Dependencias | `pip check` correcto; paquetes ML declarados presentes en el inventario | Compatibilidad declarada del entorno, no ejecución de todos los adaptadores |
| API local | Salud, modelos y aceptación responden HTTP 200 | Lectura del estado del servicio, no aceptación integral ni coincidencia de cada módulo cargado con el diff de trabajo |
| Búfer | 233 manifiestos válidos por contrato | 64 `accepted`, 106 `counterfactual`, 27 `rejected`, 19 `converged_with_violations`, 17 `quarantine` |

La prueba CUDA consumió un pico de 8.520.704 bytes asignados por Torch. Es una
operación de diagnóstico de tamaño mínimo, no un ensayo de carga del modelo 4B.
No se reabrieron en PowerFactory los 233 episodios durante esta auditoría ni se
verificó nuevamente el contenido de todos sus artefactos nativos.

## Hallazgos y mejoras, en orden de ejecución

### A1. Alta — El corpus sellado no es actualmente entrenable

La auditoría y `tests_ml/test_llm_fuentes_reales.py` fallan con
`huella de fuente modificada`. La diferencia se identificó en
`docs/constitution.md`: huella conservada
`2569bb5776cc036fc35c34312822993c4187106dd77789a0bf826e0e8c652448`,
huella leída
`8c60a40a0f4dec9d5366cbbd3047cffbae943f2e9fe5922be9b625405fa68979`.
El fallo es un control de custodia funcionando, no evidencia de datos eléctricos falsos.

Mejora: conservar el sellado previo y preparar una versión nueva con las fuentes
vigentes y copias inmutables de las normas usadas para anotar. Comparar qué cambió
en las etiquetas/políticas y excluir las humanas. No sustituir únicamente el hash
para hacer pasar el control. Repetir la auditoría de todos los subconjuntos antes
del ajuste. Cierre: preparación reproducible y prueba con fuentes reales aprobada.

### A2. Alta — El runner integral tiene contratos rotos con sus trabajadores

`tools/reentrenar_modelos.py` llama a archivos ausentes en esta copia:

- `tools/digital_twin_temporal_entrenar.py`;
- `tools/evaluar_evolutivos.py`;
- `tools/asistente_embeddings.py`;
- `tools/asistente_qlora.py`.

También envía `--dataset-v2` a `tools/asistente_entrenar.py`, que no lo admite.
Se reprodujo el rechazo real de argparse, código 2, sin crear informe ni entrenar.
El trabajador generativo disponible, `tools/llm_destilar.py`, no es el que invoca
la etapa QLoRA de ese runner. Ambos comandos de ayuda existentes terminan bien;
eso no repara la incompatibilidad de argumentos.

Mejora: completar o adaptar los trabajadores según 043/046/047/048 y conectar el
QLoRA generativo real al contrato común. Probar presencia, ayuda y argumentos de
cada trabajador antes de tomar GPU. Después ejecutar los siete trabajos reales y
releer sus informes. No generar siete estados aprobados para suplir esas llamadas.

### A3. Alta — El espacio actual no alcanza para la exportación implementada

D: tenía aproximadamente 9,17 GiB libres. Con los tamaños de la base ya exportada,
el flujo que conserva shards FP16, GGUF FP16 y GGUF Q4 necesita aproximadamente
17,32 GiB para esos tres productos, sin contar checkpoints, logs o margen.
`llm_runtime.py` no contiene una comprobación previa de espacio libre.

Mejora: calcular presupuesto con la base y checkpoints concretos, comprobar espacio
en cada volumen y abortar antes de escribir si falta. Habilitar un destino con
capacidad suficiente o una exportación que reduzca intermedios, verificándola
numéricamente. No borrar automáticamente evidencia ni mover otros proyectos.
El mínimo de 17,32 GiB es una estimación basada en esta base y este flujo, no un
umbral universal. El destino debe admitir además el resto de los artefactos.

### A4. Alta — Aún no existe evidencia del alumno LLM generativo entrenado

No se encontraron checkpoints `estado.json` del ajuste completo en su directorio.
Los tags `igea-alumno-base:*` instalados son bases históricas de comparación, <!-- legado-058: identidad de modelos instalados, conservada literalmente -->
conservadas por identidad, no un alumno destilado. QLoRA permanece como
`ERROR_ENTORNO` en el registro y la API. El error mostrado allí es el del intento
anterior; no es una medición en vivo de memoria.

La evaluación histórica de Qwen3:8b sigue publicada: 188/200 tareas (0,94),
F1 0,9393939394; rechazo frente a las puertas 0,98 y 0,95. Hay cinco eventos humanos,
pero solo tres órdenes únicas; no se cuentan como 200 humanas.
Esta auditoría releyó esos resultados, no repitió su inferencia.

Mejora: resolver A1–A3; ejecutar todas las muestras de entrenamiento, verificar y
recargar el checkpoint, comparar base/candidatos solo en selección, fijar versión,
evaluar las 200 nuevas y humanas reservadas, y conservar rechazos. No acreditar
destilación generativa con el entrenamiento del clasificador pequeño ni con un
paso LoRA de entorno.

### A5. Alta — Registro común y modelos usados conservan caminos separados

El registro común no muestra activos en sus siete familias. Sin embargo, existen
punteros históricos fuera de él: PINN `20261028-114528-e6f5`, con tres ficheros de
pesos, y Transformer de órdenes `20261024-150042-37ce`, con su fichero de pesos.
La metadata PINN guarda MAE 0,002435454 y reparto 52/10/10; se leyó como antecedente,
sin recalcularlo ni certificar de nuevo su dominio. Por tanto, «sin activo en el
registro común» no significa «no existe ningún modelo entrenado».

Mejora: conciliar por identidad y evidencia las versiones históricas con el registro
común, preservando pesos y puertas; hacer que UI y consumidores resuelvan la misma
fuente de versiones. Una migración de metadata no equivale a aceptar el modelo.
Cierre: una predicción identifica versión, origen, dominio, evaluación y estado
coherentes con la API, con recarga y reversión verificadas.

### A6. Alta — La sincronización entre familias sigue pendiente

Las cinco tareas de 050 están abiertas. `Vigilante` dispara callbacks separados de
gemelo y asistente; el coordinador ordena siete etapas, pero eso no demuestra una
instantánea compartida, un dataset enlazado por observación ni publicación conjunta.
Tampoco se encontró el enlace del nuevo trabajador LLM con la vigilancia existente.

Mejora: implementar 050 en su orden: instantánea común; vistas de lenguaje, series
y grafos; cola idempotente con presupuestos; candidatos aislados; pruebas históricas
y conjuntas; publicación atómica del conjunto y reversión. Las predicciones del
LLM/PINN no deben convertirse por sí solas en etiquetas físicas ni en recompensas
verdaderas. Los escenarios simulados conservan su clase y fuente nativa.

### A7. Media/alta — Faltan adaptadores, benchmarks y pruebas de aceptación

En 043–050 hay 32 tareas abiertas y seis cerradas según las listas actuales.
Entre las pruebas nombradas explícitamente en esas tareas, 21 archivos no existen;
su lista exacta está en `inventario.json`. Esto no mide el porcentaje implementado.

Entre los módulos ausentes están `asistente/reranker.py`, `revision_roles.py` y
`qlora.py`; el nuevo ajuste de LLM está en un módulo distinto. El runner reconoce
NHITS/TFT/PatchTST pero devuelve explícitamente adaptador pendiente, sin sustituir
sus ejecuciones por GRU. La GRU sí tiene código y una ruta web; eso no acredita
benchmark multihorizonte ni su persistencia dentro del ciclo común.

Mejora: cerrar 045–048 RF por RF con pruebas y datos reales; comparar PINN con
física sin red y ablaciones, GRU con estacional y evaluación causal, recuperación
con citas verificadas y optimización con factibilidad/coste nativos. La nueva
corrección de demanda de 057 es otra capacidad, no prueba de aprendizaje conjunto.
Su T4 nativa también permanece abierta.

### A8. Media — El preflight y las pruebas deben comprobar el recorrido real

Las pruebas del runner existentes verifican contratos de informes y reanudación;
no detectaron los cuatro archivos ausentes ni el argumento incompatible. Las 129
pruebas aprobadas de esta auditoría tampoco se presentan como ejecución real de
las siete etapas. Faltan preflight conjunto de datos/disco/memoria y una prueba
de aceptación que recorra todos los trabajadores sin omitir familias.

Mejora: prueba de contrato de cada CLI, prueba de datos reales separada de fixtures,
chequeo de artefactos y gates, y una campaña integral con informes por etapa. En la
web, distinguir último error histórico, recursos actuales, candidato y versión usada.
No convertir HTTP 200 o `complete` de la enumeración de etapas en aceptación.

## Diagnóstico de memoria y GPU

Se detectó RTX 4060 Laptop de 8.188 MiB; en la lectura inicial usaba 381 MiB y
ningún modelo Ollama estaba residente. La operación CUDA posterior fue correcta.
La memoria comprometible varió: aproximadamente 9,2 GiB en la lectura inicial y
6,47 GiB antes de la prueba pequeña; la RAM física disponible también cambió.
El servicio AppXSvc con 17 GiB observado antes no aparece entre los ocho mayores
consumos de esta lectura. No se mantiene aquel diagnóstico como hecho actual.

El umbral de 8 GiB comprometibles del ajuste es una protección del proyecto, no
garantía de que cualquier entrenamiento quepa. Medir picos de importación, carga,
optimizador y exportación, además de VRAM; dimensionar paginación con esas medidas.
Windows contabiliza memoria comprometida respaldada por RAM/paginación, incluso
cuando el cálculo usa GPU: [documentación oficial de Microsoft](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/introduction-to-the-page-file).
No se cambió paginación ni se terminaron procesos para esta auditoría.

## Orden recomendado y criterios de entrega

1. Congelar código/contexto del ciclo y regenerar correctamente el dataset vigente
   (A1). Prueba real de procedencia en verde; evidencia anterior conservada.
2. Reparar los contratos del runner y su conexión al alumno generativo (A2/A8).
   Todos los entrypoints y argumentos deben comprobarse sin arrancar modelos.
3. Resolver presupuesto de disco y memoria con margen medido (A3). Luego ejecutar
   ajuste completo y recarga real del alumno (A4), con evaluación independiente.
4. Conciliar registro/consumidores (A5), completar adaptadores/benchmarks (A7) y
   ejecutar 050 sobre una instantánea común (A6), incluida una segunda captura real.
5. Exigir comparación con el conjunto previo, retención histórica, readback de
   versiones, reversión y contraste nativo del alcance. Mantener abiertas las
   tareas sin evidencia; no bajar puertas para declarar entrega.

No se recomienda descargar más modelos antes de cerrar estos bloqueos: los cinco
del catálogo ya verificaron correctamente. Las librerías instaladas tampoco
resuelven archivos trabajadores ausentes o contratos incompatibles.

## Fundamento científico consultado

- [Witossek, maestría, Universität Leipzig/DLR, 2025](https://elib.dlr.de/220552/):
  comparación explícita de maestro, alumno y base en una tarea de dominio. Sustenta
  A4; sus resultados no se transfieren a este proyecto.
- [Mirzadeh, doctorado, Washington State University, 2022](https://rex.libraries.wsu.edu/esploro/outputs/doctoral/Alleviating-Catastrophic-Forgetting-in-Continual-Learning/99900898638301842):
  explica el deterioro de conocimientos anteriores bajo entrenamiento secuencial.
  Sustenta medir retención en A6, en vez de prometer mejora con cada ajuste.
- [Van de Ven, Tuytelaars y Tolias, Nature Machine Intelligence, 2022](https://doi.org/10.1038/s42256-022-00568-3):
  separa escenarios de aprendizaje incremental y compara replay. Sustenta separar
  contextos y evaluar histórico; no prescribe nuestros umbrales de aceptación.

Los hallazgos concretos proceden de archivos y pruebas del repositorio; estas
fuentes justifican el método de evaluación, no prueban funcionamiento local.

## Evidencia reproducible y límites

Directorio: `output/auditoria_ia_20261101_actual/`.
`inventario.py`, `entradas_y_legacy.py`, `pruebas_auditoria.py`, `probar_cuda.py`
y `contrato_cli_runner.py` conservan los generadores locales usados en esta revisión.
Resultados: `inventario.json`, `hashes_codigo.json`, `entradas_y_legacy.json`,
`modelos_legacy.json`, `contratos.xml`, `fuentes_reales.xml`, `cuda_real.json`,
`pesos_auditados.json`, `espacio_exportacion.json` y respuestas HTTP guardadas.
Los logs y manifiestos quedan locales; no se publicaron datos de referencia.

Alcance de pruebas focalizado, no suite completa del conversor. Sin entrenamiento
completo, recarga nueva de todos los modelos, prueba visual de toda la web ni
aceptación PowerFactory nueva. No se cerró ninguna tarea por esta auditoría.
