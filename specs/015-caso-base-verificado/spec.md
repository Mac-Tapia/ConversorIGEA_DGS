# Spec 015 — «Caso base» verificado de una vez; «Sin proyecto» solo calibra cargas

Estado: aprobada (2026-10-14) · Fecha: 2026-10-14 · Origen: revisión de la aceptación de CA101 del 2026-10-14

## Contexto y objetivo

La aceptación de CA101 del 2026-10-13 adoptó el proyecto existente sin comprobar la red:
0 de 0 barras con GPS comparado, 0 de 0 líneas con conectividad comprobada, sin diagrama,
y el flujo de carga sin converger. El vínculo quedó como
`IDENTIDAD_VERIFICADA_PENDIENTE_CONVERGENCIA`, y fue el ajuste a la máxima en
«Sin proyecto» el que lo promovió a `VERIFICADO_PERSISTENCIA`, con la relectura de los
bancos incluida. La calibración hacía así de última parte de la aceptación del modelo
físico. Para que convergiera, el operador corrigió el tipo de cuatro transformadores
grabando en una variación del ajuste (spec 014).

El usuario fija el reparto el 2026-10-14:

- **«Caso base»**: el modelo físico completo y correcto en DIgSILENT. Se verifica una
  vez y entero: georreferencia frente al archivo original, capacidades, grupo de
  conexión y tensión de baja de los transformadores de SED, conectividad, diagrama y
  convergencia. Si algo falla, el operador lo corrige aquí, en DIgSILENT, y se
  vuelve a verificar. Una vez copiado a «Sin proyecto», no se vuelve a tocar.
- **«Sin proyecto»**: un caso distinto, con su propio escenario de operación. La
  aplicación solo calibra en él las cargas (SED fijas por sus clientes importantes y el
  resto escaladas) y no vuelve a comprobar topología, elementos ni capacidades. Las
  modificaciones manuales del operador se hacen aquí y se graban directamente en la red,
  sin crear variaciones.
- **«Con proyecto»**: copia de «Sin proyecto» con su propio escenario de operación, creada
  antes de insertar cargas nuevas. Cada inserción, de una carga o en bloque, crea sus
  variaciones, una por carga (specs 007 y 014).

En DIgSILENT un caso copiado solo es independiente en los datos de operación, que guarda
su escenario: demanda, estado de interruptores y líneas, despacho (manual de PowerFactory
2024, cap. 15). Elementos, tipos y conexiones son de la red, que comparten todos los
casos. Por decisión del usuario, una modificación física hecha en «Sin proyecto» se graba
en esa red sin variación, y por eso también se ve desde el «Caso base».

El orden es fijo: (1) verificar el «Caso base» y corregirlo hasta que pase y converja;
(2) solo entonces se copia a «Sin proyecto», y el «Caso base» queda cerrado; (3) en
«Sin proyecto» la aplicación calibra la demanda y el operador hace sus modificaciones.

## Usuarios / actores

- Ingeniero de planificación que, desde la web, acepta un proyecto de DIgSILENT y lo calibra.
- DIgSILENT PowerFactory 2024, por su API de Python.

## Historias de usuario

- H1: Como ingeniero quiero saber al aceptar el «Caso base» si el modelo físico es
  correcto y completo, para corregirlo antes de calibrar.
- H2: Como ingeniero quiero que la calibración solo toque la demanda, para que su
  resultado dependa de las máximas y de los clientes, y no de revisiones de la red.

## Requisitos funcionales (EARS)

Verificación del «Caso base»

- RF-1: CUANDO se acepta un proyecto, nuevo o existente, EL SISTEMA verificará el
  «Caso base» con todas las comprobaciones de RF-2 a RF-8, RF-32 y RF-33.
- RF-2: EL SISTEMA comparará la posición GPS de cada barra con la del archivo original.
- RF-3: EL SISTEMA comparará el trazado GPS de cada línea con el del archivo original
  (spec 010).
- RF-4: EL SISTEMA comprobará que cada línea y cada carga están conectadas a sus barras.
- RF-5: EL SISTEMA comprobará que el diagrama geográfico existe.
- RF-6: EL SISTEMA comprobará que cada transformador, línea y banco de condensadores tiene
  definida su capacidad: potencia nominal, corriente nominal y potencia por paso.
