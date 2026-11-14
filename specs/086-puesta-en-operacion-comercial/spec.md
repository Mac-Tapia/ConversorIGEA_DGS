# Spec 086 — Puesta en operación comercial: versión 1.0 instalable, segura y probada de punta a punta

Estado: aprobada · Fecha: 2026-11-04 · Origen: petición del usuario; aprobada por el usuario: «esta aprobado el paln implementa». D1 a D7 siguen con la recomendación en lo reversible; D3 espera su orden

Cita: 002, 017, 025, 042, 047, 052, 055, 056, 058, 062, 065, 067, 072, 073, 077, 081, 083, 084, 085.

## Contexto y objetivo

Usuario: «has un plan de de tdo lo que falta y integarcion y listo para poner comnercial revsia bien profundo tdos el poeyecto y deja
lsito para implmentarlo todo». Cuatro revisiones de solo lectura sobre `f50146e8` (flujos, instalación y seguridad, universalidad, código y
modelos) dan la conclusión: el motor de ingeniería es sólido, pero **hoy es un árbol de desarrollo que corre en sitio, no un producto**.
Falta probar con el código final los flujos que se venderían, y faltan cosas que ninguna spec cubría: instalador, licencia, seguridad de la
web, durabilidad de los datos y separar lo que es de Electro Dunas.

El objetivo es una **versión 1.0** para una distribuidora, instalable en un equipo limpio, en la que cada flujo vendido se haya probado
en DIgSILENT real con el código congelado. Nada queda apagado: lo que aún no se ha probado en DIgSILENT se marca como beta, sin
retrasar la entrada (usuario, 2026-11-13).

## Alcance de la 1.0

Se vende: cargar fuente y convertir; importar con «Caso base» verificado; calibrar; cargas nuevas; «Con proyecto» con escalera; informes
de estudio y de factibilidad con su Excel; estudios de flujo, N-1 y transferencia.

Como beta, desactivable y dicho en pantalla: asistente de órdenes (provisional, con confirmación, 085), SET nueva (con revisión de un
ingeniero), diagnóstico y borrador F01–F15 del PIDE, confiabilidad.

También se entrega, activo: entrenar los modelos, el gemelo digital (PINN y GRU), el pronóstico por modelos, las mejoras y el ciclo de
aprendizaje continuo (050), la revisión por roles y las preguntas del asistente sobre el código (índice RAG 077). Lo que entrena o usa el
gemelo pide una GPU NVIDIA con CUDA y el complemento de IA (RF-37); ningún modelo pasa a uso sin sus puertas (071).

Motivo del cambio (usuario, 2026-11-13, confirmado con pregunta expresa del auditor): «nada debería estar apagado ni bloqueado». Hasta
entonces este apartado decía «No se entrega activo» de todo lo anterior, y la edición de producto negaba sus rutas y tareas. La edición
sigue decidiendo solo lo que es de seguridad: las salidas a la red, apagadas por defecto (RF-22), y que la web no admita el servidor de
desarrollo de Vite como origen.

## Decisiones del usuario que este plan pide

Se marcan con su recomendación; hasta que se respondan, el plan sigue con la recomendación en lo que es reversible.

- D1 Alcance geográfico. Recomendado: **solo Perú** en la 1.0 (60 Hz, soles y normas peruanas siguen en el perfil o como jurisdicción).
- D2 Modelo de venta. Recomendado: **puesto local por licencia**, un equipo por operador, sin servidor multiusuario.
- D3 Repositorio. Hoy el repositorio de GitHub es **público y sin licencia** (comprobado el 2026-11-04). Decidido por el usuario, 2026-11-04:
  **sigue público para recibir comentarios, y se puede usar y reutilizar**: licencia MIT desde el 2026-11-04 (`LICENSE`). La entrega al cliente sigue siendo la empaquetada (D4), y antes de cada push se revisa que no vayan
  datos de la distribuidora ni secretos.
- D4 Entrega. Recomendado: **empaquetada**, sin `tests/`, `specs/`, `.claude/` ni `.git`.
- D5 Comentarios con casos reales en el código entregado. Recomendado: **neutralizarlos en la línea de producto**, conservando el motivo
  sin el nombre del cliente. Choca con la regla de `CLAUDE.md` de citar el caso real.
- D6 Datos para las corridas: libro real de confiabilidad, fuente de «CA101 13», y qué hacer con PA217 en 025 T21 (es un proyecto vetado).
- D7 Asesoría legal: licencia comercial, DIgSILENT, datos de Osinergmin y Electro Dunas, modelos. **No es decisión técnica**: la revisión solo
  señala qué mirar.
