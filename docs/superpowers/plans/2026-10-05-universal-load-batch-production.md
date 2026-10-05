# Universal Load Batch Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidar el módulo web existente para actualizar cargas y crear SED en uno o varios alimentadores, con plan previo, relectura, `ComLdf` y rollback por alimentador.

**Architecture:** Los libros se normalizan y distribuyen por identidad de SED, hoja, nodo o coordenada. Un plan inmutable se aplica secuencialmente en PowerFactory mediante escenario/variación aislados y produce evidencia por alimentador sin contaminar los que ya terminaron.

**Tech Stack:** Python 3.12, FastAPI multipart, openpyxl/CSV, pytest, React 18, TypeScript, Vite, PowerFactory 2024 API.

**Spec:** `docs/superpowers/specs/2026-10-05-universal-reconstruction-loads-design.md`

## Global Constraints

- El módulo no supone empresa, alimentador, proyecto o CRS concretos.
- La carga base permanece intacta; actualización y SED nuevas usan escenario y variación.
- Cada fila acepta exactamente un par compatible: `kW+kvar`, `kW+FP` o `kVA+FP`.
- Los valores actuales y propuestos viven en columnas diferentes.
- El plan se verifica contra proyecto, alimentadores, archivos y hashes antes de escribir.
- Cada alimentador se relee y ejecuta `ComLdf`; un fallo revierte solo su mutación.
- Electro Dunas/IN111 se usa como prueba real disponible, no como dependencia.
- Los cambios locales preexistentes del módulo se auditan y se incorporan por hunks; no se absorben ediciones ajenas.

## Review Focus

- La misma SED en dos hojas: error previo, nunca doble aplicación.
- Libro multialimentador con una hoja genérica: asignar por identidad/nodo/coordenada y mostrar evidencia.
- Dos pares de potencia inconsistentes: error de fila; pares equivalentes dentro de tolerancia son válidos.
- Fallo de `ComLdf` en el segundo alimentador: revertir el segundo y conservar evidencia del primero.
- Proyecto PowerFactory cambiado después del plan: rechazar por conflicto de versión antes de mutar.

---

### Task 1: Caracterizar y cerrar el parser multialimentador

**Files:**
- Modify: `src/igea_dgs/loads.py`
- Modify: `src/igea_dgs/loads_create.py`
- Modify: `tests/test_sed_loads.py`
- Modify: `tests/test_sed_create.py`

**Interfaces:**
- Produces: `split_by_feeder(libro, sed_feeder, feeders)`; `split_create_by_feeder(libro, models)`; stable `SheetRead`/`NewSedLoad` errors.
- Consumes: existing workbook readers and canonical feeder models.

- [ ] **Step 1: Add missing failing edge tests**

Add the five Review Focus parser cases: duplicate SED across sheets, generic-sheet identity routing, node routing, coordinate tie/ambiguity and inconsistent power pairs.

```python
assert split['F-A'].rows[0].sed_code == 'SED-001'
assert any('más de una hoja' in error for error in split['F-A'].errors)
```

- [ ] **Step 2: Run tests and identify which gaps fail**

Run: `pytest tests/test_sed_loads.py tests/test_sed_create.py -q`
Expected: at least the newly added ambiguity/version assertions fail; preserve already-passing characterization cases.

- [ ] **Step 3: Complete normalization and routing**

