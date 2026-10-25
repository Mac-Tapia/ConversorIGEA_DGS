# Tareas — Spec 026, asistente de órdenes

Una tarea cada vez, pruebas primero. Al terminarla: suite en verde, `- [x]`, y parar.

- [x] T1. Catálogo de tareas: cada tarea de RF-11 con su función de `services`, sus datos, si
      escribe y su carril. (RF-8, RF-9, RF-10, RF-11)
      Hecho cuando: `pytest -q tests/test_asistente_tareas.py` en verde (cada tarea apunta a una
      función que existe y cada dato obligatorio tiene tipo).
      Hecho el 2026-10-24.
- [x] T2. Ejemplos sintéticos con los nombres reales del espacio. (RF-21)
      Hecho cuando: `pytest -q tests/test_asistente_sinteticos.py` en verde.
      Hecho el 2026-10-24.
- [x] T3. Transformer (tokenizador, codificador, tarea y BIO), entrenamiento en GPU, registro y
      promoción por puertas; `tools/asistente_entrenar.py`. (RF-2, RF-19, RF-20)
      Hecho cuando: `pytest -q tests/test_asistente_transformer.py` en verde, con acierto de tarea
      en frases no vistas por encima del umbral del perfil.
      Hecho el 2026-10-24: por caracteres, con los datos decididos por palabra (carácter a carácter
      el F1 de los datos era 0,13); con los 98 alimentadores, 61 proyectos y 4 zonales reales,
      acierto de tarea 98,1 % y F1 de los datos 0,87 en la prueba fija; el segundo reentrenamiento
      ya incluyó una orden confirmada en la web.
- [x] T4. Cliente de Ollama local y medida de qwen2.5:3b frente a llama3.1:8b
      (`tools/asistente_medir_ollama.py`). (RF-3, RF-5)
      Hecho cuando: `pytest -q tests/test_asistente_ollama.py` en verde y la medida elige modelo.
      Hecho el 2026-10-24: llama3.1:8b (76 %) frente a qwen2.5:3b (74 %), los dos en 1,5 s de
      mediana; Ollama suelta la GPU antes de cada entrenamiento (con su modelo cargado, entrenar dio
      «CUDA error: out of memory») y no retiene el modelo más de 60 s.
- [x] T5. Intérprete híbrido y plan con datos contrastados y razonamiento. (RF-2 a RF-7)
      Hecho cuando: `pytest -q tests/test_asistente_interprete.py` en verde.
      Hecho el 2026-10-24; los requisitos de cada tarea (entradas del espacio) se comprueban en el
      plan con la misma validación de la web: «carga la fuente» sin entradas se ofrecía para
      confirmar y fallaba después en la ruta.
- [x] T6. Web: rutas de orden, confirmación y corrección, ejecución por los trabajos de la web;
      consola en el front. (RF-1, RF-8, RF-9, RF-10, RF-12, RF-15, RF-19)
      Hecho cuando: `pytest -q tests/test_asistente_web.py` en verde y `npm run build` sin errores.
      Hecho el 2026-10-24: pestaña «Asistente»; carril `asistente`, que solo espera.
- [x] T7. Informes desde la consola y clasificador de dos niveles con los subtipos del perfil.
      (RF-13 a RF-16)
      Hecho cuando: `pytest -q tests/test_asistente_clasificador.py` en verde.
      Hecho el 2026-10-24: acierto de tipo 100 % y de subtipo 98,7 % en la prueba fija.
- [x] T8. Índice del proyecto con embeddings locales o BM25 y respuestas con cita. (RF-17, RF-18)
      Hecho cuando: `pytest -q tests/test_asistente_indice.py` en verde.
      Hecho el 2026-10-24: con BM25; los embeddings se usan si `nomic-embed-text` está instalado
      en Ollama (aún no se ha descargado).
- [x] T9. Vigilancia de trabajos, modelos, calidad y suite nocturna. (RF-22 a RF-25)
      Hecho cuando: `pytest -q tests/test_asistente_vigilancia.py` en verde.
      Hecho el 2026-10-24.
- [x] T10. Mejoras en rama aparte (`git worktree`), sin fusionar, y registro de decisiones.
      (RF-26 a RF-28)
      Hecho cuando: `pytest -q tests/test_asistente_mejoras.py` en verde.
      Hecho el 2026-10-24.
- [x] T11. Internet con filtro de identificadores, registro y propuestas de librerías.
      (RF-29 a RF-32)
      Hecho cuando: `pytest -q tests/test_asistente_internet.py` en verde.
      Hecho el 2026-10-24: probado contra GitHub y arXiv reales (8 repositorios y 5 artículos);
      «busca en github caída de tensión en IN111» se bloquea sin salir de la máquina.
- [ ] T12. Aceptación: una orden real de cada tarea de RF-11 desde la consola, en DIgSILENT;
      validación RF por RF; suite completa con las siete variables y ninguna omitida.
      (Todos)
      Hecho cuando: `grep -rnoE "026:RF-[0-9]+" tests | sort -u` lista los 32 RF y la suite pasa.
      En curso el 2026-10-24: los 32 RF citados por pruebas en verde; en la web real, consultas
      (estado, proyectos, PIDE, episodios, preguntas con cita, clasificación, búsqueda y bloqueo),
      evaluación del gemelo lanzada sola, reentrenar la PINN confirmado y planes de las órdenes que
      escriben (sistema Pisco con 2026-07, verificar el «Caso base» de IN111–TA225). Falta
      confirmar en DIgSILENT las tareas que lo usan (sistema completo, cargas, obras, estudios,
      transferencia, PIDE e informes): el 2026-10-24 otra sesión tenía DIgSILENT ocupado y el espacio
      no tenía entradas.
