# Digital Twin Episode Buffer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capturar, validar, clasificar y consultar episodios auditables de todo trabajo fuente–PowerFactory, incluido el caso dorado IN111–TA225, para formar el búfer local que alimentará los planes posteriores de generación de escenarios y entrenamiento PINN.

**Architecture:** Un paquete puro `igea_dgs.digital_twin` define el contrato, la clasificación y un almacén inmutable direccionado por contenido; un exportador nativo relee PowerFactory en una sesión nueva y produce el estado eléctrico por elemento. La capa web registra cada resultado nativo sin convertir un fallo de captura en una mutación adicional: un episodio incompleto va a cuarentena y nunca al conjunto entrenable.

**Tech Stack:** Python 3.12, dataclasses, JSON Schema, `sqlite3`, SHA-256, FastAPI, pytest, PowerFactory 2024 API; sin PyTorch en este plan.

**Spec:** `specs/024-pinn-gemelo-digital/spec.md`

## Global Constraints

- DIgSILENT PowerFactory sigue siendo la referencia; este plan no implementa inferencia ni escribe recomendaciones.
- El núcleo debe funcionar sin PyTorch; la dependencia opcional `ml` se añade en el plan de entrenamiento.
- Todo episodio conserva `source_run_id`, `source_mode`, `source_fingerprint`, proyecto, carpeta, alimentadores y huella nativa.
- Sin reapertura y relectura no existe episodio `accepted`.
- `converged_with_violations` es distinto de `accepted`; convergencia no implica aceptación operativa.
- Los intentos revertidos se guardan como `rejected` y nunca como objetivo positivo.
- Los datos y modelos permanecen locales; no hay llamadas a servicios externos en tiempo de ejecución.
- El búfer es inmutable e idempotente por SHA-256; SQLite es un índice reconstruible, no la única evidencia.
- Una captura fallida bloquea el entrenamiento del episodio, pero no intenta deshacer ni repetir una acción PowerFactory ya finalizada.
- Las pruebas unitarias no requieren licencia; la aceptación nativa se ejecuta aparte y reporta su alcance.
- Ruff se ejecuta sobre todo archivo funcional y de prueba modificado en este plan.
- No ejecutar `git commit` salvo autorización explícita del usuario; los pasos de commit son checkpoints opcionales.

## Review Focus

- Resultado convergente con subtensión: clasificar `converged_with_violations`, conservar los límites y excluirlo del objetivo positivo; Task 3 lo fija con prueba.
- Misma fuente y resultado con orden distinto de diccionarios: producir el mismo `episode_id` y una sola copia; Task 1 y Task 2 lo fijan.
- Acción aplicada pero snapshot posterior incompleto o API no disponible: conservar el borrador en `quarantine` sin cambiar PowerFactory; Task 3 y Task 5 lo fijan.
- Proyecto con dos alimentadores y un enlace manual: conservar orientación, frontera, variaciones activas y huella GPS sin unir fuentes; Task 4 y Task 7 lo fijan.
- Índice SQLite borrado o corrupto con objetos intactos: reconstruirlo desde manifiestos y recuperar las mismas consultas; Task 2 lo fija.

---

### Task 1: Contrato tipado y esquema del episodio

**Files:**
- Create: `src/igea_dgs/digital_twin/__init__.py`
- Create: `src/igea_dgs/digital_twin/episode.py`
- Create: `src/igea_dgs/schemas/digital_twin_episode_v1.schema.json`
- Test: `tests/test_digital_twin_episode.py`

**Interfaces:**
- Produces: `EpisodeClass`, `ArtifactRef`, `EpisodeManifest`, `canonical_payload(payload) -> dict[str, Any]`, `episode_sha256(payload) -> str`, `parse_episode(payload) -> EpisodeManifest`.
- Consumes: solo biblioteca estándar; `NATIVE_RESULT_STATUSES` de `igea_dgs.native_action` se traduce en Task 3, no se importa aquí.

- [ ] **Step 1: Write the failing canonicalization tests**

