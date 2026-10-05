# SKILL: VNR-GIS-TO-CYMDIST-DIGSILENT-ETL
**Version:** 1.6.0 UNIVERSAL + DATABASE/BACKUP IMPORT + WEB UI | **Runtime:** Python 3.9+ | **Target:** Existing project / Cursor / VS Code

## 0. Mandatory agent contract
Integrate an auditable OSINERGMIN VNR/IGEA/GIS → CYMDIST → DIgSILENT converter into an existing project. Audit before coding. Prefer `REUSE`, then `ADAPT`; use `REPLACE` only with justification and mark missing pieces `MISSING`.

Hard rules: discovery is read-only; never invent IGEA endpoints, credentials, CRS, CYMDIST columns, DGS schemas or electrical parameters; preserve source IDs/lineage; separate GIS/topology from simulator serialization; make tolerances/mappings configurable; block strict export on mandatory validation failures; validate by simulator import/load flow when available; treat PDF extraction only as optional recovery.

## 1. Required outputs
CYMDIST (only against a verified organizational import contract): `CYM_SECTIONS.TXT`, `CYM_LOADS.TXT`, `CYM_EQUIPMENT.TXT`.

PowerFactory: `.DGS` generated from a known-good export/template from the exact target workflow. Do **not** assume DGS v4.0 until verified.

Required modes: `audit`, `validate`, `export-cymdist`, `export-dgs`, `export-all`.

## 2. Mandatory pre-implementation audit
Inspect `pyproject.toml`, `setup.py`, requirements, virtual environments, CLI, SQLAlchemy/PostGIS/Oracle/ODBC/GeoPandas/proprietary connectors, settings/secrets, GIS preprocessors, graph code, conductor/transformer/phase/voltage catalogs, VNR→CYM/DGS mappings, known-good CYMDIST/DGS files, tests, and existing IGEA/VNR integrations.

`audit` MUST NOT alter application source. Produce:
```text
AUDIT/
├── environment.md
├── project_structure.md
├── connectors.md
├── gis_modules.md
├── catalogs.md
├── cymdist_contract.md
├── dgs_contract.md
├── risks.md
└── integration_plan.md
```

## 3. Input contract
TRAMO: `COD_TRAMO, NODO_INI, NODO_FIN, COD_COND, FASES, geometry(LineString)`.

SEDES/CARGAS: `COD_SED, NODO_CONEX, KW_MEDIDO, KVAR_MEDID, FASES, geometry(Point)`.

Also ingest where available: sources, feeders, substations, transformers, switches, reclosers, fuses, capacitors, regulators, DG and equipment catalogs.

## 4. Canonical model
Never use simulator schemas as the core model.
- nodes: `node_id,x,y,nominal_kv,phases,source_layer,source_id`
- sections: `section_id,from_node,to_node,conductor_code,phases,nominal_kv,length_m,status,geometry,source_layer,source_id`
- loads: `load_id,connection_node,kw,kvar,phases,nominal_kv,geometry,source_layer,source_id`
- additional: `transformers,switches,sources,regulators,capacitors,equipment_catalog,lineage,validation_issues`

## 5. Architecture
```text
Existing project → AUDIT → CONNECTOR ADAPTERS → CANONICAL NORMALIZATION
→ CRS/GIS CLEANING → ENDPOINTS/SNAPPING → ELECTRICAL GRAPH
→ TOPOLOGY/ELECTRICAL QA → APPROVED CATALOG ENRICHMENT
→ [CYMDIST ADAPTER | DGS ADAPTER] → EXPORT QA → IMPORT QA → LOAD-FLOW QA
```

## 6. Environment
Audit dependency management before installing anything. Compatible baseline:
```bash
python -m pip install opencv-python numpy pdf2image requests pandas geopandas shapely pyproj networkx sqlalchemy openpyxl
```
Optional DB driver example: `python -m pip install psycopg2-binary`. `pdf2image` requires Poppler; do not require it if PDF recovery is disabled.

Standalone test environment:
```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
```

## 7. Configuration
```yaml
project: {mode: audit, strict: true}
gis:
  source_crs: null
  working_crs: null
  snap_tolerance_m: 0.50
  equipment_snap_tolerance_m: 1.00
validation:
  allow_islands: false
  allow_self_loops: false
  require_source: true
  require_catalog_mapping: true
exports: {cymdist_enabled: true, dgs_enabled: true, output_dir: output}
templates: {cymdist: null, dgs: null}
```
CRS must come from authoritative metadata. EPSG:32718 is only an example for some Peru UTM 18S data.

Secrets:
```python
import os
IGEA_API_URL = os.getenv('IGEA_API_URL')
IGEA_API_TOKEN = os.getenv('IGEA_API_TOKEN')
```

## 8. Connector abstraction
```python
from typing import Protocol
class NetworkSource(Protocol):
    def load_sections(self): ...
    def load_loads(self): ...
    def load_transformers(self): ...
    def load_switches(self): ...
    def load_sources(self): ...
```
Wrap existing connectors rather than replacing them.

## 9. GIS/CRS rules
Reject unknown CRS in strict mode; use projected CRS for metric length/snapping; never snap in geographic degrees; log geometry repairs; preserve originals; lines should normally be LineString/MultiLineString and equipment Point.

## 10. Snapping
For projected endpoints: `distance(Pi,Pj) <= epsilon → same canonical node`.

Extract endpoints → spatial index → cluster within tolerance → deterministic node IDs → snap terminals → associate equipment with separate tolerance → log displacement → flag excessive corrections.

Audit: `source_object,original_x,original_y,snapped_node,snapped_x,snapped_y,distance_m,rule,status`.

## 11. Graph validation
Use NetworkX or existing graph code. Detect isolated nodes, islands, duplicates, self-loops, orphan loads, invalid switch/transformer terminals, missing source/slack, phase discontinuity, incompatible voltage and impossible source-to-load paths. Loops require operating-state analysis and are not automatically errors.

## 12. Electrical enrichment
Approved conductor mapping may require `COD_COND → material,section,R1,X1,R0,X0,ampacity,nominal_kv`.

Transformer mapping may require `Sn,HV/LV,vector_group,uk%,copper_loss,no_load_loss,taps,grounding`.

Never fabricate missing parameters.
```python
S_kva = (kw**2 + kvar**2) ** 0.5
pf = kw / S_kva if S_kva else 1.0
```
Validate P/Q, signs, phases, node, voltage and PF.

## 13. Optional PDF/OpenCV recovery
The pasted OpenCV concept is an optional preprocessor only. `findContours()` detects graphic contours, not electrical topology. Two-corner pixel/GPS interpolation is not production georeferencing.

Dependencies:
```bash
python -m pip install opencv-python numpy pdf2image requests
```
Reference extraction:
```python
import cv2
import numpy as np
from pdf2image import convert_from_path

def extract_candidate_shapes(pdf_path):
    images = convert_from_path(pdf_path)
    if not images:
        raise ValueError('No renderable PDF pages')
    frame = np.array(images[0])
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [c for c in contours if cv2.contourArea(c) > 500]
```
Production: `PDF → control points → georeferencing → projected CRS → line/point extraction → LineString reconstruction → intersections/endpoints → snapping → classification → QA → canonical staging`.

Do not POST recovered geometry to IGEA until the real endpoint, authorization and payload schema are verified.

