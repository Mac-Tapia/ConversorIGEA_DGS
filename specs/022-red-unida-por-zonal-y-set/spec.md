# Spec 022 — Red unida por zonal y SET

Estado: cumplida (revisión 033 del 2026-10-29) · implementada (2026-10-18) · Fecha: 2026-10-17

## Contexto y objetivo

Hoy la red unida pone una red externa por alimentador: cada uno es una isla con su fuente.
En NA203 + NA205 (2026-10-17) cada «External Grid» alimentaba su isla, y la calibración por
proyecto (021:RF-54) no tenía nada que acoplar. Los alimentadores de una misma SET comparten
su barra de media tensión, y la empresa los agrupa en zonales y sistemas eléctricos con su
sector típico y su norma (NTCSE, NTCSER). El usuario, el 2026-10-17, con la tabla pública
«Sistemas eléctricos Electrodunas» (4 zonales: Chincha, Pisco, Ica y Nasca; cada SET con sus
alimentadores): «propón la conversión por sistema eléctrico y SET en un solo DGS unido por
sistemas eléctricos y SET». El objetivo es un DGS con todos los alimentadores de la entrega
colgados de la barra de su SET y agrupados por zonal y sistema eléctrico, sin suponer nada
de una empresa en el código (constitución 13).

## Usuarios / actores

- Ingeniero de planificación desde la web: convierte la entrega entera y la importa en
  DIgSILENT como un proyecto.
- CLI en lote: la misma conversión.
- Los guiones de DIgSILENT (cargas, ajuste, obras, estudios) sobre ese proyecto.

## Historias de usuario

- H1: Como planificador quiero un solo DGS con todos los alimentadores en su SET y su zonal
  para estudiar la red como la opera la empresa.
- H2: Como planificador quiero que los alimentadores de una SET compartan su barra para que
  la calibración y las transferencias vean su acople.
- H3: Como planificador quiero agrupar resultados por sistema eléctrico para leer pérdidas y
  tensiones con su norma.
- H4: Como planificador quiero actualizar la tabla de la empresa cuando cambie sin tocar
  código.

## Requisitos funcionales (EARS)

Estructura de la empresa

- RF-1: DONDE el perfil de empresa trae una estructura, EL SISTEMA la leerá como zonales,
  cada zonal con sus SET, cada SET con sus alimentadores.
- RF-2: EL SISTEMA leerá de cada alimentador de la estructura su código, su SET, su
  sistema eléctrico (código y nombre), su sector típico y su norma.
- RF-3: El perfil de Electro Dunas traerá la estructura de la tabla pública «Sistemas
  eléctricos Electrodunas» (zonales Chincha, Pisco, Ica y Nasca).
- RF-4: CUANDO el operador sube en la web la tabla de la estructura en Excel, EL SISTEMA la
  usará en lugar de la del perfil para ese espacio.
- RF-5: SI la tabla subida tiene un alimentador sin SET, una SET sin zonal o un código
  repetido, ENTONCES EL SISTEMA la rechazará nombrando la fila.
- RF-6: MIENTRAS no haya estructura, EL SISTEMA convertirá la red unida como hasta ahora,
  con una red externa por alimentador.

Conversión unida por zonal y SET

- RF-7: DONDE hay estructura, EL SISTEMA escribirá en un solo DGS todos los alimentadores
  de la entrega.
- RF-8: EL SISTEMA pondrá una red (`ElmNet`) por zonal, con las SET y los alimentadores de
  ese zonal.
- RF-9: EL SISTEMA escribirá cada SET como una subestación con su código y su nombre («SET
  21 El Carmen»).
- RF-10: EL SISTEMA pondrá en cada SET una barra por cada tensión de media de sus
  alimentadores en la entrega (10 kV y 22,9 kV en Electro Dunas).
- RF-11: EL SISTEMA pondrá una red externa por barra de SET, con la consigna de tensión del
  perfil o 1,0 pu sin ella.
- RF-12: EL SISTEMA unirá la cabecera de cada alimentador a la barra de su SET y tensión
  con un interruptor de cabecera, en lugar de su red externa propia.
