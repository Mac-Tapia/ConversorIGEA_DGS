# Tareas — Spec 041

- [x] T1. Núcleo del reparto probabilístico. (RF-1, RF-2, RF-3, RF-5, RF-6, RF-7)
      Hecho cuando: `pytest -q tests/test_reparto_probabilistico.py` en verde.
      Hecho el 2026-10-31.
- [x] T2. Guion: muestras cuadradas en el mismo caso, P50 escrito, uno y varios alimentadores;
      SED de 3.1 fijas. (RF-4, RF-5, RF-8, RF-9)
      Hecho cuando: `pytest -q tests/test_reparto_probabilistico.py tests/test_ajuste_cabecera_guion.py
      tests/test_ajuste_proyecto_guion.py` en verde.
      Hecho el 2026-10-31.
- [x] T3. Web: libro de 3.1 guardado, plan con los parámetros, bandas en el informe. (RF-6, RF-9)
      Hecho cuando: el front compila y las pruebas de la web en verde.
      Hecho el 2026-10-31.
- [x] T4. [DIgSILENT] NA293 recalibrado desde la web con el reparto probabilístico.
      Hecho cuando: el informe da P05/P50/P95 por SED de mayor a menor potencia y la probabilidad
      de sobrecarga, y la misma semilla repite los números.
      Hecho el 2026-10-31, con tools/sistema_web.py (periodo 2026-09, coincidente): NA293 200/200
      repartos cuadrados, fuente las 15 fijas (dispersión 0,45, pendiente 0,13), P50 escrito y
      validado; SM298 200/200 (0,60 y 0,32), P50 escrito y validado.
- [x] T5. El P50 conserva la base total del determinista. (RF-5)
      Hecho cuando: `tests/test_reparto_probabilistico.py` (041:RF-5) en verde con su rojo por aserción.
      Hecho el 2026-11-26: rojo `D:/csg/PM_IMPL/VNR_SM115/rojo_p50.log` (1194 frente a 882); verde 194 passed
      (`verde_p50.log`) y 875 passed (`verde_vecinas.log`).
