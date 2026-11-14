# Spec 104 — Los libros nuevos de demanda se reconocen solos

Estado: aprobada · Fecha: 2026-11-12 · Origen: usuario, 2026-11-12, al añadir el libro de clientes importantes de octubre
de 2026: «todo lo has hecho tú; el conversor debe hacerlo de forma automática, reconocerlo». Coordinador, el mismo día:
el libro de abril de 2026 repite los valores de marzo y nadie lo detectó.

## Contexto y objetivo

La web solo reindexa los libros de demanda cuando el operador pulsa «Actualizar índice» (specs 013 y 025). El libro de
octubre de 2026 de clientes importantes llegó a la carpeta y lo verificó Claude a mano: mes, clientes, registros por
cliente frente a 31 días × 96, clientes nuevos y los que no están en el libro de suministros. Eso es trabajo del conversor
(memoria «conversor automático, yo solo vigilo»).

En el mismo lector se halló un defecto: elegida la carpeta de un año (`…/2025`) en vez de la de los años, los libros
«MMAA Pulso» quedaban sin año y, por tanto, sin el mes de su nombre (025:RF-6); solo entraban los que traían una fecha
única dentro. A 301 de 323 clientes les faltaba octubre de 2025 y su historia empezaba en julio. Los de 2026 con fecha en
sus hojas entraban, pero sin mes. Y un libro mensual que copia otro mes (abril de 2026 igual a marzo, día a día) entraba
como dato bueno en la máxima y en el pronóstico.

El objetivo es que la web reconozca sola cada libro nuevo o cambiado, lo verifique con el detalle de la revisión manual,
lo diga, y deje el dataset del pronóstico al día sin entrenar (spec 089, datos vivos).

## Usuarios / actores

El operador de la web, que deja libros en las carpetas de demanda de su espacio; el pronóstico (089), que lee esas carpetas.

## Requisitos funcionales (EARS)

### Reconocer solo

- RF-1: CUANDO arranca la web, se abre un espacio o vence el intervalo de revisión, EL SISTEMA comparará la foto (ruta
  relativa, tamaño y fecha de cada libro) de las fuentes de demanda del espacio —cabecera, clientes importantes,
  suministros y medidores— con la del último reconocimiento.
- RF-2: EL SISTEMA revisará cada 10 minutos por defecto; la variable `CSG_LIBROS_INTERVALO_MIN` cambia el intervalo y con
  `0` la revisión periódica se apaga.
- RF-3: EL SISTEMA hará la comparación sin abrir ningún libro y fuera del bucle de la web, y el reconocimiento será un
  trabajo de la cola: la página no espera.
- RF-4: MIENTRAS el espacio tenga un trabajo del motor en marcha o en cola, EL SISTEMA no encolará el reconocimiento y lo
  intentará en la revisión siguiente.
- RF-5: CUANDO haya libros nuevos o cambiados, EL SISTEMA reindexará esa fuente y publicará el índice; en la cabecera
  solo se abren los libros nuevos o cambiados (025:RF-28).
- RF-6: SI una fuente no tiene foto de un reconocimiento anterior, ENTONCES EL SISTEMA tomará como conocido lo que ya
  publica su índice (los libros listados, y en clientes su fecha de índice), de modo que un libro dejado después del
  último índice cuenta como nuevo sin reabrir los demás.

### Verificar cada libro nuevo

- RF-7: EL SISTEMA dirá de cada libro nuevo de clientes su mes y año y de dónde salen (nombre con el año de su carpeta,
  nombre con el año de sus fechas, fechas de dentro o asignación del operador).
- RF-8: EL SISTEMA comparará los registros de cada serie con los días del mes × 96 y dirá si el mes está completo o
  cuántas series y días le faltan.
- RF-9: EL SISTEMA dirá el periodo (primer y último registro) y los avisos de lectura del libro.
- RF-10: EL SISTEMA dirá los clientes nuevos y los que faltan frente al libro del mes anterior.
- RF-11: EL SISTEMA dirá los clientes que no están en el libro de suministros vigente, ni como código actual ni como
  anterior.
