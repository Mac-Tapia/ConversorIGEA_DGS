# Spec 028 — Escaneo del alimentador antes de recalibrar

Estado: implementada (revisión 033 del 2026-10-29) · pedida por el usuario el 2026-10-28 («en el interfaz debe tener un campo donde escanea
al alimentador para hacer la recalibración donde identifique los cambios y centrales térmicas
en cualquier alimentador; recuerda que este proyecto es universal, general, nada debe estar
fijo»), tras decir que las centrales y los bancos de NA205 los pone él a mano en DIgSILENT.

## Por qué

La recalibración de un sistema solo sabía de una central si el perfil de la empresa la traía
con su barra (la de Nasca en NA205, `nodo` 1720). Lo que el operador cambia a mano en
DIgSILENT (un generador, un banco, una variación propia) no se veía hasta que la calibración
fallaba: en Nasca (2026-10-28) la cabecera de NA205 mide la demanda menos la generación de su
central y la calibración subía el factor de escala 30 flujos sin cuadrar, y los bancos de
calibración se acumulaban entre corridas (8 en NA205). Ningún nombre de empresa, central o
alimentador puede estar fijo: el escaneo vale para cualquier alimentador de cualquier
distribuidora.

## Requisitos

Escaneo

- RF-1: CUANDO el operador pida escanear alimentadores de un proyecto de DIgSILENT, EL SISTEMA
  leerá cada uno en el caso «Sin proyecto» (el de su año, si lo hay) sin escribir nada en el
  proyecto.
- RF-2: EL SISTEMA listará los generadores de cada alimentador (`ElmGenstat`, `ElmSym`,
  `ElmPvsys`, `ElmAsm`) con su barra, su tensión, su P y Q y si está en servicio.
- RF-3: EL SISTEMA dirá de cada generador si lo creó el conversor (en su variación de central)
  o el operador.
- RF-4: EL SISTEMA listará los bancos de condensadores de cada alimentador con su barra, sus
  kvar y si está en servicio, y dirá si lo puso la calibración o el operador.
- RF-5: EL SISTEMA listará las variaciones de red del proyecto que no creó el conversor, con
  si están activas y cuántos objetos cambian.
- RF-6: DONDE haya una calibración anterior del alimentador, EL SISTEMA listará las cargas cuya
  demanda difiere de la que dejó (014:RF-10).
- RF-7: EL SISTEMA reconocerá lo que creó el conversor solo por sus propios prefijos (variación
  de central, banco de calibración, obras, cargas nuevas), nunca por nombres de una empresa.
- RF-8: SI DIgSILENT no está disponible o el alimentador no está en el proyecto, ENTONCES EL
  SISTEMA lo dirá por alimentador sin detener el escaneo de los demás.

En la web

- RF-9: EL SISTEMA tendrá en el paso de calibración un botón «Escanear en DIgSILENT» que lance
  el escaneo de los alimentadores marcados como trabajo del carril de DIgSILENT.
- RF-10: EL SISTEMA mostrará por alimentador los generadores, bancos, variaciones y cargas
  cambiadas que encontró.
- RF-11: CUANDO el escaneo encuentre un generador en un alimentador sin central declarada, EL
  SISTEMA declarará su central con la barra del generador, y el operador elegirá sus medidores
  de generación, llegada y salida.
- RF-12: DONDE la central declarada no tenga barra, EL SISTEMA tomará la del generador que
  encontró el escaneo en ese alimentador.

En la calibración

- RF-13: SI en la barra de la central hay un generador en servicio que puso el operador,
  ENTONCES EL SISTEMA lo usará con la P y Q medidas en el instante de la calibración, sin crear
  otro, y lo dirá en los avisos.
- RF-14: SI el alimentador ya tiene bancos de calibración, ENTONCES EL SISTEMA no pondrá más y
  lo dirá: los cuenta el flujo y lo demás lo decide el operador.
- RF-15: CUANDO `tools/sistema_web.py` calibre un sistema, EL SISTEMA escaneará antes sus
  alimentadores y usará la barra del generador encontrado para la central del perfil que no la
  traiga.

Recalibrar sin bloqueos (usuario, 2026-10-28: «en el caso base se debe ejecutar tal como está;
ahora en el Sin proyecto se calibra con datos máximos según la metodología con las instalaciones
que están; en la recalibración ya debe observar, escanear los nuevos tramos, centrales térmicas,
bancos y otros cambios; en base de eso debe recalibrar sin ningún bloqueo, solo se recalibra»)

- RF-16: CUANDO se simule o aplique una calibración desde la web, EL SISTEMA escaneará antes sus
  alimentadores sin que el operador lo pida, y si el escaneo falla lo dirá y calibrará igual.
