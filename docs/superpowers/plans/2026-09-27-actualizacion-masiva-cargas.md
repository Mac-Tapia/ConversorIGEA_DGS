# Actualización masiva de cargas CSV/XLSX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Actualizar cargas de uno o varios alimentadores desde CSV/XLSX con vista previa, dry-run real, identidad inequívoca, aplicación atómica por alimentador, validación de flujo y rollback auditable.

**Architecture:** El lector puro normaliza el archivo y construye un plan inmutable por alimentador sin importar PowerFactory. FastAPI custodia el plan y lo ejecuta como trabajo asíncrono; un proceso Python 3.12 mantiene una sola sesión PowerFactory, hace preflight, aplica y verifica cada alimentador secuencialmente y revierte el actual si falla. React pagina la vista previa y exige un dry-run aprobado antes de habilitar la aplicación.

**Tech Stack:** Python 3.12, FastAPI, `csv`, `openpyxl`, PowerFactory 2024 Python API, React 19, TypeScript, pytest, Vitest y Playwright.

**Spec:** `docs/superpowers/specs/2026-09-27-actualizacion-masiva-cargas-design.md`

## Global Constraints

- Los TXT, MDB, CSV y XLSX de origen son de solo lectura; cada ejecución escribe artefactos nuevos bajo `output/load_updates/<timestamp>_<batch_id>/`.
- La regla aprobada es: kW=kvar=kVA=FP=0 o los cuatro vacíos significa `SIN_DATOS` y no modifica la carga; solo `accion=poner_cero` escribe P=Q=0.
- La identidad lógica es `(Alimentador, NetworkID, SED)`; `loc_name` aislado no autoriza una actualización.
- Una fila inválida, faltante o ambigua bloquea su alimentador antes de la primera escritura.
- La atomicidad es por alimentador y todo fallo de escritura, verificación o convergencia exige rollback verificable.
- PowerFactory 2024 se ejecuta con CPython 3.12 y una sola lane serializada; no se realizan escrituras concurrentes.
- La lectura y conciliación pueden paralelizarse, pero deben producir resultados deterministas para la misma entrada.
- Los endpoints actuales de un solo alimentador siguen funcionando como adaptadores de compatibilidad.
- El módulo no crea SED, no corrige códigos por similitud y no cambia topología, interruptores, líneas ni transformadores.
- Las pruebas reales usan los proyectos dedicados `IGEA_DGS_CONVERTER_AL209` e `IGEA_DGS_CONVERTER_IN111` y restauran los valores originales.

## Review Focus

- Fila con cuatro ceros o cuatro vacíos frente a `poner_cero`: debe existir una prueba que demuestre que solo la acción explícita borra demanda (Task 1).
- Dos `ElmLod` con el mismo `loc_name` en alimentadores distintos: la identidad compuesta debe seleccionar uno y rechazar duplicados dentro del mismo alimentador (Task 4).
- XLSX con fórmula sin valor calculado o pares P/Q y kVA/FP incoherentes: debe fallar cerrado antes de crear un plan aplicable (Task 1).
- Fallo intermedio o no convergencia después de escribir: todas las cargas del alimentador deben recuperar P, Q, FP y reparto de fases (Task 4).
- Plan obsoleto por cambio de entrada, DGS, metadatos o proyecto: dry-run y apply deben rechazar el token sin tocar PowerFactory (Task 3 y Task 5).

---

### Task 1: Endurecer el contrato CSV/XLSX y la regla de potencia

**Files:**
- Modify: `src/igea_dgs/loads.py`
- Modify: `tests/test_sed_loads.py`

**Interfaces:**
- Produces: `ACTION_ZERO = "poner_cero"`.
- Produces: `SedLoad.action: str` y `SedLoad.no_data: bool` con semántica de cuatro ceros.
- Produces: `read_workbook(path: Path | str, *, reject_uncached_formulas: bool = True) -> dict[str, SheetRead]`.
- Produces: `validate_power_consistency(kw, kvar, kva, fp, *, tolerance_pct: float = 1.0) -> str | None`.
- Preserves: `write_template`, `read_sheet`, `build_plan` y `plan_to_payload` para consumidores actuales.

- [ ] **Step 1: Escribir pruebas fallidas de cuatro ceros y puesta a cero explícita**

  Agregar `test_four_zero_values_are_no_data_and_leave_existing_load_untouched`, `test_four_blank_values_are_no_data` y `test_put_zero_is_an_explicit_update` en `tests/test_sed_loads.py`. Afirmar que las dos primeras filas no aparecen en `plan.updates` y sí en `plan.no_data`, mientras `poner_cero` produce P=Q=0 en el payload.