- RF-12: SI el libro de suministros vigente es de otro mes que el libro de clientes, ENTONCES EL SISTEMA dirá que falta el
  libro de suministros de ese mes.
- RF-13: EL SISTEMA dirá los clientes con todos sus registros en cero.
- RF-14: EL SISTEMA dirá los registros que caen fuera del mes del libro en un mes que ya da otro libro activo, y el libro
  activo del mismo mes, si lo hay (046:RF-12); los valores distintos de un mismo instante los dice el dataset (089:RF-74).
- RF-15: SI un libro mensual repite los valores de otro mes —P y Q iguales en el mismo día del mes y la misma hora en al
  menos el 95 % de los registros de más de la mitad de las series comparables—, ENTONCES EL SISTEMA lo dirá con los dos
  meses.
- RF-16: SI un libro de clientes repite otro mes, ENTONCES EL SISTEMA lo dejará inactivo en el índice: no se usa para la
  máxima ni para el pronóstico hasta que llegue el libro correcto.
- RF-17: SI en una serie de un libro de cabecera un mes repite el anterior con el mismo criterio, ENTONCES EL SISTEMA lo
  dirá con la hoja y los dos meses.
- RF-18: SI un libro no se puede leer, ENTONCES EL SISTEMA dirá el motivo y seguirá con los demás: nada bloquea.
- RF-19: EL SISTEMA verificará en cada reconocimiento como mucho tres libros, los de mes más reciente primero, y dirá los
  que quedan sin verificar.

### Avisar

- RF-20: EL SISTEMA dejará el resultado de cada libro en el registro del espacio y en un aviso visible del espacio, en
  «Novedades de los libros» de 2.1, junto a los libros y no en la cabecera de la página (usuario, 2026-11-13), con la
  forma «Llegó octubre 2026 de clientes importantes: 280 clientes, completo (31 días), 2 nuevos sin suministro: …; falta
  el libro de suministros de octubre», y el de un mes repetido con la forma «Abril 2026 de clientes importantes repite los
  valores de marzo 2026: pida el libro correcto; mientras, abril no se usa para la máxima ni para el pronóstico».
- RF-21: CUANDO el operador da por visto un aviso, EL SISTEMA dejará de mostrarlo; un libro ya reconocido no vuelve a
  avisar mientras su foto no cambie.

### Datos vivos del pronóstico

- RF-22: CUANDO llega un mes nuevo o cambia un libro de cabecera o de clientes, EL SISTEMA marcará el dataset del
  pronóstico del espacio como desactualizado, con la lista de libros nuevos.
- RF-23: CUANDO el dataset está desactualizado y el espacio tiene cabecera y medidores, EL SISTEMA lo regenerará en un
  trabajo aparte, con su huella, sin entrenar ningún modelo: entrenar lo decide el operador.
- RF-24: EL SISTEMA guardará junto al dataset su perfil: por serie y por clase y magnitud, la cobertura, los huecos, los
  ceros, los negativos y los picos sobre el percentil 95, y los apartados con su motivo.
- RF-25: La herramienta de dataset del pronóstico escribirá ese mismo perfil al guardar el dataset.
- RF-26: SI un libro de clientes repite los valores del mes anterior, ENTONCES el dataset del pronóstico lo apartará con
  su motivo, también fuera de la web.

### Mes de los libros

- RF-27: SI la carpeta elegida es la de un año (cuatro cifras), ENTONCES EL SISTEMA dará ese año a sus libros y el mes de
  su nombre (025:RF-6), como si se hubiera elegido la carpeta de los años.
- RF-28: SI un libro no tiene año de carpeta, ENTONCES EL SISTEMA tomará el mes de su nombre con el año de sus fechas
  cuando ese mes está entre ellas.
- RF-29: SI de un libro no se deduce el mes, ENTONCES EL SISTEMA lo dirá en sus avisos, con lo que se pierde (las hojas
  «día, hora» no se leen) y cómo asignarlo.

### El trabajo de fondo no estorba al operador (2026-11-12)

