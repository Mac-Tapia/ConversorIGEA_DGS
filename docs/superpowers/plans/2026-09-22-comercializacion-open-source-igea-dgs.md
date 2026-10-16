# Comercialización con licencia open source — IGEA/CYMDIST → DGS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir el conversor en un producto vendible manteniendo el código bajo licencia open source: eliminar el coste cuadrático que hoy lo hace inviable a escala urbana, cerrar los defectos que producen resultados falsos con sello de válido, y construir la capa legal, de empaquetado, soporte y gobierno que permite facturar sobre un repositorio abierto.

**Modelo de licencia recomendado:** **AGPL-3.0-or-later + excepción de enlace con PowerFactory + CLA + licencia comercial dual**. La justificación y la alternativa están en la Task 0; la decisión es reversible **solo en una dirección** (ver §Decisión de licencia).

**Architecture:** No se reescribe nada. Este plan opera sobre tres ejes independientes que pueden avanzar en paralelo: (1) rendimiento y corrección en `dgs.py`/`validate.py`/`model.py`, cambios locales y medibles; (2) capa legal y de gobierno, que son ficheros nuevos en la raíz y no tocan código; (3) empaquetado, soporte y CI, que envuelven el motor sin modificar su lógica. La frontera de proceso que ya existe entre el paquete y la API propietaria de PowerFactory (`gui.py:852` lanza `subprocess`, y `import powerfactory` vive solo en `tools/powerfactory_acceptance.py:128`) es la que hace viable el copyleft y **debe preservarse como invariante arquitectónico**.

**Tech Stack:** Python 3.10–3.13 (matriz de CI), stdlib + `pyproj` (MIT), PyInstaller, GitHub Actions, `ruff`, `pyright`, `pytest` + `pytest-cov`, `reuse` (SPDX), `pip-audit`, Inno Setup o WiX para el instalador Windows, firma de código Authenticode.

**Diagnósticos de referencia:**
- `docs/DIAGNOSTICO_BACKEND_FRONTEND_2026-09-22.md` — origen de los hallazgos C-01…C-12, F-01…F-08, K-01…K-20, B-01…B-06.
- `docs/DIAGNOSTICO_TECNICO_2026-09-21.md` — hallazgos de fidelidad física.

**Plan complementario (no duplicar):** `docs/superpowers/plans/2026-09-21-robustecimiento-integral-igea-dgs.md` ya cubre 17 tareas de fidelidad eléctrica, parser estricto, política de longitudes, publicación atómica y seguridad de exportaciones. Este plan **no repite ninguna de ellas**; la §Trazabilidad indica qué hallazgo pertenece a qué plan.

---

## Global Constraints

- El motor conserva su comportamiento observable: los 84 tests existentes deben seguir pasando sin modificarse, salvo los que se añadan.
- Ningún cambio de rendimiento puede alterar un solo byte del `.dgs` producido. Se verifica por comparación binaria, no por conteos.
- **El paquete `igea_dgs` nunca importa `powerfactory`.** Toda interacción con la API propietaria ocurre en un proceso separado. Es un invariante de licencia, no de estilo.
- No se abre el repositorio al público hasta completar la Task 5 (saneamiento de datos de la distribuidora). Abrirlo antes es irreversible.
- El CLA debe estar en vigor **antes** de aceptar la primera contribución externa. Retroactivarlo exige localizar a cada contribuyente.
- Se mantiene un único árbol de código. No hay *open core* con directorios cerrados: la separación comercial es por servicio y por datos, no por código oculto.
- Windows es la plataforma de producto; Linux se mantiene en CI para disciplina de portabilidad, no como plataforma soportada.
- Ningún dato identificable de una distribuidora entra en el repositorio, ni en tests, ni en *fixtures*, ni en documentación.

## Review Focus

- **Regresión silenciosa de rendimiento:** un refactor futuro que vuelva a llamar a `_line_neighbors` dentro de un bucle debe hacer fallar CI, no solo ralentizarla. Se prueba en Task 1 Step 5.
- **Equivalencia binaria tras optimizar:** el riesgo de memoizar es servir una adyacencia obsoleta tras mutar `model.lines` (lo que `apply_georeferenced_lengths` hace). Se prueba en Task 1 Step 3.
- **Contaminación de licencia:** cualquier `import powerfactory` que aparezca dentro de `src/igea_dgs/` invalida la estrategia legal. Se prueba en Task 6 Step 1.
- **Fuga de datos de utility:** un `git add -A` no debe poder publicar nada de `referencia/`. Se prueba en Task 5 Step 2.
- **Instalación real:** la GUI resuelve recursos por ruta relativa al árbol de fuentes; instalada como *wheel* se rompe en silencio. Se prueba en Task 7 Step 1.

---

## Decisión de licencia

### El argumento decisivo: la irreversibilidad

Las dos opciones no son simétricas en el tiempo.

- Si se publica hoy bajo **Apache-2.0** y mañana se quiere apalancamiento comercial, **no se puede recuperar**: la versión permisiva ya está distribuida y cualquiera puede continuarla desde ahí.
- Si se publica hoy bajo **AGPL-3.0 con CLA** y mañana se decide que el copyleft estorba a la adopción, **se puede relicenciar a Apache-2.0 en cualquier momento**, porque el CLA concentra los derechos necesarios.

AGPL-3.0 + CLA es por tanto la opción que **preserva ambas estrategias**. Apache-2.0 cierra una de ellas de forma permanente. Con un producto cuyo modelo de negocio todavía no está validado, esa asimetría decide.

### Recomendación

| Componente | Licencia | Razón |
| --- | --- | --- |
| `src/igea_dgs/` (motor, CLI, GUI) | **AGPL-3.0-or-later** + excepción PowerFactory | Copyleft fuerte con apalancamiento sobre quien lo redistribuya o lo ofrezca como servicio |
| `src/igea_dgs/schemas/*.json` (perfil DGS) | **CC0-1.0** o Apache-2.0 | Es un contrato de formato; su valor es que todos lo adopten, no que nadie lo copie |
| `tools/powerfactory_acceptance.py` → `src/igea_dgs/powerfactory/` | **Apache-2.0** | Es el adaptador que enlaza con la API propietaria; mantenerlo permisivo elimina toda ambigüedad legal |
| Perfiles regionales validados, catálogos, casos dorados | **Propietario, no en el repo** | Es el producto de pago (ver §Modelo de ingresos) |
| Licencia comercial alternativa | **Propietaria, de pago** | Quien no puede cumplir AGPL compra la excepción |

### La excepción de enlace: el punto que hay que resolver antes de publicar

AGPL-3.0 exige que la obra combinada se distribuya bajo AGPL. `powerfactory.pyd` es propietario y no lo permite. Si el paquete AGPL importara ese módulo, **distribuir el conjunto sería una violación de la propia licencia**, y el infractor sería el proyecto.

