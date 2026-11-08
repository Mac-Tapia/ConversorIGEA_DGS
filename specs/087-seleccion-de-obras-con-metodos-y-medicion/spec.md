# Spec 087 — Selección de obras con el oráculo, métodos probabilísticos y medición de la mejora

Estado: cumplida (2026-11-08: tareas cerradas por orden del usuario, sin corrida propia; su aceptación pasa a la spec 100) · Fecha: 2026-11-04 · Origen: petición del usuario tras la corrida de Pisco

## Contexto y objetivo
Pisco (2026-11-04): la evaluación por alimentador (042:RF-24) prueba cada variante en DIgSILENT, a cerca de 1 min cada una, hasta 150 por
alimentador, y elige la primera que cumple. La búsqueda bayesiana, el frente de Pareto y la cadena de Markov de la spec 052 existen, pero ese
camino no los usa; tampoco hay manera de demostrar si una versión mejora a otra. Usuario (2026-11-04): «debes implementar todos los métodos e
integrarlo para su uso y funcionamiento en los siguientes análisis de otro o cualquier sistema […] debe medir en cuánto se mejora con estas
implementaciones: tiempo, recursos, soluciones, cantidad y calidad de obras, cumplimiento de normas, pruebas, normas de diseño».

## Usuarios / actores
Ingeniero de planificación, desde la web o con `tools/sistema_web.py`, para cualquier sistema y empresa. DIgSILENT confirma toda obra.

## Historias de usuario
- H1: Como planificador quiero la obra de menor costo que cumple, en minutos, para cualquier sistema.
- H2: Como planificador quiero saber con qué certeza cumple una obra.
- H3: Como responsable quiero demostrar con datos cuánto mejora una versión frente a otra.

## Requisitos funcionales (EARS)

Oráculo en la evaluación por alimentador
- RF-1: CUANDO la escalera por alimentador evalúa un alimentador, EL SISTEMA calculará con el oráculo todas sus variantes antes de abrir ninguna en DIgSILENT.
- RF-2: EL SISTEMA medirá en DIgSILENT primero las `escalera.confirmar_en_digsilent` variantes (3 si el perfil no lo da) que el oráculo da por cumplidoras, de menor a mayor costo.
- RF-3: SI ninguna de esa tanda cumple en DIgSILENT, ENTONCES EL SISTEMA medirá la tanda siguiente, hasta agotar las variantes.
- RF-4: SI el oráculo no se puede construir o falla, ENTONCES EL SISTEMA medirá las variantes en DIgSILENT como en 042:RF-24, y lo dirá con su motivo.
- RF-5: EL SISTEMA dará al oráculo los mismos tramos sobrecargados que a la escalera (042:RF-43).
- RF-6: EL SISTEMA dejará por variante medida lo que predijo el oráculo y lo que midió DIgSILENT, y mandará DIgSILENT si difieren.

Probabilidad bayesiana de cumplir
- RF-7: EL SISTEMA estimará la probabilidad de cumplimiento de una variante con una posterior Beta sobre los sorteos ya medidos.
- RF-8: CUANDO la posterior deja la probabilidad de alcanzar `escalera.cumplimiento` por debajo de 1 % o por encima de 99 %, EL SISTEMA dejará de sortear esa variante.
- RF-9: EL SISTEMA dirá de cada variante los sorteos usados, la fracción y la probabilidad de que alcance `escalera.cumplimiento`.

Selección
- RF-10: EL SISTEMA buscará con Optuna, para cada alimentador que no cumple, combinaciones de obras fuera de la lista de variantes, y probará primero las que el oráculo da por cumplidoras con menos costo.
- RF-11: EL SISTEMA dará el frente de Pareto de costo anual, pérdidas y tensión mínima de las variantes que cumplen en el oráculo.
- RF-12: EL SISTEMA elegirá, entre las medidas que cumplen en DIgSILENT, la de menor costo anual.
- RF-13: EL SISTEMA calculará las pérdidas de energía de la obra elegida con la cadena de Markov de la curva de cabecera, y dirá el resultado junto a su costo.

