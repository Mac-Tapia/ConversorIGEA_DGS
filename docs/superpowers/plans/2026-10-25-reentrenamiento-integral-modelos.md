# Reentrenamiento integral de modelos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir, conectar y ejecutar un flujo local y auditable que prepare datos sin fuga, ajuste todos los componentes aprendibles, calibre y valide los optimizadores evolutivos, promueva sólo mejoras demostradas y mantenga funcional el asistente cuando un candidato quede bloqueado.

**Architecture:** Un dataset común conserva procedencia y seis niveles de calidad; cada familia de modelo consume una vista propia y publica artefactos bajo un registro atómico común. Un coordinador secuencial arbitra GPU y ejecuta datos → entrenamiento → evaluación → promoción → reapertura. El asistente combina clasificación, recuperación híbrida y herramientas, y solicita una aclaración cuando falta evidencia.

**Tech Stack:** Python 3.12, PyTorch/CUDA, Transformers, PEFT, TRL, bitsandbytes, datasets, sentence-transformers, Ollama local, pytest, FastAPI/React.

**Spec:** `docs/superpowers/specs/2026-10-25-reentrenamiento-integral-modelos-design.md`

## Global Constraints

- Mantener Python `>=3.12,<3.13` por compatibilidad con PowerFactory 2024.
- No importar `powerfactory`, COM ni automatización GUI desde el núcleo de aprendizaje.
- No editar ni copiar a ciegas `.worktrees/cierre-universal-por-set`; reconciliar los commits `9618ecef`, `59f921bc`, `45e78c87`, `579416c6`, `8e33315a`, `ab3f1559`, `9626f5ec` y `4ed0dbf9` por fichero, prueba y hash.
- No iniciar entrenamiento GPU si otro entrenamiento mantiene el bloqueo; descargar Ollama antes de cada fase GPU y conservar siempre el modelo activo.
- Los 98 identificadores del vocabulario actual —o 101 cuando la fuente canónica los confirme— son entidades para expandir ranuras, no ejemplos `gold_human`.
- Sellar test antes de generar paráfrasis; ningún grupo de orden, fuente, episodio, proyecto, documento, versión o familia temporal puede cruzar particiones.
- `context` jamás se convierte en respuesta correcta; un LLM puede proponer texto, nunca autocertificar una etiqueta.
- QLoRA inicial: `Qwen/Qwen3-4B`, NF4, doble cuantización, `r=16`, `alpha=32`, dropout `0.05`, longitud 512, lote 1 y acumulación 16.
- Toda promoción exige reapertura en otro proceso, hashes, métricas por grupo, intervalos del 95 % y ausencia de regresión crítica.
- La aceptación de ML no sustituye guardado, reapertura, relectura, convergencia ni límites eléctricos nativos.
- Algoritmo genético, NSGA-II y jDE son optimizadores ya integrados, no redes entrenables: se registran y validan con al menos 20 semillas, baselines exactos/heurísticos y confirmación eléctrica nativa antes de aplicar propuestas.
- La justificación científica es la del diseño: Self-Instruct, E5, BEIR, MTEB, MTOP, MASSIVE, LoRA/QLoRA, FELM, tesis doctoral de Lippmann y tesis de maestría de Smith.

## Review Focus

- Una misma frase o familia de paráfrasis repetida entre train y validation/test debe bloquear el dataset; Task 1 lo prueba con «reentrena la pinn».
- Cien alimentadores sin confirmaciones deben producir plata con ranura conservada, pero cero oro humano; Task 2 lo prueba con una lista controlada.
- Una consulta con identificador exacto debe conservar el resultado BM25 aunque el embedding prefiera un fragmento semántico incorrecto; Task 3 lo prueba con `CA101`/`CA104`.
- Un adaptador con JSON mejor pero más campos inventados o una omisión de confirmación nunca se promueve; Task 4 lo prueba contra la base.
- Un fallo, OOM o proceso muerto durante promoción deja el puntero anterior reabrible; Task 5 lo prueba con procesos reales pequeños y escritura interrumpida.
- Una configuración evolutiva que mejora el promedio pero produce una isla, lazo prohibido o menor tasa de factibilidad debe rechazarse; Task 8 lo prueba por familia y multisemilla.

---

### Task 1: Reconciliar la base concurrente y formalizar el dataset común

