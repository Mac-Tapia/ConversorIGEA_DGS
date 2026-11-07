# Spec 098 — La transferencia de carga del operador, en la calibración y en las obras

Estado: implementada · Fecha: 2026-11-07 · Origen: usuario, 2026-11-07, proyecto `20261105-124711_CSG_TXT_CA101_CHN102`:
«para la recalibración y la calibración se debe desactivar la transferencia y hacerla con sus alimentadores completos»,
y «todo esto debe servir para cualquier estudio parecido, no solo para el proyecto CA101_CHN102».

## Contexto y objetivo

En el proyecto de CA101 y CHN102 unidos, el operador hizo a mano en DIgSILENT una transferencia de carga de CA101 a
CHN102: dos tramos nuevos (SEC_1091_1082263_a y SEC_1091_1082269_c, sin variación) y el punto que unía esa parte a CA101
abierto. Con ella pasaron a CHN102 tres bancos de 300 kvar de CA101 (EBC_1, EBC_2 y EBC_3). Las SED transferidas
conservan su etiqueta de la fuente, `p:alimentador=CA101` (la del TXT exportado), pero las alimenta CHN102.

La recalibración por la web, con el mes 2026-07 y medidas de cabecera anteriores a la transferencia, terminó en
`VIOLACION_FISICA`: «pérdidas activas negativas en CA101 (-1 271,2 kW)». Último flujo: CA101 5 340 kW en cabecera,
CHN102 2 722 kW (objetivo 2 728 kW, 2026-07-27 08:45). La causa: las cargas de cada alimentador se toman por topología y
por etiqueta (`tools/ajuste_cabecera_pf.py::cargas_sed`), así que las transferidas cuentan en CA101 aunque su potencia
entra por la cabecera de CHN102.

La medida es de la red de la fuente. La calibración se hace con la red de la fuente: mientras se calibra, la
transferencia del operador se desactiva y cada alimentador queda completo, como cuando se midió; al terminar se deja
exactamente como estaba. «Con proyecto» y las obras sí se evalúan con la transferencia, y las transferencias que propone
la escalera se hacen donde ya hay una maniobra que abrir, como hizo el operador.

Vale para cualquier proyecto unido o sistema con cualquier número de alimentadores, para varias transferencias a la
vez (también en cadena, X→Y e Y→Z, y en los dos sentidos), para cualquier fuente (TXT, MDB, VNR-GIS) y para cualquier
distribuidora, y para cualquier cambio de topología del operador que pase SED de un alimentador a otro, con o sin
bancos o generadores en la parte que pasa. CA101_CHN102 es el caso que lo motiva y la prueba en DIgSILENT.

## Requisitos funcionales (EARS)

### Reconocer la transferencia

- RF-1: CUANDO empieza una calibración, EL SISTEMA buscará las SED con la etiqueta de un alimentador del proyecto que la
  red de ahora alimenta desde otro alimentador del mismo proyecto, con una pasada por las cargas y, solo si hay alguna,
  una pasada por cada clase de elemento de la red, sin recorrer la red una vez por alimentador.
- RF-2: EL SISTEMA reconocerá en cada zona transferida lo que no es de la fuente y la une al alimentador que la alimenta
  ahora (los tramos que no venían en el DGS aceptado, 028:RF-17, y lo que el DGS dejaba abierto y ahora está cerrado),
  y el camino más corto de elementos abiertos que la unía a su alimentador de origen.
- Aclaración de RF-2: un elemento abierto en el DGS aceptado no es el punto que abrió el operador. Sin los estados del
  DGS en el plan, el camino de RF-2 se supone y el informe lo dice. Un tramo nuevo que solo lleva a SED nuevas no es de
  la transferencia.

### Calibrar con la red de la fuente

- RF-3: CUANDO se calibra o recalibra un alimentador, los de un proyecto a la vez (021:RF-54) o los de un sistema o una
  SET (022), EL SISTEMA desactivará antes del primer flujo cada transferencia del operador que sale de o llega a uno de
  los alimentadores calibrados: abrirá lo de RF-2 que la une y cerrará el camino que la unía a su origen, para que cada
  cabecera se compare con todas sus SED por etiqueta.
