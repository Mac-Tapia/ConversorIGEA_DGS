# Dataset PIDE universal PIDEELOR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir desde `referencia/PIDEELOR` un dataset universal, auditable y apto para RAG/reentrenamiento que cubra los artículos 1–20 sin convertir los resultados particulares de ELOR en reglas de otra empresa.

**Architecture:** Un módulo puro inventaría y clasifica cada archivo, extractores acotados publican texto y metadatos estructurados, y un constructor genera corpus `context`, plantillas metodológicas y tarjetas de calidad. Un CLI materializa JSONL/JSON sin modificar fuentes y valida que toda fila conserve custodia empresarial y SHA-256.

**Tech Stack:** Python 3.12, biblioteca estándar, PyPDF, python-docx, openpyxl, pyogrio opcionales, JSON/JSONL, pytest.

**Spec:** `docs/superpowers/specs/2026-10-25-dataset-pide-universal-pideelor-design.md`

## Global Constraints

- Los originales de `referencia/PIDEELOR` son solo lectura.
- Cada archivo aparece exactamente una vez en el manifiesto y recibe SHA-256 calculado por flujo.
- La empresa queda en procedencia; ninguna regla universal depende de `ELOR`.
- Todo contenido empresarial derivado se publica como `context`; `gold` exige aceptación humana o nativa externa.
- PDF/DOCX/XLSX/CSV/GIS se extraen con estado explícito; formatos propietarios nunca se marcan como leídos por su mera existencia.
- Archivos temporales, rotos, duplicados, sin CRS y con vínculos externos conservan advertencias.
- Los 20 artículos usan título canónico, etapa, entradas, procedimiento, evidencia y entregable.
- Las salidas con datos empresariales permanecen bajo `output/`.

## Review Focus

- Un archivo cambia mientras se calcula su huella: registrar error y no publicar una huella falsa.
- Un PDF/DOCX/XLSX corrupto: conservar manifiesto y emitir `extract_status=error`, sin abortar el corpus.
- Dos rutas con contenido idéntico: una identidad de contenido, todas las ubicaciones y un solo fragmento semántico.
- Un Shapefile sin CRS: registrar entidades/campos pero bloquear interpretación espacial normalizada.
- Un fragmento o registro de entrenamiento sin `file_id`/SHA-256: rechazar la publicación.

---

### Task 1: Contrato universal de artículos, formatos y alternativas

**Files:**
- Create: `config/pide_universal_2017.json`
- Create: `src/igea_dgs/pide_dataset.py`
- Create: `tests/test_pide_dataset.py`

**Interfaces:**
- Produces: `cargar_contrato(path: Path | str) -> ContratoPide`; `ContratoPide.validar() -> list[str]`.

- [ ] Escribir pruebas fallidas para exactamente 20 artículos ordenados, F01–F15, etapas completas y alternativas sin empresa.
- [ ] Ejecutar `pytest -q tests/test_pide_dataset.py` y confirmar fallo por módulo/archivo ausente.
- [ ] Implementar dataclasses y catálogo JSON con títulos canónicos de la prepublicación.
- [ ] Ejecutar las pruebas enfocadas y confirmar verde.

### Task 2: Manifiesto exhaustivo y clasificación empresarial

**Files:**
- Modify: `src/igea_dgs/pide_dataset.py`
- Modify: `tests/test_pide_dataset.py`

**Interfaces:**
- Consumes: `ContratoPide`.
- Produces: `inventariar(raiz, empresa, contrato) -> tuple[ArchivoPide, ...]`; `clasificar_ruta(path) -> ClasificacionPide`.

- [ ] Escribir pruebas fallidas para archivo único, SHA-256, temporal Office, firma real, entrega/revisión, duplicidad y mutación durante lectura.
- [ ] Confirmar RED con fixtures reales pequeños.
- [ ] Implementar inventario determinista, huella en bloques, firmas y clasificación cerrada.
- [ ] Confirmar GREEN y que ninguna ruta absoluta se serializa.

### Task 3: Extracción robusta por formato

**Files:**
- Modify: `src/igea_dgs/pide_dataset.py`
- Modify: `tests/test_pide_dataset.py`

**Interfaces:**
- Consumes: `ArchivoPide`.
- Produces: `extraer_archivo(archivo, raiz, *, max_chars) -> ExtraccionPide`.

- [ ] Escribir pruebas fallidas para PDF, DOCX, XLSX, CSV, GIS, duplicado, corrupto y propietario no leído.
- [ ] Confirmar RED.
- [ ] Implementar extractores opcionales, fragmentación con localización y límites, hojas/metadatos, capas y advertencias.
- [ ] Confirmar GREEN sin mocks de los formatos legibles.

### Task 4: Publicación de corpus y registros para LLM

**Files:**
- Modify: `src/igea_dgs/pide_dataset.py`
- Create: `tools/construir_dataset_pide.py`
- Modify: `tests/test_pide_dataset.py`

**Interfaces:**
- Consumes: manifiesto, extracciones y `ContratoPide`.
- Produces: `construir_dataset(raiz, destino, empresa, contrato_path) -> dict`; archivos `manifest.jsonl`, `fragments.jsonl`, `assets.jsonl`, `training.jsonl`, `quality.jsonl`, `summary.json`.

- [ ] Escribir pruebas fallidas para escrituras atómicas, custodia obligatoria, deduplicación semántica y registros `context` compatibles con chat.
- [ ] Confirmar RED ejecutando el CLI contra un corpus fixture.
- [ ] Implementar publicación determinista y CLI con `--raiz`, `--destino`, `--empresa`, `--contrato` y `--sin-texto`.
- [ ] Confirmar GREEN y reconstrucción byte-idéntica del fixture.

### Task 5: Construcción real y auditoría PIDEELOR

**Files:**
- Create under ignored output: `output/pide_dataset/PIDEELOR/*`
- Create: `docs/evidence/PIDEELOR_DATASET.md`
- Modify: `tests/test_pide_dataset.py`

**Interfaces:**
- Consumes: pipeline completo.
- Produces: dataset real, informe de cobertura y prueba de aceptación sobre el resumen generado.

- [ ] Ejecutar primero una prueba de aceptación que falle si el resumen no cubre 1,397 archivos, 20 artículos o si aparecen rutas absolutas.
- [ ] Construir el corpus real completo con hashes y extracción.
- [ ] Auditar conteos, duplicados, errores, cobertura por formato/artículo y tamaño de salidas.
- [ ] Redactar evidencia reproducible sin incluir identificadores sensibles ni contenido masivo.
- [ ] Ejecutar `pytest -q tests/test_pide_dataset.py tests/test_pide.py tests/test_pide_economia.py`.

### Task 6: Validación integral

**Files:**
- Modify only if a regression test proves a defect in files from Tasks 1–5.

**Interfaces:**
- Consumes: implementación y dataset real.
- Produces: evidencia de lint/compilación, suite completa y revisión final.

- [ ] Ejecutar `python -m compileall -q src tools/construir_dataset_pide.py`.
- [ ] Ejecutar `pytest -q` y registrar cualquier fallo/skip sin ocultarlo.
- [ ] Revisar diff contra spec, controles de privacidad y artefactos generados.
- [ ] Ejecutar de nuevo las pruebas enfocadas después de cualquier corrección.
