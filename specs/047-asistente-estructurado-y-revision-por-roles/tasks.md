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

- [x] T5. Destilación reproducible del maestro de sesión y ensayo del alumno. (RF-11, RF-12, RF-13, RF-14, RF-15)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_destilacion_integral.py tests/test_evaluacion_modelos.py` pasa, se ejecuta entrenamiento CUDA real con comparación supervisado/destilado, reapertura en proceso nuevo y ensayo del intérprete/plan; se informa por separado cualquier bloqueo de promoción por datos humanos.

- [x] T6. Auditar, materializar y evaluar 200 propuestas únicas, sin fuga y con puertas por alcance. (RF-13, RF-16, RF-17, RF-18)
      Hecho cuando: pruebas de `tests/test_aceptacion_agente.py` y regresiones de órdenes fijas/intérprete pasan; se ejecutan selección local de configuración y evaluación sellada de las 200 propuestas, con informe de métricas/errores/bloqueos y sin escrituras nativas.

## Evidencia de ejecución

T6: 200 propuestas únicas, 27 tareas, 54 familias; auditoría sin solapamiento de
texto/grupo con entrenamiento. Evaluación local Llama3.1:8b: 157/200 tareas,
F1 0,864646; humanas 2/3 por separado. Uso asistido **rechazado por calidad**,
sin activación ni escrituras nativas. El cierre de la tarea de evaluación no
acredita aceptación del agente. [Informe y pendientes](../../docs/ACEPTACION_INTEGRAL_AGENTE_2026-10-31.md).

T5: seis entrenamientos CUDA, semilla elegida por selección, recarga en proceso nuevo,
prueba separada y diagnóstico híbrido de las 27 tareas. Candidato bloqueado, sin
promoción. [Metodología y evidencia](../../docs/DESTILACION_AGENTE_2026-10-31.md).
Las tareas T1–T4 conservan pendientes reales; no se cierran por este entrenamiento.

Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.