Planeamiento por etapas
- RF-14: DADAS las obras elegidas y sus costos, EL SISTEMA dará con un árbol de decisión, para escenarios de demanda baja, media y alta, si conviene construir cada obra ahora o diferirla, con su valor esperado.
- RF-15: EL SISTEMA dará con un proceso de decisión de Markov, resuelto por inducción hacia atrás, el año de construcción de cada obra en el horizonte del perfil.
- RF-16: EL SISTEMA dirá las probabilidades de transición y los escenarios usados en RF-14 y RF-15.
- RF-29: EL SISTEMA medirá con el oráculo cuánto puede crecer la demanda de un alimentador antes de incumplir, sin obra o con la elegida, y lo usará como margen en RF-14 y RF-15.
- RF-30: DONDE `escalera.usar_oraculo` sea falso, EL SISTEMA medirá las variantes como en 042:RF-24, para poder comparar los dos métodos.

Modelo aprendido
- RF-17: EL SISTEMA guardará cada variante medida en DIgSILENT con sus rasgos y su resultado, sin nombres de clientes.
- RF-18: DONDE haya evaluaciones de al menos `escalera.modelo_min_sistemas` sistemas (3 si el perfil no lo da), EL SISTEMA entrenará un clasificador de árboles que prediga si una variante cumple, y lo validará dejando fuera un sistema entero cada vez.
- RF-19: MIENTRAS el clasificador no supere al orden por costo en esa validación, EL SISTEMA no lo usará.
- RF-20: DONDE el clasificador pase RF-19, EL SISTEMA lo usará solo para decidir en qué tanda se mide cada variante: ni descarta una variante ni da una obra por buena sin DIgSILENT.

Medición de la mejora
- RF-21: CUANDO termina un «Con proyecto», EL SISTEMA añadirá a `corridas_obras.jsonl` el sistema, la revisión del código, el método, el tiempo total, el tiempo de oráculo y de DIgSILENT, los flujos, las órdenes y la memoria máxima.
- RF-22: EL SISTEMA añadirá a esa fila los alimentadores resueltos y sin resolver, las obras por clase, los km, la inversión, el costo anual, las pérdidas, la tensión mínima y la carga máxima.
- RF-23: EL SISTEMA añadirá a esa fila, por cada norma de RF-24, cuántas obras la cumplen y cuántas no.
- RF-24: EL SISTEMA comprobará de cada obra aplicada: tensión en los límites del perfil, carga bajo el límite de planeamiento, sección normalizada, banco admitido en valle, ternas con su configuración (084:RF-12 a RF-15), SET en área libre (084:RF-1 a RF-8) y coordenadas (042:RF-36).
- RF-25: DADAS dos versiones o dos métodos sobre el mismo sistema, EL SISTEMA contrastará con la prueba de 081:RF-73 el tiempo y las órdenes fallidas, y dará la diferencia de cada medida de RF-21 a RF-23.
- RF-26: EL SISTEMA dirá que no hay contraste de una medida si tiene menos de 5 corridas por grupo, en vez de declarar una mejora.
- RF-27: DONDE se le dé un informe JUnit de pytest, EL SISTEMA añadirá a la fila las pruebas aprobadas, fallidas y omitidas.

Coste de cada tanda
- RF-28: MIENTRAS dure un trabajo, EL SISTEMA medirá una sola vez los sorteos base de «Sin proyecto» de cada combinación de alimentadores y cargas apartadas. Pisco (2026-11-04): cada orden los repetía, 200 flujos, unos 10 min, antes de probar la primera variante.

