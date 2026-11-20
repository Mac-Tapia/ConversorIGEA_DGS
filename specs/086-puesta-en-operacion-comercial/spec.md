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
- Decisiones del usuario del 2026-11-14, para el lanzamiento (auditoría de lanzamiento de c7):
  - U1 La entrega se usa con una **licencia comercial por puesto** (uso por equipo, sin redistribución, con garantía y limitación de
    responsabilidad), en español; el instalador la muestra y pide aceptarla; el texto final lo revisa un abogado. La MIT del
    repositorio (D3) no va en la entrega. Cambia D7 solo en esto: el producto da su propia licencia de uso, no las de terceros.
    **Sustituida el 2026-11-15 por LIC-MIT** (véase la aclaración de RF-44 de esa fecha).
  - U2 **Firma de código** con un certificado OV o un servicio de firma en la nube; el certificado nunca va en git y su trámite es del
    usuario. Un candidato final sin firmar no se entrega; uno de prueba lo avisa. Sustituye a «firma de código si D2 no la exige» de
    «Fuera de alcance».
  - U3 El Python del programa es el **3.12 oficial de python.org**, el último 3.12 con binarios de Windows que carga la API de
    DIgSILENT (3.12.10), firmado por la PSF, en lugar del 3.12.16 compilado aquí; su firma se comprueba al armar.
  - U4 **Entrega directa** (correo o enlace privado): instalador, complemento, notas, licencias y `SHA256SUMS`, que genera una
    herramienta al construir. Las 1.0.x van por el mismo canal, con 12 meses de soporte por versión.
  - U5 La lista local de términos de las dos empresas la propone a3 fuera de git y la aprueba el usuario.
  - U6 Windows 10 solo se declara con evidencia: «Windows 11 probado; Windows 10 sin probar».
  - U7 Instalación silenciosa **por usuario**, documentada; la instalación por equipo queda para después de la 1.0.
  - U8 `MANUAL_DE_USO` se entrega solo si cubre la 1.0 tal como queda.

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
- RF-19: EL SISTEMA exigirá un token de la sesión, entregado por el lanzador, en toda la API, y ningún registro ni el almacén
  de órdenes del asistente guardará ese token ni otra credencial, venga en el mensaje o en sus argumentos.
- RF-20: SI se pide escuchar fuera de `127.0.0.1` sin usuarios ni TLS, ENTONCES EL SISTEMA se negará y dirá por qué.
- RF-21: EL SISTEMA servirá sus páginas con su propio Leaflet y con una política de contenido.
  Ampliada (revisión en pantalla, 2026-11-14): las páginas generadas que la propia web enseña en un marco (el mapa de las
  cargas nuevas y la vista previa) se dejarán enmarcar solo por la web; todo lo demás, por nadie.
  Aclaración de RF-21 (revisión en navegador real, 2026-11-15): «la web» es el mismo origen (`X-Frame-Options: SAMEORIGIN` y
  `frame-ancestors 'self'`), y «por nadie», `DENY` y `frame-ancestors 'none'`. Lo decide la puerta en TODA respuesta, no la
  ruta: se cambian las cabeceras de marco que traiga. Las rutas que se dejan enmarcar van en una lista explícita, por su
  plantilla, y solo cuando responden una página HTML aislada (`sandbox`) que no es descarga; un error (JSON), una descarga
  (`attachment`) o una página sin `sandbox` de esas mismas rutas, lo que rechaza la puerta (401 y 403) y la entrada con el
  enlace del lanzador (303) llevan `DENY`. La política de esas páginas nombra cada servidor de teselas, sin comodín, y la hoja
  de seguridad dice qué se enmarca y a qué servidores se piden las teselas. La tarjeta MAPA-IFRAME lo proponía como un
  requisito aparte; queda aquí, como ampliación de este, sin número nuevo.
