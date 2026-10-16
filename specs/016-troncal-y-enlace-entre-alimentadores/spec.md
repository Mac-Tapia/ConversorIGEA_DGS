# Spec 016 — Troncal por el camino más largo, enlace entre alimentadores y conexión en un tramo

Estado: aprobada (2026-10-14) · Fecha: 2026-10-14 · Origen: petición del usuario, 2026-10-14 (cambiar
la troncal de IN111 a 120 mm² y transferir carga de IN111 a TA225)

## Contexto y objetivo

El usuario pidió dos cosas sobre el proyecto de IN111 y TA225. La primera es pasar toda
la troncal de IN111 a 120 mm² (AA12003D a 10 kV). La segunda es calcular la transferencia
de carga de IN111 a TA225. Las dos chocaron con lo que hay:

- **La troncal** de la spec 011 es la que calcula DIgSILENT (`ComBbone`, 011:RF-108), y
  `ComBbone` solo dibuja troncales entre alimentadores que tienen un enlace. IN111 no
  tiene ninguno, así que no tenía troncal. Para el usuario, la troncal de una obra es otra
  cosa: «el conjunto de tramos continuos que hacen el más largo del alimentador». En IN111
  son 71 tramos y 13,58 km desde la cabecera. De ellos, 34 tramos aéreos, con 7.413 m, no
  son de 120 mm²: de aluminio de 70 mm² (1.807 m) y de 35 mm² (874 m), de cobre de 25 mm²
  (4.717 m) y nueve tramos `DEFAULT` de 1 a 2 m entre equipos. (Corregido en la T3: la
  primera medida, 72 tramos y 13,59 km, recorría la red en profundidad y en uno de sus
  tres anillos cerrados daba la vuelta por el lado largo.) Toda la troncal
  pasa a 120 mm². El N-1 y la transferencia siguen con la troncal de DIgSILENT.
- **El enlace.** IN111 y TA225 no comparten ningún nodo ni interruptor, ni en el TXT ni
  en las `.mdb`. El punto de la troncal de TA225 más cercano a IN111 está a 1.860 m. La
  transferencia de la spec 011 no calcula nada sin un punto de enlace (011:RF-107). El
  usuario pide un trazo nuevo «desde la troncal de TA225 más cercana a IN111», como obra y
  en «Con proyecto».
- **El punto de conexión.** El enlace no tiene que llegar a un nodo que ya exista. Se
  conecta en un tramo cerrado, creando un nodo nuevo, en un punto donde la caída de
  tensión y la capacidad de TA225 lo permiten. Las cargas nuevas de la spec 007 se
  conectan igual: en el punto más cercano de la troncal, con un nodo nuevo. Hasta
  ahora iban a la barra existente más cercana (007:RF-24). En SI213 esa barra era el nodo
  de una SED, que solo tenía su seccionador (007:RF-39).

El usuario fijó además el orden de los casos: «lo que se modifica en Sin proyecto debe
pasar a Con proyecto, y la copia se hace una vez modificado el Sin proyecto; las
construcciones de nueva línea se hacen ya en Con proyecto, en variación». Esto ajusta
011:RF-57, que dejaba activar una obra solo en «Sin proyecto».

## Usuarios / actores

El ingeniero de planificación, desde el paso «4 · Obras y estudios» y el paso de cargas
nuevas de la web (specs 011 y 007), o con los guiones de `tools/`. El proyecto de
DIgSILENT ya importado y con sus tres casos.

## Historias de usuario

- H1: Como ingeniero quiero cambiar la sección de toda la troncal de un alimentador sin
  dar los tramos uno a uno, aunque el alimentador no tenga enlace con otro.
- H2: Como ingeniero quiero que una mejora hecha en «Sin proyecto» esté también en «Con
  proyecto», para no comparar dos redes distintas.
- H3: Como ingeniero quiero proponer una línea nueva entre dos alimentadores que hoy no
  se tocan, conectada donde el que recibe lo aguanta, y calcular la transferencia por
  ella.
- H4: Como ingeniero quiero que una carga nueva se conecte en la troncal, en el punto más
  cercano al suyo, no en la barra que ya existe más cerca.

## Requisitos funcionales (EARS)

Troncal por el camino más largo

- RF-1: EL SISTEMA definirá la troncal de un alimentador, para las obras, como los tramos
  del camino continuo más largo, en metros, que sale de su cabecera.
- RF-2: EL SISTEMA calculará la troncal de RF-1 con la red del caso de estudio en que se
  aplica la obra, tal como está en el proyecto de DIgSILENT.