- RF-7: EL SISTEMA comparará la capacidad de cada transformador, línea y banco de
  condensadores con la del archivo original.
- RF-8: CUANDO importa el DGS, EL SISTEMA ejecutará el flujo de carga del «Caso base» con
  las cargas del archivo original (MDB, TXT o VNR-GIS) y comprobará que converge.
- RF-9: CUANDO termina la verificación, EL SISTEMA informará por alimentador el resultado
  de cada comprobación de RF-2 a RF-8, RF-32 y RF-33, con los elementos que fallan.

Qué bloquea y qué se avisa

- RF-10: SI falla una comprobación de RF-2 a RF-6, ENTONCES EL SISTEMA no dará el
  «Caso base» de ese alimentador por verificado. El flujo (RF-8) no bloquea (RF-38 a RF-40).
- RF-11: SI una capacidad difiere de la del archivo original (RF-7), ENTONCES EL SISTEMA
  lo avisará con el valor de DIgSILENT y el del archivo, y no bloqueará: es una
  corrección del operador.
- RF-12: SI el archivo original no trae coordenadas de un elemento, ENTONCES EL SISTEMA no
  comparará su GPS y lo listará en un aviso.
- RF-13: MIENTRAS el «Caso base» de un alimentador no esté verificado, EL SISTEMA no
  calibrará ese alimentador y dirá qué comprobación falla.
- RF-14: MIENTRAS «Sin proyecto» no exista, CUANDO el operador corrige el «Caso base» en
  DIgSILENT, EL SISTEMA permitirá volver a verificarlo sin reconvertir ni volver a
  importar.
- RF-15: SI en un lote de varios alimentadores uno no está verificado, ENTONCES EL SISTEMA
  calibrará los demás e informará del que no se calibró (como 008:RF-14).

«Sin proyecto»: copia del «Caso base» verificado

- RF-16: EL SISTEMA creará «Sin proyecto» como copia del «Caso base» solo después de que
  el «Caso base» esté verificado.
- RF-17: SI el «Caso base» no está verificado, ENTONCES EL SISTEMA no creará «Sin proyecto»
  ni «Con proyecto» y dirá qué comprobación falla.
- RF-18: CUANDO crea «Sin proyecto», EL SISTEMA lo creará con una copia del escenario de
  operación del «Caso base».
- RF-19: MIENTRAS «Sin proyecto» exista, EL SISTEMA no escribirá nada en el «Caso base» ni
  en su escenario de operación, salvo la marca fija o escalable de RF-37.

«Sin proyecto»: solo cargas

- RF-20: CUANDO calibra en «Sin proyecto», EL SISTEMA solo cambiará la demanda, el factor
  de escala y el estado de servicio de las cargas del alimentador.
- RF-21: CUANDO calibra, EL SISTEMA no comprobará georreferencia, conectividad, diagrama,
  capacidades ni el inventario de elementos de la red.
- RF-22: EL SISTEMA no cambiará el estado de verificación del «Caso base» por el resultado
  de una calibración.
- RF-23: EL SISTEMA tomará la potencia de cada SED para escalar de los transformadores del
  modelo, ya verificados en el «Caso base».
- RF-24: SI el flujo de la calibración no converge, ENTONCES EL SISTEMA lo informará con el
  diagnóstico de la spec 006 sin dar por no verificado el «Caso base».
- RF-25: EL SISTEMA no tratará como fallo un cambio manual del operador en la red de
  «Sin proyecto»: lo avisa (014:RF-17) y calibra igual.

Modificaciones manuales y variaciones

- RF-26: EL SISTEMA grabará la calibración en el escenario de operación de «Sin proyecto»,
  sin crear una variación de ajuste.
- RF-27: EL SISTEMA no creará ni dejará grabando ninguna variación en «Sin proyecto», para
  que las modificaciones manuales del operador se graben directamente en la red.
- RF-28: ANTES de insertar cargas nuevas, EL SISTEMA tendrá creado «Con proyecto» como
  copia de «Sin proyecto», con su propio escenario de operación (014:RF-18).
- RF-29: CUANDO inserta cargas nuevas, una o en bloque, EL SISTEMA creará en «Con
  proyecto» una variación por cada carga nueva (spec 007), y en ningún otro caso.