- [ ] **Step 2: Ejecutar las pruebas nuevas para verificar que fallan**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_sed_loads.py -k "four_zero or four_blank or put_zero" -q --basetemp=.pytest_tmp/load_contract_red`

  Expected: FAIL porque `poner_cero` no existe y las filas sin datos todavía entran en `updates`.

- [ ] **Step 3: Implementar la acción y excluir `SIN_DATOS` de las actualizaciones**

  En `src/igea_dgs/loads.py`, añadir `ACTION_ZERO`, conservar la acción normalizada en `SedLoad` y hacer que `build_plan` trate una fila `no_data` como mencionada pero sin cambio, salvo `action == ACTION_ZERO`.

- [ ] **Step 4: Escribir pruebas fallidas de coherencia y fórmulas sin caché**

  Agregar `test_inconsistent_pq_and_kva_fp_blocks_row`, `test_consistent_redundant_power_is_accepted` y `test_uncached_xlsx_formula_is_blocking`. La primera debe exceder 1 %, la segunda quedar dentro de 1 % y la tercera crear un XLSX con una fórmula sin resultado almacenado.

- [ ] **Step 5: Ejecutar las pruebas de coherencia para verificar que fallan**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_sed_loads.py -k "inconsistent or redundant or uncached" -q --basetemp=.pytest_tmp/load_formula_red`

  Expected: FAIL porque hoy P/Q siempre prevalece y `data_only=True` no distingue una fórmula sin caché de una celda vacía.

- [ ] **Step 6: Implementar comprobación de coherencia y lectura dual de XLSX**

  Implementar `validate_power_consistency(...)`. Para XLSX, abrir una vista `data_only=False` y otra `data_only=True`; si la primera contiene una fórmula en un campo de potencia y la segunda entrega `None`, registrar un error de fila. Cerrar ambos libros en `finally`.

- [ ] **Step 7: Ejecutar todas las pruebas del lector**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_sed_loads.py -q --basetemp=.pytest_tmp/load_contract_green`

  Expected: PASS; las pruebas del Excel real pueden quedar SKIP solo cuando `referencia/PA217.xlsx` no esté presente en el worktree.

- [ ] **Step 8: Commit**

  ```bash
  git add src/igea_dgs/loads.py tests/test_sed_loads.py
  git commit -m "feat: endurecer contrato de actualización de cargas"
  ```

### Task 2: Construir el plan masivo determinista

**Files:**
- Create: `src/igea_dgs/load_batch.py`
- Create: `tests/test_load_batch.py`
- Modify: `src/igea_dgs/loads.py`

**Interfaces:**
- Consumes: `SheetRead`, `LoadUpdatePlan`, `build_plan`, `model_sed_loads` y `write_template` de Task 1.
- Produces: `FeederLoadContext(feeder, network_id, model, project_name, dgs_sha256, metadata_sha256, revision)`.
- Produces: `BulkLoadUpdatePlan(batch_id, input_sha256, feeders, ignored_sheets, row_errors)`.
- Produces: `build_bulk_update_plan(contexts, sheets, *, input_sha256) -> BulkLoadUpdatePlan`.
- Produces: `bulk_plan_to_payload(plan) -> dict` y `write_bulk_template(contexts, path) -> Path`.

- [ ] **Step 1: Escribir pruebas fallidas de consolidación multi-alimentador**

  Crear `tests/test_load_batch.py` con `test_excel_sheets_create_one_plan_per_feeder`, `test_csv_feeder_column_routes_each_row`, `test_unknown_feeder_blocks_only_that_feeder` y `test_no_sheet_is_silently_dropped`.

- [ ] **Step 2: Ejecutar las pruebas para verificar que fallan**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_load_batch.py -q --basetemp=.pytest_tmp/load_batch_red`

  Expected: FAIL con `ModuleNotFoundError: igea_dgs.load_batch`.

- [ ] **Step 3: Implementar contextos y plan masivo**

  Crear las dataclasses y `build_bulk_update_plan(...)`. Ordenar alimentadores y filas por claves canónicas antes de serializar. Una hoja auxiliar sin columna SED va a `ignored_sheets`; una hoja cuyo nombre coincide con un alimentador pero tiene esquema inválido bloquea ese alimentador.

