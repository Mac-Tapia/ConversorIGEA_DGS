# Grid Adaptativo y Columna Alimentador Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regenerar el modelo unido NA203–NA205 a escala geográfica de referencia, sin hoja fija por defecto, y dejar en PowerFactory 2024 una columna `Alimentador` verificable para cada carga y fuente, sin perder Trafomix, interruptores, SED ni trazabilidad de origen.

**Architecture:** La identidad del alimentador se origina una sola vez al construir cada `FeederModel`, sobrevive a la combinación y se materializa en un manifiesto JSON enlazado por SHA-256 al DGS. Tras importar el DGS, la compuerta de PowerFactory crea de forma idempotente una Data Extension `p:alimentador`, resuelve cada objeto por una identidad eléctrica compuesta y solo escribe los valores si todos los objetos esperados se resuelven sin ambigüedad. El lienzo adaptativo es el valor predeterminado en backend, CLI y web; A0–A4 siguen disponibles únicamente como modo explícito de impresión.

**Tech Stack:** Python 3.11+, pytest, dataclasses, JSON/SHA-256, FastAPI, React/TypeScript/Vite, API Python de DIgSILENT PowerFactory 2024, DGS 1.8.4.

**Spec:** `docs/superpowers/specs/2026-09-27-grid-adaptativo-y-columna-alimentador-design.md`

## Global Constraints

- Ejecutar este plan de forma nativa y secuencial, como pidió el usuario; no delegar tareas.
- Aplicar TDD en cada cambio: prueba roja observada, implementación mínima, prueba verde y commit acotado.
- No modificar ni sobrescribir `referencia/NA205.dgs` ni las bases MDB fuente.
- Publicar DGS, manifiesto de alimentadores e informes de validación de forma atómica.
- `NetworkID` es la única fuente de verdad de la pertenencia; no inferir por nombre `SE...`, coordenada, cercanía o conectividad posterior.
- El valor visible será la denominación corta (`NA203`, `NA205`); el `NetworkID` completo se conservará en el manifiesto de auditoría.
- La Data Extension debe llamarse internamente `alimentador`, describirse como `Alimentador` y aparecer como `p:alimentador` en la API.
- Clases objetivo: `ElmLod`, `ElmSym` y `ElmXnet`. La aceptación real principal se hace sobre `ElmLod` y `ElmXnet`; `ElmSym` se prueba sintéticamente mientras no exista en NA203–NA205.
- La creación de Data Extensions se ejecutará únicamente con proyecto activo y siempre cerrará con `EndDataExtensionModification`, incluso ante error.
- Antes de tocar Data Extensions, comprobar que el proyecto activo es exactamente el proyecto nuevo creado por la importación del DGS; nunca modificar por accidente otro proyecto abierto.
- `EndDataExtensionModification` puede desactivar el caso de estudio; reactivar caso y escenario antes de ejecutar `ComLdf`.
- Resolver todos los objetos antes de mutar cualquiera. Una fila ausente o ambigua bloquea la asignación y el flujo; no aceptar escritura parcial.
- La vista preferida es `Basic Data`. Como el manual solo garantiza Data Extensions en `Flexible Data`, comprobar la primera en vivo y usar/configurar `Flexible Data` si `Basic Data` no ofrece el atributo.
- No declarar aceptación PowerFactory por pruebas falsas. El cierre requiere importación real en PowerFactory 2024, convergencia y evidencia visual/tabular.
- Fundamentación técnica: el diagrama conserva topología y legibilidad a escala de red; la trazabilidad se preserva como dato explícito. Ver las fuentes científicas y oficiales citadas en la especificación aprobada.

## Review Focus

- Confirmar que ningún valor predeterminado residual (`A0`) reaparece en CLI, workspace, servicio web, frontend o herramienta MDB.
- Revisar que el manifiesto de alimentadores se publique o descarte junto con el DGS, nunca desfasado.
- Revisar que el emparejamiento PowerFactory use clase + nombre + terminal + subestación y que falle ante duplicados.
- Revisar idempotencia: una segunda aceptación no crea otra Data Extension ni altera asignaciones correctas.
- Revisar que el conteo de Trafomix excluidos, maniobras, SED y cargas cierre contra el origen antes de abrir PowerFactory.
- Revisar que la extensión no rompa la activación del escenario ni el flujo de potencia.

---

## Task 1: Cambiar el valor predeterminado de hoja fija a lienzo adaptativo

**Files:**

