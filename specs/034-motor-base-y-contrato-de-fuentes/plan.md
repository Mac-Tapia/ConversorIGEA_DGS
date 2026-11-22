# Plan — Spec 034

Estado: aprobada (2026-11-14: RF-34 a RF-41; RF-1 a RF-33 cumplidos el 2026-10-29) · Spec: [spec.md](spec.md)

Spec retrospectiva: no hay código nuevo. El plan es la tabla que une cada RF con el código que
ya lo cumple y con las pruebas que lo comprueban; las pruebas pasan a citarlo en el docstring
de su módulo (033:RF-18) y `CODIGO_FUENTE.md` cambia «base» por «034» (033:RF-20).

| RF | Código | Pruebas |
| --- | --- | --- |
| RF-1 | `dataset.py`, `__init__.py` | `test_dataset.py`, `test_export_layouts.py`, `test_load_data_extraction.py` |
| RF-2 | `identify.py` | `test_identify.py` |
| RF-3 | `access.py`, `study.py` | `test_access_input.py`, `test_access.py` |
| RF-4 | `sources/vnr.py`, `vnr_etl/` | `test_vnr_gis_cobertura.py`, `test_vnr_etl.py`, `test_source_crs_units.py`, `test_vnr_cymdist_bridge.py` |
| RF-5 | `dataset.py`, `batch.py` | `test_input_robustness.py` |
| RF-6 | lector del libro de cargas de SED | `test_sed_loads.py` |
| RF-7 | `catalog.py`, `catalog_data.py`, `catalog_resolution.py` | `test_catalog.py`, `test_type_resolution.py` |
| RF-8 | `catalog_merge.py` | `test_catalog_merge.py` |
| RF-9 | `model.py` | `test_model_v2.py`, `test_load_data_extraction.py` |
| RF-10 | `model.py`, `batch.py` | `test_topology_islands.py`, `test_feeder_sl143.py` |
| RF-11 | `coordenadas.py`, geografía del modelo | `test_geography_optional.py`, `test_geography_v21.py`, `test_geo_batch_v21.py`, `test_mt_connectivity_lengths.py` |
| RF-12 | modelo universal y escritor del DGS | `test_capacitor_canonical.py`, `test_dgs_capacitors.py`, `test_access.py`, `test_vnr_cymdist_bridge.py` |
| RF-13 | `schema.py`, `schemas/pf21_dgs_1_8_4.json`, validación | `test_schema.py`, `test_validate_v2.py` |
| RF-14 | `export_tables.py`, `preview.py` | `test_export_tables.py`, `test_preview.py`, `test_preview_batch.py` |
| RF-15 | `batch.py` | `test_batch_robustness.py` |
| RF-16 | todo el motor | `test_flexibility_and_scale.py`, `test_performance_budget.py` |
| RF-17 | `combine.py` | `test_combine.py` |
| RF-18 | todo el motor | `test_feeder_pa217.py`, `test_feeder_sl143.py` |
| RF-19 | contrato de fuentes | `test_source_contract.py`, `test_source_contract_front.py`, `test_universal_source_scope.py` |
| RF-20 | ejecuciones fuente y adaptadores | `test_source_runs.py`, `test_source_adapters.py`, `test_readiness.py`, `test_web_source_ui_contract.py`, `test_web_runtime_dependencies.py` |
| RF-21 | `powerfactory_metadata.py`, vínculo del proyecto | `test_powerfactory_source_run.py`, `test_feeder_metadata.py`, `test_powerfactory_feeder_metadata.py`, `test_powerfactory_binding_front.py` |
| RF-22 | reconstrucción | `test_reconstruction_contract.py`, `test_reconstruction_topology.py`, `test_reconstruction_powerfactory.py`, `test_universal_reconstruction_acceptance.py` |
| RF-23 | inventario de bancos nativos | `test_native_capacitor_discovery.py`, `test_capacitor_inventory_front.py` |
| RF-24 | aceptación de tres fuentes | `test_three_source_acceptance.py`, `test_three_source_native_load_acceptance.py` |
| RF-25 | oráculo pandapower | `test_oraculo.py` |
| RF-26 | `studies.py` | `test_studies.py` |
| RF-27 | datos de `ComTececo` | `test_economia.py` |
| RF-28 | `inventory.py` | `test_inventory.py` |
| RF-29 | `powerfactory_env.py`, `pyproject.toml` | `test_python_version.py`, `test_fixtures.py` |
| RF-30 | espacio de trabajo de la web | `test_settings.py` |
| RF-31 | arquitectura C4 | `test_interactive_architecture.py` |
| RF-32 | `sed_potencia.py` | `test_puentes.py` |
| RF-33 | `tools/apply_catalog_to_model.py`, `tools/build_input_catalog.py`, `tools/compare_schema.py`, `tools/suggest_line_type_aliases.py`, `tools/build_system_grid.py`, `tools/prueba_representacion.py`, `tools/run_powerfactory_gate.bat` | `test_herramientas_base.py` |
| RF-42 | `presentacion/web/source_runs.py` (`_originales_custodiados`, `_custodiar`, `_sha256_link`) | `test_source_runs.py` (`enlace`, `alterado`) |
| RF-34, RF-35 | `docs/architecture/workspace_to_be.dsl` (extiende `workspace.dsl`) | `test_interactive_architecture.py` (`to_be`) |
| RF-36 a RF-39, RF-41 | `docs/architecture/adr/ADR-*.md` y `adr/README.md` | `test_interactive_architecture.py` (`adr`) |
| RF-40 | `docs/architecture/adr/deuda_excepciones_mudas.json` | `test_interactive_architecture.py` (`silent`) |