- [ ] **Step 4: Escribir pruebas fallidas de identidad y determinismo**

  Agregar `test_identity_contains_feeder_network_and_sed`, `test_duplicate_sed_in_same_feeder_is_blocking`, `test_same_sed_in_different_feeders_is_valid` y `test_same_inputs_produce_same_payload_and_hashes`.

- [ ] **Step 5: Ejecutar las pruebas de identidad para verificar que fallan**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_load_batch.py -k "identity or duplicate or same_sed or same_inputs" -q --basetemp=.pytest_tmp/load_identity_red`

  Expected: FAIL hasta que cada payload lleve Alimentador, NetworkID, SED y hashes estables.

- [ ] **Step 6: Implementar serialización y plantilla consolidada**

  Implementar `bulk_plan_to_payload(...)` sin timestamps variables dentro del contenido firmado. Implementar `write_bulk_template(...)`: XLSX con una hoja por alimentador y CSV con columna `Alimentador` obligatoria.

- [ ] **Step 7: Ejecutar pruebas de dominio de cargas**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_sed_loads.py tests/test_load_batch.py -q --basetemp=.pytest_tmp/load_domain_green`

  Expected: PASS.

- [ ] **Step 8: Commit**

  ```bash
  git add src/igea_dgs/loads.py src/igea_dgs/load_batch.py tests/test_sed_loads.py tests/test_load_batch.py
  git commit -m "feat: planificar cargas de varios alimentadores"
  ```

### Task 3: Exponer plantilla, plan y custodia masivos en FastAPI

**Files:**
- Modify: `src/igea_dgs/web/workspace.py`
- Modify: `src/igea_dgs/web/services.py`
- Modify: `src/igea_dgs/web/app.py`
- Create: `tests/test_web_load_batch.py`
- Modify: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `write_bulk_template`, `build_bulk_update_plan` y `bulk_plan_to_payload` de Task 2.
- Produces: `services.load_batch_template(ws, feeders, fmt) -> Path`.
- Produces: `services.create_load_batch_plan(ws, feeders, upload) -> dict`.
- Produces: `services.load_batch_rows(ws, token, *, feeder, status, offset, limit) -> dict`.
- Produces endpoints `GET /load-template`, `POST /load-batch-plan` y `GET /load-batch-plans/{token}/rows`.

- [ ] **Step 1: Escribir pruebas API fallidas de plantilla y plan multi-alimentador**

  En `tests/test_web_load_batch.py`, agregar `test_bulk_template_contains_all_selected_feeders`, `test_bulk_plan_processes_every_sheet` y `test_bulk_csv_requires_feeder_for_multiple_models`.

- [ ] **Step 2: Ejecutar las pruebas para verificar que fallan**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_web_load_batch.py -q --basetemp=.pytest_tmp/web_load_batch_red`

  Expected: FAIL con 404 en los endpoints nuevos.

- [ ] **Step 3: Implementar servicios y endpoints de plan**

  Añadir `load_batch_template`, `create_load_batch_plan` y `load_batch_rows`. El POST multipart recibe un archivo y campos `feeder` repetidos. Guardar el JSON inmutable bajo `ws.plans_dir` y persistir en `ws.plans` su ruta, hashes, revisión y lista de alimentadores.

- [ ] **Step 4: Escribir pruebas fallidas de paginación y plan obsoleto**

  Agregar `test_plan_rows_are_paginated_without_truncating_totals`, `test_input_change_invalidates_batch_plan`, `test_dgs_hash_change_invalidates_batch_plan` y `test_project_mapping_change_invalidates_batch_plan`.

- [ ] **Step 5: Ejecutar las pruebas de custodia para verificar que fallan**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_web_load_batch.py -k "paginated or invalidates" -q --basetemp=.pytest_tmp/load_custody_red`

  Expected: FAIL hasta que `check_load_batch_plan` recalcule y compare revisión y hashes.

- [ ] **Step 6: Implementar validación de vigencia y compatibilidad individual**

  Implementar `check_load_batch_plan(ws, token) -> dict`. Adaptar los endpoints individuales existentes para crear un lote de un alimentador sin duplicar reglas; conservar sus URLs y formas de respuesta actuales.

