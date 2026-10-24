# Plan — Spec 026, asistente de órdenes

Lee: `docs/constitution.md` y `specs/026-asistente-ordenes/spec.md`.

## Contexto técnico

- Paquete nuevo `src/igea_dgs/asistente/`, sin importar PowerFactory. PyTorch (extra `ml`) para
  el Transformer y el clasificador, en la GPU como la PINN (024); Ollama por su API local
  (`http://127.0.0.1:11434`) con `urllib` de la biblioteca estándar, sin dependencias nuevas.
- La ejecución pasa por las funciones de `web/services.py` que ya lanzan las pestañas
  (`convert`, `run_system`, `cargas_ejecutar`, `ajuste_ejecutar`, `obras_ejecutar`,
  `estudios_ejecutar`, `transferencia_ejecutar`, `pide_ejecutar`, `gemelo_aprender`,
  `gemelo_entrenar`, `gemelo_temporal`, `informe_estudio`, `informe_factibilidad`…) y por
  `JobManager.submit` con su carril (P5, P7). El asistente no llama a DIgSILENT por su cuenta.
- Datos locales en `data_root() / '_asistente'` (`IGEA_ASISTENTE_DATA` para las pruebas):
  ejemplos, modelos, índice del proyecto, registro de decisiones y de consultas a internet.

## Diseño por partes

| Parte | Ficheros | Cubre |
| --- | --- | --- |
| A. Catálogo de tareas | `asistente/tareas.py`: cada tarea con su función de `services`, sus datos (obligatorios y opcionales, con tipo), si escribe, su carril y su descripción para Ollama | RF-8 a RF-11 |
| B. Ejemplos sintéticos | `asistente/sinteticos.py`: frases por plantilla y paráfrasis para cada tarea, con nombres reales de proyectos, alimentadores, sistemas y periodos del espacio; etiquetas de tarea y de cada dato (BIO) | RF-21 |
| C. Transformer | `asistente/transformer.py`: tokenizador de subpalabras propio (BPE entrenado con los ejemplos), codificador Transformer pequeño (4 capas, 4 cabezas, 128 dims) con dos salidas: tarea y etiquetas BIO de los datos; registro, puertas y promoción como 024 | RF-2, RF-19, RF-20 |
| D. Ollama | `asistente/ollama.py`: cliente local con la lista de tareas como herramientas (JSON), tiempo máximo de 30 s y comprobación de que la URL es local | RF-3, RF-5 |
| E. Intérprete y plan | `asistente/interprete.py`: Transformer → si duda, Ollama → si duda, pregunta; `asistente/plan.py`: datos contrastados con lo que existe (proyectos, alimentadores, estructura, libros), plan con razonamiento y procedencia de cada dato | RF-2 a RF-7 |
| F. Informes | `asistente/clasificador.py`: clasificador de dos niveles (informe y subtipo) sobre el mismo codificador, con los subtipos del perfil (`asistente.subtipos_estudio`); aprende de los informes generados y de las correcciones | RF-13 a RF-16 |
| G. Índice del proyecto | `asistente/indice.py`: trozos de `CODIGO_FUENTE.md`, specs (cada RF), docstrings (por `ast`), manual y constitución; embeddings de Ollama (`nomic-embed-text`) o, sin ellos, BM25; reconstrucción por huella de los ficheros; respuesta con cita o «no lo sé» | RF-17, RF-18 |
| H. Vigilancia | `asistente/vigilancia.py`: cada minuto, trabajos (fallos, tiempos frente a su historia, colas paradas, reintento del 4002) y modelos (entrenar si toca, de 024); calidad de los resultados; suite y spec 009 cada noche en otro proceso | RF-22 a RF-25 |
| I. Mejoras | `asistente/mejoras.py`: rama en un `git worktree` aparte, cambio de spec y pruebas, suite completa en la rama; nunca `merge` ni `push`; registro de propuestas y decisiones | RF-26 a RF-28 |
| J. Internet | `asistente/internet.py`: búsqueda en la API de GitHub, PyPI y arXiv; filtro que bloquea identificadores de la red (los del espacio, la estructura y el búfer) y rutas; registro de cada consulta; propuestas de librería por la parte I | RF-29 a RF-32 |
| K. Web | `web/app.py`: `POST /api/workspaces/{wid}/asistente/orden`, `.../confirmar`, `.../corregir`, `GET .../avisos`, `.../registro`; `web/services.py`: `asistente_*`; `frontend/src/components/Asistente.tsx` (consola, plan con su razonamiento, confirmar o corregir, avisos) | RF-1, RF-7, RF-8, RF-12, RF-15 |
| L. Herramientas | `tools/asistente_entrenar.py` (Transformer y clasificador, en otro proceso como la PINN), `tools/asistente_medir_ollama.py` (qwen2.5:3b frente a llama3.1:8b con las mismas órdenes) | RF-3, RF-20 |

## Decisiones

- Transformer propio pequeño y no `transformers` de Hugging Face con un modelo preentrenado: no
  añade dependencias ni descargas, se entrena en minutos en la GPU y aprende el vocabulario del
  conversor (alimentadores, SET, casos). Ollama cubre lo que el propio no entiende.
- Los datos de la orden se reconocen con etiquetas BIO y después se contrastan con lo que existe
  (RF-6): un alimentador que el modelo «ve» pero que no está en la fuente no llega al plan.
- Toda tarea que escribe pasa por la confirmación (RF-8), también si la propone la vigilancia.
- El índice es local y se reconstruye por huella: sin un modelo de embeddings, BM25 (sin
  dependencias) para que funcione sin descargar nada.
- Las mejoras van en `git worktree` y no en la copia de trabajo: hay otras sesiones trabajando en
  el repositorio (2026-10-24) y una rama del agente no puede mezclarse con su trabajo.
- Internet con la biblioteca estándar y la API pública de GitHub sin token: sin credenciales que
  guardar. El filtro de identificadores bloquea antes de enviar, no después.

## Comprobación contra la constitución

- P5 y P7: el asistente encola los mismos trabajos; no hay vía propia hacia el motor ni DIgSILENT.
- P9: Ollama y los modelos son locales; el cliente rechaza una URL que no sea local; internet
  solo con consultas filtradas y registradas.
- P13: ningún nombre fijo; los vocabularios salen del espacio, la estructura y el perfil.
- P12: cada RF con su prueba citándolo; ficheros nuevos en `CODIGO_FUENTE.md` (009).

## Estrategia de pruebas

- Unitarias puras de A, B, E, G, J; Transformer y clasificador entrenados con ejemplos sintéticos
  sorteados (semilla) y evaluados en frases que no vieron; Ollama con un servidor local falso.
- Web con el cliente de pruebas de FastAPI: orden de lectura directa, orden que escribe con
  confirmación, corrección guardada como ejemplo.
- Mejoras en un repositorio git temporal; internet con un transporte falso que comprueba el
  filtro y el registro.
- Aceptación: una orden real de cada tarea de RF-11 desde la consola, con DIgSILENT (Pisco o
  IN111–TA225), y la medida de los dos modelos de Ollama.

## Riesgos

- La GPU de 8 GB la comparten la PINN, el Transformer y Ollama: el entrenamiento y Ollama no
  corren a la vez (turno en la vigilancia); llama3.1:8b puede no caber junto a la PINN.
- Una orden ambigua que ejecute la tarea equivocada: la mitiga la confirmación con el plan.
- El índice del proyecto envejece si no se reconstruye: se reconstruye por huella al arrancar.
