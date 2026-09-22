# Robustecimiento Integral IGEA/CYMDIST → DGS → PowerFactory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir el proyecto actual en una herramienta local estricta, reproducible y científicamente trazable que preserve todos los elementos y parámetros demostrables de los TXT, genere un DGS fiel, lo importe en PowerFactory y valide el caso original sin defaults físicos ni correcciones silenciosas.

**Architecture:** Se conservará el flujo TXT → modelo → DGS → importación PowerFactory que ya funciona, migrándolo incrementalmente a paquetes pequeños. Cada etapa producirá un resultado tipado y un conjunto de diagnósticos; cualquier diagnóstico bloqueante impedirá publicar artefactos. PowerFactory se encapsulará detrás de un puerto y adaptadores idempotentes para poder probar la lógica sin la aplicación propietaria y ejecutar una aceptación real separada.

**Tech Stack:** Python 3.12 x64, dataclasses/stdlib, Pydantic 2, pyproj, pandas/openpyxl, geopandas/Shapely/leafmap, pytest, pytest-cov, Hypothesis, Ruff, Mypy, Bandit, pip-audit, DIgSILENT PowerFactory 2024 Python API.

**Spec:** `docs/superpowers/specs/2026-09-21-robustecimiento-integral-igea-dgs-design.md`

## Global Constraints

- Entorno objetivo: Windows local, un operador y PowerFactory 2024 instalado.
- Mantener el flujo TXT → DGS → importación API; no reescribir el producto desde cero.
- Ningún dato físico obligatorio puede obtenerse de un default, coincidencia aproximada o cero implícito.
- Todo parámetro productivo debe tener procedencia `observed_txt`, `observed_catalog`, `manufacturer_datasheet`, `approved_mapping` o `derived`.
- `TRAFOMIX` y su carga asociada se excluyen; la SED y su carga válida permanecen.
- Toda sección TXT debe clasificarse; una sección desconocida bloquea la conversión.
- Conservar fases, SectionID, sección transversal, conductores, ternas, circuitos, longitudes, impedancias, susceptancias, ampacidad y estados.
- Validar el caso PowerFactory original antes de cualquier corrección; las correcciones solo operan sobre una copia diagnóstica.
- Instalar exclusivamente en `.venv`; `powerfactory.pyd` se usa desde la instalación local y no desde PyPI.
- No modificar ni añadir al commit artefactos no relacionados que ya estén sin seguimiento.

## Review Focus

- CRS geográfico en grados o pies: debe conservar la longitud TXT y bloquear cualquier sustitución métrica no demostrada; se prueba en Task 6.
- Código de conductor ausente o parecido: debe bloquear, nunca elegir vecino ni `DEFAULT`; se prueba en Task 5.
- Relación ambigua TRAFOMIX/SED/carga: debe bloquear sin eliminar una carga válida; se prueba en Task 7.
- Alimentador con elementos mono/bifásicos y circuitos múltiples: debe preservar fases y multiplicidad en modelo, DGS y PowerFactory; se prueba en Tasks 8, 9 y 12.
- Fallo después de escribir un DGS nuevo: debe conservar el último resultado válido y limpiar solo temporales; se prueba en Task 10.

---

## File Structure

### Nuevos paquetes

- `src/igea_dgs/ingestion/`: parser, contratos de tablas y procedencia de filas.
- `src/igea_dgs/quality/`: diagnósticos, reglas y puertas G1–G2.
- `src/igea_dgs/domain/`: entidades eléctricas tipadas y modelo de alimentador.
- `src/igea_dgs/rules/`: reglas específicas IGEA, incluida TRAFOMIX.
- `src/igea_dgs/catalog/`: catálogo exacto, fichas técnicas y mappings aprobados.
- `src/igea_dgs/dgsio/`: construcción, serialización y validación DGS.
- `src/igea_dgs/powerfactory/`: puerto API, importación, adaptadores, inspección y estudios.
- `src/igea_dgs/validation/`: comparadores independientes G3–G6.
- `src/igea_dgs/reporting/`: manifiestos, hashes, logs y publicación atómica.

### Compatibilidad

- `dataset.py`, `model.py`, `dgs.py`, `validate.py` y `batch.py` permanecerán como fachadas durante la migración.
- `cli.py` y `gui.py` consumirán servicios; no implementarán reglas eléctricas.
- `tools/powerfactory_acceptance.py` se reducirá progresivamente a una entrada compatible que delega en `igea_dgs.powerfactory`.

---

### Task 1: Baseline reproducible y dependencias completas

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Create: `requirements-export.txt`
- Create: `requirements-powerfactory.txt`
- Create: `constraints.txt`
- Create: `scripts/bootstrap.ps1`
- Create: `scripts/verify.ps1`
- Create: `tests/test_dependency_contract.py`

**Interfaces:**
- Consumes: Python 3.12 x64 y `.venv` existente.
- Produces: `scripts/bootstrap.ps1`, `scripts/verify.ps1` y cuatro grupos de dependencias instalables.

- [ ] **Step 1: Escribir la prueba de contrato de dependencias**

```python
from pathlib import Path


def test_dependency_groups_are_declared_and_powerfactory_is_not_pypi():
    root = Path(__file__).parents[1]
    runtime = (root / "requirements.txt").read_text(encoding="utf-8")
    export = (root / "requirements-export.txt").read_text(encoding="utf-8")
    dev = (root / "requirements-dev.txt").read_text(encoding="utf-8")
    pf = (root / "requirements-powerfactory.txt").read_text(encoding="utf-8")
    assert "pyproj" in runtime
    assert all(name in export for name in ("pandas", "openpyxl", "geopandas", "shapely", "leafmap"))
    assert all(name in dev for name in ("pytest", "pytest-cov", "hypothesis", "ruff", "mypy", "bandit", "pip-audit"))
    assert "powerfactory==" not in pf.lower()
```

