# Spec 020 — SED fijas sobrecargadas: aviso y transformadores nuevos desde la web

Estado: aprobada (2026-10-16) · Fecha: 2026-10-16

> Cambiada por la spec 032 (2026-10-28): los transformadores van en la variación
> `SED_NTP_<proyecto>`, no en la red (RF-16), porque el «Caso base» conserva los kVA del
> archivo; solo bloquea una variación del operador que grabe (RF-17); y la propuesta tras
> calibrar incluye también las escaladas por encima del umbral del perfil (RF-1, RF-6 y
> «Fuera de alcance»), distinguidas de las que pasan del 100 %.

## Contexto y objetivo

La calibración de PA217 (`20261016-094237_IGEA_PA217`, 2026-10-16) no era válida y la web
solo decía «las cargas no consumen en el flujo lo que tienen escrito». La causa estaba en
el modelo, no en las cargas: la SED fija SE30940 recibía los 3818 kVA de su cliente sobre
un transformador de 400 kVA (955 %), y SE30642, SE30480 y SE30424 también pedían más que
su potencia. Con cargas PQ, «Sin proyecto» no convergía ni con las escaladas al 0,5 % de
su kVA. Esas SED ya se listaban (015:RF-59), pero en un desplegable debajo del fallo y sin
ninguna acción. Se arreglaron con un guion suelto, como en CA101 (015, T22 y T26): cada
transformador a la menor potencia de la NTP 370.400 con la máxima ≤ 80 %, y por encima de
630 kVA unidades de 630 kVA en paralelo. Tras ese cambio la calibración salió válida, a
−0,34 % y sin ajustes del flujo. El objetivo es que la web avise de forma visible de las
SED fijas sobrecargadas, proponga para cada una los transformadores según su necesidad
y, con la confirmación del operador, los implemente y vuelva a calibrar.

## Usuarios / actores

Ingeniero de planificación desde la web, en el ajuste a la máxima de cabecera (spec 006,
015); DIgSILENT PowerFactory 2024.

## Historias de usuario

- H1: Como ingeniero quiero ver, al calibrar, qué SED fijas piden más que su
  transformador, para saber por qué la calibración no converge o no es válida.
- H2: Como ingeniero quiero una propuesta de transformadores con datos de ficha para cada
  una y elegir cuáles se implementan, para no hacerlo a mano en DIgSILENT.
- H3: Como ingeniero quiero que, implementados, se vuelva a calibrar sola, para ver en el
  mismo paso si la red ya cuadra.

## Requisitos funcionales (EARS)

Detección y aviso

- RF-1: CUANDO simula o aplica la calibración, EL SISTEMA marcará como sobrecargada cada
  SED fija cuya demanda aparente supere el 100 % de su potencia instalada.
- RF-2: EL SISTEMA tomará como potencia instalada de una SED la suma de sus
  transformadores en DIgSILENT, cada uno por su número de unidades en paralelo.
- RF-3: CUANDO hay SED fijas sobrecargadas, la web mostrará al principio del resultado
  del ajuste un aviso con cuántas son y, por SED, sus clientes, su demanda en kVA, su
  potencia instalada y el porcentaje.
- RF-4: SI la calibración no es válida o no converge y hay SED fijas sobrecargadas,
  ENTONCES EL SISTEMA dirá en el aviso que la sobrecarga es la causa probable y remitirá a
  la propuesta de RF-6.
- RF-5: EL SISTEMA seguirá calibrando con SED fijas sobrecargadas: el aviso no bloquea
  (015:RF-59).

Propuesta

- RF-6: CUANDO hay SED fijas sobrecargadas, EL SISTEMA propondrá para cada una la menor
  potencia de la tabla de fichas del perfil de empresa con la que su demanda quede en el
  umbral de carga del perfil o por debajo.
- RF-7: SI ni la mayor potencia de la tabla deja la demanda en el umbral, ENTONCES EL
  SISTEMA propondrá unidades iguales de la mayor potencia en paralelo, las menos que lo
  cumplan.
- RF-8: EL SISTEMA elegirá la tabla de fichas por la tensión primaria del transformador
  de la SED.
- RF-9: EL SISTEMA mostrará en la propuesta, por SED: su transformador y su tipo actual,
  la potencia instalada, la potencia nueva, las unidades en paralelo, las pérdidas en
  vacío y con carga, la corriente en vacío, la tensión de cortocircuito, la tabla de
  origen y la carga prevista en porcentaje.
- RF-10: DONDE el perfil de empresa no trae tabla de fichas, EL SISTEMA mostrará el aviso
  de RF-3 sin propuesta y dirá que falta la tabla en el perfil.
