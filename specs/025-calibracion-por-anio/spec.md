# Spec 025 — Calibración por año de medición

Estado: aprobada (2026-10-23, con RF-26 a RF-35 añadidos ese día) · Fecha: 2026-10-23

## Contexto y objetivo

La empresa entrega las mediciones por año: en `referencia/2.-medicioncabecera` y
`referencia/4.-clientesimportantes` el usuario creó una subcarpeta por año (`2025`, `2026`, y
vendrán más). Hoy el sistema solo mira el primer nivel de esas carpetas, así que con las
subcarpetas no encuentra ningún libro, y el proyecto de DIgSILENT tiene una sola calibración
(«Sin proyecto», hecha con 2026). El usuario quiere recalibrar los modelos actuales de
DIgSILENT con las mediciones de 2025 sin perder la de 2026: «la recalibración con el modelo
de año 2025 debe ser aparte de 2026, cada uno debe hacerse de forma individual, no deben
mezclarse» (2026-10-23).

Lo que se vio en los libros reales (2026-10-23, solo estructura y recuentos):

- Cabecera 2025: un solo libro (`MEDICIONES ALIMEN_MOD PIT_2025.xlsx`), una hoja por medidor
  y registros cada 15 min de enero a diciembre, como los de 2026. Trae 7 alimentadores
  (TM105, PN107 de Chincha; AL209, PA217, SI213 de Pisco; IN111, TA225 de Ica), ninguno de
  Nasca y ningún medidor de barra de SET.
- Cuatro de sus hojas se llaman como el alimentador (`L-PA217`) y no como el medidor que da
  el libro de medidores (`L-PA235`); solo AL209, TA225 e IN111 casan por el medidor.
- Clientes 2025: doce libros `MMAA Pulso[ e].xlsx|xlsb`, legibles, pero el patrón del perfil
  solo reconoce `MMAAclientesImportantes`; por contenido, 7 de los 12 quedan «sin mes».

## Usuarios / actores

Ingeniero de planificación desde la web (paso 2, calibración) y `tools/sistema_web.py`;
DIgSILENT, donde quedan los casos de cada año.

## Historias de usuario

- H1: Como ingeniero quiero dejar los libros de cada año en su subcarpeta para que el
  sistema los encuentre sin moverlos.
- H2: Como ingeniero quiero elegir el año (y, si quiero, el mes) de las mediciones para
  calibrar con ese año.
- H3: Como ingeniero quiero que la calibración de 2025 quede en sus propios casos del mismo
  proyecto, para comparar con la de 2026 sin que una pise o contamine a la otra.

## Requisitos funcionales (EARS)

Libros por año

- RF-1: CUANDO la fuente de cabecera o de clientes es una carpeta con subcarpetas de año
  (cuatro cifras), EL SISTEMA tomará los libros de cada subcarpeta y los asociará a ese año.
- RF-2: EL SISTEMA seguirá tomando los libros sueltos del primer nivel de la carpeta, sin año
  de carpeta, como hasta ahora.
- RF-3: EL SISTEMA nombrará cada libro de una subcarpeta con su ruta relativa
  (`2025/0125 Pulso e.xlsx`), para que dos años con el mismo nombre de libro no se confundan.
- RF-4: EL SISTEMA dará la lista de años disponibles: los de las subcarpetas de cabecera, y
  de cada uno si tiene libros de clientes.
- RF-5: SI el mes que da el nombre o el contenido de un libro de clientes es de otro año que
  su subcarpeta, ENTONCES EL SISTEMA no lo activará y lo dirá con el libro y los dos años.
- RF-6: SI el perfil no da patrón o el nombre de un libro de una carpeta de año no casa con
  él, ENTONCES EL SISTEMA tomará el mes del nombre cuando traiga uno solo compatible con ese
  año, en cualquiera de estas formas: `MMAA`, `AAAAMM`, `AAAA-MM`, `MM-AAAA` o el nombre del
  mes en español o en inglés; si no, seguirá con 013:RF-4 (fecha dentro del libro). Ningún
  nombre fijo de libro de una empresa (usuario, 2026-10-23: «no va a ser necesariamente de
  la empresa Electro Dunas, puede ser de cualquier empresa; es universal y general»).
