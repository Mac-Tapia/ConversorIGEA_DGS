# Spec 052 — Optimización de «Con proyecto» con el oráculo y confirmación en DIgSILENT

Estado: cumplida (2026-11-08: tareas cerradas por orden del usuario, sin corrida propia; su aceptación pasa a la spec 100) · Fecha: 2026-11-01 · Origen: petición del usuario, 2026-11-01, al ver que la
optimización de NA203 + NA205 tardaba unas 3 horas («esto debes modificar, no debería demorar
tanto»; «antes, siempre las convergencias deben pasar por el oráculo, después lanzarlo en
DIgSILENT en cualquier caso»; «igual debes hacer la optimización junto con el oráculo; la
escalera así pierde tiempo»; «no debería fallar la implementación; debe ser robusto, preciso y
los arneses bien hechos»).

## Contexto y objetivo

La optimización de la spec 042 busca cuántas cargas nuevas caben en la red existente y con qué
obra, probando en DIgSILENT cada variante de la escalera (025) para cada número de cargas. Cada
variante cuesta de 20 a 85 s en DIgSILENT (crear la variación, la obra, el flujo y borrarla); en
NA203 + NA205 son 20 y 40 variantes por prueba, y una prueba que no cabe las recorre todas: unos
60 min por prueba y unas 3 h por optimización.

El gemelo digital (spec 024) ya tiene un flujo físico por matriz de admitancias
(`digital_twin/flujo.py`, la base de la PINN; 0,003 pu frente a DIgSILENT en IN111–TA225) y lee
de DIgSILENT el grafo eléctrico de la red. Con él, cada variante con cada número de cargas se
calcula en milisegundos. La spec 024 ya lo pide (RF-35): el oráculo propone y DIgSILENT confirma
antes de aceptar.

Esta spec hace la optimización con el oráculo y deja a DIgSILENT la confirmación: el oráculo
busca el número de cargas que caben y la obra de menor costo; DIgSILENT confirma siempre esa
obra con esas cargas y el límite (que con una carga más no cabe), y si discrepa, manda
DIgSILENT.

## Requisitos funcionales (EARS)

- RF-1: AL empezar la optimización, EL SISTEMA leerá una sola vez de DIgSILENT, en «Con
  proyecto», el grafo eléctrico (el de la spec 024) con todas las cargas nuevas activas y, por
  cada carga nueva, su barra en el grafo y su P y Q, identificada por su variación (índice de la
  spec 040), junto con la troncal y las barras de media de la escalera.
- RF-2: EL SISTEMA aplicará cada obra de una variante sobre una copia del grafo, sin tocar
  DIgSILENT: banco, su Q en su barra; nueva terna, un circuito igual en paralelo en sus tramos;
  cambio de sección, la R y la X del conductor nuevo por el largo de cada tramo; regulador, la
  tensión de su consigna aguas abajo de su tramo, dentro de su rango.
- RF-3: EL SISTEMA calculará con el flujo físico del oráculo cada variante con las k primeras
  cargas activas (las demás, sin su demanda), en la máxima y en los sorteos de la escalera, con
  el mismo criterio de cumplimiento de la escalera (025:RF-50: tensión de cada carga nueva,
  nada peor que «Sin proyecto», cargabilidad).
- RF-4: EL SISTEMA buscará con el oráculo el mayor k que cabe, galopando desde abajo y afinando
  (042:RF-2), y para esas k la variante de menor costo anual entre las que cumplen.
- RF-5: EL SISTEMA confirmará siempre en DIgSILENT, en cualquier caso: la variante elegida con
  las k cargas (máxima y sorteos) y, si k < n, que con k + 1 cargas no cumple ninguna de las
  variantes que el oráculo dio como más cercanas. Solo lo confirmado en DIgSILENT se aplica.
- RF-6: SI DIgSILENT no confirma la elegida, ENTONCES EL SISTEMA probará en DIgSILENT las
  siguientes en el orden del oráculo hasta la primera que cumpla, y si ninguna, bajará k; SI con
  k + 1 cumple en DIgSILENT, ENTONCES subirá k. Cada discrepancia se anota.
- RF-7: EL SISTEMA registrará por cada variante confirmada lo que predijo el oráculo y lo que
  midió DIgSILENT (tensión de cada carga nueva y si cumple) en el informe y como episodio del
  gemelo (spec 024), para medir y mejorar el oráculo.
- RF-8: SI no se puede leer el grafo o el flujo físico no converge sin obras, ENTONCES EL SISTEMA
  lo dirá y hará la búsqueda en DIgSILENT como en la spec 042 (galope y «basta una»); nada se
  bloquea.
