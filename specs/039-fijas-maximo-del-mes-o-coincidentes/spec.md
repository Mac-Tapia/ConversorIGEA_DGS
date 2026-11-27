# Spec 039 — Fijas del máximo del mes o coincidentes con la cabecera, elegidas y comparadas en la web

Estado: cumplida (2026-11-21: T11 cerrada con la corrida real en DIgSILENT de MEJ27-FIJAS; todas sus tareas cerradas) · antes implementada (reabierta el 2026-11-21 con MEJ27-FIJAS por orden del usuario: RF-24, RF-25) · antes cumplida (reabierta el 2026-11-20 con MEJ10-FIJAS: RF-23) · antes cumplida (2026-11-08: tareas cerradas por orden del usuario, sin corrida propia; su aceptación pasa a la spec 100) · Fecha: 2026-10-31 · Origen: petición del usuario, 2026-10-31, tras auditar a
mano NA293 («implementa que exista opción para hacer análisis y estudios desde la web estas dos
opciones … los valores máximos de fijos del mes y coincidente en la misma fecha»)

## Contexto y objetivo

En la recalibración de NA293 (2026-10-31) la Q de cabecera no cuadraba. La auditoría a mano dio:
las 15 fijas suman 7 707,5 kW y 3 725,5 kvar, cada una la POT máxima de su hoja de 15 minutos (EA ×
4) con el ERI × 4 de ese registro y ERC = 0; el registro de cabecera del 03/10 11:00 (9 889 kW,
1 711 kvar) es coherente con su kVA; y en un mismo instante (26/09/2026 11:00) las fijas suman
6 681 kW y 3 061 kvar frente a 9 669 kW y 1 717 kvar en toda la cabecera. Cada criterio cambia lo que
pesan las fijas, y el operador quiere elegirlo y compararlo desde la web.

Amplía 035:RF-1, RF-17 y 022:RF-84: hoy el plan toma el registro del instante de la máxima si el
libro de clientes lo tiene y, si no, la POT del mes, sin que el operador lo elija ni lo vea.

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA dejará elegir en la tabla cruzada de la web, al cruzar los clientes, el
  criterio de todas las fijas, «máximo del mes» o «coincidente con la cabecera», y el mismo
  criterio pasará al plan de la calibración y de la recalibración.
- Aclaración de RF-1 (usuario, 2026-10-31): por defecto, «coincidente con la cabecera».
- RF-2: CON «máximo del mes», EL SISTEMA dará a cada fija la POT máxima de su hoja de 15 minutos
  (EA × 4) y la Q del ERI × 4 de ese mismo registro.
- RF-3: CON «coincidente con la cabecera», EL SISTEMA dará a cada fija la EA × 4 y el ERI × 4 de
  su registro en el instante de la máxima de cabecera del alimentador.
- RF-4: SI el libro de clientes no tiene ese instante, ENTONCES EL SISTEMA no tomará otro para esa
  fija: lo dirá, con el periodo que daría la misma fecha, y no aplicará la calibración hasta que el
  operador elija otro periodo o el «máximo del mes».
- RF-5: EL SISTEMA ofrecerá en la web «Comparar los criterios de las fijas», como trabajo que no
  abre DIgSILENT: por fija, los dos valores de P y Q con su registro; sus sumas; la cabecera medida
  en el instante de la máxima; y la Q de la red y de los bancos de la última simulación en
  DIgSILENT, con la Q que quedaría para las escaladas con cada criterio.
- RF-6: EL SISTEMA dirá en el informe de la calibración el criterio de las fijas que usó.
- RF-7: EL SISTEMA tendrá en la tabla cruzada un desplegable con los alimentadores de la máxima buscada, para marcar
  cuáles toman sus fijas con «máximo del mes»; los no marcados toman el criterio general del selector. Usuario,
  2026-11-05, Pisco: «¿podría hacerse un desplegable para seleccionar qué alimentadores se van a considerar en las
  máximas del mes en la tabla cruzada?», con el criterio por alimentador y todos calibrados juntos.
- RF-8: EL SISTEMA llevará el criterio de cada alimentador a la tabla, al plan de la calibración y de la recalibración,
  y al informe (RF-6), y dirá en la tabla el criterio de cada fila.

### Cliente a su máxima (usuario, 2026-11-07)

Motivo, por calidad de producto: «en la tabla cruzada un cliente entra con su máxima de operación y a veces no
coincide con la máxima de la cabecera». El valor coincidente de un cliente puede no representar su operación
crítica, y para estudiar la tensión el operador quiere subir ese cliente, uno por uno, a su máxima P y Q, y verlo,
cargarlo y recalibrar desde la web («no debería ser interno: debe tener un botón o selector manual»).

