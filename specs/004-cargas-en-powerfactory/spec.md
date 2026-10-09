# Spec 004 — Cargas en un proyecto existente de DIgSILENT

Estado: aprobada (2026-10-08) · Fecha: 2026-10-08 · Origen: revisión del módulo de cargas del 2026-10-08

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

## Requisitos no funcionales

- Universal (P13): ninguna tensión, frecuencia ni CRS de una empresa como valor fijo.
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

## Fuera de alcance

- Conversión, reconstrucción y catálogo de parámetros de la conversión.
- Plantilla rellenada con las cargas que ya tiene el proyecto: la plantilla es vacía.
- Borrar o mover cargas existentes.
- Cambios en la evaluación técnico-económica (`ComTececo`): se conserva tal cual, ahora
  sobre la variación del lote.

## Criterios de finalización

- `grep -rnoE "004:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-21.
- Suite completa en verde y RF-14 de la spec 001 sin cambios.
- `npx tsc --noEmit -p .` (en `frontend/`) y `npm run build` correctos.
- Prueba real en DIgSILENT, a cargo del usuario.

## Dudas resueltas (2026-10-08)

- Conexión de una carga nueva: la barra indicada o, si no hay, la más cercana por GPS.
- Dónde quedan los cambios: una variación nueva por aplicación, para todo.
- Conductor del enlace: el de la fila si existe en el proyecto o el de la red.
- Una SED sin coincidencia se omite y se informa; no es un error ni deshace nada.