- RF-22: EL SISTEMA no saldrá a la red por defecto en la edición de producto, y cada salida se activará de forma explícita.
  Una salida cuyo destino da el usuario o el perfil (ArcGIS, OSRM) irá solo a un servidor público por http o https, comprobado
  tras resolver el nombre, y no seguirá una redirección a otra máquina (ArcGIS, solo al mismo servidor, según la
  aclaración de abajo; OSRM, ninguna); la propia máquina, el enlace local y lo reservado nunca se consultan, y
  la red privada solo con un permiso expreso de intranet. La conexión irá a la IP que se validó, con el nombre original para
  TLS y para `Host`, aunque el DNS responda otra al conectar (rebinding).
- Aclaración de RF-22 (2026-11-15, SSRF-ARCGIS; hallazgo BP-29 del Plan Maestro, seguridad P0): una salida encendida no sigue una
  redirección a otra máquina. El conector ArcGIS y el descubrimiento y la descarga del VNR-GIS oficial piden con
  `salidas_red.get_sin_redireccion_ajena`, que mira cada salto ANTES de pedirlo: ArcGIS, solo el mismo servidor (host, puerto y
  esquema, sin bajar de https a http); el portal oficial, solo sus hosts. Antes se seguía la redirección y se miraba la URL final,
  cuando 127.0.0.1, el servicio de metadatos de la nube u otra máquina ya habían recibido la petición. Una redirección rechazada
  no se reintenta. Desde el rebase de H8H5 (2026-11-16), cada salto que se sigue va también a la IP
  validada.
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
- Aclaración de RF-33 (auditoría de lanzamiento, 2026-11-14): el candidato **final** sin la lista local no se arma ni se da por
  comprobado (es un error, no un aviso); uno de prueba lo avisa. Las huellas en git cubren las siglas, paquetes, corpus, códigos de
  alimentador y sistemas de cada distribuidora con la que se trabajó, un término partido por un salto de línea cuenta, y al
  neutralizar un comentario (D5) se quitan también las cifras de su línea. El rc6 llevaba comentarios con códigos y cifras de la red
  de otra distribuidora.
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
- Aclaración de RF-44 (2026-11-14, U1 a U8): la entrega lleva además la licencia comercial por puesto, el resultado de `pip-audit`
  del lock y, aparte, `SHA256SUMS`; no lleva la MIT del repositorio, ni la parte de construir del manual de instalación, ni
  documentos de desarrollo o de la aceptación interna. Los requisitos del manual dicen lo probado: Windows 11 probado y 10 sin
  probar, PowerFactory 2024 real y 2021 a 2023 y 2025 con simulación, Excel o WPS por COM, memoria, GPU, VRAM, controlador y disco
  del complemento, y la instalación silenciosa por usuario.
- Aclaración de RF-44 (2026-11-15, LIC-MIT; decisión del usuario «MIT + comercial opcional»; sustituye a U1): la licencia del
  programa que se entrega es la MIT del repositorio (D3): va a «documentos/» como `LICENSE.txt` y el instalador la muestra y pide
  aceptarla. El acuerdo comercial (`LICENCIA_COMERCIAL.txt`) pasa a ser un documento OPCIONAL de soporte y garantía: se copia si
  está, no es condición de la entrega ni del uso y no restringe la MIT. Quedan fuera de la 1.0, por orden del usuario (open source
  con datos publicados): la revisión del texto por un abogado, la cláusula de ley y jurisdicción y el certificado de firma de
  código.
- Aclaración de RF-39 (2026-11-14, L5 y U3): el candidato final se arma con el Python oficial fijado, con su SHA-256 y la firma de la
  PSF comprobadas, y con `pip-audit` del lock sin vulnerabilidades sin justificar, desde un entorno aparte del de desarrollo.

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
- Aclaración de RF-89 (auditoría de lanzamiento, 2026-11-14): el manual de órdenes que se instala es el del programa instalado
  (`MANUAL_ORDENES.md`), solo con lo que se entrega; el de comandos es de desarrollo, y la guía de la persona ajena es material de la
  aceptación interna (T41): no se instalan.
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
- RF-106: EL SISTEMA dará a las pestañas, a los grupos de opciones y al separador del Registro su semántica ARIA, foco
  visible y manejo por teclado (flechas, Inicio, Fin e Intro), una alternativa de una sola pulsación a cada arrastre,
  objetivos de al menos 24 px y contraste AA en los temas claro y oscuro, y comunicará cada estado con texto o icono
  además del color (WCAG 2.2 AA; Plan Maestro V1, F-11; T0c, 2026-11-14).
