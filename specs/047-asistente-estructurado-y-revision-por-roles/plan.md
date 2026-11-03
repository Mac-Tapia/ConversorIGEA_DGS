# Asistente estructurado y revisión por roles — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` para ejecutar tarea por tarea. Pasos con casillas; sin delegación salvo autorización aplicable.

**Goal:** Mejorar extracción, recuperación y revisión de propuestas sin conceder autoridad de ejecución al texto de un LLM.

**Architecture:** JSON Schema y resolución determinista antes del plan actual. Recuperación híbrida con reranker evaluable y revisión secuencial acotada por especialistas locales sobre un mismo paquete de evidencias; PEFT solo ante déficit medido.

**Tech Stack:** Python 3.12, Ollama local, sentence-transformers opcional, PEFT/QLoRA local condicionado, React.

**Spec:** [spec.md](spec.md). Dependencias: 043 y 044; conservar intérprete, resolución, herramientas y confirmaciones de 026–027.

## Global Constraints

### T6: 200 propuestas y aceptación por alcance

Crear `asistente/aceptacion.py`, `asistente/propuestas_maestro.py`,
`tools/aceptar_agente.py` y `tests/test_aceptacion_agente.py`.
Corregir `ordenes_fijas.generar` para obtener 200 textos únicos deterministas y
rechazar repartos con duplicados en lugar de atribuirles independencia. Auditar
el material histórico como currículo, sin presentarlo como prueba independiente
del alumno que ya lo usó. Las propuestas de aceptación usarán familias nuevas
escritas por el maestro, fixtures públicas con entidades completas y origen
`silver_teacher_verified`; conservar su manifiesto y las tres humanas observadas.
Elegir configuración del revisor local (modelo/contexto) únicamente con selección
del corpus previo; usar después el conjunto sellado de 200. Exigir acierto de tarea
>=0,98 y F1 de entidades >=0,95 para aceptación asistida, sin rebajar umbrales.
Registrar alcance, confirmación obligatoria, cobertura y fallos. Las condiciones
humanas y eléctricas quedan separadas; no activar pesos que no pasaron sus puertas.
La opción de revisión obligatoria consulta al LLM aunque el alumno esté seguro;
si falla el revisor, se solicita aclaración. El selector y evaluador no ejecutan
acciones nativas. Usar JSON Schema por tarea y contexto suficiente para el catálogo,
manteniendo límites de salida y custodia local.
El cliente configurado que atiende en la web conserva los indicadores medidos
`revisar_transformer`, `dos_etapas` y `pensar`; rechaza tipos ambiguos en la
configuración en lugar de cambiar silenciosamente el protocolo. Las configuraciones
anteriores sin esos indicadores mantienen sus valores predeterminados.
Comparar también un protocolo de dos etapas: clasificar intención con esquema
simple y después extraer únicamente los campos de esa tarea. Máximo dos llamadas;
las tareas sin entidades necesitan una sola. Rechazar si el extractor cambia la
tarea elegida. Evaluar esta elección solo en selección antes de las 200 propuestas.
Mostrar en la API `/api/asistente/aceptacion` y en el panel del asistente las
propuestas materializadas/únicas, los eventos humanos/órdenes únicas y el resultado
por alcance. La consulta solo lee evidencia local, sin cargar modelos ni ejecutar
trabajos. La publicación del informe no modifica pesos ni autoriza escrituras.
Fundamento: las tesis de Witossek y Yun Zhang, Gou et al. IJCV y Hsieh et al. ACL,
ya enlazados en este plan, distinguen datos del maestro de validación independiente;
ninguna referencia convierte sintéticos en observaciones humanas.

