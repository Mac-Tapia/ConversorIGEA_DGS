# Spec 085 — Órdenes del maestro con grupos apartados, y la puerta de órdenes sin humanas suficientes

Estado: cumplida (2026-11-07, campaña integral en la GPU) · Fecha: 2026-11-03 · Origen: orden del usuario

Cita: 027 (RF-18, RF-19), 047 (RF-8, RF-9, RF-11), 068 (RF-26, RF-27, RF-30), 069 (RF-10), 075 (RF-1 a RF-5, RF-21), 079 (RF-45, RF-48).

## Contexto y objetivo

El usuario, el 2026-11-03: «tú debes cumplir el rol de humano, ya que eres el rol de maestro, y debes usar la metodología de
destilación». Hay 43 órdenes confirmadas por el operador, y 12 de las 16 tareas medidas tienen un solo texto: la validación cruzada de
la 075 no puede medir fuera de grupo, y faltan las 200 independientes de 027:RF-19 que nadie va a escribir. Medido: el candidato
afinado (079) da 0,847 en la sellada, 0,815 sintéticas y 0,721 humanas fuera de grupo, con puertas de 0,95 y 0,98.

El maestro (Claude) redacta órdenes en el estilo del operador para todas las tareas del catálogo, sin mirar los conjuntos sellados ni
los errores del modelo. Por tarea, una parte de sus grupos se aparta para examinar y nunca entrena; así la medida fuera de grupo dice
algo. Las tres cifras se dan separadas: humanas reales, maestro y sintéticas. Las del maestro nunca cuentan como humanas.

## Requisitos funcionales (EARS)

### Las órdenes del maestro

- RF-1: EL SISTEMA leerá las órdenes del maestro de `<almacén>/ordenes_maestro.jsonl`, local y fuera de git, cada una con su texto, su
  tarea o `ninguna`, sus datos con sus tramos, su forma, su autor, su revisión y el origen `maestro`.
- RF-2: SI una orden del maestro no tiene el origen `maestro`, ENTONCES EL SISTEMA la rechazará y la contará.
- RF-3: SI una orden del maestro nombra una tarea que no existe, ENTONCES EL SISTEMA la rechazará y la contará.
- RF-4: SI un dato de una orden del maestro sale de su texto, es de un tipo que su tarea no admite o falta uno obligatorio, ENTONCES
  EL SISTEMA la rechazará y la contará.
- RF-5: EL SISTEMA no dará a una orden del maestro la calidad `gold_human` ni la contará como orden humana (068:RF-30).

### Grupos apartados para el examen

- RF-6: EL SISTEMA agrupará las órdenes del maestro en familias con la regla de 075:RF-2 a RF-5 antes de repartirlas.
- RF-7: EL SISTEMA apartará para examen, en cada tarea, el 25 % de sus familias redondeado hacia arriba.
- RF-8: EL SISTEMA elegirá las familias apartadas por la huella de su identidad, sin depender del orden de entrada.
- RF-9: SI una tarea tiene menos de 2 familias del maestro, ENTONCES EL SISTEMA no le apartará examen y la nombrará `sin_examen`.
- RF-10: EL SISTEMA pondrá las órdenes de examen en la partición de prueba con el conjunto `examen_maestro_085`, y ninguna en entrenamiento.
- RF-11: EL SISTEMA pondrá las demás órdenes del maestro solo en entrenamiento, con variantes de erratas deterministas por su texto.
- RF-12: EL SISTEMA pondrá las órdenes `ninguna` del maestro solo en entrenamiento.
- RF-13: SI una orden del maestro coincide en texto o familia con selección, calibración, prueba, una orden humana, una fija de prueba o un
  mensaje reservado, ENTONCES EL SISTEMA la descartará y la contará.
- RF-14: SI una fila de entrenamiento de otro origen coincide en texto o familia con una orden de examen del maestro, ENTONCES EL SISTEMA
  la quitará del entrenamiento y la contará.
- RF-15: EL SISTEMA dejará idénticas, con o sin órdenes del maestro, las filas de selección, calibración y las selladas, con sus huellas.
- RF-16: EL SISTEMA dará el mismo corpus con las mismas entradas.

### Tres cifras y la puerta de órdenes

- RF-17: EL SISTEMA dará por separado el acierto y el F1 de las órdenes humanas, de las del maestro y de las sintéticas, cada uno con su
  denominador.
- RF-18: EL SISTEMA dará el acierto y el F1 del examen del maestro por tarea, cada uno con su denominador.
- RF-19: MIENTRAS haya menos de 200 órdenes humanas distintas y haya examen del maestro, EL SISTEMA aplicará la puerta de órdenes de
  0,98 y 0,95 al examen del maestro, con su denominador.