- RF-107: CUANDO se publique un candidato, EL SISTEMA habrá recorrido en un navegador real F01 (VNR), F02 (simulación sobre
  el plano), F03 (planificación) y F04 (asistente) sobre una web aislada y sin red, con axe-core sin infracciones graves ni
  críticas de WCAG 2.2 AA, y guardará las capturas y el resultado por SHA (Plan Maestro V1, F-12; T0c, 2026-11-14).
  La web aislada guarda también sus espacios en su carpeta temporal; un recorrido omitido, en «fixme», inestable o sin
  correr no cuenta como recorrido y deja la corrida en fallo, y el que aún no puede correr no se recoge, con su motivo
  (E2E-AISLADO, 2026-11-17). F02 es `frontend/e2e/plano.spec.ts`, en el arnés de la 111 (111 T16).
- RF-111: CUANDO se busquen los términos prohibidos en lo que se entrega, EL SISTEMA calculará las sales de las huellas una
  vez por cambio de la lista, y no en cada ventana de palabras.
  (INST-RUEDA, 2026-11-15: al preparar la rueda, el conjunto ordenado de las sales se construía 1,8 millones de veces,
  8 de 66 s con el perfilador. La caída de memoria al construir e instalar la rueda no es suya: medida fuera de pytest,
  la construcción no pasa de 0,28 GiB y pip, de 0,05 GiB; lo demás lo toman a la vez el antivirus y otras sesiones.)

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

### La copia de la web, con previa y con las copias del destino (2026-11-16)

Prueba en el navegador real con la cuenta local del usuario (`D:/csg/PM_IMPL/PRUEBA-CUENTA-LOCAL/INFORME.md`):
«Hacer una copia ahora» escribía unos 20 GB en Google Drive con un clic, sin decir antes lo que ocuparía ni ofrecer
«Cancelar»; las cifras de RF-82 solo salían en el Registro del trabajo ya lanzado. Y el aviso decía «Aún no hay ninguna
copia de sus datos» con una copia de 19,8 GB y manifiesto válido en la carpeta, porque solo miraba el registro de los
datos del servidor. Sobraban además seis textos de la vista inicial.

- Aclaración de RF-82 y RF-83 (2026-11-16): en la web, «Hacer una copia ahora» abre una previa que no escribe nada (ni
  recuerda la carpeta) con lo que ocupará, el espacio libre del destino y lo que se copia; la copia solo empieza al
  pulsar «Copiar», y «Cancelar» la descarta. Si no cabe, la previa lo dice con las dos cifras y no ofrece «Copiar». La
  API no encola una copia que no llegue confirmada.
- RF-108: CUANDO se pide la previa de la copia, EL SISTEMA listará en solo lectura las copias que ya hay en la carpeta
  destino, de la más nueva a la más vieja, con su fecha, su tamaño, el estado de su manifiesto y sus errores.
- RF-109: SI los datos del servidor no registran ninguna copia pero la carpeta recordada tiene una buena, ENTONCES EL
  SISTEMA contará esa copia en el aviso; sin ninguna, dirá que no consta ninguna copia, nunca que no hay.
- RF-110: EL SISTEMA no enseñará en la vista inicial contadores con «(s)», versiones técnicas, dos «:» seguidos,
  paréntesis que contradigan lo que dicen ni explicaciones largas a la vista, y sus marcadores valdrán para cualquier
  carpeta.