- RF-6b: EL SISTEMA aceptará en el perfil una lista de patrones de nombre de libro de
  clientes, además de uno solo, para la empresa que cambie la forma del nombre de un año a
  otro.

Periodo de la máxima

- RF-7: EL SISTEMA aceptará como periodo un año `AAAA` (la máxima del año entero) además de un
  mes `AAAA-MM` (013:RF-11).
- RF-8: MIENTRAS haya un periodo elegido, EL SISTEMA buscará la máxima solo en los libros de
  cabecera de la subcarpeta de su año y en los sueltos del primer nivel.
- RF-9: SI no hay periodo elegido y la carpeta tiene subcarpetas de año, ENTONCES EL SISTEMA
  no buscará la máxima y pedirá elegir un año: sin él se mezclarían años.
- RF-10: CUANDO el periodo es un año, EL SISTEMA cruzará los clientes de cada alimentador con
  el libro del mes en que cae su máxima, como ya hace el ajuste (cada máxima con los clientes
  de su propio mes).
- RF-11: SI el mes de la máxima de un alimentador no tiene libro de clientes en ese año,
  ENTONCES EL SISTEMA lo dirá y repartirá sus SED por kVA (013:RF-13).

Medidor y hoja

- RF-12: SI el medidor que da el libro de medidores no tiene hoja en los libros del año,
  ENTONCES EL SISTEMA buscará la hoja cuyo nombre es el código del alimentador, solo o tras
  un prefijo separado por un guion, un espacio, un punto o un subrayado («L-PA217», «ALIM
  PA217»), y lo avisará con el medidor y la hoja usada.
- RF-12b: SI dos hojas del mismo libro casan con el código del alimentador por RF-12,
  ENTONCES EL SISTEMA no elegirá ninguna y lo dirá con las dos.
- RF-13: SI ni el medidor ni el código del alimentador tienen hoja en los libros del año,
  ENTONCES EL SISTEMA dejará ese alimentador sin medición de ese año.

Casos de cada año en DIgSILENT

- RF-14: CUANDO el operador calibra con un año distinto del de los casos «Sin proyecto» y
  «Con proyecto» existentes, EL SISTEMA creará en el mismo proyecto «Sin proyecto <año>» y
  «Con proyecto <año>», marcados como del sistema y de ese año (011:RF-10).
- RF-15: EL SISTEMA creará «Sin proyecto <año>» como copia del «Caso base» verificado, con su
  propio escenario de operación, nunca como copia del «Sin proyecto» de otro año.
- RF-16: EL SISTEMA creará «Con proyecto <año>» como copia de «Sin proyecto <año>», como en
  014:RF-18.
- RF-17: EL SISTEMA tomará los casos «Sin proyecto» y «Con proyecto» sin año en el nombre como
  los del año con que se calibraron (2026 en los proyectos existentes), sin renombrarlos.
- RF-18: CUANDO el operador calibra con un año, EL SISTEMA escribirá la calibración solo en el
  escenario de «Sin proyecto» de ese año, sin tocar los casos ni los escenarios de otro año.
- RF-19: MIENTRAS se calibra con un año, los alimentadores del proyecto sin medición de ese
  año quedarán con la demanda del archivo (la del «Caso base»), aunque tengan calibración de
  otro año (022:RF-53).
- RF-20: EL SISTEMA guardará la calibración de cada alimentador por proyecto y por año, para
  que la de un año no se tome por cambio manual del otro (014:RF-10).
- RF-21: SI ya existe un caso de nombre «Sin proyecto <año>» o «Con proyecto <año>» que no creó
  el sistema, ENTONCES EL SISTEMA no lo tocará y pedirá renombrarlo (011:RF-10).

Web y herramienta

- RF-22: EL SISTEMA ofrecerá en el paso 2 un selector de año, con los años de RF-4, sin
  ninguno elegido al entrar (013:RF-8).
- RF-23: CUANDO el operador elige un año, EL SISTEMA ofrecerá «todo el año» y sus meses con
  libro de clientes, solo de ese año.
- RF-24: EL SISTEMA dirá en el plan, en el resultado y en el informe de la calibración el año,
  el caso en que se grabó y los libros de cabecera y de clientes usados.
- RF-25: `tools/sistema_web.py` aceptará `--periodo AAAA` y `--periodo AAAA-MM` y calibrará en
  los casos de ese año.
