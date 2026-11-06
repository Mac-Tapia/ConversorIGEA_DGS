# Spec 077 — El asistente lee skills, documentos, código y API del proyecto, y un MCP local de solo lectura

Estado: aprobada · Fecha: 2026-11-02 · Origen: petición del usuario

## Contexto y objetivo

El usuario, el 2026-11-02: «el LLM debe aprender a leer los skill, mcp, md del proyecto conversor, los archivos del proyecto,
las apis». Hoy el índice del asistente solo trae `CODIGO_FUENTE.md`, el manual de órdenes, la constitución, los RF de las specs
y los docstrings de `src/` y `tools/`; lo demás no lo ve, y el proyecto no tiene ningún servidor MCP.

Esta spec amplía lo que se puede consultar y da al LLM tres lecturas gobernadas, sin escritura, también por MCP local. Sin GPU
ni DIgSILENT en esta fase, y sin entrenar nada. Un índice mayor cambia las puntuaciones, de modo que invalida las cifras medidas
en `docs/EVALUACION_*_047.json`: esas cifras no se tocan y no se afirma que sigan valiendo, y el índice ampliado no se sirve hasta
que pase la misma puerta con conjuntos nuevos.

## Usuarios / actores

El operador que pregunta en la web, el LLM local que redacta, los revisores de la 047, un cliente MCP local y quien mida con su
turno de GPU.

## Requisitos funcionales (EARS)

### Índice ampliado

- RF-1: EL SISTEMA tendrá un corpus ampliado con las fuentes del corpus de la 047, `.claude/skills/*/SKILL.md`, `docs/*.md`, `README*`, `VNR-GIS.md` y `CLAUDE.md`.
- RF-2: EL SISTEMA indexará en el corpus ampliado el `plan.md` y el `tasks.md` de cada spec.
- RF-3: EL SISTEMA indexará en el corpus ampliado `docs/procedimientos/*.md`, cuyas citas se comprueban contra su línea.
- RF-4: EL SISTEMA indexará en el corpus ampliado las fuentes de `frontend/src`, salvo el esquema generado.
- RF-5: EL SISTEMA indexará cada ruta y método de la API desde un OpenAPI generado sin arrancar el servidor.
- RF-6: EL SISTEMA guardará en cada fragmento su vigencia, que será `vigente` o `historico`.
- RF-7: EL SISTEMA tendrá por históricos `docs/superpowers/`, `docs/DIAGNOSTICO_*`, los informes de `docs/` con fecha en el nombre y las specs retiradas.
- RF-8: CUANDO se cite un fragmento histórico, EL SISTEMA lo presentará con la marca «histórico, no vigente» en la cita y en la respuesta.
- RF-9: EL SISTEMA ordenará los fragmentos vigentes por delante de los históricos entre los hallados.
- RF-10: CUANDO se cite un fragmento de una spec no cumplida, EL SISTEMA presentará el estado de esa spec en la cita y en la respuesta.
- RF-11: EL SISTEMA partirá cada fichero de texto del corpus ampliado en trozos de un largo máximo declarado, sin perder ninguna línea con contenido.
- RF-12: CUANDO cambie un fichero del corpus ampliado, EL SISTEMA volverá a trocear solo ese fichero.
- RF-13: EL SISTEMA reutilizará el vector de cada trozo cuyo texto no cambió, también los del corpus de la 047.
- RF-14: EL SISTEMA medirá con una herramienta sin GPU el tamaño de cada corpus: trozos, caracteres, bytes de vectores previstos y memoria.
- RF-15: EL SISTEMA no indexará ningún fichero que la lista negra rechace.

### Lecturas para el LLM

