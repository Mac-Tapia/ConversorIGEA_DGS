# Spec 105 — Evolución de los clientes fijos de cualquier alimentador

Estado: cumplida · Fecha: 2026-11-12 · Origen: usuario, 2026-11-12: «incluir en la web una función que pueda convertir lo
que te pido, de cualquier alimentador con sus clientes fijos, y un tablero donde se vea sus máximas y en qué fechas, su
crecimiento, sus variaciones, la tendencia de crecimiento, en qué mes consumió más potencia activa y reactiva». Y, el
mismo día: los informes y libros que genera la web se conservan como dataset en una carpeta de archivo de la máquina.

## Contexto y objetivo

Para AL209 se armó a mano un libro Excel que une enero a octubre de 2026 con la P (kW) y la Q (kVAR) de 15 minutos de
cada cliente fijo del alimentador y su evolución mensual (guion de la sesión, resultado en
`D:/csg/informes/AL209_clientes_fijos_2026-01_a_2026-10.xlsx`, fuera de git). Al hacerlo apareció un defecto de los
datos: `0426clientesImportantes.xlsb` repite los valores de marzo, día a día, en los cuatro clientes de AL209 que tienen
los dos meses; sin detectarlo, abril parecía un mes medido igual a marzo y falseaba el crecimiento. El objetivo es que
cualquier alimentador, de cualquier empresa, tenga ese libro y un tablero desde la web, con los libros que el operador
ya asignó en «2.1 · Libros de medición», y que el libro quede archivado como dataset fuera del espacio.

## Usuarios / actores

El ingeniero de planificación desde la web; el reconocimiento de libros nuevos (spec 104), que usa la misma detección de
mes copiado; los demás informes de la web, que pueden usar el archivo.

## Historias de usuario

- H1: Como ingeniero quiero ver, por cliente fijo de un alimentador, sus máximas, sus fechas y su crecimiento mes a mes,
  para saber si su demanda crece y cuándo consume más.
- H2: Como ingeniero quiero que un mes copiado se marque y no cuente, para no tomar un dato falso por un crecimiento.
- H3: Como ingeniero quiero descargar el libro y que quede archivado en la carpeta de datasets de la máquina.

## Requisitos funcionales (EARS)

Fuentes y clientes

- RF-1: CUANDO el operador pide la evolución de uno o varios alimentadores en un rango de meses, EL SISTEMA usará los
  libros de clientes importantes, de suministros y, si están, de medidores y de cabecera ya asignados en el espacio, sin
  pedir rutas nuevas.
- RF-2: EL SISTEMA tomará como clientes fijos de un alimentador los suministros cuyo radial, en el libro de suministros
  vigente, es ese alimentador, sin patrón de nombre ni empresa supuestos.
- RF-3: SI un suministro tiene código anterior y actual distintos, ENTONCES EL SISTEMA unirá sus meses bajo el código
  actual y dirá la renumeración aplicada.
- RF-4: EL SISTEMA leerá de cada cliente fijo la P (EA × 4) y la Q (ERI × 4) de cada registro de 15 minutos con los
  mismos lectores que la calibración y el pronóstico, de los libros activos de los meses del rango; el registro de las
  00:00 del día 1 cierra el mes anterior.

Indicadores

- RF-5: EL SISTEMA dará, por cliente y mes: la P máxima con su fecha y hora y la Q en ese instante; la Q máxima con su
  fecha y hora; la P y la Q medias; la energía activa (MWh) y reactiva (MVArh); el FP medio (energía activa entre la
  aparente del mes); y el factor de carga (P media entre P máxima).
- RF-6: EL SISTEMA dirá, por cliente y mes, sus registros frente a días del mes × 96 y si el mes está completo.
- RF-7: EL SISTEMA dará, por cliente, el crecimiento de la P máxima, de la energía activa y de la Q máxima del primer al
  último mes con datos, con esos dos meses; un cliente que entra a mitad del rango crece desde su primer mes.
- RF-8: EL SISTEMA dará, por cliente, la variación porcentual de la P máxima y de la energía activa de cada mes frente al
  mes anterior con datos.
- RF-9: EL SISTEMA dará, por cliente, la tendencia mensual: la pendiente de la recta de mínimos cuadrados sobre el número
  real de cada mes con datos, en % de su media, con al menos tres meses; un mes que falta no se rellena.
