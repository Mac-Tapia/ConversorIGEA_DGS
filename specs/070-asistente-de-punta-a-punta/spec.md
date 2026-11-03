# Spec 070 — El asistente opera el conversor de punta a punta

Estado: implementada

Rama de trabajo: `asistente/070`.
Cita: 026 (asistente), 027 (RF-19, RF-43, RF-44, RF-65), 028 (RF-21 a RF-31), 046 (RF-20 a RF-24), 047 (RF-11),
063 (RF-1 a RF-11), 067 (RF-20, RF-36 a RF-40), 068 (RF-28, RF-41), 069 (RF-13, RF-17 a RF-22).

## Por qué

El usuario, el 2026-11-02: «debe trabajar con el conversor, por ejemplo convertir los 101 alimentadores, convertir uno,
hacer la calibración, recalibración, buscar en base de datos, hacer la evaluación para el ingreso de carga nueva [...] este
asistente, por tener su equipo, para que haga todo lo que le pido, desde diagnósticos hasta los entregables». También:
«en serie», «no alucinen», y universal para cualquier distribuidora.

El catálogo tenía 29 tareas: ninguna consulta datos, calibra, recalibra, busca máximas ni trata por SET. Varias de las que
había no podían terminar: `estudios` no enviaba su base y `sistema_completo` no enviaba una opción obligatoria.
Lo que pide esta spec reutiliza rutas de la web; el asistente no tiene una vía propia (026:RF-10). Se prueba sin GPU ni
DIgSILENT en esta fase: lo que solo se comprueba allí queda en tareas `[DIgSILENT]` y en la del navegador.

## Requisitos

### Lo que las tareas existentes no resolvían

- RF-1: CUANDO se ejecuten los estudios, EL SISTEMA usará como base la última calibración aplicada del proyecto.
- RF-2: SI el proyecto no tiene calibración aplicada, ENTONCES EL SISTEMA dirá en el plan que falta, en vez de ofrecer confirmar.
- RF-3: EL SISTEMA elegirá los estudios del catálogo del espacio y del proyecto, que considera su libro y su licencia.
- RF-4: DONDE la orden nombre un estudio, EL SISTEMA correrá solo ese.
- RF-5: SI el estudio nombrado no se ofrece, ENTONCES EL SISTEMA dirá en el plan el motivo que da el catálogo.
- RF-6: CUANDO una tarea de punta a punta no traiga la carpeta de los libros, EL SISTEMA usará la de los libros de demanda del espacio.
- RF-7: SI no hay carpeta dada ni libros en el espacio, ENTONCES EL SISTEMA dirá en el plan que falta la carpeta.
- RF-8: SI al proyecto entero le falta un dato obligatorio, ENTONCES EL SISTEMA parará antes de su primera etapa, nombrándolo.
- RF-9: CUANDO se integren cargas nuevas en bloque, EL SISTEMA enviará como base la última calibración aplicada del proyecto, y sin ella lo dirá en el plan.
- RF-10: SI el formulario de factibilidad no trae la solicitud, ENTONCES EL SISTEMA dirá en el plan que falta.
- RF-11: SI la carga del informe de factibilidad no está aplicada o no se ingresó sola, ENTONCES EL SISTEMA dirá en el plan que se conecte con la tarea de una carga nueva sola.
- RF-12: CUANDO el informe de estudio nombre varios alimentadores, EL SISTEMA generará un informe por alimentador.
- RF-13: CUANDO las obras en escalera o la optimización traigan libro CAPEX o tipo de cambio, EL SISTEMA los enviará a su ruta.
- RF-14: SI el perfil y el tipo de cambio no bastan para costear, ENTONCES EL SISTEMA dirá en el plan el motivo.
- RF-15: SI se pide la SET nueva directa sin libro CAPEX, ENTONCES EL SISTEMA dirá en el plan que falta el libro.
- RF-16: EL SISTEMA dará los entregables de todos los pasos del plan, no solo los del último.

### Tareas nuevas