P23, 2026-11-08 (RF-5; 086:RF-1): probe SQLite inspecciona solo rollback estable bajo guarda Windows de lectura; WAL/diarios/escritor activo y plataformas sin guarda comprobada devuelven motivo, sin inventario ficticio ni copias. El CLI devuelve fallo cuando ok=false y evita sobrescribir la fuente, incluido hardlink. El informe se publica con el escritor duradero comun: una escritura parcial por fallo de disco conserva el informe anterior. Prueba adversa roja y34regresiones probe correctas; persistencia de fuente/auxiliares y exclusión se verificaron con hijos reales propios. No acredita conversionSQLite/PF ni aceptacion de produccion.

## Ampliación del 2026-11-14: C4 TO-BE y ADR (RF-34 a RF-41)

- **TO-BE sobre el mismo modelo.** `workspace_to_be.dsl` empieza con `workspace extends workspace.dsl`: hereda el
  modelo AS-IS y solo añade, con `!element`, lo que cambia (contenedor `cadWriter`, sistema `oda`, componentes
  `cmpFachadaServicios` y `cmpCasosDeUso`) y sus relaciones, con vistas `ToBe-*` propias. Alternativa descartada: un
  segundo DSL completo, que duplicaría el AS-IS y se desfasaría de él.
- **ADR atados al código.** Cada ADR cita su evidencia con formas que la prueba resuelve sin importar el producto
  (`ast` para Python, `tomllib` para las dependencias, texto literal para lo demás). Un ADR vigente sin su evidencia
  falla (RF-38); uno pendiente con toda su evidencia, también (RF-39). Así el ADR del DXF pasará a vigente cuando
  `ezdxf` sea dependencia obligatoria. Alternativa descartada: una herramienta nueva en `tools/`; la comprobación es
  de documentación y vive en su prueba, como la del AS-IS.
- **Detectores probados.** Cada comprobación se prueba también contra repositorios sintéticos con un defecto
  sembrado (ADR sin sección, cita rota, tarea abierta, elemento desconocido, TO-BE que redefine, enlace sin fijar), y
  el ADR o la TO-BE sanos no dan ningún problema.
- **Deuda de excepciones mudas (RF-40).** El detector usa `ast`: cuenta los `except` amplios con un único cuerpo que
  calla y respeta «# justificado:». La deuda es por fichero y solo se comprueba hacia arriba, porque varias tarjetas
  retiran excepciones en paralelo (080, H8, H12) y un ratchet hacia abajo rompería su integración (ADR-005).
