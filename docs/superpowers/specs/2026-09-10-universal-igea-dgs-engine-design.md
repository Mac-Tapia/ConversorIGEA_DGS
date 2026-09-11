# Universal IGEA/CYMDIST to DGS Engine Design

## Goal
Build a deterministic, strict and scalable converter that reads RED, CARGA and BD_Equipo once and can export one, many, or all feeders to DIgSILENT DGS without requiring any reference DGS file at runtime.

## Core rule
`NA205.dgs` is a development reference only. It is not packaged, embedded, copied, parsed, or required by production code. Production compatibility is expressed through a versioned schema profile containing only DGS table definitions and field types.

## Architecture
1. `dataset.py`: parse the three CYMDIST/IGEA TXT exports once into typed tables, preserving feeder ownership, load locations, switching devices and intermediate coordinates.
2. `schema.py`: load a packaged DGS compatibility profile from JSON; no electrical/topological data is stored in the profile.
3. `model.py`: build an isolated feeder model from the parsed dataset. Missing equipment types are fatal in strict mode unless an explicit external alias file resolves them.
4. `dgs.py`: serialize deterministic FIDs and exact table headers from the selected schema profile. Connections are represented through `StaCubic`; explicit switching settings attach to the corresponding section terminal cubicle as `StaSwitch`.
5. `validate.py`: validate field counts, FID uniqueness, pointer integrity, cubicle cardinality, switch parentage, source/head consistency, load terminal selection, lengths and aggregate loads.
6. `batch.py`: convert one, several, or all feeders from one in-memory dataset and write a machine-readable manifest. A failed feeder does not invalidate other feeders.
7. `cli.py`: `list` and `convert` subcommands with `--feeder`, repeated `--feeder`, `--network`, or `--all` selection.

## Connection rules
- Section FromNode/ToNode are copied exactly from RED.
- Every emitted `ElmLne` receives two cubicles: `obj_bus=0` at FromNode and `obj_bus=1` at ToNode.
- A load is joined to its section using the LOADS table, not merely the CUSTOMER LOADS row. Current source value `Location=1` maps to ToNode. `Location=0` maps to FromNode. Any other value is rejected in strict mode until a proven mapping is configured.
- A SOURCE is connected to its declared NodeID and its DesiredVoltage is the feeder nominal voltage.
- SWITCH SETTING and SECTIONALIZER SETTING rows attach to the selected section terminal. Current `Location=S` means section start/FromNode, `Location=L` means section end/ToNode. `Status` becomes the DGS `on_off` value. Unsupported locations are fatal in strict mode.

## Strictness
- No implicit use of `DEFAULT` for unknown line types.
- No hard-coded alias derived from NA205.
- Aliases may only come from an external JSON supplied by the user.
- No missing node, source, line configuration, duplicated section, duplicated FID, dangling pointer, or wrong cubicle cardinality is tolerated.
- Generated files are deterministic for identical input/profile/alias configuration.

## Scope of this version
The engine emits the DGS classes directly supported by the supplied TXT data: General, ElmNet, ElmTerm, TypLne, ElmLne, ElmLod, ElmXnet, StaCubic and StaSwitch. The packaged schema profile can describe additional DGS tables for future transformers/substations/fuses without changing the parser or CLI architecture.
