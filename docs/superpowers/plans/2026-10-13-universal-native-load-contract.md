# Universal Native Load Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluar cada fuente TXT, MDB o VNR-GIS con un único contrato y llevar bancos, cargas, periodo y procedencia hasta una calibración y estudios verificados en PowerFactory nativo.

**Architecture:** Los adaptadores conservan únicamente la responsabilidad de leer su formato y entregan un `CymdistDataset`; `source_contract.py` audita ese modelo con lógica común. El mismo modelo alimenta DGS/sidecar, un binding custodia el proyecto importado y todos los casos de uso nativos exigen ese binding antes de modificar o estudiar la red.

**Tech Stack:** Python 3.12, dataclasses, pytest, FastAPI, React 18, TypeScript, Vite, DIgSILENT PowerFactory 2024 API.

**Spec:** `docs/superpowers/specs/2026-10-13-universal-native-load-contract-design.md`

## Global Constraints

- TXT, MDB y VNR-GIS solo difieren dentro de sus adaptadores; no se duplica lógica de bancos, cargas, cuadre o aceptación.
- No se codifican alimentadores, empresas, rutas ni cantidades de equipos concretos.
- Cada artefacto conserva `source_run_id`, `source_mode`, `source_fingerprint` y SHA-256.
- Ningún banco recibe una potencia predeterminada o inferida: capacidad, fases y escalones se conservan exactamente desde la fuente.
- El mes del libro de clientes debe coincidir con el mes de la máxima cuando se usan clientes fijos.
- `Pot` es kW; `Q = Pot × ERI / EA`; el fallback usa el FP del objetivo.
- El criterio de cuadre es kW; toda diferencia de kVAR se informa y no bloquea.
- Éxito de comando, guardado, reapertura, relectura, convergencia y cumplimiento físico son evidencias distintas.
- Los estudios aceptados se ejecutan en PowerFactory nativo; fakes y pandapower son pruebas auxiliares.
- Se preservan todos los cambios ajenos presentes en el worktree.

## Review Focus

- Bancos con 150, 300 o 450 kVAR de origen: deben conservar exactamente su valor; un banco sin capacidad no recibe ninguna.
- Libro de clientes sin periodo demostrable: no debe fijar cargas silenciosamente.
- Proyecto PowerFactory histórico con el mismo nombre: debe bloquearse por binding/run o inventario nativo distinto.
- `p:alimentador` leído como lista y wrapper duplicado: debe producir una sola carga.
- kW dentro de tolerancia y kVAR muy distinto por bancos: debe quedar `AVISO_KVAR`, no bloquear ni ocultar la diferencia.

---

### Task 1: Contrato canónico evaluado en cada carga

**Files:**
- Create: `src/igea_dgs/source_contract.py`
- Modify: `src/igea_dgs/sources/base.py`
- Modify: `src/igea_dgs/web/services.py:131`
- Modify: `src/igea_dgs/web/readiness.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/FeedersPanel.tsx`
- Test: `tests/test_source_contract.py`
- Test: `tests/test_source_adapters.py`
- Test: `tests/test_source_contract_front.py`

**Interfaces:**
- Consumes: `CymdistDataset`, provenance de `SourceLoadResult` y readiness opcional del adaptador.
- Produces: `SourceIssue`, `FeederSourceAudit`, `UniversalSourceAudit`, `audit_source(dataset, provenance) -> UniversalSourceAudit`; `SourceLoadResult.audit`.

- [ ] **Step 1: Write failing source-contract tests**
  Add `test_same_audit_contract_for_txt_mdb_vnr`, `test_missing_or_ambiguous_feeder_is_reported_once`, `test_source_audit_keeps_mode_run_and_fingerprint`, and `test_common_contract_has_no_mode_branch`. Assert identical keys and status semantics for three datasets with the same electrical content and reject source-mode branching outside `src/igea_dgs/sources/`.
- [ ] **Step 2: Run tests to verify failure**
  Run: `pytest tests/test_source_contract.py tests/test_source_adapters.py -q`
  Expected: FAIL because `audit_source` and `SourceLoadResult.audit` do not exist.
- [ ] **Step 3: Implement the common audit**
  Define `audit_source(dataset: CymdistDataset, provenance: Mapping[str, Any]) -> UniversalSourceAudit`. Traverse the dataset once, index ownership by `NetworkID`, and return deterministic sorted rows. Do not inspect `source_mode` to choose an algorithm.
- [ ] **Step 4: Integrate it into `load_dataset`**
  Execute `audit_source` immediately after adapter loading; stamp `inventory['universal_audit']`, merge per-feeder blockers into readiness, and persist the audit JSON under the active run output.