- Aclaración de RF-3: las SED transferidas escalan con el factor de su alimentador de origen, y las pérdidas de cada
  alimentador salen de su cabecera y de sus SED por etiqueta, como cuando se midió.
- RF-4: SI la medida de cabecera es del mes de la importación del proyecto en DIgSILENT o de uno posterior, ENTONCES EL
  SISTEMA avisará de que no se sabe si la medida ya incluye la transferencia del operador.
- RF-5: CUANDO termina la calibración, también si falla, se cancela o salta una excepción, EL SISTEMA dejará la
  transferencia exactamente como estaba, en el mismo caso y escenario, después de anotar en disco cada cambio antes de
  hacerlo; SI una orden muere sin restituirla, ENTONCES la orden de calibración siguiente la restituirá al empezar y lo
  dirá.
- RF-6: EL SISTEMA restituirá la transferencia antes de guardar la calibración en el escenario, para que el escenario de
  «Sin proyecto» y lo que pasa a «Con proyecto» (014:RF-31) lleven la red del operador.
- RF-7: EL SISTEMA dirá en el informe de la calibración de cada alimentador afectado qué transferencia se desactivó (de
  qué alimentador a cuál, número y nombres de las SED, kW y kvar, lo que se abrió y lo que se cerró), que se restituyó y
  la comprobación elemento por elemento del estado final.
- RF-8: SI una zona no se puede devolver a su alimentador (SED de varios orígenes, sin nada de RF-2 que abrir o sin
  camino que cerrar, o unida por la red de la fuente a SED propias de quien la alimenta), o SI tras desactivarla sus SED
  no vuelven a su alimentador, ENTONCES EL SISTEMA no la tocará o la dejará como estaba, lo dirá con el motivo y
  calibrará con la red como está.

### Escaneo

- RF-9: CUANDO escanea (028), EL SISTEMA listará las transferencias del operador con sus SED, bancos y generadores, y
  marcará en el alimentador que las recibe los bancos, los generadores y los tramos nuevos que están en él por una
  transferencia desde otro, con el alimentador de origen.

### «Con proyecto» y las obras

- RF-10: EL SISTEMA dejará la transferencia del operador como la hizo en «Sin proyecto» y, al terminar la calibración,
  en «Con proyecto»; en las obras, «Con proyecto» la trata como una alternativa más de la escalera (RF-44).
- RF-11: EL SISTEMA propondrá una transferencia o un traslado de la escalera (087:RF-31 a RF-33, RF-52) solo desde una
  barra donde ya hay un interruptor o seccionador en un cubículo del tramo que entra a ella, o un acoplador en el
  camino que la separa de aguas arriba.
- RF-12: CUANDO construye una transferencia o un traslado, EL SISTEMA abrirá esa maniobra con la apertura anotada de
  081:RF-80, de modo que al restituir se cierre ese mismo elemento y no otro de igual nombre.
- RF-13: SI ninguna barra candidata de una transferencia o de un traslado tiene maniobra, ENTONCES EL SISTEMA no lo
  propondrá, lo avisará y la escalera seguirá con los demás escalones.

### La web y lo universal

- RF-14: EL SISTEMA llevará al plan de la calibración y al del escaneo los tramos del DGS aceptado, lo que ese DGS deja
  abierto o fuera de servicio y la fecha de la importación del proyecto.
- RF-15: EL SISTEMA reconocerá y desactivará las transferencias solo con lo que dicen los datos (etiquetas, topología,
  DGS aceptado), sin nombres de alimentador, de barra ni de empresa, y sin valores por defecto de una empresa
  (constitución P13).
- Aclaración de RF-14 (T6 en DIgSILENT, 2026-11-07): el plan lleva también las rutas del DGS aceptado, y la fecha es la
  del sello del nombre del proyecto (la de la importación) o, sin sello, la del DGS; no la de la aceptación del vínculo,
  que cambia al volver a verificarlo (salía 2026-11-07 por una aceptación del 2026-11-05).

### La red de la fuente, rama por rama (T6 en DIgSILENT, 2026-11-07)