```python
def test_episode_hash_is_independent_of_mapping_order():
    assert episode_sha256({'project': 'P', 'feeders': ['A1'], 'x': {'a': 1, 'b': 2}}) == \
           episode_sha256({'x': {'b': 2, 'a': 1}, 'feeders': ['A1'], 'project': 'P'})

def test_feeder_order_is_preserved_because_it_can_express_orientation():
    assert episode_sha256({'feeders': ['A1', 'A2']}) != episode_sha256({'feeders': ['A2', 'A1']})
```

- [ ] **Step 2: Run the canonicalization tests and verify failure**

Run: `python -m pytest tests/test_digital_twin_episode.py -q`
Expected: FAIL because `igea_dgs.digital_twin.episode` does not exist.

- [ ] **Step 3: Implement the immutable domain contract**

Define:

```python
class EpisodeClass(str, Enum):
    ACCEPTED = 'accepted'
    CONVERGED_WITH_VIOLATIONS = 'converged_with_violations'
    REJECTED = 'rejected'
    COUNTERFACTUAL = 'counterfactual'
    QUARANTINE = 'quarantine'

@dataclass(frozen=True)
class ArtifactRef:
    role: str
    relative_path: str
    sha256: str
    size: int

@dataclass(frozen=True)
class EpisodeManifest:
    schema: str
    episode_id: str
    episode_class: EpisodeClass
    created_at: str
    source: Mapping[str, Any]
    native: Mapping[str, Any]
    action: Mapping[str, Any]
    topology: Mapping[str, Any]
    state: Mapping[str, Any]
    acceptance: Mapping[str, Any]
    artifacts: tuple[ArtifactRef, ...]
```

Use schema name `igea-dgs-digital-twin-episode-v1`. `episode_id` is the SHA-256 of the canonical payload excluding `episode_id` and volatile write timestamps; list order remains significant.

- [ ] **Step 4: Add validation and schema tests**

