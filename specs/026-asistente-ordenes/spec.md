# Spec 026 — Asistente de órdenes en lenguaje natural que conoce, vigila y mejora el conversor

Estado: aprobada el 2026-10-24 (32 RF), con las dudas resueltas por el usuario el mismo día; T1 a T11 implementadas el mismo día, los 32 RF citados por pruebas en verde; T12 (aceptación en DIgSILENT de las tareas que lo usan) pendiente · Fecha: 2026-10-24

## Contexto y objetivo

Usuario, 2026-10-24: «implementa el transformer y PNL para que las consultas se hagan desde la
web a través de prompt, para que hagas la tarea y las entregas del conversor a través del modelo
inteligente o agente que estamos entrenando»; «el modelo también debe hacer ambos informes y
aprender a clasificarlos a qué tipo de estudio corresponde»; «el modelo en conjunto debe saber
todas las funciones, módulos y flujos de trabajo del proyecto, debe ser capaz de monitorear y
ajustar, tomar decisiones, razonamiento y mejoras cada vez del proyecto, conectado a la web
buscando nuevas librerías, nuevos proyectos que salen en GitHub u open source, debe
autoauditarse, debe aprender cada vez más».

Hoy cada tarea del conversor (convertir, importar y calibrar un sistema, cargas, obras, PIDE,
gemelo, informes) se lanza desde su pestaña de la web, rellenando campos. El operador quiere
pedirla por escrito y que un agente local la entienda, la planifique, la ejecute con las mismas
funciones de la web, explique su razonamiento y aprenda de cada orden; y que ese agente conozca
el proyecto entero, vigile los trabajos y los modelos, y proponga mejoras del conversor sin
saltarse la revisión del operador ni sacar datos de la máquina (constitución, P9).

Decisiones del usuario del 2026-10-24: modelo híbrido (Transformer propio entrenado aquí; si
duda, un modelo local de Ollama); confirmación antes de todo lo que escribe; las mejoras de
código en una rama con su spec y sus pruebas, que el operador aprueba; internet solo con
consultas sin datos y registradas; vigila trabajos, modelos, calidad de resultados y la suite.

## Usuarios / actores

- Ingeniero de planificación desde la web (consola de órdenes).
- El agente local: el Transformer propio, el modelo de Ollama de la máquina y el índice del proyecto.
- Las funciones y trabajos de la web (`web/services.py`, `web/jobs.py`) como única vía de ejecución.
- DIgSILENT PowerFactory, por el arnés de la spec 019.
- GitHub, PyPI y repositorios de artículos, solo para buscar, sin datos.

## Historias de usuario

- H1: Como ingeniero quiero escribir «calibra el sistema Pisco con julio de 2026» y que se haga,
  tras confirmar el plan, sin buscar la pestaña ni rellenar campos.
- H2: Como ingeniero quiero pedir el informe de estudio o de factibilidad de una carga y que el
  asistente sepa qué tipo de estudio es.
- H3: Como ingeniero quiero preguntar «¿cómo calibra el conversor una barra sin medidor?» y que
  la respuesta cite los ficheros, funciones y requisitos de donde sale.
- H4: Como ingeniero quiero que el asistente me avise de un trabajo atascado, de una calibración
  fuera de tolerancia o de una prueba que se rompió, y me proponga qué hacer.
- H5: Como ingeniero quiero que el asistente me proponga mejoras del conversor y librerías nuevas
  con su evidencia, en una rama que yo reviso, y que nunca las aplique por su cuenta.

## Requisitos funcionales (EARS)

### Consola e interpretación

- RF-1: EL SISTEMA tendrá en la web una consola donde el operador escriba en español una orden
  o una pregunta.
- RF-2: CUANDO el operador envíe una orden, EL SISTEMA reconocerá con un Transformer propio,
  entrenado en la máquina, la tarea pedida y sus datos (proyecto, alimentadores, sistema o
  zonal, periodo, caso, carga nueva, ficheros de entrada).
- RF-3: SI la confianza del Transformer queda bajo el umbral del perfil, ENTONCES EL SISTEMA
  pedirá la interpretación a un modelo de lenguaje local de Ollama con la lista de tareas y sus
  datos.
- RF-4: SI ninguno de los dos alcanza la confianza mínima o falta un dato obligatorio, ENTONCES
  EL SISTEMA preguntará al operador lo que falta y no ejecutará nada.