- Modify: `tests/test_reglas.py`
- Modify: `tests/test_hoja_y_coordenadas.py`
- Modify: `tests/test_web_api.py`
- Modify: `src/igea_dgs/reglas.py`
- Modify: `src/igea_dgs/cli.py`
- Modify: `src/igea_dgs/web/workspace.py`
- Modify: `src/igea_dgs/web/services.py`
- Modify: `src/igea_dgs/web/app.py`
- Modify: `tools/convertir_grupos_mdb.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/OptionsPanel.tsx`
- Modify: `frontend/src/components/FeedersPanel.tsx`
- Modify: `README.md`

**Interfaces:**

- Consumes: `Reglas.hoja`, opción CLI/web `hoja`, `FeederModel.diagram_sheet`.
- Produces: `None`/`AUTO` para escala adaptativa, o `A0`–`A4` solo cuando el operador lo solicita.
- Invariant: `_diagram_mapper()` sigue usando `NA205_DIAGRAM_UNITS_PER_METER = 2.08` cuando `diagram_sheet is None`.

- [ ] **Step 1: Escribir las pruebas rojas del nuevo valor predeterminado**

Cambiar las aserciones para exigir:

```python
assert REGLAS_PROYECTO.hoja is None
assert 'hoja' not in item
assert estado['options']['hoja'] == 'AUTO'
```

Agregar una prueba separada que solicite `A0` explícitamente y mantenga:

```python
assert item['hoja']['formato'] == 'A0'
```

Agregar una prueba del grupo que compare el `diagram_sheet.scale` adaptativo con `2.08` y demuestre que el ancho crece con la extensión geográfica.

- [ ] **Step 2: Ejecutar las pruebas y observar el fallo esperado**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_reglas.py tests\test_hoja_y_coordenadas.py tests\test_web_api.py
```

Expected: fallos por `REGLAS_PROYECTO.hoja == 'A0'`, workspace `A0` y ausencia de `AUTO` en los contratos web/CLI.

- [ ] **Step 3: Implementar el valor adaptativo de extremo a extremo**

Implementar estas reglas:

```python
REGLAS_PROYECTO = Reglas(hoja=None, ...)

def _normalizar_hoja(value: str | None) -> str | None:
    return None if not value or value.upper() == 'AUTO' else value.upper()
```

- CLI: `--hoja` acepta `AUTO,A0,A1,A2,A3,A4`, defecto `AUTO`.
- Workspace: guarda `hoja='AUTO'`.
- Servicio: `rules_de()` convierte `AUTO` a `None`, no a `A0`.
- API/FastAPI y tipos TypeScript: amplían el literal con `AUTO`.
- UI: muestra `Adaptativa / escala real (recomendado)` primero; A0 deja de etiquetarse como regla del proyecto.
- Herramienta MDB: `--hoja AUTO` por defecto y pasa `None` a `replace`.
- Documentación: describe A0–A4 como impresión explícita.

- [ ] **Step 4: Ejecutar pruebas Python y compilación frontend**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_reglas.py tests\test_hoja_y_coordenadas.py tests\test_web_api.py
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: todas verdes; frontend compila sin incompatibilidades de literal.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_reglas.py tests/test_hoja_y_coordenadas.py tests/test_web_api.py src/igea_dgs/reglas.py src/igea_dgs/cli.py src/igea_dgs/web/workspace.py src/igea_dgs/web/services.py src/igea_dgs/web/app.py tools/convertir_grupos_mdb.py frontend/src/types.ts frontend/src/components/OptionsPanel.tsx frontend/src/components/FeedersPanel.tsx README.md
git commit -m "fix: usar grid adaptativo por defecto"
```

## Task 2: Conservar la propiedad del alimentador en el modelo eléctrico

**Files:**

- Modify: `tests/test_model.py`
- Modify: `tests/test_combine.py`
- Modify: `tests/test_puentes.py`
- Modify: `src/igea_dgs/model.py`
- Modify: `src/igea_dgs/combine.py`
- Modify: `src/igea_dgs/puentes.py`

**Interfaces:**

- Consumes: `dataset.resolve_feeder(selector)`, `feeder_short_name(network_id)`.
- Produces por objeto: `feeder: str` y `network_id: str` en `Load`, `Sed`, `SwitchingDevice` y `Coupler`.
- Invariant: `dataclasses.replace()` en la unión solo cambia nodos/tipos; no cambia propiedad.