- RF-30: SI la red física cambia después de verificar el «Caso base», también por una
  modificación hecha desde «Sin proyecto», ENTONCES EL SISTEMA listará lo cambiado en un
  aviso, sin deshacerlo ni bloquear.
- RF-31: SI el «Caso base» tiene activa alguna variación, ENTONCES EL SISTEMA la nombrará
  en un aviso, sin desactivarla ni borrarla.

Transformadores de SED

- RF-32: EL SISTEMA comprobará que el grupo de conexión de cada transformador de SED es
  el del archivo original.
- RF-33: EL SISTEMA comprobará que la tensión nominal de baja de cada transformador de SED
  es la del archivo original (en las entregas de 2026, 220 V o 380 V).
- RF-34: SI el grupo de conexión o la tensión de baja de un transformador de SED falta o
  difiere del archivo original, ENTONCES EL SISTEMA lo corregirá en el «Caso base» con el
  valor del archivo original, antes del flujo de RF-8, y no bloqueará por ello.
- RF-35: CUANDO corrige un transformador por RF-34, EL SISTEMA lo informará con el valor
  que tenía y el que deja.
- RF-36: SI un transformador de SED que hay que corregir comparte su tipo con otros que no
  lo necesitan, ENTONCES EL SISTEMA corregirá solo ese transformador, sin cambiar a los
  demás.

Marca fija o escalable

- RF-37: CUANDO calibra, EL SISTEMA escribirá en cada carga del alimentador la marca fija
  o escalable (006:RF-18), aunque DIgSILENT la guarde en la red que comparten los casos y
  el «Caso base» la vea también.

Convergencia del «Caso base»

- RF-38: SI el flujo del «Caso base» no converge, ENTONCES EL SISTEMA reducirá por igual la
  demanda de sus cargas hasta el mayor factor con el que converge, la grabará en su
  escenario de operación y lo informará con el factor, sin bloquear.
- RF-39: CUANDO verifica un proyecto ya importado, EL SISTEMA no ejecutará el flujo ni
  modificará cargas: la convergencia se comprueba al importar (RF-8, RF-38). Si además
  «Sin proyecto» ya existe, el «Caso base» no se toca (RF-19).
- RF-40: SI el flujo no converge ni con el menor factor, ENTONCES EL SISTEMA lo avisará con
  el diagnóstico y no bloqueará.
- RF-41: ANTES de importar el DGS, EL SISTEMA comprobará con el oráculo (pandapower) que la
  red del alimentador converge con las cargas del archivo original, e informará el
  resultado con la importación.

Fijas y escaladas con el factor de escala de DIgSILENT

- RF-42: EL SISTEMA tratará las cargas como de potencia constante (PQ): la calibración no
  activará la dependencia de la tensión de las cargas para converger.
- RF-43: CUANDO calibra, EL SISTEMA escribirá en cada SED fija (clientes importantes) su P y
  su Q, y dejará su factor de escala en 1.
- RF-44: CUANDO calibra, EL SISTEMA conservará en cada SED escalada la P y la Q del archivo
  original y cambiará solo su factor de escala (``scale0``), el mismo en todas, hasta
  cuadrar la cabecera con la máxima.
- RF-45: SI una SED escalada no tiene demanda en el archivo original, ENTONCES EL SISTEMA la
  dejará en cero y la listará en un aviso.
- RF-46: SI la calibración en «Sin proyecto» cuadra con ajustes del flujo de carga (los
  remedios de la spec 006), ENTONCES EL SISTEMA los dejará en el flujo de «Sin proyecto» y
  en el de «Con proyecto», para que queden convergiendo, y los nombrará en el informe.

## Requisitos que esta spec cambia

