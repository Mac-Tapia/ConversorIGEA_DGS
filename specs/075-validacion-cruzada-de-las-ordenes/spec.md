# Spec 075 — Validación cruzada con las órdenes confirmadas, y Ollama no adivina cuando el modelo ve charla

Estado: cumplida (2026-11-07, campaña integral en la GPU)

Rama de trabajo: `asistente/075`.
Cita: 027 (RF-19, RF-38), 047 (RF-11), 068 (RF-30, RF-41), 069 (RF-2, RF-6, RF-11, RF-15 a RF-22, RF-26), 070 (RF-69 a RF-73, RF-75, RF-76).

## Por qué

Medido el 2026-11-02: el candidato `6d1f4a30…` se rechazó. En la prueba sellada `df5e1db88595d378` dio 0,804 de acierto y
0,686 de F1; en las 42 órdenes confirmadas por el operador, 0,500 y 0,769, cuando el modelo en uso da 0,690; rechazo 0,908 y
se cuela 0,000. Por 070:RF-76 las confirmadas solo examinan: el modelo nunca aprendió el estilo real del operador.

El usuario lo decidió: repartir sus órdenes en 5 grupos, entrenar con 4 y examinar con el que queda, rotando, sin bajar puertas.
Con 42 textos, una sola fallada ya rompe 0,98. La medida solo vale si las erratas no la filtran: «como va el avance», «como va el
avnace» y «coma va enl avance» son una misma orden, y con una a cada lado se examinaría al modelo con lo que acaba de leer.

También en la web: «muchas gracias» a secas cayó bajo el umbral del modelo y Ollama respondió `estado` con confianza 1,0.

## Requisitos

Los umbrales de esta spec se declaran antes de medir; ninguno se ajusta mirando una medida (RF-46).

### Familias de órdenes casi iguales

- RF-1: EL SISTEMA agrupará las órdenes confirmadas en familias antes de repartirlas en vueltas.
- RF-2: EL SISTEMA pondrá en una familia dos órdenes cuya clave coincida, siendo la clave el texto sin tildes, mayúsculas, signos ni cortesía inicial, con cada dato y cada palabra con dígitos sustituidos por una misma marca.
- RF-3: EL SISTEMA pondrá en una familia dos órdenes cuya clave difiera como mucho en un 25 % de la longitud de la mayor, contando como una edición quitar, poner, cambiar o cruzar dos letras contiguas.
- RF-4: EL SISTEMA pondrá en una familia dos órdenes cuando todas las palabras con contenido de una, si son al menos dos sin contar marcas, estén en la otra, admitiendo en cada palabra de cuatro letras o más hasta un 34 % de ediciones.
- RF-5: EL SISTEMA tratará ser de la misma familia como transitivo, aunque junte órdenes de tareas distintas.

### Reparto en vueltas

- RF-6: EL SISTEMA repartirá las familias en 5 vueltas, cada familia en una sola.
- RF-7: EL SISTEMA dará el mismo reparto con la misma semilla, sea cual sea el orden de entrada.
- RF-8: EL SISTEMA dejará cada familia en la vuelta con menos órdenes de sus tareas, y a igualdad en la que tenga menos órdenes en total.
- RF-9: SI hay menos familias que vueltas, ENTONCES EL SISTEMA no dará medida fuera de grupo y dejará el candidato `BLOQUEADO_POR_DATOS`, con el motivo y las cuentas.

### Entrenar cada vuelta

- RF-10: CUANDO se mida una vuelta, EL SISTEMA la examinará con cabezas entrenadas sin ninguna orden de esa vuelta.
- RF-11: EL SISTEMA reutilizará en todas las vueltas el codificador congelado y su caché, sin codificar dos veces una frase de entrenamiento.
- RF-12: EL SISTEMA dejará fuera del entrenamiento de una vuelta toda fila de plata o sintética con el mismo texto o la misma familia que una orden examinada en ella.
- RF-13: EL SISTEMA dejará fuera del entrenamiento de una vuelta toda variante con erratas de una confirmada que caiga en la familia de una orden examinada en ella.
- RF-14: EL SISTEMA entrenará cada confirmada de las otras vueltas repetida 8 veces y con 8 variantes con erratas, deterministas por su texto, sin tocar sus datos.
- RF-15: EL SISTEMA dejará el corpus guardado idéntico: lo que cada vuelta entrena vive en memoria.
- RF-16: EL SISTEMA usará en las vueltas y en el modelo final el método y la semilla del candidato ganador en selección.

### La medida que decide

- RF-17: EL SISTEMA examinará cada orden confirmada exactamente una vez, en su vuelta.
- RF-18: EL SISTEMA dará el acierto y el F1 agregados fuera de grupo con su denominador.
- RF-19: EL SISTEMA dará el acierto y el F1 fuera de grupo por tarea, cada uno con su denominador.
- RF-20: EL SISTEMA dará por vuelta las órdenes examinadas, las confirmadas que entrenan, las filas que entrenan, las de plata apartadas y las tareas sin ninguna fila.
- RF-21: CUANDO se decida un candidato con validación cruzada, EL SISTEMA aplicará la puerta humana de 0,98 y 0,95 a la medida agregada fuera de grupo.
- RF-22: EL SISTEMA conservará las puertas de 0,95 y 0,85 sintéticas por familia y de 0,90 y 0,02 de rechazo, sin ninguna excepción.

### Tareas que no pueden aprender de sí mismas