- RF-25b: EL SISTEMA reconocerá en la carpeta de demanda, por el contenido de sus libros y no
  por el nombre de sus carpetas, cuál es el libro de medidores, la medición de cabecera, los
  clientes importantes y los suministros; `tools/sistema_web.py` no llevará nombres de
  carpeta de ninguna empresa.
- RF-25c: SI dos carpetas de la carpeta de demanda parecen del mismo tipo, o ninguna lo es,
  ENTONCES EL SISTEMA lo dirá con sus nombres y pedirá la ruta de ese tipo por opción.

Crecimiento sin tocar el código (usuario, 2026-10-23: «se van a seguir incrementando más
hojas y libros y más carpetas; debe ser adaptable y robusto»)

- RF-26: EL SISTEMA tomará también los libros de las subcarpetas que haya dentro de una
  carpeta de año, a cualquier profundidad, como de ese año.
- RF-27: EL SISTEMA reconocerá un año, un libro, una hoja o una subcarpeta nuevos al
  actualizar el índice, sin cambiar el código ni el perfil.
- RF-28: EL SISTEMA guardará un índice de cada libro de cabecera (año, hojas, primer y último
  mes con registros) con su tamaño y su fecha de modificación, y solo volverá a abrir los
  libros nuevos o cambiados.
- RF-29: SI un libro no se puede abrir o ninguna hoja tiene columnas de fecha y kW, ENTONCES
  EL SISTEMA lo dirá en el índice con el motivo y seguirá con los demás.
- RF-30: SI un mismo medidor tiene hoja en dos libros del mismo año, ENTONCES EL SISTEMA usará
  el de modificación más reciente y lo avisará con los dos libros.
- RF-31: SI la carpeta cambia mientras se construye el índice, ENTONCES EL SISTEMA lo dirá y
  pedirá actualizarlo antes de buscar la máxima (013:RF-6).

Trabajos en segundo plano (usuario: «los hilos bien hechos»)

- RF-32: EL SISTEMA construirá el índice de cabecera y el de clientes como trabajos del
  carril del motor, con progreso por libro y cancelables entre libros, sin abrir ningún libro
  dentro de una petición HTTP (P7).
- RF-33: SI se cancela o falla el índice, ENTONCES EL SISTEMA conservará el índice anterior
  entero, sin dejar uno a medias.

Cómo entra cada libro en la web (usuario: «en la web se debe identificar claro cómo se
ingresan»)

- RF-34: EL SISTEMA mostrará en el paso 2, para la cabecera y para los clientes, la carpeta
  elegida y un árbol por año con cada libro (ruta relativa), su mes o meses, sus hojas, de
  dónde salió el mes (nombre, contenido o manual), si se usa y, si no, por qué.
- RF-35: EL SISTEMA dirá en el paso 2 dónde dejar los libros de un año nuevo
  (`<carpeta>/<AAAA>/`) y que después se pulse «Actualizar índice».

Cargas nuevas sobre la calibración de un año (usuario, 2026-10-23: «después debes hacer la
inserción de las cargas en bloque en los mismos proyectos recalibrados para el año 2025»;
cambia el alcance: las cargas nuevas ya no quedan fuera)

- RF-36: CUANDO el operador inserta cargas nuevas o demandas en bloque con base en una
  calibración de un año con sus propios casos, EL SISTEMA las pondrá en «Con proyecto
  <año>» y «Sin proyecto <año>» de ese año, como 015:RF-27 y RF-28.
- RF-37: EL SISTEMA sacará el año de los casos del caso en que se grabó la calibración que
  sirve de base (007:RF-1), sin pedirlo aparte.
- RF-38: MIENTRAS se insertan cargas en los casos de un año, EL SISTEMA no tocará los casos
  ni las variaciones activas de los casos de otro año.

Obras sobre los casos de un año (usuario, 2026-10-23: en el proyecto unido IN111 + TA225,
«activar las mismas obras»; en Pisco y Chincha, «proponer obras para 2025»). Las cargas
nuevas de PA217 (PI_1 con PI_8) y de TM105 (CH_3 con CH_5) no convergen juntas en «Con
proyecto 2025»; cada una sola, sí. Las nueve de TA225 son las de 2026, creadas sobre su
enlace, su migración y su terna.