- [ ] **Step 1: Escribir pruebas rojas de procedencia individual y combinada**

Agregar aserciones equivalentes a:

```python
assert {load.feeder for load in model.loads} == {'NA203'}
assert {load.network_id for load in model.loads} == {network_id_na203}

combined, _ = combine_models([na203, na205], name='NA203_NA205')
assert {load.feeder for load in combined.loads} == {'NA203', 'NA205'}
assert all(sed.feeder in {'NA203', 'NA205'} for sed in combined.seds)
assert all(dev.feeder in {'NA203', 'NA205'} for dev in combined.devices)
```

Para puentes fundidos, comprobar que el `Coupler` hereda ambos campos del `SwitchingDevice` que lo originó.

- [ ] **Step 2: Ejecutar las pruebas y observar `AttributeError`**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_model.py tests\test_combine.py tests\test_puentes.py
```

Expected: fallos porque los dataclasses todavía no poseen `feeder`/`network_id`.

- [ ] **Step 3: Añadir procedencia explícita en el constructor**

Añadir campos con valor predeterminado al final de cada dataclass para conservar compatibilidad con fixtures posicionales:

```python
feeder: str = ''
network_id: str = ''
```

En `build_feeder_model()`, asignar `feeder=name` y `network_id=network_id` al crear cargas, SED y maniobras. En `puentes.py`, copiar esos campos al `Coupler`. No recalcularlos en `combine_models()`.

- [ ] **Step 4: Ejecutar las pruebas enfocadas**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_model.py tests\test_combine.py tests\test_puentes.py
```

Expected: verdes, incluida la identidad tras combinar alimentadores.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_model.py tests/test_combine.py tests/test_puentes.py src/igea_dgs/model.py src/igea_dgs/combine.py src/igea_dgs/puentes.py
git commit -m "feat: conservar procedencia por alimentador"
```

## Task 3: Generar un manifiesto de alimentadores enlazado al DGS

**Files:**

- Create: `src/igea_dgs/feeder_metadata.py`
- Create: `tests/test_feeder_metadata.py`
- Modify: `src/igea_dgs/dgs.py`
- Modify: `src/igea_dgs/batch.py`
- Modify: `tests/test_batch_robustness.py`
- Modify: `tests/test_reglas.py`

**Interfaces:**

- Consumes: filas efectivamente emitidas por `write_dgs()`, FID, nombres normalizados, terminal/subestación, `feeder`, `network_id`.
- Produces: `<nombre>_feeder_metadata.json` con `schema_version`, `dgs_file`, `dgs_sha256`, clases objetivo y `assignments`.
- Record mínimo:

```python
@dataclass(frozen=True)
class FeederAssignment:
    class_name: str       # ElmLod | ElmSym | ElmXnet
    dgs_fid: str
    loc_name: str
    feeder: str
    network_id: str
    terminal: str
    substation: str
    section_id: str = ''
    node_id: str = ''
```

- Invariant: para cada fila `ElmLod` y `ElmXnet` exportada hay exactamente una asignación; `ElmSym` puede tener cero.

- [ ] **Step 1: Escribir pruebas rojas del esquema y unicidad**

Cubrir:

- una carga NA203 genera `ElmLod -> NA203`;
- una carga NA205 genera `ElmLod -> NA205`;
- cada `ElmXnet` obtiene el alimentador de `CombinedInfo.feeders`;
- dos cargas con el mismo `loc_name` pero distinta SED/terminal permanecen distinguibles;
- el SHA-256 cambia si cambia el DGS;
- un registro vacío, duplicado o con clase no permitida se rechaza;
- si la conversión falla, ni DGS ni metadata se publican parcialmente.

- [ ] **Step 2: Ejecutar las pruebas y observar el fallo esperado**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_feeder_metadata.py tests\test_batch_robustness.py tests\test_reglas.py
```

Expected: módulo/archivo inexistente y manifiestos sin campo `feeder_metadata`.

- [ ] **Step 3: Implementar el esquema puro y validación cerrada**

En `feeder_metadata.py` implementar:

```python
def sha256_file(path: Path) -> str: ...
def validate_assignments(records: Sequence[FeederAssignment]) -> None: ...
def write_feeder_metadata(records, dgs_path, output_path) -> Path: ...
def read_feeder_metadata(path, *, expected_dgs=None) -> FeederMetadata: ...
```

La clave de unicidad será:

```python
(class_name, loc_name, terminal, substation)
```