La primera prueba real siguió con las pérdidas negativas: el informe dio dos zonas sin tocar («unida_en_la_fuente» y
«sin_punto»). Las sondas de solo lectura mostraron lo que hizo el operador: partió SEC_1091_1082263 con una mitad nueva
(SEC_1091_1082263_a) y una barra nueva con dos bancos, sin cambio de topología; partió SEC_1091_1082269 con un acoplador
nuevo ABIERTO («Breaker/Switch») y una línea nueva (SEC_1091_1082269_c), el punto que separa la zona de CA101; y creó un
acoplador nuevo CERRADO («Breaker/Switch(1)») entre dos barras del DGS que el DGS no une, el enlace por el que CHN102
alimenta la zona. El DGS del conversor no trae las maniobras abiertas (90 en este), así que `abiertos_dgs` venía vacío.

- RF-16: DONDE el plan trae el DGS aceptado, EL SISTEMA comparará cada rama de la red (tramos, acopladores,
  transformadores y equipos en serie, con los interruptores de sus cubículos) por clase, nombre y las dos barras que
  une con las del DGS, sin depender de que el DGS traiga lo abierto.
- RF-17: EL SISTEMA tratará como la rama de la fuente una rama del DGS cuyas barras cambiaron junto con la cadena de
  ramas y barras nuevas que vuelve a unir sus barras originales (una partición); SI toda la cadena está cerrada,
  ENTONCES no se tocará, y SI tiene un elemento abierto, ENTONCES ese es el punto que abrió el operador y se cerrará
  mientras se calibra.
- RF-18: EL SISTEMA tratará como enlace del operador una rama que no está en el DGS ni forma parte de una partición y
  que une la zona con otro alimentador, y la abrirá mientras se calibra.
- RF-19: EL SISTEMA anotará cada elemento tocado por su nombre completo y lo restituirá por él, de modo que dos
  elementos de nombre parecido («Breaker/Switch» y «Breaker/Switch(1)») no se confundan.

### Transferir por el enlace que ya existe, en la escalera (2026-11-07)

«Con proyecto» de CA101_CHN102 (job 7fcaf05e4edb): la escalera de CA101 probó primero «cambio a 22.9 kV con su fuente
(107 km, 156 SED)», que no cumple (mínima 0,807 p.u.), y fue a la obra integral. La búsqueda de vecinos salió vacía
porque 12333, 11969 y NODE_T_SU_empresa_Danper_Trujillo_SAC no tenían coordenadas, y concluyó «ni transferir o trasladar
a un vecino bastan» sin haber probado ninguna transferencia. El usuario: «¿ya probó la transferencia de carga antes de
ir a la migración a 22,9 kV?», «ya existe el punto de enlace con CHN102», «una vez transferido, debería probar con
bancos de nuevo», y que el oráculo decida y DIgSILENT confirme, sin cálculos de relleno.

- RF-20: SI una barra desde la que se busca un vecino no tiene coordenadas, ENTONCES EL SISTEMA tomará las de la barra
  con coordenadas más cercana por la red, y lo dirá; sin ninguna a su alcance, dirá que no hay vecinos para ella.
- RF-21: EL SISTEMA propondrá, antes que ningún enlace nuevo, la transferencia por cada enlace que ya existe entre el
  alimentador y un vecino del proyecto (un acoplador, un interruptor o un tramo, abierto o cerrado, que une una barra
  de uno con una del otro): abrir una maniobra existente del alimentador y cerrar el enlace si está abierto, sin línea
  nueva y sin más costo que el de las pérdidas, con las dos maniobras anotadas como en 081:RF-80.
- RF-22: EL SISTEMA propondrá las maniobras del camino de la cabecera al enlace, de la más cercana al enlace hacia la
  cabecera, y solo a un vecino con margen de tensión y de carga (087:RF-32).
- RF-23: EL SISTEMA evaluará las transferencias, por enlace existente y por enlace nuevo (087:RF-31 a RF-33), siempre
  desde una maniobra, junto con los bancos y antes del cambio de nivel de tensión, de la sección y de la terna, y
  dentro de cada escalón mandará el costo (042:RF-95).
- RF-24: CUANDO aplica una transferencia por enlace existente, EL SISTEMA dirá qué enlace usó, qué maniobra abrió, qué
  SED pasaron y con cuántos kW, y la tensión mínima y la carga máxima de los dos alimentadores antes y después.
