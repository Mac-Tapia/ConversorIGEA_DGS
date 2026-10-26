# Diseño del reentrenamiento integral y verificable de modelos

**Fecha:** 2026-10-25

**Estado:** pendiente de aprobación del usuario
**Alcance:** asistente de órdenes, recuperación documental y gemelo digital de IGEA-DGS

## 1. Intención

Reentrenar todos los componentes que aprenden del sistema con datos locales trazables, comparar
cada candidato contra su modelo promovido y contra una línea base independiente, y conservar el
modelo anterior cuando el candidato no demuestre una mejora. El resultado no será una afirmación
genérica de «entrenado»: cada modelo terminará con uno de estos estados auditables:

- `PROMOVIDO`: superó todas sus puertas y fue reabierto para inferencia.
- `RECHAZADO`: se entrenó, pero retrocedió o incumplió una puerta.
- `BLOQUEADO_POR_DATOS`: no existe evidencia suficiente o una partición válida para entrenarlo.
- `ERROR_ENTORNO`: falló una dependencia, la GPU o la persistencia; no cambia el modelo activo.

El reentrenamiento no sustituye la aceptación eléctrica. Ninguna respuesta de un LLM, métrica de
clasificación o aproximación de una PINN prueba por sí misma guardado, reapertura, convergencia o
cumplimiento de límites en DIgSILENT PowerFactory.

## 2. Estado comprobado el 2026-10-25

### 2.1 Equipo y ejecución concurrente

- GPU: NVIDIA GeForce RTX 4060 Laptop, 8 188 MiB; 7 080 MiB estaban libres durante la auditoría.
- PyTorch `2.14.1+cu126` reconoce CUDA. Están instalados `transformers`, `peft`, `bitsandbytes`,
  `datasets` y `trl`; no están instalados `optuna` ni `scikit-learn`.
- Hay dos servidores web y varias suites `pytest` activas. Ningún entrenamiento podrá comenzar
  mientras otro proceso use la GPU o escriba los mismos registros.
- La rama `codex/cierre-universal-por-set`, descendiente directa de la rama actual, ya contiene un
  constructor de dataset, QLoRA, registro de adaptadores y supervisor. Es trabajo concurrente:
  se preservará y se incorporará solo por diferencias identificadas, pruebas y hashes; no se
  copiará a ciegas ni se editará su worktree.

### 2.2 Modelos y datos existentes

| Componente | Estado físico | Evidencia y brecha principal |
|---|---|---|
| Transformer de órdenes | Pesos promovidos | 98,15 % de acierto y F1 de datos 0,869; el entrenamiento promovido declaró 4 055 ejemplos, pero solo 1 real. |
| Clasificador de informes | Pesos promovidos | Acierto de tipo 1,000 y de subtipo 0,987 en prueba sintética; falta una prueba independiente por documento real. |
| LLM de Ollama | Base preentrenada seleccionada | `llama3.1:8b` fue seleccionado frente a Qwen, pero no tiene ajuste local. Los GGUF de Ollama no son los pesos entrenables. |
| Dataset común candidato | Particiones publicadas | 6 570 train, 235 validation y 33 test; solo 5 registros son `gold` y 6 833 son contexto. El contexto no puede convertirse en respuesta correcta. |
| PINN/GNN | Conjunto de 3 miembros promovido | Hay 86 episodios en el búfer, pero la versión activa aprendió de 24 muestras útiles (20/2/2), `mae_v=0,000954`, una sola dimensión topológica de 2 470 nodos y `mae_dorados=null`. |
| GRU temporal | Implementación en memoria | Entrena y predice, pero no guarda pesos, dataset, particiones, métricas, versión promovida ni reversión. |
| Recuperador de embeddings | Ruta opcional | El índice usa BM25 y solo usa `nomic-embed-text` si está instalado; no existe dataset contrastivo ni registro de un recuperador ajustado. |

Los modelos físicos radial/mallado y la línea base estacional no se «reentrenan»: son referencias
analíticas. Permanecerán como oráculos comparativos obligatorios.

## 3. Objetivos, exclusiones y antiobjetivos

### Objetivos