- RF-9: EL SISTEMA mostrará en cada fila de fija de la tabla cruzada, con la máxima de cabecera buscada, sus dos
  valores juntos: el coincidente (RF-3), con la fecha y hora del registro de la máxima de cabecera, y el de su máxima
  del mes (RF-2), con la fecha y hora de su registro.
- RF-10: EL SISTEMA mostrará en cada fila de fija la diferencia de P entre su máxima del mes y su valor coincidente,
  en kW y en % del coincidente.
- RF-11: EL SISTEMA dejará ordenar la tabla cruzada por esa diferencia y filtrarla por una diferencia mínima en %, y no
  marcará ningún cliente por su cuenta: la decisión es del operador.
- RF-12: EL SISTEMA tendrá en cada fila de fija una casilla «a su máxima»; el cliente marcado irá con la P y la Q de su
  máxima del mes (RF-2) y los demás, con el criterio de su alimentador (RF-7).
- RF-13: EL SISTEMA tendrá acciones para marcar y desmarcar cada cliente y para desmarcar todos a la vez.
- RF-14: EL SISTEMA dirá en cada fila el criterio con que va y, en la del cliente marcado, sus kW y sus kvar de máxima
  con la fecha y hora de su registro.
- RF-15: EL SISTEMA guardará la selección en el espacio de trabajo y la volverá a cargar al reabrir la web.
- RF-16: EL SISTEMA llevará la selección al plan de la calibración y de la recalibración; si la petición no trae una
  selección, la guardada en el espacio.
- RF-17: EL SISTEMA tendrá en el paso de la tabla cruzada un botón «Recalibrar con estos criterios» que lance la
  recalibración del proyecto por la vía de 028:RF-21, con el criterio general, los alimentadores con «máximo del mes»
  y los clientes a su máxima.
- RF-18: EL SISTEMA listará en el informe de la calibración (RF-6) los clientes a su máxima, cada uno con su registro,
  sus kW y sus kvar.
- RF-19: EL SISTEMA tratará al cliente a su máxima como una fija más: su subida se descuenta de las escaladas y la
  cabecera sigue cuadrando.
- RF-20: SI el cliente marcado no tiene hoja de 15 minutos, o su POT no está en ella, ENTONCES EL SISTEMA lo dirá y lo
  llevará con su POT y su EA/ERI del mes (004:RF-66), sin bloquear.
- RF-21: SI el cliente marcado no tiene el registro del instante de la máxima, ENTONCES EL SISTEMA no bloqueará por él
  (RF-4): va a su máxima.
- RF-22: EL SISTEMA reconocerá al cliente marcado por su código del libro de clientes, para cualquier fuente y
  distribuidora, sin nombres ni códigos fijos.
- RF-23: (orden del usuario del 20-11) EL SISTEMA permitirá registrar en el espacio una corrección fechada del factor
  del medidor de un cliente (código, factor, mes desde el que vale y motivo), sin tocar el libro original. DESDE ese mes,
  la tabla cruzada, el plan del ajuste y la plausibilidad de las fijas (015:RF-73) llevarán su EA, ERI, POT, registro y
  curva por ese factor, y su fila dirá la corrección. En la web, el aviso `FM_CAMBIADO` (004:RF-111) lleva el botón que
  registra el FM anterior, con poco texto.
- RF-24: (orden del usuario del 21-11, MEJ27-FIJAS) CUANDO el cliente de una fija mida más que la cabecera de su
  alimentador (015:RF-73 a), ANTES de dar la fija por imposible EL SISTEMA buscará su causa, en este orden:
  (a) su FM cambió entre el libro del mes y el anterior con un salto de energía igual a la razón de los FM entre días
  completos de cada mes (004:RF-111), la cabecera no saltó en esos días (± 20 % y menos de la mitad del salto) o no los
  tiene, y con el FM anterior el cliente cabe en su cabecera: registrará la corrección de RF-23 con origen
  `automatico`, su motivo y su evidencia (meses y días, FM y medidores antes y después, energía del cliente y de la
  cabecera, registros que pasaban), la aplicará a su fila y seguirá; (b) los registros que pasan son a lo sumo 4 o el
  1 % del mes y todos atípicos en el cliente o en la cabecera por el filtro de Hampel (mediana de 4 registros a cada lado,
  3,5 × 1,4826 × MAD): los excluirá como datos malos y, si la fija sale de uno de ellos, irá con la mediana local, dicho;
  (c) el cliente cabe siempre en la cabecera de otro alimentador del mismo trabajo (la misma SET o el mismo sistema):
  propondrá la reasignación con el margen mínimo, sin aplicarla; (d) si nada lo explica, dirá la hipótesis más probable
  con sus números (registros, exceso máximo, fracción de la energía de la cabecera y el factor con el que cabría). Una
  corrección ya registrada, también la anulación con factor 1, manda: con ella no se deduce otra. Lo deducido se ve en la
  web y se revierte con otra corrección.