- RF-10: EL SISTEMA dirá, por cliente, el mes de mayor energía activa, el de mayor energía reactiva, el de mayor P máxima
  y el de mayor Q máxima.
- RF-11: EL SISTEMA dará los indicadores de RF-7 a RF-10 para la suma de los clientes fijos de cada alimentador, mes a
  mes con los clientes que tienen datos en ese mes, y la máxima coincidente de la suma de sus curvas.
- RF-12: DONDE el espacio tenga la medición de cabecera y el libro de medidores con el alimentador, EL SISTEMA dará por
  mes la máxima de cabecera, su instante, la P de los fijos en ese instante y su participación en %.

Calidad

- RF-13: SI el libro de un mes repite el mes anterior —P y Q iguales en el mismo día del mes y la misma hora en al menos
  el 95 % de los registros comparables de más de la mitad de los clientes con los dos meses—, ENTONCES EL SISTEMA marcará
  ese mes «copia de <mes>», lo conservará en el resumen mensual y lo dejará fuera del crecimiento, la variación, la
  tendencia y los meses de mayor valor.
- RF-14: La detección de RF-13 será una sola función de dominio, sin lectura de ficheros, que el reconocimiento de libros
  nuevos (104:RF-15) pueda usar.
- RF-15: SI un cliente fijo no tiene registros en el rango, ENTONCES EL SISTEMA lo dirá y seguirá con los demás; SI un
  alimentador no tiene clientes fijos, ENTONCES EL SISTEMA lo dirá y seguirá con los demás.
- RF-16: EL SISTEMA dirá los clientes de los libros que no están en el libro de suministros (no se sabe su alimentador),
  los meses incompletos, los valores distintos de un mismo instante entre libros (046:RF-12) y los avisos de lectura.

Trabajo, API y web

- RF-17: EL SISTEMA hará el cálculo como un trabajo del carril del motor, con avance por libro y cancelable entre libros.
- RF-18: `POST /api/workspaces/{id}/clientes-fijos/evolucion` lanzará el trabajo; `GET` de la misma ruta devolverá los
  alimentadores con clientes fijos, los meses con libro y el último resultado; `GET …/evolucion/curva` devolverá la curva
  de 15 minutos de un cliente del último resultado.
- RF-19: SI la petición pide un rango con el primer mes posterior al último, o ningún alimentador, ENTONCES la API la
  rechazará con 422.
- RF-20: La respuesta de cada ruta tendrá su contrato en `web/api_contract.py`, reflejado en `docs/asistente/openapi.json`
  y `frontend/src/api/esquema.ts`.
- RF-21: La web tendrá una pestaña «Evolución de clientes fijos» que no necesita la red cargada, con el selector de
  alimentadores, el rango de meses y el botón, desactivado mientras su trabajo corre.
- RF-22: El tablero mostrará una tarjeta por cliente con su P máxima del periodo y su fecha, su crecimiento, su
  tendencia y sus meses de mayor P y de mayor Q.
- RF-23: El tablero mostrará gráficos de líneas por mes de la P máxima, la Q máxima y la energía, por cliente y total.
- RF-24: El tablero mostrará una tabla de las variaciones mes a mes con color según suba o baje.
- RF-25: El tablero mostrará la curva de 15 minutos del cliente elegido.
- RF-26: El tablero mostrará los avisos de calidad de RF-13, RF-15 y RF-16.

Libro y archivo

- RF-27: EL SISTEMA escribirá un libro Excel con las hojas de evolución de la P máxima, de la energía y de la Q máxima,
  el resumen mensual, la variación mes a mes, una hoja por cliente con su serie de 15 minutos y las notas, con un gráfico
  de líneas en cada hoja de evolución, en la salida del espacio, donde lo lista «Resultados».
- RF-28: EL SISTEMA leerá la carpeta de archivo de `config/archivo.json` (`{"ruta": …}`), local y fuera de git; sin ruta
  no archivará nada.
- RF-29: La web dejará ver, poner y quitar la carpeta de archivo junto a las opciones.
- RF-30: CUANDO el libro de RF-27 esté escrito y haya carpeta de archivo, EL SISTEMA lo copiará a
  `<ruta>/informes/clientes_fijos/<alimentadores>/<AAAA-MM_a_AAAA-MM>/`, por un temporal que se renombra y con
  reintentos.
