# Tareas 101

- [x] T1. Selección de las SED que se cambian solas, sin repetir lo aplicado. (RF-1, RF-4, RF-6, RF-12)
      Hecho cuando: `pytest -q tests/test_transformadores_automaticos.py` en verde.
- [x] T2. Rondas de cambio y recalibración dentro de la calibración aplicada, con su Registro y su resultado. (RF-2, RF-3,
      RF-5, RF-7, RF-8, RF-9, RF-10, RF-11, RF-13)
      Hecho cuando: `pytest -q tests/test_transformadores_automaticos.py` en verde.
- [x] T3. [DIgSILENT] Calibración de CA191 + CHN192 desde la web: termina válida y sin `iopt_lev`, sin pulsar ningún
      botón. (RF-2, RF-3)
      Hecho cuando: el informe de la última ronda da `cuadrado` y la relectura de las cargas cuadra.
      Evidencia (2026-11-10), proyecto de prueba nuevo `20261110-213621_CSG_TXT_2c220c91_1_CHN10` (espacio de prueba
      3a975e2f78834bb4, misma entrega de octubre que el del operador), por la web con `tools/sistema_web.py`: con los
      transformadores del archivo (SE20701 de 50 kVA con 1 506 kVA de cliente), la calibración puso en «Sin proyecto» los 6
      de la ficha NTP 370.400 (SE20701 3 × 630 kVA, SE20730 400 kVA…), sin pulsar nada; CA191 +0,39 % y CHN192 +0,36 %,
      VALIDO, `cuadrado`, sin remedios ni `iopt_lev`; las 194 cargas consumen lo escrito. El «Caso base» conserva los
      50 kVA y «Sin proyecto» los tiene en la variación `SED_NTP_` (sonda de solo lectura sobre el proyecto de prueba
      anterior, `20261110-211207_…`, con la misma calibración). Al hacerlo apareció RF-14: el cambio no quedaba en el informe (T4).
- [x] T4. Los transformadores de la primera pasada quedan en el informe que vale. (RF-14)
      Hecho cuando: `pytest -q tests/test_transformadores_automaticos.py` en verde y el informe de la T3 los lista con su
      aviso (083:RF-31).
- [x] T5. MEJ10-FIJAS (orden del usuario del 20-11): la propuesta de la ficha parte de los kVA de la fuente del grupo y anota la reconstrucción. (RF-15)
      Hecho cuando: rojo por aserción sobre 2f9de358 y verde con `tests/test_ajuste_cabecera_guion.py -k rf15`; la corrida en DIgSILENT la decide d8.
      Hecho el 2026-11-20 (d8, cierre de la fila gSIG por orden del usuario «nada abierto»): rojo D:/csg/PM_IMPL/MEJ10_FIJAS/rojo.log (test_101_rf15_la_propuesta_parte_de_los_kva_del_grupo_de_la_fuente); verde ídem; verde integrado del hueco de MEJ567 sobre c4326366 (D:/csg/PM_IMPL/MEJ567/verde_20261120_163024.log, 2423 passed, rc=0;
      npm_test_20261120_163024.log y e2e_20261120_163024.log) y la puerta gSIG que integra esta casilla (0 fallidas, 0 omitidas).
- [x] T6 TRANSFORMADORES-DEL-ARCHIVO (27-11). Recalibrar sin los transformadores de una calibración anterior. (RF-16)
      Hecho cuando: `tests/test_ajuste_cabecera_guion.py` y `tests/test_ajuste_cabecera_web.py` (101:RF-16) en verde
      con su rojo por aserción, y LL202 y LL203 recalibrados desde la web con la casilla. Hecho el 2026-11-27
      (evidencia en el commit que lo integra).