- RF-3: EL SISTEMA calculará la troncal de RF-1 aunque el alimentador no tenga ningún
  enlace con otro alimentador.
- RF-4: EL SISTEMA no contará en el camino de RF-1 los tramos abiertos ni los que están
  fuera de servicio.
- RF-5: SI dos caminos tienen la misma longitud, ENTONCES EL SISTEMA elegirá el mismo cada
  vez, con un desempate que no dependa del orden en que DIgSILENT devuelve los objetos.
- RF-6: CUANDO una obra de sección pide «toda la troncal», EL SISTEMA asignará el tipo
  aéreo pedido a cada tramo aéreo de la troncal de RF-1 que no lo tiene ya, cualquiera
  que sea su material o su sección.
- RF-7: DONDE el operador da además un tipo de cable, EL SISTEMA asignará ese tipo a cada
  tramo de cable de la troncal que no lo tiene ya.
- RF-8: SI la troncal tiene tramos de cable de otra sección y el operador no da un tipo de
  cable, ENTONCES EL SISTEMA dejará esos tramos como están y los listará en el informe,
  sin bloquear la obra.
- RF-9: CUANDO se simula una obra de RF-6, EL SISTEMA dirá la longitud de la troncal, el
  número de tramos y los metros que cambian, agrupados por tipo de origen.
- RF-10: EL SISTEMA seguirá usando la troncal de DIgSILENT en el N-1 (011:RF-43) y en la
  transferencia (011:RF-108).

«Sin proyecto» pasa a «Con proyecto»

- RF-11: CUANDO una obra se activa en «Sin proyecto», EL SISTEMA la activará también en
  «Con proyecto».
- RF-12: SI «Con proyecto» no existe cuando se aplican obras en «Sin proyecto», ENTONCES
  EL SISTEMA lo creará como copia de «Sin proyecto» después de aplicar esas obras
  (014:RF-18).
- RF-13: SI el operador pide una obra solo en «Sin proyecto», ENTONCES EL SISTEMA la
  rechazará antes de escribir nada y dirá que lo de «Sin proyecto» pasa siempre a «Con
  proyecto».
- RF-14: EL SISTEMA no activará en «Sin proyecto» una obra pedida solo para «Con
  proyecto».

Conexión en un tramo con un nodo nuevo

- RF-15: EL SISTEMA tomará como punto de un tramo el más cercano a una posición dada sobre
  su trazado GPS (spec 010) o, si el tramo no tiene trazado, sobre la recta entre sus dos
  barras.
- RF-16: CUANDO conecta en un punto interior de un tramo, EL SISTEMA partirá el tramo en
  dos con una barra nueva en ese punto.
- RF-17: EL SISTEMA dará a los dos tramos de RF-16 el tipo, el número de ternas y el
  estado del tramo original.
- RF-18: EL SISTEMA dará a los dos tramos de RF-16 longitudes que sumen la del tramo
  original, en la proporción del punto sobre el trazado.
- RF-19: EL SISTEMA dará a la barra nueva de RF-16 la tensión nominal del tramo y las
  coordenadas GPS del punto.
- RF-20: SI el punto de RF-15 está a menos de la distancia mínima que da el operador de
  una barra del tramo, ENTONCES EL SISTEMA conectará en esa barra sin partir el tramo.
- RF-67: SI el operador deja vacía la distancia mínima, ENTONCES EL SISTEMA solo conectará
  en una barra cuando el punto coincida con ella, y partirá el tramo en los demás casos.
- RF-21: EL SISTEMA solo partirá tramos cerrados y en servicio de media tensión.
- RF-22: EL SISTEMA partirá el tramo dentro de la variación de la obra o de la carga que
  lo necesita, nunca en la red de «Sin proyecto» ni del «Caso base».

Obra de enlace entre alimentadores

- RF-23: DONDE el operador define una obra de enlace, EL SISTEMA pedirá el alimentador
  que recibe, el alimentador que cede y el tipo de línea.
- RF-24: EL SISTEMA aplicará la obra de enlace solo en «Con proyecto», en una variación
  propia (011:RF-56).
- RF-25: SI el operador pide una obra de enlace en «Sin proyecto», ENTONCES EL SISTEMA la
  rechazará antes de escribir nada y lo dirá.
- RF-26: EL SISTEMA tomará como tramos candidatos para el origen del enlace los de la
  troncal de RF-1 del alimentador que recibe cuyas dos barras están dentro de los límites
  de tensión y cuya cargabilidad está por debajo del límite, con el flujo de carga de «Con
  proyecto» antes del enlace (límites de 011:RF-35).