- [ ] **Step 2: Ejecutar la prueba y confirmar el fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_dependency_contract.py -v`  
Expected: FAIL porque faltan los nuevos archivos/grupos.

- [ ] **Step 3: Declarar dependencias directas y herramientas**

Usar estos grupos, resolviendo versiones compatibles mediante `pip index versions` y una instalación de prueba:

```text
# requirements.txt
-e .
pyproj>=3.6,<4
pydantic>=2.8,<3
platformdirs>=4.2,<5

# requirements-export.txt
-r requirements.txt
pandas>=2.2,<3
openpyxl>=3.1,<4
geopandas>=1.0,<2
shapely>=2.0,<3
leafmap>=0.38,<1

# requirements-dev.txt
-r requirements-export.txt
pytest>=8,<10
pytest-cov>=5,<8
hypothesis>=6.112,<7
ruff>=0.8,<1
mypy>=1.11,<2
bandit>=1.7,<2
pip-audit>=2.7,<3

# requirements-powerfactory.txt
-r requirements.txt
# powerfactory.pyd es provisto por PowerFactory 2024/Python/3.12.
```

Actualizar extras equivalentes en `pyproject.toml` y exigir `requires-python = ">=3.12,<3.13"` para el perfil PowerFactory local.

- [ ] **Step 4: Crear bootstrap verificable**

`scripts/bootstrap.ps1` debe comprobar Python x64/3.12, actualizar pip, instalar `-r requirements-dev.txt -c constraints.txt` y ejecutar imports. Debe terminar con error si no encuentra `C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12\powerfactory.pyd`, pero permitir `-SkipPowerFactoryCheck` para CI.

- [ ] **Step 5: Instalar todas las dependencias en `.venv`**

Run: `powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1`  
Expected: instalación exitosa e imports de runtime/export/dev; PowerFactory detectado localmente.

- [ ] **Step 6: Congelar resolución y auditar**

Run: `.\.venv\Scripts\python.exe -m pip freeze --exclude-editable`  
Copiar la resolución directa/transitiva compatible a `constraints.txt`, luego ejecutar:  
`.\.venv\Scripts\python.exe -m pip check`  
`.\.venv\Scripts\python.exe -m pip_audit -r requirements-dev.txt -c constraints.txt`

- [ ] **Step 7: Crear puerta reproducible**

`scripts/verify.ps1` ejecutará Ruff, Mypy, Bandit, pytest con cobertura y `pip check`, deteniéndose en el primer fallo.

- [ ] **Step 8: Ejecutar la prueba y la puerta**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_dependency_contract.py -v`  
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml requirements*.txt constraints.txt scripts/bootstrap.ps1 scripts/verify.ps1 tests/test_dependency_contract.py
git commit -m "build: add reproducible dependency profiles"
```

### Task 2: Diagnósticos tipados y procedencia

**Files:**
- Create: `src/igea_dgs/quality/diagnostics.py`
- Create: `src/igea_dgs/quality/gates.py`
- Create: `src/igea_dgs/quality/__init__.py`
- Create: `src/igea_dgs/domain/provenance.py`
- Create: `src/igea_dgs/domain/__init__.py`
- Create: `tests/test_diagnostics.py`

**Interfaces:**
- Produces: `Diagnostic`, `Severity`, `SourceLocation`, `Provenanced[T]`, `GateResult.raise_if_blocked()`.

- [ ] **Step 1: Escribir pruebas de bloqueo y procedencia**

```python
def test_gate_blocks_only_blocking_diagnostics():
    result = GateResult("G1", [Diagnostic.blocking("E001", "Length missing", SourceLocation("RED.txt", "LINE CONFIGURATION", 42, "Length"))])
    assert result.blocked is True
    with pytest.raises(QualityGateError, match="E001"):
        result.raise_if_blocked()


def test_provenanced_value_rejects_assumed_in_production():
    value = Provenanced(value=0.3, kind=ProvenanceKind.ASSUMED, source="internal")
    assert value.production_eligible is False
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_diagnostics.py -v`  
Expected: FAIL por módulos inexistentes.

- [ ] **Step 3: Implementar tipos inmutables y códigos estables**

Usar `StrEnum`, dataclasses congeladas y `Generic[T]`; serialización mediante métodos `to_dict()` explícitos.

- [ ] **Step 4: Ejecutar pruebas**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_diagnostics.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/igea_dgs/quality src/igea_dgs/domain tests/test_diagnostics.py
git commit -m "feat: add typed diagnostics and provenance"
```

### Task 3: Parser estricto con cobertura total

**Files:**
- Create: `src/igea_dgs/ingestion/records.py`
- Create: `src/igea_dgs/ingestion/parser.py`
- Create: `src/igea_dgs/ingestion/contracts.py`
- Create: `src/igea_dgs/ingestion/__init__.py`
- Modify: `src/igea_dgs/dataset.py`
- Create: `tests/test_strict_ingestion.py`
- Create: `tests/test_ingestion_properties.py`

**Interfaces:**
- Produces: `parse_igea_file(path: Path, contract: FileContract) -> ParsedFile`, `RawRecord`, `TableContract`.
- Compatibility: `CymdistDataset.from_files()` delega en el parser estricto.

- [ ] **Step 1: Probar duplicados, columnas sobrantes, encoding y sección desconocida**

