# Spec 037 — Caso «Cargas nuevas» en los estudios de la web

Estado: cumplida (2026-11-08: tareas cerradas por orden del usuario, sin corrida propia; su aceptación pasa a la spec 100) · Fecha: 2026-10-29 · Origen: petición del usuario sobre «Preparar los estudios».

## Contexto y objetivo

El panel del botón «Preparar los estudios» (4.2 en el código, referido como 4.1 por el
usuario) solo anuncia y ejecuta «Sin proyecto» y «Con proyecto». La spec 025:RF-61 a
RF-66 ya define «Cargas nuevas», con escenario propio y admisión gradual de cargas.
Se incorpora ese diagnóstico al mismo trabajo para distinguir demanda adicional de obras.
Esta spec amplía la ejecución de la 011 y reutiliza la 025 sin cambiar sus requisitos.

## Requisitos funcionales (EARS)

- RF-1: EL SISTEMA explicará en el panel de estudios y su confirmación los casos «Sin proyecto», «Cargas nuevas» y «Con proyecto».
- RF-2: CUANDO prepara estudios con cargas nuevas de los alimentadores marcados, EL SISTEMA renovará «Cargas nuevas» mediante la admisión gradual definida en 025:RF-61 a RF-66.
- RF-3: EL SISTEMA ejecutará los estudios elegidos primero en «Sin proyecto», después en «Cargas nuevas» si hay cargas y finalmente en «Con proyecto» si hay cargas u obras.
- RF-4: EL SISTEMA conservará el año de la calibración al preparar y resolver los casos de estudio.
- RF-5: EL SISTEMA mostrará las cargas excluidas del diagnóstico y el motivo informado por el motor, sin declarar que se estudiaron todas.
- RF-6: EL SISTEMA conservará las medidas y violaciones de «Cargas nuevas» en los resultados y CSV, manteniendo la comparación existente con proyecto menos sin proyecto.
- RF-7: SI el caso de diagnóstico no puede prepararse o no pertenece al sistema, ENTONCES EL SISTEMA informará el impedimento sin sustituirlo por «Con proyecto».
- RF-8: CUANDO prepara los casos y «Con proyecto» no tiene obras y le faltan objetos de «Sin proyecto» (014:RF-34), EL SISTEMA lo renovará como copia de «Sin proyecto» con su escenario, y conservará el anterior renombrado, sin su marca y con su escenario. (Usuario, 2026-11-01, SM218: «debes seguir el flujo: en la recalibración son modificaciones manuales y en la recalibración se consideran todos los bancos».)

## Casos límite y aclaraciones

Sin cargas nuevas se omite el diagnóstico; las obras siguen permitiendo estudiar «Con
proyecto». Si ninguna carga converge, se informa la exclusión y se mide el diagnóstico
con sus cargas activas reales. Un caso ajeno con igual nombre no se modifica. Los
guiones del operador, obras y transferencias conservan su contrato actual. Se mantienen
límites, cancelación y tiempo máximo por estudio. «Cargas nuevas» hereda las obras que
ya pertenezcan a «Sin proyecto»; no recibe obras exclusivas de «Con proyecto».

## Fundamento científico

Fuentes consultadas en la web el 2026-10-29. Sustentan evaluar el efecto de la demanda
adicional y las restricciones físicas antes de atribuir mejoras a refuerzos; la interfaz
y el orden concreto de los tres casos son decisiones de esta aplicación.

- Cicenas, M. (2025). *Decarbonisation of district heating network and its interaction
  with electricity distribution network, a case study in South-Holland*. Tesis de
  maestría, TU Delft. El resumen institucional relaciona nuevas cargas con sobrecargas
  y la necesidad de refuerzos: https://resolver.tudelft.nl/uuid:129dc238-e7ed-401a-8420-f0e99c534ae6.
- Zakaria, A. (2025). *Evaluation and allocation of distribution network hosting capacity
  for connecting renewable generation and new loads*. Tesis doctoral, University of
  Edinburgh. Evalúa nuevas cargas bajo restricciones térmicas y de tensión:
  https://era.ed.ac.uk/items/993cbe67-b153-494f-ab6b-765dcbbcf6bb.
- Gatta, F. M., Geri, A., Maccioni, M., Palazzoli, A. y Sancioni, P. (2024).
  *Low voltage electric distribution network planning with demand control*. Electric
  Power Systems Research, 226, 109950. DOI: 10.1016/j.epsr.2023.109950.
  El registro institucional muestra referencias Scopus y WoS y describe escenarios de
  crecimiento con refuerzos: https://iris.uniroma1.it/handle/11573/1700704.

## Fuera de alcance

Cambiar la admisión eléctrica de la 025, optimizar obras, modificar el PIDE, extender
los guiones del operador o declarar aceptación eléctrica con pruebas sintéticas.

## Criterio de finalización

Pruebas del plan y ejecución web, resolución nativa contra el doble del motor,
resultados CSV, trazabilidad y compilación del frontend. La comprobación real y la
relectura en DIgSILENT quedan registradas por separado.