Cover missing source fingerprint, missing units, invalid SHA-256, duplicate artifact roles, unknown class and an `accepted` episode without `reopen_verified=true`. Assert `parse_episode` raises `EpisodeValidationError` with the failing field path.

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest tests/test_digital_twin_episode.py -q`
Expected: PASS.

- [ ] **Step 6: Optional commit checkpoint**

```bash
git add src/igea_dgs/digital_twin src/igea_dgs/schemas/digital_twin_episode_v1.schema.json tests/test_digital_twin_episode.py
git commit -m "feat: define digital twin episode contract"
```

### Task 2: Búfer inmutable e índice reconstruible

**Files:**
- Create: `src/igea_dgs/digital_twin/buffer.py`
- Test: `tests/test_digital_twin_buffer.py`

**Interfaces:**
- Consumes: `EpisodeManifest`, `parse_episode`, `episode_sha256` from Task 1.
- Produces: `EpisodeQuery`, `EpisodeBuffer.put(manifest) -> Path`, `EpisodeBuffer.get(episode_id) -> EpisodeManifest`, `EpisodeBuffer.query(query) -> list[EpisodeManifest]`, `EpisodeBuffer.rebuild_index() -> int`, `default_buffer_root() -> Path`.

- [ ] **Step 1: Write failing storage tests**

Test that `put` writes one immutable manifest under `objects/<first-two>/<episode_id>.json`, a second identical `put` returns the same path without rewriting it, and a conflicting payload claiming the same ID raises `EpisodeCollisionError`.

- [ ] **Step 2: Run storage tests and verify failure**

Run: `python -m pytest tests/test_digital_twin_buffer.py -q`
Expected: FAIL because `EpisodeBuffer` does not exist.

- [ ] **Step 3: Implement atomic object storage**

Use a same-directory `.tmp` file, `flush`, `os.fsync` and `Path.replace`. Set `default_buffer_root()` to `IGEA_TWIN_DATA` when defined, otherwise `igea_dgs.web.workspace.data_root() / '_digital_twin'`.

- [ ] **Step 4: Add the SQLite index**

Create `episodes.sqlite3` with a versioned schema and indexed columns: `episode_id`, class, project, source fingerprint, action, PowerFactory version, created time and manifest relative path. Store project/feeders/topology details in the immutable JSON, not only in SQLite.

- [ ] **Step 5: Add query and rebuild tests**

Test filtering by class/project/feeder/action, deletion of `episodes.sqlite3`, `rebuild_index()`, corrupted manifest quarantine, and exact recovery of query results. A corrupt index must be replaceable without deleting objects.

- [ ] **Step 6: Run focused tests**

Run: `python -m pytest tests/test_digital_twin_buffer.py -q`
Expected: PASS.

- [ ] **Step 7: Optional commit checkpoint**

```bash
git add src/igea_dgs/digital_twin/buffer.py tests/test_digital_twin_buffer.py
git commit -m "feat: add immutable episode buffer"
```

### Task 3: Clasificación y ensamblaje de evidencia

**Files:**
- Create: `src/igea_dgs/digital_twin/capture.py`
- Modify: `src/igea_dgs/native_action.py`
- Test: `tests/test_digital_twin_capture.py`
- Test: `tests/test_native_project_gate.py`

**Interfaces:**
- Consumes: signed `native_action_context`, native result JSON, `ArtifactRef`, snapshot JSON from Task 4 and the Task 1 contract.
- Produces: `classify_episode(result, snapshot) -> EpisodeClass`, `build_episode(context, result, snapshot, artifacts, *, created_at) -> EpisodeManifest`, `quarantine_episode(context, result, error, artifacts) -> EpisodeManifest`.

- [ ] **Step 1: Write failing classification tests**

```python
@pytest.mark.parametrize(('result', 'snapshot', 'expected'), [
    ({'converged': True}, {'reopen_verified': True, 'physical_violations': []}, 'accepted'),
    ({'converged': True}, {'reopen_verified': True, 'physical_violations': [{'kind': 'undervoltage'}]}, 'converged_with_violations'),
    ({'converged': False}, {'reopen_verified': True}, 'rejected'),
    ({'converged': True}, {'reopen_verified': False}, 'quarantine'),
])
def test_episode_class_is_not_reduced_to_convergence(result, snapshot, expected): ...
```

- [ ] **Step 2: Run classification tests and verify failure**

Run: `python -m pytest tests/test_digital_twin_capture.py -q`
Expected: FAIL because capture functions do not exist.

- [ ] **Step 3: Extend the native status vocabulary without changing existing meanings**

Add pure helpers to `native_action.py` only if needed to expose normalized convergence, persistence and physical-violation fields. Preserve every existing `NATIVE_RESULT_STATUSES` value and existing test expectation.

- [ ] **Step 4: Implement episode assembly**

Require exact source identity from the signed context, native project/folder/case/variations from the snapshot, explicit units, stable object IDs, action result and artifact hashes. Missing required evidence produces a quarantine manifest with `acceptance.blockers`, never a partially valid accepted manifest.

- [ ] **Step 5: Test rejected attempts and rollback evidence**

Assert a rolled-back action remains `rejected`, includes `rollback.restored=true`, and cannot be converted to `accepted` by setting only `converged=true`. Assert the 0.8683 p.u. IN111–TA225 sample is `converged_with_violations`.

- [ ] **Step 6: Run focused regression**

Run: `python -m pytest tests/test_digital_twin_capture.py tests/test_native_project_gate.py -q`
Expected: PASS.

- [ ] **Step 7: Optional commit checkpoint**

```bash
git add src/igea_dgs/digital_twin/capture.py src/igea_dgs/native_action.py tests/test_digital_twin_capture.py tests/test_native_project_gate.py
git commit -m "feat: classify native work as twin episodes"
```

### Task 4: Snapshot nativo de red después de reapertura

**Files:**
- Create: `tools/digital_twin_snapshot_pf.py`
- Create: `src/igea_dgs/digital_twin/native_snapshot.py`
- Modify: `tests/fake_pf.py`
- Test: `tests/test_digital_twin_snapshot_pf.py`

**Interfaces:**
- Consumes: signed plan with `project`, `folder`, `feeders`, `case`, `native_action_context`, optional expected link fingerprints and voltage limits.
- Produces: `snapshot_project(app, plan) -> dict[str, Any]`; CLI `--plan`, `--output-json`; report schema `igea-dgs-digital-twin-native-snapshot-v1`.

- [ ] **Step 1: Write the failing read-only snapshot tests**

Build a fake project with two feeders, one open boundary and one manual link. Assert the report includes nodes, branches, transformers, injections, switches, active variations, nominal voltages, result values with units, component IDs and the link GPS SHA-256.

- [ ] **Step 2: Run snapshot tests and verify failure**

Run: `python -m pytest tests/test_digital_twin_snapshot_pf.py -q`
Expected: FAIL because the snapshot tool does not exist.

- [ ] **Step 3: Implement stable native identities**

In `native_snapshot.py`, define `native_object_id(obj) -> str` from project-relative full path and class. Never use Python identity or an unqualified `loc_name`. Serialize topology using terminal IDs and explicit side names.

- [ ] **Step 4: Implement the read-only extractor**

Activate the exact project and case, verify signed context before connecting, execute `ComLdf`, and read effective network-data objects only. Do not call `CreateObject`, `Delete`, `Move`, `SetAttribute` or `WriteChangesToDb`.

- [ ] **Step 5: Implement physical checks**

Report convergence separately from voltage/loading violations; compute connected components using in-service elements and switch states; hash `GPScoords`; record source and transfer components without assuming radiality or a fixed voltage.

- [ ] **Step 6: Add restart/reopen contract tests**

Test that `reopen_verified` is true only when the snapshot process identifies a fresh native session and rereads the expected active variations. A same-process payload must remain false/quarantined.

- [ ] **Step 7: Run focused tests**

Run: `python -m pytest tests/test_digital_twin_snapshot_pf.py tests/test_fake_pf_variaciones.py -q`
Expected: PASS.

- [ ] **Step 8: Optional commit checkpoint**

```bash
git add tools/digital_twin_snapshot_pf.py src/igea_dgs/digital_twin/native_snapshot.py tests/fake_pf.py tests/test_digital_twin_snapshot_pf.py
git commit -m "feat: export read-only native twin snapshots"
```

### Task 5: Captura automática de acciones PowerFactory

**Files:**
- Create: `src/igea_dgs/digital_twin/integration.py`
- Modify: `src/igea_dgs/web/services.py`
- Modify: `src/igea_dgs/web/jobs.py`
- Test: `tests/test_digital_twin_integration.py`
- Test: `tests/test_native_project_gate.py`

**Interfaces:**
- Consumes: `Workspace`, `JobContext`, signed plans, native result paths, Task 4 snapshot command, Task 2 buffer.
- Produces: `capture_native_action(ws, ctx, *, plan, result_path, action, applied) -> dict[str, Any]`; result field `digital_twin_episode` containing ID, class, manifest path and blockers.

- [ ] **Step 1: Write failing integration tests for all native action families**

Parameterize `powerfactory_flow`, `cargas_ejecutar`, `ajuste_ejecutar`, `pf_verificar`, `obras_ejecutar`, `estudios_ejecutar`, `transferencia_ejecutar` and `guion_ejecutar`. Assert each successful native result calls one capture function with the same signed context and output artifact.

- [ ] **Step 2: Run integration tests and verify failure**

Run: `python -m pytest tests/test_digital_twin_integration.py -q`
Expected: FAIL because no capture hook exists.

- [ ] **Step 3: Implement one integration boundary**

`capture_native_action` first stores the plan/result artifact hashes, then runs the read-only snapshot in the `powerfactory` lane after the mutating process has exited, builds the episode and writes it to the buffer. Do not scatter buffer writes through individual tools.

- [ ] **Step 4: Hook each service after its native output is final**

Call the same integration function after reading each `--output-json`. For `simular=True`, set `applied=False`; a simulation validated by PowerFactory may become `counterfactual`, never `accepted` as an observed action.

- [ ] **Step 5: Fail capture safely**

If snapshot/capture fails after an action, create a quarantine manifest from available artifacts, log `AVISO DIGITAL_TWIN_QUARANTINE`, and return the completed action result unchanged apart from `digital_twin_episode`. Never rerun or roll back the completed native action from this layer.

- [ ] **Step 6: Test cancellation and timeout**

Assert a cancelled or timed-out action records `rejected` or `quarantine` from available evidence and does not start a snapshot while the original PowerFactory process still owns the engine.

- [ ] **Step 7: Run focused web regressions**

Run: `python -m pytest tests/test_digital_twin_integration.py tests/test_native_project_gate.py tests/test_pf_arnes.py tests/test_pf_servidor.py -q`
Expected: PASS.

- [ ] **Step 8: Optional commit checkpoint**

```bash
git add src/igea_dgs/digital_twin/integration.py src/igea_dgs/web/services.py src/igea_dgs/web/jobs.py tests/test_digital_twin_integration.py tests/test_native_project_gate.py
git commit -m "feat: capture every native action as an episode"
```

### Task 6: Consulta web y CLI del búfer

**Files:**
- Create: `tools/digital_twin_buffer.py`
- Modify: `src/igea_dgs/web/services.py`
- Modify: `src/igea_dgs/web/app.py`
- Test: `tests/test_digital_twin_web.py`
- Test: `tests/test_digital_twin_buffer_cli.py`

**Interfaces:**
- Consumes: `EpisodeBuffer` and `EpisodeQuery` from Task 2.
- Produces: `GET /api/workspaces/{wid}/digital-twin/episodes`, `GET /api/workspaces/{wid}/digital-twin/episodes/{episode_id}`; CLI subcommands `list`, `show`, `validate`, `rebuild-index`, `register`.

- [ ] **Step 1: Write failing API authorization and filter tests**

Assert list filters project/feeder/class/action, detail returns one manifest, invalid IDs return 404, and an episode outside the active workspace is visible only when its source/project binding is shared through the existing spec-018 registry.

- [ ] **Step 2: Run API tests and verify failure**

Run: `python -m pytest tests/test_digital_twin_web.py -q`
Expected: FAIL with missing routes.

- [ ] **Step 3: Implement read-only service and routes**

Return summaries by default; detail returns the manifest but never original proprietary file contents. Use existing `WorkspaceStore` and binding rules rather than inventing a second authorization system.

- [ ] **Step 4: Write failing CLI tests**

Test valid registration, duplicate idempotency, schema rejection to quarantine, list filters and index rebuild. `register` accepts manifest/artifact paths but computes hashes itself.

- [ ] **Step 5: Implement the CLI**

Keep PowerFactory out of this tool. It manages already produced episode artifacts and exits 0 for valid/idempotent operations, 2 for invalid input and 3 for unavailable/corrupt storage.

- [ ] **Step 6: Run focused tests**

Run: `python -m pytest tests/test_digital_twin_web.py tests/test_digital_twin_buffer_cli.py -q`
Expected: PASS.

- [ ] **Step 7: Optional commit checkpoint**

```bash
git add tools/digital_twin_buffer.py src/igea_dgs/web/services.py src/igea_dgs/web/app.py tests/test_digital_twin_web.py tests/test_digital_twin_buffer_cli.py
git commit -m "feat: expose digital twin episode buffer"
```

### Task 7: Caso dorado IN111–TA225 y aceptación nativa

**Files:**
- Create: `tests/fixtures/digital_twin/in111_ta225_topology_episode.json`
- Create: `tests/test_digital_twin_in111_ta225.py`
- Create: `tools/accept_digital_twin_in111_ta225.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 4 snapshot, Task 3 capture and Task 2 buffer.
- Produces: sanitized topology fixture; native acceptance report `digital_twin_in111_ta225_acceptance.json`; no PowerFactory writes.