En la web del operador, al abrir un espacio sin índice anterior, el reconocimiento tomó como nuevos los 22 libros y
ocupó el carril del motor más de 2 minutos («22/22»); cancelarlo tardó 40 s y, al terminar, lanzó la regeneración del
dataset. Mientras, «Cargar / listar alimentadores» quedó desactivado y después en cola: «¿por qué no arranca o está lista
la web?».

- Aclaración de RF-3 y RF-4: desde RF-30 el reconocimiento no es un trabajo de la cola, y el motor ocupado es cualquier
  trabajo del operador en el motor o en DIgSILENT, de cualquier espacio (RF-32).
- RF-30: EL SISTEMA hará la revisión de libros y la regeneración del dataset en un carril de fondo propio, fuera de la
  cola de trabajos: ningún trabajo del operador quedará en cola por ellos.
- RF-31: MIENTRAS corre un trabajo de fondo, LA WEB no desactivará ningún botón del operador y lo mostrará en un
  indicador propio del aviso de libros, no en la barra de trabajos.
- RF-32: CUANDO el operador tiene un trabajo en el motor o en DIgSILENT mientras corre uno de fondo, EL SISTEMA
  detendrá el de fondo en menos de 2 s, conservará lo que ya terminó y lo reanudará cuando no quede ningún trabajo del
  operador.
- RF-33: EL SISTEMA leerá cada libro del trabajo de fondo (índice y verificación) en un proceso aparte de prioridad baja
  (en Windows, BELOW_NORMAL_PRIORITY_CLASS), que se termina al ceder.
- RF-34: SI una fuente no tiene foto anterior ni índice publicado, ENTONCES EL SISTEMA tomará su foto como base sin
  abrir, indexar ni verificar ningún libro; solo se verificarán los libros que aparezcan o cambien después.
- RF-35: CUANDO el operador pulsa «Verificar todos ahora» en el aviso de libros, EL SISTEMA reindexará las fuentes de
  clientes y de cabecera y verificará todos sus libros en el carril de fondo, sin el tope de RF-19.
- RF-36: EL SISTEMA regenerará el dataset del pronóstico solo cuando no haya trabajos del operador desde hace 5 min
  (`CSG_DATASET_REPOSO_MIN`), en un proceso aparte de prioridad baja y nunca dentro del proceso de la web.
- RF-37: SI el operador lanza un trabajo mientras se regenera el dataset, ENTONCES EL SISTEMA terminará ese proceso y
  dejará el dataset desactualizado, para el siguiente reposo.
- RF-38: MIENTRAS el dataset esté desactualizado, EL SISTEMA dirá cuándo se regenerará: la hora prevista, que espera a
  que el motor quede libre o que faltan la cabecera o los medidores.
- RF-39: CUANDO cambian el carril de fondo, los avisos o el dataset, EL SISTEMA lo publicará en los eventos del espacio y
  LA WEB volverá a leer el estado del servidor, sin dejar a la vista un aviso desfasado.
- RF-40: EL SISTEMA revisará al arrancar y en cada intervalo solo los espacios modificados o abiertos en las últimas 24
  horas (`CSG_LIBROS_RECIENTES_H`), no todos los del equipo: la web del operador recorría los 43 y encolaba la lectura
  de uno detrás de otro en el motor común a todos los espacios.
- RF-41: SI el operador no tiene abierto un espacio (ninguna pestaña conectada ni pedido en los últimos 10 min),
  ENTONCES EL SISTEMA solo comparará la foto de sus libros, sin leer ninguno, y dirá que lo nuevo se lee al abrirlo.

### El dataset no se queda «regenerando» y lo apartado se ve (2026-11-13)