- RF-41: CUANDO el operador aplica obras con un año, EL SISTEMA las aplicará en «Sin
  proyecto <año>» y «Con proyecto <año>», y creará «Con proyecto <año>» como copia de «Sin
  proyecto <año>» después de las obras de este (016:RF-12), sin tocar los casos de otro año.
- RF-42: CUANDO se reutilizan en «Con proyecto <año>» cargas nuevas creadas en los casos sin
  año (014:RF-29), EL SISTEMA activará también allí las obras que tiene activas «Con
  proyecto» sin año, sin duplicarlas, y lo dirá con sus nombres.
- RF-42b: CUANDO EL SISTEMA activa esas obras en «Con proyecto <año>», copiará también a su
  escenario los datos de operación (en servicio, estado de interruptores, escalones de
  bancos, tomas) que esas obras cambiaron en «Con proyecto» respecto de «Sin proyecto»,
  salvo los que el caso del año ya cambió por su cuenta, que se dejan y se avisan.
  (Visto en DIgSILENT el 2026-10-23: en IN111 + TA225, el enlace seguía fuera de servicio
  en «Con proyecto 2025» y cuatro cargas nuevas de TA225 quedaban sin tensión, aunque el
  flujo convergía.)
- RF-43: SI «Con proyecto <año>» no converge con sus cargas nuevas, ENTONCES EL SISTEMA dirá
  qué cargas no convergen juntas (cada una sola sí), probando una a una sus variaciones, y
  las dejará como estaban.
- RF-44: CUANDO «Con proyecto <año>» no converge con sus cargas nuevas, o converge fuera de
  los límites de tensión o de cargabilidad del perfil, EL SISTEMA probará obras sobre los
  alimentadores de esas cargas en este orden: bancos de condensadores, regulador de tensión,
  nueva terna y cambio de sección del conductor, cada obra en su variación. (Cambia el
  2026-10-24, usuario: «primero se debe probar bancos, después nueva terna, cambio de
  sección de cable»; antes, bancos, sección y terna, y se aplicaba la primera que
  convergía. El regulador, tras analizar si hace falta: en «Sin proyecto 2025» PA217 tiene
  403 de 550 barras de media bajo 0,95 sin ningún tramo sobre el 100 %, un problema solo de
  tensión.)
- RF-44b: EL SISTEMA no corregirá nada en «Sin proyecto <año>»: allí solo se calibra y se
  hace converger; las obras de la escalera van solo en «Con proyecto <año>» (usuario,
  2026-10-24: «en el caso sin proyecto no debes corregir nada, solo calibrar y hacer
  converger»).

Escalera optimizada (usuario, 2026-10-24: «se debe iterar varias veces hasta obtener la
mejor solución según la optimización y cálculos estocásticos»; la mejor, la de menor costo
anual; se sortea la demanda existente por la curva de cabecera del año y la de cada carga
nueva por su factor de uso; vale si cumple en el 95 % de 200 sorteos)

- RF-49: EL SISTEMA probará varias variantes de cada obra de la escalera (bancos: barras y
  tamaño; nueva terna: tramos desde la cabecera; cambio de sección: tramos y conductor de
  las bibliotecas) y sus combinaciones en el orden de RF-44, en vez de quedarse con la
  primera que converge.
- RF-50: EL SISTEMA dará por factible una variante solo si, en al menos la fracción de
  sorteos del perfil, el flujo converge, la barra de media de cada carga nueva queda entre
  los límites de tensión del perfil y el resto del alimentador no queda peor que en «Sin
  proyecto <año>» con el mismo sorteo: una barra o un tramo dentro de los límites sigue
  dentro, y uno que ya estaba fuera no empeora más que la tolerancia del perfil.
  (Usuario, 2026-10-24: la red existente ya incumple en la máxima de 2025 y no se corrige
  en «Sin proyecto».)
- RF-51: EL SISTEMA tomará en cada sorteo la demanda existente de un punto medido de la
  curva de cabecera del año de los casos, escalando las cargas calibradas por la razón
  entre ese punto y la máxima calibrada.
