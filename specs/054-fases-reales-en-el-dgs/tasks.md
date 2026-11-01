# Tareas — Spec 054

- [x] T1. Fases de la fuente en el modelo y en el DGS: tipos de línea, barras, cubículos, SED y
      cargas monofásicos. (RF-1 a RF-6, RF-8)
      Hecho cuando: las pruebas que citan sus RF pasan y un alimentador trifásico sale igual byte a byte.
      Hecho el 2026-11-01: `fases_de_sed` (VNR-GIS), `con_fases`, `letras_de_fase`, `it2p_de` y
      `write_dgs`; el validador acepta las columnas y los tipos por fases. `tests/test_fases_reales.py`.
- [x] T0. [DIgSILENT] Sonda en una copia de NJA202: cómo acepta DIgSILENT la SED monofásica y qué
      da cada flujo. (RF-4, RF-7)
      Hecho cuando: se sabe qué valores acepta y qué flujo hace falta.
      Hecho el 2026-11-01: ver la tabla del contexto de la spec; copia borrada.
- [x] T2. Flujo desequilibrado donde haya monofásicos: importación, calibración y estudios. (RF-7)
      Hecho cuando: las pruebas que citan RF-7 pasan.
      Hecho el 2026-11-01: `red_con_monofasicos` en `flujo_de_carga` (9 guiones) y en la
      aceptación de la importación.
- [ ] T3. [DIgSILENT] NJA202 reimportado con sus fases y calibrado con el flujo desequilibrado. (Todos)
      Hecho cuando: P y Q de cabecera dentro del 1 % con las SED monofásicas servidas.
