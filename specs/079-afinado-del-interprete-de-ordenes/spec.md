# Spec 079 — Afinado real del intérprete de órdenes: las últimas capas del codificador junto con sus cabezas

Estado: implementada

Rama de trabajo: `asistente/079`.
Cita: 027 (RF-19, RF-38), 047 (RF-1, RF-11), 069 (RF-1, RF-2, RF-4 a RF-9, RF-13, RF-17 a RF-27), 070 (RF-69 a RF-77), 075 (RF-10 a RF-22, RF-37 a RF-46), 077 (lectura local, sellados).

## Por qué

El usuario, el 2026-11-03: «se supone que se ha entrenado con fine tuning y QLoRA más avanzado». No es así: 069:RF-1 dejó el
codificador `intfloat/multilingual-e5-base` congelado y solo entrenan dos cabezas. Esta spec trae el afinado del intérprete; QLoRA
del LLM (047 T7) es otra tarea.

Medido el 2026-11-03 sobre el candidato con validación cruzada, ganador `destilado-23`: órdenes confirmadas fuera de grupo 0,721 y
F1 0,759; sellada `df5e1db88595d378` 0,797 y F1 0,675; rechazo 0,883 y se cuela 0,000; umbral 0,95. En selección, por tarea:
`calibrar` 0,03, `no_disponible` 0,23, `escanear` 0,25, `descargar_resultados` 0,40, `verificar_caso_base` 0,49 y
`simular_calibracion` 0,62. Con confianza de 0,85 o más acierta el 97,3 % y cubre el 49 %. La regla de Ollama no cumple: 9 de los 206
mensajes reservados, 0,044, llegan a Ollama, frente a 0,02 o menos; frena 27 de 1 607 órdenes de selección, 0,017, frente a 0,05 o menos.

La prueba sellada `df5e1db88595d378` ya se midió dos veces por familia y orientó esta spec: dejó de ser ciega. Hace falta otra.

## Requisitos

Los umbrales y rejillas de esta spec se declaran antes de medir. Las puertas no cambian.

### Afinado

- RF-1: CUANDO se pida con su opción, EL SISTEMA afinará las últimas capas del codificador junto con las dos cabezas.
- RF-2: MIENTRAS no se pida, EL SISTEMA entrenará solo las cabezas sobre el codificador congelado, como hasta ahora.
- RF-3: EL SISTEMA dará a las capas afinadas una tasa de aprendizaje menor que la de las cabezas.
- RF-4: EL SISTEMA dará a cada capa afinada una tasa menor que la de la capa siguiente.
- RF-5: EL SISTEMA afinará por defecto las 2 últimas capas, con lotes de 32 frases como mucho.
- RF-6: EL SISTEMA cerrará un lote antes de que pase de 1 536 piezas contando el relleno, por omisión.
- RF-7: EL SISTEMA limitará por omisión a 5 GB la memoria de GPU de su proceso, porque comparte 8 GB con la web.
- RF-8: SI se agota la memoria de GPU, ENTONCES EL SISTEMA dará un error que nombre la opción que la baja.
- RF-9: MIENTRAS afine en CUDA, EL SISTEMA pasará por las capas afinadas con precisión mixta.
- RF-10: SI no hay GPU, ENTONCES EL SISTEMA dará el error de siempre, sin caer a la CPU (069:RF-6).
- RF-11: CUANDO termine una época, EL SISTEMA medirá la partición de selección y conservará los pesos de la mejor época.
- RF-12: SI pasan 2 épocas sin mejorar en selección, ENTONCES EL SISTEMA parará ese entrenamiento.
- RF-13: SI no hay filas de selección, ENTONCES EL SISTEMA no afinará.
- RF-14: EL SISTEMA empezará cada entrenamiento, sea candidato, vuelta o modelo final, desde los pesos de la revisión fijada, sin heredar los de otro.
- RF-15: EL SISTEMA pasará por las capas afinadas en cada paso, sin guardar ni reutilizar nada de lo que ellas den.
- RF-16: EL SISTEMA guardará de cada frase solo la salida de las capas congeladas, una vez por ejecución (075:RF-11).
- RF-17: EL SISTEMA dará por cada época la pérdida, la medida en selección, el tiempo y la memoria de pico.

### El artefacto

