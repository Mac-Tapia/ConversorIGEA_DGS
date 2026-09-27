# PowerFactory Runtime Acceptance — Geographic DGS

This is the final acceptance gate for a feeder produced by the converter. Static tests prove DGS structure, source-data preservation, topology, GPS coverage and graphical references; **PowerFactory API** proves import, study/scenario activation, connectivity, scaled location, load-flow convergence, and (optionally) a short study suite.

## DigSILENT Help sources (this machine)

Installed under `C:\Program Files\DIgSILENT\PowerFactory 2024\`:

| Path | Used for |
|------|----------|
| `Help\UserManual_en.pdf` | §12.8 calculation commands in study cases; §24 Load Flow (options + §24.6 troubleshooting); §25 Short-Circuit; Operation Scenario / Study Case |
| `Help\PythonReference_en.pdf` | `GetFromStudyCase`, `IsLdfValid`, `ComLdf.Execute` (rc 0/1/2), `ComShc` |
| `Help\DplReference_en.pdf` | `GetFromStudyCase` creates command if missing; `Ldf:iopt_net = 0\|1` |
| `localisation\*\data.db` | Official ComLdf / ComShc attribute labels (`iopt_lim`, `iopt_at`, `iopt_fl`, `iopt_lev`, `iopt_allbus`, …) |
| `Api\Example\src\ApiExample.cpp` | ComImport transfer attrs + load-flow + `IsLdfValid` |
| `Python\3.10` … `3.12\powerfactory.pyd` | Python API module |

## One-shot API gate (recommended)

Requires DigSilent PowerFactory 2024 (or compatible) with the matching Python API on `PYTHONPATH`.

```bat
set PYTHONPATH=C:\Program Files\DIgSILENT\PowerFactory 2024\Python\3.12
set PATH=C:\Program Files\DIgSILENT\PowerFactory 2024;%PATH%

python tools\powerfactory_acceptance.py ^
  --import-dgs output\web\AL104.dgs ^
  --manifest output\web\AL104_geography.json ^
  --feeder-metadata output\web\AL104_feeder_metadata.json ^
  --require-diagram ^
  --run-load-flow ^
  --fix-until-converge ^
  --run-studies
