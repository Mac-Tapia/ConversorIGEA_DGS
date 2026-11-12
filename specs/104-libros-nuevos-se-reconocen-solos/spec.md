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

- RF-20: EL SISTEMA dejará el resultado de cada libro en el registro del espacio y en un aviso visible del espacio, con la
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

## Criterios de aceptación

- Con libros sintéticos «0125 Pulso e.xlsx», «1025 Pulso.xlsx» y «0526clientesImportantes.xlsx» en la carpeta de su año,
  elegida directamente, cada uno recibe su mes; sin el arreglo, no.
- Con los libros reales, el reconocimiento detecta `1026clientesImportantes.xlsx` como nuevo y produce el aviso de RF-20,
  y los doce libros de 2025 reciben su mes. Las cifras van al informe de la tarea, nunca a git.
- Con libros sintéticos, un mes copiado se detecta y queda inactivo; un mes distinto no.

## Fuera de alcance

- Entrenar o aceptar modelos: el dataset se regenera; entrenar sigue siendo una orden del operador (089, 071).
- Apartar de la máxima de cabecera un mes repetido: se avisa (RF-17) y el operador elige otro periodo; el libro de
  cabecera trae todo el año y no se puede dejar inactivo entero.
- Comparar libros de fuentes distintas (constitución, fuentes independientes): todo se compara dentro de la misma fuente.
- Leer los libros de la distribuidora desde el código: se leen por las rutas que asigna el operador.