- [ ] **Step 1: Add the sanitized golden fixture and failing tests**

The fixture contains no coordinates or customer data, only stable synthetic IDs/hashes and these required facts: source component 10 kV, 3091 in source, 3092 outside source, transfer component 22.9 kV, manual-link hash unchanged, 3091 result 0.9521694512 p.u., 3092 result 0.9604280727 p.u., minimum 0.8683284313 p.u. and class `converged_with_violations`.

- [ ] **Step 2: Run golden-case tests and verify failure**

Run: `python -m pytest tests/test_digital_twin_in111_ta225.py -q`
Expected: FAIL until the acceptance tool exists and the classifier preserves the violation.

- [ ] **Step 3: Implement read-only native acceptance**

The tool activates project `20261015-170359_IGEA_IN111_TA225` in `sistemaeletricoELD`, case `Con proyecto`, and verifies the existing active variations without creating/deleting anything. Require 3091/source connectivity at 10 kV, 3092 transfer isolation at 22.9 kV, `SEC_1091_1055021(1)` in service, link endpoints preserved, GPS SHA-256 preserved and valid `ComLdf`.

- [ ] **Step 4: Register the real episode**

Use the workspace/source binding and fresh snapshot to build the episode. Because the minimum voltage is 0.8683 p.u., assert its class is `converged_with_violations`, not `accepted`; the topological checks remain golden.