- RF-18: EL SISTEMA guardará en el artefacto del modelo las cabezas y las capas afinadas, sin el resto del codificador.
- RF-19: EL SISTEMA escribirá en los metadatos el nombre y la revisión del codificador, las capas afinadas, la huella de esas capas y la de las congeladas.
- RF-20: SI al reabrir no coincide una de esas huellas, ENTONCES EL SISTEMA dará un error que la nombre.
- RF-21: CUANDO se reabra un modelo afinado en un proceso nuevo, EL SISTEMA obtendrá sus mismas predicciones.
- RF-22: EL SISTEMA devolverá de un modelo afinado los mismos campos que 069:RF-2.
- RF-23: EL SISTEMA seguirá cargando los modelos heredados y los que tienen codificador sin afinar.
- RF-24: CUANDO el registro apruebe un modelo afinado, EL SISTEMA lo pondrá en uso con el mismo puntero que a los demás (069:RF-8).

### Pérdida contrastiva

- RF-25: MIENTRAS afine, EL SISTEMA sumará a la pérdida una contrastiva supervisada que acerque las frases de una tarea y las aleje de las de su grupo.
- RF-26: EL SISTEMA tendrá como grupos de tareas parecidas `calibrar`, `recalibrar`, `simular_calibracion`, `sistema_completo`; `escanear`, `verificar_caso_base`, `verificar_convergencia`; `convertir`, `unir`, `convertir_sistema`, `convertir_set`; y `no_disponible`, `estudios`.
- RF-27: EL SISTEMA tratará la clase `ninguna` como parecida a toda tarea.
- RF-28: EL SISTEMA pondrá en cada lote filas de las tareas de un grupo y de `ninguna`, para que tengan con quién contrastarse.
- RF-29: EL SISTEMA dará en el informe las confusiones más frecuentes del candidato ganador en selección y en calibración, nunca en prueba.
- RF-30: EL SISTEMA no sacará los grupos ni las confusiones de una prueba sellada ni de una orden confirmada.

### Currículo

- RF-31: EL SISTEMA añadirá solo a entrenamiento frases nuevas de las tareas flojas en selección.
- RF-32: EL SISTEMA marcará esas filas con el origen `parafrasis_079`.
- RF-33: EL SISTEMA tendrá al menos 10 frases nuevas por cada tarea floja declarada arriba.
- RF-34: SI una frase nueva coincide en texto o familia con selección, calibración o una prueba, ENTONCES EL SISTEMA no la llevará al entrenamiento y la contará.
- RF-35: EL SISTEMA dejará idéntica la huella de las órdenes fijas `41f7ab110ac35c0b`.
- RF-36: EL SISTEMA dejará idéntica la huella de la prueba histórica y las filas de selección y calibración (069:RF-13).
- RF-37: EL SISTEMA no hará depender el currículo nuevo de `prueba_sellada.py`, de sus filas ni de `ejemplos.jsonl`.

### Otra prueba sellada

- RF-38: EL SISTEMA tendrá una prueba `sellada_079` con al menos 5 frases nuevas por cada tarea del catálogo.
- RF-39: EL SISTEMA fijará la huella de `sellada_079`, independiente del vocabulario del espacio.
- RF-40: SI las frases de `sellada_079` cambian, ENTONCES EL SISTEMA las rechazará por la huella.
- RF-41: EL SISTEMA declarará en el módulo de `sellada_079` cómo se escribió, quién la escribió y qué no garantiza.
- RF-42: SI `sellada_079` coincide en familia con selección o calibración, ENTONCES EL SISTEMA parará, sin tocarlas.
- RF-43: EL SISTEMA no llevará al entrenamiento ninguna familia de `sellada_079`.
- RF-44: EL SISTEMA no compartirá ningún texto ni familia entre `sellada_079` y la sellada anterior.
- RF-45: CUANDO se decida un candidato, EL SISTEMA aplicará las puertas de 0,95 y 0,85 por familia a `sellada_079`.
- RF-46: EL SISTEMA medirá la sellada anterior `df5e1db88595d378`, con su huella intacta, marcada con `decide` falso.
- RF-47: EL SISTEMA dará las dos selladas en el informe y en el registro, cada una con su huella.
- RF-48: EL SISTEMA conservará las puertas de 0,98 y 0,95 humanas fuera de grupo y las de 0,90 y 0,02 de rechazo, sin ninguna excepción.

### Validación cruzada y regla de Ollama

