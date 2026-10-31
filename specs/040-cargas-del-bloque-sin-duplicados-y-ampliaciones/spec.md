# Spec 040 — Cargas del bloque sin duplicados, y ampliaciones de clientes existentes

Estado: cumplida · Fecha: 2026-10-31 · Origen: revisión de NA203 + NA205 en DIgSILENT con el
usuario, 2026-10-31 («antes de implementar las nuevas cargas en digsilent primero debes revisar y
verificar si existe o no existe esa carga nueva en físico digsilent ya sea por ubicación, nombre o
siglas»; «las cargas nuevas son algunas ampliación de potencia en el mismo punto del cliente
existente … esos casos no se debe considerar duplicado, eliminar los duplicados»)

## Contexto y objetivo

El libro de cargas nuevas de NA203 + NA205 (29-10, 36 filas de esos alimentadores) se insertó
sin que nada detectara:

- Filas repetidas en el mismo alimentador: «Fundo Luciana» y «SU Fundo Luciana…», «YANACA» y
  «PREDIO SUBLOTE N°01-FUNDO YANACA», en el mismo punto y con la misma potencia. Se crearon dos
  SED, dos líneas y dos variaciones por cliente; «Con proyecto» sumaba cada una dos veces.
- Ampliaciones de clientes que ya existen: «Cesar Alberto Monge Marquez SE50324» a 3 m de la
  SED SE50324, que está en la tabla de CARGA cruzada con su SEC; HONGWEN a 1 m de SE50323;
  «AGROPEX SAC 250 A 1000KW» a 26 m de SE50150. El libro da el incremento (750 kW = 1000 − 250),
  y se creó una SED nueva con transformador y cable junto a la que ya existía.

014:RF-27 a RF-30 solo reconocen una carga por su nombre exacto o a 1 m de otra carga **nueva**
ya creada: ni comparan las filas del libro entre sí ni las SED de la red.

Una fila del libro es, en su alimentador, una de tres cosas: **duplicada** de otra fila (no se
crea y, si ya estaba creada, se elimina), **ampliación** de un cliente existente (no es
duplicada: se suma su incremento en la SED que ya tiene, y se propone el transformador
adecuado) o **nueva** (spec 007, como hasta ahora).

## Requisitos funcionales (EARS)

Filas repetidas en el libro

- RF-1: ANTES de crear las cargas nuevas, EL SISTEMA tratará como la misma carga dos filas del
  libro con el mismo alimentador y a 1 m o menos una de otra: creará la primera, no creará las
  demás y el informe dirá de cada una de cuál es duplicada.
- RF-2: Dos filas en el mismo punto con alimentadores distintos en el libro no son duplicadas:
  cada una va al alimentador que dice el libro (usuario, 2026-10-31: «según el libro a qué
  alimentador pertenece»; MINERA PECAN en NA203 y en NA205).

Ampliaciones de clientes existentes

- RF-3: EL SISTEMA tratará una fila como ampliación de una SED existente de su alimentador
  cuando una palabra del nombre de la fila sea el nombre de esa SED, a cualquier distancia, o
  cuando su punto esté a 30 m o menos de la barra de baja de esa SED (usuario, 2026-10-31).
  Con varias a 30 m o menos, la más cercana. Una carga nueva creada antes por el sistema no
  cuenta como SED existente.
- Aclaración de RF-3: una fila que se llama exactamente como una SED existente es esa SED y
  sigue 004:RF-15 («ya existe en el alimentador»); RF-3 es para una palabra dentro del nombre.
- RF-4: CUANDO una fila es ampliación, EL SISTEMA no creará SED, transformador, línea ni barra,
  ni partirá un tramo: creará en su propia variación de carga nueva (007:RF-9, RF-10) una
  carga con la potencia de la fila en la barra de baja de la SED existente, y la medirá como
  cualquier carga nueva (007:RF-11 a RF-13).
- RF-5: CUANDO la SED de una ampliación, con lo que consume su carga en «Sin proyecto» más el
  incremento de la fila, pase del umbral de carga del perfil, EL SISTEMA propondrá en el
  informe el transformador de ficha que la deja en el umbral o por debajo (020:RF-6 a RF-11),
  sin aplicarlo.

Eliminar lo duplicado que ya se creó

- RF-6: SI una variación de carga nueva guarda una fila que es duplicada (RF-1), o una ampliación
  que se creó como SED nueva, ENTONCES EL SISTEMA la desactivará en todos los casos, la
  eliminará del proyecto y el informe la listará en «eliminadas»; al simular, solo la listará.
- RF-7: SI la misma carga está en más de una variación de carga nueva, ENTONCES EL SISTEMA
  conservará la primera por su nombre, eliminará las demás con RF-6 y reutilizará la que
  conserva (014:RF-24). Cambia 014:RF-26.
- RF-8: EL SISTEMA solo eliminará variaciones de carga nueva (`Carga_…`, 007:RF-10): nunca
  una del operador, de un ajuste o del catálogo.
- RF-9: EL SISTEMA dirá en los avisos del informe cada fila duplicada, cada ampliación con su
  SED, su criterio y su propuesta de transformador, y cada variación eliminada.

Variaciones que reconocer por su alimentador

- RF-10: EL SISTEMA nombrará la variación de una carga nueva `Carga_<SED>_<alimentador>_<sello>`
  recortando el nombre de la SED, nunca el alimentador ni el sello, para no pasar de 40
  caracteres (simulación de NA203 + NA205, 2026-10-31: «Carga_SU_Predio_3H_MINING_GROUP_SAC_NA20»
  había perdido NA203, y 13 cargas ya creadas se iban a crear otra vez).
- RF-11: SI el nombre de una variación de carga nueva ya no dice su alimentador, ENTONCES EL
  SISTEMA la tomará como del alimentador de la SED existente más cercana a su carga y, al
  reutilizarla, la renombrará como en RF-10 y lo dirá en un aviso.
- RF-12: EL SISTEMA reconocerá por su nombre una carga nueva que DIgSILENT guardó recortada para
  añadirle el sufijo «(n)» (amplía 014:RF-29): «Cesar_Alberto_Monge_Marquez_SE5032(2)» es la
  fila «Cesar Alberto Monge Marquez SE50324» (NA203, 2026-10-31); sin esto se buscaba por el
  punto y se tomaba la variación de otra fila del mismo sitio.

## Relación con otras specs

- RF-7 cambia 014:RF-26 (antes, con la carga en dos variaciones no se tocaba ninguna).
- RF-3 se mira antes que 014:RF-30: una fila a 30 m de una SED existente es esa SED, aunque
  también esté a 1 m de una carga nueva creada antes como SED aparte (que RF-6 elimina).
- RF-5 usa las fichas del perfil de empresa (`calibracion.transformadores_sed`, 020:RF-31),
  igual que la calibración; sin ellas, el umbral es el 100 % y la propuesta dice por qué falta.

## Fuera de alcance

- Cambiar el transformador de la SED de una ampliación: se propone; se aplica desde la web
  como las SED sobrecargadas de la calibración (spec 020).
- Leer el NIS de un cliente en el nombre de la fila: la red de DIgSILENT no guarda el NIS de los
  clientes, solo el nombre de su SED.

## Criterios de finalización

- `grep -rnoE "040:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-12.
- NA203 + NA205 cargado de nuevo desde la web: sin la segunda Fundo Luciana ni la segunda
  YANACA; Cesar Monge, HONGWEN y AGROPEX como ampliaciones de SE50324, SE50323 y SE50150; las
  variaciones que sobraban, eliminadas.