**Files:**
- Create: `src/igea_dgs/asistente/dataset_entrenamiento.py`
- Create: `src/igea_dgs/asistente/calidad_datos.py`
- Modify: `src/igea_dgs/web/services.py`
- Modify: `pyproject.toml`
- Test: `tests/test_asistente_dataset_entrenamiento.py`
- Test: `tests/test_asistente_calidad_datos.py`

**Interfaces:**
- Consumes: `almacen.raiz()`, episodios del gemelo, historial web y eventos de conversión existentes.
- Produces: `RegistroEntrenamiento`, `DatasetConstruido`, `construir_dataset(...)`, `particionar_dataset(...)`, `escribir_particiones(...)`, `auditar_contaminacion(...)` y manifiesto `igea-dgs-training-dataset-v2`.

- [ ] **Step 1: Portar primero las pruebas relevantes de los commits concurrentes y añadir fallos para la taxonomía v2**

  Añadir pruebas que exijan los estados `gold_human`, `gold_native`, `silver_deterministic`, `silver_teacher_verified`, `context` y `quarantine`; grupos indivisibles; hashes; rutas privadas anonimizadas; y rechazo de la repetición «reentrena la pinn» entre particiones.

- [ ] **Step 2: Ejecutar RED**

  Run: `python -m pytest tests/test_asistente_dataset_entrenamiento.py tests/test_asistente_calidad_datos.py -q`

  Expected: FAIL por módulos/estados v2 ausentes, no por error de fixture.

- [ ] **Step 3: Reconciliar la implementación existente y completar v2**

  Implementar `RegistroEntrenamiento` con `quality`, `group_id`, `provenance`, `evidence_hashes`, `license` y `verification`; asignar `gold_native` sólo desde aceptación nativa legible; agrupar antes de particionar; deduplicar exacto y por huella semántica; poner contradicciones y licencias desconocidas en cuarentena.

- [ ] **Step 4: Ejecutar GREEN y regresión del importador**

  Run: `python -m pytest tests/test_asistente_dataset_entrenamiento.py tests/test_asistente_calidad_datos.py tests/test_asistente_web.py -q`

  Expected: PASS, cero `skip`/`xfail` de este alcance.

- [ ] **Step 5: Commit**

  `git commit -m "feat: construye dataset trazable sin fuga"`

### Task 2: Generar cobertura por tareas y aprendizaje activo sin inflar oro

**Files:**
- Create: `src/igea_dgs/asistente/curacion.py`
- Modify: `src/igea_dgs/asistente/sinteticos.py`
- Modify: `src/igea_dgs/asistente/supervisor.py`
- Modify: `src/igea_dgs/asistente/interprete.py`
- Modify: `src/igea_dgs/asistente/tareas.py`
- Test: `tests/test_asistente_curacion.py`
- Test: `tests/test_asistente_supervisor.py`
- Test: `tests/test_asistente_interprete.py`

**Interfaces:**
- Consumes: `RegistroEntrenamiento`, catálogo `TAREAS`, vocabulario y predicciones Transformer/LLM.
- Produces: `expandir_catalogo(tareas, vocabulario)`, `crear_cola_curacion(registros, predicciones)`, `decidir_aclaracion(plan)` y `confirmar_desafio(...)`.

- [ ] **Step 1: Escribir pruebas de cobertura, entidades y aclaración**

  Probar que 101 alimentadores generan plata para tareas aplicables, conservan cada código y no generan `gold_human`; que campos obligatorios ausentes producen una única pregunta específica sin pasos ejecutables; y que sólo una corrección confirmada crea oro.

- [ ] **Step 2: Ejecutar RED**

  Run: `python -m pytest tests/test_asistente_curacion.py tests/test_asistente_supervisor.py tests/test_asistente_interprete.py -q`

  Expected: FAIL por API de curación/aclaración ausente.

- [ ] **Step 3: Implementar generación determinista, paráfrasis verificables y cola activa**

  Generar al menos 20 casos únicos por cada una de las 27 tareas cuando el esquema lo permita, con tres formulaciones y todas las ranuras; validar conservación de identificadores/unidades; priorizar tareas descubiertas, desacuerdo, baja confianza y ataques. Registrar propuestas del LLM como `silver_teacher_verified` únicamente después de validación independiente.

