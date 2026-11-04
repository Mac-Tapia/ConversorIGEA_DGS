# Tareas — Spec 076

- [x] T1 Spec, plan, tareas, fila en `CLAUDE.md`, índice en `CODIGO_FUENTE.md` y reservas de numeración. (RF-17)
      Hecho cuando: `tests/test_trazabilidad_specs.py` y `tests/test_inventario.py` pasan.
- [x] T2 Comprobaciones de fuente, cifras y nombres. (RF-4, RF-5, RF-6, RF-16, RF-18, RF-26)
      Hecho cuando: `tests/test_preguntas_entregables.py` las cubre, también con filas malas.
- [x] T3 Herramienta: reparto, huella, hoja e informe. (RF-7, RF-8, RF-9, RF-10, RF-11, RF-12, RF-13, RF-27)
      Hecho cuando: `tests/test_preguntas_entregables.py` pasa.
- [x] T4 Filas de los entregables y de los temas, con reglas sin código y contradicciones. (RF-1, RF-2, RF-3, RF-14, RF-15, RF-17)
      Hecho cuando: `verificar` termina sin errores y la huella queda fijada.
- [x] T5 Catálogo de hechos de la web y generador estocástico. (RF-19, RF-20, RF-21, RF-22, RF-23, RF-24, RF-25)
      Hecho cuando: `tests/test_preguntas_entregables.py` pasa con varias semillas.
- [x] T6 Revisión del operador y decisión del usuario sobre su uso.
      Hecho cuando: el operador devuelve la hoja, `importar` la marca y el usuario decide si entra al corpus.
      Hecho el 2026-11-03 por el maestro, en el rol del revisor por orden del usuario («tú debes cumplir el rol de humano»):
      443 filas marcadas contra el código, con `importar --revisor maestro`; la decisión de uso sigue en T8.
- [x] T7 La marca del maestro queda como suya y no como humana. (RF-28)
      Hecho cuando: `pytest -q tests/test_preguntas_entregables.py -k maestro` en verde.
- [ ] T8 Decisión del usuario sobre si el conjunto marcado entra al corpus del RAG o a un entrenamiento. (RF-16)
      Hecho cuando: el usuario lo decide; mientras tanto el conjunto no entra en ninguno.
