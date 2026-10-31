# Tareas — Spec 047

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [ ] T1. Esquema de salida y entidades del contexto activo. (RF-1, RF-2, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_salida_estructurada.py tests/test_asistente_interprete.py tests/test_asistente_ollama.py tests/test_asistente_tareas.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [ ] T2. Recuperación híbrida con reranker contrastado. (RF-3, RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_reranker.py tests/test_asistente_indice.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Revisión por roles acotada y trazable. (RF-5, RF-6, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_revision_roles.py tests/test_asistente_tareas.py tests/test_asistente_web.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4. Evaluación real y ajuste condicionado. (RF-8, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_asistente_ajuste_condicionado.py tests/test_asistente_qlora.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan.

## Evidencia de ejecución

Pendiente. Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.

