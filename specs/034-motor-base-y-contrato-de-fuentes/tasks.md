# Tareas — Spec 034

- [x] T1. Spec retrospectiva y tabla RF → código → pruebas. (RF-1 a RF-33)
      Hecho cuando: cada RF tiene su fila en `plan.md`.
- [x] T2. Las pruebas del motor base y del contrato de fuentes citan su RF en el docstring de
      su módulo; prueba de arranque de las herramientas de catálogo y esquema. (RF-1 a RF-33)
      Hecho cuando: `grep -rnoE "034:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-33 y esas
      pruebas pasan.
- [x] T3. `CODIGO_FUENTE.md` atribuye a la 034 cada fichero que decía solo «base». (RF-1 a RF-33)
      Hecho cuando: `pytest -q tests/test_trazabilidad_specs.py -k base` en verde.
- [ ] T4. C4 TO-BE en `docs/architecture/workspace_to_be.dsl`, que extiende `workspace.dsl` sin redefinirlo, con sus
      vistas y la Aclaración de RF-31. (RF-34, RF-35)
      Hecho cuando: `pytest -q tests/test_interactive_architecture.py -k "to_be"` en verde, y en rojo sobre 00d30651
      sin la TO-BE.
- [ ] T5. ADR por decisión de frontera en `docs/architecture/adr/` (monolito por capas, fachada de servicios, contrato
      OpenAPI, escritura duradera, avisos, DXF con DWG opcional, colas por carriles, MCP de solo lectura y editor del
      plano), con su formato en `adr/README.md` y la prueba que los compara con el código. (RF-36, RF-37, RF-38,
      RF-39, RF-41)
      Hecho cuando: `pytest -q tests/test_interactive_architecture.py -k "adr"` en verde, con cada defecto sembrado
      detectado, y en rojo sobre 00d30651 sin los ADR.
- [ ] T6. Deuda de excepciones mudas en `docs/architecture/adr/deuda_excepciones_mudas.json` y la prueba que impide
      que crezca. (RF-40)
      Hecho cuando: `pytest -q tests/test_interactive_architecture.py -k "silent"` en verde, y en rojo sobre 00d30651
      sin la deuda.