En el espacio de la web del operador el dataset quedó en «regenerando» desde las 10:32 del 2026-11-12 durante más de
11 horas, sin carpeta `pronostico/` en su ejecución. La web se había cerrado de golpe 47 minutos después de lanzarlo
(su registro arranca otro proceso a las 11:19 sin «Shutting down»): el proceso que regeneraba murió con ella, el estado
en disco siguió diciendo «regenerando», y la web siguiente solo volvía a mirar los «desactualizado». Además tenía la
vigilancia apagada (`CSG_LIBROS_NUEVOS=0`) y su «Revisar ahora» del 2026-11-13 a las 06:07 tampoco lo tocó. El mismo
día, dos libros de clientes de 2025 quedaron fuera del dataset y solo constaban en la cuenta de «motivos_apartados» del
dataset, que nadie abre (089:RF-107 a RF-113 corrigen su lectura).

- RF-42: CUANDO lanza la regeneración del dataset, EL SISTEMA guardará con su estado la identidad de su proceso y la
  de la web (pid y hora de arranque), como el diario de trabajos (096:RF-6).
- RF-43: SI el dataset está «regenerando» y su proceso no está vivo ni lo lleva esta web, ENTONCES EL SISTEMA lo pasará a
  desactualizado, con la hora y el motivo de la interrupción, al leer el estado, al revisar los libros y al arrancar.
- RF-44: CUANDO el dataset queda interrumpido, EL SISTEMA lo dirá en un aviso de los libros de demanda del espacio, con
  cuándo empezó y por qué se cortó, y lo retomará en el siguiente reposo del motor (RF-36), o en la siguiente revisión
  de libros si la vigilancia está apagada.
- RF-45: SI la regeneración que lleva esta web pasa su plazo (`CSG_DATASET_PLAZO_MIN`, 120 min), ENTONCES EL SISTEMA
  terminará su proceso, dejará el dataset desactualizado con ese motivo y lo avisará.
  Al terminarlo, por su plazo o porque el operador lanza un trabajo (RF-37), EL SISTEMA escribirá
  el estado del dataset antes de dejar de tenerlo como proceso propio, para que ninguna lectura en
  medio lo dé por «sin proceso vivo» (RF-43) ni deje un segundo aviso (carrera hallada el 2026-11-14).
- RF-46: CUANDO la web se apaga con el dataset regenerándose, EL SISTEMA terminará su proceso y lo dejará interrumpido
  en disco; al arrancar, también con la vigilancia apagada, revisará los «regenerando» de los espacios recientes sin
  abrir ningún libro.
- RF-47: CUANDO la regeneración del dataset aparta un libro o dice algo de un libro entero (su formato, su mes), EL
  SISTEMA lo mostrará como aviso de los libros de demanda del espacio, con el nombre del libro y el motivo.
- Aclaración de RF-26 (2026-11-13): el libro de abril de 2026 que se apartaba por repetir marzo es un acierto, no un falso
  positivo: en 19 hojas comparadas con energía, los 56 034 registros son iguales a los de marzo, y trae energía en 31
  días, que abril no tiene (089:RF-113).

## Criterios de aceptación

- Con libros sintéticos «0125 Pulso e.xlsx», «1025 Pulso.xlsx» y «0526clientesImportantes.xlsx» en la carpeta de su año,
  elegida directamente, cada uno recibe su mes; sin el arreglo, no.
- Con los libros reales, el reconocimiento detecta `1026clientesImportantes.xlsx` como nuevo y produce el aviso de RF-20,
  y los doce libros de 2025 reciben su mes. Las cifras van al informe de la tarea, nunca a git.
- Con libros sintéticos, un mes copiado se detecta y queda inactivo; un mes distinto no.

## Fuera de alcance

- Terminar el proceso de otra web viva: un «regenerando» con su proceso vivo en otro sitio no se toca (RF-43).

- Entrenar o aceptar modelos: el dataset se regenera; entrenar sigue siendo una orden del operador (089, 071).
- Apartar de la máxima de cabecera un mes repetido: se avisa (RF-17) y el operador elige otro periodo; el libro de
  cabecera trae todo el año y no se puede dejar inactivo entero.
- Comparar libros de fuentes distintas (constitución, fuentes independientes): todo se compara dentro de la misma fuente.
- Leer los libros de la distribuidora desde el código: se leen por las rutas que asigna el operador.