## 14. CYMDIST adapter
Output:
```text
output/cymdist/
├── CYM_SECTIONS.TXT
├── CYM_LOADS.TXT
└── CYM_EQUIPMENT.TXT
```
Use exact columns, delimiter, encoding, units and semantics from a verified target sample; deterministic ordering; stable IDs; valid node/phase/equipment references. Do not hard-code speculative columns. Prefer declarative mapping.

## 15. PowerFactory DGS adapter
Must be template/schema-driven from a known-good target export. Conceptual mapping: node→terminal/bus; section→line/cable; conductor→line type; load→load; transformer→transformer/type; switch→switching object; source→external grid/source.

Validate references, nominal voltage, phases, lengths/types, transformer data, P/Q, source/slack, encoding and headers. Never invent DGS classes/headers.

## 16. Exporter interface
```python
from typing import Protocol
from pathlib import Path
class SimulatorExporter(Protocol):
    def validate_mapping(self, model) -> list: ...
    def export(self, model, output_dir: Path) -> list[Path]: ...
```

## 17. Validation gates
A Source/schema. B GIS/CRS. C Topology/snapping. D Electrical. E Simulator mapping. F Serialization/round-trip. G Simulator import. H Load-flow convergence/energization/voltage/loading/P-Q/losses/disconnected loads.

Strict mode blocks production export on mandatory-gate failure.

## 18. CLI contract
```bash
python -m vnr_etl audit --project .
python -m vnr_etl validate --config config/settings.yaml
python -m vnr_etl export-cymdist --config config/settings.yaml
python -m vnr_etl export-dgs --config config/settings.yaml
python -m vnr_etl export-all --config config/settings.yaml
python -m vnr_etl plan-integration --project . --output AUDIT/integration_plan.md
```
No automatic migration until safe insertion points are identified.

## 19. Existing-project workflow
1. Read-only discovery.
2. Integration plan naming exact files to reuse/add/change.
3. Wrap existing connectors/exporters behind adapters; avoid broad refactors.
4. Add canonical model only if no equivalent exists.
5. Normalize copies; preserve original GIS/database records.
6. Reuse approved electrical catalogs.
7. Enable simulator adapters only after target contracts are verified.
8. Run regression tests.
9. Import outputs and run controlled load flow when simulators are available.

## 20. Recommended layout
```text
project/
├── existing_application/
├── vnr_etl/
│   ├── cli.py
│   ├── config.py
│   ├── audit/
│   ├── connectors/
│   ├── models/
│   ├── gis/
│   ├── topology/
│   ├── electrical/
│   ├── catalogs/
│   ├── exporters/{cymdist.py,dgs.py}
│   └── validation/
├── config/{settings.yaml,field_mapping.yaml,vnr_to_cym.yaml,vnr_to_dgs.yaml}
├── tests/
└── output/
```
If equivalents already exist, integrate there instead of mechanically creating this tree.

## 21. Minimum tests
Missing/malformed fields fail clearly; unknown CRS fails in strict mode; snapping is deterministic; no unintended merges beyond tolerance; valid terminals; orphan loads and phase/voltage mismatches detected; missing conductor mappings block strict export; CYMDIST/DGS references resolve; identical input yields deterministic output; existing regression tests still pass.

## 22. Transaction/rollback
Discovery is read-only. Write generated artifacts to staging/output until validation succeeds. Do not mutate source GIS/database by default. Future write-back must be a separate opt-in adapter with dry-run, authorization, logging and rollback/compensation. Use version control/backups before modifying project files.

## 23. Logging
Log `run_id,timestamp,source,object_type,source_id,stage,severity,code,message`.

Report counts, invalid geometries, snapped endpoints, mean/max displacement, islands, orphans, unresolved mappings, export counts and simulator errors/warnings.

## 24. Acceptance criteria
Production-ready only when audit/integration plan are complete; ingestion has no silent loss; CRS/topology pass or exceptions are documented; electrical mappings resolve; equipment references valid nodes; CYMDIST matches verified contract and import test; DGS matches verified contract and import test; controlled load flow passes; all simulator objects trace to source; existing project regression tests pass.

## 25. Functional audit matrix
| Component | Specification | Immediately implementable | External evidence required |
|---|---|---|---|
| Repository audit | Complete | Yes | Target project for real findings |
| Canonical model | Complete | Yes | No |
| CRS/snapping | Complete | Yes | Real GIS for acceptance |
| Graph QA | Complete | Yes | Real network for acceptance |
| PDF candidate extraction | Complete | Yes with Poppler | PDF |
| IGEA write-back | Guarded | No | Verified API contract |
| CYMDIST serialization | Architecture complete | Not final | Known-good CYMDIST sample/schema |
| DGS serialization | Architecture complete | Not final | Known-good DGS/template |
| Import/load-flow QA | Defined | No | Target simulator |

## 26. Audit conclusion
This MD is **functional as a complete integration specification and coding-agent contract** for importing the converter into an existing project. It intentionally prevents false completeness where external contracts are unknown.

The audit, canonical model, GIS normalization, snapping, graph, catalog validation, CLI and QA layers can be implemented immediately. Final CYMDIST/DGS serialization is production-valid only after discovering an existing exporter or verifying known-good target files. IGEA write-back remains disabled until the actual API is verified.

## 27. Instruction to the coding agent
When this MD is placed in a repository: run read-only audit; create `AUDIT/integration_plan.md`; identify reuse/insertion points; locate CYMDIST/DGS reference files; implement only missing layers with tests; run validation gates after each layer; do not enable production export prematurely; produce a final change report; run regression tests and simulator acceptance tests where available.

---
**End of SKILL v1.2.0**

# ADDENDUM v1.3.0 — REAL OSINERGMIN VNR/GIS ADAPTER

## A. Verified public OSINERGMIN GIS source

The implementation MUST support ArcGIS REST Feature/Map services rather than relying only on hypothetical local VNR columns.

Verified service family:

```text
https://gisem.osinergmin.gob.pe/serverch/rest/services/Electricidad/Electricidad/MapServer
```

Verified distribution group/layers include:

```text
20 Distribución
21 Salida MT SET
22 Tramo Media Tensión
23 Estructuras MT
24 Subestación de Distribución
27 Estructuras BT
28 Tramo Baja Tensión
29 Acometidas
30 Suministros
31 Tramo Alumbrado Público
32 Alumbrado Público
33 Área de Concesión
```

The public service reports EPSG:4326. It supports JSON/GeoJSON/PBF queries. Therefore the connector must read the layer metadata first and paginate according to `maxRecordCount`; it must not assume a single query returns the full network.

### A.1 Verified MT layer contract

For public `Tramo Media Tensión` (layer 22), verified fields include:

```text
OBJECTID
CODEMP
CODTRAMOMT
CODTIPORED
LONGITUD
PROPIEDAD
FECPUESTASERVICIO
SHAPE
TIPO_CENT
FECHA_PS
```

Geometry type: `esriGeometryPolyline`.

IMPORTANT: the public layer does NOT establish that `NODO_INI`, `NODO_FIN`, `COD_COND` or `FASES` exist. Those names from earlier drafts are canonical/internal fields, not guaranteed OSINERGMIN public fields.

### A.2 Richer VNR-related MT source

A verified OSINERGMIN FeatureServer layer named `Tramo Red MT Existente` exposes a richer VNR-oriented schema. Available metadata includes fields/prototype attributes such as:

```text
CODEMP
CODTRAMOMT
CODSALIDAMT
CODTRAMOMTPADRE
CODTENNOMI
CODTIPOCIRCUITO
CODNORMANEUTRO
CODTIPORED
CODSOPORTE
CODNORMA
ESTADOVNR
LONGITUD
FECPUESTASERVICIO
FECRETIRO
SECVERTICE
ANIO
SECTOR
CENTRO
```

The connector MUST discover the actual layer schema at runtime because OSINERGMIN services/layers may evolve.

## B. Regulatory/data-model grounding

OSINERGMIN Resolution 232-2017-OS/CD approves the Guide for preparation of VNR of electrical distribution installations. VNRGIS contains alphanumeric technical data and geographic coordinates used for distribution-installation information. The VNR process validates database structure/coding and georeferenced consistency.

Current OSINERGMIN technical documentation also states that graphical distribution information uses UTM coordinates with PSAD56 or WGS84, with the company information submitted consistently in the same datum and UTM zone 17, 18 or 19. Therefore:

- public REST data in EPSG:4326 must be reprojected before metric snapping;
- native company VNRGIS datasets may use UTM and must retain their declared datum/zone;
- the converter MUST inspect CRS metadata rather than hard-code EPSG:32718.

## C. Real ArcGIS REST connector

```python
from dataclasses import dataclass
import requests
import geopandas as gpd

@dataclass
class ArcGISLayer:
    url: str
    timeout: int = 60

    def metadata(self) -> dict:
        r = requests.get(self.url, params={"f": "json"}, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        return data

    def field_names(self) -> set[str]:
        return {f["name"] for f in self.metadata().get("fields", [])}

    def query_geojson(self, where="1=1", out_fields="*", page_size=None):
        meta = self.metadata()
        oid = meta.get("objectIdField") or meta.get("objectIdFieldName") or "OBJECTID"
        limit = int(page_size or meta.get("maxRecordCount", 1000))
        offset = 0
        features = []

        while True:
            params = {
                "f": "geojson",
                "where": where,
                "outFields": out_fields,
                "returnGeometry": "true",
                "outSR": 4326,
                "resultOffset": offset,
                "resultRecordCount": limit,
                "orderByFields": f"{oid} ASC",
            }
            r = requests.get(f"{self.url}/query", params=params, timeout=self.timeout)
            r.raise_for_status()
            page = r.json()
            if "error" in page:
                raise RuntimeError(page["error"])
            batch = page.get("features", [])
            features.extend(batch)
            if len(batch) < limit:
                break
            offset += len(batch)

        return gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
```

Production connector requirements:
- retry/backoff;
- connection timeout;
- pagination;
- layer metadata caching;
- schema discovery;
- filter by `CODEMP`/feeder/system when available;
- response count verification;
- provenance containing service URL, layer ID, retrieval timestamp and OBJECTID.

## D. Runtime schema adapter

Do not bind the ETL directly to one historical VNR schema.

```python
ALIASES = {
    "section_id": ["CODTRAMOMT", "COD_TRAMO", "section_id"],
    "company": ["CODEMP", "EMPRESA", "company"],
    "feeder_id": ["CODSALIDAMT", "ALIMENTADOR", "feeder_id"],
    "parent_section": ["CODTRAMOMTPADRE", "parent_section"],
    "network_type": ["CODTIPORED", "network_type"],
    "nominal_voltage_code": ["CODTENNOMI", "nominal_voltage_code"],
    "standard_code": ["CODNORMA", "standard_code"],
    "length_source": ["LONGITUD", "length_source"],
}
```

Resolution algorithm:
1. inspect actual source fields;
2. select first valid alias;
3. report unresolved canonical fields;
4. classify each field as `SOURCE`, `DERIVED`, `CATALOG`, or `MISSING`;
5. never fabricate a value.

## E. Node reconstruction

Because public MT geometry is polyline-based and may not expose explicit terminal-node IDs, create canonical nodes from geometry.

```python
from shapely.geometry import Point

def endpoints(line):
    coords = list(line.coords)
    return Point(coords[0]), Point(coords[-1])
```

For `MultiLineString`, normalize/merge valid connected parts before endpoint generation or explicitly explode with source lineage.

Node construction:
1. reproject EPSG:4326 data to the correct local projected CRS;
2. extract all section endpoints;
3. cluster endpoints within `snap_tolerance_m`;
4. create deterministic IDs from cluster coordinates/hash;
5. assign `from_node` and `to_node`;
6. preserve original endpoints and displacement;
7. compare graph adjacency with `CODTRAMOMTPADRE` where that attribute exists.

`CODTRAMOMTPADRE` is supporting connectivity evidence, not a substitute for geometric/topological QA.

## F. Electrical enrichment rule

The public GIS layer alone is NOT sufficient for a PowerFactory/CYMDIST load-flow model. A second technical source/catalog is required for parameters not present in the published layer.

Required enrichment matrix:

| Canonical value | Preferred source |
|---|---|
| section ID | CODTRAMOMT |
| feeder | CODSALIDAMT if available |
| network type | CODTIPORED |
| nominal voltage | CODTENNOMI or approved catalog |
| conductor/equipment standard | CODNORMA / company VNR catalog |
| length | geometry-derived + LONGITUD cross-check |
| from/to nodes | topology-derived or authoritative native nodes |
| phases | native VNR/company GIS/catalog; never guessed |
| R1/X1/R0/X0 | approved conductor catalog |
| ampacity | approved conductor catalog |
| load P/Q | operational/commercial/SCADA/load database |
| source/slack | SET/feeder source model |

The converter MUST produce a `missing_electrical_data.csv` report and block strict simulator export when required load-flow attributes remain unresolved.

## G. Geometry length QA

For every MT section calculate metric GIS length after projection and compare it with `LONGITUD` when parseable:

```text
delta_m = abs(length_gis_m - length_source_m)
delta_pct = 100 * delta_m / max(length_source_m, epsilon)
```

Configurable warnings/errors:

```yaml
qa:
  length_warn_pct: 2.0
  length_error_pct: 10.0
```

Do not silently replace authoritative values; record both values and the selected rule.

## H. Real-source extraction workflow

```text
OSINERGMIN ArcGIS REST
       ↓ metadata()
discover fields + CRS + maxRecordCount
       ↓
paged GeoJSON query
       ↓
filter company/feeder
       ↓
GeoDataFrame EPSG:4326
       ↓
select correct projected CRS
       ↓
normalize LineString/MultiLineString
       ↓
derive/check lengths
       ↓
endpoints
       ↓
snapping
       ↓
canonical nodes/sections
       ↓
join native VNR/company catalogs
       ↓
join conductor/equipment parameters
       ↓
join load P/Q
       ↓
topology/electrical QA
       ↓
CYMDIST adapter / DGS adapter
```

## I. Required audit command for a real project

Before integration the agent must execute conceptually:

```text
vnr_etl audit-source --url <arcgis-layer>
vnr_etl audit-project --project .
vnr_etl discover-schema --source osinergmin
vnr_etl validate-topology --config config/settings.yaml
```

Expected audit-source report:

```json
{
  "source_type": "arcgis_rest",
  "layer_name": "Tramo Media Tensión",
  "geometry_type": "esriGeometryPolyline",
  "source_crs": 4326,
  "fields": [],
  "max_record_count": 0,
  "canonical_mapping": {},
  "missing_required": [],
  "warnings": []
}
```

