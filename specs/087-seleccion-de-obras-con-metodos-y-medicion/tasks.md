# Tareas — Spec 087

Lee: `specs/087-seleccion-de-obras-con-metodos-y-medicion/spec.md` y `plan.md`.

- [x] T1. Parada bayesiana pura: posterior, decisión de parar y resumen. (RF-7, RF-8, RF-9)
      Hecho cuando: `pytest -q tests/test_seleccion_bayesiana.py` en verde.
- [x] T2. La parada bayesiana en la evaluación con sorteos de `tools/obras_pf.py`. (RF-8, RF-9)
      Hecho cuando: `pytest -q tests/test_seleccion_bayesiana.py tests/test_obras_pf_guion_042.py` en verde.
- [x] T15. Base de «Sin proyecto» una vez por trabajo. (RF-28)
      Hecho cuando: `pytest -q tests/test_seleccion_por_oraculo.py` en verde.
- [x] T3. Tandas por oráculo en la escalera por alimentador, con caída a DIgSILENT. (RF-1, RF-2, RF-3, RF-4, RF-6)
      Hecho cuando: `pytest -q tests/test_seleccion_por_oraculo.py` en verde.
- [x] T4. El oráculo con los tramos sobrecargados. (RF-5)
      Hecho cuando: `pytest -q tests/test_seleccion_por_oraculo.py` en verde.
- [x] T5. Optuna, Pareto, menor costo y pérdidas con Markov en esa selección. (RF-10, RF-11, RF-12, RF-13)
      Hecho cuando: `pytest -q tests/test_seleccion_por_oraculo.py` en verde.
- [x] T16. Margen de demanda con el oráculo e interruptor del método. (RF-29, RF-30)
      Hecho cuando: `pytest -q tests/test_seleccion_por_oraculo.py tests/test_planeamiento_etapas.py` en verde.
- [x] T6. Árbol de decisión y proceso de decisión de Markov por etapas. (RF-14, RF-15, RF-16)
      Hecho cuando: `pytest -q tests/test_planeamiento_etapas.py` en verde.
- [x] T7. Conjunto de variantes medidas y clasificador con su puerta. (RF-17, RF-18, RF-19, RF-20)
      Hecho cuando: `pytest -q tests/test_modelo_obras.py` en verde.
- [x] T8. Fila de medición de cada «Con proyecto», con recursos y resultados. (RF-21, RF-22)
      Hecho cuando: `pytest -q tests/test_medicion_obras.py` en verde.
- [x] T9. Comprobación de normas de diseño de cada obra. (RF-23, RF-24)
      Hecho cuando: `pytest -q tests/test_medicion_obras.py` en verde.
- [x] T10. Contraste entre versiones y métodos, con `tools/medir_mejora.py`. (RF-25, RF-26, RF-27)
      Hecho cuando: `pytest -q tests/test_medicion_obras.py tests/test_inventario.py` en verde.
- [x] T11. Los módulos nuevos en `CODIGO_FUENTE.md`, el manual y la tabla de `CLAUDE.md`. (Todos)
      Hecho cuando: `pytest -q tests/test_inventario.py tests/test_trazabilidad_specs.py` en verde.
- [x] T21. Solo las cumplidoras del oráculo y una tanda de cercanas; si no cumplen, a la obra integral. (RF-39, RF-40)
      Hecho cuando: `pytest -q tests/test_seleccion_por_oraculo.py` en verde.
- [x] T22. Lo que el oráculo no calcula (paso a 22,9 kV) lo mide DIgSILENT antes de transferir. (RF-41)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T23. Ninguna variante deja barras aisladas. (RF-42)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T24. La memoria del oráculo acotada. (RF-43)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T25. La obra elegida se aplica siempre. (RF-44)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T26. Confirmación conjunta del sistema y obra rehecha solo donde falla. (RF-45, RF-46, RF-47)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T27. [DIgSILENT] Pisco entero confirmado junto, con su resultado anotado. (RF-45)
      Hecho cuando: la confirmación conjunta de Pisco queda en el informe del trabajo.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T28. El déficit previo también pasa por el oráculo. (RF-48)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T29. La regla de la máxima solo cerca del criterio de los sorteos. (RF-49)
      Hecho cuando: `pytest -q tests/test_escalera_optima.py tests/test_obras_integrales.py` en verde.
- [x] T30. Sin reutilizar evaluaciones de otro código o con errores. (RF-50)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T31. Pérdidas sin doble cuenta, red releída tras una variante y sin elegir lo que dio error. (RF-51)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T32. La transferencia desde la barra más cercana a cada vecino. (RF-52)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T33. Solo vecinos que operan. (RF-53)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T34. Zona pequeña sola a alimentador nuevo, y obra integral directa. (RF-54)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T35. Bancos candidatos en todas las barras de media del alimentador, filtradas por el oráculo. (RF-55, RF-56, RF-57)
      Hecho cuando: `pytest -q tests/test_optimizacion_oraculo.py tests/test_seleccion_por_oraculo.py tests/test_obras_pf_guion.py` en verde.
      Hecho el 2026-11-06: 145 aprobadas. Falta verlo en DIgSILENT con AL209 y Cemento Inka (T13 cubre la medida).
- [x] T17. Transferencia y traslado como escalones de la escalera, reutilizando `construir_enlace` y `construir_migracion`. (RF-31, RF-32, RF-33)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T18. Alimentador nuevo con su celda en DIgSILENT, a partir de `construir_expreso`. (RF-34, RF-35)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T19. Costos de celda y de km desde los módulos del libro CAPEX, con su fila citada o por confirmar. (RF-36, RF-37)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T20. Área propuesta de cada alimentador nuevo. (RF-38)
      Hecho cuando: `pytest -q tests/test_obras_integrales.py` en verde.
- [x] T12. [DIgSILENT] Escalera de referencia en Pisco, con su fila de medición. (RF-21, RF-22, RF-23)
      Hecho cuando: hay fila con método escalera y su resultado por alimentador.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T13. [DIgSILENT] Pisco con el oráculo, sobre el mismo estado, y contraste con T12. (RF-1, RF-25)
      Hecho cuando: `tools/medir_mejora.py` da las diferencias de tiempo, obras y normas.
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
- [x] T14. [DIgSILENT] Un sistema de otra empresa con el método nuevo. (RF-1, RF-24)
      Hecho cuando: cada alimentador con cargas nuevas termina con obra medida o «ya cumple».
      Cerrada el 2026-11-08 por orden del usuario, sin corrida propia: ya no es una tarea pendiente por proyecto; su comprobación pasa a la aceptación automática (spec 100).