- RF-13: EL SISTEMA integrará en servicio, con su interruptor de cabecera cerrado, todo
  alimentador de la entrega, también los que la tabla marca «fuera de servicio» (usuario,
  2026-10-17: «no deberían estar fuera de servicio, tienes que integrarlo»).
- RF-14: EL SISTEMA definirá cada `ElmFeeder` en el cubículo de su interruptor de
  cabecera, hacia el alimentador.
- RF-15: EL SISTEMA escribirá cada sistema eléctrico como una zona de DIgSILENT con su
  código y su nombre, y asignará a ella los elementos de sus alimentadores.
- RF-16: EL SISTEMA guardará en cada zona su sector típico y su norma.
- RF-17: EL SISTEMA dibujará la cabecera de cada alimentador en sus coordenadas UTM de la
  entrega, en el mapa y en el diagrama.
- RF-18: EL SISTEMA situará la barra de cada tensión de una SET en las coordenadas de las
  cabeceras que cuelgan de ella, que coinciden (usuario, 2026-10-17: «cada cabecera
  coincide con la barra de 10 kV y 22,9 kV de la misma SET»).
- RF-18b: SI las cabeceras de una misma barra de SET no tienen las mismas coordenadas,
  ENTONCES EL SISTEMA pondrá la barra en las de la cabecera de menor código y lo avisará
  nombrando la SET.

Lo que no casa

- RF-19: SI un alimentador de la entrega no está en la estructura, ENTONCES EL SISTEMA lo
  pondrá en un grupo «Sin SET» con su red externa propia y lo avisará, sin bloquear.
- RF-20: SI un alimentador de la estructura no está en la entrega, ENTONCES EL SISTEMA lo
  listará en el informe de la conversión.
- RF-21: SI la tensión de la cabecera de un alimentador no casa con ninguna barra de su
  SET, ENTONCES EL SISTEMA creará la barra de esa tensión en la SET y lo avisará.

Medida por alimentador en la barra compartida

- RF-22: MIENTRAS varios alimentadores cuelgan de la misma barra de SET, EL SISTEMA medirá
  lo que entra en cada uno en su interruptor de cabecera, no en la red externa de la barra.
- RF-23: EL SISTEMA aplicará la medida de RF-22 en el ajuste a la máxima, en las cargas,
  en las obras y en los estudios.
- RF-24: CUANDO el operador calibra un proyecto unido por SET, EL SISTEMA calibrará juntos
  los alimentadores marcados (021:RF-54), con la consigna de tensión en la red externa de
  cada barra de SET (021:RF-61).

Puntos de enlace y oráculo de la red unida (usuario, 2026-10-17: «lo que debe identificar
son los puntos de enlace y abrirlos para ejecutar el flujo de potencia; ahí debe trabajar el
oráculo»)

- RF-26: EL SISTEMA identificará los puntos de enlace de la red unida: los nodos que
  comparten alimentadores distintos, de la misma SET o de SET distintas.
- RF-27: EL SISTEMA escribirá cada punto de enlace como un interruptor abierto entre los dos
  alimentadores, con su nombre, los dos alimentadores y sus dos SET.
- RF-28: CUANDO la red unida está armada, EL SISTEMA ejecutará el oráculo sobre ella entera
  (barras de SET, redes externas, interruptores de cabecera y enlaces abiertos) antes de
  escribir el DGS.
- RF-29: EL oráculo comprobará que cada barra alimentada lo está desde una sola barra de SET
  por los tramos y maniobras cerrados.
- RF-30: SI el oráculo encuentra un camino cerrado entre dos barras de SET, entre dos
  alimentadores o dentro de un mismo alimentador (un anillo), ENTONCES EL SISTEMA abrirá el
  punto de enlace de ese camino y lo dirá (usuario, 2026-10-17: los anillos «debe
  abrirlos»).
- RF-31: SI el camino cerrado de RF-30 no pasa por ningún punto de enlace, ENTONCES EL
  SISTEMA abrirá la maniobra o el tramo del camino más lejano de la barra de SET (el
  límite entre los dos alimentadores, o el punto del anillo más alejado de su cabecera) y
  lo dirá con su nombre.