## J. Integration with an existing converter

The agent MUST search the repository for:
- existing IGEA TXT readers;
- GIS database connectors;
- existing DGS writer;
- CYMDIST import/export mappings;
- conductor/equipment libraries;
- topology utilities;
- PowerFactory object mapping;
- tests based on previously successful exports.

If an existing DGS converter already works, preserve it and feed it the canonical model rather than replacing it.

## K. Functional test levels

### L0 — metadata
Pass when ArcGIS layer metadata and fields are discovered.

### L1 — extraction
Pass when paginated features are retrieved without count loss.

### L2 — GIS
Pass when CRS, geometry and metric length QA complete.

### L3 — topology
Pass when nodes/edges are deterministic and unexplained islands/orphans are reported.

### L4 — electrical
Pass when voltage, phase, conductor and load requirements are resolved or explicitly blocked.

### L5 — serialization
Pass when CYMDIST/DGS files satisfy verified target templates.

### L6 — simulator
Pass only after successful import into target CYMDIST/PowerFactory.

### L7 — load flow
Pass after convergence and engineering sanity checks.

## L. Production definition

A successful download from OSINERGMIN GIS is NOT by itself a completed electrical converter.

The implementation is production-functional only when:
- public/native VNR GIS extraction works;
- topology is reconstructed and validated;
- required electrical catalogs are joined;
- P/Q loads and source data are available;
- simulator mappings come from verified examples/templates;
- generated files import successfully;
- a controlled load flow passes QA.

This design permits immediate implementation against the real OSINERGMIN ArcGIS REST source while preventing unsupported assumptions about fields that the public service does not contain.


# UNIVERSAL EXTENSION v1.4 — ANY PERUVIAN VNRGIS COMPANY/PERIOD

## U1. Universal scope

The converter MUST NOT contain company-specific conversion logic. Electro Dunas (`ELDU`) is a validation fixture/case, never the canonical schema.

Supported dimensions are discovered at runtime:

```text
company → period/year → electrical system → feeder → layers/tables → schema → CRS/datum
```

The same pipeline must accept another distribution company without source-code modification when its data complies with a supported VNRGIS family or can be mapped through configuration.

## U2. Supported input modes

### MODE A — OSINERGMIN ArcGIS REST
Discover service/layer metadata, query features with pagination, retain `CODEMP/EMPRESA`, `ANIO`, system and feeder identifiers where present.

### MODE B — Official VNRGIS package
Accept `.zip/.rar` after safe extraction through an available extractor and inventory contained formats before reading them. Supported adapters may include SHP/DBF, GeoPackage, CSV/TXT, MDB/ACCDB or other audited formats. A missing reader must generate a dependency/adaptor requirement, not silent conversion.

### MODE C — Utility native VNRGIS
Read a local folder/database supplied by the distribution company. Preserve native identifiers and declared CRS/datum.

### MODE D — Existing GIS project/database
Adapters for PostGIS, Oracle Spatial, GeoPackage, SHP or an existing project connector. Reuse the host project's connector when possible.

## U3. Source fingerprint and version discovery

Every run creates:

```json
{
  "source_family": null,
  "source_uri_hash": null,
  "company_field": null,
  "company_values": [],
  "period_field": null,
  "period_values": [],
  "layers": [],
  "crs": null,
  "schema_fingerprint": null,
  "adapter_version": "1.4.0"
}
```

`schema_fingerprint` is a deterministic hash of normalized layer/table names, field names/types and geometry types. It is used to detect a changed quarterly/yearly schema without assuming a fixed publication schedule.

## U4. Semantic Schema Discovery Engine

Canonical concepts and aliases:

```yaml
company:
  aliases: [CODEMP, EMPRESA, COD_EMPRESA, EMP]
period:
  aliases: [ANIO, AÑO, PERIODO, YEAR]
system_id:
  aliases: [SISTEMA, CODSISTEMA, COD_SISTEMA]
system_name:
  aliases: [SISTEMA0, NOM_SISTEMA, SISTEMA_ELECTRICO]
feeder_id:
  aliases: [CODSALIDAMT, ALIMENTADOR, COD_ALIMENTADOR]
section_id:
  aliases: [CODTRAMOMT, COD_TRAMO, TRAMO, SECTION_ID]
sed_id:
  aliases: [CODSED, COD_SED]
set_id:
  aliases: [CODSET, COD_SET]
vnr_code:
  aliases: [CODNORMA, COD_VNR, CODVNR]
status:
  aliases: [ESTADOVNR, ESTADO]
```

Resolution order:
1. exact canonical name;
2. exact known alias;
3. normalized alias (case/accent/underscore normalization);
4. explicit project mapping;
5. semantic suggestion requiring approval in strict mode.

Never map only because two columns have compatible data types.

For each canonical field write lineage:

```text
canonical_field
source_layer
source_field
resolution_method
confidence
transform
null_count
distinct_count
```

## U5. Company independence

Forbidden:
```python
if company == "ELDU":
    # conversion rules
```

Allowed:
```python
adapter = registry.resolve(source_fingerprint)
mapping = schema_discovery.resolve(adapter, source_metadata)
model = canonicalizer.build(source, mapping)
```

Company-specific exceptions, if unavoidable, belong in declarative configuration with reason, validity period and tests:

```yaml
overrides:
  - company: ELDU
    valid_from: null
    valid_to: null
    reason: "documented source exception"
    mapping: {}
```

No override is permitted merely to make a failing test pass.

## U6. Period/quarter handling

Do not infer that every public endpoint represents the newest quarterly VNRGIS. The converter must determine freshness from source metadata/records and report:

```text
company
available_periods
selected_period
record_date_range
retrieved_at
source_service_or_file
```

Selection policies:
- `latest_available`: select maximum authoritative period found;
- `explicit`: require requested year/period;
- `all`: preserve all periods and partition output.

Never label a dataset “2026 quarterly VNRGIS” unless the source itself establishes that period.

## U7. CRS/datum discovery

Decision sequence:
1. read authoritative layer/file CRS;
2. read declared VNR datum/zone metadata if native source provides it;
3. compare coordinate ranges for anomaly detection only;
4. require explicit resolution if metadata conflicts;
5. transform to a metric working CRS for topology;
6. preserve original CRS and coordinates.

Do not guess WGS84/PSAD56 or UTM zone solely from company identity.

## U8. Universal layer classifier

Classify source tables/layers by schema + geometry + metadata:

```text
SOURCE/SUBSTATION
FEEDER
MT_SECTION
MT_STRUCTURE
DISTRIBUTION_SUBSTATION
BT_SECTION
SUPPLY/CUSTOMER
SWITCH
TRANSFORMER
REGULATOR
CAPACITOR
CATALOG
UNKNOWN
```

Unknown layers are inventoried and retained; they are not discarded.

## U9. Canonical electrical model v1

```text
Company
Period
System
Feeder
Source
Node
Section
Structure
Transformer
Switch
Regulator
Capacitor
Load
Supply
EquipmentType
ConductorType
Lineage
ValidationIssue
```

All simulator exporters consume this model. They never directly consume OSINERGMIN-specific tables.

## U10. Universal extraction interface