- RF-52: EL SISTEMA tomará cada carga nueva con su demanda declarada, sumada a la demanda
  existente, sin sortearla: «Con proyecto <año>» es la máxima calibrada más las cargas
  nuevas (usuario, 2026-10-24: «ahí suman a la máxima demanda hasta donde no converge sin
  incluir las obras; eso ya es el escenario con proyecto»).
- RF-52b: EL SISTEMA dará por factible una variante solo si además cumple los límites de
  RF-50 en «Con proyecto <año>» con la máxima calibrada; los sorteos de RF-51 se hacen solo
  sobre las variantes que pasan este primer filtro.
- RF-53: Entre las variantes factibles, EL SISTEMA elegirá la de menor costo anual:
  anualidad de la inversión con los costos unitarios del libro CAPEX, más operación y
  mantenimiento, más el costo de las pérdidas (art. 14 y 15 del PIDE, 024:RF-57).
- RF-54: EL SISTEMA aplicará en «Con proyecto <año>» solo las obras de la variante elegida,
  cada una en su variación, y no dejará creadas las demás.
- RF-55: EL SISTEMA informará cada variante probada con la fracción de sorteos que cumple,
  su inversión, su costo anual y por qué no se eligió.
- RF-56: SI ninguna variante es factible, ENTONCES EL SISTEMA lo dirá con la que más se
  acerca (mayor fracción de sorteos que cumple) y no aplicará ninguna.
- RF-59: EL SISTEMA creará en la biblioteca global de DIgSILENT los tipos de regulador de un
  catálogo de fabricante guardado en el repositorio (tensión, corriente, rango, pasos y
  fuente), sin duplicar los que ya existan con ese nombre. (Usuario, 2026-10-24: «busca
  fichas técnicas en la web de regulador y créalos en las librerías»; Eaton VR-32 de 50 Hz,
  catálogo CA225001EN de agosto de 2025.)
- RF-60: EL SISTEMA pondrá el regulador en un tramo de la troncal aguas arriba de las barras
  que quedan fuera de límites, cuya corriente con proyecto no supere la del tipo elegido.
- RF-57: SI falta en el perfil la fracción de sorteos, el número de sorteos, la tolerancia,
  la tasa o la vida útil, o en el libro CAPEX el costo de una alternativa, ENTONCES
  EL SISTEMA dirá cuál falta y no supondrá un valor (P13).
- RF-58: CUANDO se repite la escalera con la misma red, las mismas cargas y la misma
  semilla, EL SISTEMA sorteará lo mismo y elegirá la misma variante.
- RF-67: EL SISTEMA costeará la escalera en la moneda de trabajo del perfil (Electro Dunas:
  dólares, como su libro CAPEX) y pasará a ella los precios de pérdidas con el tipo de
  cambio que el operador escriba en la web al pedir la escalera, sin tomarlo del perfil
  (usuario, 2026-10-24: «trabaja en dólares»; «la tasa de cambio de dólar debe ingresar
  por la web»).
- RF-68: SI los precios de pérdidas están en otra moneda y el operador no da el tipo de
  cambio, ENTONCES EL SISTEMA no empezará la escalera y lo dirá en la web.
- RF-69: MIENTRAS evalúa la escalera de un alimentador, EL SISTEMA tendrá activas en «Con
  proyecto <año>» solo sus cargas nuevas y las de los alimentadores ya resueltos (con su obra
  aplicada), y apartará un momento las de los demás, para volver a activarlas al terminar.
  (Pisco, 2026-10-24: con las cargas de PA217 activas «Con proyecto 2025» no convergía, y
  todas las variantes de SI213 salían «no converge» aunque el problema no fuera suyo.)
  Lo mismo al aplicar la variante elegida: su flujo se comprueba con esas cargas apartadas, y
  un alimentador solo cuenta como resuelto si su obra quedó activa en «Con proyecto <año>».
  (Pisco, 2026-10-24: la terna y la sección elegidas para SI213 quedaron inactivas porque la
  aplicación normal comprobó el flujo con las cargas de PA217, y PA217 se evaluó como si SI213
  estuviera resuelto.)
- RF-71: EL SISTEMA medirá primero todas las variantes con la máxima y sorteará solo las
  que cumplen y tienen costo, de la de menor costo anual a la de mayor, hasta la primera que
  cumple en la fracción de sorteos del perfil: las más caras ya no pueden ganar y se dicen
  sin sortear. (Pisco, 2026-10-24: con 200 sorteos para cada variante que cumplía con la
  máxima, SI213 llevaba media hora y PA217 iba detrás; usuario: «sé eficiente».)