```

List registered studies without connecting to PF:

```bat
python tools\powerfactory_acceptance.py --list-studies
```

What this does:

1. Connects to PF (`GetApplication` / `GetApplicationExt`)
2. Imports the `.dgs` via **ComImport** into a new project (same pattern as DigSilent `ApiExample.cpp`)
3. Verifies that the active project is exactly the newly imported project, creates the project Data Extension `p:alimentador` for `ElmLod`, `ElmSym` and `ElmXnet`, and assigns every row from the SHA-256-bound metadata. Missing or ambiguous identities block the complete batch; a write failure rolls it back.
4. Reactivates **Study Case base** after closing the Data Extension transaction; if no **IntScenario** exists, **creates** `Operation Scenario` and activates it (`--ensure-scenario`, default on) — User Manual §12 study/scenario pattern
5. Runs **ComLdf**; with `--fix-until-converge`, on failure diagnoses and applies DigSILENT-aligned correction intents until convergence (or intents exhausted)
6. With `--run-studies`, runs the **study suite** (default: `load_flow` + `short_circuit` / ComShc)
7. **Persists DGS into the convert out_dir** (same folder as web/CLI individual convert — parent of `--import-dgs`, or `--persist-dir`):
   - Always ensures `{feeder}.dgs` (+ known sidecars if present) remain there (idempotent copy when the import path differed)
   - After LDF convergence, best-effort **ComExport** to `{feeder}_pf_converged.dgs` in that same folder (ApiExample `ExportDgsFile`); if export fails, the converter `{feeder}.dgs` stays and a warning is recorded
8. Validates (when `--manifest` is provided):
   - element counts (nodes, lines, loads, switches, sources)
   - **transformers** (`ElmTr2` SED), substations, capacitors (`ElmShnt`), regulators (`ElmVoltreg`)
   - line/load **connectivity** (cubicles → terminals)
   - **GPS / scaled location** vs `*_geography.json`
   - diagram pointer + optional WMF
   - **ComLdf** convergence (`IsLdfValid`)

Exit codes: `0` PASS, `2` FAIL, `3` PF API unavailable.

## Columna `Alimentador` en Network Model Manager

La compuerta anterior crea automáticamente una sola Data Extension llamada internamente `alimentador`, descrita como `Alimentador` y accesible por API como `p:alimentador`. No la cree manualmente antes de ejecutar la compuerta. `Grid` representa el contenedor común; no debe interpretarse como el alimentador individual cuando el DGS une varias redes.

1. Abra **Network Model Manager → Generators, Loads, and Sources → General Load**.
2. Intente primero la pestaña **Basic Data**. Abra la selección de columnas y agregue **Alimentador** inmediatamente después de **Grid**.
3. Si `Basic Data` no ofrece el atributo, abra **Flexible Data**, entre a la selección de variables y elija **Data Extension → Alimentador**. Arrastre su encabezado para dejarlo después de **Grid**.
4. Repita la selección en **Synchronous Machine** y **External Grid**. `ElmSym` puede quedar sin filas en NA203–NA205, pero la columna debe existir.
5. Filtre u ordene por `Alimentador` y verifique que cada carga muestra su alimentador según su terminal/SED; no use `Grid` (`NA203_NA205`, por ejemplo) como sustituto.
6. Compare las columnas `Name` y `Alimentador` con `<nombre>_name_alimentador.csv`. La relación admite cualquier cantidad de alimentadores dentro del mismo Grid/DGS, no solo NA203 y NA205.
7. Guarde evidencia visible de al menos una carga por alimentador y sus fuentes externas. Los conteos deben coincidir con `<nombre>_feeder_metadata.json` y con la sección `feeder_metadata.assignment` del informe PowerFactory.

La disponibilidad garantizada por DIgSILENT es en **Flexible Data**; la presencia en **Basic Data** se comprueba en vivo porque depende de la configuración de vista. El procedimiento se apoya en la documentación oficial de [Data Extensions por Python](https://www.digsilent.de/en/faq-reader-powerfactory/how-can-i-create-data-extensions-via-python.html) y en la guía oficial de [integración GIS](https://www.digsilent.de/en/paper-reader-pf-en/gis-integration.html). La decisión de conservar topología y trazabilidad explícita también está alineada con literatura académica citada en la especificación de diseño: una [tesis de maestría sobre visualización de redes](https://repositorio.comillas.edu/jspui/handle/11531/99738), una [tesis doctoral sobre modelos de distribución](https://uknowledge.uky.edu/ece_etds/134/) y el artículo indexado sobre [layout automático de diagramas unifilares](https://doi.org/10.1016/j.epsr.2003.12.005).

## Verificación reproducible NA203–NA205 antes de PowerFactory

```bat
python tools\verify_na203_na205.py ^
  --dgs output\acceptance_20260927\NA203_NA205.dgs ^
  --manifest output\acceptance_20260927\NA203_NA205_manifest.json ^
  --feeder-metadata output\acceptance_20260927\NA203_NA205_feeder_metadata.json ^
  --validation output\acceptance_20260927\NA203_NA205_validation.json ^
  --output-json output\acceptance_20260927\NA203_NA205_artifact_acceptance.json ^
  --output-txt output\acceptance_20260927\NA203_NA205_artifact_acceptance.txt
