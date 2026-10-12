# Spec 012 — Confiabilidad y capacidad de la red calibrada

Estado: aprobada (2026-10-11) · Fecha: 2026-10-11 · Origen: petición del usuario, 2026-10-11, tras
revisar el menú «Calculation» de PowerFactory 2024 con el manual de usuario (cap. 40, 41,
45 y 46)

## Contexto y objetivo

La spec 011 deja los estudios sobre los casos «Sin proyecto» y «Con proyecto» de una red
calibrada, y saca de su alcance la fiabilidad y la colocación de condensadores porque no
eran defendibles: `studies.py` registra que las tasas de falla y los tiempos de
reposición del catálogo de equipos llegan **todos a cero** (con ellos, `ComRel3` se
ejecuta y devuelve SAIFI = SAIDI = ENS = 0, un resultado limpio y sin sentido) y que
`ComCapo` no tiene precios con los que comparar el coste de un banco con las pérdidas
que ahorra.

El usuario pide (2026-10-11) cuatro estudios más con los módulos nativos de DIgSILENT,
no con bucles propios de flujos de carga:

- **Confiabilidad** (manual cap. 45, `ComRel3`): SAIFI, SAIDI y ENS por alimentador.
- **Ubicación óptima de reconectadores** (manual §46.5): dónde un reconectador mejora más
  el índice, sobre el mismo cálculo de confiabilidad.
- **Capacidad de alojamiento** (manual §41.2, `ComHostcap`): cuánta generación
  distribuida y cuánta carga nueva admite cada nodo sin violar tensión ni cargabilidad.
- **Curvas PV** (manual §40.2, `ComPvcurves`) y **ubicación óptima de condensadores**
  (manual §41.10, `ComCapo`): el margen hasta el colapso de tensión y dónde compensar.

Lo que faltaba lo aporta la empresa: el usuario decide (2026-10-11) que las tasas de
falla, los tiempos y los costes llegan en **un fichero de la empresa**, sacado de su
histórico de interrupciones, y que sin él estos estudios no se ejecutan. No se rellenan
con valores típicos: un índice de confiabilidad con tasas inventadas no se puede
defender ante el regulador.

Dos hechos del proyecto condicionan lo que se construye:

- El DGS escribe todo equipo de maniobra como interruptor automático (`StaSwitch` con
  `aUsage='cbk'`, `dgs.py`), sea fusible, seccionador o reconectador. La confiabilidad
  decide qué equipo despeja una falla y cuál solo aísla, y la ubicación de reconectadores
  elige entre interruptores: sin distinguir la clase propondría convertir un fusible en
  reconectador. La clase la escribe la spec 011 (RF-128).
- Las curvas PV y la capacidad de carga suben la demanda. La spec 011 (RF-18 a RF-22)
  mantiene fijas las SED de clientes importantes; aquí siguen fijas (usuario,
  2026-10-11).

## Usuarios / actores

- Ingeniero de planificación que, desde la web, estudia un proyecto de DIgSILENT ya
  preparado por la spec 011 (los tres casos, la base calibrada, las SED fijas).
- La empresa distribuidora, que entrega el fichero con tasas de falla, tiempos y costes.
- DIgSILENT PowerFactory 2024, por su API de Python, en el carril `powerfactory`.

## Historias de usuario

- H1: Como ingeniero quiero SAIFI, SAIDI y ENS por alimentador sin y con proyecto, para
  saber cuánto empeora o mejora la calidad de suministro.
- H2: Como ingeniero quiero cargar las tasas de falla de mi empresa en un fichero, para no
  escribirlas elemento a elemento en DIgSILENT.
- H3: Como ingeniero quiero saber dónde un reconectador baja más el SAIDI o la ENS, para
  proponer la obra con un número detrás.
- H4: Como ingeniero quiero saber cuánta generación distribuida y cuánta carga nueva admite
  cada nodo, para responder solicitudes de conexión sin un estudio a mano por cada una.
- H5: Como ingeniero quiero el margen de cada alimentador hasta el colapso de tensión,
  para saber cuánto crecimiento aguanta.
- H6: Como ingeniero quiero dónde y cuántos kvar compensar, con el coste de mi empresa,
  para proponer bancos de condensadores que se paguen con las pérdidas que ahorran.

## Requisitos funcionales (EARS)

Dónde y sobre qué

- RF-1: EL SISTEMA ofrecerá los estudios de esta spec en la parte «4.2 Estudios» de la
  pestaña «Cargas en DIgSILENT» (spec 011, RF-98), junto a los de la spec 011.