- RF-32: EL oráculo calculará el flujo de potencia de la red unida con los enlaces abiertos
  y dará su veredicto por SET y por zonal.
- RF-33: SI el flujo del oráculo no converge, ENTONCES EL SISTEMA nombrará la SET cuya isla
  no converge y la barra de mayor error, y no lo dará por bueno.
- RF-34: EL SISTEMA dejará en el informe de la conversión cada punto de enlace abierto, con
  su motivo (RF-27, RF-30 o RF-31).

Calibración del sistema por barra de SET (usuario, 2026-10-17: «para hacer la calibración
de los sistemas se debe usar el máximo valor del Excel medidoralimentador en la columna
código alimentador Barra, con su medidor, su nivel de tensión y siglas: AL es Alto la Luna;
por ejemplo, la barra B-PA2T1, 22,9, PA, es la barra de 22,9 kV de la SET Paracas»)

- RF-35 a RF-36: no se usan (nunca se definieron: los requisitos de las barras de SET
  empezaron en RF-37).
- RF-37: EL SISTEMA leerá del libro de medidores por alimentador las filas de barra: las
  que en «código alimentador» dicen «Barra», con su medidor, su nivel de tensión y sus
  siglas.
- RF-38: EL SISTEMA asignará cada medidor de barra a la barra de la SET de sus siglas y su
  nivel de tensión, con las siglas de cada SET de la estructura del perfil (AL → SET 33 Alto
  la Luna, PA → SET 32 Paracas…).
- RF-39: CUANDO el operador calibra un proyecto unido por SET, EL SISTEMA tomará como
  objetivo de cada barra de SET con medidor la máxima, registro a registro, de la suma de
  sus medidores de esa tensión (los de cada transformador, T1 y T2).
- RF-40: EL SISTEMA tomará la fecha y hora del registro de RF-39 como el instante
  coincidente de todos los alimentadores de esa barra.
- RF-41: CUANDO se identifica la máxima de una barra de SET, EL SISTEMA calibrará cada
  alimentador de esa barra con su propio medidor en la misma fecha y hora de esa máxima,
  coincidente con el medidor de barra (021:RF-50), cada uno con su factor de escala y sus
  fijas con su EA/ERI (usuario, 2026-10-17: «los alimentadores de la misma barra se deben
  calibrar con la misma fecha del medidor de barra, con fecha coincidente»).
- RF-41b: EL SISTEMA dará en el informe, por barra de SET, lo que entra desde su red externa
  frente al medidor de barra en ese registro.
- RF-41c: SI un alimentador de la barra no tiene registro en esa fecha y hora, ENTONCES EL
  SISTEMA lo dirá y no lo calibrará (021:RF-53).
- RF-42: SI una barra de SET no tiene medidor de barra, ENTONCES EL SISTEMA calibrará cada
  alimentador de esa barra con la máxima de su propio medidor, como hasta ahora.
- RF-43: EL SISTEMA no usará los medidores de barra de 220 kV: la SET entra sin su
  transformador de potencia. (Cambiado por RF-84 el 2026-10-27: los de 60 kV sí se usan.)
- RF-44: DONDE un medidor de barra es de una central («Barra CT», «CTBarra»: CT_PEDREG en la
  barra de 10 kV de Pedregal), EL SISTEMA pondrá la central en esa barra con la P y Q
  medidas en el registro objetivo de la barra, como la central de 021:RF-35.
- RF-45: SI unas siglas del libro no están en la estructura, ENTONCES EL SISTEMA las tomará
  como una barra suelta propia (alimentadores nuevos: CHN, PO y Chiribamba en Electro
  Dunas, usuario 2026-10-17), con su red externa, a la que colgarán los alimentadores de la
  entrega con esas siglas, calibrada con su medidor, y lo dirá.
- RF-46: La estructura del perfil de Electro Dunas dará a SEIN las siglas SI (B-SI1T1 es su
  barra de 10 kV).

Una opción propia, sin mezclas (usuario, 2026-10-18: «este es otra opción, por sistema
eléctrico la conversión unida; dos o más son otras opciones de conversión en DGS; no debe
ser mezclado para nada los proyectos de conversión»)

