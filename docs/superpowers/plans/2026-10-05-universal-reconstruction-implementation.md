# Universal Reconstruction and Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir cualquier alimentador TXT, MDB o VNR-GIS incompleto mediante una reconstrucción derivada, universal y auditable, y verificarlo hasta PowerFactory sin confundir supuestos con datos originales.

**Architecture:** Los adaptadores producen un modelo canónico y un inventario de ámbito; un motor puro crea una copia reconstruida y un informe de decisiones. Conversión, interfaz y PowerFactory consumen ese informe y mantienen el mismo `source_run_id`, dejando los originales inmutables.

**Tech Stack:** Python 3.12, dataclasses, FastAPI, pytest, React 18, TypeScript, Vite, PowerFactory 2024 API.

**Spec:** `docs/superpowers/specs/2026-10-05-universal-reconstruction-loads-design.md`

## Global Constraints

- TXT, MDB y VNR-GIS nunca comparten archivos primarios.
- Los originales custodiados y sus SHA-256 no se modifican.
- Empresa, periodo, CRS y alimentadores se descubren o seleccionan; no hay valores empresariales fijos.
- Los valores originales tienen prioridad y todo valor derivado registra fuente, regla, confianza y motivo.
- Producir DGS, importar, releer y converger son estados separados.
- Un supuesto permite continuar, pero nunca se etiqueta como dato original ni como solución eléctrica definitiva.
- Toda mutación PowerFactory usa el mismo plan y `source_run_id` verificados en preflight.
- Electro Dunas/IN111 es evidencia de aceptación, no una dependencia funcional.
- El fundamento metodológico se conserva en la especificación: McMorran, Özdamar, Yang et al., Valverde et al. y la tesis doctoral sobre redes con datos limitados.

## Review Focus

- Paquete VNR con varias empresas y periodos: inventariar opciones y exigir una selección, sin mezclar registros.
- Dos candidatos topológicos igualmente válidos: conservar candidatos y marcar supuesto, sin ocultar la ambigüedad.
- Código de conductor desconocido pero con atributos físicos: conservar el código y derivar parámetros en una resolución separada.
- Alimentador que solo converge reduciendo carga: entregar evidencia amarilla/roja, no `CONVERGED_RECONSTRUCTED`.
- DGS histórico con el mismo nombre: rechazarlo antes de escribir si su run/fingerprint difiere del activo.

---

### Task 1: Ámbito universal de empresa y periodo

**Files:**
- Create: `src/igea_dgs/web/source_scope.py`
- Modify: `src/igea_dgs/web/sources/vnr.py`
- Modify: `src/vnr_etl/pipeline.py`
- Modify: `src/igea_dgs/web/workspace.py`
- Modify: `src/igea_dgs/web/app.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/InputsPanel.tsx`
- Test: `tests/test_universal_source_scope.py`

**Interfaces:**
- Produces: `SourceScope(companies, periods, selected_company, selected_period, ambiguous)`; `inspect_source_scope(snapshot) -> SourceScope`; workspace options `source_company` and `source_period`.
- Consumes: `SourceSnapshot` and VNR discovery functions already present.

- [ ] **Step 1: Write the failing tests**

```python
def test_vnr_single_scope_is_detected_without_eldu_default():
    scope = inspect_source_scope(snapshot_for(company='GENERIC_CO', period='2031'))
    assert scope.selected_company == 'GENERIC_CO'
    assert scope.selected_period == '2031'

def test_vnr_multiple_companies_requires_explicit_selection():
    scope = inspect_source_scope(snapshot_for(company=['A', 'B']))
    assert scope.ambiguous is True
    assert scope.selected_company is None
```

Add API/UI contract assertions that `ELDU`, `IN111` and Electro Dunas do not appear as defaults and that a multi-scope package exposes selectors.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_universal_source_scope.py -q`
Expected: FAIL because `source_scope` does not exist and VNR defaults to `ELDU`.

- [ ] **Step 3: Implement source-scope inspection**

Add `inspect_source_scope(snapshot: SourceSnapshot) -> SourceScope`, remove the `ELDU` default from `canonicalize_vnr_package`, and pass explicit workspace selections into `VnrSourceAdapter(company: str | None, period: str | None)`. A single discovered scope is automatic; multiple scopes raise `SOURCE_SCOPE_SELECTION_REQUIRED` only at load time.

- [ ] **Step 4: Implement API and selectors**

Expose `GET /api/workspaces/{wid}/source-scope` and `PUT /api/workspaces/{wid}/source-scope`; render company/period selectors only when required and invalidate the active run when the selection changes.

- [ ] **Step 5: Run focused verification**

Run: `pytest tests/test_universal_source_scope.py tests/test_vnr_web_adapter.py tests/test_vnr_official_web.py -q`
Expected: PASS.

Run: `npm run build` in `frontend`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/web/source_scope.py src/igea_dgs/web/sources/vnr.py src/vnr_etl/pipeline.py src/igea_dgs/web/workspace.py src/igea_dgs/web/app.py frontend/src/types.ts frontend/src/api.ts frontend/src/components/InputsPanel.tsx tests/test_universal_source_scope.py
git commit -m "feat: make source scope universal"
```

