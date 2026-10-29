# Spec 014 — Calibración y cambios del operador en «Sin proyecto», cargas nuevas en «Con proyecto»

Estado: cumplida (revisión 033 del 2026-10-29) · aprobada (2026-10-14) · Fecha: 2026-10-14 · Origen: aceptación de CA101 del 2026-10-14

## Contexto y objetivo

La spec 011 (2026-10-11) llevaba la calibración a «Sin proyecto» y «Con proyecto»
activando en ellos la variación del último ajuste y desactivando las de ajustes
anteriores (011:RF-7, RF-50). En CA101 eso apagó cambios deliberados del operador. El
14/10 a las 08:34 el ajuste `_2` daba TR_SE20701 al 499 %, TR_SE20859 al 434 % y
TR_SE21082 al 214 %. El operador cambió a mano el tipo de cuatro transformadores
(200→250, 800→2000, 50→520 y 100→250 kVA), y esos cambios quedaron grabados en
`Ajuste_CA101_20261013_203247_3`, la variación que grababa en ese momento. Los ajustes
siguientes (`_4` a `_6`) desactivaron `_3`, en su caso y en «Con proyecto». El modelo
calculó entonces la cabecera, las pérdidas y los estudios sin esos transformadores. Solo
un aviso lo decía: «Ajustes anteriores desactivados».

El usuario fija el trabajo el 2026-10-14. Un caso de estudio no es una variación:

- **«Caso base»**: la red tal como vino (011:RF-3, sin cambios).
- **«Sin proyecto»**: el caso donde se calibra (ajuste a la máxima, spec 006) y donde el
  operador hace sus cambios manuales: elementos, tipos y otros. Si un cambio manual y la
  calibración chocan, **gana el cambio manual**.
- **«Con proyecto»**: copia de «Sin proyecto». En él se crean las cargas nuevas, una o en
  bloque desde la web, cada una en su variación (spec 007).
- Lo demás son resultados de simulación.

Las modificaciones manuales del modelo nativo son deliberadas: se informan como aviso y
nunca bloquean (vínculo del proyecto, `PROJECT_BINDING_NATIVE_MODIFIED`).

Además, la comprobación «la carga nueva ya existe» (004:RF-15) solo mira la red activa.
Una carga creada antes y guardada en una variación inactiva, o activa solo en
«Con proyecto», no se ve desde otro caso. Volver a lanzar la inserción la crearía otra vez.

Definiciones para esta spec:

- **Variación de carga nueva**: la que crea la spec 007 para una carga nueva.
- **Variación del operador**: cualquier otra variación. Entra aquí una variación de ajuste
  que contenga objetos distintos de las cargas existentes del alimentador ajustado, como
  `_3` de CA101 con sus cuatro transformadores.
- **Cambio manual de demanda**: una carga existente cuya demanda en el escenario de
  «Sin proyecto» difiere de la que grabó allí el último ajuste.

## Usuarios / actores

- Ingeniero de planificación que, desde la web, calibra, modifica la red y estudia
  cargas nuevas sobre un proyecto de DIgSILENT existente.
- DIgSILENT PowerFactory 2024, por su API de Python.

## Historias de usuario

- H1: Como ingeniero quiero calibrar en «Sin proyecto» respetando mis cambios manuales,
  para que la red calibrada sea la que yo modifiqué.
- H2: Como ingeniero quiero que mis cambios manuales sigan activos después de cualquier
  acción de la aplicación, para que los resultados los incluyan.
- H3: Como ingeniero quiero que volver a lanzar la inserción de cargas nuevas no las
  duplique, para poder repetirla sin limpiar el proyecto.

## Requisitos funcionales (EARS)

Calibración en «Sin proyecto»

- RF-1: MIENTRAS existan los tres casos de la spec 011, EL SISTEMA hará el ajuste a la
  máxima en «Sin proyecto».
