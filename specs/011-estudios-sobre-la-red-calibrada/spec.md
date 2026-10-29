# Spec 011 — Estudios y obras de mejora sobre la red calibrada

Estado: implementada (revisión 033 del 2026-10-29) · aprobada (2026-10-11) · Fecha: 2026-10-11 · Origen: petición del usuario, 2026-10-11 («los estudios
se deben hacer cuando se hizo la calibración en las cabeceras y la actualización de cargas por
SED, como fijas y escaladas»)

## Contexto y objetivo

Las specs 006 a 008 dejan el proyecto de DIgSILENT en un estado preciso: cada alimentador
marcado ajustado a la máxima medida en su cabecera, en su propia variación; las SED con
clientes importantes con demanda **fija** (la de esos clientes) y las demás **escaladas**
por kVA hasta cuadrar; encima, las demandas en bloque en su variación; y las cargas
nuevas, una variación por carga (spec 007). Solo sobre ese estado un estudio dice algo de
la red real: sobre la red sin calibrar mide las demandas de catálogo del export, no la
punta.

Hoy los estudios no conocen ese estado:

- `studies.py` recoge los estudios de PowerFactory y qué dato falta para cada uno, y
  `tools/base_scenario.py` los ejecuta, pero sobre el caso que se acaba de importar del
  DGS, sin variaciones de ajuste ni de demandas.
- La web no ofrece ningún estudio: después de calibrar e integrar, el operador abre
  DIgSILENT y los lanza a mano, eligiendo él qué variaciones activa en qué caso.
- Nada impide que un estudio que escala cargas mueva también las SED fijas y deshaga el
  cuadre de la cabecera sin avisar.
- No se pueden ejecutar los guiones DPL o Python que el operador ya tiene en su proyecto.

El usuario fija el 2026-10-11 cómo se ordena el proyecto: tres casos de estudio.
**Caso base**, la red como estaba, sin calibrar; **Sin proyecto**, una copia con la
calibración y las demandas por SED, donde se hacen los estudios; y **Con proyecto**, una
copia de la anterior con todas las cargas nuevas, donde se repiten los mismos estudios.
Lo que se evalúa es la diferencia entre con proyecto y sin proyecto.

Sobre esos casos el usuario pide además (2026-10-11) evaluar **obras de mejora**, cada
una en variaciones nuevas activas en «Sin proyecto», en «Con proyecto» o en los dos:
banco de condensadores, reconectador, regulador de tensión, cambio de sección de los
cables de la troncal, incremento de una terna y cambio del nivel de tensión del
alimentador (por ejemplo, de 10 a 22,9 kV). En DIgSILENT los **tipos** (`TypLne`,
`TypTr2`, `TypVoltreg`) están en la biblioteca del proyecto y no los graba ninguna
variación: cambiar un tipo cambia todos los elementos que lo usan en todos los casos.
Si una obra de «Con proyecto» tocara el tipo, cambiaría también «Sin proyecto» y podría
dejarlo sin converger. Por eso una obra nunca edita un tipo existente: crea una copia y
la asigna dentro de su variación, que sí es de un solo caso.

Se buscaron en GitHub colecciones de DPL para estudios de distribución (2026-10-11). No
hay ninguna reutilizable: las útiles son GPL o no tienen licencia, y los estudios que
interesan son comandos propios de PowerFactory que ya están en `studies.py`.

## Usuarios / actores

- Ingeniero de planificación que, desde la web, estudia un proyecto de DIgSILENT ya
  calibrado (specs 006 y 008), con las demandas actualizadas y las cargas nuevas
  conectadas (specs 007 y 008).
- DIgSILENT PowerFactory 2024, por su API de Python, en el carril `powerfactory`.

## Historias de usuario

- H1: Como ingeniero quiero los estudios en un caso «Sin proyecto» con la red calibrada,
  sin elegir yo las variaciones, para no estudiar por error la red sin ajustar.
- H2: Como ingeniero quiero los mismos estudios en un caso «Con proyecto» con todas las
  cargas nuevas, y la diferencia entre los dos, para evaluar el efecto de las cargas.
- H3: Como ingeniero quiero conservar el caso original como «Caso base», para volver a la
  red tal como vino.
- H4: Como ingeniero quiero que las SED fijas sigan fijas durante los estudios, para que la
  demanda de los clientes importantes no se reparta como la del resto.
- H5: Como ingeniero quiero los resultados por alimentador en la web y en un fichero, para
  no copiarlos de la ventana de salida de DIgSILENT.
- H6: Como ingeniero quiero ejecutar un guion DPL o Python de mi proyecto en esos casos,
  para aprovechar los guiones que ya tengo.
- H7: Como ingeniero quiero modelar obras de mejora en variaciones propias y activarlas en
  el caso que elija, para comparar la red con y sin cada obra.
- H8: Como ingeniero quiero que una obra no cambie ningún tipo compartido, para que «Sin
  proyecto» siga dando lo mismo y siga convergiendo.
- H9: Como ingeniero quiero saber cuánta carga puede pasar un alimentador a otro y hasta
  qué seccionador, en los dos sentidos, para planificar maniobras y respaldos.
- H10: Como ingeniero quiero saber cuánto margen le queda al enlace después de transferir,
  para saber si la transferencia aguanta el crecimiento de la demanda.

## Requisitos funcionales (EARS)