- RF-25: SI una transferencia, sola, no deja en norma a los dos alimentadores, ENTONCES EL SISTEMA volverá a buscar la
  escalera desde los bancos con esa topología (las variantes de bancos y la búsqueda bayesiana del alimentador,
  087:RF-55, RF-56), y la combinación competirá por su costo total con las demás, medida con los dos alimentadores.
- RF-26: EL SISTEMA juzgará en el oráculo cada maniobra candidata y descartará, con su motivo, la que no converge, la
  que deja la red peor que sin obra y las que no están entre las mejores; solo las mejores y sus combinaciones irán a
  DIgSILENT, y el registro dirá cuántas generó, cuántas descartó y por qué, cuántas combinó y cuántas confirmó
  DIgSILENT; lo que el oráculo ya juzgó y DIgSILENT confirmó o descartó no se vuelve a medir en la etapa de
  transferencias.
- RF-27: EL SISTEMA buscará los enlaces y las maniobras con lo que dice la red, para cualquier número de alimentadores,
  cualquier fuente y cualquier distribuidora, sin nombres de alimentador ni de barra.

### Lo que dejó ver la T6 de «Con proyecto» (2026-11-07, job 11469a95f83e)

La sonda de solo lectura del 2026-11-07 dio: las barras en T de las cargas nuevas de CA101 (Danper y Buganvilla) cuelgan
de la segunda troncal de CA101, que sale de la misma barra de cabecera por otro cubículo y queda fuera de su
`ElmFeeder` (305 barras, 75 cargas; 063:RF-39); el conversor sí las cuenta en CA101 (`ElmCompleto`) y midió sus
tensiones. El paso a 22,9 kV dio las tensiones de sin obra al 1e-8 porque su flujo no convergía, la obra quedaba
inactiva (011:RF-66) y se medía sin ella; se presentaba como «no cumple». CHN102, sin cargas nuevas, quedó en 0,73 p.u.
en la zona que recibió y no se trató. Y el oráculo, equilibrado, daba 0,888 p.u. en 12431 y 0,817 en 12020, donde
DIgSILENT, con su flujo desequilibrado (`iopt_net=1`), medía 0,829 y 0,730.

- RF-28: SI una variante queda inactiva en el caso donde se mide, o con ella no cambia ninguna tensión ni corriente
  respecto de sin obra, ENTONCES EL SISTEMA la marcará «no aplicada» con su causa, no la contará como «no cumple» y lo
  dirá en el registro.
- RF-29: CUANDO un alimentador marcado del proyecto sin cargas nuevas tiene barras de media bajo el límite en «Con
  proyecto», EL SISTEMA le hará su escalera con esas barras como objetivo, antes que a los demás, empezando por la
  transferencia (de vuelta o por un enlace existente) y siguiendo desde los bancos, y aplicará la obra que lo corrija.
- RF-30: DONDE el grafo del oráculo trae la tensión que midió DIgSILENT en la misma lectura, EL SISTEMA llevará la
  caída de cada barra del oráculo a la medida, conservará esa proporción para cada obra que mida y dirá en el
  registro el desvío medio y el máximo antes de corregir.

### Segunda corrida de «Con proyecto» (2026-11-07, job 3ded64ef7a44)

CHN102 subió su escalera y CA101 no se resolvió: tiene dos caminos con cargas en problemas (la cola de CH_23 hasta
SEC_1091_1080932 y la rama de CH_10 y CH_18 hasta SEC_1091_1081392) y ninguna variante juntaba la obra de los dos; cada
una arreglaba su camino (0,991 en la cola y 0,917 en Buganvilla, o 0,922 en la cola y 0,962 en Buganvilla). Sin libro
CAPEX, la sección y la terna no tenían costo: el oráculo no podía dar ninguna por buena ni la bayesiana encontrarla, la
primera pasada mandó a DIgSILENT una sección de 50 mm², y CHN102 eligió el paso a 22,9 kV (29,3 km, 50 SED, que no
aguanta ni un año) porque era la única con costo de referencia. Los reguladores no cambiaban nada (`ComLdf.iopt_at =
0`) y contaban como «cumple». La ronda 087:RF-47 volvió a medir variantes ya medidas con la misma red.