- RF-72: EL SISTEMA dejará de sortear una variante en cuanto los sorteos que no cumplen
  pasen de los que admite la fracción del perfil, porque ya no puede alcanzarla.
- RF-70: EL SISTEMA calculará las pérdidas de cada variante como lo que entra por la
  cabecera menos lo que consumen sus cargas en el flujo, no su potencia nominal. (Pisco,
  2026-10-24: con tensiones de 0,88 p.u. las cargas consumían menos que su nominal y las
  pérdidas salían negativas, −2044 kW en SI213.)
- RF-73: SI la evaluación de un alimentador ya terminó, sin cancelarse, con el mismo plan
  (proyecto, año, variantes, sorteos, cargas apartadas, parámetros y variaciones activas en
  «Con proyecto <año>») en las últimas 24 h, ENTONCES EL SISTEMA la reutilizará sin volver a
  medir, y lo dirá en el registro.
- RF-74: ANTES de probar las variantes de un alimentador, EL SISTEMA medirá «Con proyecto
  <año>» tal como está; SI ya cumple con la máxima y en los sorteos, ENTONCES no aplicará
  nada, lo dirá y lo dará por resuelto. (Pisco, 2026-10-24: volver a pedir la escalera con la
  obra de SI213 ya aplicada habría creado otra obra encima.)
  (RF-73, Pisco, 2026-10-24: la web se
  reinició dos veces a mitad de la escalera y cada vez se repetían 20 min de evaluación de
  SI213 que DIgSILENT ya había terminado.)

Caso de diagnóstico con las cargas nuevas (usuario, 2026-10-24: «debes hacer una copia al
caso sin proyecto y su escenario de operación de sin proyecto y ahí debes integrar las
nuevas cargas, cada uno con variación independiente como en con proyecto, y dejarlo
convergido sin hacer nada de cambios»; «solo crear ese caso, nada se evalúa, es para saber
la situación real con cargas nuevas; los cambios con escalera y proyectos nuevos van en con
proyecto»; nombre «Cargas nuevas <año>»; si no converge, se deja y se dice)

- RF-61: CUANDO se insertan cargas nuevas en los casos de un año (o en los sin año), EL
  SISTEMA creará o reutilizará el caso «Cargas nuevas <año>» («Cargas nuevas» sin año),
  copia de «Sin proyecto <año>», con la marca del sistema.
- RF-62: EL SISTEMA dará a «Cargas nuevas <año>» un escenario de operación propio, copia del
  de «Sin proyecto <año>» en ese momento, cada vez que se insertan cargas.
- RF-63: EL SISTEMA activará en «Cargas nuevas <año>» las variaciones de las cargas nuevas de
  los alimentadores marcados, las mismas que en «Con proyecto <año>», cada una la suya.
- RF-64: EL SISTEMA no pondrá en «Cargas nuevas <año>» ninguna obra, ningún ajuste del flujo
  ni ningún cambio de red o de demanda que no tenga «Sin proyecto <año>».
- RF-65: EL SISTEMA activará las cargas nuevas en «Cargas nuevas <año>» una a una, con un
  flujo después de cada una, y dejará activas solo las que lo dejan converger, de modo que
  el caso quede siempre convergido (usuario, 2026-10-24: «debe insertar uno por uno las
  cargas hasta donde la carga converge … y siempre debe dejar convergido en cualquier
  caso»; cambia lo acordado antes, dejar todas activas aunque no convergiera).
- RF-66: SI una carga nueva no deja converger «Cargas nuevas <año>», ENTONCES EL SISTEMA la
  dejará inactiva allí y dirá en la web con qué carga deja de converger y por qué: su
  alimentador, su potencia, la tensión mínima y los tramos sobrecargados del alimentador
  justo antes de ella, y lo que informa DIgSILENT del flujo que no convergió.

Cargas nuevas incompletas (usuario, 2026-10-23: «las cargas nuevas que no tienen datos
completos necesarios se rechazan y se deja un mensaje en la web»; obligatorios: barra o
coordenadas, y alimentador; para toda inserción desde ahora, sin tocar las ya insertadas)