- RF-27: EL SISTEMA tomará como origen del enlace el punto de los tramos candidatos de
  RF-26 más cercano a la troncal de RF-1 del alimentador que cede, medido con las
  coordenadas GPS.
- RF-28: EL SISTEMA tomará como destino del enlace el punto de la troncal de RF-1 del
  alimentador que cede más cercano al origen de RF-27, medido con las coordenadas GPS.
- RF-29: EL SISTEMA conectará el origen y el destino con RF-15 a RF-22.
- RF-30: SI ningún tramo de la troncal del que recibe cumple RF-26, ENTONCES EL SISTEMA no
  creará el enlace y lo dirá con la tensión mínima y la cargabilidad máxima de su troncal.
- RF-31: DONDE el operador indica la barra o el punto de origen o de destino, EL SISTEMA
  usará el que indica en vez del de RF-27 o RF-28.
- RF-32: SI el punto que indica el operador en el que recibe no cumple RF-26, ENTONCES EL
  SISTEMA lo usará igual y lo dirá en el informe con su tensión y su cargabilidad.
- RF-33: SI ningún tramo de uno de los dos alimentadores tiene coordenadas, ENTONCES EL
  SISTEMA no creará el enlace, salvo con los dos puntos de RF-31, y lo dirá.
- RF-34: CUANDO aplica la obra de enlace, EL SISTEMA creará una línea nueva entre origen y
  destino, con el tipo pedido y la longitud en línea recta entre ellos.
- RF-35: EL SISTEMA dará a la línea nueva el trazado GPS de sus dos extremos (spec 010).
- RF-36: EL SISTEMA dejará un seccionador abierto en el extremo de la línea nueva que toca
  al alimentador que cede: el punto de enlace.
- RF-37: EL SISTEMA dejará la línea nueva fuera de la troncal de RF-1 de los dos
  alimentadores.
- RF-38: SI el tipo pedido no existe a la tensión del alimentador que recibe, ENTONCES EL
  SISTEMA creará su copia a esa tensión (011:RF-79).
- RF-39: SI los dos alimentadores tienen distinta tensión nominal, ENTONCES EL SISTEMA
  creará igual el enlace, a la tensión del que recibe, con el seccionador de RF-36
  abierto.
- RF-61: CUANDO el enlace une dos tensiones distintas, EL SISTEMA dirá en el informe las
  dos tensiones y que el enlace no se puede cerrar hasta migrar la parte que se transfiere
  (RF-51 a RF-60).
- RF-62: EL SISTEMA no cerrará nunca un punto de enlace entre barras de distinta tensión
  nominal, porque el flujo de carga no converge.
- RF-40: SI ya existe en «Con proyecto» una obra de enlace entre los mismos dos
  alimentadores, ENTONCES EL SISTEMA no creará otra y lo dirá con su variación.
- RF-41: CUANDO se simula una obra de enlace, EL SISTEMA dirá los dos tramos y puntos, si
  cada punto parte un tramo o usa una barra, la distancia, el tipo y dónde queda el
  seccionador, sin escribir en el proyecto.
- RF-42: CUANDO la obra de enlace queda creada, EL SISTEMA ejecutará el flujo de carga de
  «Con proyecto» y dirá si converge (011:RF-66).
- RF-43: MIENTRAS el seccionador de RF-36 está abierto, EL SISTEMA dejará los dos
  alimentadores sin ningún camino cerrado entre ellos en «Con proyecto».
- RF-44: CUANDO el operador calcula una transferencia en «Con proyecto» entre los dos
  alimentadores, EL SISTEMA encontrará el seccionador de RF-36 como punto de enlace
  (011:RF-106).
- RF-63: SI las dos barras del punto de enlace tienen distinta tensión nominal en el caso
  que se calcula, ENTONCES EL SISTEMA no calculará la transferencia por ese enlace y lo
  dirá con las dos tensiones (RF-62).

Migración a la tensión del que recibe de las SED que se transfieren

El caso que lo motivó: IN111 es de 10 kV y TA225 de 22,9 kV. Las SED de IN111 que pasan a
TA225 cambian antes de nivel de tensión en «Con proyecto», en otra variación, y solo
entonces se puede cerrar el enlace.

- RF-51: DONDE el operador define una obra de migración de SED, EL SISTEMA pedirá el
  alimentador que cede, la tensión de destino y el nodo desde el que se pasa a esa
  tensión.
