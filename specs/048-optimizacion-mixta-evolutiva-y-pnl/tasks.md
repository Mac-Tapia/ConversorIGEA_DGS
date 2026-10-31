# Tareas — Spec 048

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [ ] T1. Problema mixto y caché con contexto. (RF-1, RF-2, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_problema_optimizacion.py tests/test_digital_twin_evolutivo.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [ ] T2. Benchmark de algoritmos actuales y pymoo. (RF-3, RF-6, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmark_optimizacion.py tests/test_digital_twin_evolutivo.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. PNL continua y selección top-k. (RF-4, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_adaptador_pnl.py tests/test_verificacion_top_k_completa.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4 [DIgSILENT]. Aplicación en variaciones y reapertura nativa. (RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_optimizacion_mixta_nativa.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.

## Evidencia de ejecución

Pendiente. Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.