- [ ] **Step 5: Expose the audit without recalculating it in React**
  Extend the API types and render run, source mode, object counts and blocker/warning counts in `FeedersPanel`; add `test_source_contract_front_uses_server_audit`.
- [ ] **Step 6: Run focused tests**
  Run: `pytest tests/test_source_contract.py tests/test_source_adapters.py tests/test_readiness.py tests/test_source_contract_front.py -q`
  Expected: PASS.
- [ ] **Step 7: Commit**
  Commit: `feat: audit every source through one canonical contract`

### Task 2: Bancos universales en dataset y modelo eléctrico

**Files:**
- Modify: `src/igea_dgs/dataset.py`
- Modify: `src/igea_dgs/access.py`
- Modify: `src/igea_dgs/model.py`
- Modify: `src/igea_dgs/combine.py`
- Modify: `src/igea_dgs/source_contract.py`
- Modify: `src/vnr_etl/application/cymdist_bridge.py`
- Test: `tests/test_capacitor_canonical.py`
- Test: `tests/test_vnr_cymdist_bridge.py`
- Test: `tests/test_access.py`

**Interfaces:**
- Consumes: filas de condensador TXT/MDB y `vnr_etl.models.Capacitor`, siempre con valores de la fuente.
- Produces: `CymdistDataset.capacitor_settings`; `CapacitorBank`; `capacitor_from_source(row) -> CapacitorBank`; `FeederModel.capacitors`.

- [ ] **Step 1: Write failing normalization tests**
  Add mono 150 kVAR, tri 300 kVAR, banco 450 kVAR, multi-step total, missing capacity, missing node, and ambiguous feeder cases. Assert exact source value, phases, per-step and total power; missing capacity must emit `MISSING_CAPACITOR_CAPACITY` and must not synthesize a number.
- [ ] **Step 2: Write failing three-adapter parity tests**
  Build equivalent TXT, mocked MDB rows and VNR canonical fixtures; assert all reach the same `CapacitorBank` fields without mode branches below the adapters.
- [ ] **Step 3: Run tests to verify failure**
  Run: `pytest tests/test_capacitor_canonical.py tests/test_vnr_cymdist_bridge.py tests/test_access.py -q`
  Expected: FAIL because the common dataset/model drops capacitors.
- [ ] **Step 4: Implement dataset and adapter mappings**
  Add `capacitor_settings` with an empty default for compatibility. Parse source fields losslessly; VNR must retain all `CanonicalModel.capacitors`. Resolve owner by explicit feeder first and by a unique connected node second.
- [ ] **Step 5: Implement model normalization**
  Define `CapacitorBank` and `capacitor_from_source`. Preserve every positive source capacity verbatim; retain an incomplete inventory record and issue when capacity is absent or invalid. Do not consult a profile or catalogue to invent bank power.
- [ ] **Step 6: Merge banks in combined models**
  Preserve feeder, network, node and stable identity when `build_combined` joins feeders.
- [ ] **Step 7: Run focused tests**
  Run: `pytest tests/test_capacitor_canonical.py tests/test_vnr_cymdist_bridge.py tests/test_access.py tests/test_combine.py -q`
  Expected: PASS.
- [ ] **Step 8: Commit**
  Commit: `feat: preserve capacitor banks in the universal model`

### Task 3: Exportar y releer `ElmShnt` con trazabilidad

**Files:**
- Modify: `src/igea_dgs/dgs.py`
- Modify: `src/igea_dgs/batch.py`
- Modify: `src/igea_dgs/feeder_metadata.py`
- Modify: `src/igea_dgs/powerfactory_metadata.py`
- Modify: `src/igea_dgs/geography.py`
- Modify: `tools/powerfactory_acceptance.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/FeedersPanel.tsx`
- Modify: `tests/fake_pf.py`
- Test: `tests/test_dgs_capacitors.py`
- Test: `tests/test_feeder_metadata.py`
- Test: `tests/test_powerfactory_feeder_metadata.py`
- Test: `tests/test_capacitor_inventory_front.py`

**Interfaces:**
- Consumes: `FeederModel.capacitors` from Task 2.
- Produces: `DgsManifest.shunt_fids`; `FeederAssignment` rows for `ElmShnt`; `reread_capacitors(app, expected) -> dict[str, Any]`.

