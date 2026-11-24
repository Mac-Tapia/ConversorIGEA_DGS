# Spec 070 — El asistente opera el conversor de punta a punta

Estado: aprobada (2026-11-19: RF-90 y RF-91, contexto defensivo frente a instrucciones escondidas en documentos, T26; 2026-11-18: RF-87, esperas finitas del asistente, T23; 2026-11-16: RF-79 a RF-86, el asistente cubre las specs 107 a 112, T16 a T22; 2026-11-15: 070:RF-78 v2, T14 por grupos de módulos; antes implementada)

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
- Aclaración de RF-51 (usuario, 2026-11-14: en la web, ninguna cita de RF ni jerga): lo que el plan enseña al operador
  (etapas, faltantes, dudas, razonamiento y avisos) no lleva citas de requisitos, specs ni tareas, ni claves internas;
  la cita va en el comentario del código y en el registro.
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
- Aclaración de RF-69 (2026-11-13): la medida de la sellada que decide se guarda también en su propio bloque
  (`prueba_sellada_079.medida`), en el informe y en el registro, como la anterior en `prueba_sellada.medida`, y las cifras
  del registro la leen de ahí; antes solo estaba en `sinteticas`, y el cierre de T11 no la encontraba con su huella.
- RF-70: EL SISTEMA fijará la huella de esa prueba, independiente del vocabulario del espacio.
- RF-71: EL SISTEMA no llevará al entrenamiento, a la selección ni a la calibración ninguna familia de esa prueba.
- RF-72: EL SISTEMA medirá también la prueba anterior, con su huella intacta, como histórica sin decidir.
- RF-73: EL SISTEMA conservará las puertas de 0,95 y 0,85 por familia, de 0,98 y 0,95 humanas y de rechazo.
- RF-74: EL SISTEMA no etiquetará un pronóstico como reconstrucción del gemelo temporal.
- RF-75: EL SISTEMA dejará idénticas las huellas de las órdenes fijas.
- RF-76: EL SISTEMA dejará las órdenes confirmadas por el operador solo en la prueba, aunque un texto igual, sin contar mayúsculas ni tildes, estuviera como plata o en una plantilla.
- RF-77: EL SISTEMA permitirá preparar un solo modelo del catálogo con su revisión fija, para dejar en la caché de la web el codificador que lee el intérprete.
- RF-78: EL SISTEMA no enseñará al operador citas internas: ni los mensajes de error que llegan a la web (los de
  `UserError` y el `detail` de `HTTPException`) ni los textos que pinta la web (texto, títulos y cadenas de
  `frontend/src/**/*.tsx`) llevarán «RF-n», el código de una spec entre paréntesis ni una tarea con su spec. Los
  comentarios y los docstrings sí pueden citarlos. Amplía a toda la web la aclaración de RF-51 (usuario, 2026-11-14: «en
  la web, ninguna cita de RF ni jerga»); en el navegador real salía «… conviértalos e impórtelos antes (028:RF-23).»
  (auditor 0d, 2026-11-15).
  Aclaración de RF-78 (v2, 2026-11-15): también los avisos y los mensajes que no son excepciones y que la web o el informe
  enseñan: lo que se añade a una lista de avisos y los valores de `mensaje`, `aviso`, `avisos`, `motivo`, `nota` y `texto`.
  Se limpia por grupos de módulos (tarjetas v2a, v2b…), y la prueba recorre los ya limpios hasta cubrir `src/` entero. Lo de
  la spec 107 (`src/convertersmartgrid/dominio/pit/`) lo limpia su dueño.
  Aclaración de RF-78 (v3, auditor 0d, 2026-11-15): también el texto de toda excepción de `src/` (`raise X('…')` para
  cualquier X, porque la web enseña el mensaje del trabajo que cae), lo que un guion de `tools/` escribe en su salida
  (`print`) o en sus avisos, y el texto que se arma antes en una variable de la misma función. Lo que el análisis estático
  siga sin ver lo cubre el navegador: cada recorrido de Playwright busca «RF-», «T<n>» y «(NNN:» en el texto visible con
  la función común `D:/csg/PM_IMPL/navegador_comun/sin_citas.py` y falla si aparece; los «T<n>» del dominio que pueden
  verse (nombres de transformador) van en su lista explícita, cada uno con su motivo. Y ningún código decide por una cita
  dentro de un texto (`'051:RF-9' in aviso`): al quitar las citas, esa condición dejaría de cumplirse sin avisar.

### El asistente cubre las specs 107 a 112 (2026-11-16)

Orden del usuario del 2026-11-16: «el asistente debe hacer todo el conversor», también la nube y el correo. Hasta hoy
no tenía ninguna tarea del PIT, del VAD, del plano, de los benchmarks, de la nube ni del correo, y las rutas de la nube
le estaban cerradas aunque el operador confirmara.

- RF-79: EL SISTEMA dará al asistente una tarea por cada función de la web de las specs 107 a 112: el diagnóstico, las
  alternativas y el expediente del PIT; el armado de la empresa modelo del VAD; abrir o cerrar una maniobra en una
  variación del plano y estudiarla; generar un benchmark anonimizado; enviar un informe por correo; e importar,
  publicar y compartir en la nube y conectar una cuenta.
- RF-80: CUANDO el asistente prepare un envío de correo, una publicación, un compartir, una importación o una conexión,
  EL SISTEMA lo dejará en el panel del asistente con lo exacto que saldrá (cuenta, destinatarios, ficheros con su
  huella, firma y validez del estudio) y un botón para confirmarlo.
- RF-81: EL SISTEMA solo enviará, publicará, compartirá, importará o conectará cuando el operador pulse ese botón en la
  web: la petición sale del navegador por la ruta de siempre, con su firma, y ninguna petición del ejecutor del
  asistente lo hace (109:RF-15, 110:RF-5, 110:RF-6).
- RF-82: CUANDO el operador confirme en el panel, EL SISTEMA seguirá el trabajo hasta su recibo y lo dirá en la
  conversación; un envío de estado desconocido se resuelve como en la ventana del correo (110:RF-9).
- RF-83: EL SISTEMA solo preparará esas acciones desde una orden escrita por el operador; un documento importado, aunque
  diga «envía» o «publica», no prepara ninguna.
- RF-84: MIENTRAS el modelo de órdenes en uso no conozca una tarea nueva, EL SISTEMA la reconocerá por su frase literal.
- RF-85: EL SISTEMA medirá las tareas nuevas en una prueba sellada nueva con su huella, y la anterior seguirá como
  histórica, como en la T8.
- RF-86: EL SISTEMA dará al estudio de costos del VAD rutas de la web para crear el estudio y armar la empresa modelo
  como trabajo en cola, con progreso y cancelación, y las mismas rutas servirán a la web y al asistente (P5, P7).
- RF-87: (diagnóstico del 2026-11-18, H03, tarjeta C2) EL SISTEMA hará que el asistente nunca espere sin fin a la web:
  cada petición llevará su límite de espera; un trabajo «interrumpido» (096) terminará la espera y su paso fallará con
  ese motivo; la espera de un trabajo tendrá un plazo total; y SI la web no responde varias veces seguidas, ENTONCES el
  asistente lo dirá y dejará de esperar, sin cancelar ni tocar el trabajo en la web.
- RF-88: (amplía RF-87; revisión de 1d del 2026-11-18) SI una petición del asistente a la web no recibe respuesta a
  tiempo o pierde la conexión, ENTONCES EL SISTEMA la dará por un paso fallido con su motivo en español (la ruta, el
  plazo y la causa), nunca como la excepción de la biblioteca de red, y la espera de un trabajo la seguirá contando como
  un fallo pasajero de RF-87. Las rutas que responden al terminar y no encolan (cargar la fuente, preparar los planes de
  cargas y de estudios, regenerar una norma, que espera su generador hasta 1800 s) llevarán su propio plazo, mayor que
  ese tope.
- RF-89: (pedido de c2 tras la e2e de 111-T16, 2026-11-18) SI la variable `CSG_ASISTENTE_OLLAMA` vale «0», ENTONCES el
  cliente de Ollama no abrirá ninguna conexión y la orden seguirá por la vía compatible, como con Ollama apagado; sin la
  variable, nada cambia. Las configuraciones de las pruebas de navegador la ponen cuando corren sin modelo, para que la
  web de prueba no cargue el modelo en la máquina en medio de una e2e.
- RF-90: (tarjeta MEJ-070-INYECCION, 2026-11-19; Plan Maestro PM-19, PM-23 y §10.7) EL SISTEMA ejecutará un plan que
  espera al operador (escribe, usa la licencia, sale a la red o lleva el aviso de RF-91) solo tras el clic del operador
  en la ruta de confirmación, de un solo uso, diga lo que diga el intérprete: el servicio que ejecuta lo exige aunque lo
  llame otra vía, y SI la confirmación llega con el token de la web o un `Bearer` (un programa), ENTONCES la ruta la
  rechazará con 403. La barrera está en el código (catálogo, plan, gobierno del equipo, rutas), no en el modelo.
- RF-91: SI la orden trae texto que da instrucciones al asistente (un documento pegado que dice «ignora lo anterior»,
  «omite las verificaciones», «sin pedir confirmación», «ignore previous instructions»), ENTONCES EL SISTEMA lo tratará
  como dato del documento, lo dirá en la propuesta con el trozo citado, y el plan esperará al operador aunque su tarea
  solo lea o solo prepare un envío; la tarea y sus efectos siguen saliendo del catálogo, nunca del texto.
- RF-92: (070 T22, 2026-11-24: el modelo en uso prov-8fd8a405 conoce 49 tareas y el contrato tiene 68; el código lo
  daba por «contrato de tareas o entidades incompatible», el asistente quedaba sin modelo de órdenes y la no regresión
  del candidato no se podía medir) SI el modelo de órdenes guardado conoce solo una parte de las tareas del contrato,
  sin ninguna que el contrato ya no tenga, y las mismas entidades, ENTONCES EL SISTEMA lo abrirá y predecirá con sus
  propias tareas (las nuevas, por RF-84), y la no regresión del candidato lo comparará en las mismas órdenes humanas.
  SI le falta al contrato alguna de sus tareas o cambian las entidades, ENTONCES seguirá incompatible.
- RF-93: (070 T28, 2026-11-24: el candidato de la T22 confundía tareas vecinas ante frases que no había visto) EL SISTEMA
  entrenará el intérprete también con paráfrasis de las tareas vecinas que la selección y la calibración dieron flojas o
  confundidas, cada una con la pista que la separa de su vecina, solo en entrenamiento y con su origen y su maestro; una
  que coincida por texto, por familia o por la familia ancha de la 075 con lo que mide no entra. La comprobación de fugas
  hacia las pruebas selladas contará también todas las paráfrasis que solo entrenan.
- RF-94: (070 T28, 2026-11-24: la guardia cortó la corrida con 0,85 GiB libres; la caché del prefijo ocupaba 2,75 GiB del
  proceso) MIENTRAS se afine el intérprete en una corrida, EL SISTEMA guardará los estados congelados de cada frase en
  ficheros de la corrida, con los mismos valores bit a bit, y los leerá por lotes, de modo que no ocupen la memoria del
  proceso; el largo y los tramos de cada frase seguirán en la memoria, y al soltar la caché se borrarán sus ficheros, que
  no se copian a Drive.

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
- El aviso de RF-91 reconoce las instrucciones por su forma (frases en español e inglés); una redacción que no reconoce no lleva aviso, y la protege igual RF-90: lo que escribe o envía espera el clic del operador.
- El factor de potencia de una carga sola, si la orden no lo trae, es el que propone el formulario 3.2 (008:RF-27), y el plan lo dice.