1. Congelar datasets por huella SHA-256 y separar `gold`, `context` y `quarantine`.
2. Reentrenar secuencialmente Transformer, clasificador, PINN, GRU, recuperador y adaptador LLM.
3. Optimizar hiperparámetros dentro de presupuestos reproducibles, sin usar el conjunto de prueba.
4. Evaluar por tarea, documento, alimentador, SET, familia topológica y periodo temporal.
5. Registrar código, configuración, semilla, dependencias, hardware, datos, métricas y pesos.
6. Promover de forma atómica y poder volver al modelo anterior.
7. Mostrar en la web el estado real y el motivo de promoción, rechazo o bloqueo.

### No objetivos

- Preentrenar un LLM desde cero o modificar todos sus pesos.
- Enseñar al LLM topología, normativa o resultados cambiantes mediante memorización; esos datos se
  recuperan con citas desde fuentes versionadas.
- Convertir artefactos de `output/`, documentos normativos o episodios no aceptados en verdad dorada.
- Ejecutar simultáneamente modelos que compiten por los 8 GB de VRAM.
- Declarar producción completa mientras siga pendiente la aceptación T12 en DIgSILENT.

### Antiobjetivos

- Fuga de una misma orden, plantilla, documento, `source_run_id`, familia topológica o ventana de
  tiempo entre entrenamiento y prueba.
- Promoción basada solo en pérdida de entrenamiento, exactitud agregada o una prueba sintética.
- Reducir umbrales para conseguir que un candidato sea promovido.
- Sobrescribir pesos, punteros, datasets o evidencia de una ejecución anterior.
- Considerar el desacuerdo entre modelos como una etiqueta correcta sin confirmación humana.

## 4. Enfoques considerados

### A. Reentrenar solamente los modelos propios existentes

Es el camino más corto, pero deja el LLM sin adaptación, la GRU sin registro y el recuperador sin
evaluación. No satisface «todos los modelos».

### B. Orquestación integral, adaptación eficiente y promoción por puertas — elegido

Reutiliza los contratos existentes, completa los registros que faltan y ajusta el LLM mediante
QLoRA con la base congelada. Consume menos memoria, conserva capacidades generales y permite
reversión por adaptador. Es el único enfoque compatible con 8 GB y con la trazabilidad requerida.

### C. Entrenamiento completo del LLM desde cero o de todos sus parámetros

Se descarta: el volumen de datos dorados, la VRAM y el presupuesto de validación son insuficientes;
además aumentaría el riesgo de olvido catastrófico y memorización de datos locales.

## 5. Arquitectura propuesta

### 5.1 Inventario y reconciliación de la rama concurrente

Antes de crear código nuevo se producirá un inventario por commit y fichero de las capacidades
QLoRA ya presentes en `codex/cierre-universal-por-set`. Se verificará en una copia aislada:

- procedencia y hashes de los commits relevantes;
- consumidores reales desde CLI, web y supervisor;
- pruebas rojas/verdes y suite completa;
- compatibilidad con la rama actual;
- ausencia de dependencias indebidas del conversor hacia librerías de IA.

Solo después se portarán unidades completas. No se integrarán por este trabajo cambios PIDE,
PowerFactory u otros cambios de esa rama que no sean consumidores necesarios del entrenamiento.

### 5.2 Coordinador único

Un coordinador local ejecutará fases reanudables:

1. `inventory`: modelos activos, datos, procesos, VRAM, disco y dependencias.
2. `freeze`: snapshot inmutable de cada dataset con manifiesto y hashes.
3. `train`: candidatos en orden de menor a mayor consumo de GPU.
4. `evaluate`: validación, prueba sellada, calibración y comparación con baselines.
5. `register`: artefactos y métricas, aunque el candidato sea rechazado.
6. `promote`: cambio atómico del puntero solo si todas las puertas pasan.
7. `reload`: proceso nuevo que reabre el candidato y reproduce una batería fija.
8. `report`: informe consolidado por modelo y estado terminal.