- [ ] **Step 5: Reopen and reread**

Run the acceptance in a fresh PowerFactory process, close it, then invoke the snapshot tool in another fresh process. Assert the two topology/link fingerprints match and the second report carries `reopen_verified=true`.

- [ ] **Step 6: Document operator commands**

Add commands to validate/list the buffer and run this native acceptance. State explicitly that this task captures data but does not train a PINN.

- [ ] **Step 7: Run focused and native verification**

Run without license: `python -m pytest tests/test_digital_twin_in111_ta225.py -q`
Expected: PASS.

Run with PowerFactory: `python tools/accept_digital_twin_in111_ta225.py --project 20261015-170359_IGEA_IN111_TA225 --folder sistemaeletricoELD --output-json <run>/salida/digital_twin_in111_ta225_acceptance.json`
Expected: exit 0, snapshot persisted, episode class `converged_with_violations`, all topology/link checks true and `ComLdf` valid.

- [ ] **Step 8: Optional commit checkpoint**

```bash
git add tests/fixtures/digital_twin/in111_ta225_topology_episode.json tests/test_digital_twin_in111_ta225.py tools/accept_digital_twin_in111_ta225.py README.md
git commit -m "test: capture IN111 TA225 twin episode"
```

### Task 8: Cobertura, calidad y preparación del siguiente plan