El lector compara el hash con `expected_dgs` y falla si no coincide.

- [ ] **Step 4: Construir registros desde las mismas identidades escritas al DGS**

Extender `DgsManifest` con:

```python
feeder_assignments: tuple[FeederAssignment, ...] = ()
```

En `write_dgs()` registrar:

- `ElmLod`: nombre ya normalizado, FID, terminal BT interno para SED o nodo directo, subestación si aplica, sección y nodo;
- `ElmXnet`: `External Grid <feeder>`, FID, nodo fuente, alimentador y `NetworkID` de `FeederRef`;
- `ElmSym`: colección vacía hoy, sin inventar máquinas.

- [ ] **Step 5: Publicar metadata atómicamente en conversiones individuales y de grupo**

En `batch.py`, escribir la metadata dentro de `stage` inmediatamente después del DGS y antes de validar/publicar. Incluir en los manifiestos:

```python
'feeder_metadata': str(out_dir / f'{name}_feeder_metadata.json')
```

En caso de fallo, publicar solo informes diagnósticos, igual que el DGS actual.

- [ ] **Step 6: Ejecutar pruebas enfocadas**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_feeder_metadata.py tests\test_batch_robustness.py tests\test_reglas.py tests\test_combine.py
```

Expected: verdes; número de asignaciones `ElmLod`/`ElmXnet` idéntico al número de filas DGS.

- [ ] **Step 7: Commit**

```powershell
git add src/igea_dgs/feeder_metadata.py src/igea_dgs/dgs.py src/igea_dgs/batch.py tests/test_feeder_metadata.py tests/test_batch_robustness.py tests/test_reglas.py
git commit -m "feat: publicar metadata de alimentadores"
```

## Task 4: Crear la Data Extension `Alimentador` de forma idempotente

**Files:**

- Create: `src/igea_dgs/powerfactory_metadata.py`
- Create: `tests/test_powerfactory_feeder_metadata.py`

**Interfaces:**

- Consumes: proyecto PowerFactory activo y clases `ElmLod`, `ElmSym`, `ElmXnet`.
- Produces: configuración `Trazabilidad IGEA` por clase con atributo string `p:alimentador`, descripción `Alimentador`, unidad vacía y valor inicial vacío.
- API oficial usada:

```python
settings = project.BeginDataExtensionModification()
config = settings.GetConfiguration(class_name, 'Trazabilidad IGEA')
config = config or settings.AddConfiguration(class_name, 'Trazabilidad IGEA')
config.AddString('alimentador', 'Alimentador', '', '')
project.EndDataExtensionModification()
```

- [ ] **Step 1: Construir dobles de prueba de `IntPrj`, `SetDataext` e `IntAddonvars`**

Las pruebas deben demostrar:

- primera ejecución crea tres configuraciones y el atributo;
- segunda ejecución no llama de nuevo a `AddString`;
- cualquier excepción todavía invoca `EndDataExtensionModification`;
- proyecto inactivo o API faltante produce un error explícito;
- el reporte separa `created`, `existing` y `errors` por clase.

- [ ] **Step 2: Ejecutar la prueba y observar el fallo por módulo inexistente**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_powerfactory_feeder_metadata.py
```

Expected: fallo de importación.

- [ ] **Step 3: Implementar la transacción idempotente**

Implementar funciones pequeñas:

```python
def ensure_alimentador_data_extensions(project, classes=TARGET_CLASSES) -> dict: ...
def data_extension_attribute_name() -> str:
    return 'p:alimentador'
```

No usar `RemoveAllConfigurations`, `RemoveConfiguration` ni migraciones destructivas. Si existe una configuración ajena con el mismo atributo, verificar el atributo después de cerrar la transacción y reportar conflicto sin reemplazarlo.