```python
def test_duplicate_node_is_blocking(tmp_path):
    path = write_red(tmp_path, nodes=["N1,1,2", "N1,3,4"])
    parsed = parse_igea_file(path, RED_CONTRACT)
    assert parsed.gate.blocked
    assert "DUPLICATE_KEY" in {d.code for d in parsed.gate.diagnostics}


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=40))
def test_parser_never_drops_extra_columns_silently(extra):
    # El resultado contiene EXTRA_COLUMN o conserva exactamente la fila.
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_strict_ingestion.py tests/test_ingestion_properties.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implementar parser conservando número de línea y texto original**

Abrir con UTF-8 estricto; si falla, emitir `INVALID_ENCODING`. No usar `errors="replace"`. Validar cantidad de columnas, encabezados repetidos, claves vacías y secciones no registradas.

- [ ] **Step 4: Adaptar `CymdistDataset` sin romper API pública**

Agregar `diagnostics`, `parsed_sections` y `input_hashes`; eliminar sobrescrituras silenciosas.

- [ ] **Step 5: Ejecutar pruebas antiguas y nuevas**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_dataset.py tests/test_fixtures.py tests/test_strict_ingestion.py tests/test_ingestion_properties.py -v`  
Expected: PASS o skip explícito solo si no existen TXT reales.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/ingestion src/igea_dgs/dataset.py tests/test_strict_ingestion.py tests/test_ingestion_properties.py
git commit -m "feat: add strict traceable TXT ingestion"
```

### Task 4: Inventario completo y contratos de cobertura

**Files:**
- Create: `src/igea_dgs/quality/inventory.py`
- Modify: `src/igea_dgs/inventory.py`
- Create: `config/igea_sections.json`
- Modify: `src/igea_dgs/cli.py`
- Create: `tests/test_inventory_coverage.py`

**Interfaces:**
- Produces: `build_strict_inventory(dataset) -> DatasetInventory`, CLI `inspect` y `validate-input`.

- [ ] **Step 1: Probar que una sección no soportada bloquea**

```python
def test_unknown_populated_section_blocks_conversion(dataset_with_unknown_section):
    inv = build_strict_inventory(dataset_with_unknown_section)
    assert inv.gate.blocked
    assert inv.coverage["UNKNOWN EQUIPMENT"].status == "unsupported"
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_inventory_coverage.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implementar registro de secciones y cardinalidades**

`config/igea_sections.json` mapeará cada sección a `supported`, `catalog_only` o `known_empty`, su clave y adaptador. Una sección poblada sin adaptador será bloqueante.

- [ ] **Step 4: Añadir métricas físicas**

Incluir faltantes, duplicados, rangos R/X/B/I/longitud/P/Q, fases, tipos usados, elementos por alimentador y cobertura porcentual.

- [ ] **Step 5: Añadir comandos sin escritura de DGS**

`inspect` devuelve inventario; `validate-input` ejecuta G1–G2 y código 2 ante bloqueo.

- [ ] **Step 6: Ejecutar pruebas**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_inventory.py tests/test_inventory_coverage.py tests/test_batch_cli.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/igea_dgs/quality/inventory.py src/igea_dgs/inventory.py src/igea_dgs/cli.py config/igea_sections.json tests/test_inventory_coverage.py
git commit -m "feat: enforce complete TXT section coverage"
```

### Task 5: Catálogo exacto, fichas oficiales y eliminación de fallbacks

**Files:**
- Create: `src/igea_dgs/catalog/models.py`
- Create: `src/igea_dgs/catalog/resolver.py`
- Create: `src/igea_dgs/catalog/datasheets.py`
- Create: `src/igea_dgs/catalog/__init__.py`
- Create: `config/approved_equipment_mappings.json`
- Modify: `src/igea_dgs/model.py`
- Modify: `config/line_type_aliases.json`
- Create: `tests/test_strict_catalog.py`

**Interfaces:**
- Produces: `EquipmentCatalog.resolve_exact(kind, source_id) -> ResolvedEquipment`, `DatasheetRecord`.
- Reemplaza: `_resolve_type` y `suggest_catalog_code` en producción.

- [ ] **Step 1: Probar rechazo de vecino y DEFAULT**

```python
def test_similar_conductor_code_is_not_auto_selected(catalog):
    with pytest.raises(UnresolvedEquipmentError) as exc:
        catalog.resolve_exact("overhead_line", "AA05001D")
    assert exc.value.code == "EQUIPMENT_NOT_FOUND"


def test_approved_mapping_requires_parameter_fingerprint(catalog, approved_mapping):
    resolved = catalog.resolve_exact("overhead_line", "UTILITY-X")
    assert resolved.provenance.kind is ProvenanceKind.APPROVED_MAPPING
    assert resolved.mapping.sha256
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_strict_catalog.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implementar resolución exacta y esquema de fichas**

La ficha exige `manufacturer`, `model`, `revision`, `official_url`, `retrieved_at`, `sha256`, `units` y parámetros extraídos. Rechazar dominios no aprobados o coincidencias múltiples.

- [ ] **Step 4: Deshabilitar fallback en producción**

Conservar `suggest_catalog_code` únicamente como herramienta diagnóstica que nunca alimenta `build_feeder_model`.

- [ ] **Step 5: Migrar aliases existentes a mappings firmados por hash**

Cada mapping debe incluir identificador fuente, destino exacto, medio, parámetros comparados, justificación, aprobador y fecha.