- RF-17: EL SISTEMA listará en el escaneo los tramos del alimentador que no venían en el DGS
  aceptado del proyecto (tramos nuevos), con sus barras y su longitud.
- RF-18: SI un alimentador tiene un generador en servicio que puso el operador y no tiene central
  declarada, ENTONCES EL SISTEMA lo calibrará con el generador tal como está (su P y Q en el
  flujo, la cabecera medida es la demanda menos su generación) y lo dirá, sin pedir medidores.
- RF-19: SI una central declarada no tiene barra ni generador en el escaneo, ENTONCES EL SISTEMA
  calibrará el alimentador sin ella y lo dirá, sin detener el plan.
- RF-20: EL SISTEMA no tocará el «Caso base» al recalibrar: se ejecuta tal como está (015:RF-19).
- RF-21: EL SISTEMA tendrá en la web un botón «Recalibrar», aparte de la calibración inicial, que
  sobre el proyecto ya importado escanee, busque la máxima del periodo y recalibre «Sin
  proyecto» de su sistema eléctrico, sin reconvertir ni volver a importar (usuario, 2026-10-28:
  «tiene que haber un botón para recalibrar en la web, así evitar confundir con la calibración
  inicial»).
- RF-22: EL SISTEMA tomará para recalibrar el sistema eléctrico del nombre del proyecto y la
  carpeta de los libros de demanda que ya tiene el espacio, y el operador podrá cambiarlos.
- RF-23: SI el proyecto no es de un sistema eléctrico ni de alimentadores convertidos en el
  espacio, o el espacio no tiene libros de demanda, ENTONCES EL SISTEMA lo dirá antes de empezar
  (cambiado el 2026-10-28 por RF-24: antes solo valía un sistema eléctrico).
- RF-24: EL SISTEMA recalibrará también el proyecto de un alimentador o de varios unidos, con los
  alimentadores que el espacio guardó para él y la máxima de cada uno, sin la de su barra
  (usuario, 2026-10-28: «otras conversiones, ya sea de un alimentador o dos, hasta su
  recalibración y generación de los informes»).
- RF-25: EL SISTEMA dará al operador una herramienta que convierta, importe y calibre por la web
  uno o varios alimentadores, unidos en un proyecto si son varios, igual que un sistema eléctrico.
- RF-26: CUANDO escanea, EL SISTEMA listará por alimentador cada tramo que venía en el DGS
  aceptado y que graba una variación que no es del conversor (el operador le cambió el tipo, la
  longitud o el estado), con su variación, su tipo y su longitud de ahora, y lo mostrará en la
  tabla del escaneo junto a los tramos nuevos. Usuario, 2026-10-28: «todas esas modificaciones
  manuales debe reconocerlas al momento de recalibrar» (tramos actualizados y ternas nuevas,
  según las instalaciones en campo); los tramos y ternas nuevos ya los da RF-17.

Instante según el tipo de proyecto y selección al detectar (usuario, 2026-11-02: «si se analiza por
alimentador debe ser como la A, pero si analiza por sistema se considera por barra; son cosas
diferentes que no se deben mezclar»; «estas selecciones de centrales térmicas estén para ingresar de
la web y se activen una vez se detecte en la recalibración bancos y centrales, en cualquier
alimentador o barra de cabecera»)

- RF-27: EL SISTEMA dará en la web un selector con tres tipos de análisis, que no se mezclan: alimentadores (uno a tres
  juntos, RF-28), SET (máxima de su barra, 022:RF-37) y sistema eléctrico (RF-31). Propondrá sistema eléctrico si el proyecto
  es de un sistema y alimentadores en otro caso, y el operador podrá cambiarlo. Con más de tres alimentadores no
  buscará como «alimentadores» y lo dirá. Cambiado el 2026-11-02 por el usuario: «esto debe venir desde la web, la
  selección de qué análisis se va a hacer»; solo para proyectos futuros: NA203_NA205 no se recalibra.
- RF-28: DONDE un proyecto tenga dos o más alimentadores, EL SISTEMA los calibrará en un único instante:
  el de la mayor demanda coincidente de todos, sumando en cada alimentador con central sus dos zonas
  (021:RF-31) y descartando los registros que no pasen los filtros de esa central (021:RF-30, RF-32).
  SI los medidores de una central no cuadran, ENTONCES ese alimentador cuenta por su cabecera y lo dirá.
- RF-29: CUANDO escanea, EL SISTEMA listará también los generadores y los bancos conectados en la barra de
  cabecera de cada alimentador, aparte de los del alimentador.
- RF-30: CUANDO haya un escaneo del proyecto, también el automático de una calibración o recalibración,
  EL SISTEMA activará en la web la selección de medidores de cada central hallada y avisará de lo
  detectado en cada alimentador y barra de cabecera, sin que el operador tenga que escanear otra vez.

