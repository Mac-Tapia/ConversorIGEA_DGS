# Tareas — Spec 034

- [x] T1. Spec retrospectiva y tabla RF → código → pruebas. (RF-1 a RF-33)
      Hecho cuando: cada RF tiene su fila en `plan.md`.
- [x] T2. Las pruebas del motor base y del contrato de fuentes citan su RF en el docstring de
      su módulo; prueba de arranque de las herramientas de catálogo y esquema. (RF-1 a RF-33)
      Hecho cuando: `grep -rnoE "034:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-33 y esas
      pruebas pasan.
- [x] T3. `CODIGO_FUENTE.md` atribuye a la 034 cada fichero que decía solo «base». (RF-1 a RF-33)
      Hecho cuando: `pytest -q tests/test_trazabilidad_specs.py -k base` en verde.
