# Spec 004 — Cargas en un proyecto existente de DIgSILENT

Estado: cumplida (2026-10-14, verificación RF por RF); aprobada el 2026-10-08; cambio «Demanda medida» (RF-22 a RF-41) aprobado el 2026-10-08 · Fecha: 2026-10-08 · Origen: revisión del módulo de cargas del 2026-10-08

## Contexto y objetivo

El módulo de cargas actualiza demandas por SED y crea cargas nuevas en un proyecto de
DIgSILENT que **ya existe**, importado antes desde un DGS. Hoy depende de la conversión:
arma cada plan con el modelo del TXT o la MDB cargado en la web, y no se puede usar si el
alimentador no está en las entradas de ese espacio. El usuario lo aclara: es un módulo
aparte, que no tiene nada que ver con la conversión ni con la reconstrucción. Trabaja
sobre el proyecto de DIgSILENT y los Excel del operador; una demanda se actualiza si la
SED existe y, si no existe, se omite.

La revisión del 2026-10-08 encontró además fallos que este rediseño corrige:

- La línea de enlace de una carga nueva se creaba con R y X a cero si su tipo no estaba
  en el proyecto.
- La carga nueva se escribía con P, Q, cos φ y S a la vez, que en modo P–cos φ hace que
  DIgSILENT recalcule P y pierda el valor; sin releer y sin el signo de Q.
- El lote dejaba un escenario por alimentador, que nunca pueden estar activos a la vez, y
  creaba las cargas nuevas con ese escenario activo.
- El flujo de un alimentador escribía en la red base, sin variación ni vuelta atrás.
- Cancelar mataba el proceso a mitad de un alimentador.
- Nombres de 40 caracteres con la hora al minuto: se repetían, y deshacer buscaba por
  nombre y podía borrar el trabajo de otra ejecución.
- 22,9 kV, 0,22 kV y 60 Hz como valores por defecto de una empresa (constitución P13).

## Usuarios / actores

- Ingeniero de planificación que, desde la web, actualiza demandas o conecta cargas
  nuevas en un proyecto de DIgSILENT, en uno o en varios alimentadores.
- DIgSILENT PowerFactory 2024, por su API de Python, en el carril `powerfactory`.

## Historias de usuario

- H1: Como ingeniero quiero actualizar en bloque las demandas por SED de los
  alimentadores que elija de un proyecto de DIgSILENT, para estudiar la red con la
  demanda nueva sin volver a convertir.
- H2: Como ingeniero quiero conectar cargas nuevas en ese proyecto, una o muchas, para
  evaluar su efecto en la red existente.
- H3: Como ingeniero quiero que todo quede en una variación nueva, para activarla,
  compararla o borrarla sin tocar la red base.

## Requisitos funcionales (EARS)

Proyecto

- RF-1: EL SISTEMA trabajará sobre un proyecto existente de DIgSILENT que elige el
  operador, sin necesitar entradas cargadas ni convertidas en la web.
- RF-2: CUANDO el operador lee los proyectos, EL SISTEMA listará los proyectos de
  DIgSILENT y, de cada uno, sus alimentadores.
  *Cambio del 2026-10-09:* sustituido por la spec 005, RF-11 a RF-16: se listan solo los
  proyectos de la carpeta de importación.
- RF-3: CUANDO se aplican cambios, EL SISTEMA los grabará en una variación nueva del
  proyecto, con una etapa propia que graba, sin escribir en la red base.
- RF-4: EL SISTEMA dará a cada variación un nombre que no exista ya en el proyecto.
- RF-5: EL SISTEMA aplicará igual un alimentador que varios: un alimentador es un lote
  de uno.

Actualización de demandas

- RF-6: CUANDO una fila de demanda coincide con una sola carga de SED del alimentador
  elegido, EL SISTEMA actualizará su demanda.
- RF-7: SI una fila no coincide con ninguna carga del alimentador, ENTONCES EL SISTEMA la
  omitirá, la listará en el informe y seguirá con las demás.