- [ ] **Step 7: Ejecutar pruebas web relevantes**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_web_load_batch.py tests/test_web_api.py -q --basetemp=.pytest_tmp/web_load_batch_green`

  Expected: PASS.

- [ ] **Step 8: Commit**

  ```bash
  git add src/igea_dgs/web/workspace.py src/igea_dgs/web/services.py src/igea_dgs/web/app.py tests/test_web_load_batch.py tests/test_web_api.py
  git commit -m "feat: exponer planes masivos de cargas"
  ```

### Task 4: Implementar transacción y rollback en PowerFactory

**Files:**
- Create: `tools/powerfactory_load_batch.py`
- Create: `tools/apply_sed_load_batch.py`
- Modify: `tools/apply_sed_loads.py`
- Create: `tests/test_powerfactory_load_batch.py`

**Interfaces:**
- Consumes: payload JSON de `bulk_plan_to_payload` de Task 2.
- Produces: `snapshot_load(obj) -> dict[str, Any]`.
- Produces: `write_load(obj, requested: dict) -> None`.
- Produces: `verify_load(obj, requested: dict) -> list[str]`.
- Produces: `resolve_feeder_loads(app, project_name, feeder_plan) -> dict`.
- Produces: `apply_feeder_transaction(app, feeder_plan, *, dry_run: bool) -> dict`.
- Produces CLI `tools/apply_sed_load_batch.py --plan PATH --dry-run|--apply --output-json PATH`.

- [ ] **Step 1: Escribir pruebas fallidas del preflight de identidad compuesta**

  Crear fakes de PowerFactory y agregar `test_same_loc_name_in_other_feeder_is_not_selected`, `test_duplicate_in_same_feeder_is_ambiguous`, `test_network_id_mismatch_blocks_preflight` y `test_preflight_writes_nothing_when_any_load_is_missing`.

- [ ] **Step 2: Ejecutar el preflight para verificar que falla**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_powerfactory_load_batch.py -k "preflight or same_loc or duplicate or network_id" -q --basetemp=.pytest_tmp/pf_load_preflight_red`

  Expected: FAIL porque el motor transaccional no existe.

- [ ] **Step 3: Implementar conexión, resolución y snapshot sin escrituras**

  Resolver proyecto por nombre exacto. Filtrar `ElmLod` por `loc_name` y `GetAttribute("p:alimentador")`; contrastar NetworkID y proyecto contra el plan firmado. `snapshot_load` debe capturar `mode_inp`, `i_sym`, `plini`, `qlini`, `slini`, `coslini`, `pf_recap` y valores `plini*`/`qlini*` por fase.

- [ ] **Step 4: Escribir pruebas fallidas de modos y verificación**

  Agregar pruebas parametrizadas para PC, PQ, SC, SP y QC, además de `test_unbalanced_load_preserves_phase_shares` y `test_verify_checks_p_q_pf_and_each_phase`.

- [ ] **Step 5: Ejecutar las pruebas de escritura para verificar que fallan**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_powerfactory_load_batch.py -k "mode or unbalanced or verify" -q --basetemp=.pytest_tmp/pf_load_modes_red`

  Expected: FAIL hasta implementar `write_load` y `verify_load`.

- [ ] **Step 6: Implementar escritura y verificación completa**

  Mover la lógica probada de `_escribir_carga` al motor compartido y hacer que el script individual la reutilice. Aplicar las tolerancias de la especificación a P/Q/FP y fases.

- [ ] **Step 7: Escribir pruebas fallidas de rollback y convergencia**

  Agregar `test_write_failure_restores_every_changed_load`, `test_verification_failure_rolls_back`, `test_nonconvergent_load_flow_rolls_back_and_returns_failure`, `test_failed_rollback_is_critical` y `test_dry_run_never_writes`.

- [ ] **Step 8: Ejecutar las pruebas transaccionales para verificar que fallan**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_powerfactory_load_batch.py -k "rollback or nonconvergent or dry_run" -q --basetemp=.pytest_tmp/pf_load_tx_red`

  Expected: FAIL hasta implementar la transacción.

- [ ] **Step 9: Implementar `apply_feeder_transaction` y el CLI de lote**

  Hacer preflight completo, snapshot, escritura, relectura y `ComLdf`. Ante cualquier fallo, restaurar snapshots, volver a ejecutar `ComLdf` y emitir estados `PASS`, `ROLLED_BACK` o `CRITICAL`. El proceso reutiliza una sola `app` para todos los alimentadores y devuelve código distinto de cero si alguno no queda en `PASS`.