- RF-11: SI la tensión primaria de una SED no cae en ningún rango de las tablas del
  perfil, ENTONCES EL SISTEMA la listará sin propuesta y dirá su tensión.
- RF-12: SI una SED sobrecargada tiene más de un transformador, ENTONCES EL SISTEMA la
  listará sin propuesta y lo dirá.

Confirmación

- RF-13: EL SISTEMA mostrará una casilla por cada SED con propuesta, todas marcadas al
  mostrarse, y un botón «Implementar transformadores».
- RF-14: MIENTRAS ninguna casilla esté marcada, EL SISTEMA tendrá el botón desactivado.
- RF-15: CUANDO el operador pulsa el botón, EL SISTEMA lo ejecutará como un trabajo de
  DIgSILENT en la cola, con progreso en el Registro y cancelable.

Aplicación en «Sin proyecto»

- RF-16: EL SISTEMA escribirá los transformadores nuevos en «Sin proyecto», en la red, sin
  crear una variación.
- RF-17: SI en «Sin proyecto» hay una variación activa o una etapa grabando, ENTONCES EL
  SISTEMA no cambiará nada y nombrará la variación o la etapa.
- RF-18: EL SISTEMA cambiará solo los transformadores de las SED marcadas.
- RF-19: EL SISTEMA dará a cada transformador cambiado un tipo propio por potencia, con
  las pérdidas en vacío y con carga, la corriente en vacío y la tensión de cortocircuito
  de la ficha, y las tensiones, el grupo de conexión y la secuencia cero de su tipo
  actual.
- RF-20: EL SISTEMA no modificará ningún tipo de transformador existente.
- RF-21: SI ya existe un tipo propio con el mismo nombre y los mismos datos, ENTONCES EL
  SISTEMA lo reutilizará.
- RF-22: SI ya existe un tipo propio con el mismo nombre y otros datos, ENTONCES EL
  SISTEMA no cambiará esa SED y nombrará el tipo y el dato que difiere.
- RF-23: EL SISTEMA pondrá en el transformador cambiado el número de unidades en paralelo
  de la propuesta.
- RF-24: CUANDO termina el cambio, EL SISTEMA informará por SED el tipo, la potencia y las
  unidades de antes y de después.

Recalibración

- RF-25: CUANDO termina el cambio, EL SISTEMA volverá a calibrar «Sin proyecto» en el
  mismo trabajo, con el mismo plan del ajuste, y mostrará su resultado y su validación
  física.
- RF-26: CUANDO la recalibración termina, EL SISTEMA comprobará que ninguna SED fija queda
  por encima del 100 % de su potencia instalada y que cada SED cambiada queda en el
  umbral de carga del perfil o por debajo.
- RF-32: SI tras el cambio la recalibración no es válida o no converge, ENTONCES EL SISTEMA
  lo dará como fallo, conservará los transformadores cambiados y dirá qué sigue fallando
  (las cargas que no consumen lo escrito, el remedio del flujo que necesitó o las SED que
  siguen sobrecargadas), porque la sobrecarga ya no es la causa.
- RF-27: SI se cancela después del cambio y antes de recalibrar, ENTONCES EL SISTEMA
  conservará los transformadores cambiados y dirá que falta calibrar.
- RF-28: CUANDO la recalibración es válida, EL SISTEMA la registrará como la última
  calibración del alimentador, igual que un ajuste desde la web (014:RF-10).

Tabla de fichas en el perfil

- RF-29: DONDE el perfil de empresa trae tablas de fichas, cada una tendrá su rango de
  tensión primaria, su norma de origen y, por potencia en kVA, las pérdidas en vacío y
  con carga en W, la corriente en vacío en % y la tensión de cortocircuito en %.
- RF-30: DONDE el perfil de empresa trae tablas de fichas, también traerá el umbral de
  carga con que se dimensiona, en porcentaje.
- RF-31: SI una fila de la tabla está incompleta o tiene un valor no positivo, ENTONCES EL
  SISTEMA no propondrá con esa fila y nombrará la fila y el perfil.

Cambios en la red, lo original y lo nuevo (usuario, 2026-10-17: «todos los cambios que
se hacen se deben reportar como original existente con su potencia instalada y el valor de
potencia cambiada con sus respectivos códigos SED»)

- RF-60: CUANDO la calibración cambia un elemento de la red (un transformador de RF-16, un
  banco puesto a su máxima capacidad de 015:RF-66), EL SISTEMA lo reportará en una tabla
  de cambios con el código de su SED (o la barra, si no es de una SED), el elemento, lo
  original existente con su potencia instalada y lo nuevo con su potencia.