- [ ] **Step 4: Ejecutar GREEN**

  Run: `python -m pytest tests/test_asistente_curacion.py tests/test_asistente_supervisor.py tests/test_asistente_interprete.py tests/test_asistente_sinteticos.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit**

  `git commit -m "feat: añade curacion activa y preguntas aclaratorias"`

### Task 3: Recuperación híbrida, dataset contrastivo y evaluación de embeddings

**Files:**
- Create: `src/igea_dgs/asistente/embeddings.py`
- Modify: `src/igea_dgs/asistente/indice.py`
- Modify: `src/igea_dgs/asistente/ollama.py`
- Create: `tools/asistente_embeddings.py`
- Modify: `pyproject.toml`
- Test: `tests/test_asistente_embeddings.py`
- Modify: `tests/test_asistente_indice.py`

**Interfaces:**
- Consumes: fragmentos citables, preguntas confirmadas/candidatas y manifiesto v2.
- Produces: `ParContraste`, `construir_dataset_contrastivo(...)`, `fusion_rrf(...)`, `evaluar_recuperador(...)`, `entrenar_recuperador(...)` e índice versionado reabrible.

- [ ] **Step 1: Escribir pruebas de RRF, negativos difíciles, abstención y manifiesto**

  Usar fragmentos reales mínimos: `CA101` correcto, `CA104` negativo difícil, versión obsoleta y consulta sin respuesta. Exigir Recall@1/5/10, MRR@10, nDCG@10, cita exacta, hashes de corpus/modelo/segmentación y reapertura idéntica.

- [ ] **Step 2: Ejecutar RED**

  Run: `python -m pytest tests/test_asistente_embeddings.py tests/test_asistente_indice.py -q`

  Expected: FAIL porque no existe RRF ni contrato contrastivo/versionado.

- [ ] **Step 3: Implementar BM25+denso y ajuste opcional**

  Comparar BM25, Ollama `nomic-embed-text` y `intfloat/multilingual-e5-base`; fusionar rangos, nunca puntuaciones incompatibles; entrenar con MultipleNegativesRankingLoss y negativos difíciles si la cobertura pasa; evaluar dimensiones 768/384/192 sin promover una dimensión degradada.

- [ ] **Step 4: Ejecutar GREEN y smoke con encoder real**

  Run: `python -m pytest tests/test_asistente_embeddings.py tests/test_asistente_indice.py -q`

  Run: `python tools/asistente_embeddings.py evaluar --modelo intfloat/multilingual-e5-base --dataset output/web/_asistente/dataset`

  Expected: pruebas PASS; comando produce `metrics.json` y `decision.json`, o estado explícito `BLOQUEADO_POR_DATOS` sin modificar el índice activo.

- [ ] **Step 5: Commit**

  `git commit -m "feat: integra recuperacion hibrida evaluable"`

### Task 4: Adaptación QLoRA funcional y puertas contra invención

**Files:**
- Create: `src/igea_dgs/asistente/qlora.py`
- Create: `src/igea_dgs/asistente/registro_qlora.py`
- Create: `tools/asistente_qlora.py`
- Modify: `src/igea_dgs/asistente/ollama.py`
- Modify: `src/igea_dgs/asistente/interprete.py`
- Modify: `pyproject.toml`
- Test: `tests/test_asistente_qlora.py`
- Test: `tests/test_asistente_registro_qlora.py`

**Interfaces:**
- Consumes: particiones v2, currículo plata→oro y batería sellada.
- Produces: `ConfiguracionQLoRA`, `preflight(...)`, `entrenar_adaptador(...)`, `evaluar_adaptador(...)`, `registrar_candidato(...)`, `promover(...)`, `volver_al_anterior(...)` y backend de inferencia seleccionado explícitamente.

- [ ] **Step 1: Portar pruebas concurrentes y añadir las puertas funcionales**

  Exigir hashes, licencia, revisión base, cobertura por tarea, JSON válido, exactitud de herramienta, conservación de campos, citas, aclaración, abstención, cero salto de confirmación y tasa de invención no superior a la base.

- [ ] **Step 2: Ejecutar RED**

  Run: `python -m pytest tests/test_asistente_qlora.py tests/test_asistente_registro_qlora.py -q`

  Expected: FAIL por módulos QLoRA ausentes en la rama actual.

- [ ] **Step 3: Reconciliar QLoRA existente y completar evaluación/runtime**

  Mantener base congelada, NF4 y configuración global; formar prompts para herramienta/aclaración/cita/abstención; guardar adaptador y tokenizer; exportar/servir por backend explícito; impedir que un adaptador no conectado figure como activo.

- [ ] **Step 4: Ejecutar GREEN y preflight real**

  Run: `python -m pytest tests/test_asistente_qlora.py tests/test_asistente_registro_qlora.py tests/test_asistente_ollama.py -q`

  Run: `python tools/asistente_qlora.py preflight --modelo Qwen/Qwen3-4B`

  Expected: pruebas PASS; preflight confirma CUDA/dependencias/espacio o termina en `ERROR_ENTORNO` trazable sin cambiar el activo.

- [ ] **Step 5: Commit**

  `git commit -m "feat: integra qlora funcional con puertas"`

### Task 5: Registro común y coordinador reanudable de GPU

**Files:**
- Create: `src/igea_dgs/model_registry.py`
- Create: `src/igea_dgs/training_coordinator.py`
- Create: `tools/reentrenar_modelos.py`
- Test: `tests/test_model_registry.py`
- Test: `tests/test_training_coordinator.py`

**Interfaces:**
- Consumes: adaptadores/recuperadores/modelos y sus evaluadores de Tasks 1–4 y modelos existentes.
- Produces: `EstadoModelo`, `RegistroModelo`, `BloqueoGPU`, `TrainingStage`, `TrainingCoordinator.run(resume=True)` y reporte consolidado.

- [ ] **Step 1: Escribir pruebas de estados, atomicidad, bloqueo y reanudación**

  Probar `PROMOVIDO`, `RECHAZADO`, `BLOQUEADO_POR_DATOS`, `ERROR_ENTORNO`; PID vivo/muerto; dos procesos reales compitiendo por lock; fallo entre candidato y puntero; reapertura en subproceso; y orden Transformer→clasificador→GRU→PINN→evolutivos→embeddings→QLoRA.

- [ ] **Step 2: Ejecutar RED**

  Run: `python -m pytest tests/test_model_registry.py tests/test_training_coordinator.py -q`

  Expected: FAIL por registro/coordinador ausentes.

- [ ] **Step 3: Implementar registro, lock y fases reanudables**

  Crear carpetas candidatas inmutables y punteros por `os.replace`; registrar datos, entorno, hardware, semilla, métricas, decisión y smoke reload; liberar Ollama/CUDA entre fases; no recuperar lock salvo PID inexistente.

- [ ] **Step 4: Ejecutar GREEN**

  Run: `python -m pytest tests/test_model_registry.py tests/test_training_coordinator.py -q`

  Expected: PASS y ningún artefacto activo cambia en escenarios de fallo.

- [ ] **Step 5: Commit**

  `git commit -m "feat: orquesta entrenamiento y promocion atomica"`

### Task 6: Fortalecer Transformer y clasificador con splits y métricas reales

**Files:**
- Modify: `src/igea_dgs/asistente/transformer.py`
- Modify: `src/igea_dgs/asistente/clasificador.py`
- Modify: `tools/asistente_entrenar.py`
- Modify: `tests/test_asistente_transformer.py`
- Modify: `tests/test_asistente_clasificador.py`

**Interfaces:**
- Consumes: vistas por modelo del dataset v2 y `RegistroModelo`.
- Produces: búsqueda acotada reproducible, métricas macro/por tarea/por documento, calibración ECE/Brier y decisiones registradas.

- [ ] **Step 1: Escribir pruebas de grupos, peor tarea y documentos completos**

  Exigir que plantillas hermanas y trozos del mismo DOCX no crucen particiones; que una tarea crítica degradada rechace el candidato aunque suba el promedio; y que un subtipo desconocido se abstenga.

- [ ] **Step 2: Ejecutar RED**

  Run: `python -m pytest tests/test_asistente_transformer.py tests/test_asistente_clasificador.py -q`

  Expected: FAIL en las nuevas puertas y agrupación.

- [ ] **Step 3: Implementar selección por validation y registro común**

  Evaluar las configuraciones acotadas de la spec sin tocar test; publicar macro-F1, exactitud conjunta, ECE/Brier, matriz de confusión, peor tarea y latencia; mantener modelo activo ante falta de evidencia real.

- [ ] **Step 4: Ejecutar GREEN**

  Run: `python -m pytest tests/test_asistente_transformer.py tests/test_asistente_clasificador.py tests/test_asistente_sinteticos.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit**

  `git commit -m "feat: valida modelos de lenguaje por grupos"`