- RF-45: SI una carga nueva del libro o del formulario no trae su alimentador (TRONCAL),
  ENTONCES EL SISTEMA la rechazará y lo dirá con su hoja, su fila y su SED, sin deducirlo
  de la barra.
- RF-46: EL SISTEMA mostrará en la web, en el paso de cargas, cada carga rechazada con su
  motivo, y aplicará las demás.

Cada carga nueva, independiente (usuario, 2026-10-23: «cada carga debe ser totalmente
independiente»; CH_8 de TM105 colgaba de NODE_T_CH_3, el nodo que crea la variación de CH_3)

- RF-47: CUANDO el punto más cercano de una carga nueva cae en un tramo que ya parte otra
  carga nueva (de la misma tanda o de otra), EL SISTEMA la conectará en el extremo
  existente de ese tramo más cercano a sus coordenadas, con su propia línea, sin partir el
  tramo otra vez ni usar nada que cree la variación de otra carga, y lo dirá (cambia
  016:RF-77).
- RF-48: EL SISTEMA medirá cada carga nueva con las variaciones de las demás cargas nuevas
  inactivas, de modo que desactivar una no cambie la conexión de ninguna otra.

Cargar datos nuevos desde la web (usuario, 2026-10-23: «todos los campos deben estar
habilitados para el ingreso o cargado de nuevos datos o archivos de entrada desde la web»)

- RF-39: EL SISTEMA dejará reemplazar un fichero de entrada o un libro ya asignado (RED,
  CARGA, BD_Equipo, `.mdb`, VNR-GIS, libros de demanda, libro de pérdidas) subiendo otro o
  indicando otra ruta, sin tener que quitar antes el actual.
- RF-40: MIENTRAS no corra un trabajo que lo invalidaría (P4 del skill de la web), EL
  SISTEMA tendrá habilitado cada campo de subida o de ruta; desactivado, dirá por qué.

## Requisitos no funcionales

- Universal (P13): vale para cualquier distribuidora. Ningún año, nombre de carpeta, nombre de
  libro, prefijo de hoja ni código de una empresa en el código ni como valor por defecto.
  Electro Dunas es solo el caso de prueba: lo que sea suyo va en su perfil, y sin perfil todo
  funciona con las reglas generales (RF-6, RF-12, RF-25b).
- Escala: cualquier número de años y de alimentadores; los libros de un año se abren una vez
  por búsqueda, como hoy (`Cabecera`).
- Los datos de `referencia/` no se publican ni se envían: las pruebas usan libros sintéticos y
  las de datos reales siguen tras `IGEA_DEMANDA_DIR`.

## Casos límite

- Carpeta sin subcarpetas de año: igual que hoy (RF-2), sin pedir año.
- Un medidor en libros de dos años: con periodo, solo cuenta el de su año (RF-8).
- Año sin libros de clientes: la máxima sí; el reparto, por kVA (RF-11).
- Año con ningún alimentador medido en un sistema (Nasca en 2025): el plan lo dice y no
  calibra (022:RF-53, «Ningún alimentador se puede calibrar»).
- Medidores de barra sin hoja en el año: cada alimentador con su propia máxima (022:RF-42).
- Volver a calibrar 2025: reutiliza «Sin proyecto 2025» y su escenario (011:RF-6).

## Fuera de alcance

- Estudios (011, 012), obras (016), transferencia, informes (017) y gemelo (024) sobre los
  casos de un año distinto: en esta iteración siguen en «Sin proyecto» / «Con proyecto» sin
  año, y lo dicen. Se tratarán en otra spec. Las cargas nuevas sí entran (RF-36 a RF-38).
- Un libro de medidores por año (se usa el único de `1.-medidoralimentador`, con RF-12).
- Comparar en un informe la calibración de dos años.

## Criterios de finalización

Cada RF citado por al menos una prueba (`grep -rnoE "025:RF-[0-9]+" tests | sort -u`); suite
con las siete variables en verde sin omitidas; Chincha, Pisco e Ica calibrados en DIgSILENT con
`--periodo 2025` desde la web, con «Sin proyecto 2025» válido y «Sin proyecto» (2026) sin
cambios (mismo resultado de flujo antes y después).

## Dudas abiertas

- Ninguna.