- RF-47: EL SISTEMA ofrecerá la conversión por sistema eléctrico como una opción propia, aparte
  de unir dos o más alimentadores y de convertir por alimentador.
- RF-48: CUANDO el operador convierte por sistema eléctrico, elegirá un zonal o todos, y EL
  SISTEMA convertirá todos los alimentadores de la entrega de ese zonal (con todos, también
  los «Sin SET»).
- RF-49: EL SISTEMA nombrará el DGS por sistema eléctrico «SISTEMA_<zonal>», o
  «SISTEMA_ELECTRICO» con todos, y lo registrará como de tipo «sistema».
- RF-50: MIENTRAS el operador une dos o más alimentadores, EL SISTEMA no usará la estructura:
  la red unida queda como antes (RF-6).
- RF-51: EL SISTEMA no mezclará un DGS ni un proyecto de DIgSILENT por sistema eléctrico con
  los de unir ni con los de un alimentador: su nombre, su registro y su proyecto son propios.

Calibración por sistema eléctrico (usuario, 2026-10-18: «la calibración debe hacerse por
sistema eléctrico»)

- RF-52: CUANDO el operador calibra un proyecto por sistema eléctrico, EL SISTEMA calibrará
  a la vez, en los mismos flujos, todos los alimentadores del sistema que tengan medidor
  (021:RF-54), con la máxima de barra y su instante coincidente donde la barra tenga
  medidor (RF-39 a RF-46).
- RF-53: SI un alimentador del sistema no tiene medidor de alimentador ni de barra,
  ENTONCES EL SISTEMA lo dirá en el plan y en el resultado, y lo dejará con la demanda del
  archivo en los mismos flujos (Nasca, 2026-10-18: 15 de sus 17 alimentadores sin medidor).
- RF-54: CUANDO el operador elige un proyecto por sistema eléctrico en la calibración, EL
  SISTEMA propondrá todos los alimentadores del sistema y la máxima por barra de SET.
- RF-55: SI la demanda medida de un alimentador supera lo que su red puede dar (sus fijas
  más la potencia instalada de sus escaladas por el factor de potencia del perfil),
  ENTONCES EL SISTEMA no lo calibrará, lo dirá con las dos cifras y calibrará los demás
  (Chincha, 2026-10-18: TM106 medía 3 133 kW con unos 230 kVA instalados; su factor 13,7
  impedía converger al sistema entero).
- RF-56: EL SISTEMA dará una herramienta de línea de órdenes que, por la API de la web,
  convertirá, importará y calibrará un sistema eléctrico entero, retomará lo que el espacio
  ya tenga hecho y reintentará cuando la web corte una consulta mientras trabaja.

Reconstrucción por medida (usuario, 2026-10-18: «revisa en los archivos originales los tres
alimentadores; deberían estar completos; si no, debe reconstruirlos y activarlo». TM106 trae 4
tramos y mide 3 133 kW: su red está en la de TM104, a 78 m y sin el tramo que los une; TM101,
fuera de servicio y sin medidor, a 15 m de TM105)

- RF-57: DONDE el operador pide reconstruir un alimentador al convertir por sistema
  eléctrico, EL SISTEMA buscará el nodo de otro alimentador de la misma tensión más cercano
  a su red, hasta 100 m, y añadirá el tramo que falta entre los dos, anotado como
  reconstrucción.
- RF-58: CUANDO la medida del alimentador reconstruido es mayor que cero, EL SISTEMA abrirá,
  en el camino de la cabecera del otro al nodo de unión, el punto que deja aguas abajo la
  parte de su potencia instalada en la proporción de las dos medidas, y pasará lo de aguas
  abajo al reconstruido.
- RF-58b: SI el donante tiene medida, ENTONCES EL SISTEMA no le quitará toda su red: cuando
  ningún corte del camino deja la proporción, partirá su cabecera, de modo que el donante
  conserve con su interruptor las ramas de la cabecera cuya potencia instalada se acerque a
  su parte y el reconstruido reciba las demás (usuario, 2026-10-18: «TM104 sí existe, tiene
  su medidor; no puede quedar afuera para nada»; TM104 mide 31 kW, máxima propia 224 kW).