| Requisito | Antes | Ahora |
| --- | --- | --- |
| 011:RF-3 | «Caso base» es la red tal como vino | Es la red física verificada, con las correcciones del operador hechas antes de la copia; después no se toca (RF-1, RF-14, RF-19) |
| 014, contexto | El operador hace sus cambios en «Sin proyecto», grabados en la variación que estuviera grabando | Las correcciones para aceptar el modelo van al «Caso base» antes de la copia; después, en «Sin proyecto», directas en la red y sin variaciones (RF-14, RF-27) |
| Aceptación de un proyecto existente | Solo el flujo; sin GPS, conectividad ni diagrama; se vincula pendiente de convergencia | Todas las comprobaciones de RF-2 a RF-8 (RF-1, RF-10) |
| Vínculo tras el ajuste | El ajuste promueve el vínculo a verificado | El vínculo solo lo verifica la aceptación del «Caso base» (RF-22) |
| 006:RF-10, RF-24 | Las SED repartidas reciben P y Q proporcionales a su kVA; sin kVA no se ajusta | Conservan su P y Q del archivo y escalan con el factor de escala de DIgSILENT; el kVA no hace falta (RF-44) |
| 006:RF-16 | Un remedio activa las cargas dependientes de la tensión; al terminar se restituyen todos | Las cargas son PQ: ese ajuste no se usa (RF-42); en «Sin» y «Con proyecto», casos del sistema, se conservan si la calibración cuadra (RF-46) |
| 014:RF-5 | Si faltan los tres casos, el ajuste los prepara desde el caso activo | Solo se preparan desde un «Caso base» verificado; si no lo está, no se calibra (RF-16, RF-17) |
| 006:RF-19 | El ajuste graba las demandas en una variación nueva, y también en el escenario | En el escenario de operación de «Sin proyecto», sin variación de ajuste (RF-26) |
| 011:RF-7 | «Sin proyecto» activa la variación del ajuste | No hay variación del ajuste: la calibración está en su escenario (RF-26) |

## Requisitos no funcionales

- Universal (P13): las comprobaciones comparan con el archivo original de cualquier fuente
  (TXT, MDB, VNR-GIS); ningún nombre de alimentador, SED ni CRS de una empresa como valor
  fijo.
- Escala: la verificación recorre cada alimentador una vez; ninguna comprobación recorre la
  red entera por alimentador.
- Nada se borra ni se corrige solo: la verificación lee y compara, salvo el grupo de
  conexión y la tensión de baja de los transformadores de SED, que corrige (RF-34).

## Casos límite

- Proyecto existente adoptado sin manifiesto de geografía (CA101 del 2026-10-13): no se
  puede verificar el GPS y no queda verificado (RF-1, RF-10).
- Transformador con su tipo cambiado a mano en el «Caso base»: aviso, no bloqueo (RF-11).
- Fuente sin coordenadas en parte de la red (RF-12).
- Un transformador de 380 V importado con un tipo de 220 V, o con otro grupo de conexión:
  se corrige con el valor del archivo original y se informa; no bloquea (RF-34, RF-35).
- Un tipo de transformador compartido por SED de 220 V y de 380 V: se corrigen solo las
  que lo necesitan (RF-36).
- El «Caso base» converge pero la calibración no (RF-24).
- CA101 (2026-10-14): su «Caso base» no convergía con las cargas del archivo. Al importar
  se reduce la demanda hasta que converja (RF-38); al verificar el proyecto ya importado no
  se corre el flujo (RF-39), y «Sin proyecto» calibra con su propio escenario.
- Lote con un alimentador sin verificar (RF-15).
- Calibrar sin que existan los casos y con el «Caso base» sin verificar: no se crea
  «Sin proyecto» ni se calibra (RF-17).
- El operador cambia el «Caso base» después de crear «Sin proyecto»: aviso con lo
  cambiado (RF-30).
- El operador cambia el tipo de un transformador en «Sin proyecto»: se graba en la red,
  sin variación; lo ven los tres casos, y se avisa de que la red ya no es la verificada
  (RF-27, RF-30).
- El operador abre un interruptor en «Sin proyecto»: queda en su escenario y el «Caso
  base» no cambia.
- Proyectos de antes de esta spec (CA101, `Ajuste_CA101_20261013_203247_3` con cuatro
  transformadores): sus variaciones no se tocan (014:RF-3); si alguna está activa en el
  «Caso base», se avisa (RF-31).
- Proyecto con el vínculo `IDENTIDAD_VERIFICADA_PENDIENTE_CONVERGENCIA` de antes de esta
  spec: hay que volver a verificarlo (RF-13, RF-14).

## Fuera de alcance

- Corregir el modelo de forma automática: lo corrige el operador en DIgSILENT.
- La verificación de convergencia de la pestaña (008:RF-18), que mide lo que esté activo y
  sigue igual.
