# Spec 067 — Asistente operativo: revisión, planes, modelos y tareas que funcionan desde la web

Estado: implementada

Rama de trabajo: `asistente/nucleo`.
Cita: 026 (asistente), 027 (agente en producción), 043 (gobierno de modelos), 047 (revisión por
roles), 061 (observación), 065 (permisos del equipo).

## Por qué

El usuario, el 2026-11-02: «corrige todo lo que falta, está parcial, no opera del asistente; déjalo
listo y operativo con todos sus módulos implementados». Una auditoría del código encontró que las
piezas existían pero no estaban unidas al camino real del operador:

- la revisión por roles salía siempre bloqueada desde el botón, porque nadie custodiaba como evidencia
  los informes reales del espacio (la prueba existente los registraba a mano y no lo destapaba);
- sin GPU, el Transformer de órdenes cedía a Ollama sin decirlo;
- los planes pendientes vivían en memoria y un reinicio de la web los perdía;
- «Reentrenar» registraba un candidato y no ponía nada en uso, y además la puerta de comparación con el
  modelo activo recibía siempre «sin referencia», de modo que ningún candidato podía pasar nunca;
- ninguna tarea lanzaba la escalera de obras ni la optimización de «Con proyecto»;
- el proyecto entero confirmaba todas sus etapas con un clic, sin enseñarlas, mientras el inventario
  decía que cada herramienta tenía confirmación obligatoria.

## Requisitos

### Evidencia y revisión por roles

- RF-1: CUANDO termine bien un trabajo de informe, estudio, PIDE, verificación del «Caso base», obras
  o transferencia, EL SISTEMA custodiará su resultado como evidencia del espacio.
- RF-2: EL SISTEMA guardará en cada evidencia el proyecto que nombra el resultado del trabajo.
- RF-3: EL SISTEMA guardará en cada evidencia la huella de la fuente con la que se vinculó ese proyecto
  o, sin vínculo, la de la fuente cargada en el espacio.
- RF-4: SI el resultado no nombra un proyecto o no hay huella de fuente, ENTONCES EL SISTEMA no
  custodiará ese trabajo y lo dirá en el Registro.
- RF-5: CUANDO el operador pida la revisión de un plan, EL SISTEMA usará las evidencias custodiadas del
  mismo proyecto y la misma fuente, sin ningún registro manual.
- RF-6: SI no hay evidencia del proyecto y la fuente del plan, ENTONCES EL SISTEMA dirá en el motivo de
  la revisión qué proyecto y qué fuente buscó.
- RF-7: CUANDO el operador abra el equipo del asistente, EL SISTEMA mostrará las evidencias custodiadas
  del espacio.

### Modelo que responde

- RF-8: SI el Transformer de órdenes no se puede cargar, ENTONCES EL SISTEMA seguirá interpretando la
  orden con el modelo local de Ollama.
- RF-9: SI el Transformer de órdenes no se puede cargar, ENTONCES EL SISTEMA dirá en el plan el motivo.
- RF-10: SI el Transformer de órdenes no se puede cargar, ENTONCES EL SISTEMA dirá en el plan qué modelo
  respondió, o que no respondió ninguno.
- RF-11: CUANDO un plan traiga un aviso del modelo que respondió, LA PANTALLA lo mostrará como aviso.

### Planes que sobreviven a un reinicio

- RF-12: CUANDO se proponga un plan que escribe, EL SISTEMA lo guardará por espacio con escritura atómica.
- RF-13: CUANDO la web se reinicie, EL SISTEMA seguirá ofreciendo el plan guardado pidiendo confirmación.
- RF-14: EL SISTEMA no reanudará por sí solo ninguna escritura tras un reinicio.
- RF-15: SI el proyecto, la fuente o un fichero de entrada de un plan guardado cambiaron, ENTONCES EL
  SISTEMA rechazará su confirmación y dirá que hay que proponer otro.
- RF-16: SI un plan estaba en ejecución cuando se cortó la web, ENTONCES EL SISTEMA lo ofrecerá como
  interrumpido, sin confirmación vigente.
