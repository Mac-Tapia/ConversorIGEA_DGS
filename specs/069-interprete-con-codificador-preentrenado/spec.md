# Spec 069 — Intérprete de órdenes con codificador preentrenado y clase «ninguna»

Estado: aprobada

Rama de trabajo: `asistente/maestro`.
Cita: 026 (asistente), 027 (RF-18, RF-19), 047 (RF-1, RF-11, RF-13, RF-14), 067 (RF-20 a RF-25), 068 (dataset real).

## Por qué

El usuario, el 2026-11-02: «haz lo que falta que llegue a las puertas, ahí tienes los archivos para construir dataset
o lo que necesitas, debemos dejarlo funcional y con datos reales y no alucinen».

Medido por el integrador sobre el candidato letra a letra `a35130bc`: 62,9 % en las 922 de prueba, F1 de 0,841 y rechazado.
Con confianza de 0,85 o más solo acierta el 71,7 %, y el 62,6 % de los 701 mensajes reales que no son órdenes pasa ese
umbral: propone tareas para una conversación. «Transforma la red X en dgs» le sale `transferencia` con confianza 1,0.
Un alfabeto de caracteres aprendido desde cero no conoce sinónimos. Un experimento con un codificador preentrenado
congelado, solo sobre selección y calibración, dio 90,1 % y 97,5 %, y el 94,8 % de rechazo de la conversación reservada.

## Requisitos

Los umbrales de RF-17 a RF-19 y RF-24 se declaran aquí antes de medir el modelo definitivo. El experimento del
integrador ya había visto los mensajes reservados; por eso se declara también en Limitaciones.

### Modelo

- RF-1: EL SISTEMA interpretará las órdenes con un codificador preentrenado congelado, una cabeza de tarea y una cabeza
  de etiquetas por token.
- RF-2: EL SISTEMA devolverá de cada orden `tarea`, `confianza`, `alternativas`, `datos`, `modelo` y `version`, como
  `ModeloOrdenes.predecir`.
- RF-3: EL SISTEMA no devolverá un dato cuyo tipo no admita la tarea predicha.
- RF-4: EL SISTEMA guardará como artefactos solo las cabezas y sus metadatos, y nombrará el codificador por su nombre y
  su revisión fijada.
- RF-5: SI el codificador no está en la caché local, ENTONCES EL SISTEMA dará un error que lo nombre, sin usar la red.
- RF-6: SI no hay GPU, ENTONCES EL SISTEMA dará el error de siempre, sin caer a la CPU.
- RF-7: EL SISTEMA seguirá cargando los modelos heredados que estén en uso.
- RF-8: CUANDO el registro apruebe un modelo con codificador, EL SISTEMA lo pondrá en uso con el mismo puntero que a los
  demás.
- RF-9: CUANDO se reabra un modelo con codificador en un proceso nuevo, EL SISTEMA obtendrá sus mismas predicciones.
- RF-30: CUANDO la tarea sea `pregunta`, EL SISTEMA no marcará un trozo como `texto`, porque la pregunta es el mensaje entero.
- RF-31: EL SISTEMA dará cada dato con todas sus palabras, sin recortar las de unión de sus bordes.
- RF-32: CUANDO el dato de alimentadores sea «todos los alimentadores», EL SISTEMA lo entenderá como todos.

### Clase «ninguna»

- RF-10: EL SISTEMA entrenará la clase `ninguna` con mensajes reales que el maestro etiquetó así, solo en la partición de
  entrenamiento, como plata.
- RF-11: EL SISTEMA apartará por hash del texto normalizado el 30 % de esos mensajes para medir el rechazo, fuera del corpus.
- RF-12: SI un mensaje `ninguna` coincide en texto normalizado o en familia con selección, calibración, prueba, una
  orden humana o una fija de prueba, ENTONCES EL SISTEMA no lo llevará al entrenamiento.
- RF-13: EL SISTEMA dejará idénticas las filas de selección, calibración y prueba, y las huellas de las órdenes fijas.
- RF-14: EL SISTEMA no contará los mensajes `ninguna` como órdenes humanas.
- RF-15: CUANDO el modelo responda `ninguna`, EL SISTEMA dejará la orden sin tarea, sin datos y sin consultar a otro
  modelo, para preguntar al operador.
- RF-16: EL SISTEMA no ofrecerá `ninguna` como alternativa de una orden.

### Rechazo

- RF-17: CUANDO se evalúe un candidato, EL SISTEMA aprobará la puerta de rechazo solo si la clase `ninguna` recoge al
  menos el 90 % de los mensajes reservados.
- RF-18: CUANDO se evalúe un candidato, EL SISTEMA aprobará la puerta de rechazo solo si como mucho el 2 % de los mensajes
  reservados recibe una tarea con confianza igual o mayor que su umbral.
- RF-19: SI hay menos de 100 mensajes reservados o el rechazo no se pudo medir, ENTONCES EL SISTEMA no aprobará el candidato.
- RF-20: EL SISTEMA dará en la decisión y en el JSON de salida las tasas de rechazo, de lo que se cuela y su denominador,
  del candidato y del modelo en uso.
- RF-21: EL SISTEMA no pondrá en el registro ni en el JSON de salida el texto de los mensajes reservados.
- RF-22: EL SISTEMA conservará las puertas de 0,95 y 0,85 por familia, las de 0,98 y 0,95 de las órdenes humanas y la
  política de evaluación.

### Calibración