Los tres casos de estudio

- RF-1: CUANDO el operador prepara los estudios, EL SISTEMA dejará en el proyecto tres
  casos de estudio: «Caso base», «Sin proyecto» y «Con proyecto».
- RF-2: EL SISTEMA tomará como «Caso base» el caso de estudio en que se hizo la
  calibración y le dará ese nombre.
- RF-3: EL SISTEMA dejará el «Caso base» sin activas las variaciones del ajuste, de las
  demandas en bloque ni de las cargas nuevas.
- RF-4: SI «Sin proyecto» no existe, ENTONCES EL SISTEMA lo creará como copia del «Caso
  base».
- RF-5: SI «Con proyecto» no existe, ENTONCES EL SISTEMA lo creará como copia de «Sin
  proyecto».
- RF-6: SI ya existen, ENTONCES EL SISTEMA reutilizará los casos «Sin proyecto» y «Con
  proyecto» y solo cambiará qué variaciones tienen activas.
- RF-7: EL SISTEMA activará en «Sin proyecto» la base calibrada: la variación del ajuste
  de cada alimentador marcado y, si existe, la de las demandas en bloque.
- RF-8: EL SISTEMA activará en «Con proyecto» la base calibrada y, a la vez, las
  variaciones de todas las cargas nuevas de los alimentadores marcados (spec 007).
- RF-9: SI no hay ninguna variación de carga nueva, ENTONCES EL SISTEMA no ejecutará los
  estudios en «Con proyecto» y lo dirá.
- RF-10: SI ya hay en el proyecto otro caso de estudio con uno de los tres nombres y no es
  el que creó el sistema, ENTONCES EL SISTEMA no lo tocará y pedirá al operador que lo
  renombre.
- RF-46: EL SISTEMA dará a cada uno de los tres casos su propio escenario de operación,
  activo en ese caso y en ningún otro.
- RF-47: CUANDO crea «Sin proyecto» o «Con proyecto», EL SISTEMA les dará como escenario
  una copia del que tenga el caso del que salen, con el nombre del caso.
- RF-48: SI el caso original no tiene escenario de operación, ENTONCES EL SISTEMA creará
  uno para cada caso con el nombre del caso.
- RF-49: EL SISTEMA ejecutará los estudios de cada caso con su escenario de operación
  activo y lo nombrará en el informe.
- RF-50: EL SISTEMA dejará activa en «Sin proyecto» y «Con proyecto» solo la variación del
  último ajuste de cada alimentador, y desactivará en ellos las de ajustes anteriores sin
  borrarlas.
- RF-11: CUANDO terminan los estudios, o se cancelan, EL SISTEMA dejará activo el caso de
  estudio que estaba activo al empezar.

Dónde trabajan las specs 006 a 008 una vez creados los casos

- RF-51: MIENTRAS existan los tres casos, EL SISTEMA aplicará el ajuste a la máxima y las
  demandas en bloque en «Sin proyecto».
- RF-52: MIENTRAS existan los tres casos, EL SISTEMA aplicará las cargas nuevas en «Con
  proyecto».
- RF-53: MIENTRAS existan los tres casos, EL SISTEMA no aplicará nada en el «Caso base».
  *Cambio del 2026-10-12 (006:RF-28):* salvo la demanda final del ajuste, que se graba
  también en el escenario del «Caso base»: el escenario base es la red ajustada a la
  máxima (usuario). El «Caso base» sigue sin las variaciones activas (RF-3).
- RF-54: CUANDO se aplica un ajuste o unas demandas en «Sin proyecto», EL SISTEMA activará
  también sus variaciones en «Con proyecto», para que las cargas nuevas sigan sobre la
  red calibrada.
- Aclaración de RF-54 (033, 2026-10-29): desde 014:RF-4 y 015:RF-19 y RF-26 el ajuste y las
  demandas no crean variaciones: se graban en los escenarios de «Sin proyecto» y de «Con
  proyecto», y así llegan a «Con proyecto» sin activar nada.
- RF-55: EL SISTEMA grabará el ajuste, las demandas y las cargas nuevas en sus variaciones,
  desactivando el escenario de operación del caso mientras escribe y restaurándolo al
  terminar, como hacen hoy las specs 004 y 006.
  *Cambio del 2026-10-12:* al restaurarlo, el escenario manda sobre la variación; por
  eso el ajuste y las demandas se graban además en los escenarios (006:RF-27, RF-28;
  004:RF-54, RF-55).

Base calibrada

- RF-12: EL SISTEMA tomará como base calibrada la del último ajuste aplicado en el
  proyecto, la misma que la spec 007 propone para las cargas (RF-1 y RF-37 de la 007).
- RF-13: SI el proyecto no tiene ningún ajuste aplicado, ENTONCES EL SISTEMA no preparará
  los casos y dirá que primero hay que calibrar.
- RF-14: SI un alimentador marcado no tiene variación de ajuste, o su ajuste falló,
  ENTONCES EL SISTEMA lo dejará fuera de los estudios y lo listará con el motivo.
- RF-15: SI el ajuste de un alimentador no cuadró, ENTONCES EL SISTEMA lo estudiará y lo
  avisará en el informe con su error en la cabecera, como la base de la spec 007 (RF-34).
- RF-16: SI una variación de la base ya no existe en el proyecto, ENTONCES EL SISTEMA no
  ejecutará ningún estudio y la nombrará.
