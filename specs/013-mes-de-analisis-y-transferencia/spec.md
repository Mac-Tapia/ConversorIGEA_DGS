# Spec 013 — Mes de análisis y transferencia entre dos alimentadores

Estado: borrador · Fecha: 2026-10-13 · Origen: revisión de «2.3 Clientes importantes» del 2026-10-13

## Contexto y objetivo

El cruce de clientes importantes (spec 004, RF-34 a RF-37 y RF-43) lee **un solo** libro de
clientes, el que sube el operador, y la máxima de cabecera (RF-27) se busca en **todos** los
registros del libro de medición, que trae el año entero. Nada comprueba que los dos sean del
mismo mes. Caso real del 2026-10-13: CA101 da su máxima el 16/04/2026 y PE104 el
12/01/2026. Con el libro de clientes de abril, PE104 recibe los clientes de abril sobre una
máxima de enero. La empresa deja un libro por mes (`0126clientesImportantes.xlsb` …
`0726clientesImportantes.xlsx`, y uno más cada mes), y el operador tenía que saber cuál
subir.

Cuando el operador analiza dos alimentadores, lo hace para pasar carga de uno a otro (spec
011, «4.3 Transferencia de carga»). Para eso necesita ver la curva de carga de **cada uno**,
analizar los dos en el mismo mes —priorizando el alimentador más utilizado, no necesariamente
el de mayor kW absoluto— y saber al final cuánta carga pasó al otro alimentador y con qué
subestaciones de distribución (SED). Hoy la 011 da la carga transferida de cada paso
(RF-110, RF-112), pero no qué SED cambian de alimentador.

Esta spec cambia la 004 (RF-27, RF-34, RF-39 y RF-43) y amplía la 011 (RF-110, RF-112 y
RF-121). Los RF que cambia se citan en cada requisito.

## Usuarios / actores

Ingeniero de planificación, desde la web (pestaña de cargas, pasos 2 y 4.3).

## Historias de usuario

- H1: Como ingeniero quiero indicar la carpeta de los libros mensuales de clientes una
  sola vez, para no tener que elegir el libro que toca cada vez que cambio de mes.
- H2: Como ingeniero quiero que la máxima y los clientes sean del mismo mes, para que la
  demanda fija de los clientes corresponda a la máxima que reparto.
- H3: Como ingeniero que analiza dos alimentadores quiero que el mes propuesto sea el de la
  máxima utilización verificable, porque el mayor kW absoluto no identifica por sí solo el
  alimentador con menos margen para recibir una transferencia.
- H4: Como ingeniero quiero ver juntas las curvas de carga de los dos alimentadores, para
  ver cuándo coinciden sus puntas y cuánto margen tiene el que recibe.
- H5: Como ingeniero quiero saber al final cuánta carga se transfirió y qué SED pasaron al
  otro alimentador, para preparar la maniobra.

## Requisitos funcionales (EARS)

Libros mensuales de clientes (cambia 004:RF-34 y RF-39)

- RF-1: EL SISTEMA aceptará como fuente de clientes importantes una carpeta, además de un
  único libro.
- RF-2: CUANDO el operador indica la carpeta, EL SISTEMA tomará cada libro de clientes que
  haya en ella, en cualquiera de los dos formatos de 004:RF-34.
- RF-3: EL SISTEMA sacará el mes de cada libro de su nombre, con el patrón que dé el
  perfil de empresa.
- RF-4: SI el perfil no da patrón, o el nombre de un libro no casa con él, ENTONCES EL
  SISTEMA dejará ese libro «sin mes» y pedirá al operador que le asigne uno.
- RF-5: SI dos libros dan el mismo mes, ENTONCES EL SISTEMA usará el de modificación más
  reciente y lo avisará con los dos nombres.
- RF-6: CUANDO el operador vuelve a abrir la carpeta, EL SISTEMA tomará los libros que se
  hayan añadido desde la última vez.

Mes de análisis (cambia 004:RF-27 y RF-43)

- RF-7: EL SISTEMA ofrecerá un selector de mes en el paso 2, con los meses que tengan
  libro de clientes y registros en la cabecera de los alimentadores marcados.
- RF-8: CUANDO el operador busca la máxima de un solo alimentador, EL SISTEMA propondrá el
  mes de su máxima en todo el periodo.
