# Spec 063 — Evaluación de conexión y operación comercial en un paso, para cualquier alimentador

Estado: implementada · Fecha: 2026-11-01 · Origen: petición del usuario, 2026-11-01 (informe de
la ampliación de INKA'S BERRIES S.A.C. en SM218)

Cita la 017 (informe de factibilidad, RF-47 a RF-72 y RF-136 a RF-141), la 037 (casos de
estudio) y la 011 (estudios en DIgSILENT). No las cambia: lo que aquí se pide se añade sobre ellas.

## Por qué

La factibilidad de suministro ya la emitió la distribuidora (ficha del punto de diseño y
conformidad del proyecto). Lo que falta es otra cosa: la evaluación para la conexión y la
operación comercial, que dice si la carga se puede conectar ya o si antes hay que mejorar
tramos o instalar bancos (usuario, 2026-11-01). Se hace sobre la recalibración del alimentador.


Para el informe de INKA (2026-11-01) hizo falta ejecutar a mano los estudios del paso 4.2,
revisar los casos y luego volver a 4.4. En medio, un estudio optimizador dejó «Sin proyecto»
fuera de la recalibración: los bancos EBC/ECB y los transformadores NTP dejaron de aplicarse,
y «Con proyecto» salió con SED al 826 %. El usuario: «esto debe aplicarse en el proyecto, en
la creación del informe; no todas las veces vamos a hacer los flujos y arneses: debe ejecutarse
una vez se pulse el botón de crear informe», y «debe ser universal, aplicativo para todo tipo
de alimentador».

## Requisitos

Un solo paso

- RF-1: CUANDO el operador pulsa el botón del informe de la carga nueva en 4.4, EL SISTEMA
  preparará los casos, ejecutará los flujos y escribirá la evaluación de conexión en un solo
  trabajo, sin exigir antes el paso 4.2.
- RF-2: EL SISTEMA no añadirá un botón nuevo: el del informe de la carga nueva de 4.4 hará el
  paso entero, y el paso 4.2 seguirá igual para los demás estudios.

Casos desde la recalibración

- RF-3: EL SISTEMA tomará «Sin proyecto», recalibrado con los cambios del operador y todos sus
  bancos, como estado actual.
- RF-4: EL SISTEMA preparará «Cargas nuevas» y «Con proyecto» como copia de «Sin proyecto», con
  las cargas nuevas y sus variaciones desactivadas durante la copia y activadas después.
- RF-5: CUANDO una etapa de una variación activa quede después de la hora de estudio de su
  caso, dentro de la ventana del sistema, EL SISTEMA la aplicará antes del flujo y lo dirá en
  el informe.

Flujos y conclusión

- RF-6: EL SISTEMA ejecutará el flujo equilibrado y el desequilibrado en «Sin proyecto»,
  «Cargas nuevas» y «Con proyecto».
- RF-7: EL SISTEMA tomará «Cargas nuevas» como estado proyectado sin obras, y «Con proyecto»
  como el estado con las obras del proyecto.
- RF-8: SI «Sin proyecto» y «Cargas nuevas» cumplen los límites de tensión y cargabilidad,
  ENTONCES EL SISTEMA concluirá que la carga es factible sin obras y no propondrá ninguna.
- RF-9: SI «Sin proyecto» o «Cargas nuevas» violan un límite, ENTONCES EL SISTEMA listará esas
  violaciones como el motivo de las obras y juzgará «Con proyecto» con las obras que tenga.
- RF-10: SI hay violaciones y «Con proyecto» no tiene obras, ENTONCES EL SISTEMA concluirá que
  la carga no se puede conectar sin refuerzo (mejora de tramos o bancos) y nombrará los
  elementos que lo requieren.
- RF-11: Por defecto, SI un caso no converge, ENTONCES EL SISTEMA no concluirá que la carga
  es factible y dirá en el informe el mensaje de DIgSILENT. La referencia «Cargas nuevas sin
  obras» no convergente podrá acompañar un dictamen condicionado exclusivamente a las obras
  cuando exista evidencia nativa de la operación final aplicada y persistida, «Sin proyecto»
  completo y convergente, y ambos flujos de «Con proyecto» completos, conformes y releídos.
  La referencia fallida seguirá identificada como no evaluable: no se inventarán sus
  tensiones, cargabilidades o pérdidas ni se afirmará que permite conexión sin obras.

Universal

- RF-12: EL SISTEMA aplicará el mismo paso a cualquier alimentador de cualquier fuente (TXT,
  MDB o VNR-GIS) y de cualquier distribuidora.
- RF-13: EL SISTEMA tomará los límites del perfil de la empresa y, sin perfil, ±5 % y 100 %,
  y el informe dirá cuáles usó y de dónde salen.

Datos de los PDF del solicitante

- RF-14: CUANDO los PDF dan una potencia actual y una solicitada, EL SISTEMA mostrará las dos
  y el incremento en el formulario, y el informe dirá «de A kW a B kW (+C kW)».
- RF-15: CUANDO los PDF dan un número de expediente de la distribuidora (EXP-…) y un código
  interno de la ficha, EL SISTEMA propondrá el EXP como expediente y conservará el código
  interno aparte.
- RF-16: CUANDO los PDF dan la estructura del punto de diseño, EL SISTEMA la propondrá como
  código del punto de diseño, y conservará la barra del modelo como dato del cálculo.
- RF-17: CUANDO los PDF dan la potencia de cortocircuito o las coordenadas del punto de diseño,
  EL SISTEMA las llevará a los datos del punto de diseño del informe.
- RF-18: CUANDO los PDF dan el NIS, EL SISTEMA lo propondrá en el asunto.
- RF-19: SI el alimentador de los PDF no es el de la carga elegida, ENTONCES EL SISTEMA lo
  avisará antes de generar.
- RF-20: CUANDO los PDF dan más de una fecha, EL SISTEMA propondrá la de la solicitud del
  interesado y dirá de qué documento sale cada una.

Obras para conectar

- RF-21: EL SISTEMA probará las obras de «Con proyecto» en este orden de escalones: bancos de
  condensadores, cambio de sección del conductor, terna y, al final, regulador. Cambia el orden
  de 025:RF-44.
- RF-22: EL SISTEMA elegirá la obra del primer escalón que deja la red dentro de los límites, y
  dentro de ese escalón la de menor costo anual; no subirá de escalón si el anterior ya cumple.
  Cambia 025:RF-53 y 052:RF-12. (Usuario, 2026-11-01: «primero debe comenzar con bancos y luego con
  cambio de sección y una terna después, pero si y solo si se requiere; si ya están dentro de lo
  permitido de la norma, ahí debe quedar la solución».)

- RF-23: CUANDO se evalúa la conexión de unas cargas nuevas, EL SISTEMA optimizará «Con proyecto»
  solo con esas cargas y apartará las demás cargas nuevas del proyecto. (SM218, 2026-11-01: la
  optimización de INKA contaba 4 cargas, entre ellas la copia de INKA del bloque mal ubicada.)
- RF-24: SI ninguna de las cargas pedidas está aplicada en los alimentadores marcados, ENTONCES
  EL SISTEMA lo dirá con sus nombres y no optimizará nada.

- RF-25: CUANDO la barra de una carga nueva la crea su propia variación, EL SISTEMA probará el
  banco en la barra existente más cercana de la misma troncal, la de aguas arriba del tramo que
  partió la carga. (SM218, 2026-11-01: el escalón de bancos quedaba vacío para INKA y se pasaba a
  terna con regulador sin haber probado bancos.)
- RF-26: EL SISTEMA no probará reguladores en la escalera salvo que el perfil de la empresa lo
  pida (`escalera.con_regulador`). (Usuario, 2026-11-01: «hiciste con bancos en la misma troncal,
  pero usaste regulador».)

- RF-27: EL SISTEMA probará el cambio de sección subiendo de una sección a la inmediata
  superior, entre todas las que llevan la corriente del tramo, y se quedará con la menor que deja
  la red en norma. (Usuario, 2026-11-01: «el cambio de sección debería subir al superior así
  sucesivamente, no de frente a 120 mm²».)
- RF-28: EL SISTEMA dirá en la evaluación cuánto mejora cada escalón probado (la tensión en el
  punto de diseño y la mínima de media con bancos, con cada sección y con la terna), también
  cuando no basta. (Usuario, 2026-11-01: «primero debiste probar con bancos, ver cuánto mejora».)

- RF-29: CUANDO la calibración fija la consigna de la fuente, EL SISTEMA la llevará al «Caso
  base», a «Sin proyecto», a «Cargas nuevas» y a «Con proyecto». (Usuario, 2026-11-01: «esto debe
  ser en caso base y caso con cargas y caso con proyecto, fuente a 1,02 p.u.»; SM218 medía las
  obras con la fuente a 1,00 en «Con proyecto».)

- RF-30: EL SISTEMA cambiará de sección solo los tramos cuya corriente nominal es menor que la del
  conductor nuevo, y dejará los de igual o mayor sección. (SM218, 2026-11-01: la «sección CU 50 mm²»
  reemplazaba los 10,32 km y el punto de diseño bajaba de 0,934 a 0,909 p.u.)

- RF-31: EL SISTEMA dirá de cada obra dónde va en la red de media tensión: el nodo de MT de cada
  banco y, de cada tramo que cambia de sección o lleva terna, su nodo de inicio y su nodo final.
  (Usuario, 2026-11-01: «en el cambio de tramos de cable y la ubicación de bancos deben indicarse los
  nodos de inicio y el nodo de MT donde se ubica el banco y los tramos».)

- Aclaración de RF-26 (2026-11-01): el regulador entra por defecto, al final del orden de RF-21,
  como manda 025:RF-44 («todas las obras según CAPEX hasta los reguladores, pero en orden de
  prioridad», usuario); un perfil puede quitarlo con `escalera.con_regulador: false`.

- RF-32: EL SISTEMA probará la sección y la terna sobre el camino eléctrico de la cabecera a cada
  carga nueva, y pondrá su banco en la barra existente de ese camino justo aguas arriba de la carga.
  (SM218, 2026-11-01: INKA cuelga de un ramal a 17,08 km con 5,8 km de 50, 35 y 16 mm²; la escalera
  probaba las obras en los 10,32 km de troncal de 120 mm² más cercanos por GPS.)

- RF-33: SI ninguna obra cumple en los sorteos pero alguna cumple con la máxima en DIgSILENT,
  ENTONCES EL SISTEMA elegirá la primera de esas por el orden de prioridad (RF-21, RF-22), avisará
  que los sorteos no la confirmaron y no pasará a otras obras ni a la SET nueva. (Usuario,
  2026-11-01: «si hay solución de la optimización, nada debe crearse ni ver otras obras».)

- RF-34: CUANDO las cargas nuevas que se evalúan suman más que el umbral del perfil
  (`planificacion.set_nueva_desde_kw`; Electro Dunas, 10 000 kW), EL SISTEMA planteará como solución
  una SET nueva, sin probar la escalera de bancos, secciones y ternas. (Usuario, 2026-11-01: «a las
  cargas que suman superior a 10 MW la alternativa de solución debe plantear una nueva SET».)

## Ampliación solicitada al continuar el 2026-11-01

- RF-35: EL SISTEMA incluirá planos del estado actual, con cargas nuevas y con proyecto,
  identificando problemas y obras mediante colores y/o tramas distintos y una leyenda explícita.
- RF-36: EL SISTEMA conservará cada carga nueva y cada obra en su propia variación, con las
  cargas y obras previstas activas solo en los casos a los que corresponden.
- RF-37: EL SISTEMA comprobará la solución de la SET nueva con el total de las cargas nuevas
  del proyecto, sin reducir ni apartar demanda para lograr convergencia o cumplimiento.
- RF-38: EL SISTEMA evaluará la operación de NA203–NA205 con la SET nueva y la central térmica
  fuera de servicio, y solo declarará aceptada la solución si convergen ambos flujos y se
  cumplen tensión y cargabilidad en toda la red del proyecto.
- RF-39: EL SISTEMA tratará como del alimentador las cargas, barras y tramos de todas las troncales
  de su cabecera, en los sorteos, las pérdidas, el criterio y los estudios, también en un proyecto de
  varios alimentadores. (SM218, 2026-11-02: `ElmFeeder` veía 242 de 306 cargas.)
- RF-40: CUANDO una evaluación incluya cargas de una troncal fuera del `ElmFeeder`, EL SISTEMA lo dirá
  en su informe con cuántas son.
- RF-41: DONDE el libro de pérdidas de la empresa vaya en dos hojas, EL SISTEMA leerá el sistema del
  alimentador en una y sus pérdidas reconocidas en la otra, con lo que diga el perfil de empresa.
- RF-42: CUANDO se genere el informe de la carga nueva, EL SISTEMA dejará el PDF junto al Word editable
  y, si no puede, dirá el motivo sin perder el Word.
- RF-43: SI una barra está sin tensión, ENTONCES EL SISTEMA la dirá como isla sin fuente y no la contará
  como tensión mínima ni como nodo fuera de banda.
- RF-44: EL SISTEMA juzgará la tensión mínima, la máxima y los nodos fuera de banda del informe en media
  tensión, y conservará las barras de baja tensión en los datos del estudio.
- RF-45: SI la cabecera del flujo desequilibrado se separa más de un 2 % de la del equilibrado, ENTONCES EL
  SISTEMA usará el equilibrado en el informe y lo avisará.
- RF-46: DONDE no se haya calculado el transformador de la SET, EL SISTEMA lo dejará fuera del informe,
  sin contarlo como hueco ni impedir la conclusión.
- RF-47: DONDE haya flujo de «Cargas nuevas», EL SISTEMA dibujará en el informe sus imágenes de tensión y de
  cargabilidad.
- RF-48: CUANDO el operador cambie la carga elegida, EL SISTEMA vaciará la solicitud, el punto de diseño y lo
  leído de los PDF de la carga anterior.
- RF-49: SI el cliente de la solicitud no comparte ningún nombre con la carga elegida, ENTONCES EL SISTEMA lo
  avisará en el formulario y lo señalará como hueco del informe.
- RF-50: SI Word falla después de guardar el PDF, ENTONCES EL SISTEMA dará el PDF por hecho.

## Fuera de alcance

- El informe juzga las obras aplicadas en «Con proyecto». La evaluación/refuerzo de COPARA
  solicitado en RF-36 a RF-38 se ejecuta en el arnés de obras existente; no se recrea ni
  desplaza la SET ya dimensionada y situada en el centro de cargas.
- Cortocircuito, curvas PV, capacidad de alojamiento y demás estudios nativos: siguen en 4.2.
- El informe de estudio (con las cargas en bloque) de la 017: queda como está.
- La cargabilidad del transformador de la SET (017:RF-71): sigue con su paso propio.

## Criterios de finalización

- Pulsando solo «Generar informe de factibilidad», sobre un proyecto ya calibrado y con la
  carga aplicada, sale el informe con los tres casos.
- La prueba sorteada con alimentadores de distinto tamaño y fuente pasa sin cambiar nada.
- El informe de INKA en SM218 sale desde la web con un clic y dice lo mismo que el hecho a mano.
