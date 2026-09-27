# Integración web y retiro de GUI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidar React 19 + FastAPI como única interfaz, mostrar la relación real carga–alimentador, conservar todas las ventanas actuales y retirar completamente Tkinter después de probar la equivalencia funcional.

**Architecture:** Integrar primero los cambios ya aislados de Grid adaptativo, procedencia y exportación; después añadir un inventario tipado y paginado consumido por FastAPI y por la ventana React «Cargas de SED». Las operaciones de CPU seguirán fuera del event loop y PowerFactory conservará un carril exclusivo; la GUI antigua solo se elimina tras una regresión end-to-end satisfactoria.

**Tech Stack:** Python 3.12, FastAPI, React 19, TypeScript 5.8, Vite 6, pytest, Vitest, React Testing Library, Playwright, PowerFactory 2024.

**Spec:** `docs/superpowers/specs/2026-09-27-integracion-web-y-retiro-gui-design.md`

## Global Constraints

- Conservar las ventanas Resultados, Cargas de SED, SED nuevas, Catálogo de parámetros y Sistema completo.
- Conservar Entradas, Opciones, tabla de alimentadores, trabajos, cancelación y Registro.
- El alimentador proviene de la trazabilidad eléctrica; nunca del nombre combinado de la Grid ni de proximidad.
- Admitir uno, dos o más alimentadores sin listas fijas de códigos.
- Mantener Python `>=3.12,<3.13` por compatibilidad binaria con PowerFactory 2024.
- Mantener un solo carril de PowerFactory y paralelismo acotado para conversiones independientes.
- No fusionar completa la rama `feat/robustecimiento-igea`; portar únicamente unidades revisadas.
- No eliminar la GUI antigua hasta superar la puerta de equivalencia web.
- No declarar validación real de PowerFactory a partir de dobles o pruebas sintéticas.
- No añadir React Flow, Cytoscape ni edición topológica en este alcance.

## Review Focus

- Una Grid conjunta `NA203_NA205` debe conservar `NA203` o `NA205` por carga, no copiar el nombre de la Grid; se prueba en Tasks 1–3.
- Una carga sin camino o con propietarios incompatibles debe aparecer como `DESCONECTADO` o `AMBIGUO`, nunca recibir un valor por defecto; se prueba en Task 2.
- Consultas sobre decenas de miles de cargas deben estar paginadas y ordenadas de forma determinista; se prueba en Tasks 2–4.
- Reiniciar el servidor no debe validar como vigente un inventario de entradas que cambiaron; se prueba en Tasks 2 y 5.
- La retirada de Tkinter no debe romper detección de Python/PowerFactory ni ninguna ventana web; se prueba en Tasks 6–7.

---

### Task 1: Integrar Grid adaptativo, procedencia y exportaciones completas

**Files:**
- Modify: files changed by commits `86327fa..7f01d8f`
- Preserve: `docs/superpowers/specs/2026-09-27-integracion-web-y-retiro-gui-design.md`
- Test: `tests/test_hoja_y_coordenadas.py`
- Test: `tests/test_feeder_metadata.py`
- Test: `tests/test_na203_na205_acceptance.py`
- Test: `tests/test_group_parallel_export.py`
- Test: `tests/test_web_api.py`

**Interfaces:**
- Consumes: current branch plus the twelve ordered commits on `feat/grid-alimentador-implementation`.
- Produces: `feeder_name` provenance, adaptive `diagram_sheet=None`, PowerFactory metadata, `Name → Alimentador` mapping and `electrical_tables` manifests.

- [ ] **Step 1: Create the isolated integration worktree**

Use `superpowers:using-git-worktrees`; branch from the commit containing this plan and record the merge base.

- [ ] **Step 2: Cherry-pick the feature commits in their original order**

Run: `git cherry-pick 86327fa e3af012 23a7bcd d2450ea 7701937 05baf20 a62b356 953eee6 9d4f43b bee33cd a5666ee 7f01d8f`

Expected: all twelve commits apply; resolve documentation conflicts by preserving this plan and its spec.

- [ ] **Step 3: Run focused regression tests**