Rigen la constitución y las restricciones del [plan maestro](../../docs/superpowers/plans/2026-10-31-mejora-integral-ia-conversor.md#global-constraints).
No crear otro registro, particionador o conexión nativa; consumir los contratos de
043 y 044. Antes de editar, comparar diffs y verificar rutas actuales; «integrar»
significa conservar cambios propios y ajenos, no reemplazar árboles completos.
Pruebas nuevas citan `047:RF-n`; no cerrar tareas nativas con mocks.

### T5: Destilación del maestro de sesión, alumno y funcionamiento

**Cubre:** RF-11 a RF-15; consume 044 RF-1 a RF-5 y RF-8.
Crear `asistente/curriculo_maestro.py`, `asistente/destilacion_integral.py`,
`tools/asistente_destilar.py`, `tests/test_destilacion_integral.py` y el particionador
compartido `evaluacion_modelos.py` con `tests/test_evaluacion_modelos.py`.
`tools/asistente_entrenar.py --integral` expone el protocolo a la cola existente de
la web; el servicio usa esa opción y no recalibra umbrales del modelo activo cuando
el candidato queda bloqueado o rechazado. El lanzador anterior se conserva como
compatibilidad experimental, sin usarlo para acreditar esta evaluación independiente.
El currículo declara cuatro conjuntos de familias de frases antes de entrenar;
los ejemplos derivados de cada plantilla permanecen en una sola partición.
Las frases históricas de `ordenes_fijas.FRASES`, revisadas por el maestro de sesión,
pueden ampliar solo entrenamiento; no se usa su partición histórica de prueba.
Las expansiones sintéticas con etiquetas incompatibles quedan en cuarentena; una
contradicción humana bloquea el corpus para no ignorar correcciones.
El maestro Codex de sesión aporta etiquetas y breves justificaciones verificables,
no logits internos ni múltiples votos ficticios. Se usa destilación de respuestas
con objetivos categóricos de una anotación; una distribución one-hot no se anuncia
como incertidumbre estimada del maestro.
Comparar alumno supervisado y alumno con ejemplos del maestro con configuración y
semillas iguales; seleccionar por macroacierto/F1 de selección. Calibrar temperatura
solo en calibración. Abrir prueba una vez al fijar ganador, conservando resultados
por tarea. Las cinco órdenes humanas disponibles se reservan para evaluación real;
no se aumentan mediante duplicados ni sintéticos. Con menos de 200 órdenes reales,
el candidato se conserva y la promoción queda bloqueada. No alterar punteros legacy
ni activar el candidato desde el ensayo.
Guardar artefactos y manifiestos en el registro 043, exigir recarga CUDA en proceso
nuevo y comparar predicciones. El ensayo pasa por `interprete.interpretar` y
`plan.resolver`; comprueba tareas desconocidas, entidades ajenas y autorización,
sin invocar el ejecutor nativo. El CLI mantiene informe aun en error y acepta
`--help` sin Torch/Ollama/datos empresariales. Probar primero los contratos puros,
después ejecutar entrenamiento y regresiones afectadas.
Además del smoke de tres órdenes, evaluar al agente híbrido sobre al menos una
orden sellada por tarea y las humanas únicas, publicando consultas al fallback,
acierto, abstenciones y confirmaciones. Es un diagnóstico sobre la misma prueba
sellada, no otro conjunto independiente ni una razón para reajustar al ganador.

Fundamento: [Hsieh et al., ACL Findings 2023](https://aclanthology.org/2023.findings-acl.507/),
[Hinton et al., 2015](https://research.google/pubs/distilling-the-knowledge-in-a-neural-network/),
[maestría de Witossek, DLR](https://elib.dlr.de/220552/),
[doctorado de Yun Zhang, HKUST](https://researchportal.hkust.edu.hk/en/studentTheses/knowledge-distillation-for-generative-models/)
y [Gou et al., IJCV 2021](https://doi.org/10.1007/s11263-021-01453-z).
Las referencias justifican destilación y evaluación; no prueban que este alumno
supere al maestro o cumpla aceptación eléctrica.

## Review Focus

### T7: Alumno LLM generativo y datos reales (RF-19, RF-20)

Ruling: el usuario pide explícitamente que el alumno sea el LLM local. Se añade un
ajuste generativo real; el clasificador anterior no satisface ese contrato. La
autorización experimental se apoya en el déficit real medido y en la petición de
destilación, sin inventar 200 órdenes humanas ni afirmar suficiencia estadística.

Crear `asistente/llm_destilacion.py`, `tools/llm_destilar.py` y pruebas de contrato.
La publicación local se implementa en `asistente/llm_runtime.py`: verificar hashes
del checkpoint y herramientas fijadas; ejecutar exportación, conversión y
cuantización en procesos secuenciales; publicar GGUF por renombrado después del
código 0; importar con tag nuevo y releer digest. Conservar logs y no activar.
Reutilizar lector TXT, estructura, manifiestos de fuente/vínculos y registro 043;
trabajar solo con los archivos de este proyecto. Custodiar los archivos reales de
referencia por SHA-256/localizador. El maestro redacta instrucciones y respuestas
estructuradas ancladas a esos registros, identificadas como anotaciones del maestro.
Las respuestas de interpretación describen solicitudes, nunca ejecuciones ya hechas.
No generar tensiones, pérdidas, convergencia o aceptación sin informe nativo.

Conservar cuatro particiones por familia de formulación y contexto de fuente.
Reservar una prueba nueva de al menos 200 registros antes de ajustar; no incorporar
el benchmark histórico a entrenamiento. Los casos humanos permanecen separados.
Base: Qwen3-4B-Instruct-2507 NF4 ya verificada; PEFT all-linear, rango 8, BF16,
gradient checkpointing, batch 1/acumulación 8 y pérdida causal solo en la respuesta.
La longitud se comprueba sin truncar datos o etiquetas; abortar si no cabe. Entrenar
el corpus completo, guardar checkpoints por época, elegir únicamente por selección
y conservar semillas, pasos, pérdidas, VRAM, hashes y recarga en proceso nuevo.

Comprobar primero la compatibilidad de adaptadores en el runtime Ollama con la base
GGUF de la misma revisión lógica Instruct-2507. Fijar también revisión/hash de ese
artefacto: NF4 y GGUF son cuantizaciones distintas y exigen comparación real tras
exportación. Si no es compatible, usar un trabajador Transformers local explícito,
sin presentar una exportación fallida como instalación. Mantener esquema estricto,
cola para inferencias largas y todas las confirmaciones existentes.

Fundamento: [maestría Witossek](https://elib.dlr.de/220552/),
[doctorado Zhang](https://repository.hkust.edu.hk/ir/Record/1783.1-151306),
[Gou et al., IJCV](https://doi.org/10.1007/s11263-021-01453-z),
[QLoRA](https://arxiv.org/abs/2305.14314),
[PEFT oficial](https://huggingface.co/docs/peft/developer_guides/quantization).
No se dispone de logits internos del maestro; el método es destilación de respuestas.

- JSON válido con tarea inexistente: T1, test_tarea_desconocida_rechaza.
- SED en otro alimentador pese al libro viejo: T1, test_entidad_respeta_fuente_activa.
- Reranker elimina coincidencia exacta de código: T2, test_codigo_exacto_se_conserva.
- Cuatro roles repiten la misma afirmación sin fuente: T3, test_critico_sin_evidencia_no_aprueba.
- Dataset sintético supera umbral de 200 reales: T4, test_qlora_sin_gold_real_bloquea.

---

### T1: Esquema de salida y entidades del contexto activo

**Cubre:** RF-1, RF-2, RF-10.

**Files:** Modificar `asistente/ollama.py`, `asistente/interprete.py` y `asistente/plan.py`; crear `asistente/contratos_salida.py`, `schemas/asistente_orden_v1.schema.json` y `tests/test_asistente_salida_estructurada.py`.

**Interfaces:** `esquema_orden(vocabulario: Mapping) -> dict` construye esquema de tareas/campos admitidos; `validar_orden(payload: Mapping, contexto: ContextoExperimento, vocabulario: Mapping) -> dict` rechaza desconocidos. Enviar schema en format de Ollama cuando la versión lo soporte; si no, conservar validación local estricta y motivo, nunca aceptar JSON arbitrario. Pasar resultado a resolver actual, sin nueva vía de ejecución.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_tarea_desconocida_rechaza`; `test_entidad_respeta_fuente_activa`: pertenencia TXT/MDB/VNR reconciliada prevalece sobre libro desactualizado; `test_instruccion_en_documento_no_ejecuta`: texto recuperado no crea herramienta; `test_confianza_no_salta_confirmacion`: se mantiene 027:RF-19.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_salida_estructurada.py tests/test_asistente_interprete.py tests/test_asistente_ollama.py tests/test_asistente_tareas.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 047 T1`.

### T2: Recuperación híbrida con reranker contrastado

**Cubre:** RF-3, RF-4.

**Files:** Modificar `asistente/indice.py`; crear `asistente/reranker.py` y `tests/test_asistente_reranker.py`; integrar dataset de evaluación y etapa embeddings de 043.

**Interfaces:** `reordenar(consulta: str, candidatos: Sequence[Mapping], *, modelo: str, revision: str, puntuar=None) -> list[dict]` preserva IDs, fuente y fragmento. BM25 aporta candidatos junto a vectores; proteger matches exactos de códigos. Comparar Recall@k, MRR/nDCG, corrección de citas, abstención y latencia con política sellada, sin promover embeddings por empate.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_codigo_exacto_se_conserva`: consulta SE50106 mantiene su fuente exacta cuando existe; `test_cita_apunta_fragmento_real`: el span citado existe en el documento; `test_sin_evidencia_abstiene`: no fabricar cita; usar corpus de pruebas sin datos privados publicados y evaluación real local.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_reranker.py tests/test_asistente_indice.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 047 T2`.

**Política de adopción, declarada antes de medir (RF-4, RF-27).** Conjunto: `docs/RAG_PREGUNTAS_SINTETICAS_047.json`, sellado por su SHA-256. Son preguntas **sintéticas del maestro de sesión** sobre fragmentos reales del índice: no son órdenes de operadores ni acreditan 027:RF-42. La misma prueba mide `bm25`, `hibrido` y cada reranker, sin ajustar nada con ella. Parámetros fijados: RRF `k=60`; 30 candidatos; respuesta con 6 trozos; `max_length=256`, lotes de 4, solo CUDA. Rerankers candidatos, ambos con revisión fijada en `docs/MODELOS_IA_LOCK.json`: `BAAI/bge-reranker-v2-m3` y `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`. Cada uno reordena los candidatos de la recuperación híbrida.

- Métrica primaria: MRR@10 sobre las preguntas con respuesta.
- `hibrido` se adopta frente a `bm25` si la diferencia media de MRR@10 es positiva (sin promover por empate), Recall@10 no baja y ninguna pregunta de código pierde su primer lugar. Mientras no haya informe, con vectores se usa el híbrido, porque es lo que se ordenó construir; el informe puede apartarlo.
- Un reranker se adopta solo si mejora a **los dos**, `bm25` e `hibrido`: diferencia media de MRR@10 positiva y límite inferior de su IC95 % pareado mayor que cero (`comparar_pareado`, 4000 remuestreos, semilla 0), Recall@10 no menor, ninguna pregunta de código pierde su primer lugar y percentil 95 de latencia de 5 s o menos. Entre dos que cumplan, el de mayor MRR@10.
- Si ninguno cumple, el reranker queda desactivado y esa es la decisión. Con el conjunto cambiado o sin informe, también. Un modelo que no cabe o falla al medir se anota con su error y no se adopta.

**Superficie.** `asistente/reranker.py` carga y reordena, `asistente/evaluacion_rag.py` mide y decide, `tools/asistente_evaluar_rag.py` es la Fase 2 real. Vectores en `vectores.npy` más `vectores_meta.json` (float32): el JSON canónico de `manifiesto_indice` ocupa cientos de MB de memoria con miles de fragmentos y un equipo de 16 GB compartidos no lo admite, así que el índice versionado sigue siendo de la herramienta de embeddings. `nomic-embed-text` con sus prefijos de tarea. El trabajo `asistente_indice` no ocupa el 409 del carril y cede ante cualquier otra orden; se programa tras una pregunta, que ya recibió respuesta con lo que hay, y solo en el servidor real. El reranker adoptado se carga, puntúa y descarga en cada respuesta bajo `turno_gpu`: la GPU de 8 GB la comparten Ollama y los entrenamientos.

**Puerta de abstención, declarada antes de medir (RF-31 a RF-37).** La pidió el usuario («no alucinen») tras medir 0 de 10 con vectores. El conjunto de 76 queda intacto como histórico. Dos conjuntos nuevos y separados, sintéticos del maestro: `docs/RAG_ABSTENCION_CALIBRACION_047.json` (SHA-256 `c5ba77aaca78a92d531475030b9f88cbdb08678614bda758ac794efd0e572437`) y `docs/RAG_ABSTENCION_SELLADO_047.json` (SHA-256 `2faeb8c3973f308bab55b74116ec1651581178151da6c02e8f90f35953a45231`). Cada uno trae 40 preguntas con respuesta, 20 del dominio sin respuesta en los documentos (comprobado leyendo el corpus, sin puntuar) y 20 fuera del dominio. Solo se usa mmarco, el reranker adoptado.

- **Regla.** Reranker calibrado que puntuó: mejor puntuación ≥ su umbral. Si no, con vectores: BM25 ≥ su umbral **o** coseno ≥ su umbral. Sin vectores: BM25 ≥ su umbral propio. Un código exacto hallado cuenta como evidencia (RF-37). Sin umbral para el método disponible, «No lo sé» (RF-33). `UMBRAL_COSENO` no se toca: es la conducta histórica de `abstencion=None`, que ya no usa la web.
- **Calibración.** En cada método, el umbral más bajo que deja abstención ≥ 0,95 en calibración, con margen sobre la puerta de 0,90 porque el umbral se ajusta a esas preguntas. En el par coseno-BM25, el que más preguntas con respuesta conserve; a igualdad, los más bajos. Un valor nulo significa que esa señal no cuenta.
- **Puerta, medida una sola vez en el sellado, para cada método (reranker, híbrido, BM25).** Abstención ≥ 0,90 en las preguntas sin respuesta; Recall@10 con la puerta ≥ Recall@10 sin ella en las mismas preguntas (se elige esta comparación pareada, y no las cifras del conjunto de 76, porque son otras preguntas; esas se informan solo como referencia); MRR@10 no peor de forma significativa: el límite superior del IC95 % pareado de la diferencia no es negativo. «Sin ella» es el umbral histórico.
- **T2 se cierra solo si los tres métodos cumplen.** Si alguno no cumple, se dice y T2 sigue abierta; no se recalibra con lo visto en el sellado.
- **Decisión del usuario, 2026-11-02, tras ver la medición del sellado («acepta»):** T2 se cierra si el reranker cumple la puerta completa y el híbrido y BM25 cumplen la abstención ≥ 0,90. La pérdida de respuestas sin reranker se acepta porque falla por el lado seguro («No lo sé»). No se recalibró nada con el sellado.

### T3: Revisión por roles acotada y trazable

**Cubre:** RF-5, RF-6, RF-7.

**Files:** Crear `asistente/revision_roles.py`, `schemas/revision_propuesta_v1.schema.json`, `tests/test_asistente_revision_roles.py`; integrar con `asistente/orquestador.py`, servicios y UI del asistente existentes.

**Interfaces:** `revisar_propuesta(propuesta: Mapping, evidencia: Mapping, *, contexto: ContextoExperimento, max_rondas: int = 2, cancelado: Callable[[], bool]) -> dict` ejecuta en secuencia roles fuentes/fisica/coste/riesgo con mismo snapshot/hash. Devuelve dictámenes con evidencia_ids, incertidumbres, contradicciones y propuesta final; el validador determinista decide disponibilidad. No acceso de roles a ejecutor ni API PowerFactory. Máximo dos rondas total, presupuesto de tokens/tiempo en config, cola cancelable y registro de cada intervención.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_critico_sin_evidencia_no_aprueba`; `test_dos_rondas_y_cancelacion`: nunca supera dos ni continúa cancelado; `test_desacuerdo_fisico_bloquea`: consenso textual no modifica gate físico; `test_roles_no_escriben`: ninguna llamada al cliente de escritura. Comparar rol único vs revisión con mismos casos, coste/latencia y errores detectados.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_revision_roles.py tests/test_asistente_tareas.py tests/test_asistente_web.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 047 T3`.

### T4: Evaluación real y ajuste condicionado

**Cubre:** RF-8, RF-9.

**Files:** Integrar `asistente/qlora.py`, `asistente/registro_qlora.py` y pruebas del donante tras 043; crear `tests/test_asistente_ajuste_condicionado.py`; ampliar runner y reportes.

**Interfaces:** `decidir_ajuste(metricas_reales: Mapping, dataset_manifest: Mapping) -> dict` devuelve decision necesaria/no_necesaria/bloqueada con evidencia; necesaria solo cuando tarea<0.98 o F1<0.95 en gold real suficiente. La decisión no es estado terminal del registro. Probar carga cuantizada y un paso CUDA con revisión fijada antes de un ajuste completo; medir VRAM y reapertura real de adaptador.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_qlora_sin_gold_real_bloquea`: 200 sintéticos no habilitan decidir suficiencia real; `test_baseline_cumple_no_entrena`: evidencia suficiente y puertas cumplidas da no_necesaria sin fingir entrenamiento; `test_adaptador_reabre`: prueba real de PEFT en subproceso con mismo vocabulario. Evaluación final task>=0.98 y F1>=0.95 sin usar test para elegir hiperparámetros.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_ajuste_condicionado.py tests/test_asistente_qlora.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 047 T4`.

## Cierre y evidencia

Al ejecutar, actualizar [tasks.md](tasks.md) con comandos, resultado, hashes y rutas
de informe; mantener abiertas las condiciones sin evidencia. El estado se escribe
solo en spec.md y se refleja mediante `tools/estado_specs.py --escribir`. Validar
trazabilidad además de las pruebas de cada tarea; no cerrar otras specs por arrastre.