- RF-8: SI un código coincide con más de una carga del mismo alimentador, ENTONCES EL
  SISTEMA la omitirá como ambigua y lo informará.
- RF-9: CUANDO escribe una demanda, EL SISTEMA escribirá solo los datos de entrada del
  modo de la carga, con el signo de Q, y releerá el valor efectivo.

Carga nueva

- RF-10: CUANDO una fila de carga nueva indica una barra del alimentador, EL SISTEMA la
  conectará a esa barra.
- RF-11: SI la fila no indica barra, ENTONCES EL SISTEMA la conectará a la barra del
  alimentador más cercana a sus coordenadas, según la posición GPS de las barras del
  proyecto.
- RF-12: EL SISTEMA usará para la línea de enlace el tipo de línea de la fila si existe en
  el proyecto y, si no, el tipo de una línea que llega a la barra de conexión.
- RF-13: EL SISTEMA tomará la tensión de media de la barra de conexión, la de baja de la
  fila o de un transformador de SED del mismo alimentador, y la frecuencia del proyecto.
- RF-14: CUANDO crea la carga, EL SISTEMA la escribirá como una demanda (RF-9) y la
  dibujará en el diagrama del alimentador si la barra de conexión está dibujada.
- RF-15: SI la carga nueva ya existe en el alimentador, ENTONCES EL SISTEMA no la creará
  otra vez y lo informará.
- RF-16: SI una carga nueva no se puede conectar, ENTONCES EL SISTEMA la omitirá con el
  motivo y seguirá con las demás.

Ejecución e informe

- RF-17: CUANDO el operador pide simular, EL SISTEMA informará qué coincide, qué se
  omitiría y dónde se conectaría cada carga nueva, sin escribir en el proyecto.
- RF-18: CUANDO termina de aplicar, EL SISTEMA ejecutará el flujo de carga con la
  variación activa e informará si converge y las tensiones extremas.
- RF-19: SI se cancela, ENTONCES EL SISTEMA terminará el alimentador en curso y no
  empezará otro.
- RF-20: EL SISTEMA dejará un informe por alimentador con las demandas actualizadas
  (antes y después), las omitidas y ambiguas, las cargas creadas y las no creadas.
- RF-21: SI un alimentador falla, ENTONCES EL SISTEMA seguirá con los demás.

Demanda medida (cambio aprobado el 2026-10-08)

El operador prepara las demandas con cuatro libros del área comercial y de medición:
medidor por alimentador, medición de cabecera (una hoja por medidor, exportación de los
medidores con registros cada 15 min), suministros (código actual, anterior, SED y
radial) y clientes importantes del mes (hoja resumen). Hoy los cruza a mano. La demanda
medida es una parte más del mismo módulo, junto a las que ya tiene: conectar una carga
nueva, conectar cargas nuevas en bloque y actualizar demandas en bloque (RF-1 a RF-21),
que no cambian. En esta iteración la demanda medida se extrae, se muestra y se descarga;
todavía no rellena el libro de demandas.

- RF-40: EL SISTEMA ofrecerá la demanda medida en la misma pestaña que la carga nueva,
  las cargas nuevas en bloque y la actualización de demandas en bloque.
- RF-41: EL SISTEMA mantendrá la carga nueva, las cargas nuevas en bloque y la
  actualización de demandas en bloque como las definen RF-1 a RF-21, con o sin demanda
  medida.

- RF-22: CUANDO el operador escribe un código de alimentador, EL SISTEMA mostrará cada
  código de medidor que le asigna el libro de medidores por alimentador.
- RF-23: SI el alimentador no figura en el libro de medidores, ENTONCES EL SISTEMA lo
  dirá y dejará escribir el código de medidor a mano.
- RF-24: CUANDO hay un código de medidor, EL SISTEMA buscará su hoja en todos los libros
  de medición de cabecera indicados, comparando el código sin distinguir mayúsculas,
  espacios ni separadores.
- RF-25: SI un medidor está repartido en varias hojas, una por magnitud, ENTONCES EL
  SISTEMA unirá sus registros por la fecha y hora de cada uno.