- RF-31: CUANDO un alimentador tiene cargas en dos o más caminos, EL SISTEMA armará variantes que juntan la obra de
  línea de cada camino (terna o las secciones mayores aptas), con y sin bancos, y contará una vez cada tramo común,
  con el conductor mayor de los que pasan por él.
- RF-32: EL SISTEMA reutilizará la medida de DIgSILENT de una variante solo cuando la huella de la medida sea la misma
  (variaciones activas de «Con proyecto» con lo que graba cada una, los tipos con su sección e impedancia, lo abierto
  y fuera de servicio del escenario y la demanda de cada alimentador, cargas apartadas,
  barras, sorteos, valle y parámetros) y la medida guardada no sea sospechosa; en cualquier otro caso la volverá a
  medir, y dirá en el registro cuántas reutilizó, por qué era seguro y cuántas midió de nuevo y por qué. Las
  reutilizadas no se crean de nuevo en DIgSILENT, pero cuentan para parar la escalera (042:RF-90, 073:RF-18); si todas
  son sabidas, no se abre DIgSILENT.
- RF-33: EL SISTEMA propondrá para la caída, en las obras de varios caminos, solo las secciones mayores aptas para la
  corriente, no la menor que la lleva.
- RF-34: CUANDO una obra deja un regulador, EL SISTEMA activará el ajuste automático de tomas del flujo de cada caso de
  la obra (no el del caso activo), lo anotará en la fila y en el registro de disco antes de cambiarlo y lo devolverá a
  como estaba al borrar la variante evaluada, también si la creación se corta a mitad; mientras se mide, dejará fijas
  las tomas automáticas de los demás transformadores de dos y tres devanados y de los reguladores ajenos (anotadas en
  un lote y devueltas), y aplicada, dirá cuáles regulan; guardará el valor del ajuste de antes de la primera obra con
  regulador, por proyecto y caso (en una obra de antes de guardarlo, el que anotó la obra), y lo devolverá al
  retirar la última; MIENTRAS quede activa otra variación con
  regulador, no apagará el ajuste, y lo dirá; SI con el regulador nada cambia respecto de la misma variante sin él,
  ENTONCES la marcará «no aplicada» (RF-28).
- RF-35: SI el libro CAPEX no trae el costo de la sección o de la terna, ENTONCES EL SISTEMA las costeará con el km
  del cambio de nivel, la terna por su factor del perfil (1,5 si no lo da), por confirmar; medirá el alcance
  (042:RF-92) de cada una que cumple, y dirá «no llega al horizonte más corto (N años)» de la que se midió en 0 años y
  «sin medir» de la que no se midió.
- RF-36: CUANDO la escalera vuelve a correr sobre un alimentador con una obra que ella misma aplicó en «Con proyecto»
  (o aplicada sin origen guardado que es la misma obra, por el nombre de su variación o por su contenido, que la
  elegida que la escalera aplicó), EL SISTEMA medirá las alternativas y la pila de esa obra, como una variante más con
  el costo de toda la pila, con la red sin ella y sin lo que hizo en la operación (deshecho y devuelto); SI
  la red, las cargas, los sorteos, los costos y la revisión son los de su elección, ENTONCES la conservará sin medir. La
  sustituirá solo SI la de corto plazo (RF-37) cumple y cuesta menos al año, o la vieja medida ya no cumple; con la
  medida de la vieja dudosa, la conservará y lo dirá; la vieja que se queda resuelve el alimentador solo si su medida
  cumple. Para sustituir, aplicará primero la nueva con la vieja desactivada y su operación deshecha, comprobará que
  la nueva queda activa y converge, y desde ahí solo irá hacia delante: borrará la vieja por los nombres exactos de sus
  variaciones, y lo que no se deje borrar quedará desactivado y se dirá; SI algo falla antes, ENTONCES borrará lo creado
  de la nueva (por los nombres que anotó al crearlo) con su operación y la vieja volverá activa, con su operación, sin
  recrearla; cada paso, con la operación de las dos, irá a un diario en disco que la orden siguiente completa o
  deshace, y lo aplicado del espacio se pondrá al día con él. Nunca
  comparará ni retirará lo que aplicó el operador (040:RF-8, 014:RF-3) ni lo aplicado sin origen ni evidencia, que solo
  avisará; SI sin la vieja «Con proyecto» ya cumple, ENTONCES la conservará y dirá que sobra.
