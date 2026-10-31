# Tareas — Spec 044

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [x] T0. Rechazo puntual de métricas ausentes/no finitas sin dependencias nuevas. (RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_verificacion_top_k_completa.py tests/test_digital_twin_evolutivo.py` pasa con el reproductor y sus parámetros de T0; la integración completa queda en T3.

- [ ] T1. Particiones independientes y política previa. (RF-1, RF-2, RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_evaluacion_modelos.py tests/test_digital_twin_particiones.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [ ] T2. Calibración y puertas por familia. (RF-4, RF-5, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_calibracion_independiente.py tests/test_digital_twin_oraculo.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Cerrar la verificación parcial de alternativas. (RF-6, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_verificacion_top_k_completa.py tests/test_digital_twin_evolutivo.py tests/test_digital_twin_evaluacion.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4 [DIgSILENT]. Persistencia y aceptación en el motor real. (RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_verificacion_top_k_nativa.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.

## Evidencia de ejecución

Pendiente. Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.


Ejecución 2026-10-31: ver [registro y pendientes](../../docs/EJECUCION_IA_2026-10-31.md).
