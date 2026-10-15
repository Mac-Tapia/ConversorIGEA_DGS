# Spec 007 — Cargas nuevas sobre el alimentador ajustado, una variación por carga

Estado: aprobada (2026-10-09), implementada el 2026-10-10 con el cambio RF-36 y RF-37; falta la prueba en DIgSILENT (T11) · Fecha: 2026-10-09 · Origen: uso real con SI213, 2026-10-09 (ajuste de la spec 006 aplicado y libro de cargas nuevas con coordenadas subido)

## Contexto y objetivo

El operador trabaja un alimentador en este orden: busca la máxima de cabecera, cruza los
clientes importantes, ajusta las demandas a la máxima (spec 006, que deja una variación
`Ajuste_<alimentador>_<fecha>`) y, sobre esa red ya calibrada, conecta las cargas
nuevas y actualiza demandas (spec 004). Hoy los dos pasos no se conocen:

- La pestaña de cargas no parte del alimentador ajustado: hay que volver a elegir el
  proyecto y los alimentadores, y nada dice si la variación del ajuste sigue activa, es
  decir, si las cargas nuevas se suman a la red calibrada o a la de antes.
- En la pantalla, el ajuste está debajo de las cargas nuevas: al revés del trabajo.
- Las cargas nuevas de un libro van todas en una sola variación (spec 004, «una
  variación nueva por aplicación, para todo»). El usuario pide el 2026-10-09 que cada
  carga, venga sola o de un libro, tenga su propia variación, para estudiarla por
  separado.

Al conectar una carga nueva la máxima de la cabecera ya no es la medida: la red no se
vuelve a ajustar después.

En el lenguaje de la evaluación (usuario, 2026-10-09): la base ajustada es el estado
**sin proyecto** y cada variación de carga, sobre ella, es el estado **con proyecto**
de esa carga. Lo que se informa de una carga es la diferencia entre los dos.

Esta spec cambia la regla de la spec 004 «una variación nueva por aplicación, para todo»
para las cargas nuevas.

## Usuarios / actores

- Ingeniero de planificación que, desde la web, estudia el efecto de cargas nuevas sobre
  un alimentador ya ajustado a su máxima de cabecera.
- DIgSILENT PowerFactory 2024, por su API de Python, en el carril `powerfactory`.

## Historias de usuario

- H1: Como ingeniero quiero que las cargas nuevas se conecten sobre la red ajustada a la
  máxima, para estudiarlas en el punto real de máxima demanda.
- H2: Como ingeniero quiero una variación por carga nueva, para activar, comparar o
  borrar cada una sin tocar las demás.
- H3: Como ingeniero quiero seguir del ajuste a las cargas sin volver a elegir el
  proyecto ni el alimentador, para no equivocarme de red.

## Requisitos funcionales (EARS)

Continuidad desde el ajuste

- RF-1: CUANDO un ajuste a la máxima termina aplicado, EL SISTEMA propondrá para las
  cargas el mismo proyecto y el mismo alimentador, con la variación del ajuste como base.
- RF-2: MIENTRAS haya una base propuesta, EL SISTEMA mostrará junto a las cargas el
  nombre de la variación base, la máxima de cabecera a la que se ajustó y si cuadró.
- RF-3: EL SISTEMA presentará los pasos en el orden del trabajo: proyecto, alimentador,
  máxima y clientes importantes, ajuste, y por último cargas nuevas y demandas.
- RF-4: EL SISTEMA permitirá quitar la base propuesta y trabajar sobre la red tal como
  esté activa en el proyecto.
- RF-5: SI no hay ajuste previo o se quitó la base, ENTONCES EL SISTEMA aplicará sobre las
  variaciones que estén activas en el proyecto y lo dirá en el plan y en el informe.

Base en DIgSILENT

- RF-6: CUANDO se aplican cargas sobre una base, EL SISTEMA activará la variación base
  antes de crear ninguna variación nueva.
