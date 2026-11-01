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
- [x] T4. Coherencia de fases desde la cabecera. (RF-9)
      Hecho cuando: las pruebas que citan 054:RF-9 pasan y NJA202 y 0205 tienen todas sus SED con
      camino de fases desde la cabecera.
      Hecho el 2026-11-01: `coherencia_de_fases` en `sqlserver_vnr`; NJA202 849/849 y 0205 205/205.
- [x] T3. [DIgSILENT] NJA202 reimportado con sus fases y calibrado con el flujo desequilibrado. (Todos)
      Hecho cuando: P y Q de cabecera dentro del 1 % con las SED monofásicas servidas.
      Hecho el 2026-11-01: NJA202 (849 SED, 780 monofásicas) y 0205 (205 SED) por la web desde la
      copia VNR-GIS: calibración VÁLIDA en «Sin proyecto» (−0,04 % y −0,00 %), todas consumen, reparto
      proporcional; hicieron falta 054:RF-9 (fases desde la cabecera) y escribir el modo de la carga
      monofásica (`escribir_carga`, fases vacías a 8·10⁻¹¹).