- RF-25: (orden del usuario del 21-11; enmienda 015:RF-73 y 006:RF-47) UNA fija que siga siendo físicamente imposible
  tras RF-24 (mide más que su cabecera, o pide más de 4 veces los kVA de su grupo con la media del mes que sí cabe) NO
  parará su alimentador: EL SISTEMA la liberará (su SED se reparte con las escaladas por su potencia instalada), calibrará
  el alimentador con el resto y el informe dirá `fijas_liberadas` con sus motivos y su diagnóstico. La calibración de una
  SET o de un sistema nunca se detiene por un alimentador; nunca queda «no puede cuadrar» a secas. Una fija solo dudosa
  por el reparto (`FIJAS_DEJAN_SIN_ESCALADAS`) queda con su medida y se avisa.
- RF-26: (orden del usuario del 26-11) DONDE un medidor de cabecera registre mal (un factor o el signo), EL SISTEMA
  permitirá al operador registrar en el espacio su corrección (medidor, factor, valor absoluto y, si quiere, el mes
  desde el que vale, con su motivo); al leer la cabecera multiplicará P, Q y S de sus registros por el factor y, si lo
  pide, tomará su valor absoluto, antes de buscar la máxima, la curva o la máxima por barra; lo dirá en los avisos del
  medidor, y el libro no se tocará. (LL203, L-LL123: 31 078 kW de máxima en una cabecera de media tensión; el medidor
  registraba diez veces de más y con el signo cambiado.)
- RF-27: (usuario, 2026-11-27: «sí, hazlo», tras LL203 el 26-11 y LL202 el 27-11) CUANDO la máxima de un alimentador
  sea mayor que la de la barra de su SET que lo alimenta (la suma de sus medidores, con sus correcciones), EL SISTEMA
  lo dirá en los avisos del medidor y propondrá la escala de su hoja (0,1, 0,01 o 0,001, la mayor con la que cabe)
  con valor absoluto, desde el mes de su máxima, y un botón la registrará como la corrección de RF-26; no corregirá
  nada por su cuenta. (LL202, L-LL122: 9 296 kW con la barra B-LL2T1 en 3 139 kW; sus 19,3 A a 24 kV son 805 kVA.)
- RF-28: (usuario, 2026-11-27, LL203) SI un cliente fijo pasa su cabecera solo en pocos registros (la hipótesis es que
  la cabecera no midió toda la carga en ellos, RF-24 d) y hace al menos la mitad de la energía de su cabecera, ENTONCES
  EL SISTEMA no lo liberará (enmienda RF-25): quedará fijo con su medida y lo dirá. (SE80083, 481000151: 15 registros
  de 2 976 y el 68 % de la energía de LL203; liberado, sus 2 180 kW se repartieron entre las demás SED.)

## Relación con otras specs

- Con «coincidente», RF-4 cambia 035:RF-19 y 004:RF-67: un libro de otro mes, o una hoja sin el
  registro del instante, ya no deja tomar el de la POT sin decirlo; el plan no se prepara. Con
  «máximo del mes», 035:RF-19 sigue igual: no bloquea.
- Un cliente sin hoja de 15 minutos va con su EA/ERI del mes con los dos criterios (004:RF-66) y
  no bloquea: ningún criterio le daría otro valor.

## Fuera de alcance

- Cambiar los valores de las hojas o de la red: la comparación solo lee.
- Marcar clientes «a su máxima» por una regla automática (RF-11): solo el operador los marca.
- Alimentadores con central (021): su cabecera es por zonas; se comparan sus fijas, no la cabecera.

## Criterios de finalización

- `grep -rnoE "039:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-25.
- RF-24 y RF-25 en DIgSILENT (T11): la corrida A del bloque del 20-11 repetida sin la corrección manual da los cuatro
  alimentadores válidos con la corrección automática del FM.
- CA191_CHN192 recalibrado desde la web con un cliente a su máxima: su P y su Q de máxima en el informe y la cabecera
  cuadrada.
- NA293 desde la web: «máximo del mes» da 7 707,5 kW y 3 725,5 kvar; «coincidente» con el periodo
  2026-09 da el registro de cada fija en el instante de su máxima de cabecera.