- RF-5: EL SISTEMA no enviará el texto de las órdenes, ni datos ni resultados, a ningún servicio
  externo para interpretarlos (P9).
- RF-6: EL SISTEMA comprobará cada dato reconocido contra lo que existe (proyectos de DIgSILENT,
  alimentadores de la fuente cargada, sistemas de la estructura, periodos con libro) antes de
  proponer el plan.
- RF-7: EL SISTEMA mostrará con cada plan su razonamiento: qué entendió, qué tarea eligió, con qué
  datos, de dónde sale cada uno y qué modelo lo interpretó.

### Ejecución

- RF-8: CUANDO una orden escriba en DIgSILENT o en disco, EL SISTEMA mostrará el plan (tarea,
  proyecto, alimentadores, periodo, caso y efectos) y esperará la confirmación del operador.
- RF-9: CUANDO una orden sea de solo lectura, EL SISTEMA la ejecutará sin pedir confirmación.
- RF-10: EL SISTEMA ejecutará cada tarea con las mismas funciones y trabajos de la web (cola,
  carriles, progreso, cancelación), sin una vía propia (P5, P7).
- RF-11: EL SISTEMA atenderá convertir (alimentadores, unir y por sistema eléctrico), el sistema
  eléctrico completo (convertir, importar y calibrar), cargas nuevas, obras y estudios, el PIDE y
  sus resultados, el gemelo digital (aprender, entrenar, evaluar, temporal, episodios y modelos),
  los informes y las consultas de estado.
- RF-12: CUANDO termine una tarea, EL SISTEMA responderá en la consola con su resultado y sus
  entregables (DGS, informes, formatos), con enlace a cada uno.

### Informes y su clasificación

- RF-13: EL SISTEMA generará desde la consola el informe de estudio eléctrico y el informe de
  factibilidad de la spec 017.
- RF-14: EL SISTEMA clasificará cada pedido de informe y cada informe generado en el tipo de
  estudio al que corresponde, con un clasificador que aprende de los informes y de las
  correcciones del operador.
- RF-15: SI el operador corrige el tipo de estudio, ENTONCES EL SISTEMA guardará la corrección
  como ejemplo y la usará en el siguiente entrenamiento.
- RF-16: EL SISTEMA clasificará en dos niveles: el informe (estudio eléctrico o factibilidad) y
  su subtipo de estudio (alimentación de carga nueva, mejora de tensión, refuerzo de red,
  migración de tensión, transferencia, PIDE); la lista de subtipos irá en el perfil y podrá
  crecer sin cambiar el código.

### Conocimiento del proyecto

- RF-17: EL SISTEMA mantendrá un índice local del proyecto (`CODIGO_FUENTE.md`, las specs con sus
  RF, los docstrings de `src/` y `tools/`, el manual de órdenes y la constitución) y lo
  reconstruirá cuando cambie el código.
- RF-18: CUANDO el operador pregunte cómo funciona el conversor, EL SISTEMA responderá citando
  los ficheros, las funciones y los RF de donde sale la respuesta; sin cita, dirá que no lo sabe.

### Aprendizaje

- RF-19: EL SISTEMA guardará cada orden con su interpretación, la confirmación o corrección del
  operador y el resultado, como ejemplo de entrenamiento local.
- RF-20: CUANDO haya ejemplos nuevos, EL SISTEMA reentrenará por sí mismo el Transformer y el
  clasificador de informes, y solo los promoverá si mejoran en un conjunto de prueba fijo; el
  anterior se conserva para volver a él (como 024:RF-42).
- RF-21: EL SISTEMA generará ejemplos sintéticos de órdenes a partir de la lista de tareas y de
  los nombres reales de proyectos, alimentadores y sistemas, para que el Transformer funcione
  antes de que haya órdenes del operador.

### Vigilancia y ajuste

- RF-22: EL SISTEMA vigilará los trabajos de la web y de DIgSILENT, avisará de fallos, de tiempos
  fuera de lo habitual y de colas detenidas, y reintentará solo los fallos transitorios que ya
  tienen remedio conocido (como el 4002 de la spec 019).
- RF-23: EL SISTEMA vigilará los modelos (PINN, GRU, Transformer y clasificador): reentrenará,
  promoverá o volverá al anterior según sus puertas, y lo dirá.