- RF-31: DONDE el análisis sea de sistema eléctrico, EL SISTEMA calibrará todas sus SET en un único instante: el de la mayor
  suma coincidente de sus barras de 60 kV; una SET sin medidor de 60 kV no fija el instante, se calibra en él y lo avisará.
  Una barra con huecos cuenta donde tiene registro y no descarta las demás fechas; SI no tiene el registro del instante,
  ENTONCES no suma y lo avisará. Un alimentador sin registro en el instante sigue RF-38. SI ninguna SET tiene barra de 60 kV, ENTONCES lo dirá y no buscará.
- RF-32: DONDE el análisis sea de dos o tres alimentadores, EL SISTEMA buscará por defecto el instante común de RF-28 y dará
  un desplegable con la máxima de la cabecera de cada seleccionado; CUANDO el operador elija una, TODOS los medidores se
  leerán en ese instante, y podrá volver al de por defecto. Usuario, 2026-11-02: «esto debería ser manual desde la cabecera
  con la selección desplegable, pero por defecto está bien así».
- RF-33: DONDE el análisis sea de sistema eléctrico, EL SISTEMA leerá del libro de medidores las líneas LT de 60 kV: la
  fila con sufijo «_L» o «-L» en su código o su SET es la llegada a las barras, y «_S» o «-S» la salida de la línea; su SET
  sale de la columna SET sin el prefijo «LT» ni el sufijo (LTSET25_L → SET 25). Usuario, 2026-11-03: «los que comienzan con
  s son de mediciones de la línea LT salidas y l son llegada a las barras».
- RF-34: SI una SET del sistema no tiene medidor de barra de 60 kV y sí LT de llegada, ENTONCES EL SISTEMA obtendrá su
  aporte por balance: sus llegadas menos sus salidas, menos sus clientes de alta; y, si el libro no da otras salidas que las
  mismas llegadas, menos además las barras de 60 kV de las demás SET del sistema, porque esa línea es la entrada de todo el
  sistema y sumarla entera contaría dos veces lo de ellas. Una fecha sin registro de alguno de esos medidores no se usa.
  Usuario, 2026-11-03: «si hazlo por balance».
- RF-35: EL SISTEMA leerá los clientes de alta de cada SET de `clientes_alta_por_set` en el perfil local (el repositorio es público) o de la estructura de la empresa (`clientes_alta`), porque el
  libro no dice de qué SET son; no mueven el instante del sistema, que es el de la red de sus alimentadores.
- RF-36: EL SISTEMA sumará al instante del sistema, en cada fecha, la generación coincidente de sus centrales térmicas,
  de barra o de tramo, porque la barra de 60 kV mide lo neto; un hueco de una central no descarta la fecha. Usuario,
  2026-11-03: «debe incluir las coincidentes para las centrales térmicas».
- RF-37: EL SISTEMA hará todo lo anterior para cualquier sistema eléctrico y cualquier empresa, al calibrar y al
  recalibrar, sin nombres de medidores ni de SET en el código. SI dos SET de un sistema necesitan balance y ninguna tiene
  salidas propias, ENTONCES no se puede repartir: lo dirá y esas SET no fijarán el instante.
- RF-38: SI en el análisis de sistema eléctrico un alimentador no tiene medida positiva en el instante del sistema, y solo
  entonces, EL SISTEMA tomará su máxima del mes de ese instante y, si ese mes tampoco la tiene, la de su periodo; lo nombrará
  con la fecha tomada, y sin ninguna medida en el periodo lo dirá. Usuario, 2026-11-03: «debe buscar en el mes de máxima
  medición de los que no tienen, solo cuando ocurre eso» y «nada de quedar sin carga». Cambia lo dicho en RF-31.
- RF-39: DONDE el análisis sea de sistema eléctrico, EL SISTEMA no fijará el instante en un registro de maniobra: el que tenga
  algún alimentador a más de 3 rangos intercuartílicos de sus cuartiles (021:RF-32), porque es una transferencia de carga y no su
  demanda. Dirá cuántos descartó; SI quedaran todos fuera, ENTONCES no filtrará. Pisco (2026-11-03): la máxima cruda del año, el
  10-abr 12:00, tenía a PA110 en 3 408 kW con su red para 885 kW y a PA218 en 2 864 kW, y los dos quedaban sin calibrar. Usuario:
  «deben entrar todos, analizar las mediciones y corregirlos».

## Fuera de alcance

- Crear centrales o bancos desde el escaneo: solo se leen; los crea el operador o la
  calibración (spec 021).
- Emparejar de forma automática un generador con sus medidores CT por el nombre: lo elige el
  operador en la web (o el perfil, si los trae).
- Comparar el proyecto con el DGS original (lo hace la verificación del «Caso base», spec 015).