- RF-59: SI el alimentador reconstruido no tiene medidor, ENTONCES su medida será la máxima
  de su barra de SET menos las de los demás alimentadores de la barra en ese instante, y con
  cero o menos el tramo nuevo quedará abierto: activado sin carga pasada.
- RF-60: SI no hay nodo de otro alimentador de su tensión a menos de 100 m, ENTONCES EL
  SISTEMA lo dirá y convertirá el alimentador como está.
- RF-61: EL SISTEMA aceptará las reconstrucciones en la conversión por sistema de la web y
  la herramienta de RF-56 las pedirá con sus medidas.
- RF-63: MIENTRAS un alimentador esté reconstruido por medida, EL SISTEMA calibrará con el
  kVA de las SED que le asigna el DGS reconstruido, y no con el de la entrada original
  (TM106 seguía con sus 339 kW de la entrada y no se calibraba).
- RF-62: CUANDO se implementan los transformadores de las fijas sobrecargadas de varios
  alimentadores de un proyecto (020:RF-15), EL SISTEMA los cambiará todos y recalibrará el
  proyecto una sola vez (Chincha, 2026-10-18: CA101, PE102 y PN103 no convergían por sus
  fijas sobre transformadores pequeños; uno a uno, cada uno recalibraba el sistema).

Una red por SET en un zonal grande (usuario, 2026-10-23: «el sistema eléctrico Nasca hay que
dividirlo por sus SET; la hoja en DIgSILENT no alcanza; mejor por SET». El zonal Nasca va de
la costa a la sierra, de SET 51 Nasca a SET 56, y su diagrama único no cabe en la hoja)

- RF-64: DONDE la estructura marca un zonal como dividido por SET, EL SISTEMA pondrá en ese
  zonal una red (`ElmNet`) por cada SET con alimentadores en la entrega, en lugar de la red
  del zonal de RF-8.
- RF-65: EL SISTEMA dará a cada red de RF-64 su propio diagrama, con la hoja a la medida de
  esa SET y sus alimentadores.
- RF-66: EL SISTEMA nombrará cada red de RF-64 con su zonal y su SET («Nasca SET 52
  Llipata»).
- RF-67: MIENTRAS un zonal no esté marcado como dividido por SET, EL SISTEMA mantendrá una
  sola red para todo el zonal (RF-8).
- RF-68: EL SISTEMA pondrá cada punto de enlace entre dos SET de un zonal dividido en la red
  de la SET de menor código, abierto (RF-27) y dibujado en su diagrama.
- RF-69: EL SISTEMA importará, verificará el «Caso base» y calibrará por sistema eléctrico un
  proyecto con redes por SET igual que uno con una red por zonal.
- RF-70: La estructura del perfil de Electro Dunas marcará el zonal Nasca como dividido por
  SET.

SET y alimentadores nuevos de la entrega (usuario, 2026-10-23: «en los TXT cargados existe
una nueva SET que no está en el sistema eléctrico y no carga para conversión, SET Chincha
Nueva (CHN); sus alimentadores deben considerarse, y otros que existan, cada vez que se
cargan archivos nuevos, TXT, MDB y VNR-GIS». La entrega RED_231026 trae 101 alimentadores y
siete no estaban en la tabla de la empresa: CN101, CN102, CN103 y CN201, de la SET nueva;
PA219, junto a las cabeceras de Paracas; COH101 y SC215. Quedaban «Sin SET» y la conversión
por zonal los dejaba fuera)

- RF-71: CUANDO un alimentador de la entrega no está en la estructura y sus siglas (las
  letras de su código antes del número: «PA» de PA219) son las de una SET de la estructura,
  EL SISTEMA lo pondrá en esa SET.
- RF-72: CUANDO un alimentador de la entrega no está en la estructura y sus siglas son las
  de alimentadores de la estructura que están todos en una misma SET, EL SISTEMA lo pondrá
  en esa SET.
- RF-73: SI las siglas de un alimentador nuevo no llevan a ninguna SET (RF-71, RF-72),
  ENTONCES EL SISTEMA creará una SET deducida, con código «SET» y sus siglas, que reúna a
  todos los alimentadores nuevos con esas siglas.
