# Tareas — Spec 026, asistente de órdenes

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [ ] T1. Catálogo de tareas: cada tarea de RF-11 con su función de `services`, sus datos, si
      escribe y su carril. (RF-8, RF-9, RF-10, RF-11)
      Hecho cuando: `pytest -q tests/test_asistente_tareas.py` en verde (cada tarea apunta a una
      función que existe y cada dato obligatorio tiene tipo).
- [ ] T2. Ejemplos sintéticos con los nombres reales del espacio. (RF-21)
      Hecho cuando: `pytest -q tests/test_asistente_sinteticos.py` en verde.
- [ ] T3. Transformer (tokenizador, codificador, tarea y BIO), entrenamiento en GPU, registro y
      promoción por puertas; `tools/asistente_entrenar.py`. (RF-2, RF-19, RF-20)
      Hecho cuando: `pytest -q tests/test_asistente_transformer.py` en verde, con acierto de tarea
      en frases no vistas por encima del umbral del perfil.
- [ ] T4. Cliente de Ollama local y medida de qwen2.5:3b frente a llama3.1:8b
      (`tools/asistente_medir_ollama.py`). (RF-3, RF-5)
      Hecho cuando: `pytest -q tests/test_asistente_ollama.py` en verde y la medida elige modelo.
- [ ] T5. Intérprete híbrido y plan con datos contrastados y razonamiento. (RF-2 a RF-7)
      Hecho cuando: `pytest -q tests/test_asistente_interprete.py` en verde.
- [ ] T6. Web: rutas de orden, confirmación y corrección, ejecución por los trabajos de la web;
      consola en el front. (RF-1, RF-8, RF-9, RF-10, RF-12, RF-15, RF-19)
      Hecho cuando: `pytest -q tests/test_asistente_web.py` en verde y `npm run build` sin errores.
- [ ] T7. Informes desde la consola y clasificador de dos niveles con los subtipos del perfil.
      (RF-13 a RF-16)
      Hecho cuando: `pytest -q tests/test_asistente_clasificador.py` en verde.
- [ ] T8. Índice del proyecto con embeddings locales o BM25 y respuestas con cita. (RF-17, RF-18)
      Hecho cuando: `pytest -q tests/test_asistente_indice.py` en verde.
- [ ] T9. Vigilancia de trabajos, modelos, calidad y suite nocturna. (RF-22 a RF-25)
      Hecho cuando: `pytest -q tests/test_asistente_vigilancia.py` en verde.
- [ ] T10. Mejoras en rama aparte (`git worktree`), sin fusionar, y registro de decisiones.
      (RF-26 a RF-28)
      Hecho cuando: `pytest -q tests/test_asistente_mejoras.py` en verde.
- [ ] T11. Internet con filtro de identificadores, registro y propuestas de librerías.
      (RF-29 a RF-32)
      Hecho cuando: `pytest -q tests/test_asistente_internet.py` en verde.
- [ ] T12. Aceptación: una orden real de cada tarea de RF-11 desde la consola, en DIgSILENT;
      validación RF por RF; suite completa con las siete variables y ninguna omitida.
      (Todos)
      Hecho cuando: `grep -rnoE "026:RF-[0-9]+" tests | sort -u` lista los 32 RF y la suite pasa.