- RF-31: SI la copia falla, ENTONCES EL SISTEMA lo dirá en el registro y en el resultado, y conservará el libro de la
  salida del espacio.
- RF-32: EL SISTEMA nunca borrará ni sobrescribirá nada del archivo: un fichero igual ya archivado no se copia otra vez,
  y uno distinto con el mismo nombre se archiva con otro nombre.
- RF-33: El archivo será una función reutilizable `archivar(fichero, tipo, ambito, periodo)`, en un módulo propio.

Búsqueda y exactitud (usuario, 2026-11-12: «algoritmos de búsqueda avanzada para la precisión y efectividad de la
búsqueda, para que en la web todo sea real y correcto»)

- RF-34: EL SISTEMA decidirá los clientes de un alimentador conciliando el libro de suministros, el resumen de los
  libros mensuales de clientes (alimentador y SED de cada NIS) y, si el espacio tiene la red convertida, el alimentador
  en que está su SED; cada cliente llevará su veredicto —confirmado en N fuentes, discrepa (qué dice cada una) o en una
  sola fuente— y ninguno se asignará por el parecido de su nombre.
- RF-35: EL SISTEMA comparará los códigos sin ceros a la izquierda, sin el «.0» de Excel y sin espacios, y seguirá las
  renumeraciones anterior → actual encadenadas y en los dos sentidos, diciendo en qué meses traen los libros cada código.
- RF-36: SI un cliente de los alimentadores elegidos desaparece de los libros un mes y aparece otro código ese mismo mes
  con el mismo CL o la misma SED, ENTONCES EL SISTEMA lo propondrá como posible renumeración, sin aplicarla.
- RF-37: EL SISTEMA dará cada máxima con su fecha y hora exactas y la Q del mismo registro; a igual valor, la del primer
  instante.
- RF-38: DONDE haya medición de cabecera del alimentador, SI la suma de sus fijos en un instante supera la cabecera más
  un 5 %, ENTONCES EL SISTEMA lo avisará con el número de registros y el instante de mayor exceso.
- RF-39: El tablero tendrá un buscador de clientes por NIS (también el anterior), código CL, nombre, SED o alimentador,
  con el nombre sin tildes y tolerante a erratas, que muestra el puntaje y ordena por relevancia.
- RF-40: CUANDO se archive un fichero con el mismo nombre que otro ya archivado en la misma carpeta y con otro contenido,
  EL SISTEMA lo reemplazará por su versión vigente de una vez (reemplazo atómico, sin copias «(2)»); los demás ficheros
  de la carpeta nunca se tocan. Cambia RF-32. (Usuario, 2026-11-12: «solo la versión vigente, la última»; «a otros
  archivos no deben reemplazar, solo si es el mismo archivo».)

## Requisitos no funcionales

- Universal (P13): ningún alimentador, empresa, patrón de libro ni ruta de archivo por defecto.
- Escala (P2): el número de alimentadores y de clientes es variable; se lee cada libro una vez para todos los elegidos.
- Determinismo: los mismos libros y el mismo rango dan las mismas cifras.
- Datos de la distribuidora (P9): la comprobación real solo lee y sus cifras no van a git.

## Casos límite

Mes copiado; cliente que entra a mitad del rango; mes incompleto; un mes sin libro en medio del rango (la tendencia usa el
número real del mes); cliente renumerado; alimentador sin clientes fijos; sin cabecera o sin medidores; carpeta de
archivo que no existe o bloqueada por la sincronización; cancelación a mitad.

## Fuera de alcance

Pronosticar la demanda de los clientes (spec 089); corregir el libro copiado (se avisa y lo resuelve quien lo entrega);
archivar los demás informes (estudio, factibilidad, PIDE): pueden usar `archivar` en su spec.

## Criterios de finalización

Cada RF citado por al menos una prueba (`grep "105:RF-"`), pruebas de gobierno y frontend en verde, AL209 de enero a
octubre de 2026 con las mismas cifras que el libro hecho a mano y otro alimentador con clientes fijos probado, y la
pestaña recorrida en el navegador real.