- RF-64: EL SISTEMA tomará como parte que pasa el nodo de RF-51 y todo lo que queda aguas
  abajo de él, visto desde la cabecera del alimentador que cede: barras, tramos y SED.
- RF-65: SI el nodo de RF-51 no es del alimentador que cede, ENTONCES EL SISTEMA no
  aplicará la migración y lo dirá con el nodo y el alimentador.
- RF-52: EL SISTEMA aplicará la obra de migración solo en «Con proyecto», en una variación
  propia, distinta de la del enlace.
- RF-53: SI el operador pide una obra de migración en «Sin proyecto», ENTONCES EL SISTEMA
  la rechazará antes de escribir nada y lo dirá.
- RF-54: EL SISTEMA asignará a cada transformador de las SED que pasan una copia de su
  tipo con la tensión de alta de destino, con las reglas de 011:RF-83, RF-99 y RF-103.
- RF-55: EL SISTEMA pondrá la tensión de destino en las barras de media de la parte que
  pasa (RF-64).
- RF-56: EL SISTEMA asignará a los tramos de RF-55 una copia de su tipo a la tensión de
  destino (011:RF-82).
- RF-57: EL SISTEMA no cambiará la tensión de ninguna barra, tramo ni SED del alimentador
  que cede que no pase.
- RF-58: SI la parte que pasa queda unida a la que no pasa sin un elemento abierto entre
  ellas, ENTONCES EL SISTEMA abrirá, en la variación de la migración, el tramo que entra
  al nodo de RF-51 desde la cabecera, y lo dirá con su nombre.
- RF-66: SI el punto de enlace de RF-36 no queda en la parte que pasa, ENTONCES EL SISTEMA
  aplicará igual la migración y dirá que esa parte quedará sin alimentación al no tocar
  el enlace.
- RF-59: CUANDO se simula una obra de migración, EL SISTEMA dirá las SED, las barras y los
  tramos que cambian de tensión, y los tipos nuevos, sin escribir en el proyecto.
- RF-60: CUANDO la migración queda creada, EL SISTEMA ejecutará el flujo de carga de «Con
  proyecto» y dirá si converge (011:RF-66).

Formulario de la web (paso «4.1 Obras de mejora», 011:RF-70)

- RF-68: EL SISTEMA ofrecerá en el formulario de obras la obra de enlace, con el
  alimentador que recibe, el que cede, el tipo de línea, la distancia mínima de RF-20 en
  metros y, opcionales, la barra o el punto de origen y de destino (RF-31).
- RF-69: EL SISTEMA ofrecerá en el formulario de obras la obra de migración, con el
  alimentador que cede, la tensión de destino y un campo para el nodo de RF-51.
- RF-70: EL SISTEMA ofrecerá en la obra de sección la opción «toda la troncal» (RF-6), con
  el tipo aéreo y, opcional, el tipo de cable (RF-7).
- RF-71: EL SISTEMA ofrecerá en el formulario solo «Con proyecto» como caso de las obras de
  enlace y de migración.
- RF-72: SI el operador escribe un nodo que no está en el alimentador que cede, ENTONCES EL
  SISTEMA lo dirá en el formulario con el nodo y el alimentador al simular la obra,
  antes de aplicarla.
- RF-73: EL SISTEMA ofrecerá en el paso de cargas nuevas el campo de la distancia mínima
  de RF-20 para la conexión en el tramo más cercano (RF-45).

Cargas nuevas en el tramo más cercano (cambia 007:RF-24 y 007:RF-31)

- RF-45: CUANDO una carga nueva trae coordenadas y no trae barra, EL SISTEMA la conectará
  en el punto de la troncal de RF-1 del alimentador activo más cercano a su punto, con
  RF-15 a RF-22, en vez de en la barra más cercana (007:RF-24).
- RF-46: EL SISTEMA partirá el tramo de RF-45 dentro de la variación de esa carga nueva,
  en «Con proyecto».
- RF-47: SI dos cargas nuevas caen en el mismo tramo, ENTONCES EL SISTEMA partirá cada
  una el tramo que hay en su variación, sin depender del orden en que se aplican.
- RF-48: DONDE la carga trae una barra, EL SISTEMA la conectará a esa barra, sin partir
  ningún tramo (007:RF-26).
- RF-49: EL SISTEMA mostrará en la simulación, por carga, el tramo elegido, si se parte o
  se usa una barra, y la distancia en metros del punto del libro al punto de conexión
  (cambia 007:RF-30).