- RF-26: EL SISTEMA reconocerá las columnas de la medición por su nombre, en cualquier
  posición y con sus variantes (`kW tot`, `kW tot mean`, `PF sign tot us`, `PF lag
  mean`, `Pot Aparente`…).
- RF-27: EL SISTEMA dará, por cada medidor, el kW máximo y la fecha y hora en que
  ocurrió.
- RF-28: EL SISTEMA dará el kVAR, el kVA y el FP del mismo registro que el kW máximo, sin
  buscar sus propios máximos.
- RF-29: SI el alimentador tiene varios medidores, ENTONCES EL SISTEMA dará el resultado
  de cada medidor por separado, sin sumarlos.
- RF-30: SI el registro del máximo no trae kVA o FP, ENTONCES EL SISTEMA los calculará
  con su kW y su kVAR y los marcará como calculados.
- RF-31: EL SISTEMA no tomará como máximo un registro cuyo kW esté vacío o no sea un
  número.
- RF-32: SI un medidor no está en ningún libro de cabecera, o su hoja no tiene columna de
  kW, ENTONCES EL SISTEMA lo dirá, con el libro y la hoja si los hay, y seguirá con los
  demás medidores.
- RF-33: CUANDO el operador elige un libro de suministros, EL SISTEMA leerá de cada
  suministro el código actual (`Suministro Act`), el anterior (`Suministro`), la SED y
  el radial.
- RF-34: CUANDO el operador elige un libro de clientes importantes, EL SISTEMA leerá su
  hoja resumen encontrando la fila de cabecera y las columnas por nombre, en los dos
  formatos conocidos (`Nis`, `EA`, `ERI`, `Pot` y `SUMINISTRO`, `EA_TOTAL`, `ERI_TOTAL`,
  `POT_MAX`).
- RF-35: EL SISTEMA cruzará cada cliente importante con el libro de suministros por el
  código actual y, si no coincide, por el anterior, e indicará por cuál cruzó.
- RF-36: EL SISTEMA dará de cada cliente cruzado su SED, su radial, EA, ERI y potencia
  máxima. (Cambiado el 2026-10-09: el filtro por alimentador lo fija RF-43.)
- RF-37: SI un cliente importante no cruza con ningún suministro, o cruza sin SED,
  ENTONCES EL SISTEMA lo listará aparte con el motivo.
- RF-38: CUANDO el operador lo pide, EL SISTEMA descargará en un libro Excel la máxima
  demanda de cabecera y los clientes cruzados y no cruzados.
- RF-39: EL SISTEMA aceptará los libros por subida o, en local, por ruta del servidor; los
  de cabecera también como carpeta, de la que leerá todos los `.xls`, `.xlsx` y `.xlsb`.

Cambio del 2026-10-09, pedido por el operador al usarla con los libros reales:

- RF-42: CUANDO hay libro de medidores, EL SISTEMA ofrecerá en el código de alimentador
  una lista desplegable con sus alimentadores, sin repetir, en la que se puede escribir
  para buscar.
- RF-43: CUANDO el operador cruza los clientes después de buscar una máxima, EL SISTEMA
  mostrará solo los clientes cuyo suministro tiene por radial el alimentador de esa
  máxima, dirá cuántos de otros alimentadores no muestra y dejará aparte los que no
  están en el libro de suministros, porque no se sabe de qué alimentador son.

Cambio del 2026-10-09, visto con el alimentador IN111 de Ica: su libro de medidores da
«IN111_V18 Y IN111_V119»; en el libro de cabecera `IN111_V18` es solo el kW, `IN111_V19`
el kVAR y `IN111_V20` el kVA (canales del medidor `IN111`), y `IN111_V119` no existe.

- RF-44: SI la hoja de un medidor trae el kW pero le falta el kVAR o el kVA, ENTONCES EL
  SISTEMA los tomará, por la fecha y hora del registro del kW máximo, de las hojas de una
  sola magnitud del mismo medidor (`<medidor>_<sufijo>`) o de sus canales hermanos
  (`<base>_<sufijo>`, con la base con algún dígito), y nombrará esas hojas.