- RF-9: CUANDO el operador busca la máxima de dos o más alimentadores, EL SISTEMA propondrá
  el mes que contenga la mayor utilización máxima verificable entre ellos. La utilización
  será `kVA medido / kVA admisible` solo cuando ambas magnitudes tengan origen y unidad
  verificados; no deducirá una capacidad ausente. Sin kVAR medido o sin capacidad admisible
  verificable, usará como respaldo el mayor kW máximo del periodo. EL SISTEMA mostrará el
  criterio usado. En empate de utilización elegirá el mayor kW; si también empatan, el
  instante más antiguo.
- RF-10: EL SISTEMA dejará al operador cambiar el mes propuesto.
- RF-11: MIENTRAS haya un mes elegido, EL SISTEMA buscará la máxima de cada alimentador
  marcado solo entre los registros de ese mes.
- RF-12: MIENTRAS haya un mes elegido, EL SISTEMA cruzará los clientes con el libro de ese
  mes.
- RF-13: SI el mes elegido no tiene libro de clientes, ENTONCES EL SISTEMA lo dirá y
  repartirá todas las SED por kVA, como hoy sin libro de clientes.
- RF-14: EL SISTEMA dará, junto a la máxima de cada alimentador en el mes elegido, su
  máxima en todo el periodo y el mes en que ocurrió.
- RF-15: SI el mes elegido no es el de la máxima del periodo de algún alimentador
  marcado, ENTONCES EL SISTEMA lo avisará con el alimentador y los dos meses, sin
  bloquear.
- RF-16: EL SISTEMA dirá en el resultado del cruce de qué libro y de qué mes salieron los
  clientes.
- RF-17: EL SISTEMA ofrecerá también «todo el periodo», que busca la máxima como 004:RF-27
  y avisa de que los clientes son de un solo mes.

Curvas de los alimentadores

- RF-18: CUANDO hay dos o más alimentadores marcados con máxima, EL SISTEMA mostrará a la
  vez una curva de carga por alimentador, sin que el operador tenga que cambiar de uno a
  otro.
- RF-19: EL SISTEMA dibujará las curvas de los alimentadores marcados con el mismo eje de
  tiempo.
- RF-20: EL SISTEMA marcará en cada curva su máxima del mes elegido.
- RF-21: EL SISTEMA mostrará de entrada en las curvas el mes elegido.

Resultado de la transferencia (amplía 011:RF-110, RF-112 y RF-121)

- RF-22: EL SISTEMA podrá ajustar cada alimentador a su propia máxima del mes en el paso 2,
  pero no sumará esas máximas independientes para estudiar una transferencia. Para cada
  sentido partirá de un instante común del mes elegido y ajustará ambos alimentadores a sus
  registros de cabecera de ese mismo instante.
- RF-23: EL SISTEMA dará por sentido y por enlace la carga transferida al alimentador que
  recibe en la configuración viable más lejana (011:RF-112), en kW y kVA.
- RF-24: EL SISTEMA dará por sentido y por enlace la lista de SED que pasan al alimentador
  que recibe en esa configuración, con la demanda de cada una en kW y kVA.
- RF-25: EL SISTEMA dará la carga de la cabecera de cada alimentador antes y después de
  transferir.
- RF-26: EL SISTEMA guardará la lista de SED transferidas en el fichero descargable de
  011:RF-121, en una hoja aparte.
- RF-27: EL SISTEMA cruzará las curvas por instantes comunes válidos, sin interpolar ni
  inventar registros ausentes. Para cada sentido examinará los estados coincidentes del mes
  y seleccionará mediante PowerFactory el que deje la menor transferencia viable.
- RF-28: EL SISTEMA informará el instante crítico, la cobertura temporal examinada, el
  criterio de selección y los registros de cabecera de ambos alimentadores usados en ese
  estado.
- RF-29: SI no existen instantes comunes válidos, o PowerFactory no verifica todos los
  candidatos necesarios para afirmar el resultado, ENTONCES EL SISTEMA bloqueará la
  aceptación de la transferencia y explicará qué evidencia falta. Un resultado parcial no
  se presentará como capacidad de transferencia comprobada.

## Requisitos no funcionales

- Universal (P13): el patrón del nombre de los libros (`MMAA` + `clientesImportantes` en
  Electro Dunas) va en el perfil de empresa, no en el código.
- Escala (P2): cualquier número de libros en la carpeta y de alimentadores marcados; las
  pruebas sortean cuántos.
- Nada largo dentro de una petición (P7): leer la carpeta y buscar las máximas son
  trabajos en cola, con progreso. Los libros de enero a abril pesan unos 150 MB cada uno:
  solo se abre el del mes elegido, no los siete.