- Decisiones del usuario del 2026-11-07 («de la B, haz todo según tu recomendación»): D1 **solo Perú** en la 1.0; D2 **puesto local
  por licencia**; D3 se mantiene (público, MIT); D4 **empaquetada**, sin `tests/`, `specs/`, `.claude/` ni `.git`; D5 los comentarios
  con casos reales se **neutralizan solo en el paquete entregado**, por un paso al empaquetar, y en el repositorio siguen citando el
  caso (`CLAUDE.md`); D6 el libro real de confiabilidad y la fuente de «CA101 13» los da el usuario (responsable: el usuario), y la
  025 T21 usa el PA217 del proyecto de prueba de Pisco, no el trabajado. D7 **no se considera** en la venta ni en otro uso: quien use
  el proyecto debe tener sus propias licencias (DIgSILENT, datos de las distribuidoras y de Osinergmin, modelos); el producto no las
  incluye ni las concede.

## Requisitos

### Datos que no se pierden

- RF-1: CUANDO se guarda un fichero de estado, EL SISTEMA lo sincronizará a disco antes de reemplazar el anterior.
- RF-2: SI `workspace.json` está dañado, ENTONCES EL SISTEMA mostrará el espacio como dañado con la opción de restaurar su copia anterior.
- RF-3: SI una entrada apunta a un fichero que no existe al cargar, ENTONCES EL SISTEMA la conservará marcada como no disponible.
- Aclaración de RF-3 (2026-11-13, auditoría c7): una entrada tampoco se pierde por una subida rechazada. Lo subido a una
  casilla, a un hueco de demanda, al libro de pérdidas o a los PDF del solicitante se guarda y se valida en un staging del
  espacio y se publica con `os.replace` solo si pasa; lo anterior se aparta y se retira después de asignar lo nuevo, y
  vuelve a su sitio si la asignación falla. MIENTRAS un trabajo del espacio pueda leer esos libros o PDF, la subida
  responde 409 sin tocar los guardados. Caso real: Osinergmin nombra igual el paquete VNR-GIS de cada ciclo, y una
  descarga cortada con ese nombre pisaba y después borraba el vigente, que la casilla seguía apuntando; los libros de
  demanda y los PDF se borraban antes de guardar los nuevos. Referencia: documentación de Python 3.12, `os.replace`
  («If successful, the renaming will be an atomic operation»; «may fail if src and dst are on different filesystems»,
  por eso el staging va en el propio espacio), https://docs.python.org/3.12/library/os.html#os.replace.
- RF-4: EL SISTEMA leerá la versión de `workspace.json` y lo migrará con copia previa, por pasos numerados.
- RF-5: SI `workspace.json` es de una versión futura, ENTONCES EL SISTEMA no lo sobrescribirá y lo dirá.
- RF-6: EL SISTEMA guardará las rutas de dentro del espacio relativas al espacio.
- RF-7: EL SISTEMA identificará la instalación con un identificador estable, independiente de la ruta.
- RF-8: CUANDO el destino está en otra unidad o en una ruta de red, EL SISTEMA publicará el resultado con un temporal junto al destino.
- RF-9: CUANDO se reinicia la web con trabajos a medias, EL SISTEMA los mostrará como interrumpidos, con su registro.
- RF-10: EL SISTEMA dará una orden de copia y otra de restauración de sus datos, con manifiesto.
- RF-47: SI la última copia supera la antigüedad configurada, ENTONCES EL SISTEMA lo avisará en la web.

### Informes veraces

- RF-11: EL SISTEMA ligará cada informe a la corrida que lo generó.
- RF-12: SI «Con proyecto» falla, agota su tiempo o se cancela, ENTONCES EL SISTEMA no usará un flujo anterior en el informe sin decirlo.
- RF-13: CUANDO se retoma una corrida, EL SISTEMA verificará el «Caso base» aunque no se importe de nuevo.
- RF-14: EL SISTEMA escribirá la huella del «Caso base» con la que 081 detecta que dejó de converger.

### Producto y seguridad

