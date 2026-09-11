# PowerFactory Runtime Acceptance — Geographic DGS

This is the final acceptance gate for a feeder produced by the converter. Static tests prove DGS structure, source-data preservation, topology, GPS coverage and graphical references; only the target PowerFactory installation can prove that the imported model is actually accepted and rendered.

## IN111 procedure

1. Import `IN111.dgs` with **File → Import → DGS** in PowerFactory 21.
2. Activate the project/network and verify that the imported network is named `IN111`.
3. Use PowerFactory's **Geographic Diagram** function. DIgSILENT documents that a geographic diagram can be created when GPS coordinates are available, and that after coordinate changes the geographic diagram may need to be rebuilt once.
4. Run the packaged acceptance script using the generated `IN111_geography.json` manifest:

```bat
python powerfactory_acceptance.py --manifest IN111_geography.json --require-diagram --run-load-flow --export-wmf IN111_rendered.wmf
```

If the project has no valid study case for load flow yet, omit `--run-load-flow` for the first import/graphics acceptance and execute the electrical study after completing source short-circuit and operating data.

## Automatic checks

The script checks the imported `ElmNet`, counts of `ElmTerm`, `ElmLne`, `ElmLod`, `StaSwitch` and `ElmXnet`, 100% valid `GPSlat`/`GPSlon` coverage, line-to-terminal connectivity through `StaCubic`, the `ElmNet.pDiagram` pointer, accessible diagram graphics when requested, optional WMF rendering evidence, and optional `ComLdf` execution.

The result is written to JSON and TXT. The required final fields are:

- `powerfactory_runtime_pass: true` — **PASS** for the selected runtime checks.
- `geographic_diagram_pass: true` — **PASS** for diagram materialisation/rendering evidence when `--require-diagram` and/or `--export-wmf` are used.
- Any error produces **FAIL** and exit code 2.

## Important boundary

`IN111_geography.json` preserves every transformed node coordinate and the full ordered line path, including all intermediate GIS points. The current ASCII DGS writer does not invent an unverified encoding for `ElmLne.GPScoords:MATRIX`; instead it provides terminal GPS coordinates plus deterministic `IntGrf`/`IntGrfcon` network graphics, while the lossless geometry remains in the sidecar. If a future PowerFactory export containing non-empty `ElmLne.GPScoords` is provided, that matrix representation can be added as a separately tested schema capability.

The final visual check remains PowerFactory itself: open/rebuild the Geographic Diagram and confirm that the complete feeder is visible and coherent with the GIS source. A non-empty exported `IN111_rendered.wmf` provides repeatable rendering evidence, but it does not replace engineering review of the map alignment.
