# Tareas 101

- [x] T1. Selección de las SED que se cambian solas, sin repetir lo aplicado. (RF-1, RF-4, RF-6, RF-12)
      Hecho cuando: `pytest -q tests/test_transformadores_automaticos.py` en verde.
- [x] T2. Rondas de cambio y recalibración dentro de la calibración aplicada, con su Registro y su resultado. (RF-2, RF-3,
      RF-5, RF-7, RF-8, RF-9, RF-10, RF-11, RF-13)
      Hecho cuando: `pytest -q tests/test_transformadores_automaticos.py` en verde.
- [x] T3. [DIgSILENT] Calibración de CA101 + CHN102 desde la web: termina válida y sin `iopt_lev`, sin pulsar ningún
      botón. (RF-2, RF-3)
      Hecho cuando: el informe de la última ronda da `cuadrado` y la relectura de las cargas cuadra.
      Evidencia (2026-11-10), proyecto de prueba nuevo `20261110-213621_CSG_TXT_2c220c91_1_CHN10` (espacio de prueba
      3a975e2f78834bb4, misma entrega de octubre que el del operador), por la web con `tools/sistema_web.py`: con los
      transformadores del archivo (SE20701 de 50 kVA con 1 506 kVA de cliente), la calibración puso en «Sin proyecto» los 6
      de la ficha NTP 370.400 (SE20701 3 × 630 kVA, SE20730 400 kVA…), sin pulsar nada; CA101 +0,39 % y CHN102 +0,36 %,
      VALIDO, `cuadrado`, sin remedios ni `iopt_lev`; las 194 cargas consumen lo escrito. El «Caso base» conserva los
      50 kVA y «Sin proyecto» los tiene en la variación `SED_NTP_` (sonda de solo lectura sobre el proyecto de prueba
      anterior, `20261110-211207_…`, con la misma calibración). Al hacerlo apareció RF-14: el cambio no quedaba en el informe (T4).
- [x] T4. Los transformadores de la primera pasada quedan en el informe que vale. (RF-14)
      Hecho cuando: `pytest -q tests/test_transformadores_automaticos.py` en verde y el informe de la T3 los lista con su
      aviso (083:RF-31).