- RF-2: EL SISTEMA no hará un ajuste a la máxima en «Caso base» ni en «Con proyecto».
- RF-3: CUANDO ajusta, EL SISTEMA no desactivará ni borrará ninguna variación del operador.
- RF-4: CUANDO termina un ajuste, EL SISTEMA grabará la demanda calibrada de las cargas
  existentes en el escenario de operación de «Sin proyecto» y en el de «Con proyecto».
- RF-5: SI los tres casos no existen todavía, ENTONCES EL SISTEMA los preparará (spec 011)
  antes de ajustar y ajustará en «Sin proyecto».
- RF-6: ANTES de ajustar, EL SISTEMA separará las cargas nuevas de las cargas existentes
  del alimentador.
- RF-7: MIENTRAS ajusta, EL SISTEMA dejará fuera de servicio las cargas nuevas en el
  escenario de operación del caso en que mide, para que no entren en la máxima medida.
- RF-8: CUANDO termina el ajuste, o se cancela, EL SISTEMA devolverá a cada carga nueva,
  en cada escenario, el estado de servicio que tenía antes.
- RF-9: EL SISTEMA no cambiará la demanda de una carga nueva al grabar la calibración en
  un escenario.

Gana lo manual

- RF-10: SI una carga existente tiene un cambio manual de demanda, ENTONCES EL SISTEMA la
  tratará en el ajuste como fija, con su demanda manual.
- RF-11: EL SISTEMA no sobrescribirá en ningún escenario la demanda de una carga con
  cambio manual de demanda.
- RF-12: CUANDO hay cargas con cambio manual de demanda, EL SISTEMA las listará en un aviso
  con la demanda manual y la que grabó el último ajuste.
- RF-13: SI el alimentador no tiene ningún ajuste anterior, ENTONCES EL SISTEMA no buscará
  cambios manuales de demanda y repartirá como dice la spec 006.
- RF-14: CUANDO ajusta, EL SISTEMA medirá la cabecera con las variaciones del operador que
  estén activas en «Sin proyecto».

«Sin proyecto» y «Caso base»

- RF-15: EL SISTEMA no activará, desactivará ni borrará en «Sin proyecto» ninguna
  variación del operador.
- RF-16: EL SISTEMA dejará desactivadas en «Caso base» y en «Sin proyecto» las variaciones
  de carga nueva.
- RF-17: SI el proyecto tiene modificaciones manuales posteriores a su aceptación,
  ENTONCES EL SISTEMA las listará en un aviso y no bloqueará ninguna acción por ellas.

«Con proyecto»: cargas nuevas

- RF-18: CUANDO crea «Con proyecto», EL SISTEMA lo creará como copia de «Sin proyecto»,
  con sus variaciones activas y una copia de su escenario de operación.
- RF-19: EL SISTEMA creará las cargas nuevas, una o en bloque, solo en «Con proyecto».
- RF-20: EL SISTEMA no desactivará ni borrará en «Con proyecto» ninguna variación del
  operador.
- RF-21: ANTES de insertar cargas nuevas o de estudiar «Con proyecto», EL SISTEMA activará
  en «Con proyecto» las variaciones del operador que estén activas en «Sin proyecto».
- RF-22: CUANDO activa en «Con proyecto» una variación por RF-21, EL SISTEMA lo dirá en el
  informe con su nombre.

Inserción sin duplicados

- RF-23: ANTES de crear una carga nueva, EL SISTEMA la buscará en todas las variaciones del
  proyecto, activas o no, y en la red de «Con proyecto».
- RF-24: SI la carga ya está en una variación de carga nueva, ENTONCES EL SISTEMA no la
  creará otra vez, dejará esa variación activa en «Con proyecto» e informará su nombre.
- RF-25: SI la carga ya está en la red de «Con proyecto» fuera de una variación de carga
  nueva, ENTONCES EL SISTEMA no la creará e informará dónde está.
- RF-26: SI la misma carga está en más de una variación, ENTONCES EL SISTEMA no creará
  ninguna, no cambiará cuáles están activas y las listará en un aviso.