- [ ] **Step 4: Ejecutar la prueba enfocada**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_powerfactory_feeder_metadata.py
```

Expected: verde e idempotencia demostrada.

- [ ] **Step 5: Commit**

```powershell
git add src/igea_dgs/powerfactory_metadata.py tests/test_powerfactory_feeder_metadata.py
git commit -m "feat: crear data extension de alimentador"
```

## Task 5: Resolver y asignar cargas/fuentes sin ambigüedad en PowerFactory

**Files:**

- Modify: `src/igea_dgs/powerfactory_metadata.py`
- Modify: `tests/test_powerfactory_feeder_metadata.py`
- Modify: `tools/powerfactory_acceptance.py`
- Modify: `tests/test_powerfactory_gate.py`

**Interfaces:**

- Consumes: `<nombre>_feeder_metadata.json`, objetos PowerFactory importados y `p:alimentador` ya disponible.
- Produces: valores `NA203`/`NA205` en objetos `ElmLod`, `ElmSym`, `ElmXnet`, más reporte de resolución y escritura.
- Identidad de emparejamiento exacta:

```python
(class_name, loc_name, terminal_loc_name, substation_loc_name)
```

- Invariant: no escribir ningún objeto hasta que todas las asignaciones esperadas se hayan resuelto exactamente una vez.

- [ ] **Step 1: Escribir pruebas rojas de resolución**

Cubrir:

- coincidencia exacta de carga anidada en SED por nombre + `SE..._BT` + subestación;
- coincidencia de carga directa por nombre + terminal;
- coincidencia de `ElmXnet` por nombre + terminal fuente;
- soporte sintético `ElmSym`;
- dos objetos con igual nombre y distinto terminal no se confunden;
- cero candidatos y dos candidatos bloquean toda la escritura;
- un `SetAttribute('p:alimentador', ...)` fallido revierte los objetos ya tocados a su valor anterior;
- lectura rechazada si el SHA-256 no coincide con el DGS importado.

- [ ] **Step 2: Ejecutar pruebas y observar los fallos**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_powerfactory_feeder_metadata.py tests\test_powerfactory_gate.py
```

Expected: funciones de indexado/asignación aún ausentes.

- [ ] **Step 3: Implementar indexado, preflight y rollback**

Añadir:

```python
def build_runtime_identity(obj) -> RuntimeObjectIdentity: ...
def resolve_feeder_assignments(records, objects) -> ResolutionPlan: ...
def apply_feeder_assignment_plan(plan, attribute='p:alimentador') -> dict: ...
```

Reglas:

1. indexar `app.GetCalcRelevantObjects('*.ElmLod')`, `*.ElmSym`, `*.ElmXnet`;
2. normalizar solo espacios exteriores, nunca mayúsculas ni códigos;
3. resolver todo y comprobar cardinalidad 1:1;
4. conservar valores previos;
5. escribir;
6. verificar lectura posterior;
7. revertir ante el primer fallo.

- [ ] **Step 4: Integrar en la compuerta PowerFactory**

Agregar al parser:

```text
--feeder-metadata PATH
```

Si no se indica, descubrir el hermano `<stem>_feeder_metadata.json`; si se indica y falta, fallar. Orden de `run_import_activate_flow()`:

1. importar DGS;
2. obtener el proyecto activo y verificar que su identidad coincide con el proyecto recién importado;
3. crear/verificar Data Extensions;
4. reactivar caso de estudio y escenario;
5. resolver y asignar `Alimentador`;
6. ejecutar `ComLdf`;
7. incorporar `feeder_metadata`, conteos por clase/alimentador, no resueltos y ambigüedades al JSON/TXT.

- [ ] **Step 5: Ejecutar pruebas enfocadas y ayuda CLI**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_powerfactory_feeder_metadata.py tests\test_powerfactory_gate.py
.\.venv\Scripts\python.exe tools\powerfactory_acceptance.py --help
```

Expected: verdes; ayuda incluye `--feeder-metadata`.

- [ ] **Step 6: Commit**

```powershell
git add src/igea_dgs/powerfactory_metadata.py tools/powerfactory_acceptance.py tests/test_powerfactory_feeder_metadata.py tests/test_powerfactory_gate.py
git commit -m "feat: asignar alimentador en powerfactory"
```

## Task 6: Cablear metadata y estado por la interfaz web

**Files:**

- Modify: `src/igea_dgs/web/services.py`
- Modify: `src/igea_dgs/web/workspace.py`
- Modify: `tests/test_web_api.py`
- Modify: `tests/test_reglas.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/FeedersPanel.tsx`

**Interfaces:**

- Consumes: DGS publicado y su metadata hermana.
- Produces: comando PowerFactory con `--feeder-metadata`, log de filas asignadas y estado persistido en workspace.
- Invariant: una conversión nueva sin metadata no se ofrece como lista para aceptación PowerFactory.

- [ ] **Step 1: Escribir pruebas rojas del cableado web**

Probar que `dgs_jobs()` retorna `dgs`, `geography` y `feeder_metadata`; que `powerfactory_flow()` pasa la bandera; y que la respuesta/log contiene conteos por `NA203`/`NA205`.

Agregar caso de grupo unido: `NA203_NA205.dgs` debe usar `NA203_NA205_feeder_metadata.json`, no metadata individual.

- [ ] **Step 2: Ejecutar pruebas y observar el fallo de firma**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_web_api.py tests\test_reglas.py
```