- RF-15: EL SISTEMA ofrecerá en la edición de producto los mismos entrenamientos, modelos, mejoras y ciclos de aprendizaje que en desarrollo.
- RF-16: EL SISTEMA marcará en la edición de producto las funciones en beta, activas por defecto y desactivables por el operador.
- Aclaración de RF-15 y RF-16 (usuario, 2026-11-13: «nada debería estar apagado ni bloqueado»): hasta esa fecha decían «no lanzará la
  suite de pruebas ni entrenamientos» y «ocultará lo que esté fuera del alcance de la 1.0»; la edición de producto ya no niega ninguna
  ruta ni tarea. La suite nocturna corre donde están sus pruebas: el programa instalado no trae `tests/` (D4), y entonces no se lanza ni
  se anota como interrumpida. Sin GPU CUDA, lo que la pide dice en palabras del operador qué falta, sin caer a la CPU ni dejar una traza
  en el Registro. Las mejoras del código (una rama con git y sus pruebas) quedan fuera del programa instalado, que no trae git ni el
  código fuente: allí avisan que solo funcionan en el entorno de desarrollo, sin error de git ni traza; entrenar y reentrenar siguen
  activos, y el reentreno automático va sin permiso de empezar (071:RF-6).
- RF-17: EL SISTEMA rechazará las peticiones cuyo `Host` no sea de su lista.
- RF-18: EL SISTEMA exigirá un `Origin` propio en las peticiones que cambian algo y en el WebSocket.
- RF-19: EL SISTEMA exigirá un token de la sesión, entregado por el lanzador, en toda la API.
- RF-20: SI se pide escuchar fuera de `127.0.0.1` sin usuarios ni TLS, ENTONCES EL SISTEMA se negará y dirá por qué.
- RF-21: EL SISTEMA servirá sus páginas con su propio Leaflet y con una política de contenido.
- RF-22: EL SISTEMA no saldrá a la red por defecto en la edición de producto, y cada salida se activará de forma explícita.
- RF-23: EL SISTEMA clasificará cada tarea del asistente por su efecto: lee, usa licencia, sale a la red o escribe.
- RF-24: CUANDO una tarea usa licencia o sale a la red, EL SISTEMA pedirá confirmación.
- RF-25: EL SISTEMA pedirá confirmación antes de ejecutar un guion guardado en un proyecto.
- RF-26: EL SISTEMA reintentará solo los trabajos declarados idempotentes.
- RF-27: SI un modelo temporal no tiene GPU disponible, ENTONCES EL SISTEMA seguirá el trabajo sin ese modelo y lo avisará, en vez de fallar.

### Universal

- RF-28: EL SISTEMA tomará del perfil la moneda de informes y pantallas.
- RF-29: EL SISTEMA no mostrará en la web nombres ni tensiones de una empresa concreta como ejemplo fijo.
- RF-30: EL SISTEMA validará el perfil con un esquema, con una orden que diga qué falta y qué función afecta.
- RF-31: DONDE la empresa no trae modelo de informe, EL SISTEMA generará el informe con una plantilla neutra y lo dirá.
- RF-32: EL SISTEMA entregará un perfil plantilla y otro ficticio, sin el de Electro Dunas.
- RF-33: EL SISTEMA comprobará en cada versión que lo entregado no contiene términos de una lista prohibida guardada fuera de git.
- RF-34: EL SISTEMA no entregará pesos entrenados con datos de otra empresa.
- RF-35: DONDE el perfil no define las bandas y la tensión nominal, EL SISTEMA las pedirá en vez de tomar valores de una empresa.

### Instalar y operar

- RF-36: EL SISTEMA se instalará en un Windows limpio sin Node, sin pytest y sin salida a internet.
- RF-37: EL SISTEMA dará un núcleo sin torch y un complemento de IA aparte.
- RF-38: EL SISTEMA separará programa y datos, y su actualización conservará los datos con copia previa y vuelta atrás.
- RF-39: EL SISTEMA verificará sus dependencias por huella al instalar y nunca instalará al arrancar.
- RF-40: EL SISTEMA dará una orden `doctor`, y una pantalla, que digan qué falta, qué función afecta y cómo arreglarlo.
- RF-41: EL SISTEMA escribirá su registro en ficheros rotativos.
- RF-42: EL SISTEMA dará una orden que reúna un paquete de soporte anonimizado.
- RF-43: EL SISTEMA tendrá una sola versión, mostrada en la web y con sus notas.
- RF-44: EL SISTEMA dará manuales de instalación y de operador, una hoja de seguridad y privacidad, y las licencias de terceros.

### Déficit previo