- RF-16: EL SISTEMA leerá un fichero permitido por rango de líneas, con un tope de líneas declarado por lectura.
- RF-17: EL SISTEMA buscará un texto literal en los ficheros permitidos, con un tope de resultados declarado.
- RF-18: EL SISTEMA consultará una ruta de la API en el OpenAPI generado, sin hacer ninguna petición HTTP.
- RF-19: EL SISTEMA leerá solo lo que figure en una lista blanca explícita de rutas y extensiones.
- RF-20: EL SISTEMA rechazará por lista negra `output/`, `input/`, `config/perfil_empresa.json`, `config/perfiles/`, `.env`, credenciales, `.agents/`, datos de la distribuidora, `maestro_real/` y los conjuntos y resultados sellados.
- RF-21: SI una ruta sale del repositorio con `..`, es absoluta o nombra otra unidad, ENTONCES EL SISTEMA la rechazará.
- RF-22: SI un enlace o una unión lleva fuera de la lista blanca, ENTONCES EL SISTEMA lo rechazará.
- RF-23: EL SISTEMA aplicará las listas sin distinguir mayúsculas de minúsculas.
- RF-24: SI una ruta usa un flujo alternativo, un nombre corto de Windows, un punto o un espacio final, o un byte nulo, ENTONCES EL SISTEMA la rechazará.
- RF-25: EL SISTEMA no tendrá ninguna operación de escritura en el módulo de las lecturas.

### Conexión con `pregunta` y con el gobierno

- RF-26: CUANDO una pregunta nombre un fichero permitido o una ruta de la API, EL SISTEMA añadirá su lectura como cita comprobada.
- RF-27: SI una pregunta nombra una ruta de la lista negra o que sale del repositorio, ENTONCES EL SISTEMA lo dirá sin devolver nada de su contenido.
- RF-28: CUANDO el índice ya tenga respuesta, EL SISTEMA dejará al LLM pedir un número máximo declarado de lecturas del catálogo.
- RF-29: SI el LLM pide una lectura fuera del catálogo o rechazada, ENTONCES EL SISTEMA la descartará y seguirá sin ella.
- RF-30: EL SISTEMA pasará al LLM lo leído como datos y nunca como instrucciones.
- RF-31: EL SISTEMA comprobará con `citas_que_no_apoyan` toda respuesta redactada con lecturas, igual que las demás.
- RF-32: EL SISTEMA mantendrá la abstención de la 047: una lectura pedida por el LLM nunca convierte un «No lo sé» en una respuesta.
- RF-33: EL SISTEMA ejecutará cada lectura por el gobierno del equipo, que la rechazará si el rol no está entre los de lectura.
- RF-34: EL SISTEMA anotará en la bitácora de la web cada lectura con su rol, herramienta, argumentos y huella de la salida, sin el contenido leído.
- RF-35: EL SISTEMA declarará en el inventario del equipo las lecturas, sus roles y que ningún modelo concede permisos.
- RF-36: EL SISTEMA no añadirá ninguna tarea al catálogo de órdenes.

### Servidor MCP local

- RF-37: EL SISTEMA servirá por MCP, solo por stdio, las mismas tres lecturas con la misma lógica y el mismo gobierno.
- RF-38: EL SISTEMA marcará cada herramienta MCP como de solo lectura y no expondrá ninguna otra.
- RF-39: SI falta el paquete `mcp`, ENTONCES `tools/mcp_conversor.py` lo dirá y terminará con un código propio, sin afectar a su `--help`.
- RF-40: EL SISTEMA no importará el paquete `mcp` desde la web ni desde `src/`.
- RF-41: EL SISTEMA documentará cómo conectar el servidor MCP.

### Medición y puerta

- RF-42: EL SISTEMA mantendrá en 0,90 la abstención mínima de la puerta.
- RF-43: EL SISTEMA tendrá conjuntos nuevos de calibración y de medida sellada del corpus ampliado, sin ninguna pregunta de los conjuntos de la 047.
- RF-44: EL SISTEMA formará la calibración con el reparto `corpus` de la 076 y la medida sellada con su reparto `sellado`, más preguntas nuevas ajenas al proyecto en cada uno.
- RF-45: EL SISTEMA fijará en una prueba la huella de los conjuntos nuevos.
- RF-46: EL SISTEMA medirá el conjunto sellado nuevo una sola vez.
- RF-47: MIENTRAS no exista una medición del corpus ampliado que pase la puerta, EL SISTEMA servirá en la web el corpus y los umbrales de la 047.
- RF-48: CUANDO una medición del corpus ampliado cumpla la regla aceptada en la 047 el 2026-11-02, con el reranker en la puerta completa y el híbrido y BM25 en la abstención mínima, EL SISTEMA servirá en la web ese corpus con sus umbrales.
- RF-49: SI una fila de los conjuntos nuevos pierde todas sus anclas y son más de un 5 % del conjunto, ENTONCES EL SISTEMA no medirá.
- RF-50: EL SISTEMA medirá sin GPU la recuperación BM25 con el reparto `corpus` de la 076, sin abrir el reparto `sellado`.

