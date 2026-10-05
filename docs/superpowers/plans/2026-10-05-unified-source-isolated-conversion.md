# Unified Source-Isolated Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ofrecer MDB, tres TXT y VNR-GIS en una sola interfaz, garantizando que cada ejecución use exclusivamente sus originales custodiados y llegue por el mismo flujo verificable hasta PowerFactory.

**Architecture:** Una instantánea inmutable identifica cada carga mediante `source_run_id`; adaptadores de fuente producen el mismo `CymdistDataset` y estado de preparación. Inventario, conversión DGS y PowerFactory rechazan artefactos cuya ejecución o modo no coincidan con la fuente activa.

**Tech Stack:** Python 3.12, FastAPI, dataclasses, pytest, React 18, TypeScript, Vite, PowerFactory 2024 API, `vnr_etl`.

**Spec:** `docs/superpowers/specs/2026-10-05-unified-source-isolated-conversion-design.md`

## Global Constraints

- Una ejecución activa pertenece exactamente a `txt`, `mdb` o `vnr`; nunca mezcla archivos primarios.
- Los adaptadores leen copias custodiadas con SHA-256 bajo `runs/<run_id>/originales/`.
- Los PDF regulatorios no son paquetes VNR convertibles.
- Catálogos solo completan coincidencias exactas y trazables; no inventan topología, fuente o carga.
- Toda salida y aceptación PowerFactory lleva el mismo `source_run_id` de la ejecución activa.
- Python debe permanecer en `>=3.12,<3.13` por compatibilidad con PowerFactory 2024.
- No se declara VNR real aceptado sin paquete completo; ausencia implica `BLOCKED_MISSING_OFFICIAL_PACKAGE`.

## Review Focus

- Cambio de modo conservando casillas antiguas: debe crear otro run y jamás consumirlas.
- Ruta de servidor modificada después de cargar: el run debe seguir leyendo la copia custodiada.
- ZIP/RAR VNR con traversal, enlaces o archivos duplicados: debe rechazarse sin escribir fuera del run.
- Alimentador VNR con topología pero sin fuente/carga: debe aparecer en inventario y bloquear conversión.
- DGS histórico con el mismo nombre de alimentador: PowerFactory debe rechazarlo por `source_run_id`.

---

### Task 1: Custodia inmutable y contrato de ejecución

**Files:**
- Create: `src/igea_dgs/web/source_runs.py`
- Modify: `src/igea_dgs/web/workspace.py`
- Test: `tests/test_source_runs.py`

**Interfaces:**
- Produces: `SourceFile`, `SourceSnapshot`, `SourceRunManifest`, `create_source_run(ws) -> SourceSnapshot`, `Workspace.active_run_id`, `Workspace.active_run()`.

- [ ] **Step 1: Write the failing tests**
  Add `test_source_run_custodia_originales_y_hashes`, `test_run_txt_no_incluye_slots_mdb_o_vnr`, `test_cambiar_archivo_invalida_run_sin_borrar_historial`, and `test_ruta_servidor_mutada_no_cambia_snapshot`.
- [ ] **Step 2: Run tests to verify they fail**
  Run: `pytest tests/test_source_runs.py -q`
  Expected: FAIL because `source_runs` and `active_run_id` do not exist.
- [ ] **Step 3: Implement custody**
  Define immutable manifests, streaming SHA-256/copy, mode-specific slot allowlists, atomic JSON writes and active-run persistence. `invalidate()` clears active dataset/run eligibility, never historical files.
- [ ] **Step 4: Run tests to verify they pass**
  Run: `pytest tests/test_source_runs.py -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: add immutable source run custody`

### Task 2: Adaptadores comunes TXT y MDB y rechazo de mezcla

**Files:**
- Create: `src/igea_dgs/web/sources/__init__.py`
- Create: `src/igea_dgs/web/sources/base.py`
- Create: `src/igea_dgs/web/sources/txt.py`
- Create: `src/igea_dgs/web/sources/mdb.py`
- Modify: `src/igea_dgs/web/services.py`
- Test: `tests/test_source_adapters.py`
- Test: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `SourceSnapshot` from Task 1.
- Produces: `SourceLoadResult(dataset, catalog_report, readiness, provenance)` and `adapter_for(mode: str) -> SourceAdapter`.

- [ ] **Step 1: Write the failing tests**
  Add parity tests for current TXT/MDB readers, `test_adapter_rechaza_slot_de_otro_modo`, `test_load_crea_run_antes_de_leer`, and `test_convert_rechaza_source_run_mismatch`.
- [ ] **Step 2: Run tests to verify they fail**
  Run: `pytest tests/test_source_adapters.py tests/test_web_api.py -q`
  Expected: FAIL on missing adapter contract and source-run gate.