Keep current tolerances explicit; never infer an existing SED by coordinates when its identity maps elsewhere. For new SED coordinate ties, return an ambiguity error rather than selecting by dictionary order.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_sed_loads.py tests/test_sed_create.py -q`
Expected: PASS.

- [ ] **Step 5: Commit only module-related hunks**

```bash
git add -p src/igea_dgs/loads.py src/igea_dgs/loads_create.py tests/test_sed_loads.py tests/test_sed_create.py
git commit -m "feat: normalize multi-feeder load workbooks"
```

### Task 2: Plan inmutable y custodia de libros

**Files:**
- Create: `src/igea_dgs/web/load_batch.py`
- Modify: `src/igea_dgs/web/workspace.py`
- Modify: `src/igea_dgs/web/services.py`
- Modify: `src/igea_dgs/web/app.py`
- Test: `tests/test_load_batch_plan.py`

**Interfaces:**
- Produces: `LoadBatchPlan`, `FeederLoadPlan`, `create_load_batch_plan(ws, project, feeders, update_file, create_file, economics)`, `require_current_load_batch_plan(ws, token)`.
- Consumes: Task 1 parsers, source-run identity and PowerFactory project inventory.

- [ ] **Step 1: Write failing custody/version tests**

Assert uploaded books are copied under a plan directory with SHA-256; token is immutable; order is preserved; changed project/run/file invalidates apply; and no plan with row errors is applicable.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_load_batch_plan.py -q`
Expected: FAIL because the current plan lives as loosely coupled dictionaries/uploads.

- [ ] **Step 3: Implement typed plan and custody**

Persist `load_batch_plan.json` atomically with project identity, ordered feeders, input hashes, source run/fingerprint, row routing evidence and economic parameters.

- [ ] **Step 4: Route existing endpoints through the typed plan**

Keep `POST /lote/plan` and `POST /lote/{token}/apply`; return `409 LOAD_BATCH_PLAN_STALE` before scheduling a job when any identity differs.

- [ ] **Step 5: Run focused API tests**

Run: `pytest tests/test_load_batch_plan.py tests/test_web_api.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/web/load_batch.py src/igea_dgs/web/workspace.py src/igea_dgs/web/services.py src/igea_dgs/web/app.py tests/test_load_batch_plan.py
git commit -m "feat: custody immutable load batch plans"
```

### Task 3: Aplicación PowerFactory por alimentador

**Files:**
- Modify: `tools/aplicar_lote_cargas.py`
- Modify: `tools/apply_sed_loads.py`
- Modify: `tools/create_sed_loads.py`
- Modify: `src/igea_dgs/web/services.py`
- Test: `tests/test_load_batch_powerfactory.py`

**Interfaces:**
- Consumes: `LoadBatchPlan` from Task 2.
- Produces: `apply_feeder_plan(app, feeder_plan) -> FeederApplyResult`; result fields `before`, `after`, `created`, `comldf`, `rollback`, `status`.

- [ ] **Step 1: Write failing fake-engine tests**

Cover scenario/variation creation, P/Q/FP/phases reread, `ComLdf`, failure on second feeder, rollback and continuation policy. Assert the first feeder remains accepted while the second restores all values/created objects.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_load_batch_powerfactory.py -q`
Expected: FAIL on missing per-feeder result/rollback guarantees.

- [ ] **Step 3: Implement a per-feeder transaction boundary**

Snapshot mutable attributes and created-object identities before applying. Activate a dedicated scenario/variation, apply, reread, run `ComLdf`, then commit the result or restore values/delete only newly created objects.

- [ ] **Step 4: Emit append-only batch evidence**

Write one JSON record after each feeder and a reconciled summary at the end so interruption never loses completed evidence.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_load_batch_powerfactory.py tests/test_sed_loads.py tests/test_sed_create.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/aplicar_lote_cargas.py tools/apply_sed_loads.py tools/create_sed_loads.py src/igea_dgs/web/services.py tests/test_load_batch_powerfactory.py
git commit -m "feat: apply load batches with per-feeder rollback"
```

### Task 4: Consolidar la interfaz web de cargas

**Files:**
- Modify: `frontend/src/components/LoteTab.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/Modules.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_load_batch_ui_contract.py`

**Interfaces:**
- Consumes: Task 2 plan API and Task 3 result events.
- Produces: project/feeder selection, file upload, routing evidence, plan modal, progress and downloadable result.

- [ ] **Step 1: Write failing UI contract tests**