- RF-20: CUANDO la puerta de órdenes se decida con el examen del maestro, EL SISTEMA lo dirá en la decisión con el conjunto, el
  denominador y el número de órdenes humanas que faltan.
- RF-21: CUANDO haya 200 órdenes humanas distintas o más, EL SISTEMA aplicará la puerta de órdenes a las humanas, como hasta ahora, y dará
  la del maestro sin que decida.
- RF-22: MIENTRAS la puerta de órdenes se decida con el maestro, EL SISTEMA seguirá dando la medida humana, sin que decida.
- RF-23: EL SISTEMA no cambiará las puertas de 0,98, 0,95, 0,85, 0,90 ni 0,02.
- RF-24: EL SISTEMA mantendrá la confirmación obligatoria de toda acción que escribe mientras haya menos de 200 órdenes humanas (027:RF-19).

### Informes del clasificador

- RF-25: EL SISTEMA dará en el manifiesto del clasificador de informes cuántos informes de entrenamiento y de prueba llevan cada origen.

### Modelo en uso provisional

El usuario, el 2026-11-04 («has lo recomendado»): el candidato del entrenamiento rechazado es mucho mejor que el modelo en uso (prueba
sellada 0,860 frente a 0,17; se cuela 0 % frente a 67 %), aunque no pasa las puertas. Se usa pidiendo siempre confirmación, con sus
cifras a la vista y sin marcarlo aprobado: las puertas no bajan.

- RF-26: CUANDO el usuario decida usar un candidato que no pasa las puertas, EL SISTEMA guardará en el registro quién lo decide, la fecha, el motivo, las cifras del candidato y el modelo anterior.
- RF-27: SI el candidato no está rechazado por sus puertas, no reabrió en un proceso nuevo o falla su integridad, ENTONCES EL SISTEMA no lo pondrá en uso provisional y dirá por qué.
- RF-28: EL SISTEMA dejará intacta la decisión de las puertas del candidato, sin darlo por aprobado ni por activo en el registro.
- RF-29: CUANDO se vuelva al anterior o entre un modelo aprobado, EL SISTEMA dejará de tratar como provisional al modelo que sale.
- RF-30: MIENTRAS el modelo de órdenes en uso sea provisional, EL SISTEMA dirá «provisional, no pasa las puertas» y sus cifras en la web y en cada plan del asistente.
- RF-31: EL SISTEMA no ejecutará ninguna tarea que escribe sin la confirmación del operador, sea cual sea la confianza del modelo.
- RF-32: MIENTRAS el modelo de órdenes en uso sea provisional, EL SISTEMA tampoco lanzará sin confirmación un trabajo de solo lectura.
- RF-33: EL SISTEMA dará una herramienta para ver, poner y retirar el modelo provisional, que no aplica nada sin el candidato, quien decide y el motivo.

## Fuera de alcance

Entrenar o usar la GPU; cambiar `ajuste_condicionado.py`, que decide el ajuste del LLM solo con órdenes reales (047:RF-8); cambiar las
descripciones de `TAREAS_HASTA_069`, las órdenes fijas o las selladas; marcar algo como confirmado por el operador. Bajar una puerta o aprobar un candidato por decisión del usuario: la 085 usa, no aprueba.

## Limitaciones declaradas

- El examen del maestro lo escribió el mismo autor que su entrenamiento, en la misma sesión: estima el estilo del maestro, no el del
  operador. Por eso la medida humana se sigue dando al lado.
- Las familias no captan paráfrasis con otras palabras: dos formas del mismo autor pueden caer en grupos distintos.
- Con 8 a 9 formas por tarea, el examen tiene 2 o 3 familias por tarea; una sola fallada en una tarea pesa poco en el agregado y mucho en
  su tarea.
- RF-19 es la decisión del usuario del 2026-11-03: que el maestro cumpla el rol que no cubren las órdenes humanas. Si el operador llega a
  200, decide RF-21.
- RF-32 lee «pidiendo siempre confirmación» también para los trabajos de lectura, que no escriben pero sí ocupan DIgSILENT o la GPU; las
  consultas al momento siguen respondiendo, porque no ejecutan nada. Con un modelo aprobado, los trabajos de lectura vuelven a lanzarse solos.
- La prueba sellada de las cifras (`df5e1db88595d378`) ya no era ciega cuando se midió (079) y no decide; el examen del maestro es del
  mismo autor que su entrenamiento. Son lo que hay para decidir a la vista, no una aprobación.