La arquitectura actual ya evita el problema por accidente afortunado, y hay que convertirlo en decisión explícita:

- `gui.py:852` invoca la aceptación mediante `subprocess.run(...)`: procesos separados, comunicación por línea de comandos y stdout.
- `import powerfactory` aparece **una sola vez**, en `tools/powerfactory_acceptance.py:128`, y de forma diferida dentro de una función.

Tres medidas convierten esto en una posición defendible:

1. Añadir al `LICENSE` una **excepción de enlace explícita** que autorice combinar y distribuir la obra con la API de DIgSILENT PowerFactory y sus bibliotecas.
2. Licenciar el adaptador de PowerFactory bajo **Apache-2.0**, no AGPL.
3. Un test que **prohíba** `import powerfactory` dentro de `src/igea_dgs/` (Task 6).

### Alternativa, si se prioriza adopción sobre apalancamiento

**Apache-2.0 en todo el repositorio.** Elimina la fricción con departamentos legales de utilities, hace irrelevante la excepción de enlace y acelera la adopción académica. Se monetiza solo con servicios, datos y certificación. Es una decisión válida, pero **hay que tomarla sabiendo que no tiene marcha atrás**. Si se elige esta vía: la Task 4 se simplifica (sin CLA obligatorio, basta DCO), la Task 6 Step 1 deja de ser un requisito legal y pasa a ser higiene, y el §Modelo de ingresos pierde la línea de licencia dual.

---

## Modelo de ingresos sobre un repositorio abierto

El código es ~5.400 líneas: no es el activo defendible. Lo defendible es lo que rodea a la conversión. Cinco líneas de ingreso, ordenadas por cercanía a caja:

| # | Producto | Por qué se paga | Depende de |
| --- | --- | --- | --- |
| 1 | **Soporte y SLA** | Una distribuidora no despliega una herramienta de planificación sin alguien a quien reclamar | Task 10 (log y paquete de diagnóstico: sin esto no hay soporte posible) |
| 2 | **Perfiles regionales validados** | 50 Hz, BT 0,4 kV, grupos de conexión, catálogos de conductores por país. Cada perfil es trabajo de ingeniería, no de código | Task 13 |
| 3 | **Certificación de modelo** | Informe firmado de que el DGS entregado es fiel al origen dentro de tolerancias declaradas. Es lo que la utility necesita para usarlo en decisiones reales | Plan 21-09, Tasks 11/16/17 |
| 4 | **Instalador firmado y despliegue** | El binario firmado, probado contra una versión concreta de PowerFactory, con instalación desatendida | Tasks 7, 8, 12 |
| 5 | **Licencia comercial dual** | Consultoras y vendedores de software que quieren integrarlo en su propia herramienta cerrada | Task 4 (CLA) |

Las líneas 1–4 funcionan con cualquier licencia. La 5 **solo existe si se elige copyleft con CLA**, y es la única que escala sin consumir horas.

---

## File Structure

### Nuevos ficheros en raíz (capa legal y de gobierno)

- `LICENSE` — AGPL-3.0-or-later + excepción PowerFactory.
- `LICENSES/` — textos SPDX de cada licencia usada (convención `reuse`).
- `NOTICE` — atribuciones de terceros.
- `COMMERCIAL-LICENSE.md` — términos y contacto de la licencia dual.
- `CLA.md` + `.github/cla-assistant.yml` — acuerdo de contribución.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`.
- `.github/workflows/ci.yml`, `release.yml`; `.github/ISSUE_TEMPLATE/`, `PULL_REQUEST_TEMPLATE.md`.
- `THIRD-PARTY-LICENSES.md` — generado, no escrito a mano.

### Nuevos módulos

- `src/igea_dgs/diagnostics/` — `run_id`, *logging* estructurado, paquete de soporte.
- `src/igea_dgs/powerfactory/` — adaptador Apache-2.0, migrado desde `tools/`.
- `src/igea_dgs/resources.py` — resolución de recursos con `importlib.resources`, sustituye a `_project_root()`.
- `src/igea_dgs/profiles/` — perfiles de red regionales (`frnom`, BT, grupo de conexión, escala de diagrama).
- `packaging/` — `igea-dgs.spec` (PyInstaller), `installer.iss`, scripts de firma.
- `docs/manual-operador.md` — documentación de usuario final, no de desarrollador.

### Ficheros de rendimiento (Fase A)

- Modify: `src/igea_dgs/dgs.py`, `src/igea_dgs/validate.py`, `src/igea_dgs/dataset.py`, `src/igea_dgs/model.py`, `src/igea_dgs/batch.py`.
- Create: `tests/test_performance_budget.py`, `tests/test_dgs_byte_equivalence.py`.

---

# FASE A — Rendimiento y corrección

> Prioridad absoluta. La Task 1 es ~2 h de trabajo y produce 21,6× de mejora. Nada en este plan tiene mejor relación valor/coste.

### Task 1: Eliminar el coste cuadrático del diagrama y del validador

Cierra: **C-02, B-01, B-02**.

**Files:**
- Modify: `src/igea_dgs/dgs.py`
- Modify: `src/igea_dgs/validate.py`
- Create: `tests/test_performance_budget.py`
- Create: `tests/test_dgs_byte_equivalence.py`

**Interfaces:**
- Produces: `LineNeighborIndex` (adyacencia construida una vez por modelo), `diagram_context(model) -> DiagramContext` con `neighbors` y `drawn_sections` precalculados.
- Consumes: `FeederModel` sin cambios de forma.

- [ ] **Step 1: Capturar la salida actual como referencia binaria**

Antes de optimizar, congelar el resultado. Sin esto no se puede demostrar que la optimización no cambió nada.

```python
def test_dgs_bytes_unchanged_after_optimization(ds, tmp_path, golden_dgs_bytes):
    """El .dgs debe ser idéntico byte a byte antes y después del refactor."""
    model = build_feeder_model(ds, LARGEST_FEEDER, strict=True)
    geography = build_geography(ds, model, source_crs='EPSG:32718')
    out = tmp_path / 'f.dgs'
    write_dgs(model, out, geography=geography)
    assert out.read_bytes() == golden_dgs_bytes
```

- [ ] **Step 2: Escribir el presupuesto de rendimiento y confirmar que falla**

```python
import time

MAX_SECONDS_LARGEST_FEEDER = 3.0  # hoy: ~17 s