- RF-2: EL SISTEMA ejecutará estos estudios en «Sin proyecto» y en «Con proyecto», con la
  misma base calibrada, el mismo escenario de operación y las mismas comprobaciones
  previas que la spec 011 (RF-12 a RF-17, RF-49).
- RF-3: EL SISTEMA tomará los límites de tensión y de cargabilidad de estos estudios de los
  mismos límites que la spec 011 (RF-35).
- RF-4: DONDE la licencia de DIgSILENT no incluye el módulo de un estudio, EL SISTEMA lo
  listará como no disponible con el nombre del módulo, sin permitir ejecutarlo.
- RF-5: EL SISTEMA ejecutará cada estudio con los límites de tiempo, la cancelación y el
  proceso aparte de la spec 011 (RF-39 a RF-41).

Fichero de datos de la empresa

- RF-6: EL SISTEMA permitirá al operador cargar un fichero de la empresa con tasas de
  falla, tiempos y costes para el proyecto elegido.
- RF-62: EL SISTEMA aceptará el fichero de la empresa como un libro Excel con una hoja por
  grupo de datos: tasas de falla, tiempos de maniobra, equipos telemandados, bancos de
  condensadores y costes.
- RF-63: SI al libro le falta una hoja, ENTONCES EL SISTEMA lo dirá con el nombre de la
  hoja y bloqueará solo los estudios que la necesitan (RF-17, RF-18).
- RF-7: EL SISTEMA ofrecerá una plantilla descargable del libro, con sus hojas, sus
  columnas, sus unidades y una fila de ejemplo por clase de elemento.
- RF-8: EL SISTEMA leerá del fichero, por clase de elemento, la tasa de falla
  permanente, la tasa de falla transitoria y el tiempo medio de reparación en horas.
- RF-9: EL SISTEMA tomará las tasas de falla de las líneas y los cables por kilómetro y
  año, y las de los demás elementos por unidad y año.
- RF-10: EL SISTEMA reconocerá en el fichero estas clases de elemento: línea aérea de media
  tensión, cable subterráneo de media tensión, transformador de distribución, barra,
  interruptor, reconectador, fusible y seccionador.
- RF-11: DONDE el fichero da una fila para un tipo concreto de línea o cable (por el
  nombre del tipo en el proyecto), EL SISTEMA usará esa fila para los elementos de ese
  tipo en lugar de la de su clase.
- RF-12: EL SISTEMA leerá del fichero el tiempo de localización de la falla y el tiempo de
  maniobra manual, en minutos.
- RF-13: DONDE el fichero lista equipos telemandados por su código, EL SISTEMA les dará el
  tiempo de maniobra telemandada que traiga el fichero.
- RF-14: EL SISTEMA leerá del fichero los bancos de condensadores disponibles: potencia
  por paso en kvar, número de pasos, si es trifásico o monofásico, su inversión y su vida
  útil en años.
- RF-15: EL SISTEMA leerá del fichero el coste de la energía de las pérdidas, en moneda
  por kWh, y la tasa de descuento anual.
- RF-64: EL SISTEMA calculará el coste anual de cada banco, que es el que pide
  DIgSILENT (manual §41.10.4), como su anualidad: inversión × i·(1+i)ⁿ / ((1+i)ⁿ − 1),
  con i la tasa de descuento y n la vida útil.
- RF-65: SI la tasa de descuento es cero, ENTONCES EL SISTEMA tomará como coste anual la
  inversión dividida entre la vida útil.
- RF-66: EL SISTEMA dará en el informe de la ubicación de condensadores la inversión, la
  vida útil, la tasa y el coste anual calculado de cada banco.
- RF-16: SI el fichero tiene un valor negativo, vacío donde es obligatorio o en otra
  unidad que la de la plantilla, ENTONCES EL SISTEMA lo rechazará nombrando la hoja, la
  fila y la columna.
- RF-17: SI el fichero no trae una clase de elemento que tiene la red, ENTONCES EL SISTEMA
  no ejecutará la confiabilidad ni la ubicación de reconectadores y nombrará la clase y
  cuántos elementos tiene.
- RF-18: SI el fichero no trae bancos de condensadores o el coste de la energía, ENTONCES
  EL SISTEMA no ejecutará la ubicación de condensadores y dirá qué falta.
- RF-19: MIENTRAS el proyecto no tenga fichero cargado, EL SISTEMA listará la
  confiabilidad, la ubicación de reconectadores y la de condensadores con el dato que les
  falta, como la spec 011 (RF-24), sin permitir ejecutarlas.
- RF-20: EL SISTEMA guardará con el proyecto el último fichero cargado y lo nombrará, con
  su fecha de carga, en el informe de cada estudio que lo use.