- RF-17: CUANDO va a ejecutar los estudios de un caso, EL SISTEMA ejecutará antes su flujo
  de carga y no ejecutará los estudios de ese caso si no converge.

SED fijas y escaladas

- RF-18: EL SISTEMA marcará en DIgSILENT como no ajustables por el escalado de cargas las
  cargas de las SED con clientes importantes, según el origen que el ajuste dio a cada una
  (spec 006, RF-5).
- RF-19: EL SISTEMA marcará como ajustables por el escalado de cargas las cargas de las
  SED repartidas por kVA (spec 006, RF-8).
- RF-20: EL SISTEMA ejecutará los estudios sin el escalado de cargas por alimentador, para
  que lo que entra por la cabecera siga siendo la demanda del ajuste.
- RF-21: CUANDO termina el flujo de carga de «Sin proyecto», EL SISTEMA comparará lo que
  entra por la cabecera de cada alimentador con el objetivo del ajuste y avisará si
  difiere más que la tolerancia del ajuste.
- RF-22: EL SISTEMA no modificará la demanda de ninguna carga al ejecutar un estudio.

Qué estudios

- RF-23: EL SISTEMA ofrecerá en esta iteración estos estudios del catálogo de
  `studies.py`: flujo de carga equilibrado, flujo de carga desequilibrado, contingencias
  N-1, troncal, punto de apertura óptimo, perfil de tensión y balance de fases.
- RF-24: EL SISTEMA listará los demás estudios del catálogo con el dato que les falta, sin
  permitir ejecutarlos.
- RF-25: EL SISTEMA permitirá elegir uno o varios estudios y los ejecutará, en un solo
  trabajo, primero en «Sin proyecto» y después los mismos en «Con proyecto».
- RF-26: EL SISTEMA ejecutará los estudios que proponen cambios en la red (punto de
  apertura, perfil de tensión, balance de fases) sin aplicar esos cambios al proyecto, y
  dará la propuesta en el informe.

Guiones del operador

- RF-27: EL SISTEMA listará los guiones DPL (`ComDpl`) y Python (`ComPython`) del caso de
  estudio y de la carpeta de guiones del proyecto.
- RF-28: CUANDO el operador ejecuta un guion, EL SISTEMA lo ejecutará en «Sin proyecto» y
  en «Con proyecto» con los valores de sus parámetros de entrada que el operador escriba.
- RF-29: CUANDO termina un guion, EL SISTEMA devolverá por caso su código de salida y el
  texto que escribió en la ventana de salida de DIgSILENT.
- RF-30: SI un guion devuelve un código de error, ENTONCES EL SISTEMA lo informará con ese
  código y su texto de salida, y seguirá con el siguiente estudio.

Resultados

- RF-31: CUANDO termina un estudio, EL SISTEMA informará por caso y por alimentador si
  converge, la tensión mínima y máxima con la barra de cada una, el elemento más cargado
  con su cargabilidad, lo que entra por la cabecera y las pérdidas.
- RF-32: EL SISTEMA informará por alimentador la diferencia entre «Con proyecto» y «Sin
  proyecto» en cada valor de RF-31.
- RF-33: EL SISTEMA listará por caso y por alimentador las barras fuera de los límites de
  tensión y los elementos por encima del límite de cargabilidad.
- RF-34: EL SISTEMA marcará las violaciones que aparecen en «Con proyecto» y no en «Sin
  proyecto».
- RF-35: EL SISTEMA tomará los límites de tensión y de cargabilidad del perfil de empresa,
  y el operador podrá cambiarlos antes de ejecutar.
- RF-36: CUANDO termina el contingencias N-1, EL SISTEMA listará por caso y por
  contingencia los elementos que quedan sobrecargados y las barras fuera de límites.
- RF-43: EL SISTEMA definirá las contingencias N-1 como una por cada tramo de la troncal
  de los alimentadores marcados, y ninguna en las derivaciones.
- RF-44: CUANDO se elige el contingencias N-1, EL SISTEMA calculará antes la troncal de
  cada caso, aunque el operador no la haya elegido.
- RF-45: SI un alimentador no tiene troncal calculada, ENTONCES EL SISTEMA lo dejará fuera
  del contingencias N-1 y lo dirá.
- RF-37: EL SISTEMA guardará los resultados de cada trabajo en un fichero descargable con
  una fila por caso, alimentador y estudio, y en otro con una fila por violación.
- RF-38: EL SISTEMA dirá en el informe qué variaciones estaban activas en cada caso.

Ejecución

- RF-39: EL SISTEMA ejecutará cada estudio o guion en un proceso aparte, con un límite de
  tiempo que el operador puede cambiar.
- RF-40: SI un estudio supera su límite de tiempo, ENTONCES EL SISTEMA lo terminará, lo
  informará como no terminado y seguirá con el siguiente.
- RF-41: SI el operador cancela, ENTONCES EL SISTEMA terminará el estudio en curso, no
  empezará otro y conservará los resultados de los terminados.
- RF-42: EL SISTEMA ofrecerá las obras y los estudios como paso «4 · Obras y estudios» de
  la pestaña «Cargas en DIgSILENT», después de la integración (spec 008), con el mismo
  proyecto y los mismos alimentadores marcados.