- RF-24: EL SISTEMA vigilará la calidad de los resultados (calibración fuera de tolerancia, flujo
  que no converge, norma incumplida) y propondrá la corrección; aplicarla seguirá RF-8.
- RF-25: EL SISTEMA correrá la suite de pruebas y el inventario de la spec 009 con la frecuencia
  del perfil y avisará de lo que se rompa, con la prueba y el RF afectados.

### Mejora del proyecto

- RF-26: CUANDO el agente proponga una mejora del código, EL SISTEMA la preparará en una rama
  aparte con su cambio de spec y sus pruebas, y correrá la suite completa en ella.
- RF-27: EL SISTEMA nunca fusionará una rama propia: la presentará al operador con su diff, la
  spec que cambia, el razonamiento y el resultado de la suite.
- RF-28: EL SISTEMA se autoauditará: cada propuesta y cada decisión del agente quedará registrada
  con su evidencia, y el operador podrá ver qué se propuso, qué se aceptó y qué se rechazó.

### Internet

- RF-29: EL SISTEMA podrá buscar en GitHub, PyPI y repositorios de artículos librerías,
  proyectos y técnicas, con consultas que solo contengan términos técnicos.
- RF-30: SI una consulta contiene un identificador de la red (alimentador, SED, proyecto, sistema
  de la estructura) o una ruta de datos, ENTONCES EL SISTEMA la bloqueará y lo registrará.
- RF-31: EL SISTEMA registrará cada consulta a internet con su texto, destino, fecha y motivo.
- RF-32: EL SISTEMA no instalará librerías por su cuenta: propondrá cada una en una rama
  (RF-26) con su licencia, su mantenimiento y por qué mejora el conversor.

## Requisitos no funcionales

- Local: el Transformer, el clasificador, el índice y el modelo de Ollama corren en la máquina;
  nada de los datos de la distribuidora sale de ella (P9).
- Universal (P13): ningún nombre de empresa, alimentador o sistema fijo en el modelo ni en el
  código; los vocabularios salen de los datos cargados y del perfil.
- Tiempo: la interpretación con el Transformer en menos de 1 s; con Ollama, en menos de 30 s
  en la GPU de la máquina, o se pregunta al operador.
- Determinismo: el entrenamiento con la misma semilla y los mismos ejemplos da el mismo modelo.
- Compatible: sin PyTorch ni Ollama, la consola lo dice y las pestañas de la web siguen igual.
- Idioma: órdenes, respuestas, código y mensajes en español (P10).

## Casos límite

Orden ambigua («calibra todo»), alimentador que no existe, dos sistemas con nombres parecidos,
periodo sin libro de demanda, orden que mezcla dos tareas, orden mientras DIgSILENT está ocupado,
cancelación a mitad, Ollama no arrancado, GPU ocupada entrenando la PINN, informe de un tipo que
el clasificador nunca vio, consulta a internet con un nombre de alimentador, rama propia con la
suite en rojo, pregunta sobre algo que el índice no cubre.

## Fuera de alcance

Ejecutar sin confirmación algo que escribe; fusionar código o instalar librerías sin el operador;
modelos de lenguaje remotos o de terceros; voz; varios usuarios con permisos distintos; control
de la red en operación.

## Criterios de finalización

Cada RF citado por al menos una prueba (`grep "026:RF-"`); el Transformer con un acierto de tarea
en su conjunto de prueba igual o mayor que el umbral del perfil; una orden real de cada tarea de
RF-11 ejecutada desde la consola en DIgSILENT; suite completa en verde con las siete variables.

## Dudas resueltas (usuario, 2026-10-24)

- Tipos de estudio: estudio eléctrico y factibilidad, cada uno con subtipos (RF-16).
- Modelo de Ollama: se miden qwen2.5:3b y llama3.1:8b con las mismas órdenes y se queda el que
  más acierte dentro de 30 s (en el plan).
- Índice del proyecto: búsqueda semántica con un modelo de embeddings local de Ollama
  (`nomic-embed-text`), descargado una vez con la aprobación del usuario; sin él, búsqueda por
  palabras.
- Frecuencia: trabajos y modelos cada minuto mientras la web está abierta; la suite completa cada
  noche (RF-22, RF-23, RF-25).
