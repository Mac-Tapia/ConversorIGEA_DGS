# Tareas — Spec 033

- [x] T1. `tools/estado_specs.py` y `tests/test_trazabilidad_specs.py`, que fallan con cada
      hallazgo de la revisión. (RF-1 a RF-21)
      Hecho cuando: las comprobaciones reproducen los hallazgos de
      `docs/REVISION_SPECS_2026-10-29.md` antes de corregir nada.
- [x] T2. Numeración: aclaraciones, huecos declarados, 003 y 031 reservadas, 014 T8d.
      (RF-1 a RF-4)
      Hecho cuando: `pytest -q tests/test_trazabilidad_specs.py -k "numero or huecos or define or forma"` en verde.
- [x] T3. Tareas: «Hecho cuando:» en todas, marca `[DIgSILENT]`, tareas partidas y tareas retro
      para los RF que no tenían. (RF-5 a RF-7)
      Hecho cuando: `pytest -q tests/test_trazabilidad_specs.py -k "tarea or digsilent"` en verde.
- [x] T4. Estado: vocabulario cerrado y coherente con las casillas; 013 con sus tareas, 029 y
      030 con su plan, 017 con su cambio de diseño. (RF-8 a RF-13)
      Hecho cuando: `pytest -q tests/test_trazabilidad_specs.py -k "estado or cumplida or implementada or aprobada or borrador or plan"` en verde.
- [x] T5. Pruebas: cada RF de una spec con el código cerrado citado, también los de letra;
      cada fichero de pruebas con su spec. (RF-16 a RF-18)
      Hecho cuando: `pytest -q tests/test_trazabilidad_specs.py -k "prueba or cita"` en verde.
- [x] T6. Spec 034 y `CODIGO_FUENTE.md` sin «base»; 018, 030 y 032 con sus ficheros. (RF-19, RF-20)
      Hecho cuando: `pytest -q tests/test_trazabilidad_specs.py -k "indice or base"` en verde.
- [x] T7. `specs/README.md` generado, `CLAUDE.md` reducido, commits y skill. (RF-14, RF-15, RF-21, RF-22)
      Hecho cuando: `python tools/estado_specs.py --comprobar` sale con 0 y la suite en verde.
