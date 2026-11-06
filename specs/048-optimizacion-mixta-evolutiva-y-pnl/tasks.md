# Tareas — Spec 048

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [x] T1. Problema mixto y caché con contexto. (RF-1, RF-2, RF-5)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_problema_optimizacion.py tests/test_digital_twin_evolutivo.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.
      Hecho el 2026-11-06: `digital_twin/problema_optimizacion.py` (variables tipadas con unidad, origen y
      coste trazable; `evaluar_vector`, `validar_vector`, `reparar`, `clave_evaluacion`, `CacheEvaluaciones`,
      `ContextoSintetico`) y `problema_bancos`/`problema_maniobras` en `evolutivo.py` sobre el flujo del gemelo.
      Rama `feat/048-optimizacion-mixta`; `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q
      tests/test_problema_optimizacion.py tests/test_digital_twin_evolutivo.py`: 37 passed, 0 omitidas.
      Sin cambio de lector ni de modelo del DGS: no aplican los TXT reales.

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

