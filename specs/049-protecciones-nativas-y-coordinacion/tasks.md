# Tareas — Spec 049

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [ ] T1. Disponibilidad real e inventario de entradas. (RF-1, RF-2, RF-3)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_datos.py tests/test_estudios_pf.py tests/test_datos_empresa.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [ ] T2. Escenarios de falla y captura nativa. (RF-4, RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_pf_guion.py tests/test_protecciones_datos.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Coordinación, reporte y web. (RF-5, RF-6, RF-7, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_coordinacion.py tests/test_protecciones_web.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4 [DIgSILENT]. Validación y persistencia de protecciones en PowerFactory. (RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_protecciones_nativas.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.

## Evidencia de ejecución

Pendiente. Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.