- [ ] **Step 10: Ejecutar todas las pruebas del motor PowerFactory**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_powerfactory_load_batch.py tests/test_powerfactory_feeder_metadata.py -q --basetemp=.pytest_tmp/pf_load_batch_green`

  Expected: PASS sin requerir una instalación real de PowerFactory.

- [ ] **Step 11: Commit**

  ```bash
  git add tools/powerfactory_load_batch.py tools/apply_sed_load_batch.py tools/apply_sed_loads.py tests/test_powerfactory_load_batch.py
  git commit -m "feat: aplicar cargas con rollback en PowerFactory"
  ```

### Task 5: Integrar dry-run, aplicación asíncrona y auditoría

**Files:**
- Create: `src/igea_dgs/load_audit.py`
- Modify: `src/igea_dgs/web/services.py`
- Modify: `src/igea_dgs/web/app.py`
- Modify: `src/igea_dgs/web/workspace.py`
- Modify: `tests/test_web_load_batch.py`

**Interfaces:**
- Consumes: CLI y resultados de Task 4.
- Produces: `write_load_batch_artifacts(root, plan, result) -> dict[str, str]`.
- Produces: `services.dry_run_load_batch(ws, ctx, token) -> dict`.
- Produces: `services.apply_load_batch(ws, ctx, token) -> dict`.
- Produces endpoints `POST /load-batch-plans/{token}/dry-run` y `POST /load-batch-plans/{token}/apply`.

- [ ] **Step 1: Escribir pruebas API fallidas del gate dry-run**

  Agregar `test_apply_requires_successful_dry_run`, `test_dry_run_uses_powerfactory_lane`, `test_changed_plan_after_dry_run_is_rejected` y `test_single_feeder_apply_uses_batch_engine`.

- [ ] **Step 2: Ejecutar las pruebas para verificar que fallan**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_web_load_batch.py -k "dry_run or batch_engine" -q --basetemp=.pytest_tmp/web_load_apply_red`

  Expected: FAIL por endpoints inexistentes o porque apply no exige simulación.

- [ ] **Step 3: Implementar trabajos dry-run y apply**

  Invocar `tools/apply_sed_load_batch.py` con el intérprete resuelto por `powerfactory_env.py`. Guardar en el workspace el hash exacto aprobado por dry-run y rechazar apply si cambia cualquier componente.

- [ ] **Step 4: Escribir pruebas fallidas de auditoría y cancelación**

  Agregar `test_audit_contains_before_requested_verified_and_status`, `test_each_run_uses_a_new_directory`, `test_cancel_before_write_is_clean` y `test_cancel_during_feeder_requests_rollback`.

- [ ] **Step 5: Ejecutar las pruebas de auditoría para verificar que fallan**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_web_load_batch.py -k "audit or cancel or new_directory" -q --basetemp=.pytest_tmp/load_audit_red`

  Expected: FAIL hasta que existan artefactos y estados de cancelación.

- [ ] **Step 6: Implementar artefactos inmutables y estados finales**

  Crear `input_manifest.json`, `plan.json`, `preview.csv`, `result.json`, `result.csv`, `rollback.json` y `logs.jsonl`. Incluir hashes y resultados por fila. Exponer `PASS`, `PARTIAL`, `ROLLED_BACK`, `FAILED` y `CRITICAL` sin traducir un retorno PowerFactory fallido a HTTP/job exitoso.

- [ ] **Step 7: Ejecutar pruebas web y de jobs**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_web_load_batch.py tests/test_web_api.py -q --basetemp=.pytest_tmp/load_backend_green`

  Expected: PASS, incluidas las pruebas de cancelación agregadas a `tests/test_web_load_batch.py`.

- [ ] **Step 8: Commit**

  ```bash
  git add src/igea_dgs/load_audit.py src/igea_dgs/web/services.py src/igea_dgs/web/app.py src/igea_dgs/web/workspace.py tests/test_web_load_batch.py
  git commit -m "feat: auditar lotes de cargas asincronos"
  ```

### Task 6: Implementar la experiencia multi-alimentador en React

**Files:**
- Create: `frontend/src/components/LoadBatchPanel.tsx`
- Create: `frontend/src/components/LoadBatchPanel.test.tsx`
- Modify: `frontend/src/components/Modules.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/styles.css`
- Create: `frontend/e2e/load-batch.spec.ts`