El orden de GPU será: Transformer → clasificador → GRU → PINN → embeddings → QLoRA. Antes de cada
fase se descargará Ollama de VRAM; al terminar se liberará CUDA. Un archivo de bloqueo con PID,
inicio y modelo impedirá entrenamientos simultáneos y podrá recuperarse solo si el PID ya no existe.

### 5.3 Contrato común de registro

Cada versión contendrá:

- `model_manifest.json`: clase, versión base, commit, entorno, GPU y configuración;
- `dataset_manifest.json`: fuentes, particiones, conteos y SHA-256;
- pesos o adaptador;
- `metrics.json`: validación, prueba, baseline, modelo activo e intervalos por semilla;
- `decision.json`: puertas, resultado y motivos;
- `smoke_reload.json`: predicciones obtenidas después de reabrir en otro proceso.

Los estados se publicarán primero en una carpeta candidata. `promovido.json` cambiará mediante
reemplazo atómico; `anterior` conservará la reversión. Ninguna ruta absoluta privada será parte de
los registros exportables.

## 6. Datos y entrenamiento por modelo

### 6.1 Transformer de órdenes

- Datos: catálogo de tareas, sintéticos por plantilla y órdenes confirmadas/corregidas.
- Partición: por identidad de plantilla y grupo de orden real; una paráfrasis de la misma plantilla
  nunca cruza particiones.
- Búsqueda acotada: dimensión `{96,128}`, capas `{2,4}`, cabezas compatibles, `lr` entre `3e-4` y
  `1e-3`, peso BIO y dropout; selección por validación macro, no por test.
- Puertas: exactitud macro por tarea, F1 macro por tipo de dato, exactitud conjunta tarea+datos,
  calibración ECE y latencia. No puede retroceder en ninguna tarea crítica de escritura.
- Con menos de una prueba real representativa por tarea se podrá guardar candidato, pero no afirmar
  aceptación de lenguaje real.

### 6.2 Clasificador de informes

- Datos: documentos generados, documentos confirmados y correcciones; los trozos del mismo DOCX
  permanecen en una sola partición.
- Puertas: macro-F1 de tipo y subtipo, matriz de confusión, prueba por documento completo y rechazo
  explícito de subtipos desconocidos. El candidato debe superar al activo y a una mayoría por clase.
- Los informes generados por el propio sistema no serán independientes de su plantilla; se
  informarán por separado de documentos reales revisados.

### 6.3 PINN/GNN del gemelo

- Datos: solo episodios con grafo y resultados nativos legibles; `accepted` y casos dorados se
  distinguen de contraejemplos, cuarentena y no convergencia.
- Partición: grupo indivisible por familia topológica/proyecto y orden temporal. La prueba debe
  contener familias no usadas para ajustar hiperparámetros.
- Búsqueda acotada: ocultas, pasos de mensaje, tasa, peso físico, exponente de carga y semillas del
  conjunto; se mantiene el conjunto de tres miembros para incertidumbre.
- Puertas: MAE de tensión, error de pérdidas, residuo físico, cobertura del intervalo, detección
  fuera de dominio y desempeño por familia. Una métrica global no compensa una familia degradada.
- Si no hay diversidad topológica o casos dorados suficientes, el nuevo conjunto queda como
  candidato experimental y no sustituye al activo.

### 6.4 GRU temporal

- Descubrimiento de curvas por contenido y metadatos, nunca por un nombre fijo.
- Una serie necesita frecuencia verificable, unidades, procedencia, observados diferenciados de
  imputados y al menos 30 días; los objetivos imputados no entran a entrenamiento ni prueba.
- División cronológica 70/15/15 con una zona de separación de una ventana para evitar fuga.
- Búsqueda acotada: ventana `{96,192,672}`, ocultas `{16,32,64}`, tasa y paciencia; parada temprana
  por validación.
- Puertas por alimentador/SET: MAE, RMSE, MAPE solo donde el denominador sea válido, error del pico,
  hora del pico y cobertura. Debe superar al modelo estacional en test.
- Se añadirá registro, carga, promoción, reversión e inferencia de la versión promovida. Si una
  cabecera carece de datos, queda `BLOQUEADO_POR_DATOS`, no se reemplaza por pseudo-medidas.

### 6.5 Recuperador de embeddings