- RF-50: SI ningún tramo de la troncal del alimentador activo tiene coordenadas, ENTONCES
  EL SISTEMA no conectará por coordenadas ninguna carga y lo dirá una vez, con el
  alimentador (007:RF-28).

Etapas de las variaciones (prueba en DIgSILENT con IN111 + TA225, 2026-10-15)

- RF-74: CUANDO crea la etapa de una variación (carga nueva, ajuste u obra), EL SISTEMA le
  dará una fecha de activación propia, la siguiente libre antes de la hora del caso de
  estudio, de modo que la más nueva se aplique la última. Con tres o más etapas activas
  de la misma fecha DIgSILENT no aplica ninguna y no lo dice: «Con proyecto» calculaba
  sin las nueve cargas nuevas de TA225 ni las obras (cambia 007:RF-3 y 006:RF-19).
- RF-75: CUANDO graba una obra de «Con proyecto», EL SISTEMA leerá la red y escribirá la
  obra con las variaciones de cargas nuevas apartadas, las devolverá antes de su flujo y
  avisará SI la obra y una carga graban el mismo objeto.

## Requisitos no funcionales

- Determinismo: con el mismo proyecto, la troncal, los puntos del enlace y el tramo de
  cada carga nueva son los mismos en cada ejecución (RF-5).
- Escala: la troncal y el tramo más cercano se calculan por alimentador con un recorrido
  de su red, sin recorrer la red entera del proyecto por cada alimentador ni por cada
  carga (constitución P2).
- Universal: nada de nombres de Electro Dunas ni de un CRS fijo; las coordenadas son las
  del proyecto y los límites, los del perfil de empresa (P13).
- Idioma: mensajes e informe en español.

## Casos límite

- Alimentador con un solo tramo: la troncal es ese tramo.
- La troncal pasa por tramos de longitud casi nula (`LINE:DEFAULT` de 1 a 2 m entre
  equipos): cuentan para la continuidad y RF-6 les asigna el tipo pedido.
- Una obra de sección ya aplicada en «Sin proyecto» antes de esta spec, sin activar en
  «Con proyecto»: RF-11 la activa al aplicar o estudiar la siguiente obra, y lo dice.
- El punto más cercano cae justo en un extremo del tramo: RF-20 usa la barra.
- El flujo de «Con proyecto» no converge antes del enlace: no hay datos para RF-26 y no se
  crea el enlace salvo con los puntos de RF-31.
- Deshacer una carga nueva (007:RF-38) que partió un tramo: al borrar su variación el
  tramo vuelve a estar entero.
- Cancelación a mitad: no queda ninguna obra a medias (011:RF-41).

## Fuera de alcance

- Trazar el enlace siguiendo calles o un recorrido: va en línea recta.
- Elegir el enlace por un criterio económico o de pérdidas.
- Cambiar la troncal que usa el N-1 (011:RF-43) o la transferencia (011:RF-108).
- Obras de enlace entre más de dos alimentadores a la vez.
- Cerrar el enlace como parte de la obra: se deja abierto y lo cierra la transferencia o
  el operador.
- Partir tramos de baja tensión.

## Criterios de finalización

- Cada RF citado por al menos una prueba (`grep -rnoE "016:RF-[0-9]+" tests | sort -u`).
- Suite en verde con los datos reales (las tres `IGEA_*`).
- Prueba en DIgSILENT con IN111 y TA225: la troncal de IN111 pasa a 120 mm² en «Sin
  proyecto» y «Con proyecto», el enlace queda solo en «Con proyecto» partiendo un tramo de
  cada alimentador y abierto (IN111 a 10 kV, TA225 a 22,9 kV); las SED de IN111 que
  pasan, migradas a 22,9 kV en otra variación; y la transferencia de IN111 a TA225 se
  calcula por el enlace después de la migración.
- 007:RF-24, RF-30 y RF-31 y 011:RF-57 anotados con el cambio de esta spec.

## Dudas abiertas

Ninguna. Resueltas por el usuario el 2026-10-14: la troncal del N-1 y de la transferencia
no cambia (RF-10); toda la troncal pasa a 120 mm² (RF-6); el enlace se deja abierto entre
tensiones distintas (RF-39); el operador indica el nodo desde el que se migra (RF-51); la
distancia mínima la da el operador en la web (RF-20, RF-68); los dos puntos del enlace se
buscan por coordenadas solo en las troncales (RF-27, RF-28); las cargas nuevas también
se conectan solo en la troncal (RF-45).
