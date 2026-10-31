# Tareas — Spec 045

Estado inicial: todas pendientes; este documento no acredita ejecución.
Leer [spec.md](spec.md), [plan.md](plan.md) y sus contratos dependientes antes de editar.
Cada tarea exige pruebas primero, evidencia y revisión del diff propio.

- [ ] T1. Versionar episodios, contexto y grafo. (RF-1, RF-2, RF-3, RF-10)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_gemelo_contratos_v2.py tests/test_digital_twin_episode.py tests/test_digital_twin_buffer.py tests/test_digital_twin_snapshot_pf.py` pasa
      y están guardadas las evidencias adicionales descritas en T1 del plan.

- [ ] T2. Física representada y fronteras comprobables. (RF-4, RF-5, RF-6, RF-7)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_pinn_fisica_y_fronteras.py tests/test_digital_twin_flujo.py tests/test_digital_twin_in111_ta225.py` pasa
      y están guardadas las evidencias adicionales descritas en T2 del plan.

- [ ] T3. Ablaciones, dominio y candidato opcional PyG. (RF-8, RF-9)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_benchmark_pinn.py tests/test_digital_twin_oraculo.py` pasa
      y están guardadas las evidencias adicionales descritas en T3 del plan.

- [ ] T4 [DIgSILENT]. Contraste del gemelo con la red nativa. (RF-11)
      Hecho cuando: `.venv/Scripts/python.exe -m pytest -q tests/test_gemelo_fisico_nativo.py` pasa
      y están guardadas las evidencias adicionales descritas en T4 del plan, con motor real, reapertura y relectura; no se admiten dobles para cerrar esta tarea.

## Evidencia de ejecución

Pendiente. Anotar aquí, al ejecutar cada tarea, revisión, datos/contexto, comando,
resultado, informe y limitaciones; no marcar casillas por existir código o por una
simulación que solo converge.