Assert the tab is reachable, generic labels are used, one/both books work, ordered feeders are preserved, row errors disable apply, and results distinguish applied/rolled-back/review states.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_load_batch_ui_contract.py -q`
Expected: FAIL on missing result/provenance states even if the current draft tab renders.

- [ ] **Step 3: Complete UI contracts and evidence views**

Integrate the existing `LoteTab` draft without company-specific text. Show current/proposed values, routing basis, scenario/variation names, per-feeder `ComLdf` and rollback.

- [ ] **Step 4: Verify API and build**

Run: `pytest tests/test_load_batch_ui_contract.py tests/test_web_api.py -q`
Expected: PASS.

Run: `npm run build` in `frontend`
Expected: exit 0.

- [ ] **Step 5: Commit only load-UI hunks**

```bash
git add frontend/src/components/LoteTab.tsx frontend/src/App.tsx frontend/src/api.ts frontend/src/types.ts frontend/src/components/Modules.tsx frontend/src/styles.css tests/test_load_batch_ui_contract.py
git commit -m "feat: expose universal load batch workflow"
```

### Task 5: Regresión completa y aceptación real de cargas

**Files:**
- Create: `tools/accept_load_batch.py`
- Create: `tests/test_load_batch_acceptance.py`
- Create: `docs/runbooks/load-batch-production-acceptance.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: all prior tasks and the reconstruction source identity.
- Produces: audited summary with project, ordered feeders, input hashes, before/after values, created objects, `ComLdf` and rollback.

- [ ] **Step 1: Write failing generic acceptance test**

Use projects/feeders `UTILITY_PROJECT`, `F-A`, `F-B` and SED codes unrelated to Electro Dunas. Require a mixed workbook and an injected second-feeder failure.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_load_batch_acceptance.py -q`
Expected: FAIL until the runner persists the complete evidence contract.

- [ ] **Step 3: Implement runner and runbook**

The runner has explicit dry-run and real-PowerFactory modes and never claims real persistence from fake tests. Document recovery and rerun commands plus the scientific basis referenced by the spec.

- [ ] **Step 4: Run full automated verification**

Run: `pytest --basetemp=.pytest_tmp\load_batch -q`
Expected: zero failures; record pass/skip/warning totals.

Run: `npm run build` in `frontend`
Expected: exit 0.

- [ ] **Step 5: Run real controlled acceptance**

Use the current real project containing IN111 only as an example. Prepare one safe update, verify plan, apply in an isolated scenario, reread P/Q/FP/phases, execute `ComLdf`, and verify rollback with a deliberately failing second dry-run or disposable scenario.

- [ ] **Step 6: Commit**

```bash
git add tools/accept_load_batch.py tests/test_load_batch_acceptance.py docs/runbooks/load-batch-production-acceptance.md README.md
git commit -m "test: verify universal load batch workflow"
```

### Task 6: Final verification, commit reconciliation and push

**Files:**
- Modify only files from Tasks 1–5 if verification finds a tested defect.

**Interfaces:**
- Consumes: both implementation plans and their commits.
- Produces: clean scoped commit series and pushed branch `lectura-de-las-dos-disposiciones`.

- [ ] **Step 1: Verify both plans against the specification**

Map every requirement in Sections 2–14 to a test, artifact or explicit external blocker.

- [ ] **Step 2: Run final verification**

Run: `pytest --basetemp=.pytest_tmp\final -q`
Expected: zero failures.

Run: `npm run build` in `frontend`
Expected: exit 0.

Run focused real acceptance commands from both runbooks and inspect the JSON evidence rather than command exit alone.

- [ ] **Step 3: Audit version control scope**

Run: `git diff --check`, `git status --short`, `git log --oneline`, and inspect every commit. Preserve unrelated user files/hunks and record any intentionally uncommitted work.

- [ ] **Step 4: Push**

Run: `git push origin lectura-de-las-dos-disposiciones`
Expected: remote branch updated to the verified HEAD. If authentication or remote policy blocks the push, report the exact error without claiming publication.