- RF-17: EL SISTEMA reconocerá los tipos de dato `set`, `estudio`, `alcance` y `anio`.
- RF-18: EL SISTEMA añadirá los tipos nuevos al final de la lista, para que los modelos heredados conserven el significado de sus etiquetas.
- RF-19: EL SISTEMA convertirá una SET sola por la ruta de conversión por sistema.
- RF-20: EL SISTEMA llevará de punta a punta uno o varios alimentadores por `tools/sistema_web.py --red`.
- RF-21: EL SISTEMA llevará de punta a punta una SET por `tools/sistema_web.py --set`.
- RF-22: EL SISTEMA buscará la máxima por alcance: coincidente en alimentadores, de barra en una SET y de 60 kV en un sistema.
- RF-23: EL SISTEMA cruzará los clientes de la máxima ya buscada, con su fecha cuando la haya.
- RF-24: EL SISTEMA calibrará un proyecto con la última máxima buscada, preparando el plan y aplicándolo.
- RF-25: EL SISTEMA simulará esa misma calibración, sin aplicarla.
- RF-26: EL SISTEMA recalibrará un proyecto con la misma función que la ruta de recalibrar, en el trabajo del asistente, cuyo carril ocupa esa ruta.
- RF-27: EL SISTEMA escaneará un proyecto por la ruta de escanear de la web.
- RF-28: EL SISTEMA verificará la convergencia por la ruta de verificar de la web.
- RF-29: EL SISTEMA conectará una carga nueva sola con el formulario de la ruta del plan de cargas, con la potencia, el factor de potencia y la ubicación de la orden.
- RF-30: SI a la carga sola le falta la potencia o la ubicación, ENTONCES EL SISTEMA dirá en el plan cuál, sin deducirla.
- RF-31: EL SISTEMA ofrecerá el proyecto entero como tarea, con la lista de sus etapas en el plan.
- RF-32: EL SISTEMA cancelará los trabajos en curso del espacio, nombrándolos en el plan.
- RF-33: MIENTRAS corra un trabajo del carril del asistente, EL SISTEMA admitirá la orden de cancelar y su confirmación.
- RF-34: EL SISTEMA leerá los PDF del solicitante de la ruta dada, por la ruta de documentos de la web.
- RF-35: EL SISTEMA preparará el ZIP de los resultados y dará el enlace de su descarga.
- RF-36: EL SISTEMA lanzará el pronóstico de la spec 046 con su clase, sus libros, su zona horaria y su cadencia, sin suponer ninguno.
- RF-37: CUANDO termine el pronóstico, EL SISTEMA dirá quién ganó en cada objetivo y por qué, si es la referencia, y que es un pronóstico y no una medición.
- RF-38: EL SISTEMA pedirá confirmación de toda tarea nueva que escriba, y ninguna se reanudará sola.
- RF-39: EL SISTEMA reconocerá por su frase literal las tareas que el modelo en uso no conoce.

### Consulta de datos

- RF-40: EL SISTEMA responderá a la consulta de datos sin escribir y sin abrir DIgSILENT.
- RF-41: EL SISTEMA consultará alimentadores, SED por alimentador, medidores, clientes fijos, máximas ya buscadas, años de medición, catálogo, variaciones escaneadas, proyectos y última calibración.
- RF-42: EL SISTEMA dará cada respuesta con la fuente de la que sale.
- RF-43: SI el dato no está, ENTONCES EL SISTEMA dirá «no lo encuentro» y qué hacer, sin un valor deducido.
- RF-44: SI lo pedido vivía en memoria y se perdió con un reinicio, ENTONCES EL SISTEMA dirá que se vuelva a buscar.
- RF-45: EL SISTEMA dará las SED de un alimentador por una ruta de lectura que use el modelo de ese alimentador, sin recorrer tablas enteras.
- RF-46: EL SISTEMA bloqueará en la búsqueda en internet lo que haya devuelto la consulta de datos.

### No disponible

- RF-47: CUANDO se pida cortocircuito, protecciones, optimización no lineal o un estudio no ofrecido, EL SISTEMA responderá que no está disponible y por qué.
- RF-48: EL SISTEMA sacará el motivo de un estudio de `estudios_no_ofrecidos`.
- RF-49: EL SISTEMA no ejecutará nada ni dará cifras en esa respuesta.

### Evaluar una carga nueva

- RF-50: EL SISTEMA encadenará diagnóstico, calibración si hace falta, carga, evaluación, obras si hacen falta e informe.
- RF-51: EL SISTEMA enseñará las etapas en el plan y las confirmará de una vez.
- RF-52: SI las etapas cambiaron desde que se mostraron, ENTONCES EL SISTEMA no las ejecutará.
- RF-53: DONDE el proyecto tenga calibración aplicada, EL SISTEMA omitirá la etapa de calibración y lo dirá.
- RF-54: DONDE la evaluación concluya factible sin obras, EL SISTEMA omitirá las obras y lo dirá.
- RF-55: EL SISTEMA generará el libro del informe solo si el perfil lo declara.
- RF-56: CUANDO la ejecución se corte, EL SISTEMA retomará solo con una nueva confirmación, sin repetir lo hecho.