- RF-61: EL SISTEMA dará la potencia instalada de un transformador como unidades × kVA y
  su total en kVA, y la de un banco como escalones conectados × kvar por escalón.
- RF-62: EL SISTEMA mostrará la tabla de cambios en el resultado del ajuste de la web y la
  guardará en el informe del ajuste.

## Requisitos no funcionales

- Ninguna norma, potencia ni umbral en el código: todo viene del perfil de empresa (P13).
  Electro Dunas: NTP 370.400-2013, Tablas 6 (AT ≤ 17,5 kV) y 7 (17,5 < AT ≤ 36 kV) de las
  especificaciones de FONAFE (2017, rev. 2), de 15 a 630 kVA, y umbral del 80 %.
- La propuesta se calcula con lo que ya leyó la calibración: no añade flujos.
- Mensajes en español (P10).

## Casos límite

- SED de PA217: 8 × 630 kVA (SE30940), 3 × 630 (SE30480), 2 × 630 (SE30642), 1 × 500
  (SE30424), Tabla 7 (22,9 kV) (RF-6, RF-7, RF-8).
- SED con ya varias unidades en paralelo que sigue sobrecargada (RF-2, RF-23).
- Dos SED de distinta tensión de baja o grupo que piden la misma potencia: tipos propios
  distintos (RF-19).
- Tipo propio ya creado por un cambio anterior (PA217, CA101): se reutiliza o se avisa
  (RF-21, RF-22).
- El operador desmarca una SED con un cruce dudoso: no se cambia, y la calibración puede
  seguir sin salir válida (RF-18, RF-26).
- Perfil sin tablas (otra distribuidora) (RF-10).
- Cancelar con el trabajo en cola, durante el cambio y entre el cambio y la recalibración
  (RF-15, RF-27).

## Fuera de alcance

- SED escaladas y SED fijas entre el 80 % y el 100 %: no entran en la propuesta
  (usuario, 2026-10-16).
- Cambios en «Con proyecto» como obra en una variación (spec 016).
- SED con más de un transformador: se listan sin propuesta (RF-12).
- Volver atrás un cambio desde la web: se hace en DIgSILENT.
- Citar los transformadores cambiados en el informe de estudio (spec 017).
- Comprobar el cruce del cliente con su SED.

## Requisitos que esta spec cambia

| Requisito | Antes | Ahora |
| --- | --- | --- |
| 015, «Fuera de alcance» | Corregir el modelo de forma automática: lo corrige el operador en DIgSILENT | Los transformadores de las SED fijas sobrecargadas, con la confirmación del operador desde la web (RF-13 a RF-24) |
| 015:RF-59 | Aviso en el informe y en la web, debajo del resultado | El mismo aviso, al principio del resultado, con la propuesta (RF-3, RF-6) |

## Criterios de finalización

- Cada RF citado por al menos una prueba (`grep -rnoE "020:RF-[0-9]+" tests | sort -u`).
- Suite en verde y el front compilado.
- Prueba en DIgSILENT desde la web con un alimentador con SED fijas sobrecargadas: aviso,
  propuesta, implementación y recalibración **válida**, sin la adaptación automática del
  modelo.

## Dudas resueltas

1. Dónde se escribe: en «Sin proyecto», en la red, sin variación, porque ahí se calibra
   (usuario, 2026-10-16; RF-16).
2. Qué SED: solo las fijas que superan el 100 % de su potencia instalada; se dimensionan
   con el umbral del 80 % (usuario, 2026-10-16, que corrigió un primer «por encima del
   80 %»; RF-1, RF-6).
3. Confirmación: una casilla por SED y un botón (usuario, 2026-10-16; RF-13).
4. Después: recalibra sola en el mismo trabajo (usuario, 2026-10-16; RF-25).
5. Por encima de la mayor potencia de la tabla: unidades de esa potencia en paralelo
   (usuario, 2026-10-16, en PA217: las fórmulas de la NTP no valen tan lejos, la de
   pérdidas con carga decrece desde unos 1600 kVA; RF-7).
6. Tras implementar, la calibración tiene que salir válida: si la sobrecarga era lo que
   impedía converger o validar, no tiene por qué fallar (usuario, 2026-10-16). Si falla,
   es un fallo con su diagnóstico, no un resultado aceptado, y los transformadores nuevos
   se quedan (RF-26, RF-32). En PA217 salió válida a −0,34 % (015, T26).

## Dudas abiertas

Ninguna.