def test_largest_feeder_converts_within_budget(ds, tmp_path):
    net = max((k for k, v in ds.feeders.items() if v), key=lambda k: len(ds.feeders[k]))
    start = time.perf_counter()
    model = build_feeder_model(ds, net, strict=True)
    geography = build_geography(ds, model, source_crs='EPSG:32718')
    out = tmp_path / 'f.dgs'
    write_dgs(model, out, geography=geography)
    report = validate_dgs(model, out, geography=geography)
    elapsed = time.perf_counter() - start
    assert report['errors_total'] == 0
    assert elapsed < MAX_SECONDS_LARGEST_FEEDER, f'{elapsed:.1f}s excede el presupuesto'
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_performance_budget.py -v` → debe fallar con ~17 s.

- [ ] **Step 3: Probar la invalidación del índice de adyacencia**

Este es el riesgo real de memoizar: `apply_georeferenced_lengths` **reasigna `model.lines`** (`model.py:823`). Un índice memoizado por `id(model)` servirá datos obsoletos si no se invalida.

```python
def test_neighbor_index_reflects_mutated_lines(model):
    first = diagram_anchor_node(model, some_stub_tip)
    model.lines = [ln for ln in model.lines if ln.section_id != some_stub_section]
    model.section_by_id = {ln.section_id: ln for ln in model.lines}
    assert diagram_anchor_node(model, some_stub_tip) != first
```

- [ ] **Step 4: Implementar**

1. `dgs.py` — construir la adyacencia **una vez** y pasarla explícitamente, en lugar de memoizar por `id()`. Cambiar las firmas hace visible la dependencia y elimina la clase de error del Step 3:
   - `diagram_anchor_node(model, node_id, *, neighbors, max_stub_m=1.0)`
   - `is_micro_service_stub_line(model, line, *, neighbors, max_stub_m=1.0)`
   - `diagram_line_sections(model, *, neighbors=None)` — construye el índice si no lo recibe, para no romper llamadores externos.
2. `dgs.py` — calcular `drawn = diagram_line_sections(...)` **una vez** en `write_dgs` y propagarlo a `visible_pointterm_nodes` y `diagram_line_rail_counts`, que hoy lo recomputan.
3. `validate.py:512` — sustituir el `next((ln for ln in model.lines if _loc(ln.section_id) == name), None)` por un `dict` construido antes del bucle:
   ```python
   line_by_loc = {_loc(ln.section_id): ln for ln in model.lines}
   ```
4. Revisar el resto de `validate.py` en busca del mismo patrón (`_loc` se llama 6,6 M de veces; el `next` explica la mayor parte, no necesariamente todo).

- [ ] **Step 5: Verificar y blindar**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Criterios:
- `84 passed` sin cambios de expectativa.
- `test_dgs_bytes_unchanged_after_optimization` pasa → la optimización es semánticamente neutra.
- Alimentador mayor < 3 s (medido: 0,80 s).
- `test_all_mode_converts_every_feeder_without_blocking` < 40 s (medido: 35 s).
- Suite completa < 70 s (medido: 55 s).

- [ ] **Step 6: Documentar el invariante**

Comentario en `_line_neighbors` y en `diagram_line_sections` explicando que **no deben llamarse dentro de un bucle sobre líneas**, con referencia al presupuesto de la Task 1. El test es la defensa; el comentario evita que alguien lo desactive por «lento en CI».

---

### Task 2: Pre-indexar el dataset por alimentador

Cierra: **B-03, B-04, B-05**.

**Files:**
- Modify: `src/igea_dgs/dataset.py`
- Modify: `src/igea_dgs/model.py`
- Modify: `src/igea_dgs/geography.py`
- Create: `tests/test_dataset_indexes.py`

**Interfaces:**
- Produces: `CymdistDataset.loads_by_feeder`, `.devices_by_feeder`, `.intermediate_by_section`, `.line_catalog` (cacheada), construidos una vez en `from_files`.

- [ ] **Step 1: Probar que el coste del lote es lineal en alimentadores**

```python
def test_per_feeder_cost_does_not_scan_whole_dataset(ds):
    """Construir el modelo de 1 alimentador no debe recorrer las 37.283 filas
    de INTERMEDIATE NODES ni las 7.287 cargas del export completo."""
    small = min((k for k, v in ds.feeders.items() if v), key=lambda k: len(ds.feeders[k]))
    with count_iterations(ds, 'intermediate_nodes') as counter:
        build_feeder_model(ds, small, strict=False)
    assert counter.value < 10 * len(ds.feeders[small])
```

- [ ] **Step 2: Implementar los índices en `from_files`**

Construir en la lectura, no por alimentador:
- `intermediate_by_section: dict[str, tuple[dict, ...]]`
- `loads_by_feeder: dict[str, tuple[tuple[str, str], ...]]` usando `section_owner`
- `devices_by_feeder: dict[str, tuple[tuple[str, dict], ...]]` para `SWITCH` y `SECTIONALIZER`
- `line_catalog` — resultado de `_catalog(dataset)` cacheado

Sustituir en `model.py:680` (`for key, row in dataset.customer_loads.items()`), `model.py:736-737` (barrido de maniobras) y `geography.py:117` (*bucketing* duplicado).

- [ ] **Step 3: Eliminar la rama O(S·I) latente**

`model.py:420` escanea `dataset.intermediate_nodes` por sección cuando no recibe el índice. Hoy ningún llamador la activa, pero es una trampa. Hacer el índice obligatorio en la firma.

- [ ] **Step 4: Verificar**

Run: `.\.venv\Scripts\python.exe -m pytest -q`. El lote de 96 debe bajar de ~35 s a ~30 s (la ganancia esperada es ~2 s de barridos, modesta frente a la Task 1). Equivalencia binaria intacta.

---

### Task 3: Paralelizar el modo `--all`

Cierra: **B-06**. Depende de Task 1 y de la publicación atómica (plan 21-09, Task 10).

**Files:**
- Modify: `src/igea_dgs/batch.py`
- Modify: `src/igea_dgs/cli.py`
- Create: `tests/test_batch_parallel.py`

- [ ] **Step 1: Probar equivalencia entre secuencial y paralelo**

```python
def test_parallel_batch_produces_identical_artifacts(ds, tmp_path):
    seq = convert_selection(ds, None, tmp_path / 'seq', all_feeders=True, workers=1)
    par = convert_selection(ds, None, tmp_path / 'par', all_feeders=True, workers=4)
    assert seq['summary'] == par['summary']
    for item in seq['feeders']:
        if item['status'] != 'ok':
            continue
        a = (tmp_path / 'seq' / f"{item['feeder']}.dgs").read_bytes()
        b = (tmp_path / 'par' / f"{item['feeder']}.dgs").read_bytes()
        assert a == b, item['feeder']