Usuario, 2026-11-04: «sigeu has cerrar», tras la opción recomendada. SI112 quedó a 0,945 p.u. con la obra aplicada, y PA217 a 0,925: la carga cumple, y un ramal existente sigue bajo el límite sin empeorar.

- RF-48: CUANDO una barra de un alimentador con obra queda bajo el límite sin empeorar frente a «Sin proyecto», EL SISTEMA la anotará como déficit previo con su barra y su tensión.
- RF-49: EL SISTEMA separará en el informe lo que causa la carga de lo que ya estaba fuera de límites.
- RF-50: SI queda un déficit previo, ENTONCES EL SISTEMA no dirá que el alimentador queda en norma.
- RF-52: SI un alimentador tiene una barra que ya estaba bajo el límite, con o sin obra para la carga, ENTONCES EL SISTEMA presentará una obra que la corrija, con su costo aparte del de la carga. Usuario (2026-11-04): «si existe barra que ya estaba baja se presenta obra».

### Factor de seguridad de la SET nueva

Usuario, 2026-11-04: «debe ser 1.25 si no se considera la tasa de crecimiento».

- RF-51: SI la potencia de diseño de la SET nueva no cuenta la tasa de crecimiento, ENTONCES EL SISTEMA usará `factor_seguridad_set_sin_tasa`; con la tasa, `factor_seguridad_set`.
- RF-53: CUANDO dimensiona un elevador o un regulador sin contar la tasa de crecimiento, EL SISTEMA usará también `factor_seguridad_set_sin_tasa`. Usuario (2026-11-04): «sí aplica, para regulador 1.25».
- RF-54: SI en Windows sustituir un fichero de estado falla porque otro proceso lo tiene abierto en ese instante (`PermissionError`), ENTONCES EL SISTEMA lo reintentará unas pocas veces, en menos de dos segundos, y solo después dará el error. (Suite completa del 2026-11-10: un trabajo de la web no se encoló una vez de 8 613 pruebas.)
- RF-55: SI el perfil de la empresa no trae las fichas de transformadores de SED o el tamaño de banco por tensión, ENTONCES el
  diagnóstico lo avisará con la función que afecta (calibrar un alimentador con una SED sobrecargada) y cómo completarlo, en
  vez de dar el perfil por bueno. (Programa instalado de prueba, 2026-11-11: sin perfil, CA101 no quedó válido y el
  diagnóstico decía «se puede leer».)
- RF-56: EL SISTEMA dejará cargar desde la web el perfil de la empresa y, si lo nombra, su estructura; lo validará como
  `validar-perfil` antes de escribir, no guardará nada si tiene errores, y si es bueno lo dejará en la carpeta de datos con
  copia del anterior. Usuario (2026-11-11): «debe usar todos los perfiles de la empresa, todos los libros deben cargar desde
  la web»; en el programa instalado el perfil hubo que dejarlo a mano.

### Defectos de la instalación del rc5 (2026-11-12)

Instalado y usado el rc5 en este equipo, como un operador: cuatro defectos sin prueba que los viera.

- RF-57: SI la instalación no puede terminar, ENTONCES EL SISTEMA dejará el motivo que da `instalar_candidato.py` en el
  registro del instalador y en el aviso al operador, también en una instalación silenciosa, y no solo su código de salida.
  (rc5: el registro decía «Resultado de instalar_candidato.py: 1»; el motivo era el programa abierto en el puerto 8765.)
- RF-58: SI la carpeta de una instalación anterior registrada está en la carpeta temporal de Windows o ya no tiene el
  programa, ENTONCES EL SISTEMA instalará en la carpeta por defecto y lo anotará en el registro; una actualización sobre
  una instalación válida seguirá en su carpeta, y la que se pida con `/DIR` manda. (rc5: se instaló en `%TEMP%\csgp`,
  la carpeta de un ensayo del rc1.)
- RF-59: CUANDO el perfil de la empresa se carga desde la web con éxito, EL SISTEMA pondrá al día, sin recargar la página,
  lo que se muestra del perfil: el CRS de origen enseña el del perfil y deja de avisar de que no hay perfil.
- RF-60: EL SISTEMA escribirá el nombre del programa de cálculo como «DIgSILENT» en la web, en el registro y en su
  código; «DigSILENT» y «DigSilent» son erratas.
- RF-61: CUANDO un texto armado une «a» o «de» con un nombre que empieza por el artículo «el», EL SISTEMA escribirá la
  contracción «al» o «del» («La salida al portal de Osinergmin»), nunca «a el» ni «de el».