- [ ] **Step 6: Ejecutar pruebas**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_type_resolution.py tests/test_strict_catalog.py tests/test_model_v2.py -v`  
Expected: pruebas antiguas de fallback actualizadas para esperar bloqueo; todo PASS.

- [ ] **Step 7: Commit**

```bash
git add src/igea_dgs/catalog src/igea_dgs/model.py config/approved_equipment_mappings.json config/line_type_aliases.json tests/test_strict_catalog.py tests/test_type_resolution.py
git commit -m "feat: require exact traceable equipment data"
```

### Task 6: Longitudes y geografía dimensionalmente correctas

**Files:**
- Create: `src/igea_dgs/domain/lengths.py`
- Modify: `src/igea_dgs/geography.py`
- Modify: `src/igea_dgs/model.py`
- Modify: `src/igea_dgs/cli.py`
- Create: `tests/test_length_policy.py`

**Interfaces:**
- Produces: `LengthPolicy`, `compare_lengths(line, crs) -> LengthComparison`, `apply_length_policy(...)`.

- [ ] **Step 1: Probar CRS en grados, pies y metros**

```python
@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:2230"])
def test_non_metric_crs_never_replaces_txt_length_implicitly(crs, model, dataset):
    result = apply_length_policy(model, dataset, crs, LengthPolicy.TXT_AUTHORITATIVE)
    assert all(line.length_source == "txt" for line in result.lines)
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_length_policy.py -v`  
Expected: FAIL porque el modelo reemplaza siempre con `hypot`.

- [ ] **Step 3: Implementar política explícita**

Valores: `TXT_AUTHORITATIVE`, `GEODESIC_VALIDATED`, `PROJECTED_VALIDATED`. Consultar unidades con `pyproj.CRS`; transformar antes de medir; registrar razón GIS/TXT y outliers por mediana/MAD.

- [ ] **Step 4: Eliminar mutación automática del constructor**

`build_feeder_model` conservará TXT. La política se aplica explícitamente desde orquestación.

- [ ] **Step 5: Ejecutar regresión**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_length_policy.py tests/test_mt_connectivity_lengths.py tests/test_geography_v21.py -v`  
Expected: PASS con expectativas actualizadas.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/domain/lengths.py src/igea_dgs/geography.py src/igea_dgs/model.py src/igea_dgs/cli.py tests/test_length_policy.py tests/test_mt_connectivity_lengths.py
git commit -m "fix: make electrical length policy explicit"
```

### Task 7: Regla TRAFOMIX y relación SED/carga

**Files:**
- Create: `src/igea_dgs/rules/trafomix.py`
- Create: `src/igea_dgs/rules/sed.py`
- Create: `src/igea_dgs/rules/__init__.py`
- Modify: `src/igea_dgs/model.py`
- Create: `tests/fixtures/trafomix/RED.txt`
- Create: `tests/fixtures/trafomix/CARGA.txt`
- Create: `tests/fixtures/trafomix/BD_Equipo.txt`
- Create: `tests/test_trafomix_rule.py`

**Interfaces:**
- Produces: `classify_distribution_asset(record_set) -> AssetClassification`, `apply_trafomix_rule(...) -> RuleResult`.

- [ ] **Step 1: Codificar casos exactos y ambiguos**

```python
def test_trafomix_and_its_load_are_excluded_but_sed_load_remains(trafomix_dataset):
    result = apply_trafomix_rule(trafomix_dataset)
    assert result.excluded_keys == {("SEC1", "TRAFOMIX-01"), ("SEC1", "LOAD-TM-01")}
    assert ("SEC1", "LOAD-SED-01") in result.retained_load_keys


def test_ambiguous_trafomix_relation_blocks(ambiguous_dataset):
    result = apply_trafomix_rule(ambiguous_dataset)
    assert result.gate.blocked
    assert "TRAFOMIX_AMBIGUOUS_RELATION" in {d.code for d in result.gate.diagnostics}
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_trafomix_rule.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implementar clasificación por campos y relaciones**

Usar clave `(SectionID, DeviceNumber)`, placement, tipo de carga/equipo y referencias cruzadas. Los patrones textuales solo aportan evidencia secundaria y nunca resuelven una ambigüedad.

- [ ] **Step 4: Eliminar inferencia automática de `ElmTr2`**

Separar `SedSite` de `DistributionTransformer`; crear transformador solo con `TransformerSpec` completo.

- [ ] **Step 5: Ejecutar regresión SED/DGS**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_trafomix_rule.py tests/test_graphics_sed.py tests/test_mt_connectivity_lengths.py -v`  
Expected: PASS con pruebas antiguas actualizadas a la nueva semántica.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/rules src/igea_dgs/model.py tests/fixtures/trafomix tests/test_trafomix_rule.py tests/test_graphics_sed.py tests/test_mt_connectivity_lengths.py
git commit -m "fix: exclude TRAFOMIX without losing valid SED loads"
```

### Task 8: Modelo eléctrico completo por fase y multiplicidad

**Files:**
- Create: `src/igea_dgs/domain/phases.py`
- Create: `src/igea_dgs/domain/equipment.py`
- Create: `src/igea_dgs/domain/feeder.py`
- Modify: `src/igea_dgs/model.py`
- Create: `tests/test_phase_model.py`
- Create: `tests/test_multicircuit_model.py`

**Interfaces:**
- Produces: `PhaseSet`, `ConductorArrangement`, `CircuitMultiplicity`, `OverheadLine`, `UndergroundCable`, `LoadSpec`, `SourceSpec`, `SolarPlantSpec`, `ThermalGeneratorSpec`.

- [ ] **Step 1: Probar fases y circuitos**