```

- [ ] **Step 2: Implementar `workers` con `ProcessPoolExecutor`**

- `workers: int = 1` por defecto; `--workers N` en el CLI; `os.cpu_count()` como máximo sugerido en la GUI.
- El `dataset` no es serializable de forma eficiente: pasar las rutas y reconstruirlo por proceso, o usar `fork`/`spawn` con inicializador que lea una vez.
- El manifiesto se ensambla en el proceso padre para preservar el orden determinista.
- La cancelación (Task 14) debe propagarse a los procesos hijos.

- [ ] **Step 3: Verificar**

Determinismo del manifiesto y equivalencia binaria con `workers=1` y `workers=4`.

---

# FASE B — Licencia y gobierno

> Se puede ejecutar en paralelo a la Fase A: son ficheros nuevos que no tocan el motor. **La Task 5 bloquea la apertura del repositorio.**

### Task 0: Decidir el modelo de licencia

- [ ] **Step 1: Resolver la decisión de §Decisión de licencia**

Salida esperada: una nota de una página en `docs/adr/0001-modelo-de-licencia.md` que registre la opción elegida, la fecha, quién decide y el razonamiento. Sin este registro, la decisión se reabrirá cada trimestre.

- [ ] **Step 2: Confirmar la titularidad del copyright**

Verificar que no hay código de terceros sin atribución, ni fragmentos de documentación de DIgSILENT, ni código derivado de CYMDIST en el repositorio. El perfil `pf21_dgs_1_8_4.json` describe un formato propietario: confirmar que contiene únicamente nombres de tablas y campos (hecho observable: no contiene datos de red), y documentar que fue obtenido por observación del formato, no copiado de documentación licenciada.

Este paso es aburrido y es el que detiene una operación si se omite.

---

### Task 4: Publicar la capa legal

Cierra: **K-01, K-04, K-05, C-07 (parte legal)**.

**Files:**
- Create: `LICENSE`, `LICENSES/AGPL-3.0-or-later.txt`, `LICENSES/Apache-2.0.txt`
- Create: `NOTICE`, `COMMERCIAL-LICENSE.md`, `CLA.md`, `CHANGELOG.md`
- Create: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`
- Create: `.github/cla-assistant.yml`, `.github/ISSUE_TEMPLATE/bug.yml`, `.github/PULL_REQUEST_TEMPLATE.md`
- Modify: `pyproject.toml` (campo `license`, clasificadores), todos los `*.py` (cabecera SPDX)
- Create: `tests/test_license_headers.py`

**Interfaces:**
- Produces: repositorio conforme a la especificación REUSE, verificable con `reuse lint`.

- [ ] **Step 1: Probar la conformidad de licencia**

```python
def test_every_source_file_declares_its_license():
    missing = [
        p for p in Path('src').rglob('*.py')
        if 'SPDX-License-Identifier:' not in p.read_text(encoding='utf-8')[:512]
    ]
    assert not missing, missing


def test_powerfactory_adapter_is_permissive():
    header = Path('src/igea_dgs/powerfactory/__init__.py').read_text(encoding='utf-8')[:512]
    assert 'SPDX-License-Identifier: Apache-2.0' in header
```

- [ ] **Step 2: Escribir `LICENSE` con la excepción de enlace**

Texto AGPL-3.0 íntegro, más una excepción adicional al final, en la línea de:

> Additional permission under GNU AGPL version 3 section 7: If you modify this Program, or any covered work, by linking or combining it with the DIgSILENT PowerFactory Python API and its associated libraries (or a modified version of those libraries), the licensors of this Program grant you additional permission to convey the resulting work.

El texto definitivo debe revisarlo un abogado. La redacción de arriba sigue el patrón habitual de excepción OpenSSL y es un punto de partida, no un dictamen.

- [ ] **Step 3: Escribir `COMMERCIAL-LICENSE.md`**

Qué incluye la licencia comercial (derecho a redistribuir sin publicar modificaciones, soporte, indemnización), qué no, y cómo contratarla. Sin precios en el repositorio; solo el canal.

- [ ] **Step 4: Instalar el CLA**

`CLA.md` basado en Apache ICLA/CCLA, más `cla-assistant` en el workflow de PR. **Requisito temporal: activo antes del primer PR externo.**

- [ ] **Step 5: Semver y CHANGELOG**

Declarar la política: `MAJOR` para cambios incompatibles del `.dgs` o del CLI; `MINOR` para tablas/campos nuevos del perfil; `PATCH` para correcciones. `CHANGELOG.md` en formato *Keep a Changelog*. Versión única en `src/igea_dgs/__init__.py`, leída por `pyproject.toml` con `dynamic = ["version"]` — hoy está duplicada en ambos.

- [ ] **Step 6: Verificar**

Run: `reuse lint` y `.\.venv\Scripts\python.exe -m pytest tests/test_license_headers.py -v`.

---

### Task 5: Saneamiento del dato y del historial — BLOQUEA LA APERTURA

Cierra: **K-14, C-11**.

**Files:**
- Modify: `.gitignore`
- Create: `scripts/check_no_utility_data.py`
- Create: `.github/workflows/data-guard.yml`
- Create: `tests/test_no_utility_data_tracked.py`

**Interfaces:**
- Produces: una puerta que rechaza cualquier *commit* con datos identificables de distribuidora.

- [ ] **Step 1: Auditar el historial completo**

```bash
git log --all --numstat --format='%H' -- referencia/ | head -100
git rev-list --all --objects -- referencia/ | head -50
```

Buscar en todo el historial, no solo en `HEAD`. Si algún `RED_*.txt`, `CARGA_*.txt`, `BD_Equipo*.txt`, `*.dgs` de producción o `audit_ternas_*.json` fue *commiteado* alguna vez, **el historial debe reescribirse con `git filter-repo` antes de abrir el repositorio**. Publicar y luego borrar no sirve: los objetos quedan accesibles y los *forks* los conservan.

- [ ] **Step 2: Probar la puerta de datos**

```python
def test_no_utility_data_is_tracked():
    tracked = subprocess.run(['git', 'ls-files'], capture_output=True, text=True).stdout.split()
    forbidden = [
        f for f in tracked
        if f.startswith('referencia/') and not f.endswith(('.md', '.example.json'))
    ]
    assert not forbidden, f'Datos de distribuidora versionados: {forbidden}'
```

Hoy este test pasaría, pero `referencia/audit_ternas_{backbone,classified,ug}.json` (56 KB con identificadores reales: `IN110`, `SEC_2010_1146990_SE42147`) están **sin ignorar**, de modo que un `git add -A` los versionaría. La `.gitignore` actual solo cubre los tres patrones de TXT.

- [ ] **Step 3: Endurecer `.gitignore`**

Invertir la política: ignorar `referencia/*` completo y permitir explícitamente lo que deba versionarse.

```gitignore
referencia/*
!referencia/README.md
!referencia/*.example.json
```

- [ ] **Step 4: Anonimizar los *fixtures* de test**

