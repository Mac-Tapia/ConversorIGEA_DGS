# Spec 035 — Fijas de la tabla en el instante de la máxima, Q de cabecera con bancos y unidades de DIgSILENT

Estado: implementada · pedida por el usuario el 2026-10-29 («verifica que la tabla cruzada de los
SED coincida en la misma fecha del valor de cabecera seleccionada y los valores de las columnas
de Pot (kW) y Q (kvar) de la misma tabla se carguen a DIgSILENT con escala 1, fijas, y los SED que
no están en la tabla se escalan para cuadrar al valor de la cabecera más fijas; además debe
considerar los bancos si existen en la red; si existen, también se debe cuadrar los Q (kvar);
verifica que las unidades sean las correctas en DIgSILENT»; prueba real con SM218).

## Por qué

Revisado el 2026-10-29, tres cosas no cuadraban con lo pedido:

- La tabla de clientes cruzados de la web (paso 2.3) se pedía sin instante: enseñaba la POT de
  cada cliente, cada una de su propio día, y el kVAR del registro de esa POT. El plan del ajuste,
  en cambio, escribe en las fijas la P y la Q del registro del instante de la máxima de su
  alimentador (004:RF-67). Lo que el operador veía no era lo que iba a DIgSILENT.
- La Q de cabecera no se cuadraba nunca: 006:RF-12 y RF-14 la dejaban como resultado de la red y
  solo se informaba. SM218 tiene siete bancos de 450 kvar en servicio (3 150 kvar): con las
  escaladas a FP 0,98 la Q de cabecera queda lejos de la medida sin que nada la corrija.
- Todo se escribía dando por hecho MW y Mvar (`plini = kW / 1000`). La unidad de las cargas es un
  ajuste del proyecto de DIgSILENT (`SetPrj.cspqexp`): en un proyecto en kW las demandas
  quedarían mil veces menores sin ningún aviso. SM218 está en MW y Mvar (sonda del 2026-10-29).

## Requisitos

Tabla cruzada en el instante de la máxima

- RF-1: CUANDO el operador cruza los clientes importantes con una máxima de cabecera buscada,
  EL SISTEMA tomará de cada cliente el registro de 15 minutos de la fecha y hora de la máxima de
  su alimentador (la de su barra de 60 kV si la tiene, 022:RF-84), la misma con que el ajuste
  escribe las fijas.
- RF-2: EL SISTEMA mostrará en la tabla, por cliente, la P (kW) y la Q (kvar) que se escribirán en
  su SED, la fecha y hora de la que salen y de dónde salen (registro del instante, registro de su
  POT, EA/ERI del mes o FP de la cabecera), con el mismo cálculo que el ajuste.
- RF-3: SI un cliente no tiene registro en ese instante, ENTONCES EL SISTEMA lo dirá en la fila y
  usará lo que use el ajuste (004:RF-66, RF-67), sin otro cálculo para la tabla.
- RF-4: EL SISTEMA escribirá en cada SED fija la suma de la P y de la Q que la tabla muestra para
  sus clientes conectados, con factor de escala 1 y sin escalar (`i_scale` 0).

Q de cabecera con bancos

- RF-5: CUANDO se recalibra (RF-22) y el alimentador tiene bancos de condensadores en servicio
  en el proyecto, EL SISTEMA cuadrará en «Sin proyecto» la Q de cabecera además de la P, en el
  mismo flujo, con una precisión de ±2 % (usuario, 2026-10-29).
- RF-6: Para cuadrar la Q, EL SISTEMA cambiará solo la Q de las SED escaladas, un mismo factor
  para todas; las fijas conservan la Q de la tabla (RF-4) y los bancos quedan como estén, a su
  máxima capacidad (015:RF-66).
- RF-7: EL SISTEMA escribirá en cada escalada su Q base por el cociente entre el factor de Q y el
  de P, de modo que un solo factor de escala de DIgSILENT (`scale0`) siga valiendo para P y Q.
- RF-8: SI ni con las escaladas sin reactiva la Q de cabecera baja a la medida, ENTONCES EL
  SISTEMA dejará las escaladas sin reactiva, aceptará por kW y dirá cuántos kvar de compensación
  faltan.
- RF-9: SI las escaladas no tienen Q base (FP 1 en el perfil), ENTONCES EL SISTEMA no podrá
  cuadrar la Q, aceptará por kW y lo dirá.
- RF-10: EN la primera calibración, o SI el alimentador no tiene bancos en servicio, EL SISTEMA
  seguirá como hasta ahora: Q de las escaladas con el FP del perfil y Q de cabecera informada
  (006:RF-12, RF-14).
- RF-11: EL SISTEMA dirá en el informe de la calibración el criterio (kW, o kW y kvar), el factor
  de Q, el FP que resultó para las escaladas, la Q de cabecera frente a la medida y los kvar que
  entregan los bancos.
- RF-12: EL SISTEMA validará en DIgSILENT las escaladas con el FP que resultó del cuadre de la Q,
  no con el del perfil (015:RF-67).
- RF-13: SI la red ya tiene el reparto de kW pero no la Q medida, ENTONCES EL SISTEMA no la dará
  por calibrada (sin «NO_REDISTRIBUIR») y volverá a cuadrar.