```python
def test_single_phase_load_and_double_circuit_line_are_preserved(dataset):
    feeder = build_strict_feeder_model(dataset, "F1")
    assert feeder.loads[0].phases == PhaseSet.A
    assert feeder.lines[0].circuits.count == 2
    assert feeder.lines[0].conductors_per_phase == 3
    assert feeder.lines[0].cross_section_mm2 == Decimal("150")
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_phase_model.py tests/test_multicircuit_model.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implementar entidades con `Decimal` y unidades explícitas**

No usar `float` sin unidad para datos de entrada. Normalizar a kV, MW, Mvar, ohm/km, µS/km, A, mm² y km en el límite de ingestión.

- [ ] **Step 4: Implementar todos los `ValueType` demostrados por fixtures reales**

Cada tipo tendrá fórmula documentada; un tipo desconocido emite `UNSUPPORTED_LOAD_VALUE_TYPE` bloqueante. No asignar Q=0 por defecto.

- [ ] **Step 5: Construir adaptadores de fuente, solar y térmica**

Solo crear especificaciones si se satisfacen contratos mínimos por estudio.

- [ ] **Step 6: Ejecutar pruebas**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_phase_model.py tests/test_multicircuit_model.py tests/test_model_v2.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/igea_dgs/domain src/igea_dgs/model.py tests/test_phase_model.py tests/test_multicircuit_model.py tests/test_model_v2.py
git commit -m "feat: preserve phase and circuit fidelity"
```

### Task 9: Constructor DGS fiel sin defaults físicos

**Files:**
- Create: `src/igea_dgs/dgsio/builder.py`
- Create: `src/igea_dgs/dgsio/writer.py`
- Create: `src/igea_dgs/dgsio/parser.py`
- Create: `src/igea_dgs/dgsio/__init__.py`
- Modify: `src/igea_dgs/dgs.py`
- Modify: `src/igea_dgs/schemas/pf21_dgs_1_8_4.json`
- Create: `tests/test_dgs_electrical_fidelity.py`

**Interfaces:**
- Produces: `build_dgs_document(feeder) -> DgsDocument`, `write_dgs_document(document, path)`.

- [ ] **Step 1: Probar ausencia de constantes inventadas**

```python
def test_dgs_preserves_line_electrical_data_and_multiplicity(strict_feeder, tmp_path):
    path = write_strict_dgs(strict_feeder, tmp_path / "f.dgs")
    tables = parse_dgs(path)
    typ = tables["TypLne"]["rows_dict"][0]
    line = tables["ElmLne"]["rows_dict"][0]
    assert Decimal(typ["bline"]) == strict_feeder.lines[0].b1_us_km
    assert line["nlnum"] == "2"


def test_missing_transformer_spec_never_creates_typtr2(sed_without_transformer, tmp_path):
    tables = render_tables(sed_without_transformer)
    assert "TypTr2" not in tables or tables["TypTr2"] == []
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_dgs_electrical_fidelity.py -v`  
Expected: FAIL.

- [ ] **Step 3: Extraer constructor y escritor**

El constructor solo acepta un modelo que pasó G3. El escritor no toma decisiones eléctricas y debe ser determinista byte a byte.

- [ ] **Step 4: Mapear fases, B1/B0, circuitos y equipos soportados**

Cada atributo tendrá una prueba de ida y vuelta. Si el perfil DGS no puede representar un dato requerido, bloquear con `DGS_PROFILE_CAPABILITY_GAP` y derivar su creación al adaptador API aprobado.

- [ ] **Step 5: Mantener fachada compatible**

`dgs.write_dgs` delegará en `dgsio` y emitirá advertencia de deprecación solo para parámetros obsoletos, no para uso normal.

- [ ] **Step 6: Ejecutar pruebas**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_dgs_electrical_fidelity.py tests/test_dgs_v2.py tests/test_schema.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/igea_dgs/dgsio src/igea_dgs/dgs.py src/igea_dgs/schemas tests/test_dgs_electrical_fidelity.py tests/test_dgs_v2.py
git commit -m "feat: build DGS without physical defaults"
```

### Task 10: Publicación transaccional y manifiestos reproducibles

**Files:**
- Create: `src/igea_dgs/reporting/atomic.py`
- Create: `src/igea_dgs/reporting/manifest.py`
- Create: `src/igea_dgs/reporting/hashing.py`
- Create: `src/igea_dgs/reporting/__init__.py`
- Modify: `src/igea_dgs/batch.py`
- Create: `tests/test_atomic_batch.py`

**Interfaces:**
- Produces: `AtomicRunPublisher`, `RunManifest`, `sha256_file(path)`.

- [ ] **Step 1: Probar preservación del resultado bueno**

```python
def test_failure_after_new_dgs_write_keeps_previous_release(tmp_path, injected_failure):
    final = tmp_path / "F1.dgs"
    final.write_text("KNOWN-GOOD", encoding="utf-8")
    with pytest.raises(InjectedFailure):
        publish_feeder_with_failure(final.parent, injected_failure)
    assert final.read_text(encoding="utf-8") == "KNOWN-GOOD"
    assert not list(tmp_path.glob(".run-*.tmp"))
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_atomic_batch.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implementar staging y `os.replace`**

Crear todo bajo `.runs/<run_id>/<feeder>/`; validar; publicar archivos con reemplazo atómico; conservar `releases/<feeder>/previous` y limpiar temporales de la ejecución actual.

- [ ] **Step 4: Añadir hashes y entorno**

Manifiesto incluye hashes de entradas/config/fichas/salidas, Python, plataforma, dependencias directas, esquema, políticas, tiempos y resultado de puertas.