- RF-98: EL SISTEMA presentará el paso 4 en tres partes, en este orden: «4.1 Obras de
  mejora», «4.2 Estudios» y «4.3 Transferencia de carga».

Obras de mejora: reglas comunes

En DIgSILENT 2024 (comprobado en `datascheme.db` el 2026-10-11) cada obra es: banco de
condensadores, un `ElmShnt` capacitivo (`shtype`, `qcapn`, `ncapx`, `ushnm`), sin tipo;
reconectador, un interruptor (`ElmCoup` o `StaSwitch`) con un relé `ElmRelay` de tipo
reconectador (`TypRecl`); regulador de tensión, un `ElmVoltreg` con su `TypVoltreg`;
sección de cable, el `typ_id` del `ElmLne`; una terna más, `ElmLne.nlnum`; nivel de
tensión, `ElmTerm.uknom` de las barras de media, `TypLne.uline` y `TypTr2.utrn_h`.

- RF-56: DONDE el operador define obras de mejora, EL SISTEMA creará una variación nueva
  por obra, con un nombre que diga la obra y el alimentador, sin repetir el de una
  variación existente.
- RF-57: EL SISTEMA activará cada obra solo en el caso o los casos que elija el operador:
  «Sin proyecto», «Con proyecto» o los dos.
  **Cambiado por 016:RF-11 a RF-14 (2026-10-15):** una obra en «Sin proyecto» va también en «Con proyecto», pedirla solo en «Sin proyecto» se rechaza, y el enlace y la migración van solo en «Con proyecto».
- RF-58: EL SISTEMA no activará nunca una obra en el «Caso base».
- RF-59: EL SISTEMA no modificará ningún tipo existente del proyecto.
- RF-60: CUANDO una obra necesita un tipo con otros datos que el que tiene el elemento,
  EL SISTEMA creará una copia del tipo con los datos nuevos y la asignará al elemento
  dentro de la variación de la obra.
- RF-61: EL SISTEMA nombrará la copia de un tipo con el nombre del original y el cambio
  (la tensión con el mismo sufijo que pone el conversor, `_22_9kV`, o la sección).
- RF-62: SI ya existe una copia con el mismo nombre y los mismos datos, ENTONCES EL
  SISTEMA la reutilizará en lugar de crear otra.
- RF-63: SI ya existe un tipo con ese nombre y otros datos, ENTONCES EL SISTEMA no lo
  reutilizará, creará la copia con otro nombre libre y lo dirá.
- RF-64: CUANDO termina de crear las obras, EL SISTEMA ejecutará el flujo de carga de
  «Sin proyecto» y comprobará que, en los alimentadores sin obras en ese caso, la
  cabecera y la tensión mínima son las mismas que antes de crearlas.
- RF-65: SI la comprobación de RF-64 encuentra una diferencia, ENTONCES EL SISTEMA lo
  dirá con el alimentador y el valor, porque significa que una obra tocó algo compartido.
- RF-66: CUANDO una obra queda creada, EL SISTEMA ejecutará el flujo de carga en cada caso
  en que está activa e informará si converge.
- RF-67: SI con una obra el flujo de un caso no converge, ENTONCES EL SISTEMA la dejará
  inactiva en ese caso, la conservará en el proyecto y dará el diagnóstico de la spec 006
  (RF-15).
- RF-68: EL SISTEMA listará en el informe de los estudios las obras activas en cada caso.
- RF-69: CUANDO se simula, EL SISTEMA dirá por obra los elementos que cambiaría, los
  tipos que copiaría y el nombre de su variación, sin escribir en el proyecto.

Obras de mejora: entrada manual con las librerías de DIgSILENT

El operador define cada obra a mano, eligiendo los elementos y los tipos en listas que
salen del propio DIgSILENT, y puede traer tipos de otros proyectos o estudios (usuario,
2026-10-11).

- RF-70: EL SISTEMA recibirá las obras una a una en un formulario de la web, sin libro
  Excel.
- RF-88: EL SISTEMA ofrecerá en el formulario, para elegir, los alimentadores marcados y,
  del alimentador elegido, sus barras y sus tramos leídos del proyecto de DIgSILENT.
- RF-89: EL SISTEMA ofrecerá para elegir los tipos de la clase que pide la obra (`TypLne`,
  `TypTr2`, `TypVoltreg`, `TypRecl`) que hay en la biblioteca del proyecto.
- RF-90: EL SISTEMA ofrecerá también los tipos de esa clase de la biblioteca global de
  DIgSILENT.
- RF-91: DONDE el operador elige otro proyecto de DIgSILENT como origen, EL SISTEMA
  ofrecerá también los tipos de esa clase de la biblioteca de ese proyecto.
- RF-92: CUANDO la obra usa un tipo de la biblioteca global o de otro proyecto, EL SISTEMA
  lo copiará a la biblioteca del proyecto y asignará la copia, para que el proyecto no
  dependa del otro.
- RF-93: SI el tipo elegido ya está copiado en la biblioteca del proyecto con los mismos
  datos, ENTONCES EL SISTEMA reutilizará esa copia (RF-62).
- RF-94: EL SISTEMA mostrará junto a cada tipo de la lista los datos que deciden la
  elección: tensión nominal y corriente nominal o sección en las líneas, potencia y
  tensiones en los transformadores, tensión, corriente y rango en los reguladores.