- RF-9: EL SISTEMA no supondrá nada de una empresa: tensiones, cumplimiento, sorteos, costos y
  tamaño de banco salen del perfil y del libro CAPEX, como en la escalera.
- RF-10: EL SISTEMA dirá cuánto tardó cada parte (oráculo y confirmación en DIgSILENT) y cuántas
  variantes se calcularon en cada uno.

Añadido el 2026-11-01, a petición del usuario («la optimización debería demorar, es una búsqueda
óptima»; «puedes usar los bayesianos, decisiones de Markov, cadenas de Markov, teoría de juegos,
algoritmos avanzados de búsqueda y optimización; usa los módulos que ya se tienen»):

- RF-11: EL SISTEMA buscará con el oráculo, además de las variantes de la escalera, combinaciones
  de obras (módulos de banco por barra candidata y, por tramo de la troncal, nada, terna o cambio
  de sección) con búsqueda bayesiana, dentro del número de evaluaciones que dé el perfil.
- RF-12: CUANDO la búsqueda bayesiana encuentre una combinación que cumple y cuesta menos que la
  mejor variante de la escalera, EL SISTEMA la pondrá primera en la lista que confirma DIgSILENT.
- RF-13: EL SISTEMA dará el frente de Pareto (costo anual, pérdidas y tensión mínima) de las
  combinaciones que cumplen, con el algoritmo evolutivo multiobjetivo del gemelo, y marcará en
  él la elegida.
- RF-14: EL SISTEMA sorteará la demanda existente con una cadena de Markov de la curva de cabecera
  del año —estados por nivel de demanda, transición entre instantes consecutivos—, con la misma
  cantidad de sorteos y la misma semilla de la escalera, y dirá la probabilidad estacionaria de
  cada nivel.
- RF-15: EL SISTEMA repartirá el costo anual de la obra elegida entre las k cargas nuevas que caben
  por su valor de Shapley, siendo el costo de un grupo de cargas el de la variante más barata que
  cumple con ellas, estimado por permutaciones sorteadas con la semilla de la escalera.
- RF-16: SI la búsqueda bayesiana, el frente o el reparto agotan su presupuesto de evaluaciones,
  ENTONCES EL SISTEMA dará lo mejor encontrado y lo dirá con cuántas evaluaciones usó.
- RF-17: DONDE haya un PINN promovido (spec 024) y la red de la variante esté dentro de su
  dominio, EL SISTEMA usará su tensión para el criterio, y si no, la del flujo físico; cada medida
  dirá qué oráculo la dio (usuario, 2026-11-01: «recuerda que son dos oráculos, puedes usar
  también el PINN»).
- RF-18: ANTES de crear la SET nueva de la 042, EL SISTEMA la comprobará con el oráculo: las ramas
  trasladadas abiertas en su tramo de entrada y alimentadas desde la SET (una fuente por rama, con
  la línea desde el punto elegido a su distancia GPS y la impedancia por km del tramo abierto),
  con todas las cargas nuevas y la obra elegida, con el criterio de la escalera; dirá si cumple y
  DIgSILENT la confirma al crearla (usuario, 2026-11-01: «el oráculo ya debió determinar esa
  solución»).
- RF-19: EL SISTEMA nombrará la SET nueva y sus objetos en DIgSILENT con el nombre que dé el
  operador (en NA203 + NA205, «SET COPARA»); sin nombre, «SET_NUEVA».
- Aclaración de RF-7: lo predicho y lo medido de cada variante confirmada va al informe y a
  `oraculo_con_proyecto_<fecha>.json` de la salida; el episodio del gemelo con relectura nativa
  sigue en la spec 024, que es la que hace esa relectura.

## Relación con otras specs

- Hace la búsqueda de la 042 (RF-1 a RF-4) con el oráculo de la 024 (RF-35, RF-64 a RF-66).
- Usa las variantes, el criterio, los sorteos y los costos de la escalera de la 025.
- Identifica las cargas nuevas por su variación con el índice de la 040.

## Fuera de alcance

- Un proceso de decisión de Markov para el orden de conexión de las cargas: el orden lo fija la
  042 (de mayor a menor potencia, usuario 2026-10-31); otro orden contradiría esa decisión.
- La asignación de cargas por programación entera mixta con flujo linealizado: es de la spec 048.

- Entrenar la PINN: aquí se usa su base física; el aprendizaje sigue en la 024.
- El diseño de la SET nueva (042:RF-5 a RF-12): aquí solo se comprueba con el oráculo y se nombra.

## Criterios de finalización

- `grep -rnoE "052:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-19.
- NA203 + NA205 optimizado desde la web en menos de 20 min, con la elegida y el límite
  confirmados en DIgSILENT y la comparación oráculo–DIgSILENT en el informe.