- [ ] **Step 3: Implement adapters and gate**
  Move branching out of `_read_dataset`; pass only snapshot paths. Stamp inventory, conversions, groups and DGS metadata with `source_run_id`, `source_mode` and source fingerprint.
- [ ] **Step 4: Run focused tests**
  Run: `pytest tests/test_source_adapters.py tests/test_web_api.py -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `refactor: route txt and mdb through source adapters`

### Task 3: Ingesta segura y puente canónico VNR-GIS

**Files:**
- Create: `src/igea_dgs/web/sources/vnr.py`
- Create: `src/vnr_etl/application/cymdist_bridge.py`
- Modify: `src/vnr_etl/connectors/registry.py`
- Modify: `src/vnr_etl/pipeline.py`
- Test: `tests/test_vnr_web_adapter.py`
- Test: `tests/test_vnr_etl.py`

**Interfaces:**
- Consumes: `SourceSnapshot`, `CanonicalModel`, `SourceLoadResult`.
- Produces: `safe_extract_package(path, destination) -> ExtractReport`, `canonical_to_cymdist(model) -> BridgeResult`, `VnrSourceAdapter.load(...)`.

- [ ] **Step 1: Write the failing tests**
  Build a deterministic VNR fixture with two `CODSALIDAMT`; test ZIP traversal/duplicate rejection, feeder enumeration, exact company/period filter, bridge identity, and explicit missing-source/load readiness.
- [ ] **Step 2: Run tests to verify they fail**
  Run: `pytest tests/test_vnr_web_adapter.py tests/test_vnr_etl.py -q`
  Expected: FAIL because safe package ingestion and bridge are absent.
- [ ] **Step 3: Implement minimal VNR adapter**
  Resolve layers/schema at runtime, preserve lineages, require projected CRS and exact fields, map canonical objects to the existing dataset contract, and emit `INVENTORY_ONLY`/`BLOCKED` instead of defaults.
- [ ] **Step 4: Run focused tests**
  Run: `pytest tests/test_vnr_web_adapter.py tests/test_vnr_etl.py -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: adapt complete vnr packages to common dataset`

### Task 4: Descubrimiento oficial y carga manual VNR

**Files:**
- Modify: `src/vnr_etl/discovery/official.py`
- Modify: `src/vnr_etl/discovery/download.py`
- Modify: `src/igea_dgs/web/app.py`
- Modify: `src/igea_dgs/web/workspace.py`
- Test: `tests/test_vnr_official_web.py`

**Interfaces:**
- Produces: `GET /api/vnr/publications`, `POST /api/workspaces/{wid}/vnr/download`, slot `vnr_package` and status `BLOCKED_MISSING_OFFICIAL_PACKAGE`.

- [ ] **Step 1: Write the failing tests**
  Test that discovery exposes evidence/date/hash, rejects a PDF URL, downloads only allowlisted data packages, and accepts manual package upload/path.
- [ ] **Step 2: Run tests to verify they fail**
  Run: `pytest tests/test_vnr_official_web.py -q`
  Expected: FAIL on absent routes/slot and package classification.
- [ ] **Step 3: Implement discovery API**
  Reuse `vnr_etl.discovery`; validate scheme/host/content type/extension, bounded streaming size and hash. Never convert a regulatory document.
- [ ] **Step 4: Run focused tests**
  Run: `pytest tests/test_vnr_official_web.py -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: expose verified vnr package discovery`

### Task 5: Preparación por alimentador y selección uniforme

**Files:**
- Create: `src/igea_dgs/web/readiness.py`
- Modify: `src/igea_dgs/web/services.py`
- Modify: `src/igea_dgs/web/app.py`
- Modify: `tests/test_inventory.py`
- Modify: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `SourceLoadResult.readiness`.
- Produces: `assess_feeder_readiness(dataset, feeder, provenance) -> FeederReadiness`; feeder rows with `readiness`, `blocking_codes`, `source_run_id`, `source_mode`.

- [ ] **Step 1: Write the failing tests**
  Cover one/multiple/all selections for each mode, blocked VNR feeder, exact catalogue failure and conversion of a mixed-readiness selection.
- [ ] **Step 2: Run tests to verify they fail**
  Run: `pytest tests/test_inventory.py tests/test_web_api.py -q`
  Expected: FAIL because feeder readiness is not exposed/enforced.
- [ ] **Step 3: Implement readiness gates**
  Add deterministic state transitions and fail-closed preflight before batch conversion; preserve inventory visibility for blocked feeders.
- [ ] **Step 4: Run focused tests**
  Run: `pytest tests/test_inventory.py tests/test_web_api.py -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: gate conversion by feeder readiness`

### Task 6: Interfaz web de tres alternativas e historial

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/InputsPanel.tsx`
- Modify: `frontend/src/components/FeedersPanel.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `src/igea_dgs/web/app.py`
- Test: `tests/test_web_api.py`

**Interfaces:**
- Consumes: API and feeder fields from Tasks 4-5.
- Produces: third `vnr` mode, active-source banner, VNR discovery/manual controls, readiness filters and source manifest links.

- [ ] **Step 1: Write the failing API contract tests**
  Assert health exposes `vnr`, workspace exposes active run/fingerprint, and history/manifest routes cannot escape their workspace.
- [ ] **Step 2: Run tests to verify they fail**
  Run: `pytest tests/test_web_api.py -q`
  Expected: FAIL on new contract fields/routes.
- [ ] **Step 3: Implement TypeScript/UI changes**
  Extend unions, add controls/statuses, disable conversion/PF actions for blocked or stale rows, and retain existing one/many/all behavior.
- [ ] **Step 4: Verify API and frontend**
  Run: `pytest tests/test_web_api.py -q`
  Expected: PASS.
  Run: `npm run build` in `frontend`
  Expected: exit 0 with TypeScript and Vite build successful.
- [ ] **Step 5: Commit**
  Commit: `feat: add source-isolated vnr workflow to web ui`

### Task 7: Puerta de procedencia en PowerFactory

**Files:**
- Modify: `src/igea_dgs/web/services.py`
- Modify: `tools/powerfactory_acceptance.py`
- Modify: `tests/test_powerfactory_gate.py`
- Modify: `tests/test_powerfactory_feeder_metadata.py`
- Modify: `tests/test_web_api.py`

**Interfaces:**
- Consumes: active `source_run_id`, stamped DGS and feeder metadata.
- Produces: `check_powerfactory_source_run(ws, targets) -> None`; acceptance JSON fields `source_run_id`, `source_mode`, `source_fingerprint`, reread evidence and rollback status.

- [ ] **Step 1: Write the failing tests**
  Add same-name historical DGS rejection, exact-run acceptance, dry-run/actual plan identity, reread field requirements and rollback-report tests.
- [ ] **Step 2: Run tests to verify they fail**
  Run: `pytest tests/test_powerfactory_gate.py tests/test_powerfactory_feeder_metadata.py tests/test_web_api.py -q`
  Expected: FAIL on missing source-run enforcement/evidence.
- [ ] **Step 3: Implement PowerFactory gate**
  Pass source evidence to the acceptance tool, verify before mutation, require effective reread plus `ComLdf`, and record rollback outcome on failure.
- [ ] **Step 4: Run focused tests**
  Run: `pytest tests/test_powerfactory_gate.py tests/test_powerfactory_feeder_metadata.py tests/test_web_api.py -q`
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: bind powerfactory acceptance to source run`