### Reglas de dominio

- RF-57: SI una búsqueda coincidente lleva más de 3 alimentadores, ENTONCES EL SISTEMA la rechazará proponiendo SET o sistema.
- RF-58: SI una tarea por alimentadores pide más de 3, ENTONCES EL SISTEMA lo dirá en el plan proponiendo SET o sistema.
- RF-59: CUANDO se recalibre un proyecto de SET, EL SISTEMA conservará su criterio de barra.
- RF-60: EL SISTEMA buscará la máxima de una SET por barra y sin el instante común de 60 kV.
- RF-61: SI se pide calibrar el proyecto de transmisión del perfil, ENTONCES EL SISTEMA lo rechazará diciendo que no se calibra.

### La vía antigua de entrenamiento

- RF-62: CUANDO `tools/asistente_entrenar.py` se llame sin opciones de la vía antigua, EL SISTEMA tomará la vía gobernada por el registro.
- RF-63: EL SISTEMA no promoverá ningún modelo de órdenes sin el registro.
- RF-64: CUANDO se pida expresamente la vía antigua, EL SISTEMA correrá con el turno de la GPU y registrará la decisión.
- RF-65: EL SISTEMA quitará del entrenamiento los textos que estén en la prueba.
- RF-66: EL SISTEMA declarará la calidad de los datos en el manifiesto de lo que registre.

### Currículo y prueba

- RF-67: EL SISTEMA añadirá frases de entrenamiento con su origen marcado.
- RF-68: EL SISTEMA tendrá al menos cinco paráfrasis de entrenamiento distintas por tarea.
- RF-69: EL SISTEMA medirá los candidatos con una prueba sellada nueva de varias paráfrasis por tarea, generada de un modo declarado.
- RF-70: EL SISTEMA fijará la huella de esa prueba, independiente del vocabulario del espacio.
- RF-71: EL SISTEMA no llevará al entrenamiento, a la selección ni a la calibración ninguna familia de esa prueba.
- RF-72: EL SISTEMA medirá también la prueba anterior, con su huella intacta, como histórica sin decidir.
- RF-73: EL SISTEMA conservará las puertas de 0,95 y 0,85 por familia, de 0,98 y 0,95 humanas y de rechazo.
- RF-74: EL SISTEMA no etiquetará un pronóstico como reconstrucción del gemelo temporal.
- RF-75: EL SISTEMA dejará idénticas las huellas de las órdenes fijas.
- RF-76: EL SISTEMA dejará las órdenes confirmadas por el operador solo en la prueba, aunque un texto igual, sin contar mayúsculas ni tildes, estuviera como plata o en una plantilla.
- RF-77: EL SISTEMA permitirá preparar un solo modelo del catálogo con su revisión fija, para dejar en la caché de la web el codificador que lee el intérprete.

## Fuera de alcance

Entrenar; tocar pesos; bajar puertas; `arrancar_vigilancia` y el interruptor de autoentrenamiento; `digital_twin/oraculo.py`,
`optimizacion_oraculo.py`, `BloqueoGPU`; el código del pronóstico; deshacer cargas, obras manuales, libro de confiabilidad y
guiones como tareas; rellenar el formulario del informe desde el PDF, que sigue siendo del operador en la web (017:RF-137).

## Limitaciones declaradas

- El tope de 3 alimentadores es una regla del análisis decidida por el usuario, no un tamaño de la red: no contradice P2.
- 027:RF-65 pedía órdenes fijas de todas las tareas; las tareas nuevas no entran en ellas para conservar su huella (068:RF-41).
- La frase literal reconoce tareas nuevas mientras no haya modelo que las conozca; no las reconoce con cualquier redacción.
- El corpus sellado del ajuste generativo (047) sigue con las tareas de hasta la 069.
- Las etiquetas de plata de los textos reales (068) se pusieron con el catálogo anterior: alguna orden que hoy es de una tarea nueva puede enseñar la antigua. La prueba sellada es sintética: el 98 % de las humanas sigue midiéndose con solo las que haya confirmado el operador.
- La huella b800c6ca1a11d9ba incluía las 3 humanas de entonces. Con más órdenes confirmadas no se reproduce literalmente; lo comparable es la huella de sus filas sintéticas, y salen las que repitan el texto de una humana nueva (047:RF-11).
- El factor de potencia de una carga sola, si la orden no lo trae, es el que propone el formulario 3.2 (008:RF-27), y el plan lo dice.