- [ ] **Step 5: Ejecutar pruebas**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_atomic_batch.py tests/test_batch_cli.py tests/test_geo_batch_v21.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/reporting src/igea_dgs/batch.py tests/test_atomic_batch.py tests/test_batch_cli.py
git commit -m "feat: publish validated feeder runs atomically"
```

### Task 11: Validadores independientes G3 y G4

**Files:**
- Create: `src/igea_dgs/validation/source_model.py`
- Create: `src/igea_dgs/validation/model_dgs.py`
- Create: `src/igea_dgs/validation/results.py`
- Create: `src/igea_dgs/validation/__init__.py`
- Modify: `src/igea_dgs/validate.py`
- Create: `tests/test_source_model_fidelity.py`
- Create: `tests/test_model_dgs_fidelity.py`

**Interfaces:**
- Produces: `validate_source_model(parsed, feeder)`, `validate_model_dgs(feeder, parsed_dgs)`.

- [ ] **Step 1: Crear expectativas independientes desde registros fuente**

```python
def test_source_model_validator_detects_phase_loss(parsed_source, mutated_model):
    mutated_model.lines[0] = replace(mutated_model.lines[0], phases=PhaseSet.ABC)
    result = validate_source_model(parsed_source, mutated_model)
    assert "PHASE_MISMATCH" in result.error_codes
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_source_model_fidelity.py tests/test_model_dgs_fidelity.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implementar comparadores sin reutilizar el builder**

Calcular esperados directamente de `RawRecord` + contratos, no desde funciones de construcción. Comparar identidad, topología, fases, parámetros, multiplicidad, exclusiones y totales P/Q.

- [ ] **Step 4: Diferenciar verificación de validación**

Mantener validaciones estructurales existentes como `structural`; agregar `source_fidelity` y `electrical_fidelity` en reportes.

- [ ] **Step 5: Ejecutar pruebas**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_source_model_fidelity.py tests/test_model_dgs_fidelity.py tests/test_validate_v2.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/igea_dgs/validation src/igea_dgs/validate.py tests/test_source_model_fidelity.py tests/test_model_dgs_fidelity.py
git commit -m "feat: validate source and DGS fidelity independently"
```

### Task 12: Puerto PowerFactory y adaptadores idempotentes

**Files:**
- Create: `src/igea_dgs/powerfactory/port.py`
- Create: `src/igea_dgs/powerfactory/session.py`
- Create: `src/igea_dgs/powerfactory/importer.py`
- Create: `src/igea_dgs/powerfactory/adapters/base.py`
- Create: `src/igea_dgs/powerfactory/adapters/sources.py`
- Create: `src/igea_dgs/powerfactory/adapters/solar.py`
- Create: `src/igea_dgs/powerfactory/adapters/thermal.py`
- Create: `src/igea_dgs/powerfactory/adapters/equipment.py`
- Create: `src/igea_dgs/powerfactory/inspector.py`
- Create: `src/igea_dgs/powerfactory/__init__.py`
- Modify: `tools/powerfactory_acceptance.py`
- Create: `tests/fakes/fake_powerfactory.py`
- Create: `tests/test_powerfactory_adapters.py`

**Interfaces:**
- Produces: `PowerFactoryPort`, `ManagedPowerFactorySession`, `import_dgs`, `EquipmentAdapter` (`preflight/apply/inspect/rollback/report`).

- [ ] **Step 1: Probar idempotencia y rollback con fake**

```python
def test_solar_adapter_is_idempotent(fake_pf, solar_spec):
    adapter = SolarAdapter(fake_pf)
    adapter.apply(solar_spec)
    adapter.apply(solar_spec)
    assert fake_pf.count("ElmGenstat", external_id=solar_spec.external_id) == 1


def test_adapter_rolls_back_created_objects_on_failure(fake_pf, failing_thermal_spec):
    with pytest.raises(AdapterApplyError):
        ThermalAdapter(fake_pf).apply(failing_thermal_spec)
    assert fake_pf.objects_created_in_current_unit == []
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_powerfactory_adapters.py -v`  
Expected: FAIL.

- [ ] **Step 3: Definir puerto mínimo basado en llamadas reales actuales**

Extraer solo operaciones usadas: proyecto/caso/escenario, búsqueda, creación, atributos, importación, comandos, resultados y mensajes.

- [ ] **Step 4: Implementar sesión administrada**

Exigir nombre de proyecto administrado y `run_id`; rechazar mutar un proyecto distinto sin flag explícito; registrar versión de PF, Python y licencia disponible.

- [ ] **Step 5: Implementar adaptadores por tecnología**

Cada adaptador verifica campos mínimos y usa claves externas estables. No convertir una planta solar en carga negativa ni un térmico en fuente genérica sin contrato aprobado.

- [ ] **Step 6: Convertir script existente en fachada**

Mantener argumentos compatibles, delegando en el paquete; reducir capturas genéricas y devolver errores tipados.

- [ ] **Step 7: Ejecutar unitarias PF**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_powerfactory_adapters.py tests/test_powerfactory_gate.py -v`  
Expected: PASS sin abrir PowerFactory.

- [ ] **Step 8: Commit**

```bash
git add src/igea_dgs/powerfactory tools/powerfactory_acceptance.py tests/fakes tests/test_powerfactory_adapters.py tests/test_powerfactory_gate.py
git commit -m "feat: modularize idempotent PowerFactory integration"
```

### Task 13: Validación PowerFactory G5 y estudios G6

**Files:**
- Create: `src/igea_dgs/validation/powerfactory_model.py`
- Create: `src/igea_dgs/powerfactory/studies/load_flow.py`
- Create: `src/igea_dgs/powerfactory/studies/short_circuit.py`
- Create: `src/igea_dgs/powerfactory/studies/__init__.py`
- Create: `tests/test_powerfactory_fidelity.py`
- Modify: `docs/POWERFACTORY_ACCEPTANCE.md`

**Interfaces:**
- Produces: `inspect_and_validate_pf(feeder, port)`, `run_original_load_flow`, `run_diagnostic_copy`, `run_short_circuit_if_complete`.

- [ ] **Step 1: Probar separación original/diagnóstico**