- RF-95: EL SISTEMA guardará las obras definidas en el espacio de trabajo hasta que se
  apliquen, para revisarlas, quitarlas o simularlas antes.

Banco de condensadores

- RF-71: CUANDO la obra es un banco de condensadores, EL SISTEMA creará un `ElmShnt`
  capacitivo en la barra indicada, con la potencia reactiva total, el número de
  escalones y la tensión nominal de la barra.
- RF-72: DONDE el operador da una consigna de tensión, EL SISTEMA dejará el banco por
  escalones regulando esa tensión; si no, fijo con todos los escalones conectados.

Reconectador

- RF-73: CUANDO la obra es un reconectador, EL SISTEMA creará un interruptor cerrado al
  principio del tramo indicado, marcado con protección y reenganche, sin relé. (Cambiado el
  2026-10-24 en la prueba real, T19: el relé sin su tipo de relé de DIgSILENT, `TypRelay`,
  deja el flujo sin calcular, «missing type»; la confiabilidad y la ubicación de
  reconectadores leen las marcas del interruptor, spec 012.)
- RF-73b: SI el operador elige un tipo de reenganche, ENTONCES EL SISTEMA no creará el relé
  y lo dirá en el informe, porque elegir el tipo de relé es de las protecciones (RF-74).
- RF-74: EL SISTEMA dirá en el informe que el reconectador no cambia el flujo de carga ni
  los estudios de esta iteración, porque su efecto está en la fiabilidad y las
  protecciones, que hoy no son defendibles (faltan tasas de falla y curvas).

Regulador de tensión

- RF-75: CUANDO la obra es un regulador de tensión, EL SISTEMA lo intercalará al
  principio del tramo indicado, con una barra nueva entre el regulador y el tramo.
- RF-76: EL SISTEMA dará al regulador la consigna de tensión, el rango y el número de
  pasos que indique el operador, en un tipo copiado si ninguno del proyecto los tiene.

Cambio de sección en la troncal

- RF-77: CUANDO la obra es un cambio de sección, EL SISTEMA asignará el tipo de línea
  indicado a los tramos de la troncal del alimentador, la que da el estudio de troncal
  (RF-44).
- RF-78: DONDE el operador indica solo unos tramos, EL SISTEMA cambiará solo esos.
- RF-87: SI un tramo indicado no es de la troncal, ENTONCES EL SISTEMA lo cambiará igual y
  lo anotará.
  **Cambiado por 016:RF-1 (2026-10-15):** la troncal de las obras es la del camino continuo más largo desde la cabecera, no la de `ComBbone` (que siguen usando el N-1 y la transferencia, 016:RF-10).
- RF-79: SI el tipo indicado no existe en el proyecto a la tensión del alimentador,
  ENTONCES EL SISTEMA lo creará como copia, a esa tensión, de uno que exista con esa
  sección, o, si no hay ninguno, rechazará la obra diciendo qué tipo falta.

Incremento de una terna

- RF-80: CUANDO la obra es una terna más, EL SISTEMA sumará uno al número de ternas en
  paralelo de los tramos indicados, o de la troncal si no se indican, con el mismo tipo.

Cambio del nivel de tensión

- RF-81: CUANDO la obra es un cambio de tensión, EL SISTEMA migrará el alimentador entero
  a la tensión nueva: todas sus barras de media tensión, desde la de su cabecera.
- RF-82: EL SISTEMA asignará a cada línea del alimentador una copia de su tipo a la
  tensión nueva (RF-60).
- RF-83: EL SISTEMA creará en la biblioteca del proyecto, por cada tipo de transformador
  de distribución (SED) del alimentador migrado, un tipo nuevo en el que solo cambia la
  tensión de alta, que pasa a la nueva, y lo asignará a esos transformadores en la
  variación.
- RF-103: EL SISTEMA conservará en cada tipo nuevo de SED la tensión de baja y la
  potencia nominal del tipo original, para que cada SED del alimentador migrado siga con
  su misma potencia y su misma tensión de baja.
- RF-99: EL SISTEMA creará un solo tipo nuevo por tipo original y tensión, compartido por
  todos los transformadores del alimentador que usaban el original (RF-62).
- RF-84: EL SISTEMA pondrá la tensión nueva en los condensadores y reguladores de media
  tensión del alimentador.
- RF-85: EL SISTEMA tomará la tensión de origen del alimentador y la de destino del
  operador, sin valores fijos en el código (P13).
- RF-86: EL SISTEMA pondrá la tensión nueva en la barra de alimentación de la cabecera
  del alimentador migrado, sin añadir ningún transformador de subestación.
- RF-100: EL SISTEMA dejará la fuente de tensión del alimentador (la red externa de su
  cabecera) en esa barra, de modo que alimente a la tensión nueva.
- RF-101: EL SISTEMA conservará la consigna de la fuente en p.u. y dirá en el informe su
  valor en kV a la tensión nueva.
- RF-102: SI la barra de cabecera o la fuente alimentan también a otro alimentador que no
  se migra, ENTONCES EL SISTEMA no aplicará la obra y nombrará ese alimentador.
- RF-96: EL SISTEMA no añadirá barras ni transformadores en la cabecera del alimentador
  migrado.
- RF-97: EL SISTEMA no cambiará la tensión de ninguna barra ni fuente de los demás
  alimentadores.

