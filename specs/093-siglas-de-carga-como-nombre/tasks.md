# Tareas 093

Lee: `specs/093-siglas-de-carga-como-nombre/spec.md` y `plan.md`.

- [x] T1. La sigla nombra la carga nueva y la descripción la acompaña. (RF-1, RF-2, RF-3)
      Hecho cuando: `pytest -q tests/test_cargas_pf.py tests/test_cargas_pf_web.py` en verde.
- [x] T3. La ampliación se reconoce también por la descripción. (RF-4)
      Hecho cuando: `pytest -q tests/test_cargas_pf.py` en verde.
- [x] T2. [DIgSILENT] Cemento Inka (PI_15) en AL209 creada como `PI_15` con su variación `Carga_PI_15_AL209_…`. (RF-1)
      Hecho cuando: la aplicación de la web informa la carga PI_15 y su variación con la sigla.
      Hecho el 2026-11-07 en el Pisco de prueba `20261107-043049_CSG_TXT_SISTEMA_PISCO` (espacio 35ff5dab8b2b46a6): la aplicación
      por la web (`cargas_pf_aplicacion_2c84088afbc1.json`) informa PI_15 en AL209 con su variación `Carga_PI_15_AL209_20261107_080704`.