- RF-62: CUANDO cambian los libros de demanda del espacio en «2.1 · Libros de medición», EL SISTEMA volverá a pedir al
  servidor lo que la recalibración de «Sin proyecto» deduce de ellos, sin recargar la página. (rc5: asignados los libros
  por ruta y calibrado, «Recalibrar» seguía diciendo «El espacio no tiene libros de demanda» hasta recargar.)

### Fondo de mapa: calles y satélite (2026-11-12)

Usuario (2026-11-12): ver la red sobre un plano «como en Google Maps», con «Calles + satélite». En la edición de producto la
salida de las teselas está apagada (RF-22) y solo se encendía con su variable al arrancar: el operador del programa instalado
veía la red sobre fondo blanco y no tenía cómo cambiarlo.

- RF-63: DONDE la salida de las teselas está encendida, EL SISTEMA dibujará la vista previa con dos fondos, calles
  (OpenStreetMap) y satélite (Esri World Imagery), cada uno con su atribución, y un selector de capas, con calles por defecto
  y la red siempre encima.
- RF-64: SI un fondo no carga, ENTONCES EL SISTEMA dirá en el mapa cuál no llegó, y la red se dibujará igual.
- RF-65: MIENTRAS la salida de las teselas está apagada, la vista previa no contendrá ninguna dirección de teselas, y el
  HTML seguirá llevando Leaflet dentro en los dos casos.
- RF-66: EL SISTEMA decidirá si una salida a la red está encendida por su variable de entorno; sin ella, por lo guardado en
  el equipo; sin nada de eso, por la edición.
- RF-67: EL SISTEMA dejará encender y apagar desde la web el fondo de mapa, lo recordará en la carpeta local de configuración
  del programa, fuera de git, y lo aplicará a las conversiones siguientes sin cambiar los mapas ya generados.
- RF-68: SI la variable de entorno fija la salida de las teselas, ENTONCES la web lo dirá y no dejará cambiarla.
- RF-69: EL SISTEMA dirá por la API cada salida a la red con su estado, su origen (variable, equipo o edición) y su destino;
  desde la web solo se podrá cambiar la de las teselas.

### Cada aviso en su paso (2026-11-12)

Usuario (2026-11-12): arriba de la web se apilaban «Aún no hay ninguna copia de sus datos…» y dos tarjetas «Trabajo
interrumpido: Cargar / listar alimentadores» (11:20:31 y 10:33:13): «estos mensajes deberían aparecer en el numeral que
corresponde de la web». Las dos interrupciones ya no valían: después el mismo «Cargar / listar» terminó bien. Amplía RF-9.

- RF-70: CUANDO un trabajo queda interrumpido, fallido o cancelado, EL SISTEMA mostrará su aviso en el paso de la web
  cuyo botón lo lanza, según una tabla de cada tipo de trabajo a su paso que está en un solo sitio.
- RF-71: SI un tipo de trabajo no tiene paso en esa tabla, ENTONCES EL SISTEMA mostrará su aviso en la zona general de
  arriba; ningún tipo que encola el servidor queda fuera de la tabla.
- RF-72: EL SISTEMA dará en cada aviso «Ver su registro» y «Dar por visto», y «Reintentar» solo si el trabajo se repite
  con sus mismos datos, sin más parámetro que el espacio; los avisos del mismo ámbito se dan por vistos juntos.
- RF-73: CUANDO después de un trabajo interrumpido, fallido o cancelado termina bien otro del mismo tipo y del mismo
  ámbito (el espacio y el proyecto o los alimentadores de su título), EL SISTEMA dará el aviso por resuelto y no lo
  mostrará; el trabajo seguirá en el registro del espacio.
- RF-74: EL SISTEMA dejará arriba solo los avisos generales del espacio (copia de datos, ficheros que no están,
  espacios dañados, datos del espacio), y el de la copia de datos y el de los ficheros irán en una línea que se
  despliega; la copia no tiene botón en la web, se hace con la orden del manual.
- RF-75: MIENTRAS el paso de un aviso está en una pestaña que se ofrece, la pestaña dirá cuántos avisos tiene; SI la
  pestaña no se ofrece, ENTONCES el aviso irá a la zona general.
- RF-76: CUANDO se optimiza «Con proyecto» en alimentadores marcados sin ninguna carga nueva aplicada, EL SISTEMA
  subirá la escalera de 098:RF-29 en cada uno que viole límites y aplicará la obra elegida; el que cumple quedará sin
  obras, sin reponer cargas ni consultar el oráculo de cargas. SI se pidieron cargas concretas y ninguna está
  aplicada, ENTONCES lo rechazará diciendo cuáles. (Electro Oriente NJA202, T32: 0,568 p.u. y ninguna obra ofrecida.)