Transferencia de carga entre dos alimentadores

El usuario pide (2026-10-11) una sección para saber cuánta carga puede pasar un
alimentador a otro por su punto de enlace y hasta qué nodo o seccionador existente, en
los dos sentidos. DIgSILENT 2024 no tiene un comando que lo dé (manual de usuario, cap.
40.5, 41.3 y 46): la capacidad de transferencia (`ComTransfer`) escala cargas entre
regiones sin abrir ni cerrar nada, y la puntuación de la troncal (`ComBbone`) prueba solo
el paso del alimentador entero. Lo que sí da DIgSILENT es el camino entre los dos
alimentadores por su punto de enlace (la troncal, `ElmBbone`), y sobre él se construye el
cálculo: cerrar el enlace y abrir, uno tras otro hacia la cabecera del alimentador que
cede, cada punto del camino, con un flujo de carga en cada paso.

- RF-104: EL SISTEMA ofrecerá una parte «4.3 Transferencia de carga» en la que el operador
  elige dos alimentadores marcados y el caso en que se calcula: «Sin proyecto», «Con
  proyecto» o los dos.
- RF-105: CUANDO el operador calcula una transferencia, EL SISTEMA la calculará en los dos
  sentidos: del primero al segundo y del segundo al primero.
- RF-106: EL SISTEMA buscará los puntos de enlace normalmente abiertos que unen los dos
  alimentadores y calculará la transferencia por cada uno.
- RF-107: SI los dos alimentadores no tienen ningún punto de enlace entre ellos, ENTONCES
  EL SISTEMA no calculará nada y lo dirá con los dos nombres.
- RF-108: EL SISTEMA tomará como camino de la transferencia el que va del punto de enlace
  a la cabecera del alimentador que cede, por la troncal que calcula DIgSILENT entre los
  dos alimentadores.
- RF-109: CUANDO calcula un sentido, EL SISTEMA cerrará el punto de enlace y abrirá, uno
  tras otro desde el enlace hacia la cabecera del que cede, cada seccionador existente
  del camino, y ejecutará un flujo de carga en cada paso.
- RF-110: EL SISTEMA contará en cada paso la carga transferida, en kW y kVA: la que queda
  entre el seccionador abierto y el punto de enlace, alimentada ya por el que recibe.
- RF-111: EL SISTEMA dará por viable un paso cuando el flujo converge y ningún elemento
  del alimentador que recibe, ni de la parte transferida, pasa del límite de
  cargabilidad ni sale de los límites de tensión (RF-35).
- RF-112: EL SISTEMA informará por sentido y por enlace la máxima carga transferible: la
  del seccionador viable más lejano del enlace, con su nombre.
- RF-113: EL SISTEMA informará también, por sentido, el nodo del camino más lejano del
  enlace hasta el que la transferencia seguiría siendo viable si allí hubiera un
  seccionador, con la carga que se transferiría hasta él.
- RF-114: EL SISTEMA informará por sentido el elemento que limita la transferencia en el
  primer paso no viable y el motivo: sobrecarga, con su cargabilidad, o tensión, con la
  barra y su valor.
- RF-115: EL SISTEMA dará por cada paso el seccionador o nodo, la carga transferida, la
  tensión mínima, la cargabilidad máxima y lo que entra por la cabecera del que recibe.
- RF-116: SI ningún paso es viable, ENTONCES EL SISTEMA dirá que ese sentido no admite
  transferencia y el elemento que lo impide ya en el primer paso.
- RF-117: SI el camino no tiene ningún seccionador existente, ENTONCES EL SISTEMA dará solo
  el resultado por nodos (RF-113) y lo dirá.
- RF-118: EL SISTEMA contará como puntos de maniobra solo los seccionadores que están en
  la troncal del alimentador que cede, y no los fusibles, interruptores, reconectadores,
  seccionalizadores ni los seccionadores de las derivaciones.
- RF-128: EL SISTEMA reconocerá un seccionador por la clase de equipo que trae la entrada
  (la tabla de seccionadores del export), escrita en el proyecto al convertir.
- RF-129: SI el proyecto de DIgSILENT no distingue los seccionadores de los demás equipos
  de maniobra (un proyecto convertido antes de esta spec) y no hay entrada cargada con
  la que reconocerlos, ENTONCES EL SISTEMA dará solo el resultado por nodos (RF-113) y
  dirá que hay que volver a convertir el alimentador o cargar su entrada.
- RF-119: CUANDO termina un sentido, EL SISTEMA dejará cada interruptor del proyecto en el
  estado en que estaba y lo comprobará.
- RF-120: EL SISTEMA no grabará en ninguna variación ni en ningún escenario las maniobras
  del cálculo.
- RF-121: EL SISTEMA guardará el resultado de las transferencias en un fichero descargable
  con una fila por caso, sentido, enlace y paso.

Capacidad del enlace con la herramienta de transmisión

El usuario pide (2026-10-11) usar la transferencia de potencia de los sistemas de
transmisión si sirve. DIgSILENT la tiene: el análisis de capacidad de transferencia
(`ComTransfer`, manual §40.5), que sube la carga de un conjunto de elementos y baja la de
otro hasta que algo pasa de su límite, y mide lo que cruza una frontera. No maniobra, así
que no dice hasta qué seccionador (eso lo dan RF-109 a RF-113), pero sí cuánto más puede
pasar por el enlace en una configuración dada: el margen que queda para crecer.

