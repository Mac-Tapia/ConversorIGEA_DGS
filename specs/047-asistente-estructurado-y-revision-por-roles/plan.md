# Asistente estructurado y revisión por roles — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` para ejecutar tarea por tarea. Pasos con casillas; sin delegación salvo autorización aplicable.

**Goal:** Mejorar extracción, recuperación y revisión de propuestas sin conceder autoridad de ejecución al texto de un LLM.

**Architecture:** JSON Schema y resolución determinista antes del plan actual. Recuperación híbrida con reranker evaluable y revisión secuencial acotada por especialistas locales sobre un mismo paquete de evidencias; PEFT solo ante déficit medido.

**Tech Stack:** Python 3.12, Ollama local, sentence-transformers opcional, PEFT/QLoRA local condicionado, React.

**Spec:** [spec.md](spec.md). Dependencias: 043 y 044; conservar intérprete, resolución, herramientas y confirmaciones de 026–027.

## Global Constraints

Rigen la constitución y las restricciones del [plan maestro](../../docs/superpowers/plans/2026-10-31-mejora-integral-ia-conversor.md#global-constraints).
No crear otro registro, particionador o conexión nativa; consumir los contratos de
043 y 044. Antes de editar, comparar diffs y verificar rutas actuales; «integrar»
significa conservar cambios propios y ajenos, no reemplazar árboles completos.
Pruebas nuevas citan `047:RF-n`; no cerrar tareas nativas con mocks.

## Review Focus

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

**Interfaces:** `reordenar(consulta: str, candidatos: Sequence[Mapping], *, modelo: str, revision: str) -> list[dict]` preserva IDs, fuente y fragmento. BM25 aporta candidatos junto a vectores; proteger matches exactos de códigos. Comparar Recall@k, MRR/nDCG, corrección de citas, abstención y latencia con política sellada, sin promover embeddings por empate.

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