Expected: `dgs_jobs()` todavía devuelve tuplas de tres valores y el comando no contiene la metadata.

- [ ] **Step 3: Implementar cableado y mensajes operativos**

- Ampliar la tupla de job con `metadata_path`.
- Validar metadata faltante con mensaje que indique reconvertir el DGS.
- Añadir `--feeder-metadata <path>` al subprocess.
- Persistir en `ws.groups`/`ws.conversions` el nombre de la metadata y el resumen de aceptación.
- Mostrar en interfaz: `Alimentador: asignado X/X cargas, Y/Y fuentes`.
- Mantener los botones existentes y no cambiar el flujo de cargas/SED.

- [ ] **Step 4: Verificar backend y frontend**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_web_api.py tests\test_reglas.py tests\test_powerfactory_gate.py
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: verde; la interfaz compila y el comando queda observable en el fake runner.

- [ ] **Step 5: Commit**

```powershell
git add src/igea_dgs/web/services.py src/igea_dgs/web/workspace.py tests/test_web_api.py tests/test_reglas.py frontend/src/types.ts frontend/src/components/FeedersPanel.tsx
git commit -m "feat: cablear columna alimentador en la web"
```

## Task 7: Formalizar la regresión eléctrica NA203–NA205

**Files:**

- Create: `tests/test_na203_na205_acceptance.py`
- Create: `tools/verify_na203_na205.py`
- Modify: `docs/POWERFACTORY_ACCEPTANCE.md`
- Modify: `pytest.ini`

**Interfaces:**

- Consumes: base MDB real, catálogo, DGS/metadata/validation generados.
- Produces: informe JSON/TXT reproducible con conteos, escala, extensión, Trafomix, SED, maniobras y pertenencia.
- Invariant: la prueba real se omite claramente si la MDB no está disponible; nunca se presenta el skip como aceptación.

- [ ] **Step 1: Escribir pruebas rojas del verificador puro**

El verificador debe exigir como mínimo:

```text
feeders == [NA203, NA205]
trafomix_excluded == 92
trafomix_m_present == 0
ElmLod assignments == ElmLod rows
ElmXnet assignments == 2
feeders in assignments == {NA203, NA205}
SED internal topology complete
switch source/output reconciliation has no loss
diagram scale == 2.08 u/m (within tolerance)
diagram width/height are derived from geometry, not A0
validation errors_total == 0
```

No fijar a ciegas el total de interruptores: compararlo con el inventario fuente, los puentes fundidos, los acopladores internos de SED y los ties abiertos reportados.

- [ ] **Step 2: Ejecutar la prueba y observar el fallo por verificador ausente**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_na203_na205_acceptance.py
```

- [ ] **Step 3: Implementar el verificador de artefactos**

El script acepta:

```text
--dgs
--manifest
--feeder-metadata
--validation
--output-json
--output-txt
```

Debe salir con código distinto de cero ante cualquier incumplimiento y escribir siempre un diagnóstico.

- [ ] **Step 4: Documentar aceptación de la columna en PowerFactory**

En `docs/POWERFACTORY_ACCEPTANCE.md` añadir:

1. ruta automática para crear `p:alimentador`;
2. cómo abrir `Generators, Loads, and Sources > General Load`;
3. intentar `Basic Data` y seleccionar `Alimentador` después de `Grid`;
4. si no aparece ahí, abrir `Flexible Data`, selección de variables, `Data Extension > Alimentador`, y arrastrarla después de `Grid`;
5. repetir para `Synchronous Machine` y `External Grid`;
6. guardar evidencia de al menos una carga NA203, una NA205 y ambas fuentes.

- [ ] **Step 5: Ejecutar pruebas enfocadas**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_na203_na205_acceptance.py tests\test_graphics_sed.py tests\test_diagram_topology_coverage.py tests\test_load_data_extraction.py tests\test_puentes.py
```

Expected: verdes; las pruebas sintéticas prueban los contratos aunque la MDB real no esté presente.

- [ ] **Step 6: Commit**