- Aclaración de RF-110 (2026-11-19, revisión de la web en navegador real): vale para toda la web, no solo la vista
  inicial: ningún texto con «palabra(s)» o «palabra(es)» (la cuenta concuerda), y el Registro nombra cada casilla como
  la ve el operador («CARGA»), nunca por su clave interna («loads»).
- Aclaración de RF-110 (2026-11-16): los seis textos de la prueba con la cuenta local: «0 fichero(s) asignados por
  contenido»; «PowerFactory 2024 · Python 3.12» en la cabecera (Python pasa a la ayuda); «Pendientes: la fuente: …»;
  «(proyecto: no se presenta como norma vigente)» de la RM 428-2017, ahora en una frase y solo con un tipo elegido
  (072:RF-37 sigue); la ayuda del CRS, plegada; y el marcador «G:/Mi unidad/…» del campo de la copia.

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
- RF-112: (auditoría del 18-11, H01 y H02) CUANDO falle la observación (el evento de un trabajo) o el diario de
  trabajos, EL SISTEMA no dejará un trabajo «en curso» con su hilo muerto ni ejecutará un trabajo sin su recibo durable:
  con diario, un trabajo nuevo o relanzado que no se pudo anotar no se admite (503 con su motivo); si no se pudo publicar
  el inicio, el trabajo termina con error sin ejecutarse; si falla publicar o anotar el final, el estado final queda
  consultable y el fallo va al log del servidor; el carril sigue atendiendo el siguiente trabajo. Sin diario, la admisión
  no cambia. Enmienda la decisión del 04-11 (086 T6) por la que un disco lleno no paraba el trabajo: sin recibo, si la web cae, el
  trabajo no sale como interrumpido (RF-9).
- RF-113: (auditoría del 18-11, H04) CUANDO llegue una petición que cambia algo, EL SISTEMA impondrá su cota mientras
  llega el cuerpo, no después de que el parser lo haya recibido entero: el tope es el menor entre
  `CSG_UPLOAD_MAX_REQUEST_BYTES` (por defecto 64 GiB, cuatro veces la cota de un archivo, para no bajar de los lotes
  que se admitían) y el espacio libre de la carpeta temporal menos 1 GiB de reserva. Con un Content-Length mayor se
  responde 413 sin leer el cuerpo; sin Content-Length o con uno falso, al pasar el tope. El 413 dice en español si es la
  cuota o el disco. La cota de cada archivo (`CSG_UPLOAD_MAX_BYTES`, 16 GiB) no cambia.
- RF-114: (auditoría del 18-11, H05) CUANDO se encole un trabajo, EL SISTEMA aceptará como mucho
  `CSG_TRABAJOS_EN_COLA_MAX` trabajos en espera (por defecto 64) por espacio y carril; el siguiente se rechaza con 409 y
  su motivo en español, antes de anotar su recibo, publicarlo o encolarlo. Y CUANDO termine un trabajo, EL SISTEMA
  conservará en memoria como mucho `CSG_TRABAJOS_TERMINADOS_MAX` terminados por espacio (por defecto 200), quitando
  primero los más antiguos, pero nunca un interrumpido, un trabajo de una cadena de relanzados, el último terminado de
  cada tipo en su espacio (lo que usan el ajuste, la base o la máxima de cabecera) ni una descarga cuyo fichero sigue en
  disco. Un valor que no es un entero positivo deja el de por defecto.
- RF-115: (auditoría del 18-11, H15) CUANDO una pestaña pida los eventos desde un número cuyo siguiente ya salió del
  registro acotado del espacio, EL SISTEMA antepondrá un evento `historial_truncado` (con los eventos perdidos y el
  número hasta el que se perdieron) a los que conserva, por la consulta y por el WebSocket; un historial completo no
  lo lleva. La pestaña lo dice en el Registro en una línea, sin citar requisitos, y relee del servidor el espacio y sus
  trabajos sin duplicarlos.