- Los documentos de código, especificaciones y normativa verificada son contexto citable, no
  respuestas doradas.
- Se construirá una prueba de recuperación con pares pregunta→fragmento confirmados y negativos
  difíciles del mismo documento.
- Primero se compararán BM25 y `nomic-embed-text`. Solo se ajustará un recuperador si existen al
  menos 100 pares confirmados y una licencia compatible; en otro caso quedará
  `BLOQUEADO_POR_DATOS` y BM25 seguirá activo.
- Puertas: Recall@5, MRR@10, precisión de cita, respuesta «No lo sé» fuera de cobertura y latencia.

### 6.6 LLM con QLoRA

- Base elegida para el primer candidato: `Qwen/Qwen3-4B`, licencia Apache-2.0 y pesos entrenables
  independientes de Ollama. Se usará modo no pensante para JSON de herramientas.
- QLoRA: NF4, doble cuantización, base congelada, `r=16`, `alpha=32`, dropout `0,05`, gradient
  checkpointing, lote 1, acumulación 16 y longitud inicial 512. Un smoke test de memoria precederá
  la descarga/ejecución completa; un OOM termina en `ERROR_ENTORNO`, no reduce silenciosamente la
  calidad ni cambia de modelo.
- Solo los registros `gold` forman pares de supervisión. `context` alimenta recuperación y
  `quarantine` no se entrena. No se bajará la puerta actual de 100 dorados totales, con dorados en
  train/validation/test.
- La prueba queda sellada antes del ajuste. Las métricas incluyen exactitud de herramienta y JSON,
  campos inventados, citas correctas, abstención, latencia y pruebas adversariales con órdenes que
  contienen identificadores o intentos de anular la confirmación.
- Se compara contra `llama3.1:8b`, Qwen sin adaptar y el Transformer. El adaptador solo se promueve
  si mejora la tarea objetivo sin aumentar invenciones ni saltarse confirmaciones.
- El adaptador promovido se exportará a un formato consumible por el runtime local o se servirá
  mediante un backend explícito. Escribir un adaptador Hugging Face sin conectarlo a inferencia no
  cuenta como integración.

## 7. Supervisor y aprendizaje continuo

El supervisor compara Transformer, LLM y reglas deterministas. Registra desacuerdos, pero no los
etiqueta. Solo una confirmación o corrección del operador crea un ejemplo dorado. La vigilancia
puede proponer reentrenamiento cuando haya suficientes dorados nuevos o deriva medida; no puede
promover, ejecutar escrituras eléctricas ni rebajar puertas por sí sola.

La actualización será por repetición completa del histórico aprobado más datos nuevos, con un
conjunto de regresión inmutable, para reducir olvido. El estado de cada modelo aparecerá en la web
con versión, fecha, cobertura, métricas, bloqueo y enlace al manifiesto.

## 8. Seguridad, privacidad y operación

- Todo se ejecuta localmente; el cliente del asistente seguirá rechazando endpoints no locales.
- Antes de descargar pesos se registran repositorio, revisión, licencia, tamaño y SHA-256 cuando el
  proveedor lo exponga.
- No se envían fuentes eléctricas, nombres privados, rutas o resultados a servicios remotos.
- Los datasets exportables sustituyen rutas absolutas y conservan identificadores solo cuando son
  necesarios para probar el contrato del dominio.
- No se eliminan modelos, `output/`, `referencia/`, episodios, índices ni datasets anteriores.
- Un corte, OOM o cancelación deja el activo intacto y un manifiesto de ejecución incompleta.

## 9. Verificación y aceptación

### Código

- Desarrollo TDD: cada cambio empieza con una prueba que falla por la ausencia del comportamiento.
- Pruebas unitarias de partición, fuga, hashes, bloqueo GPU, registros y promoción.
- Integración con procesos reales y pesos pequeños; los dobles no prueban CUDA ni persistencia.
- Suite completa Python sin `skip`/`xfail` atribuibles al alcance y compilación del frontend.

### Datos y modelos