Datos de confiabilidad en DIgSILENT

- RF-21: CUANDO el operador aplica el fichero, EL SISTEMA escribirá los modelos de falla y
  reparación en una variación propia, «Datos de confiabilidad», activa en «Sin proyecto»
  y en «Con proyecto» y nunca en el «Caso base».
- RF-22: EL SISTEMA asignará los modelos de falla a los elementos, dentro de esa variación,
  y no modificará ningún tipo existente del proyecto (spec 011, RF-59).
- RF-23: CUANDO el operador aplica un fichero nuevo, EL SISTEMA reemplazará los modelos de
  la variación «Datos de confiabilidad» sin crear otra.
- RF-24: EL SISTEMA dará a cada carga el número de clientes que trae la entrada
  (`ElmLod.NrCust`).
- RF-25: SI hay cargas sin número de clientes, ENTONCES EL SISTEMA las contará por
  alimentador en el informe, porque no pesan en SAIFI ni en SAIDI.
- RF-70: SI todas las cargas de un alimentador tienen un solo cliente, ENTONCES EL SISTEMA
  avisará que el número de clientes probablemente no llegó al proyecto y que SAIFI y
  SAIDI quedan ponderados por SED, no por cliente.
- RF-26: SI el proyecto no distingue la clase de cada equipo de maniobra (spec 011,
  RF-129), ENTONCES EL SISTEMA no ejecutará la confiabilidad ni la ubicación de
  reconectadores y dirá que hay que volver a convertir el alimentador o cargar su entrada.
- RF-27: EL SISTEMA configurará los interruptores, reconectadores y fusibles como equipos
  que despejan la falla, y los seccionadores como equipos que solo aíslan y reponen.
- RF-69: SI la cabecera de un alimentador no tiene un interruptor automático con
  protección, ENTONCES EL SISTEMA creará uno, cerrado, en el primer tramo del alimentador,
  dentro de la variación «Datos de confiabilidad».

Confiabilidad

- RF-28: EL SISTEMA ejecutará la confiabilidad con el comando de DIgSILENT
  (`ComRel3`), con análisis por flujo de carga y en modo de red de distribución.
- RF-29: EL SISTEMA ejecutará la confiabilidad en un único instante, el del caso de
  estudio.
- RF-30: CUANDO termina la confiabilidad, EL SISTEMA informará por caso y por alimentador
  SAIFI, SAIDI, CAIDI, ENS y, si el fichero trae tasas transitorias, MAIFI.
- RF-31: EL SISTEMA informará por alimentador la diferencia entre «Con proyecto» y «Sin
  proyecto» en cada índice de RF-30.
- RF-67: EL SISTEMA informará la energía no suministrada (ENS) en kWh por año, por caso,
  por alimentador y en total de los alimentadores marcados, porque es el índice que pide
  el regulador.
- RF-68: EL SISTEMA informará la diferencia de ENS entre «Con proyecto» y «Sin proyecto»
  por alimentador y en total, en kWh por año y en porcentaje.
- RF-32: EL SISTEMA informará por caso y por alimentador los cinco elementos que más
  aportan a la ENS, con su aporte.
- RF-33: SI todas las tasas de falla de un alimentador son cero tras aplicar el fichero,
  ENTONCES EL SISTEMA no informará sus índices y lo dirá, en vez de dar ceros.
- RF-71: SI un alimentador no tiene tensión antes de la falla (su fuente está fuera de
  servicio o el flujo no lo alimenta), ENTONCES EL SISTEMA no informará sus índices y
  dirá que está sin tensión, en vez de dar ceros.

Ubicación óptima de reconectadores

- RF-34: EL SISTEMA ejecutará la ubicación óptima de reconectadores con el comando de
  DIgSILENT (manual §46.5), sobre la misma configuración de la confiabilidad.
- RF-35: EL SISTEMA tomará como candidatos solo los equipos de clase interruptor o
  reconectador, y nunca un fusible, un seccionador ni el interruptor interno de una SED
  que crea el conversor.
- RF-36: EL SISTEMA excluirá como candidatos los equipos que protegen solo cables.
- RF-37: EL SISTEMA minimizará por defecto la ENS (RF-67) y permitirá al operador elegir
  SAIDI en su lugar, el número máximo de reconectadores en total y el máximo por
  alimentador.
- RF-38: EL SISTEMA ejecutará la ubicación de reconectadores sin cambiar la red: solo
  calcula y propone.
- RF-39: CUANDO termina, EL SISTEMA informará por caso cada reconectador propuesto, con su
  alimentador y la mejora del índice elegido que aporta.