### Task 2: Contrato inmutable de reconstrucción

**Files:**
- Create: `src/igea_dgs/reconstruction.py`
- Test: `tests/test_reconstruction_contract.py`

**Interfaces:**
- Produces: `EvidenceLevel`, `ReconstructionPolicy`, `ReconstructionDecision`, `ReconstructionReport`, `ReconstructionResult`; `reconstruct_dataset(dataset, policy, catalogs) -> ReconstructionResult`.
- Consumes: `CymdistDataset`; no workspace or PowerFactory state.

- [ ] **Step 1: Write the failing contract tests**

```python
def test_reconstruction_never_mutates_original_dataset():
    before = fingerprint(dataset)
    result = reconstruct_dataset(dataset, ReconstructionPolicy(), [])
    assert fingerprint(dataset) == before
    assert result.dataset is not dataset

def test_every_changed_field_has_original_and_evidence():
    decision = result.report.decisions[0]
    assert decision.level in {EvidenceLevel.CATALOG_MATCH, EvidenceLevel.ENGINEERING_ASSUMPTION}
    assert decision.original_value != decision.applied_value
    assert decision.rule and decision.reason and 0 <= decision.confidence <= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reconstruction_contract.py -q`
Expected: FAIL with missing module/API.

- [ ] **Step 3: Implement the immutable contract**

Define the dataclasses and JSON serialization. `reconstruct_dataset` deep-copies only the canonical dataset structures and initially returns an unchanged copy; rule registries added by later tasks append decisions through one `record_change(...)` method.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_reconstruction_contract.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/igea_dgs/reconstruction.py tests/test_reconstruction_contract.py
git commit -m "feat: add auditable reconstruction contract"
```

### Task 3: Reconstrucción topológica determinista

**Files:**
- Create: `src/igea_dgs/reconstruction_topology.py`
- Modify: `src/igea_dgs/reconstruction.py`
- Test: `tests/test_reconstruction_topology.py`

**Interfaces:**
- Consumes: `ReconstructionPolicy`, `ReconstructionResult` from Task 2.
- Produces: `repair_missing_nodes(result)`, `repair_discontinuities(result)`, `TopologyCandidate`; decisions with rules `RECOVER_REFERENCED_NODE`, `CREATE_TERMINAL_NODE`, `UNIQUE_COMPATIBLE_CONNECTION`, `RANKED_AMBIGUOUS_CONNECTION`.

- [ ] **Step 1: Write failing generic-network tests**

Cover: referenced node omitted from `NODE`; a terminal derived from section coordinates; unique same-kV connection; two equidistant candidates; a candidate at another voltage; and no cross-company connection.

```python
assert repaired.sections['S1']['ToNodeID'] == 'N_DERIVED_S1_TO'
assert report.decisions[-1].level is EvidenceLevel.ENGINEERING_ASSUMPTION
assert report.decisions[-1].candidates == ('N2', 'N3')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reconstruction_topology.py -q`
Expected: FAIL because topology repair functions do not exist.

- [ ] **Step 3: Implement node and discontinuity repair**

Use voltage, phase, coordinates, graph degree and feeder/company scope. Toda conexión topológica inferida usa `ENGINEERING_ASSUMPTION`; una coincidencia única recibe mayor confianza y una selección entre varios candidatos conserva el ranking completo. Nunca cruza límites de tensión o ámbito.

- [ ] **Step 4: Integrate existing bridge and island rules**

Call existing `fundir_puentes` only after dataset reconstruction and preserve its transformations in the report. Do not silently de-energize an island with load at this stage.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_reconstruction_topology.py tests/test_topology_islands.py tests/test_puentes.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/reconstruction.py src/igea_dgs/reconstruction_topology.py tests/test_reconstruction_topology.py
git commit -m "feat: reconstruct incomplete feeder topology"
```

### Task 4: Resolución universal de equipos y parámetros

**Files:**
- Create: `src/igea_dgs/catalog_resolution.py`
- Modify: `src/igea_dgs/reconstruction.py`
- Modify: `src/igea_dgs/reglas.py`
- Test: `tests/test_catalog_resolution.py`