- RF-37: EL SISTEMA aplicará en el estudio de «Con proyecto» solo la alternativa de corto plazo: la más barata, en el
  orden de la escalera (042:RF-56), que cumple desde el año 0 del análisis hasta el año del periodo de corto plazo (el
  del perfil, `escalera.periodo_corto_plazo_anios` o `planificacion.periodo_corto_plazo_anios`, o el primer año del
  PIDE, `planificacion.anios_horizonte`; sin él, 4, el periodo del PIDE), con la máxima, los sorteos y el valle de hoy
  y la demanda proyectada de ese año; SI ninguna llega a ese año, ENTONCES elegirá la más barata que cumple hoy y lo
  dirá. No planteará en este estudio la obra de los años siguientes (usuario, 2026-11-07: «en estos estudios solo haz
  el año cero»).
- RF-38: CUANDO una obra de la escalera nombra la mitad «(n)» que dejó una carga nueva al partir un tramo, y esa mitad no
  existe en la red sobre la que se graba la obra (las cargas nuevas apartadas), EL SISTEMA tomará el tramo entero, una
  sola vez, y no dará la obra por ajena al alimentador. CA101 (2026-11-07): «El tramo 'SEC_1091_1081392(1)' no es del
  alimentador CA101» en toda terna o sección de varios caminos, que salía «no cumple» sin medirse.

- RF-39: EL SISTEMA buscará en qué año el alimentador, con la alternativa de corto plazo puesta, vuelve a salir de
  límites con la demanda proyectada (las cargas nuevas, constantes, 030:RF-9): el oráculo corregido (RF-30) busca el
  primer año que falla desde el siguiente al del periodo hasta el horizonte, y DIgSILENT lo confirma solo en ese año y
  en el anterior; SI no hay oráculo o DIgSILENT no lo confirma, ENTONCES DIgSILENT lo buscará por bisección.
- RF-40: EL SISTEMA dará en el informe y en la web, por alimentador, el año en que vuelve a tener problemas, con la
  barra y su tensión, y que la alternativa de ese año se plantea en el PIDE partiendo de la de corto plazo; no buscará
  ni medirá en este estudio ninguna obra de ese año.
- RF-41: CUANDO a una variante le falta tensión, EL SISTEMA probará más módulos de banco (3, 4, …, del tamaño del
  perfil), solos y con las obras de línea de varios caminos, mientras el oráculo corregido vea que mejora la barra peor
  y el valle no pase del límite, y dirá hasta cuántos módulos probó y por qué se paró. CA101 (2026-11-07), con su
  transferencia: 1×300 kvar dejaba la cola en 0,874 p.u. y 2×300 kvar con refuerzo en 0,922; no se probaba un tercero.
- RF-42: EL SISTEMA no propondrá una transferencia por un enlace que une barras de tensiones distintas sin un
  transformador, y lo dirá. CA101 y CHN102 (2026-11-07): tras pasar CHN102 a 22,9 kV, «Breaker/Switch» unía 10 kV con
  22,9 kV.

- RF-43: CUANDO el alimentador que recibe una transferencia del operador queda fuera de límites en «Con proyecto»,
  EL SISTEMA probará primero otro punto de corte de la misma transferencia (devolver parte de la zona al que la cedió
  por el punto que abrió el operador, abriendo otra maniobra de la zona, de la que más devuelve a la que menos), aunque
  el que la recibe de vuelta no tenga margen ahora, midiendo los dos (RF-25); después, bancos y obras de línea, en la
  misma tensión mientras haya alternativa más barata.