```

El código `0` exige dos fuentes, correspondencia total de cargas/fuentes con metadata, 92 Trafomix excluidos y ninguno `M…` modelado como SED, topología interna completa de SED, reconciliación de maniobras, cero errores de validación y lienzo adaptativo cercano a 2,08 unidades/metro. El código `2` deja igualmente ambos diagnósticos. La prueba marcada `real_na203_na205` se omite si no se proporciona la carpeta real; ese `skip` significa **no ejecutado**, nunca aceptación.

### Convert out_dir alignment

| Path | Who writes it |
|------|----------------|
| Web workspace (`output/web/<id>/output`) | `convert_selection` → `{feeder}.dgs`, sidecars, `batch_manifest.json` |
| CLI `--out-dir` | Same via `convert_selection` |
| Production batch `output/production_all` | Same when converting with that `--out-dir` |
| PF gate | Imports from that folder; then **persists** `{feeder}.dgs` there again and optionally `{feeder}_pf_converged.dgs` |

Flags: `--persist-dir DIR`, `--no-persist-dgs`, `--no-export-converged-dgs`.

### Correction intents (`--fix-until-converge`)

Applied in the live PF project. The converter `{feeder}.dgs` on disk is always kept in the convert folder; in-memory corrections (outserv / load scale) are only written back if ComExport succeeds as `{feeder}_pf_converged.dgs`. Order and options follow **User Manual §24.6** and ComLdf attribute labels from Help localisation:

1. **Relaxed ComLdf options** — `iopt_lim=0` (no reactive limits), `iopt_plim=0`, `iopt_at=0` / `iopt_asht=0` / `iPST_at=0` (no auto taps), `iopt_pq=0`, `iopt_fl=1` (flat start), `iopt_lev=1` (Automatic Model Adaptation for Convergence). *Not* invented flags such as `iIgnoreLimits` / `iopt_start`.
2. Voltage source(s) in service (`outserv=0` on ElmXnet/ElmVac)
3. Floating / unsupplied loads out of service (`outserv=1`) — §24.6.3
4. Scale active loads to 50% (load shedding hint — §24.6.4)
5. Island / disconnected heuristic + ensure source in service
6. Scale loads to 75%, then 100% of original

`ComLdf.Execute` return codes are interpreted per Python Reference: `0` OK, `1` inner-loop divergence, `2` outer-loop divergence.

Each attempt is logged in the JSON/TXT report under `load_flow_loop`.

### Study suite (`--run-studies`)

Extensible registry in `tools/powerfactory_acceptance.py` (`STUDY_REGISTRY` / `DEFAULT_STUDY_SUITE`):

| Study id | Command | Status |
|----------|---------|--------|
| `load_flow` | `ComLdf` | Runnable (fix-until-converge supported) |
| `short_circuit` | `ComShc` | Runnable when module/licence allows; soft-fail + warning if unavailable |
| `contingency` | `ComContingency` / `ComSimoutage` | Documented gap (not wired) |
| `opf` | `ComOpf` | Documented gap |
| `rms` | `ComInc` + `ComSim` | Documented gap |
| `harmonics` | — | Documented gap |
| `reliability` | `ComNmink` | Documented gap |

Override the list: `--studies load_flow,short_circuit`.

Short-circuit defaults (applied only when attributes exist): prefer IEC 60909 (`iopt_iec=1`), all busbars (`iopt_allbus=2`), max currents (`iopt_max=1`), 3-phase fault flags. If the short-circuit licence is missing, Execute typically fails — the report marks `available=false` / warnings without inventing results.

### Interfaz web

In the web UI, select converted feeder(s) and press **«Cargar DGS en DigSILENT + flujo»**. FastAPI launches this script as a subprocess with `--run-load-flow --fix-until-converge --run-studies` and `PF_PYTHON` / `PYTHONPATH` set when DigSilent’s Python folder is found.

## Equipment scope (important)

| Element | In DGS today | Source |
|---------|--------------|--------|
| SED transformers (`ElmTr2` / `ElmSubstat`) | Yes | Heuristic from CARGA customer codes (`SE…`) |
| Lines / loads / SW / sectionalizers | Yes | RED + CARGA |
| Capacitor banks (`ElmShnt`) | Only if RED has placement | Current `referencia` RED has **no** `CAPACITOR SETTING` (BD_Equipo catalog alone is not enough) |
| Voltage regulators (`ElmVoltreg`) | Only if RED has placement | Current RED has **no** `REGULATOR SETTING` |

The gate **expects capacitors=0 and regulators=0** for typical IGEA exports and reports that clearly in warnings. When those SETTINGS appear in a future TXT, the converter must map them before PF can load them.

## Manual procedure (without `--import-dgs`)

1. Import `IN111.dgs` with **File → Import → DGS** in PowerFactory.
2. Activate the project/network named like the feeder.
3. Activate Study Case base + Operation Scenario (or let `--ensure-scenario` create one).
4. Run:

```bat
python tools\powerfactory_acceptance.py --manifest IN111_geography.json --require-diagram --run-load-flow --export-wmf IN111_rendered.wmf
```

## Report fields

- `powerfactory_runtime_pass`
- `connectivity_pass`
- `location_scale_pass`
- `equipment_pass`
- `geographic_diagram_pass`
- `convergence_pass` (when load flow requested)
- `scenario_ensure` (when a scenario was created/activated)
- `load_flow_loop` (attempts, diagnosis, solutions when `--fix-until-converge`)
- `study_suite` (per-study results when `--run-studies`)
- `dgs_persist` (convert out_dir path, copy/export actions, optional `converged_dgs`)
- `feeder_metadata` (Data Extensions, asignaciones, conteos por clase/alimentador, no resueltos y ambiguos)

## Boundary

`*_geography.json` keeps full intermediate GIS paths. ASCII DGS places terminal GPS + IntGrf graphics; full polylines stay in the sidecar until a verified `ElmLne.GPScoords` encoding is available.