### Task 8: Regresión completa y aceptación real controlada

**Files:**
- Create: `tools/accept_three_sources.py`
- Create: `docs/runbooks/three-source-production-acceptance.md`
- Modify: `README.md`
- Test: `tests/test_three_source_acceptance.py`

**Interfaces:**
- Produces: audited acceptance summary distinguishing static, synthetic, MDB/TXT real, VNR real/blocked and PowerFactory real.

- [ ] **Step 1: Write the failing acceptance-contract test**
  Require per-mode input hashes, feeder counts, selected IDs, DGS hashes, PF evidence level, and explicit `SKIP_MISSING_INPUT`/`BLOCKED_MISSING_OFFICIAL_PACKAGE`.
- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_three_source_acceptance.py -q`
  Expected: FAIL because the acceptance runner does not exist.
- [ ] **Step 3: Implement runner and runbook**
  Use separate workspaces/runs for MDB, TXT and VNR. Never copy values between sources. Select IN111 where present and preserve every artifact under a timestamped audit directory.
- [ ] **Step 4: Run full automated verification**
  Run: `pytest --basetemp=.pytest_tmp -q`
  Expected: zero failures; report pass/skip totals.
  Run: `npm run build` in `frontend`
  Expected: exit 0.
- [ ] **Step 5: Run real acceptance**
  Execute MDB and TXT against their current originals, then VNR against the official/manual package if available. Run IN111 through PowerFactory only after same-run preflight; capture reread and `ComLdf`. A missing VNR package must be reported as blocked, never substituted with synthetic evidence.
- [ ] **Step 6: Reconcile evidence against the spec**
  Confirm every requirement in Sections 2-10 has a test or real artifact and list any remaining environmental blocker.
- [ ] **Step 7: Commit**
  Commit: `test: add audited three-source production acceptance`