- [ ] **Step 1: Write failing DGS and sidecar tests**
  Assert one `ElmShnt` and cubicle per complete source bank, exact source `ctech/qcapn/ncapx/ncapa/ushnm/outserv`, stable FID, and `p:alimentador` assignment metadata. Assert an incomplete bank creates no `ElmShnt` and remains visible as `MISSING_CAPACITOR_CAPACITY` in the manifest.
- [ ] **Step 2: Run tests to verify failure**
  Run: `pytest tests/test_dgs_capacitors.py tests/test_feeder_metadata.py tests/test_powerfactory_feeder_metadata.py -q`
  Expected: FAIL because `DgsManifest` and metadata omit shunts.
- [ ] **Step 3: Extend DGS and metadata**
  Export banks from the common model only. Add `ElmShnt` to metadata target classes and identify it by name, terminal and parent substation/grid context.
- [ ] **Step 4: Add native reread and rollback evidence**
  Compare all required shunt attributes and connection after import/reopen. A mismatch returns `BLOQUEADO_PERSISTENCIA` and records rollback status.
- [ ] **Step 5: Render planned and reread bank values**
  Show per-feeder bank count, phase technology, Mvar per step, active/maximum steps and total native Mvar from server evidence; add `test_bank_panel_does_not_recalculate_power`.
- [ ] **Step 6: Run focused tests**
  Run: `pytest tests/test_dgs_capacitors.py tests/test_feeder_metadata.py tests/test_powerfactory_feeder_metadata.py tests/test_powerfactory_gate.py tests/test_capacitor_inventory_front.py -q`
  Expected: PASS.
- [ ] **Step 7: Commit**
  Commit: `feat: export and verify traced powerfactory shunts`

### Task 4: Binding verificable del proyecto PowerFactory

**Files:**
- Create: `src/igea_dgs/powerfactory_binding.py`
- Modify: `src/igea_dgs/web/workspace.py`
- Modify: `src/igea_dgs/web/services.py:557-821`
- Modify: `tools/powerfactory_acceptance.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/CargasTab.tsx`
- Test: `tests/test_powerfactory_binding.py`
- Modify: `tests/test_powerfactory_source_run.py`
- Test: `tests/test_powerfactory_binding_front.py`

**Interfaces:**
- Consumes: evidencia fuente, DGS/sidecar, proyecto importado y objetos nativos.
- Produces: `PowerFactoryProjectBinding`; `native_inventory_sha256(app, feeders) -> str`; `record_project_binding(ws, binding) -> None`; `require_project_binding(ws, project, feeders) -> PowerFactoryProjectBinding`.

- [ ] **Step 1: Write failing binding tests**
  Cover exact run accepted, historical same-name project rejected, changed native topology rejected, changed P/Q allowed, and wrapper identity stability.
- [ ] **Step 2: Run tests to verify failure**
  Run: `pytest tests/test_powerfactory_binding.py tests/test_powerfactory_source_run.py -q`
  Expected: FAIL because workspace stores only project names.
- [ ] **Step 3: Implement stable native inventory hashing**
  Hash sorted class, `GetFullName`, connection, feeder labels and immutable equipment identity; exclude operational P/Q and result attributes.
- [ ] **Step 4: Persist binding after successful acceptance**
  Record project/folder, hashes, feeders, run identity, native hash and reread evidence atomically in the workspace.
- [ ] **Step 5: Enforce binding before native actions**
  `require_project_binding` must run before creating any plan or launching any PowerFactory mutation/study.
- [ ] **Step 6: Show binding identity in the native workflow**
  Render project, run, source fingerprint prefix, feeder set and last native reread in `CargasTab`; an unbound or stale project disables native actions with the server reason.
- [ ] **Step 7: Run focused tests**
  Run: `pytest tests/test_powerfactory_binding.py tests/test_powerfactory_source_run.py tests/test_carpeta_pf.py tests/test_powerfactory_binding_front.py -q`
  Expected: PASS.
- [ ] **Step 8: Commit**
  Commit: `feat: bind native projects to their active source run`

### Task 5: Periodo demostrado y cargas importantes fijas

