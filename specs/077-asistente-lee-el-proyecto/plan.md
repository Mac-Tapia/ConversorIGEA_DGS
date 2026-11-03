# Plan — Spec 077

- `src/convertersmartgrid/asistente/lectura_proyecto.py`: la política de rutas, las tres lecturas y su catálogo; un solo sitio para la web y el MCP. (RF-16 a RF-25, RF-27, RF-29)
- `src/convertersmartgrid/asistente/corpus_proyecto.py`: ficheros del corpus ampliado, troceado, vigencia, estado de cada spec, caché por fichero y medida de tamaño. (RF-1 a RF-7, RF-11, RF-12, RF-14, RF-15)
- `src/convertersmartgrid/asistente/indice.py`: el corpus como parámetro; `Fragmento` con vigencia y estado de spec; presentación de lo histórico y de lo no cumplido; las lecturas como citas. El corpus de la 047 sigue siendo el valor por defecto, con el mismo texto. (RF-6, RF-8 a RF-10, RF-13, RF-26, RF-28, RF-31, RF-32)
- `src/convertersmartgrid/asistente/equipo.py`: `LecturaGobernada`, y su apartado en `inventario_equipo`. (RF-33 a RF-35)
- `src/convertersmartgrid/asistente/ollama.py`: `pedir_lecturas`, con el catálogo como esquema, y lo leído como datos. (RF-28, RF-30)
- `src/convertersmartgrid/asistente/reranker.py`: `corpus_vigente`, los umbrales y la política de la medición del corpus ampliado. (RF-47, RF-48)
- `src/convertersmartgrid/asistente/evaluacion_rag.py`: anclas por contenido en varias fuentes y formación de los conjuntos nuevos. (RF-43, RF-44, RF-49)
- `src/convertersmartgrid/web/services.py`: `asistente_pregunta` elige corpus y gobierna las lecturas. (RF-26, RF-47)
- `tools/mcp_conversor.py`: el servidor MCP por stdio, sin lógica propia. (RF-37 a RF-40)
- `tools/asistente_indice_ampliado.py`: medir tamaños, BM25 con el reparto `corpus` y formar los conjuntos. (RF-14, RF-44, RF-50)
- `tools/asistente_evaluar_rag.py`: `--corpus 077` en sus tres modos. (RF-46, RF-49)
- `tools/generar_contrato_api.py`: escribe también `docs/asistente/openapi.json`. (RF-5)
- `docs/MCP_CONVERSOR.md`: cómo conectar el MCP. (RF-41)
- `docs/CONJUNTO_FUERA_077.json`, `docs/CONJUNTO_ABSTENCION_CALIBRACION_077.json`, `docs/CONJUNTO_ABSTENCION_SELLADO_077.json`: los conjuntos nuevos. (RF-43 a RF-45)
- `tests/test_asistente_lectura_proyecto.py`, `tests/test_asistente_corpus_ampliado.py`, `tests/test_mcp_conversor.py`.

Decisiones:

- **Hasta pasar la puerta, la web sirve el corpus de la 047.** Alternativas descartadas: seguir con los umbrales de la 047 sobre el índice mayor, que daría una abstención sin medir, y dejar la abstención sin calibrar, que dejaría al asistente en «No lo sé» a todo hasta el turno de GPU. Las lecturas por nombre sí funcionan desde el primer momento, porque su evidencia es el propio fichero.
- **`pregunta` no se reparte en tareas nuevas.** Añadir tareas al catálogo rompería `prueba_sellada.filas` y dejaría al Transformer sin esas salidas; las lecturas son pasos internos de `pregunta`.
- **Búsqueda literal, sin expresiones regulares.** Una expresión pedida por el modelo puede colgar el carril; Python no tiene tiempo máximo para `re`.
- **`consultar_api` lee `docs/asistente/openapi.json`.** Lo escribe `tools/generar_contrato_api.py` y una prueba lo compara con `create_app().openapi()`. Alternativa descartada: importar la web desde `asistente/`, que invierte las capas y carga FastAPI en un MCP que no lo necesita.
- **Los informes de `docs/` con fecha en el nombre son históricos.** Son fotos de un día; `CLAUDE.md` solo nombra algunos, y presentar una foto vieja como vigente es el error que la spec quiere evitar.
- **El cuerpo de Python no se indexa.** Multiplicaría los trozos y la memoria de un equipo de 16 GB; la búsqueda literal ya lo alcanza. Por eso las filas de la 076 cuya única fuente es un cuerpo de función quedan fuera de los conjuntos nuevos, y se cuentan.
- **El MCP no escribe nada en disco.** Su bitácora va a stderr, para que «solo lectura» sea literal; la web anota en `equipo_acciones` porque ya es su registro.
- **Vectores por corpus, en carpetas separadas.** `calcular_vectores` de uno no borra los del otro; los del corpus de la 047 siembran los del ampliado, porque el texto de esos trozos es el mismo.

- **Dos políticas, y la abierta la decide el servidor.** `Politica` no es un argumento del catálogo: ni el modelo ni un cliente pueden pedirla. Por defecto, la restringida. La web abre la local tras `ollama.destino_llm`; el MCP, solo con `--datos-locales`. El índice siempre usa la restringida. Alternativa descartada: una sola lista amplia, porque un cliente MCP puede estar en la nube. (RF-51, RF-57, RF-61, RF-66)
- **`cliente_configurado` no lee ninguna dirección:** siempre usa `127.0.0.1`, y `ClienteOllama` rechaza otro servidor. `destino_llm` mira además si `ollama.json` declara otra dirección, porque alguien la quiso así, y si el modelo es de los `-cloud` de Ollama, que se sirven en local y se ejecutan fuera. Alternativa descartada: fiarse del anfitrión. (RF-57, RF-58)
- **Lo leído bloquea por palabras con mayúscula o cifra.** Sobra bloqueo si un dato trae «Flujo», pero P9 falla por el lado seguro; bloquear también las minúsculas dejaría la búsqueda sin uso. (RF-59)
- **`ordenes_fijas.py` y `prueba_sellada.py` quedan vedados** porque sus frases deciden una puerta de las órdenes, y `docs/asistente/*` salvo el OpenAPI porque mezcla los dos repartos de la 076. (RF-54)

Pruebas: rutas con `..`, enlaces, uniones, mayúsculas y nombres de NTFS, en un repositorio sintético; el MCP con un servidor real por stdio si el paquete está, y sin él; un doble de Ollama para las lecturas pedidas por el LLM. Sin datos reales.

Lo que no se comprueba aquí: la medición con vectores y reranker, que pide turno de GPU, y la respuesta en la web real.