Run: `python -m pytest tests/test_hoja_y_coordenadas.py tests/test_feeder_metadata.py tests/test_powerfactory_feeder_metadata.py tests/test_group_parallel_export.py tests/test_na203_na205_acceptance.py tests/test_web_api.py -q`

Expected: PASS; fixture-dependent tests may SKIP only with their documented missing-input reason.

- [ ] **Step 4: Build the unchanged frontend**

Run: `npm run build` in `frontend`

Expected: TypeScript and Vite build succeed.

- [ ] **Step 5: Record the integration gate**

No new commit is needed beyond the cherry-picks; record their range and test output in the execution ledger.

---

### Task 2: Crear el inventario tipado de cargas y SED

**Files:**
- Create: `src/igea_dgs/load_inventory.py`
- Modify: `src/igea_dgs/web/workspace.py`
- Modify: `src/igea_dgs/web/services.py`
- Create: `tests/test_load_inventory.py`

**Interfaces:**
- Consumes: `CymdistDataset`, `FeederModel`, `Reglas`, `Catalogo`, and per-load `feeder_name` from Task 1.
- Produces: `LoadInventoryRow`, `LoadInventoryPage`, `build_load_inventory(...)`, `query_load_inventory(...)`, and a workspace cache invalidated with the dataset.

- [ ] **Step 1: Write failing ownership and electrical-field tests**

Add tests:

- `test_inventory_keeps_real_feeder_inside_combined_grid`
- `test_inventory_reports_disconnected_and_ambiguous_without_guessing`
- `test_inventory_exposes_load_and_transformer_electrical_fields`
- `test_inventory_accepts_arbitrary_feeder_codes`

Assert `Name=SE50033`, `Grid=NA203_NA205`, and `Alimentador` equal to the owning feeder, never `NA203_NA205`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/test_load_inventory.py -q`

Expected: FAIL because `igea_dgs.load_inventory` does not exist.

- [ ] **Step 3: Implement the immutable row and query contracts**

Define:

```python
@dataclass(frozen=True)
class LoadInventoryRow: ...

@dataclass(frozen=True)
class LoadInventoryPage:
    total: int
    offset: int
    limit: int
    rows: tuple[LoadInventoryRow, ...]

def build_load_inventory(dataset, networks, *, reglas, catalogo, grid_name=None) -> tuple[LoadInventoryRow, ...]: ...

def query_load_inventory(rows, *, feeder=None, status=None, search=None,
                         offset=0, limit=100) -> LoadInventoryPage: ...
```

Build each feeder model once, join `Load` and `Sed` by stable load key, and sort by `(alimentador, name, section_id, device_number)`.

- [ ] **Step 4: Add pagination and invalid-bound tests**

Add `test_inventory_pagination_is_stable` and `test_inventory_rejects_negative_offset_and_out_of_range_limit`; allowed `limit` is `1..500`.

- [ ] **Step 5: Run the tests and verify RED for bounds**

Run: `python -m pytest tests/test_load_inventory.py -q`

Expected: new bounds tests FAIL until validation is implemented.

- [ ] **Step 6: Implement filtering, pagination and cache invalidation**

Add `Workspace.load_inventory_cache`; clear it in `Workspace.invalidate()`. Cache keys must include loaded dataset identity and selected Grid/feeders, never only workspace ID.

- [ ] **Step 7: Run focused and full Python suites**

Run: `python -m pytest tests/test_load_inventory.py tests/test_model_v2.py tests/test_combine.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/igea_dgs/load_inventory.py src/igea_dgs/web/workspace.py src/igea_dgs/web/services.py tests/test_load_inventory.py
git commit -m "feat: crear inventario tipado de cargas"
```

---

### Task 3: Publicar inventario paginado y exportaciones por FastAPI

**Files:**
- Modify: `src/igea_dgs/web/app.py`
- Modify: `src/igea_dgs/web/services.py`
- Modify: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `query_load_inventory(...)` from Task 2 and existing workspace/session validation.
- Produces: `GET /api/workspaces/{wid}/electrical-inventory` and `GET /api/workspaces/{wid}/electrical-inventory.{fmt}` for `csv|json`.

- [ ] **Step 1: Write failing API contract tests**

Add:

- `test_electrical_inventory_requires_loaded_workspace`
- `test_electrical_inventory_filters_feeder_status_and_search`
- `test_electrical_inventory_paginates_deterministically`
- `test_electrical_inventory_rejects_invalid_bounds`
- `test_electrical_inventory_csv_and_json_match_screen_rows`

Assert response keys `total`, `offset`, `limit`, `filters`, `rows`; assert each row includes `name`, `grid`, `alimentador`, `network_id`, `sed`, terminals, electrical values, `status`, `diagnostic`, and `provenance`.

- [ ] **Step 2: Run the API tests and verify RED**

Run: `python -m pytest tests/test_web_api.py -k electrical_inventory -q`

Expected: FAIL with 404 for the new endpoints.

- [ ] **Step 3: Implement service functions**

Add:

```python
def electrical_inventory(ws: Workspace, *, feeder: str | None, status: str | None,
                         search: str | None, offset: int, limit: int) -> dict[str, Any]: ...