```python
def test_original_case_is_not_mutated_when_load_flow_diverges(fake_pf, feeder):
    before = fake_pf.snapshot()
    result = run_original_load_flow(fake_pf, feeder)
    assert result.converged is False
    assert fake_pf.snapshot() == before


def test_short_circuit_blocks_without_source_impedance(fake_pf, incomplete_source):
    result = run_short_circuit_if_complete(fake_pf, incomplete_source)
    assert result.status == "blocked"
    assert "SOURCE_SHORT_CIRCUIT_DATA_MISSING" in result.error_codes
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_powerfactory_fidelity.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implementar inspección independiente de objetos efectivos**

Comparar conteos, external IDs, tipos, fases, multiplicidad, conectividad, estados y atributos numéricos con tolerancias declaradas.

- [ ] **Step 4: Implementar flujo original inmutable**

No ejecutar los correction intents actuales sobre el caso original. La copia diagnóstica incluirá diff completo y nombre distinto.

- [ ] **Step 5: Implementar preflight IEC 60909**

Bloquear ComShc cuando falten datos mínimos de fuentes/generadores; distinguir falta de licencia de falta de datos.

- [ ] **Step 6: Ejecutar pruebas**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_powerfactory_fidelity.py tests/test_powerfactory_gate.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/igea_dgs/validation/powerfactory_model.py src/igea_dgs/powerfactory/studies tests/test_powerfactory_fidelity.py docs/POWERFACTORY_ACCEPTANCE.md
git commit -m "feat: separate original-case and diagnostic PF studies"
```

### Task 14: CLI integral y GUI delgada

**Files:**
- Create: `src/igea_dgs/services/pipeline.py`
- Create: `src/igea_dgs/services/__init__.py`
- Modify: `src/igea_dgs/cli.py`
- Modify: `src/igea_dgs/gui.py`
- Create: `tests/test_pipeline_service.py`
- Create: `tests/test_cli_commands.py`
- Create: `tests/test_gui_presenter.py`

**Interfaces:**
- Produces: `PipelineService.inspect/validate_input/convert/import_pf/validate_pf/study/run`.

- [ ] **Step 1: Probar que CLI y GUI comparten servicio**

```python
def test_run_stops_before_dgs_when_g2_blocks(fake_service, cli_runner):
    result = cli_runner("run", fixture="missing-conductor")
    assert result.exit_code == 2
    assert fake_service.calls == ["inspect", "validate_input"]


def test_gui_presenter_lists_trafomix_exclusions(summary):
    view = PipelinePresenter().render(summary)
    assert "TRAFOMIX excluidos" in view
    assert summary.exclusions[0].source_key in view
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_service.py tests/test_cli_commands.py tests/test_gui_presenter.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implementar servicio de aplicación**

El servicio es el único orquestador de puertas y publicación. GUI/CLI traducen entradas y presentan resultados.

- [ ] **Step 4: Implementar comandos**

Añadir `inspect`, `validate-input`, `convert`, `import-pf`, `validate-pf`, `study`, `run`, `catalog`; todos aceptan `--json` y devuelven 0/2/3 según éxito, bloqueo o API no disponible.

- [ ] **Step 5: Dividir GUI sin cambiar experiencia principal**

Extraer estado/presentador/worker; mostrar puerta actual, errores accionables, procedencia, cobertura y caso original frente a diagnóstico.

- [ ] **Step 6: Ejecutar pruebas**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_service.py tests/test_cli_commands.py tests/test_gui_presenter.py tests/test_batch_cli.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/igea_dgs/services src/igea_dgs/cli.py src/igea_dgs/gui.py tests/test_pipeline_service.py tests/test_cli_commands.py tests/test_gui_presenter.py
git commit -m "feat: expose strict pipeline through CLI and GUI"
```

### Task 15: Seguridad de exportaciones

**Files:**
- Modify: `src/igea_dgs/preview.py`
- Modify: `src/igea_dgs/export_tables.py`
- Create: `src/igea_dgs/reporting/sanitize.py`
- Create: `tests/test_export_security.py`

**Interfaces:**
- Produces: `escape_html_text`, `safe_script_json`, `neutralize_spreadsheet_formula`.

- [ ] **Step 1: Probar payloads hostiles**

```python
@pytest.mark.parametrize("value", ["</script><script>alert(1)</script>", "=WEBSERVICE(\"https://example.invalid\")", "+CMD|' /C calc'!A0"])
def test_untrusted_identifier_cannot_execute_in_exports(value, exporter):
    artifacts = exporter(value)
    assert "</script><script>" not in artifacts.html
    assert not artifacts.xlsx_cell.startswith(("=", "+", "-", "@"))
```

- [ ] **Step 2: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_export_security.py -v`  
Expected: FAIL.

- [ ] **Step 3: Implementar sanitización contextual**

Usar `html.escape`, reemplazo seguro de `</` en JSON embebido y prefijo apóstrofo para fórmulas; conservar el valor original en manifiesto JSON escapado por el serializador.

- [ ] **Step 4: Ejecutar Bandit y pruebas**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_export_security.py tests/test_preview.py tests/test_export_tables.py -v`  
Run: `.\.venv\Scripts\python.exe -m bandit -r src -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/igea_dgs/preview.py src/igea_dgs/export_tables.py src/igea_dgs/reporting/sanitize.py tests/test_export_security.py
git commit -m "fix: sanitize HTML and spreadsheet exports"
```

### Task 16: Casos dorados y validación científica

**Files:**
- Create: `tests/golden/README.md`
- Create: `tests/golden/manifest.schema.json`
- Create: `tests/golden/sample_balanced/expected.json`
- Create: `tests/golden/sample_unbalanced/expected.json`
- Create: `tests/golden/sample_generation/expected.json`
- Create: `src/igea_dgs/validation/kpis.py`
- Create: `tests/test_golden_feeders.py`