```python
class VNRSourceAdapter:
    def probe(self, source): ...
    def metadata(self): ...
    def list_layers(self): ...
    def read_layer(self, layer, filters=None): ...
    def available_companies(self): ...
    def available_periods(self, company=None): ...
    def close(self): ...
```

Registry:

```python
ADAPTERS = [
    ArcGISRestAdapter,
    GeoPackageAdapter,
    ShapefileFolderAdapter,
    DelimitedTextAdapter,
    PostGISAdapter,
    OracleSpatialAdapter,
    AccessVNRAdapter,
]
```

Adapters unavailable because an optional driver is missing must return a clear install/action requirement.

## U11. ArcGIS pagination and count reconciliation

Before downloading a layer:
1. request metadata;
2. request `returnCountOnly=true`;
3. page according to supported pagination/max record count;
4. deduplicate by ObjectID;
5. compare downloaded unique records with server count;
6. fail/retry on unexplained mismatch.

This prevents silent truncation at ArcGIS record limits.

## U12. Topology reconstruction hierarchy

Preferred connectivity evidence:
1. authoritative explicit native node IDs;
2. documented parent/terminal relationships;
3. geometric endpoints/intersections;
4. snapping within configured tolerance.

If explicit topology and geometry disagree, retain both and emit a conflict. Never silently choose one.

## U13. Multi-company validation suite

Minimum fixtures:
- Electro Dunas dataset/sample;
- at least one different OSINERGMIN company;
- synthetic edge cases.

Tests must prove:
- no company name/code is required in core conversion functions;
- alias differences resolve correctly;
- period selection works;
- schema fingerprints change when fields change;
- unknown fields/layers are preserved in inventory;
- output canonical schema is identical across companies;
- identical canonical models yield identical simulator serialization independent of source company.

## U14. CYMDIST and PowerFactory remain target adapters

Universal source support does not mean speculative target formats.

```text
ANY VNRGIS
   ↓
UNIVERSAL CANONICAL MODEL
   ├── CYMDIST TargetProfile
   └── PowerFactory DGSTargetProfile
```

Each `TargetProfile` records:
- simulator/version/workflow;
- verified sample/template hash;
- encoding/delimiter;
- object/table mapping;
- required fields;
- units;
- validation rules.

A new simulator version can therefore be supported without modifying source adapters.

## U15. CLI v1.4

```bash
python -m vnr_etl probe SOURCE
python -m vnr_etl companies SOURCE
python -m vnr_etl periods SOURCE --company CODE
python -m vnr_etl inventory SOURCE
python -m vnr_etl audit SOURCE --project .
python -m vnr_etl convert SOURCE --company CODE --period latest_available
python -m vnr_etl validate output/canonical
python -m vnr_etl export-cymdist output/canonical --profile config/cymdist.yaml
python -m vnr_etl export-dgs output/canonical --profile config/powerfactory.yaml
```

No `--company` is required when the source contains exactly one unambiguous company.

## U16. Incremental/period comparison

For successive VNRGIS deliveries calculate by stable source ID:

```text
ADDED
REMOVED
MODIFIED_GEOMETRY
MODIFIED_ATTRIBUTES
UNCHANGED
UNRESOLVED_IDENTITY
```

Produce:
`period_diff_sections.csv`, `period_diff_seds.csv`, `period_diff_equipment.csv`.

This supports periodic updates without rebuilding trust in the entire source manually.

## U17. Data-quality report

Per company/period:
- layer and record counts;
- null/duplicate IDs;
- geometry errors;
- CRS conflicts;
- topology islands/orphans;
- snapping statistics;
- voltage/phase inconsistencies;
- catalog coverage;
- missing electrical parameters;
- source-to-canonical mapping coverage;
- target-export readiness.

Readiness states:
`DISCOVERED → NORMALIZED → TOPOLOGY_VALID → ELECTRICALLY_ENRICHED → EXPORT_READY → SIMULATOR_VALIDATED`.

## U18. Current OSINERGMIN REST evidence used by this design

The official OSINERGMIN `VNR_GIS_INTERRUPCIONES` ArcGIS service exposes separate layers for substations, feeders, electrical systems, companies and supplies. Its feeder layer exposes fields including `CODEMP`, `CODSALIDAMT`, `ANIO`, `ALIMENTADOR`, `SISTEMA`, `SISTEMA0` and `COD_VNR`, uses EPSG:4326, supports GeoJSON and pagination. The company layer illustrates schema variation by using fields such as `EMPRESA` and `NOM_EMP`.

Therefore runtime discovery is a required engineering feature, not an optional convenience.

## U19. Universal acceptance test

The skill is accepted as UNIVERSAL only after:
1. two different real companies can be probed without source-code edits;
2. available periods are discovered from records/metadata;
3. both normalize to the same canonical schema;
4. topology QA runs on both;
5. missing electrical attributes are reported rather than invented;
6. one verified target profile exports a structurally valid simulator file;
7. simulator import is successful;
8. regression tests confirm the first company still works after adding the second.

## U20. Implementation directive

When imported into an existing converter project, implement in this order:

```text
READ-ONLY PROJECT AUDIT
→ SOURCE PROBE
→ ADAPTER REGISTRY
→ SCHEMA DISCOVERY
→ SOURCE FINGERPRINT
→ CANONICAL MODEL
→ CRS/NORMALIZATION
→ TOPOLOGY
→ ELECTRICAL ENRICHMENT
→ PERIOD DIFF
→ TARGET PROFILES
→ CYMDIST/DGS EXPORT
→ SIMULATOR QA
```

Do not start by rewriting the DGS writer or by special-casing Electro Dunas.


# UNIVERSAL VNRGIS DISCOVERY & DOWNLOAD MANAGER — v1.5

## D1. Purpose

The skill MUST be capable of discovering, cataloguing, selecting and downloading the newest verifiable VNRGIS information published by OSINERGMIN for any electricity distribution company, without hard-coding a fixed list of companies, a fixed year, or a guessed URL.

The discovery layer is separate from the electrical conversion layer:

```text
OSINERGMIN OFFICIAL SOURCES
          ↓
SOURCE DISCOVERY
          ↓
PUBLICATION CATALOG
          ↓
COMPANY/PERIOD RESOLUTION
          ↓
DOWNLOAD / REST EXTRACTION
          ↓
HASH + MANIFEST + CACHE
          ↓
VNR SOURCE ADAPTER
          ↓
UNIVERSAL CANONICAL MODEL
          ↓
CYMDIST / POWERFACTORY
```

## D2. Authoritative-source policy

Discovery MUST prioritize official OSINERGMIN domains and services. The manager may use:
1. OSINERGMIN regulatory-process pages containing VNR/VNRGIS publications and company download links.
2. OSINERGMIN resolutions and their annex/publication pages.
3. Official `www2.osinergmin.gob.pe/GRT/Procesos-Regulatorios/VNR/...` downloadable artifacts.
4. Official OSINERGMIN ArcGIS REST directories/services as complementary GIS sources.
5. Other OSINERGMIN official endpoints discovered from the above.

Search-engine results are discovery hints only. Before download, resolve and validate the final host as an allowed official OSINERGMIN source unless an operator explicitly approves another source.

## D3. Never confuse publication families

The manager MUST classify each discovered source, for example:

```text
REGULATORY_VNRGIS_PACKAGE
REGULATORY_VNR_PUBLICATION
ARCGIS_PUBLIC_REFERENCE
INTERRUPTION_GIS
SICODI
MAP_DENSITY
MANUAL_INSTALLER
UNKNOWN
```