- RF-17: CUANDO una escritura termine bien, EL SISTEMA retirará su plan guardado.
- RF-18: SI se confirma de nuevo un plan ya ejecutado, ENTONCES EL SISTEMA lo rechazará.
- RF-19: CUANDO el operador abra la consola, LA PANTALLA mostrará los planes guardados del espacio.

### Modelos en uso gobernados por el registro

- RF-20: CUANDO el reentrenamiento termine con un candidato que el registro aprobó por sus puertas, EL
  SISTEMA lo pondrá en uso cambiando un único puntero de forma atómica.
- RF-21: EL SISTEMA verificará las huellas de los artefactos del candidato antes de ponerlo en uso.
- RF-22: CUANDO un candidato pase a uso, EL SISTEMA conservará el modelo anterior.
- RF-23: CUANDO el operador vuelva al modelo anterior, EL SISTEMA dejará de acuerdo el puntero y el registro.
- RF-24: SI el candidato queda rechazado, bloqueado por datos o con error de entorno, ENTONCES EL SISTEMA
  mantendrá el modelo en uso.
- RF-25: EL SISTEMA medirá el modelo en uso sobre la misma prueba sellada del candidato para la puerta de
  comparación, sin relajar ninguna puerta ni umbral.
- RF-26: CUANDO se reentrene el asistente, EL SISTEMA someterá el clasificador de informes a la misma vía
  de registro y puesta en uso.
- RF-27: SI no hay informes reales en la prueba del clasificador, ENTONCES EL SISTEMA registrará
  BLOQUEADO_POR_DATOS sin entrenarlo.
- RF-28: EL SISTEMA dirá en la descripción de la tarea de reentrenar que el clasificador solo se entrena
  con informes reales.
- RF-29: EL SISTEMA dirá en el estado de los modelos qué versión está en uso.

### Tareas que faltaban

- RF-30: EL SISTEMA ofrecerá una tarea que lance la escalera de obras por su ruta de la web.
- RF-31: EL SISTEMA ofrecerá una tarea que lance la optimización de «Con proyecto» por su ruta de la web.
- RF-32: EL SISTEMA tratará esas dos tareas como escrituras con confirmación y contexto sellado.
- RF-33: EL SISTEMA declarará esas dos tareas y el informe de factibilidad en el carril de DIgSILENT.
- RF-34: CUANDO se pida un informe de factibilidad de una carga que no existe, EL SISTEMA lo dirá en el plan
  antes de ofrecer confirmarlo.
- RF-35: EL SISTEMA tendrá ejemplos de esas dos tareas en los conjuntos de intenciones, sin tocar los pesos.
- RF-36: SI el Transformer en uso no conoce una tarea del catálogo y la orden, sin ser una pregunta, nombra
  su frase literal, ENTONCES EL SISTEMA interpretará esa tarea por el catálogo.

### Proyecto entero

- RF-37: CUANDO el operador pida el proyecto entero, EL SISTEMA le enseñará antes la lista de etapas con las
  que escriben, las ya hechas y las que se omitirán.
- RF-38: SI la orden del proyecto entero no trae la confirmación de la lista mostrada, ENTONCES EL SISTEMA la
  rechazará sin encolar nada.
- RF-39: SI la fuente, los datos o las etapas cambiaron desde que se mostró la lista, ENTONCES EL SISTEMA
  rechazará la confirmación.
- RF-40: EL SISTEMA dirá en el inventario del equipo que el proyecto entero se confirma con una lista única,
  no etapa por etapa.

## Fuera de alcance

- Índice y recuperación RAG (`asistente/indice.py`), `digital_twin/temporal*` y la optimización PNL de la
  spec 048: la tarea de PNL se añadirá cuando exista su ruta.
- Relajar puertas o umbrales. Con pocas órdenes humanas un candidato solo pasa si cumple todas sus puertas;
  decidir si la muestra humana debe ser mayor es de la spec 047 (RF-13), no de esta.
- El camino antiguo por CLI `tools/asistente_entrenar.py` sin `--integral`, que sigue promoviendo con sus
  puertas propias y no se llama desde la web.
- Entrenar de verdad y ejecutar en DIgSILENT dentro de esta rama: quedan como tareas abiertas.