- RF-74: EL SISTEMA pondrá cada SET deducida de RF-73 en el zonal del alimentador de la
  estructura cuya cabecera esté más cerca de la de alguno de sus alimentadores.
- RF-75: SI ningún alimentador de una SET deducida tiene coordenadas en su cabecera,
  ENTONCES EL SISTEMA lo dejará «Sin SET» (RF-19).
- RF-76: EL SISTEMA dará a un alimentador colocado por RF-71 o RF-72 el sistema eléctrico
  que comparten los alimentadores de su SET, y ninguno si no comparten uno; a los de una
  SET deducida, ninguno.
- RF-77: EL SISTEMA aplicará RF-71 a RF-75 a toda entrega que se cargue, sea TXT, MDB o
  VNR-GIS, y con la estructura del perfil o la subida en Excel, en la web y en el CLI.
- RF-78: EL SISTEMA avisará de cada alimentador colocado por RF-71 a RF-74, con su SET, su
  zonal y la regla que lo colocó, en el resumen de la estructura y en el informe de la
  conversión, sin bloquear.
- RF-79: La estructura del perfil de Electro Dunas tendrá la SET Chincha Nueva (siglas CN),
  en el zonal Chincha, con CN101, CN102, CN103 y CN201 en el sistema eléctrico SE0043
  Chincha (usuario, 2026-10-23).
- RF-80: La estructura del perfil de Electro Dunas pondrá PO101, de la SET 35 Pampa de
  Ocas, en el sistema eléctrico SE0046 Pisco (usuario, 2026-10-23).
- RF-81: CUANDO una SET de la estructura declare varias siglas, EL SISTEMA tratará como el
  mismo alimentador los códigos que solo difieren en esas siglas: en la estructura, en el
  libro de medidores (sus medidores y si es de la red) y en la barra de su SET. La SET
  nueva Chincha Nueva viene en RED_231026 como CN101 a CN201 y en los libros de la empresa
  como CHN101 a CHN201, con el medidor de barra CHNB1T1; en la web sus alimentadores no
  encontraban medidor y su barra quedaba suelta (usuario, 2026-10-27). El perfil de
  Electro Dunas da a la SET CHN las siglas CN y CHN; sin siglas declaradas no se casa nada.
- RF-82: La web tendrá, junto a «Convertir sistema», un desplegable con las SET de la
  entrega (las del sistema elegido, o todas), cada una con sus alimentadores, y un botón
  «Convertir SET» que convierte solo esa SET como en su sistema: su red, sus barras y la
  red externa de cada barra (usuario, 2026-10-27: «debe haber botón para conversión por
  sistema y SET»). La API (`/convert/sistema`) aceptará `sets` y rechazará una SET que
  no esté en la estructura.
- RF-83: La web pedirá la estructura al cargar la entrega, no al enfocar un desplegable:
  el de sistemas estaba desactivado sin ella, nunca recibía el foco y no aparecía ningún
  sistema ni la SET nueva Chincha Nueva (usuario, 2026-10-27).
- RF-84: CUANDO el libro de medidores traiga filas de barra de 60 kV (columna ALIMENTADOR
  «Barra…», MEDIDOR, nivel de tensión y SET), EL SISTEMA calibrará cada sistema eléctrico
  con la máxima de la barra de 60 kV de cada SET: la suma, registro a registro, de sus
  medidores de 60 kV, y todos los alimentadores de esa SET, de cualquier tensión, en esa
  fecha y hora (usuario, 2026-10-27: «la calibración de cualquier sistema eléctrico debe
  ser con el máximo valor de barras en 60 kV, emparejando la columna alimentador, que ahí
  dice barra de 60 kV, MEDIDOR y columna SET»). Prevalece sobre la barra de media de RF-38.
- RF-85: EL SISTEMA reconocerá la columna «SET» del libro de medidores como la de las
  siglas, y su valor por las siglas de la SET, su código («SET 21») o su nombre.