```powershell
git add tests/test_na203_na205_acceptance.py tools/verify_na203_na205.py docs/POWERFACTORY_ACCEPTANCE.md pytest.ini
git commit -m "test: cubrir aceptacion na203 na205"
```

## Task 8: Regenerar y validar los dos alimentadores reales

**Files:**

- Read only: `referencia/NA205.dgs`
- Read only: MDB de red y catálogo configurados en el entorno
- Generate, do not commit: `output/acceptance_20260927/*`

**Interfaces:**

- Consumes: datos reales NA203/NA205.
- Produces: DGS unido, metadata, manifiesto, validaciones, hashes y comparación con referencia.

- [ ] **Step 1: Resolver rutas exactas y registrar hashes de entrada**

Run:

```powershell
Get-FileHash referencia\NA205.dgs -Algorithm SHA256
Get-FileHash <RED_MDB> -Algorithm SHA256
Get-FileHash <CATALOGO_XLSX> -Algorithm SHA256
```

No continuar si hay más de una MDB candidata y el manifiesto previo no permite resolverla sin ambigüedad.

- [ ] **Step 2: Ejecutar la conversión real adaptativa sin importar todavía**

Run:

```powershell
.\.venv\Scripts\python.exe tools\convertir_grupos_mdb.py --mdb <RED_MDB> --catalogo <CATALOGO_XLSX> --grupo NA203_NA205=NA203,NA205 --out-dir output\acceptance_20260927 --hoja AUTO
```

Expected: `NA203_NA205.dgs`, `_manifest.json`, `_validation.*`, `_geography.json` y `_feeder_metadata.json` publicados; estado `ok`.

- [ ] **Step 3: Ejecutar verificación de artefactos**

Run:

```powershell
.\.venv\Scripts\python.exe tools\verify_na203_na205.py --dgs output\acceptance_20260927\NA203_NA205.dgs --manifest output\acceptance_20260927\NA203_NA205_manifest.json --feeder-metadata output\acceptance_20260927\NA203_NA205_feeder_metadata.json --validation output\acceptance_20260927\NA203_NA205_validation.json --output-json output\acceptance_20260927\NA203_NA205_artifact_acceptance.json --output-txt output\acceptance_20260927\NA203_NA205_artifact_acceptance.txt
```

Expected: código 0 y todas las compuertas en `PASS`.

- [ ] **Step 4: Comparar cuantitativamente con la referencia**

Registrar en el informe:

- unidades por metro y escala equivalente;
- ancho/alto del lienzo;
- cantidad de `ElmLod`, `ElmSubstat`, `ElmTr2`, `ElmCoup`, `StaSwitch`, `ElmXnet`;
- distribución de cargas por NA203/NA205;
- diferencia entre el DGS nuevo y la referencia sin asumir igualdad byte a byte.

- [ ] **Step 5: No hacer commit de datos operativos**

Confirmar que `git status --short` no incluye MDB, DGS reales ni informes con datos de la empresa.

## Task 9: Importar en PowerFactory 2024 y comprobar la columna visible

**Files:**

- Generate, do not commit: `output/acceptance_20260927/NA203_NA205_powerfactory_acceptance.json`
- Generate, do not commit: `output/acceptance_20260927/NA203_NA205_powerfactory_acceptance.txt`
- Generate, do not commit: capturas de Grid y Network Model Manager

**Interfaces:**

- Consumes: DGS y metadata aprobados en Task 8.
- Produces: proyecto PowerFactory, escenario activo, flujo convergente, Data Extensions y evidencia visual.

- [ ] **Step 1: Ejecutar la compuerta real**

Run:

```powershell
<PF_PYTHON> tools\powerfactory_acceptance.py --import-dgs output\acceptance_20260927\NA203_NA205.dgs --manifest output\acceptance_20260927\NA203_NA205_geography.json --feeder-metadata output\acceptance_20260927\NA203_NA205_feeder_metadata.json --ensure-scenario --run-load-flow --require-diagram --output-json output\acceptance_20260927\NA203_NA205_powerfactory_acceptance.json --output-txt output\acceptance_20260927\NA203_NA205_powerfactory_acceptance.txt
```

Expected:

- importación sin errores estructurales;
- `p:alimentador` existente en las tres clases;
- todas las cargas/fuentes resueltas y escritas;
- `ComLdf` converge sin escalar ni desconectar cargas;
- diagrama presente.

- [ ] **Step 2: Verificar tamaño real del Grid en la UI**

Abrir el diagrama, ejecutar `Zoom All` y guardar captura. Confirmar que:

- el lienzo abarca la extensión de NA203–NA205;
- no está limitado a A0;
- las SED y etiquetas no forman la nube comprimida de la captura inicial;
- los símbolos mantienen proporción coherente con `referencia/NA205.dgs`.

- [ ] **Step 3: Verificar la columna de cargas**

En `Network Model Manager > Generators, Loads, and Sources > General Load`:

- configurar `Alimentador` después de `Grid` en `Basic Data` si está disponible;
- de lo contrario configurar `Flexible Data` con el mismo orden lógico;
- comprobar una fila `SE...` de NA203 y una de NA205;
- filtrar/ordenar por `Alimentador` y comprobar que los conteos coinciden con metadata.

- [ ] **Step 4: Verificar máquinas y fuentes**

- `Synchronous Machine`: columna creada/configurada aunque la tabla real esté vacía.
- `External Grid`: dos filas, una `NA203` y otra `NA205`.

- [ ] **Step 5: Guardar evidencia sin sobreafirmar**

El informe final debe distinguir:

- pruebas unitarias/sintéticas;
- validación del DGS real;
- aceptación real PowerFactory;
- vista usada (`Basic Data` o `Flexible Data`) y motivo.

Si PowerFactory no está disponible, el plan queda pendiente en esta Task y no se declara completado.

## Task 10: Regresión completa, documentación y cierre

**Files:**

- Modify: `README.md`
- Modify: `docs/MANUAL_COMANDOS.md`
- Modify: `docs/POWERFACTORY_ACCEPTANCE.md`
- Modify: cualquier changelog/versionado que ya use el repositorio

- [ ] **Step 1: Actualizar documentación operativa**

Documentar:

- `AUTO` como defecto;
- A0–A4 como opción explícita;
- nombre y ubicación del manifiesto de alimentadores;
- creación automática de `p:alimentador`;
- diferencia entre `General Load` y SED: la fila `SE50033` es un `ElmLod` alojado dentro de una subestación;
- fallback justificado a `Flexible Data`.

- [ ] **Step 2: Ejecutar suite Python completa**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp\grid_alimentador
```

Expected: todas las pruebas verdes, sin convertir skips de PowerFactory en éxito real.

- [ ] **Step 3: Ejecutar compilación frontend final**

Run:

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: ambos código 0.

- [ ] **Step 4: Ejecutar verificaciones de repositorio**

Run:

```powershell
git diff --check
git status --short
git log --oneline -12
```

Expected: sin whitespace errors; solo cambios deliberados; ningún artefacto real sensible preparado para commit.

- [ ] **Step 5: Revisar cobertura contra la especificación**

Marcar explícitamente cada criterio de aceptación de la especificación como:

```text
PASS unitario
PASS artefacto real
PASS PowerFactory real
PENDIENTE con causa y evidencia
```

No usar `PASS` para una capa que no se ejecutó.

- [ ] **Step 6: Commit final de documentación**

```powershell
git add README.md docs/MANUAL_COMANDOS.md docs/POWERFACTORY_ACCEPTANCE.md
git commit -m "docs: documentar grid adaptativo y alimentador"
```

- [ ] **Step 7: Aplicar verificación antes de completar**

Invocar `superpowers:verification-before-completion`, revisar salidas frescas de pytest, frontend, verificador NA203–NA205 y PowerFactory, y solo entonces declarar la implementación terminada.

## Base científica y oficial que gobierna la implementación

- La tesis de maestría *Automatic Single-Line Diagram Generation for LV Networks from GIS Data* sustenta separar topología, georreferenciación y generación legible del unifilar, en lugar de comprimir arbitrariamente toda la red en una hoja fija.
- Rao y Deekshit, *Energy Loss Estimation in Distribution Feeders*, Electric Power Systems Research, DOI `10.1016/j.epsr.2003.12.005`, sustenta conservar la identidad del alimentador para análisis técnicos por feeder.
- La tesis doctoral *Optimal Distribution Feeder Reconfiguration Considering Generation Costs and Line Losses* sustenta preservar fronteras y maniobras de alimentador para reconfiguración y operación radial.
- La documentación oficial DIgSILENT confirma que Data Extensions añade atributos por clase, los expone a scripts/DGS y permite mostrarlos en `Flexible Data`; la referencia Python 2024 define `BeginDataExtensionModification`, `AddConfiguration`, `AddString` y `EndDataExtensionModification`.