- RF-49: CUANDO se pida validación cruzada con afinado, EL SISTEMA afinará cada vuelta y el modelo final con el método y la semilla del ganador en selección (075:RF-16).
- RF-50: EL SISTEMA elegirá la regla de Ollama en una rejilla declarada aquí: `ninguna` entre las 2, 3, 4 o 5 primeras opciones, y un piso de confianza de 0, 0,3 o 0,5 bajo el cual tampoco se consulta.
- RF-51: EL SISTEMA medirá esa rejilla solo con la partición de selección y los mensajes reservados, sin consultar a Ollama (075:RF-42).
- RF-52: EL SISTEMA elegirá la combinación que cumpla 0,02 o menos de reservados a Ollama y 0,05 o menos de órdenes frenadas, y entre ellas la que menos órdenes frene.
- RF-53: SI ninguna combinación cumple, ENTONCES EL SISTEMA elegirá, sin pasar de 0,05 de órdenes frenadas, la que menos reservados deje llegar y dirá que no cumple.
- RF-54: EL SISTEMA guardará la regla elegida en el modelo.
- RF-55: CUANDO el modelo traiga su regla, EL SISTEMA la usará en el intérprete en vez de la fija, sin consultar a Ollama en lo que ella frene.
- RF-56: SI el modelo no trae regla, ENTONCES EL SISTEMA usará la de 075:RF-37.
- RF-57: EL SISTEMA dará la rejilla medida en el informe, sin que decida la promoción (075:RF-45).

### Convivencia con la 077 y operación

- RF-58: EL SISTEMA leerá el codificador solo de la caché local que señale el entorno del proceso, administrada o la del usuario, sin usar la red.
- RF-59: SI el codificador no está en esa caché, ENTONCES EL SISTEMA dará un error que nombre el modelo, su revisión y la orden que lo prepara.
- RF-60: EL SISTEMA dejará `sellada_079` vedada a la lectura local del LLM, como las demás selladas (077).
- RF-61: EL SISTEMA dará el afinado por `tools/asistente_entrenar.py` con su opción, combinable con la validación cruzada.
- RF-62: SI esa opción se pide fuera de la vía integral, ENTONCES EL SISTEMA la rechazará.
- RF-63: EL SISTEMA guardará en el protocolo las capas, las tasas, los lotes, los grupos y la rejilla antes de entrenar ningún candidato.
- RF-64: EL SISTEMA no pondrá en el registro ni en el JSON de salida el texto de una orden confirmada, de un mensaje reservado ni de una prueba.

## Fuera de alcance

Entrenar o usar la GPU en esta fase; QLoRA del LLM (047 T7); bajar puertas; cambiar `PoliticaEvaluacion`, las órdenes fijas, las
descripciones o plantillas de `TAREAS_HASTA_069`, o las frases de la sellada anterior; tocar `lectura_proyecto.py`, `corpus_proyecto.py`,
`indice.py`, `valle.py`, `dgs.py`, `digital_twin/`, `plan.py` o `tareas.py`; leer `prueba_sellada.py`, sus filas, `ejemplos.jsonl` o
`maestro_real/` para escribir frases.

## Limitaciones declaradas

- `sellada_079` la escribió el mismo autor que el currículo de esta spec, en la misma sesión y sabiendo qué tareas salen flojas: otro redactor no era posible aquí. Es una estimación optimista frente a otro redactor, y por eso las dos se informan. Se escribió y se fijó antes de escribir el currículo y antes de medir, y no se ajusta tras medir: si se toca, deja de ser independiente y hay que declararlo.
- Las familias (firma sin datos) no captan paráfrasis con otras palabras: el mismo autor puede repetir ideas con palabras distintas. Se comprueba además con la familia más ancha de la 075, pero no es una garantía.
- RF-29 mira selección y calibración, que deciden la parada, la temperatura y el umbral: su medida ya no es independiente, como antes.
- La regla de RF-52 se elige con los mensajes reservados que también miden el rechazo. No contamina esa puerta, porque la regla solo actúa bajo el umbral y RF-17 y RF-18 de 069 no dependen de ella; sí hace optimista su propia cifra de cumplimiento, con solo 206 mensajes y un mínimo de 4 que llegan.
- RF-55 amplía 075:RF-39: si el modelo trae regla, `ninguna` en tercer lugar o más puede frenar la consulta. Sin regla, 075:RF-39 sigue igual.
- RF-7 limita lo que este proceso reserva; no reserva nada frente a otro proceso que ya ocupe la GPU. La web sigue con el codificador del modelo en uso cargado mientras se entrena.
- La memoria y el tiempo reales en la GPU no se han medido en esta fase: lo medido sin GPU está en el plan; lo demás lo dará RF-17 en la primera ejecución.
- Con 2 de 12 capas y 44 298 filas de entrenamiento, el afinado puede sobreajustar a las plantillas: la parada mira selección, no la sellada.
- Afinar no arregla etiquetas de plata erróneas ni frases que el operador escribe de un modo que nadie ha visto.