- RF-77: MIENTRAS el proyecto elegido está calibrado, con alimentadores marcados y sin cargas nuevas integradas, la
  pestaña de DIgSILENT ofrecerá «Obras para el estado actual», con el tipo de cambio y el libro CAPEX, y mostrará su
  resultado diciendo que lo medido es el estado actual. SI en disco hay cargas nuevas aplicadas en los alimentadores
  marcados y el informe de su aplicación ya no está en la sesión (tras reiniciar la web), ENTONCES el bloque se llamará
  «Obras en «Con proyecto» con las cargas nuevas», las nombrará y su botón dirá «Proponer obras automáticamente»; el
  servidor ya las evalúa con esas cargas (CA101 con SECA001, 2026-11-13).

### La 1.0 instalada: manuales, una versión y vuelta atrás (2026-11-13)

Usuario (2026-11-13): los manuales se instalan con el programa, y la versión sale de un solo sitio. Auditor (2026-11-13): el rc5
de este equipo no tiene `anterior.txt`, y «volver atrás» no tiene a qué volver. En el rc5, el candidato iba a `{app}\_entrega` y
se borraba al terminar, con sus manuales; el paquete decía 1.0.0rc1 mientras el candidato se armó con `--version 1.0.0rc5` y el
instalador recibió `/DVersion` a mano; y «Acerca de» enseñaba las notas del rc1.

- RF-89: CUANDO se instala, EL SISTEMA dejará en la carpeta del programa, fuera de la carpeta de entrega que se borra al
  terminar, el manual de instalación, el de órdenes, la guía de prueba para una persona ajena y las notas de su publicación.
- RF-90: EL SISTEMA dará en el menú Inicio un acceso que abre el manual de instalación instalado.
- RF-91: SI al armar el candidato falta uno de los documentos que se instalan, ENTONCES EL SISTEMA no lo armará y dirá cuáles faltan.
- RF-92: EL SISTEMA escribirá su versión en un solo sitio, el paquete; pyproject, el candidato y el instalador la leerán de
  ahí, y el instalador rechazará que se le pase otra.
- RF-93: EL SISTEMA enseñará en «Acerca de» solo las notas de su propia versión; SI las notas del paquete no empiezan por el
  apartado de su versión, ENTONCES no se armará el candidato.
- RF-94: CUANDO se instala una versión sobre otra, EL SISTEMA registrará la que estaba como la anterior a la que volver,
  aunque esa versión no hubiera registrado ninguna.
- RF-95: SI el puntero de la versión instalada falta o nombra una versión sin su Python, ENTONCES EL SISTEMA tomará como la
  que estaba la versión instalada más reciente que conserve su Python, y no la retirará.
- RF-96: CUANDO termina una instalación, EL SISTEMA dejará en el registro del instalador a qué versión se puede volver, o que
  no queda ninguna.
- RF-97: SI una instalación no termina, ENTONCES EL SISTEMA dejará intactos los documentos de la versión que sigue instalada,
  sin restos de los nuevos; los nuevos solo sustituirán a los anteriores cuando la versión nueva quede como la que se usa.
  (Auditor, 2026-11-13: el instalador vaciaba y copiaba los documentos antes de saber si la instalación terminaba.)
- RF-98: CUANDO se vuelve atrás, EL SISTEMA pondrá a la vez la versión anterior como la que se usa y sus documentos como
  los del programa, y retirará los de la versión que se deja, cuyo programa se aparta sin borrarse. (Auditor, 2026-11-13:
  volver atrás dejaba los documentos de la versión nueva junto al programa anterior.)
- RF-99: EL SISTEMA guardará, aparte de los documentos de la versión que se usa, solo los de la versión a la que se puede
  volver, y ninguno cuando no haya a cuál volver.
- RF-100: SI no hay versión anterior, también tras volver atrás una vez o tras una instalación que no terminó, ENTONCES EL
  SISTEMA dirá que no hay a cuál volver y no cambiará nada; una instalación que no termina deja la versión, la anterior,
  la nota de la copia de datos y los documentos como estaban.