- RF-23: SI una tarea tiene sus órdenes confirmadas en una sola familia, o menos de dos familias que puedan entrenar, ENTONCES EL SISTEMA la marcará `sin_independencia`, con su motivo.
- RF-24: EL SISTEMA no dará a una tarea `sin_independencia` el visto bueno por tarea: su `cumple` será nulo, nunca verdadero.
- RF-25: EL SISTEMA contará las órdenes de esa tarea en la medida agregada, con su acierto o su fallo, sin apartarlas del denominador.
- RF-26: EL SISTEMA nombrará en la decisión las tareas `sin_independencia`, sin añadir por ellas puerta alguna ni quitar ninguna.

### El modelo final

- RF-27: CUANDO termine la validación, EL SISTEMA entrenará el modelo final con todas las confirmadas que puedan entrenar.
- RF-28: SI una confirmada coincide en texto o familia con selección, calibración, prueba sintética, prueba sellada, mensajes reservados o fijas de prueba, ENTONCES EL SISTEMA no la entrenará en ninguna vuelta ni en el modelo final, la seguirá examinando y la contará.
- RF-29: EL SISTEMA medirá el modelo final en la prueba sellada `df5e1db88595d378`, sin que ninguna de sus filas entrene.
- RF-30: EL SISTEMA dará la medida humana del modelo final marcada como no independiente y sin decidir.
- RF-31: EL SISTEMA mantendrá la confirmación obligatoria de toda acción que escribe mientras haya menos de 200 órdenes (027:RF-19).
- RF-32: EL SISTEMA no contará como órdenes humanas ni la plata ni las variantes de las confirmadas (068:RF-30).
- RF-33: EL SISTEMA dejará idéntica la huella de las órdenes fijas `41f7ab110ac35c0b` y la de la prueba sellada.
- RF-34: EL SISTEMA no pondrá en el registro ni en el JSON de salida el texto de una orden confirmada.
- RF-35: EL SISTEMA hará la validación cruzada solo si se pide con su opción.
- RF-36: MIENTRAS no se pida, EL SISTEMA dejará las confirmadas solo en la prueba (070:RF-76).

### Ollama no impone una tarea en lo que el modelo ve como charla

- RF-37: CUANDO el modelo con clase `ninguna` no llegue a su umbral y `ninguna` sea su primera o su segunda opción, EL SISTEMA dejará la orden sin tarea, sin consultar a Ollama.
- RF-38: CUANDO eso ocurra, EL SISTEMA preguntará al operador por la tarea, ofreciendo las alternativas del modelo, y dirá en lo consultado que Ollama no se consultó.
- RF-39: SI `ninguna` es la tercera opción o una posterior, ENTONCES EL SISTEMA consultará a Ollama como hasta ahora.
- RF-40: MIENTRAS el modelo llegue a su umbral, EL SISTEMA no aplicará esta regla.
- RF-41: SI el modelo no tiene clase `ninguna`, ENTONCES EL SISTEMA consultará a Ollama como hasta ahora.
- RF-42: EL SISTEMA medirá la regla solo con la partición de selección y los mensajes reservados, sin consultar a Ollama y suponiendo que imponga tarea siempre que se le pregunte.
- RF-43: EL SISTEMA dará la regla por cumplida solo si llega a Ollama como mucho el 2 % de los mensajes reservados.
- RF-44: EL SISTEMA dará la regla por cumplida solo si frena como mucho el 5 % de las órdenes de selección.
- RF-45: EL SISTEMA dará esa medida en el informe sin que decida la promoción.

### Sin ajustar mirando

- RF-46: EL SISTEMA guardará en el protocolo las vueltas, la semilla, los umbrales de familia y el peso de las confirmadas antes de entrenar ninguna vuelta.

## Fuera de alcance

Entrenar, usar la GPU o DIgSILENT en esta fase; bajar puertas; cambiar `PoliticaEvaluacion`, las órdenes fijas o la prueba sellada;
reentrenar el codificador; pedir a Ollama que nombre su evidencia; tocar `digital_twin/oraculo.py`, `optimizacion_oraculo.py`,
`valle.py`, `escalera_optima.py` o `pide*`; leer `ejemplos.jsonl` o `maestro_real/` desde pruebas.

## Limitaciones declaradas

- RF-25 y RF-26 no añaden puerta por las tareas `sin_independencia`, porque una tarea sin ninguna confirmada tampoco la tiene: bloquearlas haría que confirmar una orden nueva impidiera promover, y borrarla lo permitiera. Una de ellas que falle sí rompe el 0,98 agregado, y eso no tiene excepción.
- Sobre una tarea `sin_independencia`, un acierto dice que el modelo la reconoce sin haber visto ninguna orden del operador de esa tarea; no dice que aprendió de ellas.
- La medida fuera de grupo es de cabezas entrenadas con 4/5 de las confirmadas: estima el modelo final, no lo mide.
- RF-3 y RF-4 agrupan de más antes que de menos: «calibra X» y «recalibra X» caen juntas. Eso resta entrenamiento y no da medidas optimistas.
- Las familias no captan paráfrasis con otras palabras: «como va el avance» y «en que quedamos» son familias distintas y se entrenan una con la otra.
- Si tras ver la medida fuera de grupo se cambian RF-3, RF-4 o RF-14, esa medida deja de ser independiente: hay que declararlo en la siguiente ejecución.
- La regla de Ollama usa la posición de `ninguna`, no su probabilidad: una orden real en la que el modelo duda y `ninguna` va segunda se le pregunta al operador. Ese es su coste, y RF-44 lo mide.
- El modelo heredado letra a letra no tiene clase `ninguna`: con él la regla no aplica (RF-41).
- RF-42 no mide una respuesta real de Ollama: da la cota superior de lo que podría colarse.
