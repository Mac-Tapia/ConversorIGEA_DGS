# Tareas — Spec 043

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [ ] T1. Integrar registro y exclusión de GPU. (RF-1, RF-6)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_model_registry.py tests/test_training_coordinator.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [x] T2. Contrato común y custodia de datos. (RF-2, RF-3, RF-4)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_experimentos.py tests/test_asistente_dataset_entrenamiento.py tests/test_asistente_calidad_datos.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Runner, reanudación y promoción con reapertura. (RF-5, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_experimentos_runner.py tests/test_reentrenamiento_integral.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4. Visibilidad y aceptación de integración. (RF-8)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_modelos_web.py tests/test_model_registry.py tests/test_training_coordinator.py tests/test_experimentos.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan.

- [x] T5. Preparar repositorios GitHub con URL, commit y licencia fijados, sin sobrescribir copias modificadas ni imponer dependencias al núcleo. (RF-9, RF-10, RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_upstream_ia.py` pasa y `tools/preparar_upstream_ia.py --verificar` valida las copias reales del catálogo.

## Evidencia de ejecución

- [ ] T6. Instalar y verificar bibliotecas y pesos faltantes del catálogo local. (RF-12)
      Hecho cuando: el catálogo fijado, las pruebas de preparación, las descargas completas y las operaciones reales de bibliotecas/modelos tienen informes; `pip check` pasa sin cambiar las versiones previas del núcleo. Descargar no cierra entrenamiento, integración o aceptación eléctrica.

T5: siete pruebas con Git y subprocesos reales pasaron; se verificaron las nueve
copias públicas. Catálogo y reproducción en [reutilización GitHub](../../docs/REUSO_GITHUB_IA_2026-10-31.md).
La implementación de adaptadores y su aceptación permanecen en 045–048.

T6 parcial: 33 paquetes instalados, cero versiones previas del núcleo cambiadas,
`pip check` correcto; nueve ensayos de entorno/GPU y un ensayo real Ipopt pasaron.
Catálogos fijados y descargas reanudables implementados; conservar abierta hasta
verificar todos los pesos completos. [Informe](../../docs/ACEPTACION_INTEGRAL_AGENTE_2026-10-31.md).

Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.


Ejecución 2026-10-31: ver [registro y pendientes](../../docs/EJECUCION_IA_2026-10-31.md).

Las tareas abiertas pueden contener código parcial: el registro distingue implementación, datos reales, verificación y aceptación pendiente.