- RF-116: (prueba funcional del 19-11) CUANDO un guion de PowerFactory aún no haya escrito la marca de conexión
  («Conectado a DIgSILENT», de pf_arnes.conectar, también dentro del servidor), EL SISTEMA lo terminará si pasa el
  límite de arranque (005:RF-21) sin escribir nada desde su última línea, y lo reintentará una vez como a uno mudo;
  sus avisos previos (turno liberado, espera de turno) reinician el plazo pero ya no dan el guion por arrancado. Con
  fichero de cancelación, un guion que aún no conectó se termina al cancelar. Ya conectado, nada cambia; los guiones
  que no son de PowerFactory siguen con la primera línea.
- RF-117: (CI del 19-11, e2e F03; amplía 024:RF-9, cumplida) CUANDO varias aperturas a la vez del búfer de episodios
  del gemelo lo encuentren sin índice válido, EL SISTEMA lo rehará una sola vez por proceso (cerrojo por carpeta,
  comprobando de nuevo dentro), con un temporal propio por llamada, y si otro proceso ya dejó un índice válido lo
  aceptará en vez de fallar; ninguna apertura falla por el bloqueo de ficheros de Windows y no quedan temporales.
- RF-118: (revisión de la web en navegador real, 19-11) CUANDO la web liste los espacios, EL SISTEMA leerá y
  analizará cada `workspace.json` una sola vez por listado y no lo volverá a leer mientras no cambien su fecha ni su
  tamaño ni los de su copia anterior; un espacio dañado o de una versión futura sigue saliendo con su estado y su motivo
  (RF-2, RF-5). Un `workspace.json` real llega a 12 MB y la web se quedaba en «Conectando con el conversor…».
- RF-119: (prueba funcional del 19-11; amplía 024:RF-55, cumplida) CUANDO el perfil no declare la hoja del libro
  CAPEX, EL SISTEMA recorrerá todas las hojas del libro y leerá las que tengan, en una fila de cabecera, la columna del
  nombre de la obra y la de su costo unitario (con los nombres de columna del perfil o, si no declara ninguno, los
  habituales: «Proyecto», «Obra», «Denominación», «Costo Unitario», «Precio Unitario»…), y dirá en sus avisos qué hojas
  leyó y cuáles no reconoció. SI ninguna hoja sirve, el error dirá en español qué columnas buscó, qué hojas tiene el
  libro y qué declarar en el perfil (`planificacion.capex.hoja` y `columnas`), nunca «None». Con la hoja declarada,
  nada cambia.
- RF-120: (orden del integrador del 19-11 por la ablación de 045 T3; amplía 050:RF-23, sin RF nuevo en la 024 ni en la
  050) CUANDO la web grabe un episodio del gemelo, EL SISTEMA guardará en él el periodo y el criterio de fijas de la
  última calibración del proyecto que llegó a aplicarse en el espacio (una que falló entera no cuenta) y la huella del
  perfil de empresa vigente. Y CUANDO un episodio ya grabado no los traiga, EL SISTEMA no reescribirá su objeto
  (024:RF-10): `tools/rellenar_identidad_043.py` deducirá, en seco por defecto, el periodo y el criterio de la última
  calibración del mismo proyecto anterior al episodio (capturada en el búfer o en los espacios) y la huella del perfil
  vigente, diciendo de dónde sale cada campo; con `--aplicar` y un responsable lo escribirá de una vez en el registro
  aparte `identidad_043.jsonl` del búfer, nunca en `objetos/` ni en el índice. `preparar_ciclo_aprendizaje.py`
  combinará cada objeto con su fila, que completa lo que falta y nunca sustituye lo que el episodio dice (si lo
  contradice, cuarentena con el motivo), congelará lo usado con la instantánea y dejará en cuarentena, con su motivo,
  lo que no se pudo deducir. Un búfer sin el registro se sigue leyendo igual.
- RF-121 a RF-121: no se usa en esta rama: lo define el tope del horizonte de entrenamiento de la 031, si llega a hacer
  falta; al rebasarlo, esta línea se sustituye por la suya.
