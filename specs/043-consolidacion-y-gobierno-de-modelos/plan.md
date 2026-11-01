# Consolidación y gobierno de modelos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` para ejecutar tarea por tarea. Pasos con casillas; sin delegación salvo autorización aplicable.

**Goal:** Consolidar un registro y un coordinador reproducibles sin perder las mejoras concurrentes.

**Architecture:** Integrar las implementaciones existentes del donante después de comparar sus diffs. El contexto y el contrato de experimento son comunes a todas las familias; la API publica evidencia del registro, no una promoción inferida del fin de un proceso.

**Tech Stack:** Python 3.12, JSON canónico, SQLite existente, PyTorch/CUDA bajo demanda, FastAPI y React.

**Spec:** [spec.md](spec.md). Dependencias: 024, 026 y 027; integración selectiva del worktree de reentrenamiento.

## Global Constraints

### Preparación reproducible T6 (RF-12)

1. Auditar paquetes del entorno Python 3.12, clones fijados y pesos completos. Fijar las versiones existentes como restricciones antes de instalar paquetes faltantes; conservar informe pip antes/después. Declarar las bibliotecas opcionales en el extra `ml` de `pyproject.toml`, sin convertirlas en requisito de arranque del núcleo; conservar revisiones Git y wheel Windows para pymoo.
2. Crear `docs/MODELOS_IA_LOCK.json` y `tools/preparar_modelos_ia.py`: auditoría local por defecto, descarga explícita de revisiones fijas, verificación de tamaño/SHA-256 para pesos y digest para Ollama. Sin código remoto de modelos ni activación automática.
3. Probar catálogo inválido, archivos truncados y hash incorrecto; ejecutar descarga real, `pip check`, forward de grafos, clases de pronóstico, optimización y modelos locales. Respetar exclusión GPU para operaciones que la usan.
   Comprobar memoria antes de importar/cargar pesos: en sistemas sin contador de compromiso, mínimo 3 GiB físicos para E5, 4 GiB para BGE y 6 GiB para NF4/LoRA. En Windows usar `GlobalMemoryStatusEx`: mínimo físico de 0,5 GiB y margen comprometible de 6 GiB para E5/BGE/evaluador o 8 GiB para NF4. La RAM física libre no mide por sí sola el margen de asignación de Windows; una sonda local acreditó importación Torch/CUDA con 1,32 GiB físicos y 9,13 GiB comprometibles. El contador comprometible también debe bloquear aunque haya RAM física suficiente. Cargar BGE directamente en CUDA con `device_map`, evitando construir primero la copia completa CPU. Recursos insuficientes producen fallo explícito, nunca skip ni aceptación. La base NF4 debe tener licencia/revisión fijadas para la GPU de 8 GB; conservar variantes no seleccionadas y sus parciales como experimentos archivados.
4. Registrar evidencia y cualquier fallo real. La aceptación de las 200 propuestas y las puertas eléctricas conservan su autoridad independiente.