- RF-45: SI un medidor no tiene hoja pero es un canal de un medidor que sí la tiene, y otro
  medidor del mismo alimentador ya da ese medidor, ENTONCES EL SISTEMA dará un solo
  resultado, con un aviso que nombre el canal que no está.

Cambio del 2026-10-12, pedido por el operador al escribir una carga nueva a mano: el
formulario pedía a la vez kW, kVAR, kVA y FP, y la barra antes que las coordenadas.
Además, en un proyecto convertido la barra de BT de cada SED tiene el GPS de su nodo de
MT, así que la «barra más cercana» podía ser una de 0,38 kV; y la SED nueva quedaba sin
GPS, fuera de su sitio en el diagrama geográfico.

- RF-46: EL SISTEMA pedirá en el formulario de una carga nueva la demanda como potencia
  activa (kW) y factor de potencia; el kVAR y el kVA quedan solo en el libro.
- RF-47: EL SISTEMA pedirá en el formulario la ubicación por coordenadas (Lat/Lon o
  CoordX/CoordY) y dejará la barra, el alimentador, el tipo de línea y la tensión de baja
  como opciones que se despliegan.
- RF-48: CUANDO busca la barra más cercana a una carga nueva, EL SISTEMA considerará solo
  barras de más de 1 kV y, a igual distancia, preferirá la de la red a la interna de una
  SED.
- RF-49: CUANDO crea una carga nueva, EL SISTEMA escribirá en su SED, sus barras y su
  carga el GPS de la fila o, si la fila no lo trae, el de la barra de conexión.

Cambio del 2026-10-12, con un libro de planificación de cargas nuevas de SI213 (hoja
«DemandaNUEVA»): cabecera `DESCRIPCION`, `DEM PROY (KW)`, `TRONCAL`, `BARRA`, `SISTEMA`,
`SUBESTACIÓN`, `COORDENADAS UTM (X)`, `COORDENADAS UTM (Y)`. Sin columna SED la hoja
entera se rechazaba; tampoco trae el kVA del transformador, y su «BARRA» es la de la
subestación, no una barra del proyecto.

- RF-50: SI la barra indicada en la fila no está, o está en varios, de los alimentadores
  elegidos y la fila trae coordenadas, ENTONCES EL SISTEMA conectará la carga a la barra
  más cercana por GPS y lo anotará en la carga creada; sin coordenadas, no la creará.
- RF-51: EL SISTEMA reconocerá en el libro de cargas nuevas, además de los alias, las
  columnas cuyo nombre termine en kW o kVAR como demanda, las que contengan «UTM» o
  empiecen por «coord» y terminen en X/Este o Y/Norte como CoordX/CoordY, y «TRONCAL»
  como alimentador.
- RF-52: SI una carga nueva no trae kVA_instalado, ENTONCES EL SISTEMA tomará la menor
  potencia normalizada (IEC 60076-1, serie R10) que cubra su demanda y lo anotará en los
  avisos del plan.
- RF-53: SI el libro no trae columna SED, ENTONCES EL SISTEMA nombrará cada carga por su
  descripción (`DESCRIPCION`, `nombre`, `proyecto`, `cliente`) y, si tampoco la tiene, por
  su hoja y su fila, con un aviso.

Cambio del 2026-10-12 (spec 006, RF-27): con el escenario de operación activo, la
potencia de las cargas que manda es la del escenario, no la de la variación; las
demandas grabadas solo en la variación no se veían en la cabecera.

- RF-54: CUANDO actualiza demandas, EL SISTEMA las grabará también en el escenario de
  operación del caso en que escribe, si lo tiene.
- RF-55: MIENTRAS existan los tres casos de la spec 011, EL SISTEMA grabará las demandas
  también en el escenario de «Con proyecto» y no en el del «Caso base».

## Requisitos no funcionales

- Universal (P13): ninguna tensión, frecuencia ni CRS de una empresa como valor fijo.
- Demanda medida: los nombres de columna y de hoja reconocidos (RF-26, RF-33, RF-34)
  son variantes genéricas; las propias de una empresa se añaden en su perfil (P13).