**Interfaces:**
- Consumes: source equipment tables, manufacturer/global catalog descriptors and `ReconstructionPolicy`.
- Produces: `CatalogSource`, `EquipmentQuery`, `ResolvedParameters`; `resolve_equipment(query, catalogs, policy) -> ResolvedParameters`; rules `EXACT_SOURCE`, `EXACT_MANUFACTURER`, `EXACT_GLOBAL`, `COMPATIBLE_ATTRIBUTES`, `PHYSICAL_DERIVATION`, `PROVISIONAL_PROFILE`.

- [ ] **Step 1: Write failing hierarchy tests**

Assert exact source beats manufacturer/global; manufacturer beats global; compatibility requires class/material/section/voltage/aerial agreement; physical derivation preserves the original code; and an ambiguous tie falls to a provisional profile with both candidates recorded.

```python
assert resolved.original_code == 'USER-CODE-17'
assert resolved.parameters['R1'] == pytest.approx(expected_r1)
assert resolved.rule == 'PHYSICAL_DERIVATION'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_catalog_resolution.py -q`
Expected: FAIL with missing resolver.

- [ ] **Step 3: Implement catalog descriptors and hierarchy**

Every catalog descriptor includes name, kind, version, manufacturer, path/URL and SHA-256. Never rename `LineCableID`; store adopted parameters and provenance separately before materializing equipment rows.

- [ ] **Step 4: Integrate with dataset preparation**

Replace implicit nearest/`DEFAULT` use in the reconstructed path with `resolve_equipment`; retain the literal `DEFAULT` marker only for bridge processing. Existing literal conversion remains available for regression comparison.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_catalog_resolution.py tests/test_type_resolution.py tests/test_reglas.py tests/test_puentes.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/catalog_resolution.py src/igea_dgs/reconstruction.py src/igea_dgs/reglas.py tests/test_catalog_resolution.py
git commit -m "feat: resolve missing equipment with provenance"
```

### Task 5: Integración de diagnóstico, reconstrucción y conversión

**Files:**
- Create: `src/igea_dgs/web/reconstruction_service.py`
- Modify: `src/igea_dgs/web/readiness.py`
- Modify: `src/igea_dgs/web/services.py`
- Modify: `src/igea_dgs/web/app.py`
- Modify: `src/igea_dgs/web/workspace.py`
- Test: `tests/test_web_reconstruction.py`

**Interfaces:**
- Consumes: `reconstruct_dataset` and source-run custody.
- Produces: `diagnose_selection(ws, feeders)`, `reconstruct_selection(ws, feeders, policy)`, endpoints `POST /diagnose` and `POST /reconstruct`; persisted `reconstruction_report.json` per run.

- [ ] **Step 1: Write failing service/API tests**

Cover one/many/all, missing nodes, unresolved conductor, old-run rejection, atomic selection, original hash stability and the Review Focus case of equally ranked candidates.

```python
assert response.status_code == 200
assert row['readiness'] == 'READY_RECONSTRUCTED'
assert manifest['source_sha256'] == original_sha
assert manifest['assumptions'] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_reconstruction.py tests/test_readiness.py -q`
Expected: FAIL because incomplete feeders are blocked and endpoints are absent.

- [ ] **Step 3: Implement reconstruction service**

Diagnostics are read-only. Reconstruction writes derived artifacts beneath the active run and updates readiness to `READY_ORIGINAL`, `READY_RECONSTRUCTED` or `CONVERTED_WITH_ASSUMPTIONS`; only identity/scope/path safety errors block execution.

- [ ] **Step 4: Route conversion through the derived dataset**

`services.convert` and group conversion consume the active reconstruction result for the same run; stamp DGS sidecars and batch manifests with report hash, counts and evidence levels.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_web_reconstruction.py tests/test_readiness.py tests/test_source_adapters.py tests/test_web_api.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/web/reconstruction_service.py src/igea_dgs/web/readiness.py src/igea_dgs/web/services.py src/igea_dgs/web/app.py src/igea_dgs/web/workspace.py tests/test_web_reconstruction.py
git commit -m "feat: reconstruct incomplete feeders before conversion"
```

### Task 6: Interfaz de diagnóstico y reconstrucción

**Files:**
- Create: `frontend/src/components/ReconstructionPanel.tsx`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/FeedersPanel.tsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_web_reconstruction_ui_contract.py`

**Interfaces:**
- Consumes: Task 5 endpoints and readiness states.
- Produces: buttons `Diagnosticar`, `Reconstruir y convertir`, `Ver cambios`; table fields `source_quality`, `repair_count`, `assumption_count`, `catalog_sources`, `convergence_state`.

- [ ] **Step 1: Write failing API/UI contract tests**

Assert generic labels, no `ELDU`/IN111 defaults, selectable incomplete feeders, semantic status tones, report links and disabled mutation only for active-job or stale-run conditions.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_reconstruction_ui_contract.py -q`
Expected: FAIL on absent contract fields/components.