- RF-34: SI el ajuste de la base no cuadró, ENTONCES EL SISTEMA la aceptará como base y
  lo avisará en el plan y en el informe con su error en la cabecera.
- RF-7: SI la variación base ya no existe en el proyecto, ENTONCES EL SISTEMA no aplicará
  nada y lo dirá con su nombre.
- RF-8: EL SISTEMA listará en el informe las variaciones que estaban activas al empezar y
  las que quedan activas al terminar.

Una variación por carga nueva

- RF-9: CUANDO se aplican cargas nuevas, EL SISTEMA creará una variación nueva por cada
  carga, venga del libro o del formulario.
- RF-10: EL SISTEMA nombrará cada variación con la SED de la carga y el alimentador, sin
  repetir el nombre de una variación existente.
- RF-11: EL SISTEMA grabará en la variación de una carga solo los objetos de esa carga:
  su barra, su transformador, su carga y su línea de enlace si la hay.
- RF-12: MIENTRAS se conecta una carga, EL SISTEMA tendrá activas la base y la variación
  de esa carga, y ninguna variación de otra carga del mismo libro.
- RF-13: CUANDO una carga queda conectada, EL SISTEMA ejecutará el flujo de carga con la
  base y esa carga (con proyecto) e informará si converge, las tensiones extremas y lo
  que entra por la cabecera.
- RF-32: EL SISTEMA ejecutará el flujo de carga de la base sola (sin proyecto) una vez
  por aplicación, antes de la primera carga, y lo dará en el informe como referencia.
- RF-33: EL SISTEMA informará por carga la diferencia entre con proyecto y sin proyecto
  en el kW y el kVAR de la cabecera, en sus pérdidas y en la tensión mínima.
- RF-14: EL SISTEMA no volverá a ajustar las demandas a la máxima tras conectar una carga.
- RF-15: SI una carga no se puede conectar (spec 004: sin barra ni coordenadas, barra no
  hallada, alimentador no elegido), ENTONCES EL SISTEMA no creará su variación, la listará
  con el motivo y seguirá con la siguiente.
- RF-16: SI el operador cancela, ENTONCES EL SISTEMA terminará la carga en curso, no
  empezará otra y conservará las variaciones ya creadas.
- RF-17: CUANDO terminan todas las cargas, o se cancela, EL SISTEMA dejará activa la base
  y ninguna variación de las cargas, para que ninguna se sume a otra sin que el operador
  la active.

Simulación

- RF-18: CUANDO se simula, EL SISTEMA dirá por carga la barra, el criterio de conexión y
  el nombre de la variación que crearía, sin escribir en el proyecto.

Demandas en bloque

- RF-19: CUANDO se aplican demandas en bloque, EL SISTEMA las grabará en una variación
  propia, distinta de las de las cargas nuevas.
- RF-35: CUANDO en una misma aplicación hay demandas en bloque y cargas nuevas, EL
  SISTEMA aplicará primero las demandas, y su variación formará parte del estado sin
  proyecto de cada carga.
- RF-20: CUANDO el libro de demandas trae una SED que el ajuste calibró, EL SISTEMA
  escribirá el valor del libro en la variación de las demandas.
- RF-21: EL SISTEMA listará en el plan y en el informe las SED calibradas por el ajuste
  que el libro de demandas cambia, con su demanda antes y después.

Evaluación técnico-económica

- RF-22: DONDE el operador pide la evaluación técnico-económica, EL SISTEMA la hará por
  cada carga conectada, con la base y la variación de esa carga activas.
- RF-23: EL SISTEMA dará en el informe el resultado de la evaluación de cada carga por
  separado, con la SED de la carga.

Conexión de cada carga al alimentador activo

