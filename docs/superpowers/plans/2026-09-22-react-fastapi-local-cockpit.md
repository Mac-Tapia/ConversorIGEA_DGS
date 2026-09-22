# React + FastAPI Local Grid Cockpit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar un cockpit local React que conserve la selección y conversión actuales, añada edición unifilar/mapa y exponga el pipeline estricto G1–G6 mediante FastAPI sin modificar TXT originales.

**Architecture:** FastAPI sirve la build React y adapta servicios Python tipados; SQLite almacena proyectos, revisiones y trabajos, mientras `changes.jsonl` conserva el historial append-only. React usa la API como única fuente de verdad; Cytoscape y Leaflet comparten IDs externos y toda mutación eléctrica vuelve al dominio para validación.

**Tech Stack:** CPython 3.12 x64, FastAPI, Uvicorn, Pydantic 2, SQLite, React 19, TypeScript, Vite, TanStack Query, React Hook Form, Cytoscape.js, Leaflet, Vitest, Testing Library, Playwright, DIgSILENT PowerFactory 2024.

**Spec:** `docs/superpowers/specs/2026-09-22-react-fastapi-local-cockpit-design.md`

## Global Constraints

- La aplicación escucha solo en `127.0.0.1` y requiere token de sesión en HTTP/WebSocket.
- Los TXT originales RED/CARGA/BD_Equipo nunca se modifican; se verifica SHA-256 antes y después.
- El modo estricto es obligatorio; no hay defaults físicos, aliases libres ni matching aproximado.
- React no implementa reglas eléctricas; `PipelineService` es el único orquestador G1–G6.
- Solo una revisión aprobada G1–G4 puede publicar DGS o importarse en PowerFactory.
- El caso PowerFactory original es inmutable; correcciones solo en copia diagnóstica con `run_id`.
- Tkinter continúa disponible como respaldo mediante un lanzador separado.
- Todos los recursos web funcionan offline; no se usan CDN.
- Cada tarea sigue RED → GREEN → refactor → verificación completa → commit.

## Review Focus

- Carpeta con dos candidatos RED o lote mezclado: Task 2 prueba que la detección bloquea con `INPUT_FILE_AMBIGUOUS` y no elige por orden.
- Dos pestañas editando la misma revisión: Task 3 prueba conflicto optimista HTTP 409 y preservación del historial.
- Reconexión WebSocket después de terminar un trabajo: Task 5 prueba replay del último estado persistido.
- Eliminar un nodo conectado desde Cytoscape: Task 8 prueba bloqueo y que no se pierde ninguna arista.
- Cierre durante una unidad PowerFactory mutante: Task 11 prueba cancelación cooperativa, rollback y ausencia de PASS falso.

---

### Task 1: Dependencias reproducibles, FastAPI mínimo y scaffold React

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Modify: `constraints.txt`
- Create: `requirements-web.txt`
- Create: `src/igea_dgs/web/__init__.py`
- Create: `src/igea_dgs/web/app.py`
- Create: `web/package.json`
- Create: `web/package-lock.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/src/main.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/app.css`
- Create: `web/src/App.test.tsx`
- Create: `tests/test_web_health.py`
- Modify: `scripts/bootstrap.ps1`
- Modify: `scripts/verify.ps1`

**Interfaces:**
- Produces: `create_app(*, project_root: Path, session_token: str) -> FastAPI`, `GET /api/health`, comandos `npm run test`, `npm run build`.

- [ ] **Step 1: Escribir pruebas fallidas de health y shell React**

```python
def test_health_is_local_and_versioned(tmp_path):
    app = create_app(project_root=tmp_path, session_token="secret")
    response = TestClient(app).get("/api/health", headers={"X-Session-Token": "secret"})
    assert response.json() == {"status": "ok", "api_version": "1"}

def test_missing_session_token_is_rejected(tmp_path):
    response = TestClient(create_app(project_root=tmp_path, session_token="secret")).get("/api/health")
    assert response.status_code == 401
```