A public ArcGIS service whose description identifies an older VNR year MUST NOT be labeled as the newest regulatory VNRGIS simply because the service is online today.

## D4. Dynamic company registry

Do not maintain a manually frozen company list as the primary registry.

Build the company catalog dynamically from:
- company entries on the selected official VNRGIS publication;
- company attributes from official GIS layers;
- aliases found in official publications.

Canonical company record:

```json
{
  "company_id": "stable-internal-id",
  "codes": ["..."],
  "official_name": "...",
  "aliases": ["..."],
  "source_refs": ["..."],
  "first_seen": null,
  "last_seen": null
}
```

Aliases/name changes must not create duplicate companies when authoritative evidence establishes identity continuity.

## D5. Publication catalog

Every discovered VNR/VNRGIS publication becomes a catalog record:

```json
{
  "publication_id": "...",
  "title": "...",
  "publication_type": "REGULATORY_VNRGIS_PACKAGE",
  "regulatory_reference": "...",
  "reference_date": "...",
  "published_at": "...",
  "discovered_at": "...",
  "official_page": "...",
  "company": "...",
  "company_code": "...",
  "period_label": "...",
  "download_url": "...",
  "file_name": "...",
  "file_type": "...",
  "status": "DISCOVERED"
}
```

The catalog MUST preserve older publications. Never overwrite history when a newer VNRGIS appears.

## D6. Freshness resolver

`latest` means newest authoritative publication discovered for the requested company/source family, not today's server timestamp.

Selection algorithm:
1. filter official-source records;
2. filter `REGULATORY_VNRGIS_PACKAGE` when regulatory VNRGIS is requested;
3. resolve company identity;
4. extract authoritative reference/publication dates and period labels;
5. rank only records with defensible dates;
6. select newest;
7. report ambiguity instead of guessing when dates/periods conflict.

Return:

```json
{
  "company": "...",
  "requested": "latest",
  "selected_publication": "...",
  "reference_period": "...",
  "published_at": "...",
  "confidence": "HIGH|MEDIUM|LOW",
  "alternatives": []
}
```

## D7. Search strategy

Discovery is multi-stage:

```text
A. Check known official regulatory index/process pages
B. Follow links to current VNR/VNRGIS process
C. Parse downloadable company artifacts
D. Enumerate company names/codes
E. Inspect official ArcGIS service directory for complementary sources
F. Reconcile with local publication catalog
G. Add only new/changed records
```

The implementation SHOULD support a pluggable web-discovery provider because search interfaces can change. HTML/link parsing and ArcGIS REST discovery must be independent modules.

## D8. Official-host allowlist

Default:

```yaml
discovery:
  allowed_hosts:
    - osinergmin.gob.pe
    - www.osinergmin.gob.pe
    - www2.osinergmin.gob.pe
    - gisem.osinergmin.gob.pe
```

Subdomains discovered from official OSINERGMIN pages can be proposed but require validation before automatic download.

Reject:
- lookalike domains;
- URL shorteners;
- third-party mirrors by default;
- executable downloads unless explicitly required and approved.

## D9. Download manager

Required features:
- streaming download;
- connect/read timeout;
- retry with exponential backoff;
- resumable download when server supports ranges;
- maximum configurable file size;
- temporary `.part` file;
- atomic rename after success;
- SHA-256;
- content-length check where available;
- MIME/extension sanity check;
- archive integrity test;
- cache;
- force-refresh option.

Pseudo-interface:

```python
class VNRDownloadManager:
    def download(self, publication, destination, force=False): ...
    def verify(self, path, expected=None): ...
    def cached(self, publication): ...
```

## D10. Download manifest

Each downloaded source MUST create `manifest.json`:

```json
{
  "publication_id": "...",
  "company": "...",
  "period": "...",
  "source_url": "...",
  "retrieved_at": "...",
  "http_status": 200,
  "content_type": "...",
  "bytes": 0,
  "sha256": "...",
  "archive_test": "PASS",
  "extract_status": "NOT_EXTRACTED"
}
```

This makes every CYMDIST/DGS output traceable to the exact VNRGIS source bytes.

## D11. Safe archive handling

For ZIP/RAR:
- inventory before extraction when supported;
- reject absolute paths and `../` traversal;
- configurable uncompressed-size limit;
- reject suspicious nested archive bombs;
- extract to a run-specific staging folder;
- never execute files from an archive;
- detect actual contained data formats;
- retain original archive unchanged.

RAR support is optional-driver based. If unavailable, report the exact missing dependency rather than silently skipping the archive.

## D12. Download-on-demand behavior

Examples:

```bash
python -m vnr_etl search-vnr --company "Electro Dunas"
python -m vnr_etl search-vnr --all-companies --latest
python -m vnr_etl list-vnr --company "Electro Dunas"
python -m vnr_etl download-vnr --company "Electro Dunas" --period latest
python -m vnr_etl download-vnr --all-companies --period latest
python -m vnr_etl sync-vnr --all-companies
```

`search-vnr` does not download large artifacts.
`download-vnr` downloads explicitly selected artifacts.
`sync-vnr` compares the local catalog/cache and retrieves only missing/changed selected publications.

## D13. User-request resolver

Natural requests should map to deterministic selection:

```text
"descarga el VNRGIS más reciente de Electro Dunas"
→ company=resolved(Electro Dunas)
→ source_family=REGULATORY_VNRGIS_PACKAGE
→ period=latest
→ show selected official publication
→ download
→ verify
→ manifest

"descarga VNRGIS 2025 de todas las empresas"
→ period/reference=2025
→ enumerate official companies in that publication family
→ download each available company package
→ report unavailable companies separately
```

Never silently substitute a different year/source family.

## D14. All-company synchronization

Maintain:

```text
data/vnr_catalog/
├── catalog.json
├── companies.json
└── snapshots/

data/vnr_downloads/
├── <company>/
│   └── <publication_or_period>/
│       ├── source.<ext>
│       └── manifest.json
```

A synchronization report includes:
- companies discovered;
- companies with current package;
- new publications;
- changed links/files;
- downloads successful;
- downloads failed;
- unavailable/ambiguous companies.

## D15. API/ArcGIS complementary extraction

For ArcGIS sources, do not require an archive download. Persist:
- service URL;
- layer URL/ID;
- metadata snapshot;
- query filters;
- record count before extraction;
- unique records extracted;
- retrieval timestamp;
- response/output hash.

ArcGIS data may complement regulatory packages, but source-family labels remain explicit.

## D16. Automated update check

Command:

```bash
python -m vnr_etl check-updates --all-companies
```

Algorithm:
1. refresh official publication indexes;
2. compare publication IDs/URLs/reference dates/hashes where possible;
3. do not download unchanged large artifacts;
4. emit `AVAILABLE`, `CURRENT`, `CHANGED`, `AMBIGUOUS`, or `UNAVAILABLE`.

This command is suitable for an external scheduler, but the converter itself remains deterministic and does not silently update sources during a conversion unless configured.

## D17. Configuration