- Demanda medida: buscar la cabecera abre libros de cientos de MB (1 GB entre los cuatro
  del caso de prueba): es un trabajo en cola, con progreso y cancelable (P7), y solo
  convierte a filas las hojas del medidor buscado.
- Demanda medida (P9): los libros son datos de la distribuidora; las pruebas usan libros
  sintéticos y, con datos reales, una variable de entorno que apunta a ellos.
- Escala: cualquier número de alimentadores y de filas; nada fijo en código ni pruebas.
- Idioma y estilo del proyecto (P10). Nada largo en una petición HTTP (P7).

## Casos límite

- Libro con filas de varios alimentadores, o de uno que no se eligió.
- La misma SED en dos alimentadores de una red unida: se busca solo en el elegido.
- Alimentador sin `ElmFeeder` en el proyecto: se busca en todo el proyecto y se avisa.
- Barra sin GPS o alimentador sin ninguna barra con GPS: la carga sin barra indicada no
  se puede conectar (RF-16).
- Tipo de línea indicado que no existe en el proyecto, o barra sin línea que llegue.
- Cancelar durante el primer alimentador, o entre dos.
- Demanda medida: un medidor cuyo código casa por prefijo con varias hojas que no son
  magnitudes de él (p. ej. `X1` y `X10`): se compara el código entero; un sufijo solo
  vale si la hoja tiene una sola magnitud.
- Demanda medida: dos registros con el mismo kW máximo: se da el primero en el tiempo.
- Demanda medida: hoja con columnas sin nombre al final, o con registros vacíos.
- Demanda medida: cliente importante repetido en la hoja resumen.
- Demanda medida: códigos de suministro escritos como número en un libro y como texto
  en otro (`1234.0` frente a `1234`).

## Fuera de alcance

- Demanda medida: repartir la máxima demanda de cabecera entre las SED, descontar los
  clientes importantes o rellenar con ello el libro de demandas; sumar medidores.

- Conversión, reconstrucción y catálogo de parámetros de la conversión.
- Plantilla rellenada con las cargas que ya tiene el proyecto: la plantilla es vacía.
- Borrar o mover cargas existentes.
- Cambios en la evaluación técnico-económica (`ComTececo`): se conserva tal cual, ahora
  sobre la variación del lote.

## Criterios de finalización

- `grep -rnoE "004:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-55.
- Suite completa en verde y RF-14 de la spec 001 sin cambios.
- `npx tsc --noEmit -p .` (en `frontend/`) y `npm run build` correctos.
- Prueba real en DIgSILENT, a cargo del usuario.

## Dudas resueltas (2026-10-08)

- Conexión de una carga nueva: la barra indicada o, si no hay, la más cercana por GPS.
- Dónde quedan los cambios: una variación nueva por aplicación, para todo.
- Conductor del enlace: el de la fila si existe en el proyecto o el de la red.
- Una SED sin coincidencia se omite y se informa; no es un error ni deshace nada.
- Demanda medida: se muestra y se descarga; el reparto entre SED queda para otro cambio.
- Demanda medida: varios medidores de un alimentador son unidades distintas: un
  resultado por medidor, sin sumar; solo el kW es un máximo, el resto es del mismo
  registro.
- Demanda medida: «Pot» del formato nuevo de clientes importantes es `POT_MAX`.
- Demanda medida: los clientes importantes no se filtran por el alimentador.
- Demanda medida: el cruce por código anterior sale de los datos: en los libros de enero
  a abril el `Nis` casa con `Suministro` y no con `Suministro Act`; en los de mayo a julio,
  al revés.

## Cambios de la spec 014 (2026-10-14)

- RF-15: «la carga nueva ya existe» no se busca solo en la red activa: se busca en todas
  las variaciones del proyecto, activas o no, y en la red de «Con proyecto», por su nombre
  en el alimentador (014:RF-23, RF-27). Si ya existe no se crea otra vez; si difiere del
  libro, se avisa de cada diferencia (014:RF-24 a RF-26, RF-28).