```tsx
it('renders the six cockpit modules', () => {
  render(<App />)
  for (const label of ['Proyecto', 'Diagnóstico G1–G4', 'Unifilar', 'Mapa', 'PowerFactory G5–G6', 'Evidencias']) {
    expect(screen.getByText(label)).toBeInTheDocument()
  }
})
```

- [ ] **Step 2: Ejecutar RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_web_health.py -v`  
Expected: FAIL porque `igea_dgs.web` no existe.

Run: `npm --prefix web test -- --run`  
Expected: FAIL porque no existe el proyecto web.

- [ ] **Step 3: Añadir dependencias y aplicación mínima**

Añadir `fastapi`, `uvicorn[standard]`, `python-multipart` y `httpx` con límites compatibles; añadir extra `web`. Fijar React 19, Vite, TypeScript, Vitest, Testing Library, TanStack Query, React Router, React Hook Form, Cytoscape, Leaflet y Playwright en `package-lock.json`. Implementar middleware de token y shell accesible.

- [ ] **Step 4: Integrar bootstrap/verify**

`bootstrap.ps1` instala `requirements-web.txt`, ejecuta `npm ci`; `verify.ps1` ejecuta lint/typecheck/test/build web además de la puerta Python y falla con cualquier código no cero.

- [ ] **Step 5: Ejecutar GREEN y regresión**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_web_health.py -v`  
Run: `npm --prefix web test -- --run`  
Run: `npm --prefix web run build`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml requirements*.txt constraints.txt scripts web src/igea_dgs/web tests/test_web_health.py
git commit -m "build: scaffold local FastAPI React cockpit"
```

### Task 2: Custodia de proyectos y selección segura de entradas

**Files:**
- Create: `src/igea_dgs/projects/models.py`
- Create: `src/igea_dgs/projects/store.py`
- Create: `src/igea_dgs/projects/inputs.py`
- Create: `src/igea_dgs/projects/__init__.py`
- Create: `src/igea_dgs/web/routes/projects.py`
- Create: `src/igea_dgs/web/routes/dialogs.py`
- Create: `src/igea_dgs/web/routes/__init__.py`
- Modify: `src/igea_dgs/web/app.py`
- Create: `tests/test_project_custody_api.py`

**Interfaces:**
- Produces: `ProjectStore.create`, `ProjectStore.get`, `register_inputs(project_id, InputSelection) -> InputManifest`, `detect_input_set(folder) -> InputSelection`, endpoints `/api/projects`, `/api/dialog/*`, `/api/projects/{id}/inputs`.

- [ ] **Step 1: Escribir pruebas fallidas de custodia y ambigüedad**

```python
def test_register_inputs_hashes_without_modifying_originals(api, txt_triplet):
    before = {p: p.read_bytes() for p in txt_triplet}
    result = api.register_paths(txt_triplet)
    assert all(len(item.sha256) == 64 for item in result.files)
    assert {p: p.read_bytes() for p in txt_triplet} == before

def test_folder_with_two_red_candidates_blocks(api, tmp_path, txt_triplet):
    (tmp_path / "RED_COPY.txt").write_text("duplicate", encoding="utf-8")
    response = api.detect_folder(tmp_path)
    assert response.status_code == 422
    assert response.json()["code"] == "INPUT_FILE_AMBIGUOUS"
```

- [ ] **Step 2: Ejecutar RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_project_custody_api.py -v`  
Expected: FAIL por módulos ausentes.

- [ ] **Step 3: Implementar SQLite y resolución canónica**

Crear tablas `projects` e `input_files`. Toda ruta se resuelve con `Path.resolve(strict=True)` y solo se registra tras selección explícita. Detectar exactamente un RED, CARGA y BD_Equipo; cero produce `INPUT_TXT_MISSING`, más de uno `INPUT_FILE_AMBIGUOUS`.

- [ ] **Step 4: Implementar diálogo Windows inyectable**

Definir protocolo `NativeDialogPort.select_file(patterns) -> Path | None` y `select_folder() -> Path | None`; implementación Tk usa `filedialog` en hilo STA. En tests usar fake; cancelar devuelve 204.

- [ ] **Step 5: Ejecutar pruebas y suite**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_project_custody_api.py tests/test_strict_ingestion.py -v`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/projects src/igea_dgs/web tests/test_project_custody_api.py
git commit -m "feat: add immutable local project custody"
```

### Task 3: Revisiones y operaciones auditables

**Files:**
- Create: `src/igea_dgs/revisions/models.py`
- Create: `src/igea_dgs/revisions/store.py`
- Create: `src/igea_dgs/revisions/apply.py`
- Create: `src/igea_dgs/revisions/__init__.py`
- Create: `src/igea_dgs/web/routes/revisions.py`
- Modify: `src/igea_dgs/web/app.py`
- Create: `tests/test_revision_api.py`

**Interfaces:**
- Produces: `ChangeOperation`, `RevisionSnapshot`, `RevisionStore.append(expected_version, operation)`, `undo(operation_id)`, endpoints GET/POST revisions y operations.

- [ ] **Step 1: Escribir pruebas RED para append, undo y conflicto**

```python
def test_change_is_append_only_and_undo_adds_inverse(revision_store):
    first = revision_store.append(0, update_line("L1", "circuits", 1, 2))
    undone = revision_store.undo(first.operation_id, expected_version=1)
    assert undone.sequence == 2
    assert revision_store.read_log() == [first, undone]
    assert revision_store.snapshot().lines["L1"].circuits.count == 1

def test_stale_browser_revision_returns_conflict(client, revision):
    client.post(operation_url(revision), json=operation(version=0, value=2))
    response = client.post(operation_url(revision), json=operation(version=0, value=3))
    assert response.status_code == 409
    assert response.json()["code"] == "REVISION_VERSION_CONFLICT"
```

- [ ] **Step 2: Ejecutar RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_revision_api.py -v`

- [ ] **Step 3: Implementar JSONL y aplicación pura**

Validar acciones `create/update/delete/connect/disconnect/move`, IDs, unidades, valor anterior y justificación. Escribir cada línea con flush + fsync y actualizar versión SQLite en la misma sección crítica. `move` solo modifica layout; demás operaciones producen modelo de dominio.

- [ ] **Step 4: Ejecutar GREEN y propiedades**

Añadir Hypothesis: aplicar operación + inversa conserva snapshot; una secuencia inválida no modifica log ni versión.

Run: `\.venv\Scripts\python.exe -m pytest tests/test_revision_api.py -v`
Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

- [ ] **Step 5: Commit**

```bash
git add src/igea_dgs/revisions src/igea_dgs/web tests/test_revision_api.py
git commit -m "feat: add audited editable network revisions"
```

### Task 4: Pipeline web estricto G1–G4

**Files:**
- Modify: `src/igea_dgs/services/pipeline.py`
- Create: `src/igea_dgs/services/project_pipeline.py`
- Create: `src/igea_dgs/web/routes/pipeline.py`
- Modify: `src/igea_dgs/web/app.py`
- Create: `tests/test_project_pipeline_api.py`

**Interfaces:**
- Consumes: `ProjectStore`, `RevisionStore`, inventario estricto, catálogo, reglas, validadores, `write_strict_dgs`.
- Produces: `ProjectPipeline.inspect`, `validate_revision`, `publish_revision`, endpoints inspect/validate/publish.

- [ ] **Step 1: Escribir prueba que prohíbe batch heredado**

```python
def test_web_pipeline_stops_at_g2_and_never_calls_legacy_batch(project_pipeline, missing_catalog):
    result = project_pipeline.validate_revision(missing_catalog.revision_id)
    assert result.exit_code == 2
    assert result.last_gate == "G2"
    assert not missing_catalog.output_dir.joinpath("F1.dgs").exists()

def test_web_modules_do_not_import_legacy_batch():
    for path in Path("src/igea_dgs/web").rglob("*.py"):
        assert "igea_dgs.batch" not in path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Ejecutar RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_project_pipeline_api.py -v`

- [ ] **Step 3: Implementar adaptación completa**

G1 usa parser/inventario estricto; G2 modelo estricto + catálogo exacto + TRAFOMIX; G3 fuente-modelo; G4 modelo-DGS. Convertir cada `Diagnostic` en DTO API conservando location/details. Publicar solo mediante `AtomicRunPublisher`.

- [ ] **Step 4: Probar líneas, cables, multiplicidad y generación**

Añadir fixtures que incluyan aéreo, subterráneo, 2 circuitos, 2 conductores/fase, solar, térmica, TRAFOMIX+load y SED+load. Afirmar presencia/exclusión exacta y ausencia de defaults.

- [ ] **Step 5: Ejecutar GREEN y suite**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_project_pipeline_api.py tests/test_independence.py tests/test_trafomix_rule.py -v`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/services src/igea_dgs/web tests/test_project_pipeline_api.py
git commit -m "feat: expose strict G1-G4 project pipeline"
```

### Task 5: Trabajos persistentes, progreso y WebSocket

**Files:**
- Create: `src/igea_dgs/jobs/models.py`
- Create: `src/igea_dgs/jobs/manager.py`
- Create: `src/igea_dgs/jobs/__init__.py`
- Create: `src/igea_dgs/web/routes/jobs.py`
- Modify: `src/igea_dgs/web/app.py`
- Create: `tests/test_job_websocket.py`

**Interfaces:**
- Produces: `JobManager.submit`, `emit`, `cancel`, `snapshot`, `subscribe`; HTTP 202 `{run_id}` y WS `/api/jobs/{run_id}/events`.

- [ ] **Step 1: Escribir pruebas RED de progreso, replay y cancelación**

```python
def test_reconnected_websocket_replays_terminal_state(client, completed_job, token):
    with client.websocket_connect(f"/api/jobs/{completed_job.run_id}/events?token={token}") as ws:
        assert ws.receive_json()["state"] == "passed"

def test_cancelled_job_never_becomes_passed(job_manager, cancellable_job):
    job_manager.cancel(cancellable_job.run_id)
    assert job_manager.snapshot(cancellable_job.run_id).state == "cancelled"
```

- [ ] **Step 2: Ejecutar RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_job_websocket.py -v`

- [ ] **Step 3: Implementar máquina de estados persistente**

Usar SQLite y `threading.Event` de cancelación. Persistir cada transición antes de emitir. Serializar trabajos mutantes PowerFactory con un lock exclusivo. Rechazar transiciones ilegales.

- [ ] **Step 4: Ejecutar GREEN y suite**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_job_websocket.py -v`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

- [ ] **Step 5: Commit**

```bash
git add src/igea_dgs/jobs src/igea_dgs/web tests/test_job_websocket.py
git commit -m "feat: add persistent local pipeline jobs"
```

### Task 6: Cockpit React y selección dinámica de archivos

**Files:**
- Create: `web/src/api/client.ts`
- Create: `web/src/api/types.ts`
- Create: `web/src/app/router.tsx`
- Create: `web/src/layout/CockpitLayout.tsx`
- Create: `web/src/features/project/ProjectPage.tsx`
- Create: `web/src/features/project/InputSelector.tsx`
- Create: `web/src/features/project/ProjectPage.test.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/app.css`

**Interfaces:**
- Consumes: endpoints de proyectos/dialog/input.
- Produces: pantalla aprobada de proyecto, hooks `useProject`, `useRegisterInputs`.

- [ ] **Step 1: Escribir pruebas RED de interacción real**

```tsx
it('selects a folder and renders all three detected paths', async () => {
  server.use(dialogFolderSuccess(), detectInputsSuccess())
  render(<ProjectPage />)
  await userEvent.click(screen.getByRole('button', { name: /seleccionar carpeta de entrada/i }))
  expect(await screen.findByDisplayValue(/RED_PA217\.txt/)).toBeVisible()
  expect(screen.getByDisplayValue(/CARGA_PA217\.txt/)).toBeVisible()
  expect(screen.getByDisplayValue(/BD_Equipo_PA217\.txt/)).toBeVisible()
})

it('does not enable inspect until input and output paths are valid', () => {
  render(<ProjectPage />)
  expect(screen.getByRole('button', { name: /analizar TXT/i })).toBeDisabled()
})
```

- [ ] **Step 2: Ejecutar RED**

Run: `npm --prefix web test -- --run ProjectPage.test.tsx`

- [ ] **Step 3: Implementar cockpit accesible y responsive**

Conservar campos RED/CARGA/BD_Equipo/salida, CRS, longitud, geografía, preview, XLSX y TSV. Añadir carpeta, drag/drop, hashes y estados. Eliminar aliases libres y checkbox no estricto. Usar etiquetas, navegación por teclado y `aria-live` para progreso.

- [ ] **Step 4: Ejecutar GREEN y build**

Run: `npm --prefix web test -- --run`  
Run: `npm --prefix web run typecheck`  
Run: `npm --prefix web run build`

- [ ] **Step 5: Commit**

```bash
git add web
git commit -m "feat: add local project cockpit and input selection"
```

### Task 7: Tablero de diagnóstico y navegación cruzada

**Files:**
- Create: `web/src/features/diagnostics/DiagnosticsPage.tsx`
- Create: `web/src/features/diagnostics/DiagnosticTable.tsx`
- Create: `web/src/features/diagnostics/GateSummary.tsx`
- Create: `web/src/features/diagnostics/DiagnosticsPage.test.tsx`
- Modify: `web/src/app/router.tsx`
- Modify: `web/src/api/types.ts`

**Interfaces:**
- Produces: filtros por gate/severity/code, selección global `SelectedElementContext`, exportación JSON/CSV.

- [ ] **Step 1: Escribir pruebas RED**

```tsx
it('shows TRAFOMIX exclusions separately from preserved SED loads', async () => {
  renderDiagnostics(fixtureWithExclusions())
  expect(await screen.findByText('TRAFOMIX excluidos: 2')).toBeVisible()
  expect(screen.getByText('SED y cargas conservadas: 7')).toBeVisible()
})

it('selecting a diagnostic publishes its external id', async () => {
  const selected = renderDiagnostics(blockedLineFixture())
  await userEvent.click(await screen.findByText('SOURCE_SHORT_CIRCUIT_DATA_MISSING'))
  expect(selected.current).toBe('SRC-01')
})
```

- [ ] **Step 2: Ejecutar RED**

Run: `npm --prefix web test -- --run DiagnosticsPage.test.tsx`

- [ ] **Step 3: Implementar tabla virtualizada y resúmenes**

Mostrar código, mensaje, localización, valor observado, evidencia requerida, enlace a unifilar/mapa y estado de puerta. No renderizar texto no confiable como HTML.

- [ ] **Step 4: Ejecutar GREEN y build**

Run: `npm --prefix web test -- --run`  
Run: `npm --prefix web run build`

- [ ] **Step 5: Commit**

```bash
git add web/src/features/diagnostics web/src/app web/src/api
git commit -m "feat: add actionable G1-G4 diagnostics dashboard"
```

### Task 8: Editor unifilar Cytoscape y panel de propiedades

**Files:**
- Create: `src/igea_dgs/web/routes/graph.py`
- Modify: `src/igea_dgs/web/app.py`
- Create: `tests/test_graph_edit_api.py`
- Create: `web/src/features/graph/GraphPage.tsx`
- Create: `web/src/features/graph/NetworkCanvas.tsx`
- Create: `web/src/features/graph/PropertyPanel.tsx`
- Create: `web/src/features/graph/changeMapper.ts`
- Create: `web/src/features/graph/GraphPage.test.tsx`
- Modify: `web/src/app/router.tsx`

**Interfaces:**
- Produces: `GET .../graph -> GraphDto`, operaciones de grafo → `ChangeOperation`, foco por external ID.

- [ ] **Step 1: Escribir RED backend para eliminación conectada**

```python
def test_deleting_connected_node_is_blocked_without_losing_edges(graph_api, connected_graph):
    before = graph_api.snapshot(connected_graph)
    response = graph_api.delete_node("N1", expected_version=0)
    assert response.status_code == 422
    assert response.json()["code"] == "CONNECTED_NODE_DELETE_BLOCKED"
    assert graph_api.snapshot(connected_graph) == before
```

- [ ] **Step 2: Escribir RED frontend para edición versionada**

```tsx
it('submits a circuit change with old value, unit and justification', async () => {
  renderGraph(lineL1())
  await selectElement('L1')
  await userEvent.clear(screen.getByLabelText(/circuitos/i))
  await userEvent.type(screen.getByLabelText(/circuitos/i), '2')
  await userEvent.type(screen.getByLabelText(/justificación/i), 'Plano aprobado R07')
  await userEvent.click(screen.getByRole('button', { name: /proponer cambio/i }))
  expect(lastOperation()).toMatchObject({ external_id: 'L1', field: 'circuits', old_value: 1, new_value: 2 })
})
```

- [ ] **Step 3: Ejecutar RED backend/frontend**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_graph_edit_api.py -v`  
Run: `npm --prefix web test -- --run GraphPage.test.tsx`

- [ ] **Step 4: Implementar grafo, estilos y operaciones**

Soportar multigrafo, selección, zoom, layout guardado, create/update/delete/connect/disconnect/move, undo/redo. Marcar aéreo/subterráneo, fases, bloqueo, fuera de servicio, TRAFOMIX excluido, SED, carga y generación. Datos eléctricos se confirman en API antes de actualizar; movimiento usa optimismo reversible.

- [ ] **Step 5: Ejecutar GREEN y suite**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_graph_edit_api.py -v`  
Run: `npm --prefix web test -- --run`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/web web/src/features/graph tests/test_graph_edit_api.py
git commit -m "feat: add audited Cytoscape network editor"
```

### Task 9: Mapa Leaflet sincronizado y política de longitud

**Files:**
- Create: `src/igea_dgs/web/routes/map.py`
- Modify: `src/igea_dgs/web/app.py`
- Create: `tests/test_map_edit_api.py`
- Create: `web/src/features/map/MapPage.tsx`
- Create: `web/src/features/map/NetworkMap.tsx`
- Create: `web/src/features/map/MapPage.test.tsx`
- Modify: `web/src/app/router.tsx`

**Interfaces:**
- Produces: GeoJSON seguro por revisión, selección sincronizada, operación `move_geometry` y validación de política de longitud.

- [ ] **Step 1: Escribir RED para no cambiar longitud implícitamente**

```python
def test_moving_geometry_does_not_replace_txt_length_without_policy(map_api, line):
    map_api.move_geometry(line.section_id, shifted_path())
    effective = map_api.get_line(line.section_id)
    assert effective.length_km == line.length_km
    assert effective.geometry != line.geometry
```

- [ ] **Step 2: Escribir RED frontend de selección bidireccional**

```tsx
it('focuses the line selected in diagnostics', async () => {
  renderMap({ selectedElementId: 'L-013' })
  expect(await mapFeature('L-013')).toHaveClass('selected')
})
```

- [ ] **Step 3: Implementar y probar**

Empaquetar tiles/base offline o permitir mapa sin tiles; no usar CDN. Escapar popups. Mantener TXT autoritativo por defecto y pedir confirmación/política para reemplazo dimensional.

Run: `\.venv\Scripts\python.exe -m pytest tests/test_map_edit_api.py tests/test_length_policy.py -v`  
Run: `npm --prefix web test -- --run MapPage.test.tsx`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

- [ ] **Step 4: Commit**

```bash
git add src/igea_dgs/web web/src/features/map tests/test_map_edit_api.py
git commit -m "feat: add synchronized offline network map"
```

### Task 10: Publicación DGS, evidencias y descarga segura

**Files:**
- Create: `src/igea_dgs/web/routes/evidence.py`
- Modify: `src/igea_dgs/web/routes/pipeline.py`
- Modify: `src/igea_dgs/web/app.py`
- Create: `tests/test_web_publish_atomic.py`
- Create: `web/src/features/evidence/EvidencePage.tsx`
- Create: `web/src/features/evidence/EvidencePage.test.tsx`
- Modify: `web/src/app/router.tsx`

**Interfaces:**
- Produces: publish 202 job, manifiesto con hashes, endpoints de evidencia/descarga dentro del proyecto.

- [ ] **Step 1: Escribir RED de bloqueo y atomicidad**

```python
def test_blocked_revision_cannot_replace_known_good_publish(web_api, blocked_revision, known_good):
    response = web_api.publish(blocked_revision)
    assert response.status_code == 422
    assert known_good.read_bytes() == web_api.known_good_bytes()
    assert not web_api.has_partial_staging()
```

- [ ] **Step 2: Ejecutar RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_web_publish_atomic.py -v`

- [ ] **Step 3: Implementar evidencia completa**

Incluir input/revision/DGS hashes, versiones, diagnostics, coverage, catálogo, exclusiones, cambios, conteos y gate results. Validar download path por ID de artefacto, nunca por ruta suministrada.

- [ ] **Step 4: Implementar página y pruebas**

```tsx
it('keeps publish disabled while any blocking diagnostic exists', async () => {
  render(<EvidencePage />, { revision: blockedRevision() })
  expect(await screen.findByRole('button', { name: /publicar DGS/i })).toBeDisabled()
})
```

Run: `npm --prefix web test -- --run EvidencePage.test.tsx`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

- [ ] **Step 5: Commit**

```bash
git add src/igea_dgs/web web/src/features/evidence tests/test_web_publish_atomic.py
git commit -m "feat: publish strict DGS and evidence atomically"
```

### Task 11: PowerFactory G5–G6 desde la API y cockpit

**Files:**
- Create: `src/igea_dgs/web/routes/powerfactory.py`
- Create: `src/igea_dgs/services/powerfactory_pipeline.py`
- Modify: `src/igea_dgs/web/app.py`
- Modify: `src/igea_dgs/powerfactory/studies/load_flow.py`
- Create: `tests/test_powerfactory_web_pipeline.py`
- Create: `web/src/features/powerfactory/PowerFactoryPage.tsx`
- Create: `web/src/features/powerfactory/StudyResults.tsx`
- Create: `web/src/features/powerfactory/PowerFactoryPage.test.tsx`
- Modify: `web/src/app/router.tsx`

**Interfaces:**
- Produces: import/validate/studies jobs, `PowerFactoryRunSummary`, pantalla original/diagnóstico, cancelación con rollback.

- [ ] **Step 1: Escribir RED de procedencia e inmutabilidad**

```python
def test_import_rejects_dgs_not_published_by_revision(pf_pipeline, arbitrary_dgs):
    result = pf_pipeline.import_revision(arbitrary_dgs)
    assert result.error_codes == {"UNTRUSTED_DGS_PROVENANCE"}

def test_cancel_during_pf_mutation_rolls_back_and_never_passes(pf_pipeline, fake_pf):
    run = pf_pipeline.start_diagnostic(fake_pf)
    run.cancel()
    assert fake_pf.snapshot() == fake_pf.before
    assert run.state == "cancelled"
    assert run.state != "passed"
```

- [ ] **Step 2: Ejecutar RED**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_powerfactory_web_pipeline.py -v`

- [ ] **Step 3: Implementar G5–G6**

Importar solo artefacto publicado con hash coincidente. Validar proyecto/Study Case/escenario exactos, objetos efectivos e idempotencia. Ejecutar `run_original_load_flow` sin correcciones; crear copia para diagnóstico. Preflight IEC 60909 distingue datos/licencia/ejecución. Persistir diffs y KPIs.

- [ ] **Step 4: Implementar pantalla y pruebas**

```tsx
it('never labels a diagnostic converged copy as original pass', async () => {
  renderPowerFactory(originalFailedDiagnosticPassed())
  expect(await screen.findByText('Original: no converge')).toBeVisible()
  expect(screen.getByText('Copia diagnóstica: converge')).toBeVisible()
  expect(screen.queryByText('Aceptación original aprobada')).not.toBeInTheDocument()
})
```

Run: `npm --prefix web test -- --run PowerFactoryPage.test.tsx`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`

- [ ] **Step 5: Commit**

```bash
git add src/igea_dgs/services src/igea_dgs/web src/igea_dgs/powerfactory web/src/features/powerfactory tests/test_powerfactory_web_pipeline.py
git commit -m "feat: expose guarded PowerFactory G5-G6 cockpit"
```

### Task 12: Lanzador local, empaquetado offline y aceptación integral

**Files:**
- Create: `src/igea_dgs/web/launcher.py`
- Modify: `src/igea_dgs/web/app.py`
- Modify: `pyproject.toml`
- Modify: `run_gui.bat`
- Create: `run_tkinter.bat`
- Create: `scripts/build-web.ps1`
- Modify: `scripts/acceptance.ps1`
- Create: `web/e2e/project-flow.spec.ts`
- Create: `tests/test_web_launcher.py`
- Modify: `README.md`
- Modify: `docs/OPERATIONS_RUNBOOK.md`
- Modify: `CODIGO_FUENTE.md`

**Interfaces:**
- Produces: comando `igea-dgs-web`, un solo arranque, React estático offline, Tkinter backup y aceptación reproducible.

- [ ] **Step 1: Escribir RED del lanzador**

```python
def test_launcher_binds_only_loopback_and_opens_tokenized_url(fake_uvicorn, fake_browser):
    launch(project_root=Path("."), port=0)
    assert fake_uvicorn.host == "127.0.0.1"
    assert fake_browser.url.startswith("http://127.0.0.1:")
    assert "token=" in fake_browser.url
```

- [ ] **Step 2: Escribir E2E RED**

```ts
test('TXT to blocked-or-published DGS is fully navigable', async ({ page }) => {
  await page.goto(appUrl)
  await selectFixtureFolder(page, 'complete-three-file-set')
  await page.getByRole('button', { name: /analizar TXT/i }).click()
  await expect(page.getByText(/G1 aprobada/i)).toBeVisible()
  await page.getByRole('link', { name: /unifilar/i }).click()
  await expect(page.locator('[data-cy="network-canvas"]')).toBeVisible()
  await page.getByRole('link', { name: /evidencias/i }).click()
  await expect(page.getByText(/hash sha-256/i)).toBeVisible()
})
```

- [ ] **Step 3: Implementar build y launcher**

`scripts/build-web.ps1` ejecuta `npm ci`, tests, typecheck, build y copia `web/dist` a package data. El launcher sirve SPA fallback, tokeniza URL, abre browser y maneja SIGINT/cierre. `run_gui.bat` invoca web; `run_tkinter.bat` conserva GUI anterior.

- [ ] **Step 4: Ejecutar aceptación local completa**

Run: `powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`  
Run: `npm --prefix web run e2e`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/acceptance.ps1 -InputDir referencia -OutputDir output\web_acceptance_final`

Expected: gates de software PASS; si faltan TXT reales, aceptación reporta `blocked/G1/INPUT_TXT_MISSING` y `powerfactory_executed=false`, nunca un PASS artificial.

- [ ] **Step 5: Verificación manual real cuando existan TXT**

Registrar hashes, conteos, revisión, DGS publicado, importación, segunda ejecución idempotente, G5, flujo original, copia diagnóstica y G6. No cerrar esta evidencia como PASS mientras el conjunto real no exista.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/web pyproject.toml run_gui.bat run_tkinter.bat scripts web/e2e tests/test_web_launcher.py README.md docs/OPERATIONS_RUNBOOK.md CODIGO_FUENTE.md
git commit -m "feat: ship offline local React grid cockpit"
```

## Final Verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
npm --prefix web run e2e
powershell -ExecutionPolicy Bypass -File scripts/acceptance.ps1 -InputDir referencia -OutputDir output\web_acceptance_final
git status --short
```

Entrega de software completa exige bootstrap, Python, frontend y Playwright verdes; árbol Git limpio; ningún import web del batch heredado; recursos offline; y aceptación controlada. Aceptación eléctrica real exige adicionalmente TXT coherentes y ejecución PowerFactory con evidencia; si faltan, se informa bloqueada y no se degrada ninguna puerta.