- RF-86: SI una SET no tiene medidor de barra de 60 kV, ENTONCES EL SISTEMA seguirá con su
  barra de media (RF-38 a RF-42); SI un medidor de 60 kV no es de ninguna SET de la
  estructura, ENTONCES lo dirá y no lo usará, sin barra suelta; los de 220 kV no se usan.
  SI un medidor de una barra no tiene registros en el periodo (B-PA6T1 en julio de 2026),
  ENTONCES EL SISTEMA lo dirá y sumará la barra con los demás. Una columna SET vacía se
  deduce del nombre del medidor (TMB6T2 → SET 22), y un medidor en dos SET se avisa.
- RF-87: Una SET tiene 1, 2 o 3 transformadores (T1, T2, T3 en el rótulo «Barra60KV_T2» o
  en el medidor, B-PA6T2, TA6TR2). EL SISTEMA sumará, registro a registro, los medidores
  de todos sus transformadores en cada barra (la de 60 kV y cada una de media), dirá de
  qué transformador es cada medidor en el resultado y el Registro, y avisará si los
  transformadores medidos en 60 kV no son los mismos que en media (usuario, 2026-10-27).
- RF-88: Los medidores que empiezan por CT son centrales térmicas. La web listará las del
  libro con su SET y su nivel, y el operador dirá si cada una está en la barra de su SET
  (CT_PEDREG, en la de 10 kV de Pedregal) o en un tramo de media de un alimentador (la de
  Nasca, CT_BH4 NA, en la troncal de 22,9 kV de NA205); la propuesta sale de
  `centrales_termicas` del perfil. EL SISTEMA pondrá la de barra como generador en esa
  barra con su medida en el instante de la barra de 60 kV, y la de tramo no la pondrá en
  la barra: la medirá con su alimentador, en ese mismo instante (021:RF-28) (usuario,
  2026-10-27).
- RF-89: SI la barra de 60 kV de una SET marca, en su instante, menos de la mitad de lo
  que dan sus barras de media menos la generación de sus centrales, ENTONCES EL SISTEMA lo
  dirá (otra unidad o un medidor mal configurado: CHNB6T1 de Chincha Nueva, 8,3 frente a
  ~3 300 kW, en DIgSILENT el 2026-10-28) y usará igual su instante, que no cambia con la
  unidad.
- RF-90: CUANDO una SET de la estructura declare varias siglas, la primera será la
  canónica, y EL SISTEMA nombrará con ella al alimentador desde la carga de la fuente
  (inventario, DGS, web y calibración): la red de RED_231026 trae CN101 a CN201 y la SET
  Chincha Nueva se declara `["CHN", "CN"]`, así que son CHN101 a CHN201 (usuario,
  2026-10-28: «debes corregirlo con los CHN desde la carga de los TXT en la web»). Sin
  perfil, el nombre de la red tal cual.
- RF-91: EL SISTEMA buscará la máxima de la barra de 60 kV solo entre los registros que
  tienen también todos los medidores de los alimentadores de su SET, para que el instante
  coincida en todos; si la máxima sin esa condición cae en un registro que falta en alguno,
  lo dirá con las dos fechas (CHNB6T1 dio el 2026-07-24 11:45 y CHN101, CHN102 y CHN201 no
  tenían ese registro y quedaban sin calibrar, DIgSILENT, 2026-10-28).
- RF-92: no se usa (nunca se definió: la herramienta de las hojas entró como RF-93).
- RF-93: EL SISTEMA dará una herramienta de solo lectura que compare en DIgSILENT la hoja de
  cada diagrama con sus gráficos y conectores y diga, por diagrama, su formato, su
  orientación y si todo cae dentro. Usuario, 2026-10-29: no había ninguna en `tools/`
  (`prueba_representacion.py` mira el DGS). Medido ese día en Nasca por SET: DIgSILENT crea
  la hoja a la medida y la orienta él (vertical la SET 52, la 53 y la 56, más altas que
  anchas); los vectores de los conectores traen −1 en los puntos sin usar, que no son del
  dibujo. No hace falta orientar las hojas al importar.

Informe