**Files:**
- Modify: `specs/024-pinn-gemelo-digital/spec.md` only if implementation reveals a contract correction.
- Create: `docs/superpowers/plans/2026-10-21-digital-twin-scenario-matrix.md` after this plan is accepted and complete.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified Phase 1 delivery and evidence inventory for the scenario-generation plan.

- [ ] **Step 1: Run the complete focused suite**

Run: `python -m pytest tests/test_digital_twin_episode.py tests/test_digital_twin_buffer.py tests/test_digital_twin_capture.py tests/test_digital_twin_snapshot_pf.py tests/test_digital_twin_integration.py tests/test_digital_twin_web.py tests/test_digital_twin_buffer_cli.py tests/test_digital_twin_in111_ta225.py -q`
Expected: PASS with no skipped test hiding a missing contract.

- [ ] **Step 2: Run affected native-contract regressions**

Run: `python -m pytest tests/test_native_project_gate.py tests/test_powerfactory_source_run.py tests/test_powerfactory_binding.py tests/test_pf_arnes.py tests/test_pf_servidor.py -q`
Expected: PASS.

- [ ] **Step 3: Run scoped Ruff**

Run: `python -m ruff check src/igea_dgs/digital_twin src/igea_dgs/native_action.py src/igea_dgs/web/services.py src/igea_dgs/web/jobs.py src/igea_dgs/web/app.py tools/digital_twin_snapshot_pf.py tools/digital_twin_buffer.py tools/accept_digital_twin_in111_ta225.py tests/test_digital_twin_*.py`
Expected: PASS. Report this exact scope; do not claim repository-wide Ruff.

- [ ] **Step 4: Run formatting and diff checks**

Run: `git diff --check`
Expected: no errors.

- [ ] **Step 5: Audit RF coverage**

Map implemented tests to spec RF-1 through RF-10 and RF-24 through RF-27. Mark RF-11 through RF-23 as planned, not implemented; do not present the PINN as trained.

- [ ] **Step 6: Inventory training readiness**

Report episode counts by class/project/topology, missing fields, quarantined causes and license-time estimate. The next plan starts only if there is at least one complete golden episode and the buffer/index rebuild passes.

- [ ] **Step 7: Optional final commit checkpoint**

```bash
git add docs/superpowers/plans/2026-10-21-digital-twin-episode-buffer.md
git commit -m "docs: plan digital twin episode buffer"
```