**Files:**
- Modify: `src/igea_dgs/demanda_medida.py`
- Modify: `src/igea_dgs/ajuste_cabecera.py`
- Modify: `src/igea_dgs/web/services.py:1540-1715`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/AjusteCabecera.tsx`
- Test: `tests/test_demanda_medida.py`
- Test: `tests/test_ajuste_cabecera.py`
- Test: `tests/test_ajuste_cabecera_web.py`

**Interfaces:**
- Consumes: fecha de `Objetivo`, catálogo/libro activo de clientes y binding de Task 4.
- Produces: `periodo_de_fecha(value) -> str`; `periodo_clientes_activo(ws) -> ClientPeriodEvidence`; plan `igea-dgs-ajuste-cabecera-v2` con `source`, `project_binding`, `periodo` y evidencia de clientes.

- [ ] **Step 1: Write failing period tests**
  Add coincident month accepted, different month blocked, unknown month blocked, and no-client-book allowed with explicit warning.
- [ ] **Step 2: Write failing P/Q/FP tests**
  Assert `Pot=100`, `EA=400`, `ERI=120` gives `P=100`, `Q=30` and the corresponding FP; assert fallback names the client when EA/ERI is absent.
- [ ] **Step 3: Run tests to verify failure**
  Run: `pytest tests/test_demanda_medida.py tests/test_ajuste_cabecera.py tests/test_ajuste_cabecera_web.py -q`
  Expected: FAIL because the plan does not bind the client period or native project.
- [ ] **Step 4: Implement period evidence and v2 plan**
  Resolve the active client book fingerprint, file/sheet and period once. Call `require_project_binding`; embed immutable evidence in every feeder plan.
- [ ] **Step 5: Keep the load formula source-independent**
  Continue using `fijas_de` for all modes. Rename user messages from “TXT o MDB” to “fuente canónica activa” and fetch backup kVA from the active dataset only.
- [ ] **Step 6: Render evidence in the frontend**
  Show maximum month, client-book month, fixed/scaled counts, P/Q/FP derivation warnings and binding status.
- [ ] **Step 7: Run focused tests and frontend build**
  Run: `pytest tests/test_demanda_medida.py tests/test_ajuste_cabecera.py tests/test_ajuste_cabecera_web.py -q`
  Expected: PASS.
  Run: `npm run build` in `frontend`
  Expected: exit 0.
- [ ] **Step 8: Commit**
  Commit: `feat: bind important loads to the feeder peak month`

### Task 6: Cuadre universal a kW y diferencia kVAR no bloqueante

**Files:**
- Modify: `src/igea_dgs/ajuste_cabecera.py`
- Modify: `tools/ajuste_cabecera_pf.py`
- Modify: `specs/006-ajuste-a-la-maxima-de-cabecera/spec.md`
- Modify: `frontend/src/components/AjusteCabecera.tsx`
- Modify: `frontend/src/types.ts`
- Test: `tests/test_ajuste_cabecera.py`
- Test: `tests/test_ajuste_cabecera_guion.py`
- Test: `tests/test_ajuste_cabecera_web.py`

**Interfaces:**
- Consumes: plan v2 and project binding from Task 5.
- Produces: `cuadrado_kw(medida, objetivo, tolerancia) -> bool`; `kvar_difference(medida, objetivo, tolerancia) -> dict`; report status `OK` or `AVISO_KVAR`.

- [ ] **Step 1: Write failing acceptance tests**
  Cover Q above/below target, zero-Q target, capacitor-driven Q, kW outside tolerance, and nonconverged flow. Assert only valid kW can produce `OK/AVISO_KVAR`.
- [ ] **Step 2: Write failing native-population tests**
  Assert topology/tag union counts, list-valued tags, contradictory label exclusion and duplicate-wrapper collapse by `GetFullName`.
- [ ] **Step 3: Run tests to verify failure**
  Run: `pytest tests/test_ajuste_cabecera.py tests/test_ajuste_cabecera_guion.py tests/test_ajuste_cabecera_web.py -q`
  Expected: FAIL because Q still conditionally blocks and the report lacks universal audit fields.
- [ ] **Step 4: Implement kW-only acceptance**
  Replace the conditional Q gate with `cuadrado_kw`. Keep initial Q allocation, iterate the active scaling factor for P/losses, and always retain the native Q result.
- [ ] **Step 5: Emit the complete nonblocking Q report**
  Add objective, native value, signed/relative difference, tolerance and `bloquea=false`; choose `AVISO_KVAR` only when the informational tolerance is exceeded.
- [ ] **Step 6: Add native reread before and after flow**
  Verify P/Q/FP, state and scaling flag for every changed SED; include population source counts and shunt reread from Task 3.
- [ ] **Step 7: Run focused tests and frontend build**
  Run: `pytest tests/test_ajuste_cabecera.py tests/test_ajuste_cabecera_guion.py tests/test_ajuste_cabecera_web.py -q`
  Expected: PASS.
  Run: `npm run build` in `frontend`
  Expected: exit 0.
- [ ] **Step 8: Commit**
  Commit: `feat: accept native kw balance with reported kvar difference`

### Task 7: Aplicar la misma puerta a todos los casos de uso nativos

**Files:**
- Modify: `src/igea_dgs/web/services.py:1192-2290`
- Modify: `src/igea_dgs/cargas_pf.py`
- Modify: `src/igea_dgs/estudios_pf.py`
- Modify: `src/igea_dgs/obras_pf.py`
- Modify: `src/igea_dgs/transferencia_pf.py`
- Modify: `tools/cargas_pf.py`
- Modify: `tools/estudios_pf.py`
- Modify: `tools/obras_pf.py`
- Modify: `tools/transferencia_pf.py`
- Test: `tests/test_native_project_gate.py`
- Modify: `tests/test_estudios_pf_guion.py`

**Interfaces:**
- Consumes: `require_project_binding` from Task 4 and report statuses from Task 6.
- Produces: `native_action_context(ws, project, feeders, action) -> dict` shared by cargas, verificación, obras, estudios and transferencia.

- [ ] **Step 1: Write failing cross-action gate tests**
  Parameterize `cargas_plan`, `ajuste_plan`, `pf_verificar`, `obras_*`, `estudios_plan` and `transferencia_ejecutar`; assert stale/unbound projects are rejected before subprocess launch.
- [ ] **Step 2: Write failing status tests**
  Assert no generic `FAIL` status is emitted: data/persistence/convergence/physical/not-applicable states remain distinct, and Q warnings do not disable studies.
- [ ] **Step 3: Run tests to verify failure**
  Run: `pytest tests/test_native_project_gate.py tests/test_estudios_pf_guion.py -q`
  Expected: FAIL because native actions validate projects independently or not at all.
- [ ] **Step 4: Implement one shared context gate**
  Build the context once in `services.py`, embed it in plans, and verify it again inside each native tool before mutation. Remove duplicated source/project checks replaced by this interface.
- [ ] **Step 5: Normalize result statuses**
  Map command and physical outcomes to the seven statuses in the spec without changing the underlying numerical evidence.
- [ ] **Step 6: Run focused tests**
  Run: `pytest tests/test_native_project_gate.py tests/test_estudios_pf_guion.py tests/test_obras_pf_guion.py tests/test_cargas_pf_guion.py -q`
  Expected: PASS.
- [ ] **Step 7: Commit**
  Commit: `refactor: gate every native study through one project contract`

### Task 8: Aceptación universal, documentación y verificación real

**Files:**
- Modify: `tools/accept_three_sources.py`
- Create: `docs/runbooks/universal-native-load-acceptance.md`
- Modify: `CODIGO_FUENTE.md`
- Modify: `docs/MANUAL_COMANDOS.md`
- Test: `tests/test_three_source_native_load_acceptance.py`
- Modify: `tests/test_three_source_acceptance.py`

**Interfaces:**
- Consumes: source audit, DGS/shunt metadata, project binding and adjustment report from Tasks 1-7.
- Produces: acceptance schema `igea-dgs-three-source-native-load-v1` and a per-mode evidence bundle.

- [ ] **Step 1: Write failing acceptance-schema tests**
  Require source audit hash, capacitor counts/power, metadata assignment counts, project binding, client period evidence, fixed/scaled counts, native P/Q, Q warning, `ComLdf` validity and physical violations.
- [ ] **Step 2: Run tests to verify failure**
  Run: `pytest tests/test_three_source_native_load_acceptance.py tests/test_three_source_acceptance.py -q`
  Expected: FAIL because the runner stops at DGS/initial PowerFactory acceptance.
- [ ] **Step 3: Extend the runner without source-specific algorithms**
  Keep separate workspaces and runs but invoke the same public services for load, convert, import, calibrate and study. Missing official input remains explicit and is never substituted.
- [ ] **Step 4: Document operator evidence**
  Describe how to distinguish command exit, save, reopen/reread, converged flow and physical acceptance; document `AVISO_KVAR` as nonblocking.
- [ ] **Step 5: Run complete automated verification**
  Run: `pytest --basetemp=.pytest_tmp -q`
  Expected: zero failures.
  Run: `npm run build` in `frontend`
  Expected: exit 0.
- [ ] **Step 6: Run real PowerFactory acceptance**
  Use each official TXT/MDB/VNR source available. For every executed mode, save DGS/sidecar hashes, project binding, native bank/load reread, `ComLdf`, P/Q head measurement, voltage minimum and maximum loading. Do not declare an unavailable mode accepted.
- [ ] **Step 7: Reconcile against the spec**
  Check every criterion in Sections 14-15 and list environmental gaps separately from code/test failures.
- [ ] **Step 8: Commit**
  Commit: `test: prove universal native load contract across sources`
