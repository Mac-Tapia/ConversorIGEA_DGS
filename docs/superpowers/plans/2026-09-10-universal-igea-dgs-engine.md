# Universal IGEA/CYMDIST to DGS Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the feeder-specific prototype with a reference-free, versioned, strict batch converter for one, many, or all feeders.

**Architecture:** Parse source TXT files once into a reusable dataset, build isolated feeder models, serialize through a versioned DGS schema profile, and validate every relationship before reporting success. A reference DGS is allowed only in optional development compatibility tests and is never a runtime dependency.

**Tech Stack:** Python 3.11+, standard library, pytest.

**Spec:** `docs/superpowers/specs/2026-09-10-universal-igea-dgs-engine-design.md`

## Global Constraints

- Runtime must not read, bundle, or require `NA205.dgs` or any other reference DGS.
- The three TXT exports are the source of network/electrical data.
- Strict mode is the default.
- Aliases are external configuration, never hard-coded in source.
- Conversion supports one feeder, repeated feeder selections, or all feeders in one process.
- Output must be deterministic.

---

### Task 1: Versioned DGS schema profile

**Files:** Create `src/igea_dgs/schemas/pf21_dgs_1_8_4.json`, `src/igea_dgs/schema.py`; Test `tests/test_schema.py`.
**Interfaces:** `load_schema(profile: str) -> DgsSchema`; `DgsSchema.header(table: str) -> str`.

- [ ] Write a failing test that loads the packaged profile and checks exact headers for core DGS tables and confirms no reference-file path/content is stored.
- [ ] Run the test and confirm failure because `schema.py` does not exist.
- [ ] Implement JSON profile loading and typed schema objects.
- [ ] Re-run the test and confirm pass.

### Task 2: Parse reusable CYMDIST dataset

**Files:** Create `src/igea_dgs/dataset.py`; Test `tests/test_dataset.py`.
**Interfaces:** `CymdistDataset.from_files(red, loads, equipment)`, `.feeder_ids()`, `.resolve_feeder(selector)`.

- [ ] Write failing tests for dataset integrity (N feeders == N sources, section/config ownership, load-table joins, switch/sectionalizer retention and feeder resolution by short name). Counts come from the loaded TXT, not a fixed N.
- [ ] Run and confirm failure.
- [ ] Implement one-pass parsers and indexes.
- [ ] Re-run and confirm pass.

### Task 3: Strict feeder model and connection semantics

**Files:** Replace `src/igea_dgs/model.py`; Test `tests/test_model_v2.py`.
**Interfaces:** `build_feeder_model(dataset, selector, aliases=None, strict=True) -> FeederModel`.

- [ ] Write failing tests for IN111 counts, source voltage, load Location=1 -> ToNode, section device Location=S -> From cubicle intent, and unresolved line type failure on a known affected feeder.
- [ ] Run and confirm failure.
- [ ] Implement typed model objects and strict alias handling from a supplied dict.
- [ ] Re-run and confirm pass.

### Task 4: Deterministic DGS writer

**Files:** Replace `src/igea_dgs/dgs.py`; Test `tests/test_dgs_v2.py`.
**Interfaces:** `write_dgs(model, path, schema_profile='pf21_dgs_1_8_4') -> DgsManifest`.

- [ ] Write failing tests for exact headers, deterministic bytes, two cubicles per line, one cubicle per load/source, correct load terminal, switch parent cubicle, and no reference-DGS text.
- [ ] Run and confirm failure.
- [ ] Implement writer using only the packaged schema profile and feeder model.
- [ ] Re-run and confirm pass.

### Task 5: Strict DGS validator

**Files:** Replace `src/igea_dgs/validate.py`; Test `tests/test_validate_v2.py`.
**Interfaces:** `validate_dgs(model, path, schema_profile=...) -> dict`.

- [ ] Write failing tests for duplicate FID, dangling typ_id, wrong cubicle count, wrong switch parent, length mismatch and clean IN111.
- [ ] Run and confirm failure.
- [ ] Implement schema and referential validation.
- [ ] Re-run and confirm pass.

### Task 6: Batch conversion and CLI

**Files:** Create `src/igea_dgs/batch.py`; Replace `src/igea_dgs/cli.py`; Test `tests/test_batch_cli.py`.
**Interfaces:** `convert_selection(dataset, selectors, out_dir, ...) -> BatchManifest` and CLI `list` / `convert`.

- [ ] Write failing tests for one feeder, multiple feeders, `--all`, independent failures, and manifest generation.
- [ ] Run and confirm failure.
- [ ] Implement batch engine and CLI selection semantics.
- [ ] Re-run and confirm pass.

### Task 7: Whole-dataset audit and packaging

**Files:** Update `README.md`; create `config/line_type_aliases.example.json`; generated `output/audit_all.json` and `output/IN111.dgs`.

- [ ] Run the full strict audit for every feeder in the loaded TXT and record success/failure per feeder without silent topology guesses.
- [ ] Generate IN111 in strict mode and validate it.
- [ ] Run the complete pytest suite.
- [ ] Scan production source for `NA205.dgs`, `/mnt/data/NA205`, or `reference_dgs` runtime dependency; require zero hits.
- [ ] Package source, schemas, tests, docs, example config and generated audit into a ZIP.
