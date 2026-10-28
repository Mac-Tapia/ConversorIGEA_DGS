# Spec 028 — Escaneo del alimentador antes de recalibrar

Estado: pedida por el usuario el 2026-10-28 («en el interfaz debe tener un campo donde escanea
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
- RF-23: SI el proyecto no es de un sistema eléctrico o el espacio no tiene libros de demanda,
  ENTONCES EL SISTEMA lo dirá antes de empezar.

## Fuera de alcance

- Crear centrales o bancos desde el escaneo: solo se leen; los crea el operador o la
  calibración (spec 021).
- Emparejar de forma automática un generador con sus medidores CT por el nombre: lo elige el
  operador en la web (o el perfil, si los trae).
- Comparar el proyecto con el DGS original (lo hace la verificación del «Caso base», spec 015).
