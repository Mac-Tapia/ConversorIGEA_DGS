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
  --import-dgs output\gui\AL104.dgs ^
  --manifest output\gui\AL104_geography.json ^
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
3. Activates **Study Case base**; if no **IntScenario** exists, **creates** `Operation Scenario` and activates it (`--ensure-scenario`, default on) — User Manual §12 study/scenario pattern
4. Runs **ComLdf**; with `--fix-until-converge`, on failure diagnoses and applies DigSILENT-aligned correction intents until convergence (or intents exhausted)
5. With `--run-studies`, runs the **study suite** (default: `load_flow` + `short_circuit` / ComShc)
6. **Persists DGS into the convert out_dir** (same folder as GUI/CLI individual convert — parent of `--import-dgs`, or `--persist-dir`):
   - Always ensures `{feeder}.dgs` (+ known sidecars if present) remain there (idempotent copy when the import path differed)
   - After LDF convergence, best-effort **ComExport** to `{feeder}_pf_converged.dgs` in that same folder (ApiExample `ExportDgsFile`); if export fails, the converter `{feeder}.dgs` stays and a warning is recorded
7. Validates (when `--manifest` is provided):
   - element counts (nodes, lines, loads, switches, sources)
   - **transformers** (`ElmTr2` SED), substations, capacitors (`ElmShnt`), regulators (`ElmVoltreg`)
   - line/load **connectivity** (cubicles → terminals)
   - **GPS / scaled location** vs `*_geography.json`
   - diagram pointer + optional WMF
   - **ComLdf** convergence (`IsLdfValid`)

Exit codes: `0` PASS, `2` FAIL, `3` PF API unavailable.

### Convert out_dir alignment

| Path | Who writes it |
|------|----------------|
| GUI **Carpeta de salida** (default `output/gui`) | `convert_selection` → `{feeder}.dgs`, sidecars, `batch_manifest.json` |
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

### GUI

In the desktop UI, select converted feeder(s) and press **«Cargar DGS en DigSILENT + flujo»**. The GUI launches this script as a subprocess with `--run-load-flow --fix-until-converge --run-studies` and `PF_PYTHON` / `PYTHONPATH` set when DigSilent’s Python folder is found.

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

## Boundary

`*_geography.json` keeps full intermediate GIS paths. ASCII DGS places terminal GPS + IntGrf graphics; full polylines stay in the sidecar until a verified `ElmLne.GPScoords` encoding is available.