- RF-40: CUANDO el operador acepta un reconectador propuesto, EL SISTEMA lo dará como
  obra «Reconectador» de la spec 011 (RF-56 en adelante), en su propia variación.

Capacidad de alojamiento

- RF-41: EL SISTEMA ejecutará la capacidad de alojamiento con el comando de DIgSILENT
  (`ComHostcap`), en dos cálculos: generación distribuida y carga nueva.
- RF-42: EL SISTEMA tomará como sitios los nodos de media tensión de los alimentadores
  marcados.
- RF-43: EL SISTEMA considerará solo los límites térmicos y de tensión de RF-3, y no los
  de protecciones, calidad de energía ni aporte al cortocircuito.
- RF-44: EL SISTEMA calculará la carga nueva nodo a nodo: en cada sitio por separado,
  con las demás cargas como están.
- RF-72: SI DIgSILENT no calcula la carga nueva de un nodo porque no tiene carga conectada,
  ENTONCES EL SISTEMA lo informará como «sin carga conectada» y no como capacidad cero.
- RF-45: DONDE el operador pide además el crecimiento conjunto, EL SISTEMA subirá a la vez
  solo las cargas escalables (spec 011, RF-19) y dejará fijas las de clientes importantes.
- RF-46: SI el comando de DIgSILENT no permite dejar fijas las cargas de clientes
  importantes en el crecimiento conjunto, ENTONCES EL SISTEMA no ofrecerá ese modo y lo
  dirá.
- RF-47: CUANDO termina, EL SISTEMA informará por caso y por nodo la potencia máxima de
  generación distribuida, la de carga nueva, el elemento que la limita y el motivo:
  sobrecarga o tensión.
- RF-48: EL SISTEMA informará por caso y por alimentador la menor y la mayor capacidad de
  sus nodos, con el nombre del nodo.
- RF-49: EL SISTEMA guardará la capacidad por nodo en un fichero descargable, con una fila
  por caso y nodo.

Curvas PV

- RF-50: EL SISTEMA ejecutará las curvas PV con el comando de DIgSILENT (`ComPvcurves`), un
  cálculo por alimentador marcado.
- RF-51: EL SISTEMA subirá solo las cargas escalables del alimentador y dejará fijas las
  de clientes importantes.
- RF-52: CUANDO termina, EL SISTEMA informará por caso y por alimentador la demanda
  inicial, la demanda crítica, el margen en kW y en porcentaje, y la barra crítica.
- RF-53: DONDE el operador elige considerar contingencias, EL SISTEMA usará las N-1 de la
  troncal de la spec 011 (RF-43) e informará la contingencia más crítica por alimentador.

Ubicación óptima de condensadores

- RF-54: EL SISTEMA ejecutará la ubicación óptima de condensadores con el comando de
  DIgSILENT (`ComCapo`), un cálculo por alimentador marcado, con los bancos y el coste de
  la energía del fichero.
- RF-55: EL SISTEMA ejecutará la ubicación de condensadores sin instalar nada: solo
  calcula y propone.
- RF-56: CUANDO termina, EL SISTEMA informará por caso y por alimentador cada banco
  propuesto, con su nodo, sus kvar y pasos, y el ahorro anual de pérdidas frente a su
  coste.
- RF-57: SI la optimización no propone ningún banco, ENTONCES EL SISTEMA lo dirá por
  alimentador, porque ningún banco se paga con lo que ahorra.
- RF-58: CUANDO el operador acepta un banco propuesto, EL SISTEMA lo dará como obra «Banco
  de condensadores» de la spec 011, en su propia variación.

Resultados y estado del proyecto

- RF-59: EL SISTEMA guardará los resultados de estos estudios en los ficheros de la spec
  011 (RF-37), con una fila por caso, alimentador y estudio.
- RF-60: CUANDO termina un estudio de esta spec, EL SISTEMA comprobará que ninguna carga
  cambió de demanda, que ninguna variación se creó salvo «Datos de confiabilidad» y que
  el caso conserva su hora de estudio y su etapa de grabación.
- RF-61: SI la comprobación de RF-60 encuentra un cambio, ENTONCES EL SISTEMA lo deshará,
  lo nombrará y marcará el estudio como no fiable.

## Requisitos no funcionales

- Escala: la confiabilidad y la capacidad de alojamiento se ejecutan sobre todos los
  alimentadores marcados, sin número fijo; el tiempo lo acota el límite de RF-5, no un
  tamaño de red.