### Task 7: Persistir y promover GRU; ampliar puertas PINN/GNN

**Files:**
- Modify: `src/igea_dgs/digital_twin/temporal.py`
- Modify: `src/igea_dgs/digital_twin/oraculo.py`
- Modify: `src/igea_dgs/digital_twin/api.py`
- Create: `tests/test_digital_twin_temporal_registry.py`
- Modify: `tests/test_digital_twin_temporal.py`
- Modify: `tests/test_digital_twin_oraculo.py`

**Interfaces:**
- Consumes: curvas reales con frecuencia/unidades/procedencia, episodios con clase y familia topológica, `RegistroModelo`.
- Produces: `entrenar_temporal_y_promover(...)`, `cargar_temporal(...)`, comparación estacional, métricas por alimentador/SET y puertas PINN por familia/cobertura/OOD.

- [ ] **Step 1: Escribir pruebas de persistencia, cronología y familias**

  Exigir separación cronológica 70/15/15 con gap de una ventana, exclusión de objetivos imputados, mínimo 30 días, reapertura GRU idéntica, superación estacional y rechazo PINN sin diversidad o con una familia degradada.

- [ ] **Step 2: Ejecutar RED**

  Run: `python -m pytest tests/test_digital_twin_temporal.py tests/test_digital_twin_temporal_registry.py tests/test_digital_twin_oraculo.py -q`

  Expected: FAIL por registro temporal y puertas ampliadas ausentes.

