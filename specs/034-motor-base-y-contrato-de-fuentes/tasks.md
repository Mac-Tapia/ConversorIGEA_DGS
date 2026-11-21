# Tareas — Spec 034

- [x] T1. Spec retrospectiva y tabla RF → código → pruebas. (RF-1 a RF-33)
      Hecho cuando: cada RF tiene su fila en `plan.md`.
- [x] T2. Las pruebas del motor base y del contrato de fuentes citan su RF en el docstring de
      su módulo; prueba de arranque de las herramientas de catálogo y esquema. (RF-1 a RF-33)
      Hecho cuando: `grep -rnoE "034:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-33 y esas
      pruebas pasan.
- [x] T3. `CODIGO_FUENTE.md` atribuye a la 034 cada fichero que decía solo «base». (RF-1 a RF-33)
      Hecho cuando: `pytest -q tests/test_trazabilidad_specs.py -k base` en verde.
- [x] T4. C4 TO-BE en `docs/architecture/workspace_to_be.dsl`, que extiende `workspace.dsl` sin redefinirlo, con sus
      vistas y la Aclaración de RF-31. (RF-34, RF-35)
      Hecho cuando: `pytest -q tests/test_interactive_architecture.py -k "to_be"` en verde, y en rojo sobre 00d30651
      sin la TO-BE.
- [x] T5. ADR por decisión de frontera en `docs/architecture/adr/` (monolito por capas, fachada de servicios, contrato
      OpenAPI, escritura duradera, avisos, DXF con DWG opcional, colas por carriles, MCP de solo lectura y editor del
      plano), con su formato en `adr/README.md` y la prueba que los compara con el código. (RF-36, RF-37, RF-38,
      RF-39, RF-41)
      Hecho cuando: `pytest -q tests/test_interactive_architecture.py -k "adr"` en verde, con cada defecto sembrado
      detectado, y en rojo sobre 00d30651 sin los ADR.
- [x] T6. Deuda de excepciones mudas en `docs/architecture/adr/deuda_excepciones_mudas.json` y la prueba que impide
      que crezca. (RF-40)
      Hecho cuando: `pytest -q tests/test_interactive_architecture.py -k "silent"` en verde, y en rojo sobre 00d30651
      sin la deuda.
      RF y sus pruebas (una por RF; todas en el mapa `D:/csg/PM_IMPL/PISTA3/MARCAS-PISTA3/mapa_T_RF_pruebas.tsv`):
      T4 RF-34: `tests/test_interactive_architecture.py::test_to_be_checker_detects_each_seeded_defect` (línea 609).
      T4 RF-35: `tests/test_interactive_architecture.py::test_to_be_checker_detects_each_seeded_defect` (línea 609).
      T5 RF-36: `tests/test_interactive_architecture.py::test_adrs_are_complete_and_coherent_with_the_code` (línea 485).
      T5 RF-37: `tests/test_interactive_architecture.py::test_adr_checker_flags_bad_citations_and_unknown_elements` (línea 574).
      T5 RF-38: `tests/test_interactive_architecture.py::test_adr_checker_detects_each_seeded_defect` (línea 563).
      T5 RF-39: `tests/test_interactive_architecture.py::test_adr_checker_detects_each_seeded_defect` (línea 563).
      T5 RF-41: `tests/test_interactive_architecture.py::test_adr_checker_detects_each_seeded_defect` (línea 563).
      T6 RF-40: `tests/test_interactive_architecture.py::test_silent_broad_excepts_do_not_grow_beyond_registered_debt` (línea 698).
      T4 a T6 hechas el 2026-11-15 (MARCAS-PISTA3; código de 79d1da10): rojo sobre 00d30651 con solo la prueba,
      `D:/csg/PM_IMPL/PISTA3/MARCAS-PISTA3/humo_034_rojo.log` (5 F por aserción, rojo=VALIDO: falta la TO-BE, los ADR y la
      deuda); verde `humo_034_verde.log` (5 passed) y la suite entera sobre el árbol de e182c823 con las 14 variables CSG_*: `D:/csg/INTEGRA_54/g107/integra_g12f13_82_183656.log` (línea 1202) «Puerta de calidad: 9582 pruebas, 0 fallidas, 0 omitidas.»
