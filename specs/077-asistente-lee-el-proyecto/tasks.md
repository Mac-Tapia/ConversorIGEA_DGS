# Tareas — Spec 077

- [x] T1 Política de rutas y las tres lecturas. (RF-16, RF-17, RF-18, RF-19, RF-20, RF-21, RF-22, RF-23, RF-24, RF-25)
      Hecho cuando: `tests/test_asistente_lectura_proyecto.py` pasa.
- [x] T2 Corpus ampliado: ficheros, trozos, vigencia, caché por fichero y OpenAPI. (RF-1, RF-2, RF-3, RF-4, RF-5, RF-6, RF-7, RF-11, RF-12, RF-13, RF-14, RF-15)
      Hecho cuando: `tests/test_asistente_corpus_ampliado.py` pasa.
- [x] T3 Presentación de lo histórico y de lo no cumplido, y conexión con `pregunta` y el gobierno. (RF-8, RF-9, RF-10, RF-26, RF-27, RF-28, RF-29, RF-30, RF-31, RF-32, RF-33, RF-34, RF-35, RF-36)
      Hecho cuando: `tests/test_asistente_corpus_ampliado.py` y `tests/test_asistente_lectura_proyecto.py` pasan.
- [x] T4 Servidor MCP por stdio y su documentación. (RF-37, RF-38, RF-39, RF-40, RF-41)
      Hecho cuando: `tests/test_mcp_conversor.py` pasa.
- [x] T5 Conjuntos nuevos, comando de medición y puerta para servir el corpus ampliado. (RF-42, RF-43, RF-44, RF-45, RF-46, RF-47, RF-48, RF-49, RF-50)
      Hecho cuando: `tests/test_asistente_corpus_ampliado.py` pasa y `--corpus 077 --solo-conjunto` termina con código 0.
- [x] T8 Dos políticas y raíces locales: el árbol entero con LLM local, exclusiones, comprobación de que el LLM es local. (RF-51, RF-52, RF-53, RF-54, RF-55, RF-56, RF-57, RF-58, RF-66)
      Hecho cuando: `tests/test_asistente_lectura_local.py` pasa.
- [x] T9 Lo leído no sale, MCP restringido por defecto, lectores de binarios y topes. (RF-59, RF-60, RF-61, RF-62, RF-63, RF-64, RF-65, RF-67, RF-68)
      Hecho cuando: `tests/test_asistente_lectura_local.py` y `tests/test_mcp_conversor.py` pasan.
- [x] T6 Medición real con turno de GPU: calibrar y medir una vez el conjunto sellado del corpus ampliado.
      Hecho cuando: `docs/EVALUACION_ABSTENCION_077.json` existe; la lanza el usuario. Se mide, no se ajusta.
- [x] T10 Regla de forma: una pregunta que nombra un fichero del árbol o una ruta de la API va a `pregunta` antes del modelo, sin capturar órdenes de acción ni preguntas sin ruta. (RF-69, RF-70, RF-71, RF-72, RF-73, RF-74)
      Hecho cuando: `tests/test_asistente_lectura_proyecto.py` pasa con los tres casos reales del 2026-11-06, la pregunta de control y dos órdenes de acción, y pasan `tests/test_asistente_interprete.py` y `tests/test_interprete_codificador.py`.
- [ ] T7 Comprobación en la web real, tras reiniciarla: una pregunta por un skill, por una ruta de la API y por un fichero rechazado.
      Hecho cuando: las tres respuestas se ven en el navegador con su cita o su rechazo.

T6, 2026-11-03: medido una vez sobre el conjunto sellado (`docs/EVALUACION_ABSTENCION_077.json`, 15 673 vectores, 78 con respuesta y 50 sin ella). Reranker con puerta: MRR@10 0,316, recall@10 0,406, abstención 0,98, 33 de 78 preguntas con respuesta abstenidas. `cumple_todos` es falso: el índice ampliado no se sirve y sigue el de la 047. Se mide, no se ajusta.

T7, 2026-11-06: sigue abierta. En la web real (espacio de prueba `1985f689071b42ee`) las tres preguntas no llegan a
`pregunta` y no hay cita ni rechazo que ver: «¿cómo se prueba la web según .claude/skills/convertersmartgrid-frontend/SKILL.md?»
sale sin tarea (simular_calibracion 2 %), «¿cómo se usa la ruta POST /api/workspaces/{wid}/agente/proyecto/lista de la API?»
sin tarea (pregunta 45 %, Ollama sin respuesta válida) y «¿qué hay en el fichero ../../Windows/win.ini?» sin tarea (episodios
32 %). El Transformer provisional `prov-8fd8a405a322c80c` no reconoce como pregunta una que nombra un fichero o una ruta, y
RF-26 y RF-27 solo actúan dentro de `pregunta`; la pregunta de control «¿cómo se calibra una barra sin medidor?» sí responde
con cita. El arreglo toca el intérprete, fuera del alcance de esta spec. Capturas en `output/evidencia_web_067_077/077_T7_*.png`.