Los 84 tests dependen hoy de los TXT reales vía `IGEA_RED`/`IGEA_LOADS`/`IGEA_EQUIPMENT` y hacen *skip* sin ellos. Un proyecto open source necesita un *fixture* sintético versionable: un generador que produzca un export CYMDIST pequeño (~50 secciones, 3 alimentadores, topología con doble circuito, un tramo monofásico, una SED) con identificadores inventados. Sin esto, ningún contribuyente externo puede ejecutar la suite útil, y CI solo prueba las 46 pruebas independientes de datos.

Es la tarea con más trabajo real de esta fase y la que decide si el proyecto es contribuible.

- [ ] **Step 5: Revisar `tools/_publish_to_github.py`**

Script de publicación presente en el repo, sin seguimiento. Auditar qué sube exactamente y a dónde antes de que alguien lo ejecute. Si no es necesario, eliminarlo.

---

### Task 6: Aislar la API propietaria y auditar terceros

Cierra: **K-03 (parte legal), invariante de licencia**.

**Files:**
- Create: `src/igea_dgs/powerfactory/__init__.py`, `adapter.py`, `acceptance.py`
- Modify: `tools/powerfactory_acceptance.py` → entrada delgada de compatibilidad
- Create: `THIRD-PARTY-LICENSES.md` (generado)
- Create: `tests/test_license_isolation.py`

- [ ] **Step 1: Probar el aislamiento (test de licencia, no de estilo)**

```python
def test_engine_never_imports_proprietary_api():
    """AGPL + powerfactory.pyd propietario = violación de licencia al distribuir.
    El motor solo puede hablar con PowerFactory por proceso separado."""
    offenders = []
    for path in Path('src/igea_dgs').rglob('*.py'):
        if 'powerfactory' in path.parts:
            continue  # el adaptador Apache-2.0 sí puede
        source = path.read_text(encoding='utf-8')
        if re.search(r'^\s*import powerfactory|^\s*from powerfactory', source, re.M):
            offenders.append(str(path))
    assert not offenders, f'Importación propietaria en código AGPL: {offenders}'
```

- [ ] **Step 2: Migrar el adaptador**

Mover `tools/powerfactory_acceptance.py` (97 KB) a `src/igea_dgs/powerfactory/` con cabecera Apache-2.0, dejando en `tools/` una entrada que delega. Preserva la frontera de proceso actual (`gui.py:852` sigue usando `subprocess`) y a la vez resuelve K-03, porque el adaptador pasa a estar empaquetado.

Nota: el plan 21-09 Task 12 ya prevé el puerto `igea_dgs.powerfactory`. Coordinar para no migrar dos veces; si esa tarea va primero, esta se reduce a fijar la licencia y el test.

- [ ] **Step 3: Generar el inventario de terceros**

`pip-licenses` o `reuse` sobre el árbol de dependencias. Estado conocido: `pyproj` es **MIT** (verificado: `License-Expression: MIT`), compatible con AGPL. Los extras `[xlsx]` (pandas BSD-3, openpyxl MIT) y `[preview]` (geopandas BSD-3, leafmap MIT) también. Ninguna incompatibilidad detectada; el inventario debe automatizarse para que siga siendo cierto.

- [ ] **Step 4: Verificar**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_license_isolation.py -v` y `pip-audit`.

---

# FASE C — Empaquetado y distribución

### Task 7: Resolver recursos sin depender del árbol de fuentes

Cierra: **F-04, K-03**.

**Files:**
- Create: `src/igea_dgs/resources.py`
- Modify: `src/igea_dgs/gui.py` (eliminar `_project_root`, `_referencia_dir`, `_default_referencia_inputs`)
- Modify: `pyproject.toml` (`package-data`)
- Create: `tests/test_installed_layout.py`

- [ ] **Step 1: Probar la instalación como wheel**

```python
def test_gui_resources_resolve_when_installed_as_wheel(tmp_path, built_wheel):
    """_project_root() = parents[2] asume <raíz>/src/igea_dgs/.
    Instalado en site-packages apunta fuera del paquete."""
    venv = make_venv(tmp_path)
    venv.pip_install(built_wheel)
    result = venv.run_python('-c', 'from igea_dgs.resources import acceptance_script, default_aliases;'
                                  'print(acceptance_script().is_file(), default_aliases() is not None)')
    assert 'True True' in result.stdout
```

- [ ] **Step 2: Implementar `resources.py`**

`importlib.resources.files('igea_dgs')` para el esquema, el adaptador de PowerFactory, los perfiles regionales y la plantilla de aliases. Empaquetar `config/` y los perfiles como `package-data`.

- [ ] **Step 3: Eliminar el prefill de `referencia/` (F-05)**

`_default_referencia_inputs` rellena los tres campos con los TXT del repo. En producto es un riesgo: el operador puede convertir el export de otra empresa sin notarlo. Sustituir por campos vacíos y, si se quiere conveniencia, por las últimas rutas de la sesión anterior (Task 14).

- [ ] **Step 4: Verificar**

Construir el *wheel*, instalarlo en un venv limpio y ejecutar una conversión y el botón de PowerFactory.

---

### Task 8: Instalador firmado para Windows

Cierra: **K-02, C-07 (parte técnica)**.

**Files:**
- Create: `packaging/igea-dgs.spec`, `packaging/installer.iss`, `packaging/sign.ps1`
- Create: `.github/workflows/release.yml`
- Create: `docs/instalacion.md`

- [ ] **Step 1: Empaquetar con PyInstaller en modo *onedir***

El punto delicado es `pyproj`: necesita los datos de PROJ (`proj.db`), que PyInstaller no recoge solo. Añadir el *hook* correspondiente y verificar que la transformación de CRS funciona en la máquina destino sin `PROJ_DATA` en el entorno.

- [ ] **Step 2: Probar el binario en una máquina sin Python**

Criterio de aceptación: instalar en Windows limpio (sin Python, sin `pip`), abrir la GUI, cargar tres TXT, convertir un alimentador con georreferenciación y ejecutar el flujo de PowerFactory. Es la prueba que hoy falla por F-04.

- [ ] **Step 3: Firmar**

Certificado Authenticode para el `.exe` y el instalador. Sin firma, SmartScreen bloquea la instalación y el departamento de TI de una utility la rechaza. Es un coste anual pequeño y un bloqueo comercial absoluto.

- [ ] **Step 4: Automatizar en `release.yml`**

*Tag* → construir *wheel* + instalador → firmar → publicar en GitHub Releases con `CHANGELOG` y SHA-256.

---

### Task 9: Documentación de operador

Cierra: **K-11**.

**Files:**
- Create: `docs/manual-operador.md`, `docs/instalacion.md`, `docs/solucion-de-problemas.md`
- Modify: `README.md`

- [ ] **Step 1: Reescribir el README para dos audiencias**

El README actual es una guía de desarrollador: `PYTHONPATH=src`, `pip install -e .`, rutas del repo. Separar: una sección de usuario (descargar el instalador, abrir, convertir) y una de desarrollador (clonar, venv, tests). Un cliente no debe encontrarse `set PYTHONPATH=src` en la primera pantalla.

- [ ] **Step 2: Manual de operador**

Flujo completo con capturas, qué significa cada casilla, **qué CRS elegir y por qué importa** (con la advertencia explícita sobre CRS no métricos), cómo leer el informe de validación, qué hacer ante cada error frecuente.

- [ ] **Step 3: Documentar los supuestos del modelo**

Página honesta que enumere qué se sintetiza y qué no: transformadores SED, `frnom`, BT, grupo de conexión, fases, `B1/B0`, cortocircuito de fuente. Un cliente que descubre esto después de comprar es una devolución; uno que lo lee antes es un cliente informado. Esta página es, además, el argumento de venta de los perfiles validados (Task 13).

---

# FASE D — Soporte y calidad de construcción

### Task 10: Trazabilidad y paquete de diagnóstico

Cierra: **K-06, K-07, F-03, C-09**.

**Files:**
- Create: `src/igea_dgs/diagnostics/__init__.py`, `logging.py`, `support_bundle.py`
- Modify: `src/igea_dgs/batch.py`, `cli.py`, `gui.py`
- Create: `tests/test_diagnostics.py`

**Interfaces:**
- Produces: `configure_logging(run_id)`, `RunContext` (`run_id`, versiones, hashes), `build_support_bundle(out) -> Path`.

- [ ] **Step 1: Probar que el manifiesto es reproducible y auditable**

```python
def test_manifest_records_provenance(ds, tmp_path):
    manifest = convert_selection(ds, ['F1'], tmp_path)
    assert re.fullmatch(r'[0-9a-f]{32}', manifest['run_id'])
    env = manifest['environment']
    assert env['igea_dgs_version'] and env['python_version'] and env['pyproj_version']
    assert env['schema_profile'] == 'pf21_dgs_1_8_4'
    for key in ('red', 'loads', 'equipment'):
        assert re.fullmatch(r'[0-9a-f]{64}', manifest['inputs'][key]['sha256'])