- RF-27: EL SISTEMA reconocerá que una carga ya existe por su nombre en el alimentador,
  el mismo con que se nombra al crearla (004:RF-15, 007:RF-10).
- RF-28: SI una carga ya existente difiere de la fila del libro en potencia o en punto,
  ENTONCES EL SISTEMA no la creará otra vez y avisará de cada diferencia con el valor
  existente y el del libro.
- RF-29: EL SISTEMA reconocerá la carga de RF-27 en una variación también cuando DIgSILENT
  le ha añadido un sufijo «(n)» al guardarla en la etapa, donde la SED, su barra y su carga
  comparten carpeta y nombre (PN107, 2026-10-16: la carga CH_9 estaba guardada como
  «CH_9(2)», no se reconoció, se creó otra en una segunda variación que partía otra vez el
  trozo de la primera y «Con proyecto» no ejecutaba el flujo).
- RF-30: SI una fila del libro no coincide por nombre con ninguna carga nueva ya creada,
  ENTONCES EL SISTEMA la buscará también por su punto: la carga nueva de su alimentador a
  1 m o menos de sus coordenadas es esa misma carga, se trata con RF-24 a RF-26 y el
  motivo dice con qué nombre está (usuario, 2026-10-16: «la comparación podría ser por el
  nombre y el mismo punto de coordenadas»).

Lo hecho a mano en «Sin proyecto» pasa a «Con proyecto» (usuario, 2026-10-16: en PN107 se
creó un banco de condensadores en «Sin proyecto» y no estaba en «Con proyecto»)

- RF-31: ANTES de insertar cargas nuevas, aplicar obras, preparar los casos, estudiar
  «Con proyecto» o ejecutar en él un guion del operador, y DESPUÉS de cada ajuste, EL
  SISTEMA activará en «Con proyecto» las variaciones del operador activas en «Sin
  proyecto» (RF-21) y comparará los datos de operación de los tres casos.
- RF-32: SI un dato de operación (en servicio de bancos, interruptores, transformadores y
  líneas; escalones de un banco; estado de un interruptor; tap de un transformador)
  difiere en «Sin proyecto» del «Caso base» y «Con proyecto» lo tiene como el «Caso
  base», ENTONCES EL SISTEMA lo escribirá en el escenario de «Con proyecto» y lo dirá.
- RF-33: SI «Sin proyecto» y «Con proyecto» cambiaron el mismo dato y lo tienen distinto,
  ENTONCES EL SISTEMA dejará el de «Con proyecto» (una obra) y avisará de cada uno.
- RF-34: SI un elemento está en la red de «Sin proyecto» y no en la de «Con proyecto»
  después de RF-31, ENTONCES EL SISTEMA lo listará en un aviso.

## Requisitos que esta spec cambia

| Requisito | Antes | Ahora |
| --- | --- | --- |
| 011:RF-2 | «Caso base» es el caso en que se calibró | La calibración se hace en «Sin proyecto» (RF-1, RF-5) |
| 011:RF-6 | Al reutilizar los casos, cambia sus variaciones activas | Solo las de carga nueva; las del operador solo se activan en «Con proyecto» (RF-15, RF-20, RF-21) |
| 011:RF-7 | Activa la variación del ajuste en «Sin proyecto» | La calibración está en «Sin proyecto» y no apaga variaciones del operador (RF-3) |
| 011:RF-8 | Activa en «Con proyecto» la base calibrada y las cargas | Hereda «Sin proyecto» y suma las cargas nuevas (RF-18, RF-21, RF-24) |
| 011:RF-50 | Desactiva los ajustes anteriores en «Sin» y «Con» | Nunca una variación del operador (RF-3, RF-20) |
| 006:RF-28 | Graba la demanda del ajuste en los tres escenarios | En «Sin» y «Con», solo en cargas existentes y sin pisar lo manual (RF-4, RF-9, RF-11) |
| 004:RF-15 | «Ya existe» se busca en la red activa | En todas las variaciones y en «Con proyecto» (RF-23) |