- Las cargas nuevas de «Con proyecto» (specs 007 y 014).

## Criterios de finalización

- Cada RF citado por al menos una prueba (`grep -rnoE "015:RF-[0-9]+" tests`).
- Suite en verde con los datos reales (variables `IGEA_*`).
- Prueba en DIgSILENT con CA101: la verificación del «Caso base» lista lo que falla;
  corregido en DIgSILENT, pasa; la calibración en «Sin proyecto» solo cambia cargas.

## Dudas resueltas

1. Si el «Caso base» no converge con las cargas del archivo original, no se bloquea: se
   modifica la carga hasta que converja (usuario, 2026-10-14, que cambió su primera
   respuesta: «nada iba a bloquear el flujo»; RF-38 a RF-40). Bloquean solo las
   comprobaciones físicas de RF-2 a RF-6.
2. Se verifica en el «Caso base» todo lo que antes se comprobaba al calibrar en
   «Sin proyecto» (usuario, 2026-10-14; RF-2 a RF-8, RF-21).
3. El modelo físico se corrige en el «Caso base», en DIgSILENT, antes de la copia
   (usuario, 2026-10-14; RF-14).
4. Orden fijo: el «Caso base» terminado, corregido y convergente; después la copia a
   «Sin proyecto»; después la calibración, solo de la demanda (usuario, 2026-10-14;
   RF-16 a RF-20).
5. Una vez hecha la copia, la aplicación no vuelve a tocar el «Caso base»: son casos
   distintos, con escenarios distintos. Las modificaciones manuales se hacen en
   «Sin proyecto» y se graban directamente en la red, sin crear variaciones; la
   calibración solo cambia cargas (usuario, 2026-10-14; RF-19, RF-26, RF-27). Se le
   explicó que un cambio físico grabado así se ve también desde el «Caso base»
   (manual de PowerFactory 2024, cap. 15), y lo mantuvo.
6. Las variaciones solo nacen en «Con proyecto», creado antes como copia de
   «Sin proyecto» con su escenario: una por carga nueva, en cada inserción, de una carga
   o en bloque (usuario, 2026-10-14; RF-28, RF-29).
7. Tolerancia del GPS: la de la spec 010, 1e-7 grados para barras y líneas (usuario,
   2026-10-14; RF-2, RF-3).
8. Al importar el DGS se verifican el grupo de conexión y la tensión de baja de los
   transformadores de SED; no tienen que ver con las cargas. Si faltan o difieren del
   archivo original no se bloquea: se corrigen, y ningún flujo queda bloqueado por el
   grupo de una SED (usuario, 2026-10-14; RF-32 a RF-36). Los niveles se toman del
   archivo original, no se fijan en el código (P13).
9. La marca fija o escalable no la guarda el escenario (T1). Se escribe igual: el «Caso
   base» conserva su demanda porque en él no se calibra ni se escala nada (usuario,
   2026-10-14; RF-19, RF-37).
10. La convergencia se prueba solo al importar el DGS; antes, el oráculo ya debe converger
    con las cargas del archivo original (MDB, TXT o VNR-GIS) (usuario, 2026-10-14; RF-8,
    RF-39, RF-41).
11. Las cargas son PQ, no dependen de la tensión. Las fijas reciben su P y Q; las escaladas
    conservan las suyas y suben con el factor de escala de DIgSILENT (normalmente 1) hasta
    cuadrar con la máxima (usuario, 2026-10-14; RF-42 a RF-45).
12. «Sin proyecto» tiene que quedar convergiendo: los ajustes del flujo que necesitó la
    calibración se quedan en él y en «Con proyecto» (usuario, 2026-10-14; RF-46).

## Para el plan

- Qué atributos de la carga guarda el escenario de operación (potencia, escala, fuera de
  servicio, `i_scale`). Lo que no guarde, escrito sin variación, cambiaría también el
  «Caso base» y rompería RF-19: el plan tiene que decir qué se hace con él.
- Cómo se distingue en RF-30 un cambio del operador de uno de la propia aplicación.
- El cuadre se mide hoy con el escenario apagado y la variación activa; sin variación,
  se mide con el escenario de «Sin proyecto» activo.