Más obras en la escalera (usuario, 2026-11-04: «debe integrar como obra nuevos alimentadores, transferencias de cargas, traslado de cargas, las nuevas celdas, crearlas, pero sí debe estar en módulo PIT de CAPEX; proponer área o zonas para otro nuevo alimentador»)
- RF-31: SI ninguna variante de bancos, sección, terna y regulador cumple en un alimentador, ENTONCES EL SISTEMA probará, en este orden, transferir carga, trasladar carga, un alimentador nuevo y una SET nueva, y se parará en la primera que cumpla en DIgSILENT.
- RF-32: EL SISTEMA propondrá la transferencia con un enlace hacia el alimentador vecino más cercano que conserve margen de tensión y de carga.
- RF-33: EL SISTEMA propondrá el traslado de la rama con la carga nueva hacia otro alimentador, o a otra tensión si el vecino la tiene distinta.
- RF-34: EL SISTEMA propondrá para cada zona que lo necesite un alimentador nuevo, con su punto de salida en la barra de la SET, su trazado y su punto de llegada georreferenciados.
- RF-35: CUANDO una obra necesita una salida nueva en una SET, EL SISTEMA creará su celda en DIgSILENT como parte de la obra.
- RF-36: EL SISTEMA tomará el costo de cada celda y de cada km de alimentador nuevo de los módulos del libro CAPEX de la empresa (hojas de módulos PIT y de nuevos alimentadores), citando la fila usada.
- RF-37: SI el libro no trae ese módulo, ENTONCES EL SISTEMA usará el costo del más parecido y lo marcará por confirmar, como en 042:RF-33.
- RF-38: EL SISTEMA propondrá el área de cada alimentador nuevo: la zona que agrupa sus cargas, con su centro de carga, su demanda presente y a horizonte, sus coordenadas y las barras que pasarían a él.

No insistir en lo que no va a cumplir (usuario, 2026-11-04: «no hacer cálculo en vano, si no hay solución proponer obra más
integral, no insistir en algo que no va a solucionar»):
- RF-39: EL SISTEMA medirá en DIgSILENT, de cada alimentador, solo las variantes que el oráculo da por cumplidoras y una tanda de las más cercanas; sustituye a «hasta agotar las variantes» de RF-3.
- RF-40: SI ninguna de las variantes de RF-39 cumple en DIgSILENT, ENTONCES EL SISTEMA pasará el alimentador a la obra integral (alimentador nuevo o SET nueva, 042:RF-24) sin medir las demás, y dirá cuántas dejó sin medir.

El paso a 22,9 kV no se pierde (usuario, 2026-11-04: «verifica si está considerada la migración de alimentadores 10 kV a
22,9 kV»; la lista del oráculo se armaba sin el escalón de nivel de 042:RF-50):
- RF-41: EL SISTEMA medirá en DIgSILENT las variantes que el oráculo no sabe calcular (el paso a 22,9 kV por celda, por su fuente o con elevador, 042:RF-50 a RF-61) cuando las de RF-39 no cumplan, antes de transferir o trasladar.
- RF-42: EL SISTEMA no dará por buena una variante que deje sin servicio barras de media que lo tenían sin ella, en toda la red y no solo en los alimentadores medidos. Usuario (2026-11-04): «no debe haber separaciones o aislados».
- RF-43: EL SISTEMA guardará a la vez como mucho 64 redes factorizadas del oráculo, las de uso más reciente. Pisco entero (2026-11-04): sin tope, la web llegó a 6 GB y el trabajo cayó con MemoryError.
- RF-44: CUANDO se aplica la obra que eligió la evaluación, EL SISTEMA la aplicará sin volver a preguntar si «Con proyecto» ya cumple sin sorteos. Pisco (2026-11-04): CHI201 se dio por resuelto con su sección elegida y sin aplicarla.