```yaml
discovery:
  enabled: true
  official_only: true
  source_priority:
    - REGULATORY_VNRGIS_PACKAGE
    - REGULATORY_VNR_PUBLICATION
    - ARCGIS_PUBLIC_REFERENCE
  allowed_hosts:
    - osinergmin.gob.pe
    - www.osinergmin.gob.pe
    - www2.osinergmin.gob.pe
    - gisem.osinergmin.gob.pe
  refresh_catalog_hours: 24

download:
  cache_dir: data/vnr_downloads
  temp_dir: data/tmp
  retries: 3
  connect_timeout_s: 20
  read_timeout_s: 180
  max_file_size_mb: 4096
  sha256: true
  verify_archive: true
  auto_extract: false
```

## D18. Discovery tests

Mandatory tests:
1. parses an official process page containing multiple company links;
2. identifies company/file pairs without hard-coded company names;
3. rejects third-party host by default;
4. retains two periods for the same company;
5. `latest` selects by authoritative date, not lexical filename;
6. ambiguous periods return ambiguity;
7. HTTP failure does not create a completed cache artifact;
8. partial file remains `.part`;
9. SHA-256 is stable;
10. unsafe archive path is rejected;
11. unchanged sync does not redownload;
12. changed publication creates a new immutable catalog record;
13. old ArcGIS dataset is not mislabeled as latest regulatory VNRGIS.

## D19. Conversion provenance

Every canonical dataset and simulator export must include a provenance record:

```text
source_publication_id
source_company
source_period
source_url
source_sha256
retrieved_at
schema_fingerprint
canonical_model_version
target_profile_hash
converter_version
```

Therefore a PowerFactory/CYMDIST model can always be reproduced from the same official source.

## D20. Critical implementation rule

The discovery manager MUST be capable of finding newer OSINERGMIN publications without a source-code release.

URLs, years and company lists are DATA discovered at runtime. Only discovery rules, validation policies and adapters belong in code.

If OSINERGMIN changes the website structure, discovery must fail transparently with diagnostic evidence and permit a new parser plugin; it must never fall back to an unverified third-party VNRGIS.

## D21. Current verified baseline

At the time this specification was updated (2026), OSINERGMIN's 2026 resolution index includes Resolution 154-2026-OS/CD concerning publication of the project for fixing the VNR of electrical distribution installations at 31 December 2025.

An older official regulatory VNR page demonstrably exposes "Instalador, Manual y Bases de Datos por empresa" and direct company `.rar` artifacts under the official `www2.osinergmin.gob.pe/GRT/Procesos-Regulatorios/VNR/...` hierarchy.

The currently visible `VNR_GIS_INTERRUPCIONES` ArcGIS service describes its content as VNR 2016, even though the endpoint remains active. It is therefore a complementary/reference GIS source, not proof of the latest VNRGIS regulatory package.

The discovery manager must search the current official regulatory publication structure at runtime and select the newest defensible company package instead of freezing any of these baseline URLs as "latest".

# EXTENSION v1.6 — ENTERPRISE DATABASES, BACKUPS, REQUIREMENTS AND WEB UI

## E1. Universal source layer
The same audited pipeline MUST accept:
- OSINERGMIN regulatory VNRGIS discovery/download and official ArcGIS REST.
- Authorized READ-ONLY enterprise DB: PostgreSQL/PostGIS, Oracle/Oracle Spatial, SQL Server, SQLite, Access and audited ODBC sources.
- Database exports/backups: `.sql`, PostgreSQL `.dump/.backup`, SQL Server `.bak`, Oracle `.dmp`, SQLite `.db/.sqlite`, Access `.mdb/.accdb`.
- VNRGIS/GIS packages: `.rar`, `.zip`, SHP/DBF, GeoPackage, CSV/TXT and other audited formats.

All converge to Schema Discovery → Canonical Model → GIS/Topology QA → Electrical Enrichment → CYMDIST/DGS.

## E2. Direct enterprise database connection
Default policy is READ ONLY. Discover engine/version, schemas, tables/views, columns/types, PK/FK, geometry columns, SRID/CRS, bounded samples and relationships. Never hard-code company table names.

Required adapter interface:
```python
class EnterpriseDatabaseAdapter:
    def probe(self): ...
    def test_connection(self): ...
    def discover_schemas(self): ...
    def discover_tables(self): ...
    def discover_columns(self, table): ...
    def discover_geometry(self, table): ...
    def discover_relations(self): ...
    def profile(self, table, limit=100): ...
    def read_network(self, filters=None): ...
```

Initial adapters: PostgreSQL/PostGIS, Oracle/Oracle Spatial, SQL Server, SQLite, Access and ODBC.

## E3. Database backup/export handling
| Input | Safe handling |
|---|---|
| `.sql` | Inspect dialect, DDL and data statements before execution |
| `.dump/.backup` | Detect PostgreSQL format; restore only in isolated compatible environment if required |
| `.bak` | SQL Server native restore in isolated compatible environment |
| `.dmp` | Oracle-compatible Data Pump/import tooling |
| `.db/.sqlite` | Direct SQLite adapter |
| `.mdb/.accdb` | Access/ODBC adapter |
| `.rar/.zip` | Safe inventory/extraction |
| `.shp/.dbf/.gpkg` | GIS adapter |
| `.txt/.csv` | Encoding/delimiter/schema discovery |

Binary backups MUST use compatible native restoration mechanisms; do not reverse-engineer arbitrary bytes.

## E4. SQL dump safety
Default is PARSE/INSPECT ONLY. Inspect probable dialect, encoding, CREATE TABLE/VIEW, ALTER TABLE, PK/FK, indexes, INSERT/COPY, spatial types/extensions, SRIDs and approximate object counts.

If execution/restoration is required: use a disposable isolated DB, least privilege, no production credentials, explicit approval, resource limits, and destroy it after extraction. Never execute an uploaded SQL dump against a production database.

## E5. Restore workflow
```text
BACKUP → ENGINE/FORMAT DETECTION → INTEGRITY/SAFETY → RESTORE PLAN
→ ISOLATED TEMP DB → READ-ONLY DISCOVERY → CANONICAL EXTRACTION
→ DESTROY TEMP DB
```

## E6. Enterprise GIS ↔ official VNRGIS reconciliation
When both exist, compare stable identities and classify:
`MATCHED`, `ONLY_ENTERPRISE`, `ONLY_VNRGIS`, `ADDED`, `REMOVED`,
`MODIFIED_GEOMETRY`, `MODIFIED_ATTRIBUTES`, `UNRESOLVED_IDENTITY`.
Never mutate either source during reconciliation.

## E7. requirements files are mandatory
ALL implemented Python dependencies MUST be machine-readable. Do not leave required libraries only in documentation or manual `pip install` commands.

Required project policy:
```text
requirements.txt
requirements-dev.txt
requirements-optional.txt
```

`requirements.txt` MUST contain everything needed by the default runtime and Web UI. Platform/engine-specific drivers may be in `requirements-optional.txt`, but must be documented and testable.

Baseline groups:
```text
# Core
pandas
numpy
requests
PyYAML
pydantic

# GIS
geopandas
shapely
pyproj

# Topology
networkx

# Database abstraction
SQLAlchemy

# File/data
openpyxl
pdf2image
opencv-python

# Web
fastapi
uvicorn
python-multipart
jinja2
```

`requirements-dev.txt` should include testing/linting tools such as `pytest` according to host-project policy.

Optional adapters may include `psycopg`/`psycopg2`, `pyodbc`, Oracle `oracledb`, Access/ODBC and RAR support.