```

- [ ] **Step 2: Logging estructurado a fichero**

`logging` con `run_id` en cada registro, a `%LOCALAPPDATA%/igea-dgs/logs/` con rotación. La GUI conecta un `Handler` que vuelca al widget: un solo flujo, dos destinos. Hoy el Registro de la GUI vive solo en memoria y se borra al cerrar (`gui.py:527`), lo que hace imposible el soporte.

- [ ] **Step 3: Enriquecer el manifiesto**

`run_id`, versión del paquete, Python, `pyproj`, perfil de esquema, SHA-256 de los tres TXT, tiempos por etapa y por alimentador, `workers`, política de imputación aplicada, avisos por alimentador.

Coordinar con el plan 21-09 Task 10 (`RunManifest`, `sha256_file`), que define estructuras equivalentes. Si esa tarea va primero, esta se reduce al *logging* y al paquete de soporte.

- [ ] **Step 4: Botón «Exportar diagnóstico»**

ZIP con log, manifiesto, inventario, versiones y entorno — **sin los TXT de entrada** (son datos del cliente). Es lo que se pide al abrir una incidencia.

- [ ] **Step 5: Escribir el manifiesto siempre**

`batch_manifest.json` se escribe hoy en `batch.py:234`, fuera de `try`. Moverlo a un `finally` con los ítems procesados y `status: 'cancelled'` o `'crashed'`. Un lote sin manifiesto es un lote sin traza.

---

### Task 11: Integración continua

Cierra: **K-10, C-12**.

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `ruff.toml`, `pyrightconfig.json`, `constraints.txt`
- Modify: `requirements-dev.txt`, `pyproject.toml`

- [ ] **Step 1: Declarar las herramientas que faltan**

`requirements-dev.txt` contiene hoy solo `pytest`. Añadir `ruff`, `pyright`, `pytest-cov`, `pip-audit`, `reuse`. El diagnóstico del 21-09 ya registró que `ruff` no era ejecutable por no estar declarado; sigue sin estarlo.

- [ ] **Step 2: Fijar la versión mínima real de Python**

`requires-python = ">=3.10"` pero el `.venv` corre **3.14.4** y nada prueba 3.10. Decidir y probar: matriz `3.10, 3.11, 3.12, 3.13` en CI, o subir el mínimo a lo que realmente se soporta. Declarar soporte de una versión sin probarla es una promesa que se rompe en casa del cliente.

- [ ] **Step 3: `ci.yml`**

```yaml
# ejes: windows-latest (producto) + ubuntu-latest (disciplina)
# python: 3.10 … 3.13
# pasos: ruff check · ruff format --check · pyright · reuse lint · pip-audit
#        pytest -q --cov=igea_dgs --cov-branch --cov-fail-under=<umbral>
#        pytest tests/test_performance_budget.py   <-- la defensa de la Task 1
#        pytest tests/test_license_isolation.py    <-- la defensa de la Task 6
#        pytest tests/test_no_utility_data_tracked.py
```

El *fixture* sintético de la Task 5 Step 4 es lo que permite que CI ejecute la suite completa sin datos de cliente.

- [ ] **Step 4: Fijar el umbral de cobertura al valor medido**

Medir primero, fijar el umbral justo por debajo, subirlo por tareas. Un umbral aspiracional se desactiva en la primera urgencia.

- [ ] **Step 5: Lockfile**

`constraints.txt` con versiones y hashes para construcciones reproducibles del instalador. `pyproject.toml` conserva los rangos.

---

# FASE E — Producto internacional

### Task 12: Perfil de red parametrizado

Cierra: **§3.3 del diagnóstico (`frnom`, BT, grupo de conexión, escala)**. Es la tarea que abre mercados.

**Files:**
- Create: `src/igea_dgs/profiles/__init__.py`, `network_profile.py`
- Create: `src/igea_dgs/profiles/pe_60hz_022kv.json`, `generic_50hz_04kv.json`
- Modify: `src/igea_dgs/dgs.py`, `cli.py`, `gui.py`
- Create: `tests/test_network_profile.py`

**Interfaces:**
- Produces: `NetworkProfile` con `frnom`, `lv_kv`, `vector_group`, `uk_pct`, `diagram_units_per_meter`, y la procedencia de cada valor.

- [ ] **Step 1: Probar que 50 Hz produce 50 Hz**

```python
def test_profile_frequency_reaches_every_dgs_table(ds, tmp_path):
    profile = NetworkProfile.load('generic_50hz_04kv')
    out = tmp_path / 'f.dgs'
    write_dgs(model, out, profile=profile)
    tables = parse_dgs(out)
    for table in ('ElmNet', 'TypLne', 'TypTr2'):
        assert all(row['frnom'] == '50' for row in tables[table]['rows'])