- RF-101: SI volver atrás falla a mitad, ENTONCES EL SISTEMA dejará la instalación exactamente como estaba.
- RF-102: CUANDO se instala una versión que está apartada en `versiones/` pero no es la que se usa, EL SISTEMA la volverá
  a poner en uso como en una actualización normal: la que se usa pasará a ser la anterior y sus documentos a
  `documentos.anterior`, los datos se copiarán como en cualquier actualización y no se borrará nada; «ya está» solo se dirá
  de la versión que se usa. (Integrador, 2026-11-13: tras volver atrás, reinstalar la versión nueva decía «ya está» y para
  volver a ella había que desinstalar.)
- RF-103: SI al deshacer un cambio de versión que no terminó falla uno de sus pasos, ENTONCES EL SISTEMA seguirá con los
  demás, informará del fallo original con los pasos que no pudo deshacer anotados y dejará en el registro qué quedó a
  medias y cómo arreglarlo a mano, con sus rutas. (Auditor, 2026-11-13: el fallo de un paso del deshacer tapaba el
  original y dejaba sin deshacer los siguientes, el estado mezclado que RF-97 y RF-98 impiden.)
- RF-104: SI Windows no deja renombrar una carpeta de documentos o un puntero de versión porque están en uso, ENTONCES EL SISTEMA lo
  reintentará unas pocas veces, con una espera creciente y acotada a unos segundos, y si sigue sin poder deshará el cambio
  y pedirá que se cierren los documentos de ConverterSmartGrid abiertos (manual, notas) antes de volver a intentarlo.
  (Auditor, 2026-11-13: `os.replace` de una carpeta falla con WinError 32 o 5 si un visor, Defender u OneDrive o Drive
  tienen un fichero abierto; CPython lo da como `PermissionError`. La documentación de `os.replace` solo promete el
  cambio atómico como requisito POSIX: https://docs.python.org/3.12/library/os.html#os.replace; los códigos, en
  https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-; pip reintenta igual
  `os.replace`, en https://github.com/pypa/pip/blob/26.2.1/src/pip/_internal/utils/filesystem.py.)
- RF-105: SI no se puede borrar una carpeta de paso de los documentos (`documentos.retirar`, `documentos.preparando` o
  `documentos.anterior`), o una versión vieja de `versiones/` al retirarla, ENTONCES EL SISTEMA no fallará por ello, pero lo dirá con su ruta en el registro del instalador.
  (Auditor, 2026-11-13: `shutil.rmtree(..., ignore_errors=True)` lo callaba y la carpeta se quedaba sin que nadie lo
  supiera.)

### Copia de los datos sin duplicados, a un destino que sincroniza (2026-11-12)

La web avisaba «Aún no hay ninguna copia de sus datos». La orden `tools/copia_datos.py crear` iba a escribir unos 95 GB
de unos datos que ocupaban unos 21 en el disco: el paquete VNR-GIS `ELOR25_V2` (5,4 GB) estaba en once ejecuciones de
`output/web` y en su original como enlaces duros de un solo fichero físico, y lo mismo `BASE JUL25 1.mdb` y los TXT. El
destino del usuario es Google Drive (`G:\Mi unidad\ConverterSmartGrid\copias_de_datos\`), con unos 41 GB libres, sin
enlaces duros y que bloquea un fichero mientras lo sincroniza. Amplía RF-10 y RF-47.

- RF-78: CUANDO se crea una copia, EL SISTEMA guardará cada fichero físico una vez: los nombres de un mismo fichero
  (enlaces duros) y los ficheros distintos con la misma huella SHA-256 ocuparán en la copia lo que uno.
- RF-79: EL SISTEMA anotará en el manifiesto todos los nombres de cada fichero guardado, con su huella, y seguirá
  verificando y restaurando igual las copias de un manifiesto de versión anterior.
- RF-80: CUANDO se restaura una copia, EL SISTEMA recreará todos los nombres de cada fichero: los que eran enlaces duros
  de un mismo fichero, como enlace duro del primero si el destino lo admite, y los demás nombres, como copia con su
  huella comprobada. Dos ficheros distintos con el mismo contenido (dos registros vacíos que crecen por separado)
  vuelven separados, como hace `rsync -H`, que solo enlaza lo que ya era un enlace en el origen.
- RF-81: SI una escritura en el destino falla por un bloqueo (la sincronización de Google Drive o de OneDrive),
  ENTONCES EL SISTEMA la repetirá con espera creciente y, si sigue fallando, anotará el fichero como error de la copia.
- RF-82: CUANDO se pide una copia, EL SISTEMA dirá antes de escribir nada cuántos bytes físicos únicos ocupará y cuánto
  espacio libre hay en el destino.
- RF-83: SI la copia no cabe en el destino, ENTONCES EL SISTEMA no la empezará y lo dirá con las dos cifras.
- RF-84: SI una copia se cancela o falla a medias, ENTONCES EL SISTEMA retirará su carpeta `.parcial`, con los mismos
  reintentos de RF-81, y no dejará ninguna carpeta con el nombre de una copia buena.
- RF-85: DONDE el aviso de la copia de datos se muestra, EL SISTEMA ofrecerá «Hacer una copia ahora», que pide la
  carpeta destino y la recuerda en el equipo.
- RF-86: EL SISTEMA hará la copia de la web como un trabajo con progreso y cancelación, no la empezará con otros
  trabajos en curso y no admitirá otro trabajo mientras copia, tampoco los que se encolan sin la ruta de la web
  (VNR-GIS, los reintentos de la vigilancia).
- Aclaración de RF-86 (2026-11-13, auditoría c7): borrar un espacio comprueba sus trabajos y lo borra bajo el mismo
  cerrojo con que la web encola, y un trabajo no se admite sobre un espacio que se borró mientras se encolaba (404);
  reemplazar libros o PDF guardados (aclaración de RF-3) va bajo ese cerrojo. Antes, otro clic encolaba un trabajo
  entre «no hay trabajos» y el borrado, y el borrado le quitaba la carpeta en marcha.
- Aclaración de RF-74 (2026-11-12): la copia ya tiene botón en la web (RF-85); la orden del manual sigue sirviendo.

### Variaciones y casos del conversor por su marca, también en una copia del proyecto (2026-11-12)

En la copia PRUEBA064_184942 de PA217, la calibración buscaba `Fichas_PRUEBA064_184942` y, al no hallarla, creaba otra
junto a la `Fichas_<original>` que traía la copia; la restitución de la 064 no la deshacía en «Con proyecto». Y, como
«Cargas nuevas» solo se rehace al insertar una carga (025:RF-79), al recalibrar se quedó con la fuente a 1,025 p.u.
mientras los demás casos pasaban a 1,0278.

- RF-87: CUANDO la calibración graba fichas de conductores o transformadores en un proyecto que ya trae una variación
  del conversor con ese prefijo (`Fichas_`, `SED_NTP_`), EL SISTEMA grabará en ella aunque su nombre sea el de otro
  proyecto, y creará la del proyecto solo si no hay ninguna. La reconocerá por la marca del conversor en su
  descripción, que pone al crearla o al reutilizarla, y, en las creadas antes de la marca, por la etapa que crea el
  conversor (`Etapa_fichas`, `Etapa_sed_ntp`); nunca solo por el prefijo. SI una variación con ese prefijo no es del
  conversor, ENTONCES no la tocará y lo avisará; SI hay más de una del conversor, ENTONCES no elegirá ninguna, lo
  avisará y grabará en la del proyecto.
- RF-88: CUANDO la calibración fija la consigna de la fuente, EL SISTEMA la fijará también en el caso «Cargas nuevas»
  del sistema de ese año, hallado por su nombre y su marca, y seguirá sin error si ese caso no existe.

### Aceptación

- RF-45: CUANDO se congela un candidato, cada flujo vendido tendrá evidencia en DIgSILENT, por la web y ligada a esa revisión, antes de aceptarlo.
- RF-46: La 1.0 se aceptará en un equipo limpio, con una empresa distinta de Electro Dunas y con un corte de luz simulado a media corrida.
- Aclaración de RF-46 (usuario, 2026-11-04: «haslo todo con este local; para otro local o usuario se debe dejar un manual»): la aceptación se hace en este equipo, con su DIgSILENT y por turnos, instalando con el `setup.exe` en un entorno sin nada de desarrollo. No demuestra lo que dependa de lo que este Windows ya tiene: el manual de instalación explica cómo llevarlo a otro equipo o usuario, y el primer cliente se acompaña.

## Fuera de alcance

Multiusuario en servidor, firma de código si D2 no la exige, otros países, cortocircuito y protecciones (049, que no existen y hay que
declararlo al cliente), mover los módulos a sus capas (002 T7 y T9), MADRL (074), aprendizaje continuo con datos reales (050), QLoRA (047 T7),
PINN (045 T3), optimización mixta (048), 072 T3 y T9, 027 T11 y T26, 071 T5.