El libro de cargas nuevas trae el punto de cada carga en coordenadas (usuario,
2026-10-09): la carga va al nudo más cercano del alimentador que se está trabajando, no
al más cercano de todo el proyecto. Las cargas del libro ya están revisadas, validadas y
aprobadas para conectarse a ese alimentador: el sistema no las vuelve a juzgar. El alimentador activo es el de la base o, sin base,
el que el operador elige.

- RF-24: CUANDO una carga trae coordenadas y no trae barra, EL SISTEMA la conectará a la
  barra del alimentador activo más cercana a su punto, entre las que tienen coordenadas
  en DIgSILENT.
  **Cambiado por 016:RF-45 (2026-10-15):** la carga va al punto más cercano de la troncal del alimentador activo, partiendo el tramo en su variación; ya no a la barra más cercana.
- RF-25: EL SISTEMA no buscará la barra más cercana en otros alimentadores del proyecto
  que el activo.
- RF-26: DONDE la carga trae una barra, EL SISTEMA la conectará a esa barra, como
  alternativa a las coordenadas.
- RF-27: SI la barra indicada no está en el alimentador activo, ENTONCES EL SISTEMA no
  conectará la carga y lo dirá con el nombre de la barra.
- RF-28: SI ninguna barra del alimentador activo tiene coordenadas en DIgSILENT,
  ENTONCES EL SISTEMA no conectará por coordenadas ninguna carga y lo dirá una vez,
  con el alimentador.
  **Cambiado por 016:RF-50 (2026-10-15):** cuenta que ningún tramo de la troncal tenga coordenadas.
- RF-29: SI la carga trae un alimentador (TRONCAL) que no es ninguno de los marcados,
  ENTONCES EL SISTEMA no la creará, la dará como no creada con su alimentador y dirá una
  vez cuántas del libro son de alimentadores no marcados. (Cambio del 2026-10-13: antes
  se conectaba al activo; el libro de planificación trae las cargas de todos los
  alimentadores y con SI213 marcado se crearon 28, 27 de otros, una a 216 km.)
- RF-30: EL SISTEMA mostrará en el plan, por carga, el punto del libro, y en la
  simulación la barra elegida y su distancia en metros al punto.
  **Cambiado por 016:RF-49 (2026-10-15):** la simulación dice además el tramo, si se parte y la distancia al punto de conexión.
- RF-31: EL SISTEMA conectará la carga a su barra más cercana cualquiera que sea la
  distancia, sin umbral que avise ni que la rechace: la distancia solo se informa.
  **Cambiado por 016:RF-45 y RF-20 (2026-10-15):** el punto es el de la troncal; a menos de la distancia mínima de una barra, se engancha en ella.

Cambio del 2026-10-10: varios alimentadores (spec 008)

La spec 008 ajusta en un trabajo todos los alimentadores marcados, cada uno en su
variación, y los mismos marcados se usan para integrar. La base son entonces las
variaciones del ajuste, una por alimentador, y «el alimentador activo» de RF-24 a RF-29
es, para cada carga, uno de los marcados:

- RF-36: MIENTRAS haya varios alimentadores marcados, EL SISTEMA tomará como alimentador
  activo de una carga el de su columna si está entre los marcados (si no lo está, RF-29)
  y, si la columna viene vacía, el de la barra más cercana a su punto entre todos los
  marcados.
- RF-37: CUANDO la base viene de un ajuste de varios alimentadores, EL SISTEMA activará
  la variación de cada alimentador ajustado y dejará fuera de la base los que fallaron,
  y lo dirá en el plan.

Cambio del 2026-10-13: deshacer una aplicación

- RF-38: CUANDO el operador pide deshacer una aplicación con su informe, EL SISTEMA
  borrará las variaciones de las cargas nuevas que dice el informe, los símbolos que
  dibujó en el diagrama y los tipos de transformador que creó y que ya no usa ningún
  transformador del proyecto; con `--simular`, solo lo listará.