**Interfaces:**
- Produces: `compare_kpis(expected, actual, tolerances) -> KpiComparison`.

- [ ] **Step 1: Definir contrato dorado sin copiar resultados del conversor**

`expected.json` será preparado desde TXT revisado y export/medición PowerFactory independiente e incluirá hashes, revisor, tensiones, corrientes, P/Q, pérdidas, estados y tolerancias.

- [ ] **Step 2: Escribir prueba de desviación**

```python
def test_golden_voltage_outside_predeclared_tolerance_fails(golden, actual):
    actual.bus_voltage_pu["N2"] += Decimal("0.02")
    comparison = compare_kpis(golden, actual, golden.tolerances)
    assert comparison.passed is False
    assert comparison.failures[0].metric == "bus_voltage_pu"
```

- [ ] **Step 3: Confirmar fallo**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_golden_feeders.py -v`  
Expected: FAIL.

- [ ] **Step 4: Implementar comparación cuantitativa**

Tolerancias se declaran antes de ejecutar; comparar tensión por barra, corriente/carga por tramo, P/Q de fuentes y cargas, pérdidas y equipos en servicio.

- [ ] **Step 5: Ejecutar casos dorados**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_golden_feeders.py -v`  
Expected: PASS para fixtures sintéticos; casos reales permanecen bloqueados hasta que el usuario aporte/apruebe sus expectativas independientes.

- [ ] **Step 6: Commit**

```bash
git add tests/golden src/igea_dgs/validation/kpis.py tests/test_golden_feeders.py
git commit -m "test: add independent golden feeder validation"
```

### Task 17: Aceptación real en PowerFactory y cierre documental

**Files:**
- Modify: `README.md`
- Modify: `CODIGO_FUENTE.md`
- Modify: `docs/POWERFACTORY_ACCEPTANCE.md`
- Create: `docs/OPERATIONS_RUNBOOK.md`
- Create: `docs/DATA_DICTIONARY.md`
- Create: `docs/EQUIPMENT_CATALOG.md`
- Create: `scripts/acceptance.ps1`
- Create: `tests/test_documented_commands.py`

**Interfaces:**
- Produces: comando reproducible de aceptación y documentación operativa completa.

- [ ] **Step 1: Probar que los comandos documentados existen**

```python
def test_documented_cli_commands_are_registered():
    help_text = subprocess.run([sys.executable, "-m", "igea_dgs.cli", "--help"], check=True, capture_output=True, text=True).stdout
    for command in ("inspect", "validate-input", "convert", "import-pf", "validate-pf", "study", "run", "catalog"):
        assert command in help_text
```

- [ ] **Step 2: Ejecutar puerta local completa**

Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`  
Expected: Ruff, Mypy, Bandit, pip check y pytest PASS; cobertura de ramas críticas ≥90 %.

- [ ] **Step 3: Ejecutar conversión real en un directorio de aceptación nuevo**

Run: `powershell -ExecutionPolicy Bypass -File scripts/acceptance.ps1 -InputDir referencia -OutputDir output\acceptance_<run_id>`  
Expected: todo alimentador convertible queda `passed` o `blocked` por un dato concreto; ninguno usa fallback.

- [ ] **Step 4: Ejecutar aceptación real PowerFactory**

Usar Python 3.12 de PowerFactory y el proyecto administrado. Verificar importación, idempotencia de segunda ejecución, G5 y flujo original. No aceptar como PASS una copia con cargas escaladas/desconectadas.

- [ ] **Step 5: Revisar TRAFOMIX y generación con conteos antes/después**

El reporte debe demostrar claves excluidas, SED/cargas conservadas y todas las fuentes/plantas/generadores presentes o bloqueados con diagnóstico.

- [ ] **Step 6: Actualizar documentación con resultados reales**

Registrar fecha, hashes, versiones, número de alimentadores, resultados por puerta, convergencia original y limitaciones restantes.

- [ ] **Step 7: Ejecutar prueba documental y puerta final**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_documented_commands.py -v`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1`  
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add README.md CODIGO_FUENTE.md docs/POWERFACTORY_ACCEPTANCE.md docs/OPERATIONS_RUNBOOK.md docs/DATA_DICTIONARY.md docs/EQUIPMENT_CATALOG.md scripts/acceptance.ps1 tests/test_documented_commands.py
git commit -m "docs: publish validated local operating workflow"
```

## Iteration and Stop Rules

Después de cada Task:

1. ejecutar la prueba focal;
2. ejecutar las pruebas de regresión indicadas;
3. ejecutar Ruff/Mypy sobre archivos modificados;
4. revisar el diff;
5. corregir hasta verde;
6. crear el commit de la tarea;
7. no iniciar la siguiente tarea si existe un fallo no explicado.

Un alimentador bloqueado por datos reales no constituye un fallo del software si el diagnóstico identifica exactamente el dato necesario. No se relajará una regla para aumentar artificialmente el porcentaje de conversiones.

## Final Verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
powershell -ExecutionPolicy Bypass -File scripts/acceptance.ps1 -InputDir referencia -OutputDir output\acceptance_final
```

La entrega se considerará completa únicamente cuando:

- la instalación desde `.venv` sea reproducible;
- todas las pruebas locales pasen;
- todos los elementos TXT estén convertidos o bloqueados con causa verificable;
- no existan defaults físicos ni mappings aproximados;
- TRAFOMIX/carga estén excluidos sin perder SED/carga válida;
- una segunda ejecución PowerFactory sea idempotente;
- los reportes distingan caso original y copia diagnóstica;
- la aceptación real PowerFactory y sus limitaciones queden documentadas con evidencia.