- Auditoría independiente de duplicados y grupos compartidos entre particiones.
- Ejecución real GPU por modelo, reapertura desde disco y reproducción de la prueba fija.
- Reporte por modelo con datos usados, métricas, baseline, activo, decisión y limitaciones.
- Para PINN y GRU, pruebas con datos reales separados; para el LLM, prueba dorada y adversarial.

### Eléctrica

La aceptación final de acciones que tocan PowerFactory conserva sus puertas propias: proyecto
vinculado, ejecución, guardado, reapertura en proceso nuevo, relectura, convergencia y límites. El
informe distinguirá aceptación del modelo de ML y aceptación eléctrica nativa.

## 10. Fundamento científico

- La arquitectura Transformer se basa en autoatención y permite procesamiento paralelo de
  secuencias (Vaswani et al., 2017).
- El modelado conjunto de intención y extracción de ranuras es un contrato reconocido para
  asistentes orientados a tareas (Hardalov et al., 2023).
- LoRA congela el modelo base y aprende matrices de bajo rango; QLoRA añade cuantización NF4 y
  optimizadores paginados para reducir memoria (Hu et al., 2022; Dettmers et al., 2023).
- La adaptación a dominio debe evaluarse contra datos del dominio y preservar generalización;
  Christofidellis (2023) estudia esta relación en su tesis doctoral.
- La predicción de carga en distribución exige datos operativos y evaluación fuera de muestra;
  Almalaq (2019) lo desarrolla en tesis doctoral, Guo (2025) en tesis de maestría y Lin (2023)
  aplica GRU bidireccional a carga de transformadores de distribución.

### Referencias APA 7

Almalaq, A. S. (2019). *Distribution level building load prediction using deep learning*
[Doctoral dissertation, University of Denver]. Digital Commons.
https://digitalcommons.du.edu/etd/1641/

Christofidellis, D. (2023). *Accelerating scientific discovery using domain adaptive language
modelling* [Doctoral thesis, Queen's University Belfast]. Queen's Research Portal.
https://pure.qub.ac.uk/en/studentTheses/accelerating-scientific-discovery-using-domain-adaptive-language-/

Dettmers, T., Pagnoni, A., Holtzman, A., & Zettlemoyer, L. (2023). QLoRA: Efficient finetuning of
quantized LLMs. *Advances in Neural Information Processing Systems, 36*.
https://papers.neurips.cc/paper_files/paper/2023/file/1feb87871436031bdc0f2beaa62a049b-Paper-Conference.pdf

Guo, H. (2025). *Load forecasting and modeling for power system* [Master's thesis, Southern
Methodist University]. SMU Scholar. https://scholar.smu.edu/engineering_electrical_etds/84/

Hardalov, M., Koychev, I., & Nakov, P. (2023). Enriched pre-trained Transformers for joint slot
filling and intent detection. In *Proceedings of RANLP 2023* (pp. 480–493). INCOMA.
https://aclanthology.org/2023.ranlp-1.54/

Hu, E. J., Shen, Y., Wallis, P., Allen-Zhu, Z., Li, Y., Wang, S., Wang, L., & Chen, W. (2022).
LoRA: Low-rank adaptation of large language models. In *International Conference on Learning
Representations*. https://arxiv.org/abs/2106.09685

Lin, W.-L. (2023). *Distribution transformers load forecasting using bidirectional gated recurrent
units* [Master's thesis, National Taipei University of Technology]. National Digital Library of
Theses and Dissertations in Taiwan.
https://ndltd.ncl.edu.tw/cgi-bin/gs32/gsweb.cgi/login?o=dnclcdr&s=id%3D%22111TIT00441105%22.&searchmode=basic

Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., &
Polosukhin, I. (2017). Attention is all you need. *Advances in Neural Information Processing
Systems, 30*. https://arxiv.org/abs/1706.03762

## 11. Criterio de cierre

El trabajo termina cuando todos los componentes del inventario poseen un estado terminal con
evidencia reciente; los candidatos promovidos se reabren y reproducen; los rechazados conservan
motivo y artefactos; y los bloqueados identifican exactamente qué dato falta y cómo obtenerlo. No
se usará «todos reentrenados» si algún componente quedó bloqueado, ni «producción» mientras falte
la aceptación nativa aplicable.
