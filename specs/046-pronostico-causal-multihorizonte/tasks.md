# Tareas — Spec 046

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [ ] T1. Preparación causal y corrección de GRU. (RF-1, RF-2, RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_series_causales.py tests/test_digital_twin_temporal.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [ ] T2. Adaptadores y salida multihorizonte. (RF-4, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pronostico_multihorizonte.py tests/test_digital_twin_temporal.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Benchmark, calibración y promoción temporal. (RF-6, RF-7, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_evaluacion_temporal.py tests/test_pronostico_multihorizonte.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

## Evidencia de ejecución

Pendiente. Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.