Unidades de DIgSILENT

- RF-14: ANTES de escribir ninguna demanda, EL SISTEMA leerá en DIgSILENT la unidad de P y Q de
  las cargas (`plini`, `qlini`) y la de los bancos (`qcapn`) del proyecto.
- RF-15: SI esa unidad no es MW y Mvar, ENTONCES EL SISTEMA no escribirá nada y dirá la unidad que
  encontró y dónde cambiarla (ajustes del proyecto).
- RF-16: EL SISTEMA dirá en el informe de la calibración las unidades leídas.

Libro de clientes de otro mes (usuario, 2026-10-29: «si no existe el mismo mes de la cabecera
usa el mes anterior… el mes anterior solo siempre y cuando no exista el del mismo mes»; «nada
debe ser inventado, todo debe ser real y preciso»)

- RF-17: SI no hay libro de clientes importantes del mismo mes que la máxima de cabecera del
  alimentador, ENTONCES EL SISTEMA usará el del mes anterior más cercano que exista, y solo en
  ese caso; SI tampoco hay uno anterior, ENTONCES sus SED se reparten por kVA (025:RF-11).
- RF-18: CUANDO usa el libro de un mes anterior, EL SISTEMA lo dirá en el plan, en la tabla y
  en el informe con el libro y su mes, y sus clientes irán con lo que ese libro trae (el
  registro de su POT o su EA/ERI del mes), sin deducir ningún valor de la fecha de la máxima.

Sin bloquear y con revisión del evaluador (usuario, 2026-10-29: «cuando se hace cambio de mes
con otro mes que no sea el de la cabecera no debe bloquear nada»; «si no existen [bancos] se
debe recomendar revisar el proyecto del alimentador para su implementación o revisión de los
bancos existentes, donde el evaluador debe validar»)

- RF-19: SI el libro de clientes con que se cruza es de un mes distinto al de la máxima de
  cabecera, ENTONCES EL SISTEMA no bloqueará el plan ni el ajuste: usará ese libro y lo dirá con
  los dos meses (cambia 013:RF-30).
- RF-20: SI al recalibrar el alimentador no tiene bancos en servicio y su Q de cabecera queda fuera de ±2 % de
  la medida, o los tiene y no alcanzan (RF-8), ENTONCES EL SISTEMA recomendará en el informe y en
  la web revisar en el proyecto del alimentador la implementación de bancos o los existentes,
  con la Q calculada, la medida y la diferencia, para que el evaluador lo valide.

Recalibración (usuario, 2026-10-29: «la recalibración se debe activar ya con la primera
calibración … con opción de seleccionar primero los valores de cabeceras, barra y SET y sus
valores de tablas cruzadas, hacer lo mismo como se calibra … considerando toda la topología:
SED nuevas, bancos y todo»)

- RF-21: CUANDO un proyecto tiene su primera calibración, EL SISTEMA activará la recalibración:
  los mismos pasos de la calibración (la máxima del alimentador o de su barra y SET, la tabla
  cruzada y el ajuste) sobre la red que haya en DIgSILENT, escaneada antes de aplicar (028:RF-16),
  con el botón «Recalibrar (n.º k)» y el número guardado con cada calibración; el «Recalibrar»
  rápido (028:RF-21) se activa también desde la primera calibración.

Qué cuadra cada una (usuario, 2026-10-29: «en la calibración solo se cuadra la P kW y en la
recalibración se cuadra la P kW y kvar; esto debe estar bien claro y definido»; «la
recalibración ya debe llegar con los cambios de implementación, ya sea bancos y cambios de
sección de cables… no confundas con obras, ese es otro caso con proyecto; la recalibración es
de ajustes o cambios de actualización»)

- RF-22: EL SISTEMA cuadrará solo la P (kW) en la primera calibración de un alimentador, y la P
  (kW) y la Q (kvar) en cada recalibración (RF-5), y lo dirá en el botón, en el plan y en el
  informe («Calibración: solo P» o «Recalibración n.º k: P y Q»).
- RF-23: EL SISTEMA recalibrará «Sin proyecto» con las actualizaciones de la red que tenga ese
  caso (bancos implementados, cambios de sección o de tipo de conductor, tramos nuevos y demandas
  cambiadas a mano, escaneados antes, 028:RF-16, RF-17, RF-26), y no con las obras de «Con
  proyecto», que son otro caso (spec 011).

## Fuera de alcance

- Alimentadores con central en su troncal (spec 021): se calibran por zonas y su Q sigue
  informada.
- Cambiar los escalones de los bancos para cuadrar la Q: los bancos existentes trabajan a su
  máxima capacidad (015:RF-66) y los que faltan los añade 021:RF-64 si el operador lo pide.
- Convertir a otras unidades en lugar de detenerse (RF-15): ningún proyecto importado por el
  conversor las tiene; si aparece uno, se decidirá entonces.

## Relación con otras specs

- Cambia 006:RF-12 y RF-14 y 015:RF-54 solo cuando hay bancos en servicio (RF-5 a RF-10).
- Usa 004:RF-66, RF-67 y 022:RF-84 para el registro del cliente.