- RF-25b: EL SISTEMA omitirá una SET, un sistema eléctrico o un zonal de la estructura que
  no tenga ningún alimentador en la entrega, y escribirá todo el que tenga alguno
  (usuario, 2026-10-17: «si no existen, los SER deben omitirse, pero si tienen sus redes no
  se deben omitir»).
- RF-25: EL SISTEMA dará en el informe de la conversión, por zonal y SET, sus alimentadores
  convertidos, los que faltan y los que quedaron «Sin SET».

## Requisitos no funcionales

- Determinismo: el DGS es idéntico byte a byte con `workers=1` y `workers>1`; el orden de
  zonales, SET y alimentadores es el de sus códigos.
- Escala: ninguna regla depende del número de alimentadores, SET ni zonales; la estructura
  se indexa una vez, no se recorre por alimentador.
- Universal (constitución 13): zonales, SET, sistemas eléctricos y normas vienen del perfil
  o de la tabla subida; el código no conoce ningún nombre de Electro Dunas.
- Las fuentes son independientes: TXT, MDB y VNR-GIS se convierten igual con la estructura.
- Idioma: español.

## Casos límite

- Disposición reducida y completa del TXT: el resultado es el mismo.
- Una SET con alimentadores de 10 kV y de 22,9 kV: dos barras y dos redes externas.
- Un alimentador partido en varias redes en la base (PE104 en 260924.mdb): todas sus
  partes cuelgan de la misma barra.
- Una SET, un sistema eléctrico (SER Chincha, SER Nasca) o un zonal sin alimentadores en
  la entrega: no se escribe (RF-25b).
- Una entrega de un solo zonal: un solo `ElmNet`.
- Enlaces entre alimentadores (`ElmCoup` abiertos) entre SET o zonales distintos: siguen
  abiertos y se dibujan.
- Un alimentador que aparece con dos SET en la tabla: error de RF-5.
- Dos alimentadores de SET distintas unidos por un tramo cerrado en el GIS: el camino se
  abre en su punto de enlace (RF-30) y el flujo corre con cada SET por su lado.
- Un punto de enlace entre tensiones distintas (10 y 22,9 kV): abierto, como en 016.
- La central térmica de un alimentador (spec 021): sigue en su variación de «Sin proyecto».

## Fuera de alcance

- El transformador de potencia AT/MT de cada SET y la red de transmisión: la SET entra con
  barras de media y red externa (el usuario, 2026-10-17).
- Los clientes por alimentador de la tabla (columnas por fecha): no se usan en la red.
- Migrar los proyectos ya importados en DIgSILENT: hay que importar el DGS nuevo.
- Las transferencias entre SET o zonales distintos.
- Asignar cada alimentador al transformador T1 o T2 de su SET: la barra de cada tensión
  suma los medidores de sus transformadores (RF-39).
- Un DGS por zonal además del unido.
- Marcar un zonal como dividido por SET desde la tabla de Excel subida en la web: la marca
  va en la estructura del perfil.
- Dividir por SET el proyecto ya importado: hay que importar el DGS nuevo.
- Guardar en el perfil las SET deducidas (RF-73): se deducen de nuevo con cada entrega; la
  que se confirme se escribe a mano en la estructura, como Chincha Nueva (RF-79).
- Deducir el nombre o el sistema eléctrico de una SET deducida.

## Criterios de finalización

- Cada RF citado por al menos una prueba (`grep -rnoE "022:RF-[0-9]+" tests`).
- Suite en verde con los TXT, la MDB y VNR-GIS reales, y DGS idéntico con `workers=1` y
  `workers>1`.
- Probado en DIgSILENT: la entrega de Electro Dunas importada como un proyecto, con los
  cuatro zonales, sus SET y un flujo que converge; NA203 + NA205 calibrados juntos en SET
  51 Nasca.

## Dudas abiertas

Ninguna. Resueltas el 2026-10-17: los alimentadores «fuera de servicio» de la tabla se integran
(RF-13); los anillos se abren (RF-30); las cabeceras en sus coordenadas UTM y las barras de
SET en ellas (RF-17, RF-18); lo que no tiene redes se omite (RF-25b); siglas sin SET, barra suelta propia (RF-45); SI
es SEIN (RF-46).