- [ ] **Step 3: Implement TypeScript contracts and panel**

Render original/catalog/assumption decisions with before/after values and filters. Use green for original convergence, blue for catalog reconstruction, yellow for assumptions and red only for `NEEDS_OPERATOR_REVIEW`.

- [ ] **Step 4: Update feeder actions**

Allow selecting every inventoried feeder. A conversion click diagnoses/reconstructs first when required and displays the plan before mutation; `Convertir todos` follows the same flow.

- [ ] **Step 5: Verify frontend and API**

Run: `pytest tests/test_web_reconstruction_ui_contract.py tests/test_web_api.py -q`
Expected: PASS.

Run: `npm run build` in `frontend`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ReconstructionPanel.tsx frontend/src/types.ts frontend/src/api.ts frontend/src/components/FeedersPanel.tsx frontend/src/styles.css tests/test_web_reconstruction_ui_contract.py
git commit -m "feat: expose reconstruction evidence in web ui"
```

### Task 7: Convergencia PowerFactory clasificada y reversible

**Files:**
- Modify: `tools/powerfactory_acceptance.py`
- Modify: `src/igea_dgs/powerfactory_metadata.py`
- Modify: `src/igea_dgs/web/services.py`
- Test: `tests/test_reconstruction_powerfactory.py`

**Interfaces:**
- Consumes: reconstruction report hash and DGS sidecar.
- Produces: `classify_convergence(report) -> str`; PowerFactory evidence fields `reconstruction`, `attempts`, `effective_reread`, `load_intervention`, `rollback`.

- [ ] **Step 1: Write failing acceptance tests**

Cover original convergence, catalog reconstruction, assumption convergence, convergence only after load reduction, stale DGS, reread failure and rollback. The load-reduction case must assert `NEEDS_OPERATOR_REVIEW`, not a converged state.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reconstruction_powerfactory.py tests/test_powerfactory_gate.py -q`
Expected: FAIL on missing reconstruction classification/evidence.

- [ ] **Step 3: Bind reconstruction evidence before mutation**

Verify report hash, source identity and dry-run plan. Record every correction attempt with before/after values; keep existing isolated-project behavior and value-level rollback.

- [ ] **Step 4: Implement final-state classification**

Require source verification, feeder reread and valid `ComLdf`. Any shed/scaled/disconnected load prevents green/blue convergence classification even if `ComLdf` returns success.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_reconstruction_powerfactory.py tests/test_powerfactory_gate.py tests/test_powerfactory_source_run.py tests/test_powerfactory_feeder_metadata.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/powerfactory_acceptance.py src/igea_dgs/powerfactory_metadata.py src/igea_dgs/web/services.py tests/test_reconstruction_powerfactory.py
git commit -m "feat: classify reconstructed powerfactory convergence"
```

### Task 8: Regresión, evidencia universal y aceptación real

**Files:**
- Modify: `tools/accept_three_sources.py`
- Create: `tests/test_universal_reconstruction_acceptance.py`
- Modify: `docs/runbooks/three-source-production-acceptance.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: acceptance summary with original/reconstructed hashes, decision counts, convergence class and explicit environmental blockers.

- [ ] **Step 1: Write failing end-to-end tests**

Use generic company `UTILITY_X`, feeders `F-A`/`F-B`, non-Peruvian CRS, missing node and missing conductor parameters. Assert both feeders produce DGS, originals remain unchanged and assumptions are visible.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_universal_reconstruction_acceptance.py -q`
Expected: FAIL until all evidence reaches the summary.

- [ ] **Step 3: Extend runner and documentation**

Add reconstruction policy arguments and report paths without changing source isolation. Update the runbook with evidence classes and the scientific sources from the spec.

- [ ] **Step 4: Run full automated verification**

Run: `pytest --basetemp=.pytest_tmp\universal_reconstruction -q`
Expected: zero failures; record pass/skip/warning totals.

Run: `npm run build` in `frontend`
Expected: exit 0.

- [ ] **Step 5: Run real controlled acceptance**

Execute current TXT and MDB originals independently for IN111 through reconstruction, DGS, PowerFactory reread and `ComLdf`. Run VNR real only if a complete package exists; otherwise retain the explicit external blocker. Compare original hashes before/after.

- [ ] **Step 6: Reconcile every spec section**

Create a checklist mapping Sections 2–14 to tests or real artifacts. State any remaining environmental blocker plainly.

- [ ] **Step 7: Commit**

```bash
git add tools/accept_three_sources.py tests/test_universal_reconstruction_acceptance.py docs/runbooks/three-source-production-acceptance.md README.md
git commit -m "test: verify universal reconstruction workflow"
```
