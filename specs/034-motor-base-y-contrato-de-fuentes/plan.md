# Plan — Spec 034

Estado: cumplida (2026-10-29) · Spec: [spec.md](spec.md)

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