**Interfaces:**
- Consumes: endpoints y payloads de Task 3 y Task 5.
- Produces: `LoadBatchPlan`, `LoadBatchRow`, `LoadBatchResult` en `types.ts`.
- Produces: `api.loadBatchPlan`, `api.loadBatchRows`, `api.dryRunLoadBatch` y `api.applyLoadBatch`.
- Produces: `LoadBatchPanel` usado por `LoadsTab`.

- [ ] **Step 1: Escribir pruebas React fallidas de selección y plantilla**

  Crear `LoadBatchPanel.test.tsx` con `selects_one_many_or_all_feeders`, `downloads_one_consolidated_template` y `uploads_xlsx_or_csv_with_repeated_feeder_fields`.

- [ ] **Step 2: Ejecutar las pruebas para verificar que fallan**

  Run: `npm test -- --run src/components/LoadBatchPanel.test.tsx`

  Workdir: `frontend`

  Expected: FAIL porque el componente y los métodos API no existen.

- [ ] **Step 3: Implementar tipos, cliente API y selección**

  Crear las interfaces y métodos exactos. Extraer el flujo de cargas de `Modules.tsx` a `LoadBatchPanel.tsx` sin modificar los demás módulos.

- [ ] **Step 4: Escribir pruebas React fallidas de vista previa paginada**

  Agregar `shows_totals_without_500_row_cap`, `filters_rows_by_feeder_and_status`, `shows_unknown_ambiguous_and_no_data`, y `disables_apply_until_dry_run_passes`.

- [ ] **Step 5: Ejecutar las pruebas de vista previa para verificar que fallan**

  Run: `npm test -- --run src/components/LoadBatchPanel.test.tsx`

  Workdir: `frontend`

  Expected: FAIL en paginación, filtros o gate dry-run.

- [ ] **Step 6: Implementar tabla, dry-run, progreso y auditoría**

  Mostrar totales del servidor, paginar filas, agrupar por alimentador y habilitar `Aplicar` solo cuando el mismo hash tenga dry-run `PASS`. Agregar enlaces a JSON/CSV y estados de rollback.

- [ ] **Step 7: Escribir prueba E2E fallida del recorrido completo**

  Crear `frontend/e2e/load-batch.spec.ts` con un recorrido usando backend simulado: seleccionar AL209 e IN111, descargar plantilla, subir archivo, revisar plan, dry-run, aplicar y descargar auditoría.

- [ ] **Step 8: Ejecutar Vitest, typecheck y build**

  Run: `npm test -- --run && npm run typecheck && npm run build`

  Workdir: `frontend`

  Expected: PASS.

- [ ] **Step 9: Ejecutar el E2E web**

  Run: `npm run test:e2e -- load-batch.spec.ts`

  Workdir: `frontend`

  Expected: PASS.

- [ ] **Step 10: Commit**

  ```bash
  git add frontend/src/components/LoadBatchPanel.tsx frontend/src/components/LoadBatchPanel.test.tsx frontend/src/components/Modules.tsx frontend/src/api.ts frontend/src/types.ts frontend/src/styles.css frontend/e2e/load-batch.spec.ts
  git commit -m "feat: actualizar cargas por lote desde React"
  ```

### Task 7: Crear y ejecutar la aceptación real AL209/IN111

**Files:**
- Create: `tools/load_batch_acceptance.py`
- Create: `tests/test_load_batch_acceptance.py`
- Create: `tests/test_load_batch_real_powerfactory.py`
- Modify: `docs/POWERFACTORY_ACCEPTANCE.md`

**Interfaces:**
- Consumes: motor transaccional de Task 4 y artefactos de Task 5.
- Produces: `run_acceptance(plan_path, *, restore_originals: bool = True) -> dict`.
- Produces: informe `load_batch_acceptance.json` con aplicación, convergencia, restauración y hashes.

- [ ] **Step 1: Escribir prueba fallida del harness de restauración**

  Agregar `test_acceptance_requires_dedicated_projects`, `test_acceptance_always_requests_restore` y `test_acceptance_report_proves_values_were_restored` usando un motor fake.