### Lectura de lo local con un LLM local (corrección del usuario, 2026-11-02)

El usuario: «no debería proteger, se supone que se está especializando para operar en local al LLM» y «el LLM debe leer todos
los archivos del proyecto, incluso del local». Lo de abajo cambia para el LLM local lo que RF-19 y RF-20 cerraban.

- Aclaración de RF-19: la lista blanca solo vale para la política restringida (RF-57, RF-61); con el LLM local manda RF-51.
- Aclaración de RF-20: la lista negra entera solo vale para la política restringida; con el LLM local quedan RF-53, RF-54 y RF-55.
- Aclaración de RF-25: esto es lectura; las escrituras siguen por plan y confirmación del operador, sin ningún camino nuevo.
- RF-51: MIENTRAS el LLM sea local, EL SISTEMA leerá en la web cualquier fichero del árbol del proyecto, también los ignorados por git.
- RF-52: MIENTRAS el LLM sea local, EL SISTEMA leerá también las raíces de `CSG_LLM_RAICES`, `CSG_DEMANDA_DIR` y `raices_llm` del perfil local, sin ninguna ruta fija en el código.
- RF-53: EL SISTEMA no leerá con ninguna política credenciales ni secretos, porque sirven para entrar en otro sitio, no explican el proyecto y una vez leídos pueden acabar citados.
- RF-54: EL SISTEMA no leerá con ninguna política los conjuntos sellados ni sus resultados, porque deciden una puerta y un modelo que los lee deja de medirse a ciegas.
- RF-55: EL SISTEMA no leerá con ninguna política `ejemplos.jsonl` ni `etiquetas*.jsonl`, porque las órdenes confirmadas son la prueba humana y las etiquetas guardan su parte reservada.
- RF-56: EL SISTEMA no indexará ni recorrerá en una búsqueda `.git`, `.venv`, `node_modules`, `.worktrees` ni las cachés, que se leerán solo si se nombran.
- RF-57: SI la configuración de Ollama apunta a un servidor que no sea de esta máquina o elige un modelo en la nube, ENTONCES EL SISTEMA aplicará la política restringida y lo avisará en la respuesta.
- RF-58: SI la configuración de Ollama no se puede leer, ENTONCES EL SISTEMA aplicará la política restringida y lo avisará en la respuesta.
- RF-59: CUANDO se haya leído un dato local, EL SISTEMA bloqueará en la búsqueda en internet su ruta, sus códigos y sus nombres propios.
- RF-60: EL SISTEMA no tendrá ningún camino por el que una lectura llame a internet o a un servicio externo.
- RF-61: EL SISTEMA servirá el MCP con la política restringida por defecto, porque su cliente puede estar en la nube.
- RF-62: DONDE se arranque el MCP con `--datos-locales`, EL SISTEMA le abrirá lo mismo que al LLM local, salvo RF-53, RF-54 y RF-55.
- RF-63: CUANDO se lea un libro de Excel, EL SISTEMA usará el lector del proyecto, con una fila por línea y sus hojas.
- RF-64: CUANDO se lea un PDF, EL SISTEMA usará el lector del proyecto.
- RF-65: CUANDO se pida una base de Access u otro binario, EL SISTEMA dirá qué ruta usar y no devolverá sus bytes.
- RF-66: EL SISTEMA no indexará los datos locales, que se leerán bajo demanda.
- RF-67: EL SISTEMA cortará toda búsqueda en un tope declarado de tiempo y de resultados, y dirá que cortó.
- RF-68: EL SISTEMA leerá un rango de un fichero grande sin cargarlo entero en memoria.