- Cálculo temporal auditable: todos los instantes comunes empezarán como candidatos. Para
  un sentido, un instante solo podrá marcarse como dominado si otro tiene simultáneamente
  kW y valor absoluto de kVAR no menores tanto en el donante como en el receptor; si falta
  algún kVAR, no se descartará por dominancia. El informe guardará el instante dominante de
  cada descarte y PowerFactory verificará todos los no dominados. Cualquier otra reducción
  o límite de candidatos dejará el resultado parcial conforme a RF-29.
- Datos de la distribuidora (P9): los libros de `referencia/4.-clientesimportantes` solo
  los leen las pruebas por variable de entorno.

## Casos límite

- Carpeta vacía, o sin ningún libro de clientes reconocible.
- Libro mensual con la hoja «resumen» vacía, o en un formato distinto al de su vecino
  (abril `Nis/EA/ERI/Pot`, mayo `SUMINISTRO/EA_TOTAL/…`).
- Mes con libro de clientes pero sin registros de cabecera de un alimentador marcado, o al
  revés.
- Dos alimentadores con la misma máxima en meses distintos (empate en RF-9).
- Mes a medias: el último mes de la medición tiene registros solo de unos días.
- Libro añadido a la carpeta mientras hay un trabajo en marcha.
- Transferencia en la que ninguna SED cambia de alimentador (el primer paso ya no es
  viable, 011:RF-116).

## Fuera de alcance

- Elegir un mes distinto para cada alimentador.
- Análisis de varios meses a la vez, o una curva anual por SED.
- Descargar los libros del sistema comercial: la carpeta la mantiene el operador.
- Cambiar cómo se reparte la máxima entre las SED (spec 006).

## Criterios de finalización

Cada RF citado por al menos una prueba (`grep -rnoE "013:RF-[0-9]+" tests | sort -u`); la
suite en verde con los datos reales y la carpeta de clientes; y RF-22 a RF-29 probados en
DIgSILENT con CA101 y PE104. La aceptación nativa incluirá el fichero descargable, la
relectura de sus resultados y evidencia de que ambos alimentadores se simularon en el mismo
instante.

## Decisiones cerradas (aprobadas el 2026-10-13)

- El mes propuesto se decide por porcentaje de utilización cuando la capacidad es
  verificable; el mayor kW es respaldo explícito, no una capacidad supuesta.
- Las máximas mensuales independientes sirven para el ajuste individual del paso 2, pero
  no forman un estado de transferencia. La transferencia usa registros coincidentes y
  busca por sentido el estado temporal más restrictivo.
- No se interpola una curva para fabricar coincidencia. Sin registros comunes o sin
  verificación nativa suficiente, la aceptación queda bloqueada.

## Fundamento científico

Estas fuentes sustentan la decisión de conservar la dimensión temporal, distinguir máxima
coincidente de suma de máximas individuales y verificar la reconfiguración bajo demanda
variable. La regla concreta RF-9 y el contrato fail-closed RF-29 son decisiones de diseño de
esta aplicación derivadas de esos principios, no citas literales de las fuentes.

- Erickson, G. D. (1980), *Peak demand cost management through load control*, tesis de
  maestría en Ingeniería Eléctrica, University of Tennessee. Distingue la máxima coincidente
  de la suma de máximas individuales y muestra el efecto de la diversidad de carga:
  <https://trace.tennessee.edu/handle/20.500.14382/37180>.
- Ding, F. (2015), *Smart Distribution System Automation: Network Reconfiguration and
  Energy Management*, tesis doctoral, Case Western Reserve University. Formula la
  reconfiguración dinámica considerando demanda variable en el tiempo:
  <http://rave.ohiolink.edu/etdc/view?acc_num=case1417291114>.
- Mahdavi, M., Haes Alhelou, H., Siano, P. y Loia, V. (2022), «A Robust Mixed-Integer
  Programming Model for Reconfiguration of Distribution Feeders Under Uncertain and
  Variable Loads Considering Capacitor Banks, Voltage Regulators, and Protective Relays»,
  *IEEE Transactions on Industrial Informatics*, DOI 10.1109/TII.2022.3141412:
  <https://doi.org/10.1109/TII.2022.3141412>.
- Azizivahed, A. et al. (2018), «Multi-objective dynamic distribution feeder
  reconfiguration in automated distribution systems», *Energy*, 147, 896–914. Extiende la
  reconfiguración a múltiples intervalos con cargas variables:
  <https://doi.org/10.1016/j.energy.2018.01.111>.