- RF-44: EL SISTEMA tratará en «Con proyecto» la transferencia del operador como una alternativa más de la escalera
  del alimentador que cede: la deshará allí (nunca en «Sin proyecto») para medir sin ella, la propondrá con su mismo
  corte («la transferencia del operador») y con los otros cortes por su enlace (RF-21, RF-22), juzgará cada una en
  los dos alimentadores (RF-25) y del año 0 al del periodo (RF-37), y competirá por costo con las demás; SI no se
  elige, ENTONCES la escalera seguirá sin ella; el que la recibe se trabaja después del que cede, y el informe da una
  fila propia con sus cifras, con ella y sin ella, y si se eligió. Usuario (2026-11-07): «para obras se propone la
  transferencia de carga y se analiza si da solución a la mala calidad de producto en la cola de CA101».

- RF-45: EL SISTEMA evaluará en «Con proyecto» los escalones en orden fijo, cada uno entero antes del siguiente:
  bancos; cambio de sección; terna nueva; transferencia de carga (la del operador, otros cortes y enlaces); después, el
  cambio de nivel y el regulador; y la obra integral solo con todos evaluados. Una combinación va en el escalón de su
  obra mayor (la de varios caminos, en el de su obra de línea). En cada escalón el oráculo ordena y filtra, DIgSILENT
  confirma las mejores, y SI alguna cumple (del año 0 al del periodo, en los dos alimentadores si hay transferencia)
  ENTONCES se para ahí y elige la más barata de ese escalón; si no, pasa al siguiente. Dirá por escalón cuántas dio el
  oráculo, cuántas descartó, cuántas midió DIgSILENT y cuántas cumplen. Cambia 098:RF-23 y 087:RF-40 (ya no se va a la
  obra integral porque no cumplan las primeras del oráculo). Usuario (2026-11-07): «se evalúa con bancos, después con
  cambio de sección de cables, después nueva terna, después transferencia de carga; nada debería saltar».

## Relación con otras specs

- Amplía 006/015/021/022/028 (calibración y recalibración): la cabecera se compara con la red de la fuente.
- Amplía 028:RF-17 (tramos nuevos) y 028:RF-26 (cambios del operador): el escaneo dice cuáles son de una transferencia.
- Amplía 087:RF-31 a RF-33 y RF-52: las barras candidatas, solo con maniobra; y cambia 087:RF-41 en el orden: la
  transferencia se mide antes que el paso a 22,9 kV (098:RF-23).
- Amplía 042:RF-56: la transferencia cuenta con los bancos en el grupo económico (098:RF-23).
- Cambia 042:RF-30 para varios caminos: la sección de un camino y la terna de otro sí se combinan (098:RF-31).
- Amplía 025:RF-73 (evaluación reutilizada) a cada variante (098:RF-32) y 042:RF-54 a la sección y la terna (098:RF-35).
- Cambia 042:RF-56 y 042:RF-75 en lo que se aplica: la de corto plazo, que llega al año del periodo (098:RF-37);
  amplía 042:RF-60 a la obra elegida con la regla anterior (098:RF-36). El año en que vuelve a fallar va con las
  alternativas que leen el plan y el PIDE (072:RF-4).
- Al PIDE (072, 030), no a este estudio: plantear en cada año del PIDE, según lo que pida y la normativa de
  planeamiento, la obra encima de las anteriores, empezando por la de corto plazo de aquí. El enganche: el año en que
  vuelve a fallar (`vuelve_a_fallar` de la elegida guardada) y `escalera_optima.largo_plazo` y `contiene`, que quedan para
  esa ruta. Queda anotado como pendiente en la 072 (T14).
- Amplía 081:RF-80 y RF-81: un interruptor de cubículo se anota con su nombre completo.
- No cambia la 013 (transferencia como estudio entre dos alimentadores) ni 081:RF-83 y RF-84: lo del operador que no
  deja barras sin tensión se respeta en «Con proyecto».

## Fuera de alcance

- Reconocer una transferencia hecha en un proyecto sin «Sin proyecto» (la primera calibración lo crea desde el «Caso
  base», que aún no tiene lo hecho después a mano).
- Saber la fecha exacta en que el operador hizo la transferencia: el aviso de RF-4 usa la de la importación.
- Transferencias a un alimentador de otro proyecto de DIgSILENT.

## Criterios de finalización

- `grep -rnoE "098:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-45.
- Recalibrado por la web el proyecto CA101_CHN102 (mes 2026-07), sin pérdidas negativas y con la transferencia del
  operador como la dejó; «Con proyecto» corrido con la transferencia puesta.
