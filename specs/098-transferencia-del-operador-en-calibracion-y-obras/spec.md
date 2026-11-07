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

- RF-10: EL SISTEMA conservará en «Con proyecto» la transferencia del operador en su mismo punto, sin revertirla ni
  medirla como si no existiera, y las obras de la escalera (042, 087) se evaluarán con ella.
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

## Relación con otras specs

- Amplía 006/015/021/022/028 (calibración y recalibración): la cabecera se compara con la red de la fuente.
- Amplía 028:RF-17 (tramos nuevos) y 028:RF-26 (cambios del operador): el escaneo dice cuáles son de una transferencia.
- Amplía 087:RF-31 a RF-33 y RF-52: las barras candidatas, solo con maniobra; y cambia 087:RF-41 en el orden: la
  transferencia se mide antes que el paso a 22,9 kV (098:RF-23).
- Amplía 042:RF-56: la transferencia cuenta con los bancos en el grupo económico (098:RF-23).
- Amplía 081:RF-80 y RF-81: un interruptor de cubículo se anota con su nombre completo.
- No cambia la 013 (transferencia como estudio entre dos alimentadores) ni 081:RF-83 y RF-84: lo del operador que no
  deja barras sin tensión se respeta en «Con proyecto».

## Fuera de alcance

- Reconocer una transferencia hecha en un proyecto sin «Sin proyecto» (la primera calibración lo crea desde el «Caso
  base», que aún no tiene lo hecho después a mano).
- Saber la fecha exacta en que el operador hizo la transferencia: el aviso de RF-4 usa la de la importación.
- Transferencias a un alimentador de otro proyecto de DIgSILENT.

## Criterios de finalización

- `grep -rnoE "098:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-27.
- Recalibrado por la web el proyecto CA101_CHN102 (mes 2026-07), sin pérdidas negativas y con la transferencia del
  operador como la dejó; «Con proyecto» corrido con la transferencia puesta.
