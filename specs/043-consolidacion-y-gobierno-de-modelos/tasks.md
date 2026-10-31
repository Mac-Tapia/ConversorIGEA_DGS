# Tareas — Spec 043

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [ ] T1. Integrar registro y exclusión de GPU. (RF-1, RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_model_registry.py tests/test_training_coordinator.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [ ] T2. Contrato común y custodia de datos. (RF-2, RF-3, RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_experimentos.py tests/test_asistente_dataset_entrenamiento.py tests/test_asistente_calidad_datos.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Runner, reanudación y promoción con reapertura. (RF-5, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_experimentos_runner.py tests/test_reentrenamiento_integral.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4. Visibilidad y aceptación de integración. (RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_modelos_web.py tests/test_model_registry.py tests/test_training_coordinator.py tests/test_experimentos.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan.

## Evidencia de ejecución

Pendiente. Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.