- RF-122: EL SISTEMA informará por sentido y por enlace la capacidad del enlace: la
  máxima potencia que el alimentador que recibe puede entregar por el enlace, en la
  configuración del seccionador viable más lejano, subiendo la carga de la parte
  transferida hasta el primer límite.
- RF-123: EL SISTEMA informará el margen del enlace: la capacidad de RF-122 menos la carga
  que ya se transfiere en esa configuración.
- RF-124: DONDE la licencia de DIgSILENT incluye el análisis de capacidad de
  transferencia, EL SISTEMA calculará RF-122 con él.
- RF-125: SI la licencia no lo incluye, o el análisis no termina con una solución viable,
  ENTONCES EL SISTEMA calculará RF-122 con flujos de carga sucesivos subiendo esa carga, y
  dirá en el informe con qué método se calculó.
- RF-126: EL SISTEMA no guardará en ningún escenario ni variación el punto de operación
  escalado del análisis.
- RF-127: EL SISTEMA aplicará en el análisis los mismos límites de tensión y cargabilidad
  que en los pasos (RF-35), solo sobre el alimentador que recibe y la parte transferida.

## Requisitos no funcionales

- Carril `powerfactory`, un único proceso con el motor a la vez, con progreso por estudio
  y por caso, y cancelable (P7).
- Escala (P2): cualquier número de alimentadores marcados, cargas nuevas, barras y
  contingencias, sin tope fijo ni tamaños fijos en las pruebas.
- Universal (P13): límites y tolerancias del perfil de empresa; ningún código de Electro
  Dunas como valor por defecto.
- Determinismo: los ficheros de resultados ordenan casos, alimentadores, elementos y
  contingencias por nombre, y son iguales en dos ejecuciones sobre el mismo proyecto.
- Datos de la distribuidora (P9): las pruebas usan proyectos y resultados sintéticos; la
  prueba en DIgSILENT la hace el usuario.

## Casos límite

- Proyecto con un solo alimentador marcado.
- Ajuste de varios alimentadores en el que alguno falló (RF-14) o no cuadró (RF-15).
- La variación del ajuste borrada o desactivada a mano en DIgSILENT (RF-16).
- Sin demandas en bloque: «Sin proyecto» es solo el ajuste.
- Sin cargas nuevas: solo se estudia «Sin proyecto» (RF-9).
- Cargas nuevas añadidas después de una primera ejecución: «Con proyecto» las suma en la
  siguiente (RF-6 y RF-8).
- Escenario de operación activo en el caso original: lo conserva el «Caso base», y cada
  copia lleva una copia propia (RF-46 a RF-49).
- Escenario de un caso modificado a mano en DIgSILENT: no se sobrescribe al reutilizar el
  caso (RF-6).
- Todas las SED de un alimentador con clientes importantes: todas fijas, ninguna escalable.
- Un `ComDpl` con parámetros de entrada de tipo objeto o conjunto, que no se escriben como
  texto.
- Contingencias N-1 sobre muchos alimentadores: el estudio pesado que más puede tardar
  (RF-39).
- Un estudio que no deja resultados.
- Un tipo compartido por alimentadores de los dos casos: la obra lo copia y no lo toca
  (RF-59, RF-60).
- La misma obra pedida dos veces: la segunda variación lleva otro nombre (RF-56).
- Dos obras sobre el mismo tramo en el mismo caso (sección y terna): se aplican las dos,
  en el orden en que llegan.
- Cambio de tensión de un alimentador con cargas nuevas en «Con proyecto»: sus
  transformadores también se copian a la tensión nueva.
- Una obra que no converge en «Con proyecto» y sí en «Sin proyecto» (RF-67).
- Dos alimentadores con varios puntos de enlace entre ellos: una transferencia por enlace
  (RF-106).
- Un alimentador que ya recibe al límite: ningún paso viable (RF-116).
- Un enlace que une tres alimentadores: solo cuentan los dos elegidos.
- Un seccionador abierto en el camino que no es el enlace: el camino se corta ahí y se
  dice.
- Transferencia con una obra activa en «Con proyecto» (una terna más, un regulador): se
  calcula con ella, y la diferencia con «Sin proyecto» muestra lo que aporta la obra.

## Fuera de alcance

- Traer o copiar DPL de repositorios externos.
- Ejecutar estudios en el «Caso base»: se conserva como referencia.
- Un caso por carga nueva o combinaciones de cargas: «Con proyecto» las lleva todas. La
  diferencia carga a carga del flujo de carga sigue en la spec 007 (RF-33).
- Los estudios que no son defendibles hoy (cortocircuito, cuasi-dinámica, evaluación
  económica, protecciones, armónicos). La fiabilidad y la colocación de condensadores
  pasan a la spec 012 (2026-10-11), con las tasas y los costes de un fichero de la
  empresa.
- Calcular la ubicación óptima de las obras: la indica el operador. La propuesta de
  reconectadores y condensadores con los módulos de DIgSILENT es de la spec 012, y la
  obra se sigue creando aquí.
- Coste e inversión de las obras: la evaluación económica sigue bloqueada (faltan precios).
- Ajustes y curvas de protección del reconectador.
- Aplicar al proyecto lo que proponen el punto de apertura, el perfil de tensión o el
  balance de fases (RF-26).