### Una pregunta que nombra un fichero o una ruta de la API llega a `pregunta` (prueba en la web, 2026-11-06)

En la web real (077 T7) tres preguntas no llegaron a `pregunta`, y RF-26 y RF-27 solo actúan dentro de ella: «¿cómo se prueba
la web según .claude/skills/convertersmartgrid-frontend/SKILL.md?» salió como `simular_calibracion` al 2 %, «¿cómo se usa la
ruta POST /api/workspaces/{wid}/agente/proyecto/lista de la API?» quedó en `pregunta` al 45 %, bajo el umbral, sin respuesta
válida de Ollama, y «¿qué hay en el fichero ../../Windows/win.ini?» salió como `episodios` al 32 %, cuando debía rechazarse
dentro de `pregunta`. La pregunta de control «¿cómo se calibra una barra sin medidor?» sí llegó al 97 %. Es una regla de forma,
no un ajuste del modelo: no se entrena nada.

- RF-69: CUANDO una orden tenga forma de pregunta y nombre un fichero del árbol o una ruta de la API, EL SISTEMA la llevará a la tarea `pregunta` antes de consultar al Transformer y a Ollama, sea cual sea su confianza.
- RF-70: EL SISTEMA dará a una orden forma de pregunta si empieza por una palabra interrogativa, con o sin «¿», o si lleva «¿» o «?» y empieza por un verbo de consulta («hay», «existe», «es», «sirve», «tiene», «se»), nunca por una petición de acción.
- RF-71: EL SISTEMA tendrá por nombrado un fichero cuando la orden traiga una ruta con «/» o «\» que acabe en extensión, un `SKILL.md` o un `../` (también `..\`), y una ruta de la API cuando traiga `/api/…`, con o sin verbo HTTP.
- RF-72: SI la orden coincide con una frase literal de una tarea que se reconoce también como pregunta, ENTONCES EL SISTEMA no aplicará RF-69.
- RF-73: EL SISTEMA no aplicará RF-69 a una orden sin forma de pregunta ni a una pregunta que no nombre un fichero ni una ruta de la API.
- RF-74: CUANDO RF-69 decida la tarea, EL SISTEMA lo dirá en lo consultado y en el razonamiento del plan, y no marcará ningún trozo como `texto` (069:RF-30).

## Requisitos no funcionales

- Python 3.12; la dependencia `mcp` es opcional y queda fuera de `requirements.txt`.
- Sin GPU ni DIgSILENT; ninguna petición de red; memoria medida y comunicada con el dato real.
- Sin datos ni nombres reales en las pruebas, ni texto de `maestro_real/`.

## Fuera de alcance

- Entrenar o ajustar ningún modelo, y bajar la puerta de abstención.
- Cambiar `interprete.py`, `codificador_ordenes.py`, `validacion_cruzada.py`, `valle.py`, `escalera_optima.py` o `digital_twin/`.
  Aclaración del 2026-11-06: `interprete.py` cambia solo por la regla de forma de RF-69 a RF-74; ningún modelo, umbral ni
  conjunto de entrenamiento cambia por ella.
- Tocar `docs/EVALUACION_*_047.json`, sus conjuntos o sus umbrales.
- Duplicar `consultar_datos`: lo que ya responde esa orden se sigue pidiendo por ella.
- MCP por HTTP, recursos o herramientas de escritura.
- Indexar el cuerpo del código Python, que se consulta con la búsqueda literal.
- Pantallas nuevas en la web.

## Criterios de aceptación

- Con el índice ampliado se responde con cita a una pregunta de un skill, de un procedimiento y de una ruta de la API.
- Una ruta rechazada no devuelve contenido por ninguna de las tres herramientas ni por MCP.
- Sin medición aprobada, la web responde con el corpus de la 047 y lo prueba una prueba.