- [ ] **Step 3: Implementar persistencia, evaluación y promoción por grupo**

  Guardar arquitectura, escala, pesos, frecuencia, fuentes y particiones; calcular MAE/RMSE/error y hora del pico/cobertura; ampliar PINN con `mae_dorados`, métricas por familia, cobertura del conjunto y detección OOD; nunca usar pseudo-medidas como objetivo.

- [ ] **Step 4: Ejecutar GREEN**

  Run: `python -m pytest tests/test_digital_twin_temporal.py tests/test_digital_twin_temporal_registry.py tests/test_digital_twin_oraculo.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit**

  `git commit -m "feat: registra gru y endurece puertas del gemelo"`

### Task 8: Registrar y validar algoritmo genético, NSGA-II y jDE

**Files:**
- Modify: `src/igea_dgs/digital_twin/evolutivo.py`
- Modify: `src/igea_dgs/web/services.py`
- Create: `src/igea_dgs/digital_twin/evaluacion_evolutiva.py`
- Create: `tools/evaluar_evolutivos.py`
- Modify: `tests/test_digital_twin_evolutivo.py`
- Create: `tests/test_digital_twin_evolutivo_registry.py`

**Interfaces:**
- Consumes: flujo/oráculo fijado por Task 7, familias de grafos, perfiles económicos y `RegistroModelo`.
- Produces: `ConfiguracionEvolutiva`, `evaluar_multisemilla(...)`, `comparar_configuraciones(...)`, registro reabrible y decisión por algoritmo/problema.

- [ ] **Step 1: Escribir pruebas de exactitud, restricciones, multisemilla y registro**

  Conservar óptimos conocidos de objetivo entero, Schaffer y Rosenbrock; añadir enumeración exacta en redes pequeñas, 20 semillas, tasa de factibilidad, brecha, hipervolumen, dispersión, presupuesto de evaluaciones y rechazo absoluto de islas/lazos/violaciones.

- [ ] **Step 2: Ejecutar RED**

  Run: `python -m pytest tests/test_digital_twin_evolutivo.py tests/test_digital_twin_evolutivo_registry.py -q`

  Expected: las 27 pruebas existentes pasan y las nuevas fallan por evaluación/registro ausentes.

- [ ] **Step 3: Implementar evaluación y promoción de configuración**

  Versionar operadores, población, generaciones, semillas, límites, costes, función objetivo, grafo/oráculo y presupuesto; comparar configuración activa, candidata, búsqueda exacta pequeña y heurística determinista; impedir promoción por mejora media cuando empeora factibilidad o una familia crítica.

- [ ] **Step 4: Ejecutar GREEN y benchmark reproducible**

  Run: `python -m pytest tests/test_digital_twin_evolutivo.py tests/test_digital_twin_evolutivo_registry.py tests/test_digital_twin_flujo.py -q`

  Run: `python tools/evaluar_evolutivos.py --seeds 20 --report output/web/_asistente/evolutivos-report.json`

  Expected: pruebas PASS y reporte con GA, NSGA-II, jDE, baselines, intervalos y decisión; ninguna propuesta se aplica en PowerFactory.

- [ ] **Step 5: Verificar consumidor PIDE y aceptación nativa separada**

  Run: `python -m pytest tests/test_digital_twin_evolutivo.py -q -k "web or pide or reconfiguracion or consigna"`

  Expected: consumidor real conserva la propuesta y `confirmar_en_pf`; la aceptación nativa queda pendiente hasta ejecutar guardado/reapertura/convergencia sobre los casos autorizados.

- [ ] **Step 6: Commit**

  `git commit -m "feat: registra y valida optimizadores evolutivos"`

### Task 9: Integración web/CLI, ejecución real y aceptación integral

**Files:**
- Modify: `src/igea_dgs/web/app.py`
- Modify: `src/igea_dgs/web/services.py`
- Modify: `frontend/src/**` sólo en componentes consumidores del estado de modelos
- Modify: `docs/MANUAL_COMANDOS.md`
- Create: `docs/REENTRENAMIENTO_MODELOS.md`
- Create: `tests/test_reentrenamiento_integral.py`
- Modify: `tests/test_asistente_web.py`

**Interfaces:**
- Consumes: `TrainingCoordinator`, registros, configuraciones evolutivas y backends promovidos.
- Produces: endpoints/CLI de inventario, ejecución, estado, curación, métricas, reversión y reporte final con evidencia.

- [ ] **Step 1: Escribir la prueba extremo a extremo sellada**

  Cubrir respuesta con cita, herramienta válida, aclaración sin ejecución, abstención, fallo nativo informado, intento de saltar confirmación, evidencia obsoleta y reinicio que carga los modelos promovidos. Probar que la UI distingue promovido/rechazado/bloqueado/error.

- [ ] **Step 2: Ejecutar RED**

  Run: `python -m pytest tests/test_reentrenamiento_integral.py tests/test_asistente_web.py -q`

  Expected: FAIL por integración/estado incompletos.

- [ ] **Step 3: Conectar consumidores y documentar operación**

  Exponer el coordinador sin bloquear el event loop; mostrar cobertura y motivos; conectar el backend QLoRA o mantener base+RAG+herramientas explícitamente; añadir comandos de construir, evaluar, entrenar, reanudar, revertir y auditar.

- [ ] **Step 4: Ejecutar GREEN, frontend y suite completa**

  Run: `python -m pytest tests/test_reentrenamiento_integral.py tests/test_asistente_web.py -q`

  Run: `npm --prefix frontend run build`

  Run: `python -m pytest -q`

  Expected: PASS completo sin omitir fallos; cualquier timeout se resuelve leyendo el resultado final del proceso, no declarándolo verde.

- [ ] **Step 5: Ejecutar el reentrenamiento real secuencial**

  Run: `python tools/reentrenar_modelos.py run --resume --report output/web/_asistente/training-report.json`

  Expected: cada componente termina `PROMOVIDO`, `RECHAZADO`, `BLOQUEADO_POR_DATOS` o `ERROR_ENTORNO`; cada promoción tiene smoke reload y ninguna fase altera la aceptación eléctrica T12.

- [ ] **Step 6: Auditar evidencia y repetir pruebas selladas contra los pesos reabiertos**

  Run: `python tools/reentrenar_modelos.py verify --report output/web/_asistente/training-report.json --fail-on-incomplete`

  Expected: exit 0 sólo si todos los artefactos, hashes, métricas, decisiones y consumidores son legibles. Un modelo bloqueado es un estado honesto, pero `--fail-on-incomplete` impide declarar “todos reentrenados”.

- [ ] **Step 7: Commit**

  `git commit -m "feat: entrega reentrenamiento integral verificable"`

## Cierre y revisión

- Ejecutar una revisión integral contra el spec y este plan, con foco en los cinco casos de `Review Focus`.
- Corregir hallazgos Critical/Important mediante RED→GREEN y repetir la suite completa.
- Aplicar `superpowers:finishing-a-development-branch`; no fusionar ni publicar sin autorización.