- [ ] **Step 2: Ejecutar las pruebas para verificar que fallan**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_load_batch_acceptance.py -q --basetemp=.pytest_tmp/load_acceptance_red`

  Expected: FAIL porque el harness no existe.

- [ ] **Step 3: Implementar el harness y documentar el procedimiento**

  El harness debe rechazar proyectos sin prefijo `IGEA_DGS_CONVERTER_`, capturar originales, aplicar un cambio controlado, comprobar valores y convergencia, restaurar originales y comprobar otra vez la convergencia. Documentar comandos y artefactos en `docs/POWERFACTORY_ACCEPTANCE.md`.

- [ ] **Step 4: Escribir pruebas reales opt-in**

  Crear `tests/test_load_batch_real_powerfactory.py` marcado para omitir salvo `IGEA_RUN_REAL_PF=1`. Incluir `test_real_al209_mdb_load_batch_restores_originals`, `test_real_in111_txt_load_batch_restores_originals` y `test_real_combined_batch_reuses_one_application_session`.

- [ ] **Step 5: Ejecutar las pruebas fake del harness**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests/test_load_batch_acceptance.py -q --basetemp=.pytest_tmp/load_acceptance_green`

  Expected: PASS.

- [ ] **Step 6: Ejecutar la aceptación real con Python 3.12 de PowerFactory**

  Run:

  ```powershell
  $env:IGEA_RUN_REAL_PF='1'
  D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest tests\test_load_batch_real_powerfactory.py -v -s --basetemp=.pytest_tmp\load_real_pf
  ```

  Expected: 3 PASS; AL209 e IN111 convergen tras aplicar y después de restaurar; el lote combinado registra una sola conexión `GetApplicationExt`.

- [ ] **Step 7: Inspeccionar los informes reales**

  Verificar que cada informe tenga `not_found=[]`, `ambiguous=[]`, `write_errors=[]`, `verification_errors=[]`, `rollback_errors=[]`, `ComLdf.return_code=0`, `IsLdfValid=true` y valores finales iguales a los originales dentro de tolerancia.

- [ ] **Step 8: Commit**

  ```bash
  git add tools/load_batch_acceptance.py tests/test_load_batch_acceptance.py tests/test_load_batch_real_powerfactory.py docs/POWERFACTORY_ACCEPTANCE.md
  git commit -m "test: validar cargas reales en AL209 e IN111"
  ```

### Task 8: Regresión completa y cierre documental

**Files:**
- Modify: `README.md`
- Modify: `docs/MANUAL_COMANDOS.md`
- Modify: `docs/VALIDACION_INTEGRACION_WEB_2026-09-27.md`

**Interfaces:**
- Consumes: todos los entregables anteriores.
- Produces: instrucciones de operador y matriz final de evidencia.

- [ ] **Step 1: Actualizar documentación operativa**

  Documentar plantilla, acciones `actualizar`/`omitir`/`poner_cero`, regla de cuatro ceros, dry-run obligatorio, estados del lote, rollback, rutas de auditoría y recuperación de errores.

- [ ] **Step 2: Ejecutar toda la suite Python**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp/full_load_batch`

  Expected: PASS; los skips deben corresponder solo a dependencias o pruebas reales opt-in documentadas.

- [ ] **Step 3: Ejecutar toda la verificación frontend**

  Run: `npm test -- --run && npm run typecheck && npm run build && npm run test:e2e`

  Workdir: `frontend`

  Expected: PASS.

- [ ] **Step 4: Ejecutar verificaciones estáticas disponibles**

  Run: `D:\converter\ConversorIGEA_DGS\.venv\Scripts\python.exe -m ruff check src tests tools`

  Expected: PASS. Si Ruff no está instalado, registrarlo como `NOT RUN` y no convertirlo en evidencia de éxito.

- [ ] **Step 5: Repetir la aceptación real después de la suite completa**

  Ejecutar el comando de Task 7 y confirmar que los proyectos dedicados terminan con sus cargas originales y flujo convergente.

- [ ] **Step 6: Revisar custodia y working tree**

  Run: `git status --short && git diff --check`

  Expected: solo los tres documentos de este task antes del commit; ningún MDB, TXT, DGS real, workspace temporal ni informe ignorado se agrega al repositorio.

- [ ] **Step 7: Commit**

  ```bash
  git add README.md docs/MANUAL_COMANDOS.md docs/VALIDACION_INTEGRACION_WEB_2026-09-27.md
  git commit -m "docs: documentar actualizacion masiva de cargas"
  ```

- [ ] **Step 8: Verificación final de historial y estado**

  Run: `git log -12 --oneline && git status --short --branch`

  Expected: la especificación, el plan y ocho commits de implementación aparecen como unidades revisables; la rama está limpia y la evidencia real queda enlazada desde el informe de validación.