- RF-39: SI ninguna línea llega a la barra elegida y la fila no da un tipo de línea del
  proyecto, ENTONCES EL SISTEMA tomará para la línea de enlace el tipo más usado de las
  líneas del alimentador a la tensión de la barra y lo dirá en el informe. (SI213,
  2026-10-13: la barra más cercana era el nodo de una SED, solo con su seccionador.)
- RF-40: CUANDO no hay en la sesión ningún ajuste aplicado del proyecto (p. ej. tras
  reiniciar la web, o en otro espacio que usó la fuente del vínculo, 018:RF-10), EL SISTEMA
  tomará como base el último ajuste aplicado guardado en disco, con los informes por
  alimentador de esa aplicación. (CA101, 2026-10-15: la calibración seguía en «Sin
  proyecto» y la web pedía volver a calibrar para estudiar.)

## Casos límite

- Libro con otro alimentador en su columna: no se crea y se dice (RF-29). Si ninguna
  fila es de un alimentador marcado, no se crea ninguna carga nueva.
- Punto lejos del alimentador activo: se conecta a su barra más cercana y se informa
  la distancia (RF-31).
- Coordenadas del libro en otro sistema de referencia que las barras de DIgSILENT: se
  convierten con el CRS del perfil de empresa, como en la spec 004.
- Dos filas del libro con la misma SED: la segunda no se crea (spec 004, RF-15).
- Un libro de muchas cargas: tantas variaciones como cargas conectadas, sin tope fijo.
- La variación base desactivada o borrada a mano en DIgSILENT entre el ajuste y las
  cargas (RF-7).
- Un escenario de operación activo: se desactiva y se restaura como hoy (spec 004).

## Fuera de alcance

- Volver a ajustar a la máxima después de conectar cargas.
- Combinar varias cargas en una variación o estudiar combinaciones de cargas.
- Borrar o renombrar variaciones ya creadas.
- Otros criterios de conexión que la barra indicada o la más cercana por coordenadas
  (por ejemplo, la más cercana por tensión o por capacidad).
- Cambios en el ajuste a la máxima (spec 006).

## Criterios de finalización

- `grep -rnoE "007:RF-[0-9]+" tests | sort -u` lista todos los RF.
- Suite completa en verde, también las pruebas de las specs 004 y 006.
- `npx tsc --noEmit -p .` (en `frontend/`) y `npm run build` correctos.
- Prueba real en DIgSILENT con SI213, a cargo del usuario.

## Dudas resueltas (2026-10-09)

- Agrupación: una variación por carga nueva, venga sola o de un libro (usuario).
- Tras conectar una carga, la máxima ya no es la medida: no se recalibra (usuario).
- Las demandas en bloque van en su propia variación (usuario: «cada una con su variación»).
- Al terminar queda activa solo la base (usuario).
- El libro de demandas manda sobre una SED calibrada, y se informa (usuario).
- La evaluación técnico-económica, una por carga (usuario).
- Conexión: por las coordenadas del libro a la barra más cercana del alimentador activo;
  la barra indicada queda como alternativa (usuario).
- Las cargas del libro vienen aprobadas para el alimentador: se conectan siempre, sin
  umbral de distancia (usuario).
- La base es el estado sin proyecto; base + carga, el estado con proyecto (usuario).
- Un ajuste que no cuadró sirve de base, con aviso; las demandas del mismo envío entran
  en el estado sin proyecto (propuesta del 2026-10-09, sin objeción).

## Cambios de la spec 014 (2026-10-14)

- Las cargas nuevas se crean solo en «Con proyecto», copia de «Sin proyecto» con sus
  variaciones activas y su escenario (014:RF-18, RF-19); antes de insertarlas se activan
  en «Con proyecto» las variaciones del operador activas en «Sin proyecto» (014:RF-21).
- RF-10: el nombre de la variación (SED y alimentador) es también la clave con que se
  reconoce una carga ya creada; repetir la inserción no la duplica (014:RF-23 a RF-28).