def test_profile_without_declared_lv_voltage_is_rejected():
    with pytest.raises(ProfileError, match='lv_kv'):
        NetworkProfile.from_dict({'frnom': 50})
```

- [ ] **Step 2: Extraer las constantes**

Hoy fijas en `dgs.py`: `frnom=60` (en `ElmNet`, `TypLne`, `TypTr2`), `NA205_SED_LV_KV=0.22`, `uktr=uk0tr=4.0`, `tr2cn_h='D'`/`tr2cn_l='YN'`/`nt2ag=5`, `NA205_DIAGRAM_UNITS_PER_METER=2.08`, `NA205_FEEDER_ICOLOR=11`.

Regla: **sin valor por defecto silencioso**. Si el perfil no declara un parámetro físico, la conversión falla indicando qué falta. El perfil peruano actual se conserva como `pe_60hz_022kv.json` para no romper nada, declarado explícitamente.

- [ ] **Step 3: Renombrar las constantes `NA205_*`**

Son nombres de calibración interna que aparecen en la salida de un producto «universal». Renombrar a términos de dominio (`DIAGRAM_UNITS_PER_METER`, `FEEDER_COLOR`) manteniendo el valor y documentando su origen en el perfil.

- [ ] **Step 4: Exponer el perfil en CLI y GUI**

`--profile` en el CLI; desplegable en la GUI con el perfil mostrado en el resumen de conversión y registrado en el manifiesto.

---

### Task 13: GUI de producto

Cierra: **F-01, F-02, F-05, F-07, K-08**.

**Files:**
- Modify: `src/igea_dgs/gui.py`
- Modify: `src/igea_dgs/batch.py` (soporte de cancelación)
- Create: `tests/test_gui_controller.py`

**Interfaces:**
- Produces: `ConversionController` (sin Tk) con `start`, `cancel`, `is_busy`; `convert_selection(..., cancel: threading.Event | None = None)`.

- [ ] **Step 1: Probar la cancelación en el motor, sin GUI**

```python
def test_cancel_event_stops_batch_without_partial_artifacts(ds, tmp_path):
    cancel = threading.Event()

    def on_progress(nid, i, total):
        if i == 3:
            cancel.set()

    manifest = convert_selection(ds, None, tmp_path, all_feeders=True,
                                 cancel=cancel, on_progress=on_progress)
    assert manifest['summary']['status'] == 'cancelled'
    assert not list(tmp_path.glob('*.dgs.tmp'))
    for item in manifest['feeders']:
        if item['status'] == 'ok':
            assert (tmp_path / f"{item['feeder']}.dgs").exists()
```

- [ ] **Step 2: Cancelación y cierre seguro**

- `threading.Event` consultado en el bucle de `convert_selection`; botón Cancelar habilitado solo durante `_busy`.
- `_on_close` (`gui.py:1107`) debe comprobar `self._busy`, pedir confirmación, señalar la cancelación y **esperar** al hilo antes de `root.destroy()`. Hoy destruye la ventana y el proceso termina, matando el hilo *daemon* a mitad de escritura: `.dgs` truncados indistinguibles de válidos.
- Depende de la escritura atómica (plan 21-09, Task 10) para que la cancelación no deje residuos.

- [ ] **Step 3: Retirar `EPSG:4326` del desplegable de CRS de origen (F-07)**

Es la vía de acceso al defecto C-01: coordenadas en grados medidas con `math.hypot` e interpretadas como metros → factor 110.575× y `errors_total = 0`. La corrección de fondo es la política de longitudes del plan 21-09 Task 6; **retirar la opción del desplegable es la mitigación inmediata** y debe hacerse ya, antes de que exista la política completa.

- [ ] **Step 4: Persistir la sesión**

El checklist del skill de frontend pide persistir las últimas rutas en `%LOCALAPPDATA%/igea-dgs/gui_state.json`; el código hace lo contrario y **borra** el fichero (`_discard_legacy_state`, `gui.py:527`). Reconsiderar en clave de producto: persistir rutas y CRS, con un botón «Nueva sesión» explícito. Si se mantiene el borrado, actualizar el skill para que el checklist no contradiga al código.

- [ ] **Step 5: Extraer el controlador**

`gui.py` son 1.129 líneas sin un solo test. Extraer la lógica (validación de entradas, orquestación, formato de resúmenes) a un controlador sin dependencia de Tk, testeable. La vista queda como cableado de widgets. Coordinar con el plan 21-09 Task 14 («GUI delgada»), que apunta al mismo objetivo desde el lado del servicio.

---

### Task 14: Vista previa sin red y sin inyección

Cierra: **K-13**. (K-12, la inyección HTML, la cubre el plan 21-09 Task 15.)

**Files:**
- Modify: `src/igea_dgs/preview.py`
- Create: `src/igea_dgs/vendor/leaflet/` (Leaflet empotrado)
- Create: `tests/test_preview_offline.py`

- [ ] **Step 1: Probar que el HTML no pide nada a la red**

```python
def test_preview_html_has_no_external_references(model, geography, tmp_path):
    out = write_preview_html(model, geography, tmp_path / 'p.html', backend='leaflet')
    html = out.read_text(encoding='utf-8')
    assert 'unpkg.com' not in html and 'cdn.' not in html
    assert not re.search(r'(src|href)="https?://', html)