Diagnóstico de memoria contrastado con [Microsoft: memoria y compromiso](https://learn.microsoft.com/en-us/windows/win32/memory/memory-performance-information)
y [Hugging Face: carga de modelos grandes mediante el dispositivo meta](https://huggingface.co/docs/transformers/main/big_models).
Las justificaciones de maestría, doctorado y artículos indexados permanecen en
[el informe de aceptación](../../docs/ACEPTACION_INTEGRAL_AGENTE_2026-10-31.md#fundamento-consultado-en-la-web).

Rigen la constitución y las restricciones del [plan maestro](../../docs/superpowers/plans/2026-10-31-mejora-integral-ia-conversor.md#global-constraints).
No crear otro registro, particionador o conexión nativa; consumir los contratos de
043 y 044. Antes de editar, comparar diffs y verificar rutas actuales; «integrar»
significa conservar cambios propios y ajenos, no reemplazar árboles completos.
Pruebas nuevas citan `043:RF-n`; no cerrar tareas nativas con mocks.

## Review Focus

### T7: Trabajadores y contratos realmente ejecutables

Autorización del usuario 2026-11-01: crear los cuatro CLI que la auditoría encontró
ausentes. Reutilizar selectivamente el worktree `reentrenamiento-integral`, sin
sobrescribir implementaciones modernas ni importar desde el worktree en runtime.
Crear `tools/digital_twin_temporal_entrenar.py`, `tools/evaluar_evolutivos.py`,
`tools/asistente_embeddings.py`, `tools/asistente_qlora.py` y sus módulos auxiliares.
QLoRA reutiliza `llm_destilacion.entrenar_epoca`, la base NF4 fijada y su sellado;
no se hace pasar el dataset v2 de tres partes por el corpus generativo de cuatro.
La evaluación evolutiva de funciones analíticas se etiqueta como tal, sin inventar
mediciones ni aprobación eléctrica. Un algoritmo de búsqueda se evalúa, no se
presenta como red neuronal entrenada. La GRU conserva validación causal actual.
Los embeddings entrenan solo con train y evalúan consultas de prueba explícitas;
consultas extractivas autogeneradas no acreditan benchmark humano independiente.
Todos mantienen artefactos candidatos, informes y confirmaciones; no autoactivan.
Permitir a procesos hijos usar la guardia GPU de su padre solo al cotejar PID y
token reales del lock, sin permitir saltarlo por una variable booleana.
Escribir primero `tests/test_trabajadores_coordinador.py`; observar RED y después
ejecutar contratos/regresiones y operaciones reales adecuadas. Mantener T3 y 050
abiertas hasta la campaña integral y publicación conjunta verificadas.

Fundamento: comparación maestro/alumno de la [maestría Witossek](https://elib.dlr.de/220552/),
retención del [doctorado Mirzadeh](https://doi.org/10.7273/000004632), y separación de
contextos/evaluación en [Nature Machine Intelligence](https://doi.org/10.1038/s42256-022-00568-3).

- Contextos con igual nombre y fuente distinta: T2, test_contexto_distinto_no_reutiliza.
- Lock GPU ilegible o perteneciente a proceso vivo: T1, test_lock_ilegible_bloquea.
- Artefacto promovido que no reabre: T3, test_smoke_fallido_no_promueve.
- Órdenes sintéticas contadas como reales: T2, test_sintetico_no_es_gold_real.
- Informe reanudado con configuración distinta: T3, test_resume_config_distinta_rechaza.

---

### T1: Integrar registro y exclusión de GPU

**Cubre:** RF-1, RF-6.

**Files:** Integrar selectivamente `src/convertersmartgrid/model_registry.py`, `src/convertersmartgrid/training_coordinator.py` y `tools/reentrenar_modelos.py` desde `.worktrees/reentrenamiento-integral/`; crear sus pruebas en raíz si no existen.

**Interfaces:** Preservar `RegistroModelo.registrar_candidato(modelo, *, model_manifest, dataset_manifest, metrics, decision, smoke_reload, artifacts=()) -> dict`, `.promover(modelo, candidate_id)`, `.volver_al_anterior(modelo)` y `TrainingStage(name, run, uses_gpu=True)`. Conservar las siete etapas históricas y `BloqueoGPU`; no usar `os.kill(pid, 0)` en Windows.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_lock_ilegible_bloquea`: un lock corrupto no se borra ni permite entrar; `test_estados_terminales`: el vocabulario del registro coincide exactamente con los cuatro estados. La publicación usa reemplazo atómico y conserva el candidato anterior.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_model_registry.py tests/test_training_coordinator.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 043 T1`.

### T2: Contrato común y custodia de datos

**Cubre:** RF-2, RF-3, RF-4.

**Files:** Crear `src/convertersmartgrid/experimentos.py`; integrar `asistente/dataset_entrenamiento.py` y `asistente/calidad_datos.py` del donante; crear `tests/test_experimentos.py` y adaptar las pruebas de dataset del donante.

**Interfaces:** Definir `ContextoExperimento` inmutable con `source_run_id: str`, `source_mode: str`, `source_fingerprint: str`, `project: str`, `feeders: tuple[str, ...]`, `case_id: str`, `case_role: str`, `year: int | None`, `period: str`, `criterio_fijas: str`, `profile_hash: str`, `topology_hash: str`, `controls_hash: str`, `scenario_hash: str`. `clave_contexto(contexto: ContextoExperimento) -> str` usa JSON canónico y SHA-256. `ExperimentoSpec` contiene contexto, algoritmo, semillas, política, revisión y schema_version; `cargar_experimento(ruta: Path) -> ExperimentoSpec` rechaza campos incompatibles.

- [x] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_contexto_distinto_no_reutiliza`: cambiar source_run_id o criterio_fijas cambia la clave; `test_sintetico_no_es_gold_real`: 200 sintéticos producen contador real=0; `test_duplicados_comparten_grupo`: copias con distinto nombre comparten grupo de observación. Incluir semillas/distribución 041 y bloque/etapa 040–042 en scenario_hash.
- [x] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_experimentos.py tests/test_asistente_dataset_entrenamiento.py tests/test_asistente_calidad_datos.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [x] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [x] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [x] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 043 T2`.

### T3: Runner, reanudación y promoción con reapertura

**Cubre:** RF-5, RF-7.

**Files:** Modificar `tools/reentrenar_modelos.py`, `model_registry.py` y `training_coordinator.py`; crear `tests/test_experimentos_runner.py` y portar regresiones `tests/test_reentrenamiento_integral.py`.

**Interfaces:** Añadir `run --config RUTA` sin retirar argumentos existentes. Comparar hash de `ExperimentoSpec` al reanudar; `verify --report RUTA --fail-on-incomplete` mantiene salida distinta de cero ante estados incompletos. Reutilizar `reabrir_en_subproceso(comando, timeout_s=120, cwd=None) -> dict`; marcar publicación solo después de comprobar `ok` y retorno cero.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_smoke_fallido_no_promueve`: un artefacto ilegible mantiene activo el anterior; `test_resume_config_distinta_rechaza`: cambia una semilla y no reutiliza métricas; `test_etapa_temporal_conserva_alias_gru`: PatchTST se informa como algorithm dentro de la etapa gru. Ejecutar además una reapertura real en subproceso con el artefacto mínimo admitido por cada familia integrada.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_experimentos_runner.py tests/test_reentrenamiento_integral.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 043 T3`.

### T4: Visibilidad y aceptación de integración

El registro común puede conservar un puntero `latest.json` a la última decisión de
candidato, distinto de `active.json`. La web puede usarlo si no existe etapa del
coordinador o si la decisión del registro es más reciente que ese informe,
comprobando sus manifiestos sin releer pesos en HTTP. Un candidato
bloqueado sigue sin activarse ni acredita haber completado todas las familias.

**Cubre:** RF-8.

**Files:** Integrar/adaptar `GET /api/asistente/modelos` en `src/convertersmartgrid/web/app.py` y `services.py`; modificar `frontend/src/components/Asistente.tsx`, `frontend/src/types.ts` y `frontend/src/api.ts`; crear `tests/test_modelos_web.py`.

**Interfaces:** La respuesta tiene `schema_version`, `familias` con `estado`, `candidate_id`, `algorithm`, `report_path`, `gates` y `bloqueos`; una etapa pendiente no se convierte en estado terminal inventado. La carga de informes no ejecuta entrenamiento. El runner existente de trabajos conserva cancelación.

- [ ] Escribir primero las pruebas con las citas RF correspondientes. Aserciones:
  `test_modelos_web_no_infiere_promocion`: proceso terminado sin informe aprobado no muestra PROMOVIDO; `test_importar_nucleo_sin_adaptadores`: arrancar sin PyG/NeuralForecast/pymoo/Pyomo opcionales funciona. Verificar UI con informes de los cuatro estados y `npm --prefix frontend run build`.
- [ ] Ejecutar `.venv/Scripts/python.exe -m pytest -q tests/test_modelos_web.py tests/test_model_registry.py tests/test_training_coordinator.py tests/test_experimentos.py` y observar el fallo
  que demuestra la brecha (o ausencia de interfaz), sin ocultar errores de entorno.
- [ ] Implementar el contrato descrito en los archivos indicados, con el mínimo
  cambio que cubra estas aserciones y conservando las interfaces vigentes.
- [ ] Repetir el comando hasta PASS sin skips de requisitos obligatorios; ampliar
  solo a las regresiones de los módulos tocados y registrar evidencia real indicada.
- [ ] Revisar el diff propio, actualizar `CODIGO_FUENTE.md` si se crea código y
  registrar un commit de alcance propio que cite `spec 043 T4`.

## Cierre y evidencia

### T5: Reutilización reproducible de proyectos de GitHub

**Cubre:** RF-9, RF-10, RF-11. Petición explícita del usuario de priorizar uso/clonación de GitHub.

**Archivos:** crear `docs/UPSTREAM_IA_LOCK.json`, `src/convertersmartgrid/upstream_ia.py`, `tools/preparar_upstream_ia.py`,
`tests/test_upstream_ia.py` y documentación de selección. Las copias quedan en
`external/upstream/`, excluidas del repositorio padre; se preservan sus licencias.

**Interfaz:** `preparar_catalogo(catalogo: Mapping, destino: Path, *, verificar: bool = False) -> dict`.
Cada entrada fija id, URL HTTPS GitHub, commit SHA-1 de 40 dígitos, licencia SPDX,
ruta de licencia y SHA-256 de ese blob Git. La verificación comprueba origen, revisión,
árbol limpio y licencia; no ejecuta scripts del repositorio descargado. No actualizar
automáticamente copias existentes. Adaptadores se implementan en 045–048 consumiendo
el contrato y entorno opcional; clonar no equivale a incorporar ni validar un modelo.

- [ ] Pruebas primero con repositorios Git locales reales: clonación fijada,
  revisión/licencia incorrectas, cambios locales preservados y núcleo sin dependencias nuevas.
- [ ] Observar fallos, implementar herramienta y repetir las pruebas hasta PASS.
- [ ] Clonar y verificar proyectos públicos elegidos; registrar hashes, licencias y uso concreto.
- [ ] Registrar evidencia y commit de alcance propio con referencia a spec 043 T5.

Al ejecutar, actualizar [tasks.md](tasks.md) con comandos, resultado, hashes y rutas
de informe; mantener abiertas las condiciones sin evidencia. El estado se escribe
solo en spec.md y se refleja mediante `tools/estado_specs.py --escribir`. Validar
trazabilidad además de las pruebas de cada tarea; no cerrar otras specs por arrastre.