- Volver a ajustar a la máxima después de un estudio.
- Escribir guiones DPL o Python desde la web.
- Cambiar los ajustes de cada comando más allá de los límites (RF-35) y del escalado
  (RF-20); se usan los del caso de estudio.
- La prueba real en DIgSILENT: la hace el usuario.

## Criterios de finalización

- `grep -rnoE "011:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-129.
- Suite completa en verde, también la de las specs 004, 006, 007 y 008.
- `npx tsc --noEmit -p .` y `npm run build` en `frontend/` correctos.
- Prueba real en DIgSILENT con un proyecto de dos alimentadores calibrados y al menos una
  carga nueva, a cargo del usuario.

## Dudas resueltas (2026-10-11)

- «Fijas y escaladas» es la marca de cada carga en DIgSILENT: clientes importantes no
  escalables, repartidas escalables (usuario; RF-18 y RF-19).
- Estudios de esta iteración: flujo equilibrado y desequilibrado, contingencias N-1,
  troncal, punto de apertura, perfil de tensión y balance de fases (usuario; RF-23).
- Un ajuste que no cuadró se estudia con aviso (usuario; RF-15).
- Tres casos: «Caso base» (el original, sin calibrar), «Sin proyecto» (copia calibrada,
  donde se estudia) y «Con proyecto» (copia con todas las cargas nuevas juntas, donde se
  repiten los estudios) (usuario; RF-1 a RF-8).
- Nombres fijos, y los casos se reutilizan; uno ajeno con el mismo nombre se pide
  renombrar (usuario; RF-6 y RF-10).
- El caso original se renombra a «Caso base» (usuario; RF-2).
- Contingencias N-1: solo los tramos de la troncal (usuario; RF-43 a RF-45).
- Cada caso tiene su propio escenario de operación; el del original se conserva y los
  estudios lo usan (usuario; RF-46 a RF-49).
- Los ajustes anteriores se desactivan, no se borran (usuario; RF-50).
- Una vez creados los casos, el ajuste y las demandas van en «Sin proyecto», las cargas
  nuevas en «Con proyecto» y el «Caso base» no se toca (usuario; RF-51 a RF-54).
- Las demandas se siguen grabando en las variaciones con el escenario desactivado
  mientras se escribe (usuario; RF-55).
- Obras: una variación por obra (usuario; RF-56).
- Las obras se definen a mano en un formulario, eligiendo elementos y tipos de las
  librerías de DIgSILENT, con tipos que se pueden traer de otros proyectos (usuario;
  RF-70, RF-88 a RF-95).
- Transferencia: solo cuentan los seccionadores de la troncal (usuario; RF-118).
- Cambio de tensión: se migra el alimentador entero, desde su cabecera. No hace falta
  ninguna SET: la fuente de tensión y la barra de alimentación de la cabecera pasan a la
  tensión nueva (usuario; RF-81, RF-86, RF-96, RF-97, RF-100 a RF-102).
- Los tipos de los transformadores de las SED a la tensión nueva los crea el sistema en
  la biblioteca del proyecto; no se eligen (usuario; RF-83, RF-99).
- En los tipos nuevos de las SED solo cambia la tensión de alta: la de baja y la potencia
  son las de las SED del alimentador que se migra (usuario; RF-83, RF-103).
- Los pasos del regulador se dan a cada lado de la toma central: ±16 pasos son las
  tomas −16 a +16, como el rango, que DIgSILENT da en «+/-» (usuario, 2026-10-12; RF-76).

## Dudas abiertas

Ninguna.

## Cambios de la spec 014 (2026-10-14)

- Aclaración de RF-2: la calibración no se hace en el «Caso base» sino en «Sin proyecto» (014:RF-1,
  RF-5).
- Aclaración de RF-6: al reutilizar los casos solo cambian las variaciones de carga nueva; las del
  operador solo se activan en «Con proyecto», si lo están en «Sin proyecto» (014:RF-15,
  RF-20, RF-21).
- RF-7, RF-50: la calibración no desactiva ni borra variaciones del operador (014:RF-3,
  RF-20).
- Aclaración de RF-8: «Con proyecto» hereda «Sin proyecto» y suma las cargas nuevas (014:RF-18, RF-21,
  RF-24).
- RF-54, RF-55: sustituidos después por la spec 015 (sección siguiente): no hay variación
  del ajuste ni de las demandas; se graban en el escenario de «Sin proyecto».

## Cambios de la spec 015 (2026-10-14)

- RF-2, RF-3: el «Caso base» es la red física verificada frente al archivo original, con
  las correcciones del operador hechas antes de copiarlo; después no se toca (015:RF-1,
  RF-14, RF-19).
- RF-4, RF-5: «Sin proyecto» se crea solo con el «Caso base» verificado, y «Con
  proyecto», antes de insertar cargas nuevas (015:RF-16, RF-17, RF-28).
- RF-7, RF-8, RF-12, RF-13, RF-16, RF-50, RF-54, RF-55: no hay variación del ajuste ni de
  las demandas en bloque. La calibración y las demandas están en el escenario de «Sin
  proyecto» (y se copian al de «Con proyecto»); un alimentador está calibrado si su
  ajuste aplicado no falló (015:RF-26, RF-27). Los ajustes de antes de la 015 no se tocan.