El sistema entero, junto (usuario, 2026-11-04: «¿por qué DIgSILENT corre alimentador por alimentador y no todo el
sistema?»; «sí, implementa»):
- RF-45: CUANDO cada alimentador tiene su obra, EL SISTEMA confirmará en DIgSILENT el sistema entero, con todas las obras y todas las cargas nuevas activas, en un solo flujo por instante: con la máxima, en los sorteos y en valle, y sin barras aisladas (RF-42).
- RF-46: SI la confirmación conjunta no cumple, ENTONCES EL SISTEMA dirá de qué alimentadores son los motivos, con sus barras y tramos.
- RF-47: EL SISTEMA rehará la obra solo de los alimentadores de RF-46, con las cargas nuevas de los demás activas, y confirmará de nuevo, como mucho dos veces.
- RF-48: CUANDO se evalúa la obra del déficit previo (042:RF-64), EL SISTEMA leerá el grafo con la obra de la carga ya aplicada y medirá en DIgSILENT solo lo de RF-39 y RF-41. Pisco (2026-11-04): la de PA217 medía sus 55 variantes una a una.
- RF-49: EL SISTEMA aplicará 063:RF-33 solo a la obra cuyos sorteos lleguen a `escalera.sorteos_decide_no` (90 % si el perfil no lo da); por debajo, el alimentador seguirá con RF-41 y RF-31. Pisco (2026-11-04): CHI201 se daba por resuelto con el 60 % de sus sorteos; el usuario eligió «acotar la regla».
- RF-50: EL SISTEMA no reutilizará (025:RF-73) una evaluación medida con otro código de la escalera ni una con variantes que dieron error. Pisco (2026-11-04): corregido el traslado, se reutilizó el error de CHI201.
- RF-51: EL SISTEMA contará las pérdidas de varios alimentadores con cada carga una sola vez, volverá a leer la red tras borrar una variante que cambia la topología y no elegirá por 063:RF-33 una variante cuya medida dio error. Pisco (2026-11-04): la transferencia de CHI201 a SC215 salía con −37 151 al año y sin sorteos.
- RF-52: EL SISTEMA propondrá la transferencia, por cada vecino con margen, desde la barra de la troncal más cercana a él, entre las que van desde la que sale de límites hasta el final del camino de la carga. Pisco (2026-11-04): con un único nodo fijo, la de 189 m de CHI201 a SC215 dejaba de proponerse.
- RF-53: EL SISTEMA propondrá transferir o trasladar carga solo a un alimentador que opera: con demanda medida en su calibración. Pisco (2026-11-04): SC215 ya no opera y era el único vecino propuesto para CHI201.
- RF-54: EL SISTEMA propondrá un alimentador nuevo para la zona que no llega a `planificacion.set_nueva_desde_kw`, aunque sea la única zona, y dejará pedir la obra integral sin repetir la escalera ya hecha. Pisco (2026-11-04): los 0,66 MW de CHI201 iban a una SET nueva; usuario: «debería ir de frente a planteo de nuevos alimentadores».
- RF-55: CUANDO el oráculo busca dónde poner bancos en un alimentador con cargas nuevas, EL SISTEMA tomará como candidatas todas las barras de media del alimentador que existen sin las cargas nuevas, no solo la barra de cada carga. AL209 (2026-11-06), usuario: «la ubicación óptima de bancos se debe hacer en todo el alimentador AL209 […] usar los algoritmos avanzados»; la búsqueda bayesiana y el NSGA-II solo veían la barra de Cemento Inka.
- RF-56: SI las barras candidatas de un alimentador pasan de `escalera.candidatas_banco` (30 si el perfil no lo da), ENTONCES EL SISTEMA se quedará con las que más suben, según el oráculo con un módulo de banco en cada una, la tensión de las barras de sus cargas nuevas (y, a igualdad, las que más bajan las pérdidas), y conservará siempre la barra de banco de cada carga.
- RF-57: EL SISTEMA dirá en el registro del trabajo, por alimentador, cuántas barras de media tuvo, cuántas pasaron a la búsqueda y cuáles fueron.

## Requisitos no funcionales
- Determinismo: con la misma semilla, misma red y mismo perfil, el oráculo, Optuna, Markov y el árbol dan el mismo resultado.
- Universal: nada de este método depende de una empresa, sistema o tensión (constitución 13).
- Escala: nada fijado al número de alimentadores (constitución 2).
- Objetivo a comprobar con T13, no a dar por hecho: el «Con proyecto» de un mismo sistema, en menos de la mitad del tiempo de la escalera, con obras que cumplen igual en DIgSILENT.

## Casos límite
Oráculo con discrepancias sistemáticas (RF-3 y RF-6); alimentador sin curva de cabecera (042:RF-42), que se evalúa sin Markov; variante con 0 sorteos porque no cumple en la máxima; cancelación a mitad, que deja la fila de RF-21 con estado cancelado; una sola corrida (RF-26).

## Fuera de alcance
Decidir una obra sin DIgSILENT. Entrenar el piloto MADRL de la spec 074, que sigue por su cuenta. Sustituir el oráculo físico por un modelo aprendido. Programación no lineal de la spec 048.

## Criterios de finalización
Cada RF citado por una prueba (`grep -rnoE "087:RF-[0-9]+" tests | sort -u`), suite en verde, T13 y T14 hechas en DIgSILENT.

## Dudas abiertas
Ninguna: los umbrales se dan en el perfil y sus valores por defecto se anotan como supuestos (042:RF-39).