The agent MUST audit existing dependency files, merge rather than overwrite, resolve version conflicts, pin reproducible versions according to project policy, run install/import tests, remove unused packages, and document native dependencies such as Poppler, ODBC drivers and database restore clients.

## E8. Dependency doctor
Required:
```bash
python -m vnr_etl doctor
```
Report Python version, required packages, optional adapters, GeoPandas/GDAL health, Poppler, ODBC drivers, PostgreSQL/Oracle/SQL Server support, RAR support, Web UI dependencies and simulator prerequisites. Missing optional support disables only that adapter.

## E9. Web UI is mandatory
EVERY major user-facing CLI capability MUST also be integrated into the Web UI. CLI and Web MUST call the SAME application/service layer; conversion logic may not be duplicated in routes/templates.

```text
APPLICATION CORE
   ├── CLI
   └── WEB UI
```

If the host project already has a Web framework, reuse it. Otherwise FastAPI + templates/light frontend is the default reference architecture.

## E10. Web Dashboard
Show VNRGIS catalog freshness, companies/periods, download/cache status, jobs, source readiness, validation state and CYMDIST/DGS export readiness.

## E11. Web Source Center
Provide:
1. OSINERGMIN Online.
2. Upload VNRGIS/GIS.
3. Upload Database Backup.
4. Connect Enterprise Database.
5. Existing Project Source.

## E12. OSINERGMIN Web workflow
Refresh official catalog; search/list companies; list periods; choose latest/explicit publication; inspect metadata; download; verify SHA-256; safely extract; sync selected/all companies.

## E13. Backup/file Web workflow
Allow controlled upload of supported formats. Before processing show detected format, size, SHA-256, probable DB engine, archive inventory, safety state, required adapter/native tool and proposed action. Uploaded SQL is NEVER automatically executed.

## E14. Enterprise DB Web workflow
Form fields: engine, host, port, database/service, schema, username, secret, supported SSL/TLS options.
Actions: Test Connection, Discover Schemas, Discover Tables, Inspect Geometry/SRID, Build Mapping.
Never expose secrets in logs or responses. READ ONLY by default.

## E15. Schema Discovery Web UI
Display source layer/table, fields/types, geometry, proposed canonical concept, alias/mapping, confidence, null/distinct statistics and unresolved fields. Authorized users may approve overrides saved as configuration, never as company-specific source-code branches.

## E16. GIS/Topology Web QA
Interactive/map-oriented view should expose nodes/sections, islands, orphan loads, snapping displacement, geometry errors, CRS and length discrepancies.

## E17. Electrical Enrichment Web QA
Show conductor/equipment coverage, missing R/X/ampacity, voltage/phase mappings, load P/Q coverage and source/slack status.

## E18. Reconciliation Web UI
Compare enterprise DB ↔ official VNRGIS or two periods. Filter MATCHED/ADDED/REMOVED/MODIFIED_GEOMETRY/MODIFIED_ATTRIBUTES/etc.

## E19. Export Center
Choose CYMDIST/PowerFactory, select verified TargetProfile, run pre-export gates, generate artifacts, display errors/warnings and retain provenance.

## E20. Web API contract
Illustrative endpoints:
```text
GET  /api/health
GET  /api/doctor
POST /api/discovery/refresh
GET  /api/vnr/companies
GET  /api/vnr/publications
POST /api/vnr/download
POST /api/sources/upload
POST /api/sources/inspect
POST /api/database/test
POST /api/database/discover
POST /api/schema/resolve
POST /api/topology/build
POST /api/validate
POST /api/reconcile
POST /api/export/cymdist
POST /api/export/dgs
GET  /api/jobs/{id}
GET  /api/artifacts/{id}
```
Adapt routes to host-project conventions.

## E21. Long-running jobs
Downloads, restores, extraction and conversion use a job abstraction:
`QUEUED`, `RUNNING`, `WAITING_FOR_APPROVAL`, `SUCCEEDED`, `FAILED`, `CANCELLED`.
Store progress, stage, safe logs, timestamps and outputs. Do not hold browser requests indefinitely.

## E22. Web security
Require authentication beyond localhost, appropriate authorization, upload limits, MIME/content inspection, safe archive extraction, no arbitrary paths, no shell string concatenation, secret redaction, parameterized SQL, READ-ONLY DB users, audit logs and secure artifact IDs. Production DB write actions are disabled by default.

## E23. CLI/Web parity
| Capability | CLI | Web |
|---|---:|---:|
| Doctor/dependencies | Yes | Yes |
| Search latest OSINERGMIN VNRGIS | Yes | Yes |
| List companies/periods | Yes | Yes |
| Download/sync | Yes | Yes |
| Upload VNRGIS/GIS | Yes | Yes |
| Upload DB backup | Yes | Yes |
| Inspect SQL dump | Yes | Yes |
| Connect enterprise DB | Yes | Yes |
| Schema discovery/mapping approval | Yes | Yes |
| GIS/topology QA | Yes | Yes |
| Electrical QA | Yes | Yes |
| Reconciliation | Yes | Yes |
| CYMDIST export | Yes | Yes |
| DGS export | Yes | Yes |
| Logs/provenance | Yes | Yes |

## E24. Shared application structure
```text
vnr_etl/
├── application/services/
├── application/jobs/
├── adapters/sources/
├── adapters/databases/
├── adapters/backups/
├── discovery/
├── canonical/
├── gis/
├── topology/
├── electrical/
├── reconciliation/
├── exporters/
├── web/
└── cli/
```
Web and CLI import `application/services`; neither implements independent business logic.

## E25. Mandatory Web tests
Test health/doctor, official discovery, upload detection, unsafe archive rejection, non-execution of SQL during inspection, credential redaction, read-only DB discovery, mapping persistence, topology jobs, validation errors, blocked invalid export, artifact retrieval, provenance and CLI/Web output equivalence.

## E26. v1.6 acceptance
Release only when:
1. dependency files fully describe Python requirements;
2. `doctor` validates capabilities;
3. OSINERGMIN discovery/download remains functional;
4. at least one direct SQL/GIS DB adapter is demonstrated;
5. `.sql` inspection works without execution;
6. binary backup support is demonstrated or clearly capability-gated;
7. VNRGIS/GIS archive ingestion works;
8. all source types converge to the canonical model;
9. Web exposes all major workflows;
10. CLI/Web share services;
11. security tests cover uploads/secrets/DB access;
12. CYMDIST/DGS gates remain strict;
13. provenance traces output to exact source/hash/schema/TargetProfile.

## E27. Final architecture
```text
OSINERGMIN ONLINE ─┐
ENTERPRISE DB ─────┤
DB BACKUP/EXPORT ──┼→ SOURCE INSPECTOR → SCHEMA DISCOVERY → CANONICAL MODEL
VNRGIS/GIS FILE ───┘       → GIS/TOPOLOGY QA → ELECTRICAL ENRICHMENT
                            → RECONCILIATION → TARGET PROFILE
                            → CYMDIST / POWERFACTORY → SIMULATOR QA

The same application services are exposed through CLI + WEB UI.
```

The platform is therefore a universal, auditable electrical-distribution ETL:
**OSINERGMIN + VNRGIS + enterprise GIS databases + SQL/database backups + GIS files → canonical electrical model → CYMDIST / DIgSILENT PowerFactory.**