```

- [ ] **Step 2: Empotrar Leaflet**

`preview.py:293-294` carga Leaflet desde `unpkg.com` sin `integrity`. Dos problemas: las redes de utilities suelen estar aisladas y la vista previa simplemente no carga; y sin SRI, un CDN comprometido ejecuta código en la máquina del operador. Empotrar Leaflet (BSD-2, compatible) en `vendor/` y declararlo en `THIRD-PARTY-LICENSES.md`. Si se conserva la vía CDN como opción, añadir `integrity` + `crossorigin`.

---

# FASE F — Fidelidad eléctrica (plan 21-09, no duplicar)

Los hallazgos de física siguen su propio plan. Resumen de dependencias, para secuenciar:

| Hallazgo | Tarea propietaria en `2026-09-21-robustecimiento-integral-igea-dgs.md` |
| --- | --- |
| C-01 longitudes y unidades de CRS | Task 6 — `LengthPolicy`, `compare_lengths` |
| C-03 geografía realmente opcional | Task 6 (misma política) |
| C-04 fases extremo a extremo | Task 8 |
| C-05 transformadores SED sintetizados | Tasks 5, 7, 9 |
| C-06 sustitución silenciosa de tipo de línea | Task 5 |
| C-08 publicación atómica | Task 10 |
| C-10 inyección HTML / fórmulas en hojas | Task 15 |
| K-12 escape de identificadores en preview | Task 15 |
| K-15 fórmulas en CSV/XLSX | Task 15 |
| K-16…K-19 contrato de ingestión, `_float`/`_int`, `ValueType` | Tasks 2, 3, 4 |
| `B1/B0`, cortocircuito de fuente | Task 9 |
| Oráculo independiente, casos dorados | Tasks 11, 16, 17 |

**Único solapamiento a resolver:** este plan retira `EPSG:4326` del desplegable (Task 13 Step 3) como mitigación inmediata de C-01, mientras el plan 21-09 Task 6 construye la política completa. Son compatibles: primero se cierra la puerta, después se instala la cerradura.

---

## Trazabilidad: todos los hallazgos tienen dueño

| ID | Hallazgo | Tarea |
| --- | --- | --- |
| C-01 | CRS no métrico corrompe longitudes en silencio | 13.3 (mitigación) + plan 21-09 T6 |
| C-02 | Coste cuadrático | **1** |
| C-03 | `--no-geography` exige coordenadas | plan 21-09 T6 |
| C-04 | Fases ignoradas | plan 21-09 T8 |
| C-05 | Transformadores sintetizados | plan 21-09 T5/T7/T9 |
| C-06 | Sustitución silenciosa de tipo | plan 21-09 T5 |
| C-07 | Sin licencia, sin instalador, GUI no instalable | **4, 7, 8** |
| C-08 | Cierre durante lote trunca ficheros | **13** + plan 21-09 T10 |
| C-09 | Sin log, sin `run_id`, sin hashes | **10** |
| C-10 | Inyección en preview, CDN sin SRI | **14** + plan 21-09 T15 |
| C-11 | Datos de distribuidora sin ignorar | **5** |
| C-12 | Sin CI, lint, tipado, lockfile | **11** |
| F-01 | Sin cancelación | **13** |
| F-02 | Cierre corrompe salida | **13** |
| F-03 | Registro no persistente | **10** |
| F-04 | GUI solo funciona desde fuentes | **7** |
| F-05 | Prefill desde `referencia/` | **7.3** |
| F-06 | Detección frágil de PowerFactory | **7** (vía `resources.py` y registro de Windows) |
| F-07 | `EPSG:4326` en el desplegable | **13.3** |
| F-08 | `gui.py` monolítico sin tests | **13.5** + plan 21-09 T14 |
| K-01 | Sin `LICENSE` | **4** |
| K-02 | Sin instalador | **8** |
| K-03 | Paquete incompleto | **6.2, 7** |
| K-04 | Sin licenciamiento | **4.3** |
| K-05 | Sin semver ni CHANGELOG | **4.5** |
| K-06 | Sin logging a fichero | **10.2** |
| K-07 | Manifiesto sin procedencia | **10.3** |
| K-08 | Sin cancelación ni reanudación | **13.2** |
| K-09 | Sin escritura atómica | plan 21-09 T10 |
| K-10 | Sin CI | **11** |
| K-11 | Sin documentación de operador | **9** |
| K-12 | Inyección HTML | plan 21-09 T15 |
| K-13 | CDN sin SRI ni modo offline | **14** |
| K-14 | Datos de utility sin `.gitignore` | **5** |
| K-15 | Fórmulas en exportaciones | plan 21-09 T15 |
| K-16 | Duplicados sin ubicación | plan 21-09 T3 |
| K-17 | Sobrescritura silenciosa en ingestión | plan 21-09 T3 |
| K-18 | `_float`/`_int` convierten basura en 0 | plan 21-09 T2/T3 |
| K-19 | `Q = 0` silencioso | plan 21-09 T3 |
| K-20 | Colisión aborta el lote completo | **A.1 extra** (ver abajo) |
| B-01 | `_line_neighbors` en bucle | **1** |
| B-02 | Búsqueda lineal en validador | **1** |
| B-03 | Barridos O(F·N) | **2** |
| B-04 | *Bucketing* duplicado | **2** |
| B-05 | Rama O(S·I) latente | **2.3** |
| B-06 | Conversión secuencial | **3** |
| §3.3 | Física fijada a una red | **12** |

**Pendiente suelto — K-20:** `_selection` (`batch.py:56`) lanza `ValueError` por colisión de nombres cortos **antes** del bucle, de modo que un solo choque aborta el lote completo y no se convierte nada. Contradice la regla de dominio 3 del skill de backend. Corrección de ~2 h: desambiguar con `<short>__<hash8(network_id)>` y registrar el aviso en el manifiesto, o fallar solo ese alimentador. Añadir como Step extra de la Task 3, que ya toca `batch.py`.

---

## Cronograma sugerido

| Semana | Fase A (rendimiento) | Fase B (legal) | Fases C/D/E |
| --- | --- | --- | --- |
| 1 | **Task 1** (2 h, 21,6×) · Task 2 | Task 0 · Task 4 | — |
| 2 | Task 3 | **Task 5** (bloquea apertura) · Task 6 | Task 7 |
| 3 | — | — | Task 8 · Task 10 |
| 4 | — | — | Task 11 · Task 9 |
| 5-6 | — | — | Task 12 · Task 13 · Task 14 |

La Fase A y la Fase B no comparten ficheros: pueden avanzar en paralelo sin conflictos de *merge*. La apertura pública del repositorio ocurre al terminar la Task 5, no antes.

## Criterios de salida

Este plan está terminado cuando:

1. El alimentador mayor convierte en < 3 s y el lote de 96 en < 40 s, con presupuesto verificado en CI.
2. El `.dgs` producido es idéntico byte a byte al de antes de optimizar.
3. Un alimentador de 20.000 tramos convierte en < 30 s.
4. `reuse lint` pasa; cada fichero declara su licencia; el motor no importa `powerfactory`.
5. `git ls-files` no contiene ningún dato identificable de distribuidora, y el historial está auditado.
6. La suite completa se ejecuta sin datos de cliente, con *fixture* sintético.
7. El instalador firmado funciona en Windows limpio sin Python, incluido el flujo de PowerFactory.
8. Todo resultado es trazable: `run_id`, hashes, versiones y tiempos en el manifiesto; paquete de diagnóstico exportable.
9. CI en verde en Windows y Linux, Python 3.10–3.13, con lint, tipado, cobertura y auditoría de dependencias.
10. Cancelar o cerrar durante un lote no deja ningún artefacto parcial.
11. Un perfil de 50 Hz produce un DGS de 50 Hz en todas las tablas, y un perfil incompleto es rechazado.
12. La vista previa funciona sin acceso a internet.
13. `LICENSE`, `COMMERCIAL-LICENSE.md`, `CLA.md`, `CHANGELOG.md` y el manual de operador están publicados.

Los criterios de fidelidad eléctrica (fases preservadas, cero sustituciones no aprobadas, oráculo independiente) pertenecen al plan del 21-09 y no se declaran aquí.