- Universalidad (constitución P13): las clases de elemento y el fichero no dependen de
  una distribuidora; nada de Electro Dunas como valor por defecto.
- Idioma: mensajes, columnas de la plantilla e informe en español.
- Datos de la distribuidora (P9): el fichero de la empresa no se publica ni se envía a
  un servicio externo.

## Casos límite

- Fichero con una clase que la red no tiene: se acepta y se ignora esa fila.
- Fichero cargado y luego otro con menos clases: RF-17 vuelve a bloquear.
- Alimentador sin ningún interruptor ni reconectador candidato: RF-39 lo dice.
- Alimentador todo en cable: sin candidatos a reconectador (RF-36).
- Carga nueva de la spec 007 que cae en un nodo: la capacidad de «Con proyecto» ya la
  incluye; la diferencia con «Sin proyecto» es lo que consume.
- Flujo que no converge al empezar la curva PV: se aplica la spec 011, RF-17.
- Cancelación a mitad de la confiabilidad: los índices de los alimentadores terminados
  se conservan (spec 011, RF-41).

## Fuera de alcance

- Valores típicos de tasas de falla: sin fichero no hay estudio (usuario, 2026-10-11).
- Coste de la energía interrumpida (EIC) y minimizarla: no hay costes de interrupción.
- Evaluación técnico-económica (`ComTececo`): sigue en el «Fuera de alcance» de la 011.
- Ubicación óptima de telemandos y reposición manual óptima (manual §46.3 y §46.4).
- Mantenimiento planificado y confiabilidad a lo largo del año con estados de carga.
- Límites de protecciones, de calidad de energía y de cortocircuito en la capacidad de
  alojamiento: la impedancia de las fuentes llega por defecto (`studies.py`).
- Curvas QV, PTDF y descomposición de flujos.
- Aplicar sin el operador lo que proponen los optimizadores (RF-38, RF-55).
- Ajustes y curvas del reconectador propuesto (como en la spec 011).
- La prueba real en DIgSILENT: la hace el usuario.

## Criterios de finalización

- `grep -rnoE "012:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-72.
- Suite completa en verde, también la de la spec 011.
- `npx tsc --noEmit -p .` y `npm run build` en `frontend/` correctos.
- Prueba real en DIgSILENT con dos alimentadores calibrados y un fichero de la empresa, a
  cargo del usuario.

## Dudas resueltas (2026-10-11)

- Entran confiabilidad, ubicación de reconectadores, capacidad de alojamiento, curvas PV
  y ubicación de condensadores (usuario).
- Tasas de falla y tiempos: fichero de la empresa; sin él, no se ejecuta (usuario; RF-6 a
  RF-19).
- Bancos y coste de la energía: el mismo fichero (usuario; RF-14, RF-15, RF-18).
- Capacidad de alojamiento: generación y carga (usuario; RF-41).
- Curvas PV y crecimiento conjunto: solo crecen las cargas escalables (usuario; RF-45,
  RF-51).
- Spec nueva, no ampliación de la 011 (usuario).
- El fichero es un libro Excel con varias hojas (usuario; RF-62, RF-63).
- La empresa da inversión, vida útil y tasa; el sistema calcula el coste anual (usuario;
  RF-14, RF-15, RF-64 a RF-66).
- El índice que exige el regulador es la energía no suministrada; es el que se minimiza
  por defecto al ubicar reconectadores (usuario; RF-67, RF-68, RF-32, RF-37).

## Prueba en DIgSILENT (2026-10-12)

A petición del usuario, las sondas de T1 se ejecutaron en DIgSILENT 2024 sobre una copia
de un proyecto real de dos alimentadores ya convertidos, borrada al terminar. Cambiaron
la spec en lo siguiente:

- Sin interruptor de cabecera, `ComRel3` descarta todas las fallas de línea («No
  protection devices to clear the faults»): el DGS une la red externa al primer tramo sin
  interruptor, y solo despejan los interruptores automáticos con protección. Con uno en
  la cabecera desaparecieron los errores y los índices pasaron de solo transformadores a
  la red completa (RF-69).
- Las SED convertidas llevan un interruptor automático interno; sin excluirlo, la
  ubicación de reconectadores los tomaría como candidatos (RF-35).
- Todas las cargas tenían un cliente, el valor por defecto de PowerFactory (RF-70).
- Uno de los dos alimentadores tenía su fuente fuera de servicio y daba índices cero
  (RF-71).
- En carga nueva, DIgSILENT solo calcula los nodos con carga conectada (RF-72).
- `ComOpri` cambia la hora de estudio del caso y deja su variación grabando (RF-60).

## Dudas abiertas

Ninguna.