def export_electrical_inventory(ws: Workspace, *, fmt: str, filters...) -> Path: ...
```

Use atomic temporary-file replacement for exports and UTF-8 with BOM for CSV.

- [ ] **Step 4: Implement FastAPI routes**

Validate query bounds through FastAPI types; use existing `UserError` handling and existing safe file response patterns.

- [ ] **Step 5: Run focused and complete API tests**

Run: `python -m pytest tests/test_web_api.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/web/app.py src/igea_dgs/web/services.py tests/test_web_api.py
git commit -m "feat: publicar inventario electrico por api"
```

---

### Task 4: Integrar la tabla de inventario en «Cargas de SED»

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/components/LoadInventoryTable.tsx`
- Create: `frontend/src/components/LoadInventoryTable.test.tsx`
- Modify: `frontend/src/components/Modules.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 3 REST shape.
- Produces: tested, paginated `LoadInventoryTable` embedded above the existing template/apply workflow in `LoadsTab`.

- [ ] **Step 1: Install the frontend test harness**

Add Vitest, jsdom, React Testing Library and user-event as dev dependencies; add `test` and `test:run` scripts. Configure Vitest in `vite.config.ts`.

- [ ] **Step 2: Write the failing table tests**

Add tests:

- `shows Name Grid Alimentador SED and electrical columns`
- `sends feeder status search offset and limit to the API`
- `renders NO_IDENTIFICADO AMBIGUO and DESCONECTADO visibly`
- `changes page without loading all rows`
- `keeps the existing load template workflow mounted`

- [ ] **Step 3: Run tests and verify RED**

Run: `npm run test:run -- LoadInventoryTable.test.tsx`

Expected: FAIL because the component/API client does not exist.

- [ ] **Step 4: Add TypeScript contracts and API client**

Define `LoadInventoryRow`, `LoadInventoryPage`, `LoadInventoryFilters`; add `api.electricalInventory(...)` and URL helpers for filtered CSV/JSON.

- [ ] **Step 5: Implement the table and integrate `LoadsTab`**

Place **Inventario de cargas** before the current update workflow. Default page size is 100; debounce text search; retain selected feeder when exactly one feeder is selected and allow `Todos` otherwise.

- [ ] **Step 6: Run component tests, typecheck and build**

Run: `npm run test:run && npm run typecheck && npm run build`

Expected: all tests pass and Vite emits `frontend/dist`.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src
git commit -m "feat: mostrar cargas por alimentador en react"
```

---

### Task 5: Añadir custodia mínima y diagnósticos tipados sin reemplazar la web

**Files:**
- Create: `src/igea_dgs/web/custody.py`
- Modify: `src/igea_dgs/web/workspace.py`
- Modify: `src/igea_dgs/web/app.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/InputsPanel.tsx`
- Create: `tests/test_web_custody.py`

**Interfaces:**
- Consumes: uploaded input paths and existing workspace serialization.
- Produces: immutable per-input `sha256`, `size`, `mtime_ns`, typed diagnostic code and stale-input detection.

- [ ] **Step 1: Write failing custody tests**

Add:

- `test_upload_records_sha256_size_and_original_name`
- `test_changed_input_invalidates_loaded_dataset_and_inventory`
- `test_ambiguous_input_has_stable_error_code`
- `test_reloaded_workspace_revalidates_input_fingerprints`

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_web_custody.py -q`

Expected: FAIL because custody metadata and typed codes are absent.

- [ ] **Step 3: Implement focused custody helpers**

Define `fingerprint(path: Path) -> InputFingerprint` and `verify_fingerprint(...)`. Persist only serializable metadata; do not introduce the divergent projects/revisions frontend.

- [ ] **Step 4: Expose diagnostics without changing successful response shapes**

Error responses add `code` and `context`; existing `detail` remains for compatibility. Show changed/stale input in `InputsPanel`.

- [ ] **Step 5: Run backend and frontend regression**

Run: `python -m pytest tests/test_web_custody.py tests/test_web_api.py -q`

Run: `npm run test:run && npm run build` in `frontend`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/web/custody.py src/igea_dgs/web/workspace.py src/igea_dgs/web/app.py frontend/src tests/test_web_custody.py
git commit -m "feat: custodiar entradas y tipar diagnosticos web"
```

---

### Task 6: Probar equivalencia de todas las ventanas web

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/window-parity.spec.ts`
- Create: `tests/web_fixture_server.py`

**Interfaces:**
- Consumes: complete React/FastAPI interface from Tasks 1–5.
- Produces: executable equivalence gate required before legacy deletion.

- [ ] **Step 1: Add Playwright and write the failing parity scenario**

The scenario must verify visible access to Entradas, Opciones, Alimentadores, Resultados, Cargas de SED including inventory, SED nuevas, Catálogo, Sistema completo, JobBar and Registro.

- [ ] **Step 2: Run the scenario and verify RED**

Run: `npm run test:e2e -- window-parity.spec.ts`

Expected: FAIL until the fixture server and selectors exist.

- [ ] **Step 3: Implement deterministic fixture server and stable accessible selectors**

Use the real FastAPI app with temporary workspace data; mock only the proprietary PowerFactory boundary. Do not mock React components or API client behavior.

- [ ] **Step 4: Run parity and frontend suites**

Run: `npm run test:e2e -- window-parity.spec.ts && npm run test:run && npm run build`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/playwright.config.ts frontend/e2e frontend/src tests/web_fixture_server.py
git commit -m "test: verificar equivalencia de ventanas web"
```

---

### Task 7: Retirar Tkinter y convertir `run_web.bat` en el único lanzador

**Files:**
- Create: `run_web.bat`
- Delete: `run_gui.bat`
- Delete: `run_gui_escritorio.bat`
- Delete: `src/igea_dgs/gui.py`
- Delete: `tests/test_gui_wiring.py`
- Modify: `src/igea_dgs/cli.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_python_version.py`
- Create: `tests/test_no_legacy_gui.py`
- Modify: `README.md`
- Modify: `CODIGO_FUENTE.md`
- Modify: `docs/MANUAL_COMANDOS.md`
- Modify: `docs/POWERFACTORY_ACCEPTANCE.md`

**Interfaces:**
- Consumes: Task 6 passing parity gate and `powerfactory_env.version_key`.
- Produces: `run_web.bat`, `igea-dgs-web`, `python -m igea_dgs.web`, and CLI `web` as the only visual access paths.

- [ ] **Step 1: Write the failing absence and launcher tests**

Add tests that assert:

- no `igea-dgs-gui` project script;
- CLI parser rejects `gui`;
- no tracked `src/igea_dgs/gui.py`, `run_gui.bat`, `run_gui_escritorio.bat` or `tests/test_gui_wiring.py`;
- `run_web.bat` launches `python -m igea_dgs.web` and builds React only when needed;
- documentation contains no operational legacy GUI instruction.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_no_legacy_gui.py tests/test_python_version.py -q`

Expected: FAIL because legacy GUI artifacts still exist.

- [ ] **Step 3: Create `run_web.bat` and update entry points**

Preserve the working environment/bootstrap behavior of current `run_gui.bat`, remove all fallback references to Tkinter, and rename user-facing output to web interface.

- [ ] **Step 4: Retarget the version helper test**

Import `version_key` directly from `igea_dgs.powerfactory_env`; no compatibility alias remains.

- [ ] **Step 5: Delete legacy files and update documentation**

Delete only the four exact tracked legacy files listed above. Rename example output paths from `output/gui` to `output/web` where they describe the web workspace.

- [ ] **Step 6: Run legacy absence, CLI, web and parity gates**

Run: `python -m pytest tests/test_no_legacy_gui.py tests/test_python_version.py tests/test_web_api.py -q`

Run: `npm run test:e2e -- window-parity.spec.ts && npm run test:run && npm run build` in `frontend`

Expected: PASS; `python -m igea_dgs.cli gui` exits as invalid command.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: retirar interfaz tkinter antigua"
```

---

### Task 8: Validación integral y aceptación de alimentadores de referencia

**Files:**
- Create: `tools/verify_reference_feeders.py`
- Create: `tests/test_reference_feeders.py`
- Modify: `docs/POWERFACTORY_ACCEPTANCE.md`
- Create: `docs/VALIDACION_INTEGRACION_WEB_2026-09-27.md`

**Interfaces:**
- Consumes: all prior tasks, reference inputs discoverable under the repository reference folder, and optional PowerFactory 2024.
- Produces: machine-readable and human-readable evidence for NA203, NA205, PE104 and CA101.

- [ ] **Step 1: Write failing fixture-discovery and report-contract tests**

Add:

- `test_reference_verifier_reports_each_required_feeder`
- `test_reference_verifier_distinguishes_missing_fixture_from_failure`
- `test_reference_verifier_checks_name_to_feeder_mapping`
- `test_reference_verifier_checks_grid_scale_trafomix_switches_and_sed`
- `test_reference_verifier_labels_powerfactory_not_run`

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_reference_feeders.py -q`

Expected: FAIL because the verifier does not exist.

- [ ] **Step 3: Implement the verifier**

Define CLI options `--reference-root`, `--output`, `--feeders` and `--powerfactory`. Generate JSON and Markdown with one status per gate: `PASS`, `FAIL`, `SKIP_MISSING_INPUT`, `NOT_RUN_POWERFACTORY`.

- [ ] **Step 4: Run automated reference validation**

Run: `python tools/verify_reference_feeders.py --reference-root referencia --output output/validation --feeders NA203 NA205 PE104 CA101`

Expected: each available feeder is validated; missing inputs are named explicitly and do not masquerade as PASS.

- [ ] **Step 5: Run the complete local quality gate**

Run: `python -m pytest -q`

Run: `npm run test:run && npm run typecheck && npm run build && npm run test:e2e` in `frontend`

Expected: all executable tests PASS; only documented proprietary/missing-fixture skips remain.

- [ ] **Step 6: Run PowerFactory acceptance when available**

Run the existing acceptance tool for each available DGS and verify visible `Alimentador`, assignment counts, topology and load flow. If PowerFactory is unavailable, record `NOT_RUN_POWERFACTORY`; do not claim PASS.

- [ ] **Step 7: Write the validation report and commit**

Document exact commands, versions, counts, hashes, PASS/FAIL/SKIP boundaries and links to generated artifacts.

```bash
git add tools/verify_reference_feeders.py tests/test_reference_feeders.py docs/POWERFACTORY_ACCEPTANCE.md docs/VALIDACION_INTEGRACION_WEB_2026-09-27.md
git commit -m "test: validar integracion web y alimentadores de referencia"
```

---

## Final verification and review

- [ ] Run `git diff --check` and confirm the worktree has no unintended files.
- [ ] Run the complete Python and frontend gates again and save their output in the execution workspace.
- [ ] Generate a whole-branch review package from the recorded merge base to `HEAD`.
- [ ] Request one independent whole-branch review using `superpowers:requesting-code-review`.
- [ ] Fix Critical/Important findings in one RED→GREEN pass; ledger Minor findings without silently expanding scope.
- [ ] Use `superpowers:verification-before-completion` before claiming success.
- [ ] Use `superpowers:finishing-a-development-branch`; do not merge into the user branch without the required branch-finish decision.