- RF-122: (orden del usuario del 19-11: «aquí debería haber un selector de su SET de los que están conectados los
  alimentadores … todas las SET deberían habilitarse para seleccionar su coincidencia; las centrales no pertenecen a
  ninguna de las cargas analizadas»; amplía 022:RF-88, cumplida) EN la máxima por barra, EL SISTEMA dejará elegir la
  SET de cada central térmica (CT…) del libro entre todas las de la estructura, primero las de los alimentadores
  analizados; el tramo que se ofrece es de un alimentador de la SET elegida. Una central cuya SET no tiene ninguno de
  los alimentadores analizados no entra en la máxima y se dice por qué, en la web y en los avisos del trabajo.
- RF-123: (orden del usuario del 19-11: «aquí debe haber sus etiquetas de la potencia kW y fecha que ocurrió la máxima
  de cada alimentador; en la imagen solo se ven los puntos») CUANDO la gráfica de curvas de cabecera tenga varias
  curvas, EL SISTEMA pondrá junto al punto de la máxima de cada una su etiqueta con el alimentador, los kW y la fecha y
  hora, en el color de su curva y repartidas para que no se tapen entre ellas ni salgan del gráfico.
- RF-124: (orden del usuario del 19-11: «verificar qué pasó en la calibración … corregir, proponer la mejora e
  implementarla» y «el mismo caso para la calibración de sistema eléctrico, de una SET»; amplía 083:RF-30, cumplida) EN
  la calibración de un alimentador o de un proyecto (por alimentadores, por SET o por sistema eléctrico), CUANDO un
  alimentador siga por encima de
  su medida con las escaladas al mínimo (medido contra su factor de antes del arranque del oráculo) y su exceso no se
  pueda corregir en sus fijas, EL SISTEMA lo dejará quieto con su causa (lo que da frente a lo medido, sus fijas, sus
  pérdidas y la SED fija que más pesa) y, si los demás ya cumplen, parará sin gastar los flujos que quedan. Cada
  alimentador se informa con su estado: el que cumple en el flujo común sale cuadrado y solo el imposible sale con su
  causa. La calibración sigue siendo una, por proyecto, y nunca se borra nada del proyecto.
- RF-125: (orden del usuario del 19-11 sobre su calibración real: «la lectura no trae el grafo eléctrico, corregir y
  mejorar»; amplía 024:RF-4, cumplida) SI tras una acción nativa el flujo no converge al reabrir el proyecto, ENTONCES
  EL SISTEMA leerá igual la red (el grafo, sin resultados), clasificará el episodio como `rejected` con la causa «el
  flujo no converge tras reabrir» (no `accepted` sin flujo ni cuarentena por un grafo que faltaba), lo dirá en el
  Registro y la línea del guion de lectura dirá la causa de su código; una lectura que no vale (otro proyecto,
  alimentadores o caso) sigue en cuarentena.
- RF-126: (orden del usuario del 19-11: «aquí debe haber también su máxima no coincidente de cada alimentador, ya sea
  de dos alimentadores, SET, sistema eléctrico»; amplía 028:RF-27, RF-28, cumplida) EN «Instante de la calibración», EL
  SISTEMA ofrecerá también «Máxima de cada alimentador (no coincidente)», con dos o más alimentadores, en el análisis de
  una SET y en el de un sistema eléctrico. El valor por defecto de cada análisis no cambia (la coincidente, la barra de la SET o el sistema) y
  la web lo sigue proponiendo según el proyecto. Elegida, la web y el informe de la calibración dicen la fecha y hora de
  cada alimentador y avisan, sin bloquear, de que esos instantes no ocurrieron juntos.

## Fuera de alcance

Multiusuario en servidor, instalación por equipo (U7, después de la 1.0), otros países, cortocircuito y protecciones (049, que no existen y hay que
declararlo al cliente), mover los módulos a sus capas (002 T7 y T9), MADRL (074), aprendizaje continuo con datos reales (050), QLoRA (047 T7),
PINN (045 T3), optimización mixta (048), 072 T3 y T9, 027 T11 y T26, 071 T5.