## Requisitos no funcionales

- Universal (P13): los nombres de los tres casos son los de la spec 011. Ningún nombre de
  alimentador ni de SED de una empresa como valor fijo.
- Escala: buscar si una carga ya existe recorre las variaciones del proyecto una vez por
  aplicación, no una vez por carga.
- Nada se borra: ninguna acción de esta spec borra variaciones, etapas ni objetos del
  operador.

## Casos límite

- Cambios manuales grabados por el operador dentro de una variación de ajuste (CA101,
  `_3`): es una variación del operador y no se desactiva (RF-3, RF-15).
- Recalibrar cuando «Con proyecto» ya tiene cargas nuevas en servicio (RF-4, RF-7 a RF-9).
- Una carga existente con su demanda cambiada a mano en «Sin proyecto» (RF-10 a RF-12).
- Cancelar a mitad de un ajuste: las cargas nuevas vuelven a su estado (RF-8).
- Una carga nueva que está en una variación inactiva de otra aplicación (RF-24).
- Una carga nueva repetida en dos variaciones (RF-26).
- Inserción cancelada a mitad: las cargas creadas cuentan como existentes al repetir
  (RF-23).
- Proyecto sin los tres casos (RF-5).

## Fuera de alcance

- Reorganizar o borrar las variaciones de proyectos que ya existen (CA101 `_151034` a
  `_6`). Cuáles se activan en cada caso lo decide el operador.
- Desactivar en «Con proyecto» una variación que el operador desactivó en «Sin proyecto»:
  RF-21 solo activa, nunca apaga.
- Los estudios de la spec 012.

## Criterios de finalización

- Cada RF citado por al menos una prueba (`grep -rnoE "014:RF-[0-9]+" tests`).
- Suite en verde con los datos reales (variables `IGEA_*`).
- Prueba en DIgSILENT con CA101: un ajuste en «Sin proyecto» que deje activa `_3` con sus
  cuatro transformadores, y una inserción repetida que no cree cargas duplicadas.

## Dudas resueltas

1. Recalibrar con los casos ya creados (usuario, 2026-10-14): se actualizan los casos.
   Antes se separan las cargas nuevas de las existentes, y las nuevas quedan fuera de
   servicio mientras dura el ajuste (RF-4, RF-6 a RF-9).
2. «Con proyecto» activa también las variaciones del operador que estén activas en
   «Sin proyecto» (RF-21, RF-22).
3. Una carga nueva se reconoce por su nombre en su alimentador; una diferencia de potencia
   o de punto solo se avisa (RF-27, RF-28).
4. Entre la calibración y lo manual gana lo manual. La calibración se hace en «Sin
   proyecto», que es el caso de origen de «Con proyecto» (RF-1, RF-10 a RF-12, RF-18).

## Para el plan

- Cómo se graba el ajuste dentro de «Sin proyecto»: en el escenario de operación o en una
  variación propia que no apague las del operador. No cambia lo observable.
- Cómo se recuerda la demanda que grabó el último ajuste, para detectar el cambio manual
  (RF-10): el informe del ajuste o una marca en DIgSILENT.

## Cambios de la spec 015 (2026-10-14)

- Contexto: el operador corrige el modelo físico en el «Caso base» antes de copiarlo;
  después, sus modificaciones en «Sin proyecto» se graban directamente en la red, sin
  variaciones (015:RF-14, RF-27). Las variaciones del operador de antes de la 015 se
  siguen conservando (RF-3, RF-15, RF-20).
- Aclaración de RF-5: «Sin proyecto» solo se crea con el «Caso base» verificado (015:RF-17).
- Aclaración de RF-10: el cambio manual de demanda se compara con la última calibración que guarda la
  web, porque la calibración ya no deja variación (015:RF-26).