- RF-23: EL SISTEMA ajustará la temperatura del modelo solo con la partición de calibración.
- RF-24: EL SISTEMA fijará como umbral del modelo el menor de 0,85, 0,90 y 0,95 con el que acierte al menos el 98 % de lo
  que cubre en la partición de calibración.
- RF-25: SI ningún umbral llega al 98 %, ENTONCES EL SISTEMA fijará 0,95.
- RF-26: CUANDO el modelo traiga su umbral, EL SISTEMA lo usará en el intérprete en vez del fijo de 0,85.
- RF-27: EL SISTEMA dará la cobertura y el acierto por umbral del candidato y del modelo en uso en la prueba, sin
  usarlos para decidir el diseño.

### Entrenamiento y currículo

- RF-28: CUANDO se pida el entrenamiento integral, EL SISTEMA entrenará las cabezas sobre el codificador y leerá los
  mensajes `ninguna` del almacén.
- RF-29: EL SISTEMA añadirá solo a entrenamiento las frases de operador de las tareas flojas, con esas tareas elegidas
  mirando selección y calibración.
- RF-33: CUANDO se pida el entrenamiento integral con `--codificador large`, EL SISTEMA usará `intfloat/multilingual-e5-large`
  con su revisión fija del catálogo verificado (`docs/MODELOS_IA_LOCK.json`) y guardará en el modelo el codificador que usó,
  para reabrirlo con él (RF-4). Sin la opción sigue el base. (2026-11-11: con el base y 6 capas afinadas el candidato llegó a
  0,995 en selección y a 0,875 en la sellada; la distancia entre las dos, no un error concreto de la prueba, motiva el cambio.)
- RF-34: CUANDO se guarde cada candidato, EL SISTEMA comprobará en ese momento que anota el codificador con que se entrenó,
  y si no, parará el entrenamiento. (2026-11-11: el error salió al reabrir, tras 1 h 45 min de GPU.)
- RF-35: EL SISTEMA promoverá el intérprete con la puerta selectiva (decisión del usuario del 2026-11-11): sobre lo que
  da con confianza igual o mayor que su umbral calibrado, la tarea acertada en al menos el 98 % y el plan de sus datos igual
  al de las etiquetas en al menos el 95 %, con al menos la mitad de las órdenes ejecutadas solas, en la sellada y en el
  conjunto que decide (085:RF-19); en el total no acertará menos que el modelo en uso. Lo demás lo confirma el operador o lo
  resuelve el modelo local. De la charla reservada (RF-17 a RF-19) cuenta la que se colaría a ejecutarse sola (como mucho
  el 2 %, con al menos 100 mensajes medidos), no la que no reconoce como `ninguna` y queda bajo el umbral. La puerta de
  todas las órdenes queda en la decisión para comparar.
- RF-36: EL SISTEMA resolverá en el plan las listas de alimentadores sin las palabras de unión («CA101 a CHN102»), la ruta
  que existe dentro de un trozo con palabras de más, y el texto de `pregunta` y `clasificar_informe` como el mensaje entero;
  `buscar_internet` sigue con su trozo, para no sacar a la red las palabras de la orden (086:RF-24).
- RF-37: EL SISTEMA elegirá el umbral de ejecución con el límite inferior de Wilson (95 %) del acierto en calibración, no
  con el acierto puntual. (2026-11-11: el puntual eligió 0,90 por 0,981 y en la sellada acertó 0,970 de lo ejecutado solo.)
- RF-38: SI, sobre las mismas órdenes humanas, el candidato acierta la tarea menos que el modelo en uso con una
  diferencia significativa en la prueba de McNemar exacta unilateral (binomial sobre las órdenes discordantes, α = 0,05),
  ENTONCES EL SISTEMA rechazará el candidato, haya o no 200 humanas y decida o no el examen del maestro (085:RF-19).
  (2026-11-12: reg-75fdd605 se promovió con 0 fallos acertando 32 de 43 humanas frente a 41 de 43 de prov-8fd8a405;
  Dietterich, *Neural Computation* 10(7), 1998, https://web.engr.oregonstate.edu/~tgd/publications/dietterich-approximate-statistical-tests-nc1998.pdf;
  Miller, *Adding Error Bars to Evals*, 2024, https://arxiv.org/abs/2411.00640.)
- RF-39: EL SISTEMA medirá el modelo en uso y el candidato orden por orden sobre las mismas humanas, con el modelo que
  da la medida humana informada (el de fuera de grupo con validación cruzada), y guardará la prueba en la decisión.
- RF-40: SI hay modelo en uso y no se pudo medir sobre las humanas, ENTONCES EL SISTEMA no aprobará el candidato; sin
  modelo en uso, la puerta de RF-38 no aplica y lo dirá.

## Fuera de alcance

Ajustar el codificador, cambiar puertas existentes, medir en la prueba para decidir el diseño, promover a mano, y la
vía antigua `entrenar_y_promover`, que sigue entrenando el modelo letra a letra.

## Limitaciones declaradas

El umbral de RF-24 empezaba en 0,70 y se subió a 0,85 tras medir en desarrollo, sin tocar RF-17 ni RF-18. La conversación reservada ya la vio el experimento del integrador, en un modelo descartado: su medida orienta los umbrales
de RF-17 y RF-18, que por eso no son una estimación ciega. Mensajes casi iguales («sigue», «sigue hasta cerrar») pueden caer
a los dos lados del hash, lo que favorece el rechazo. Cada tarea de la prueba es una sola paráfrasis expandida (068).
