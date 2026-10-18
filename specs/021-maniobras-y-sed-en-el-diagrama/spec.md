# Spec 021 — Maniobras en el extremo de la línea, SED unidas a su barra, curvas de todos los alimentadores y central térmica en la calibración

Estado: aprobada (2026-10-17; RF-50 a RF-53 añadidos el mismo día) · Fecha: 2026-10-17

## Contexto y objetivo

En el diagrama de `20261016-160231_IGEA_NA203_NA205` (vía Access, 260924.mdb) aparecen
grupos de tres y cuatro puntos negros en menos de 1 m donde en campo hay una derivación
con fusibles. La causa no es un hueco del archivo: CYMDIST cuelga cada seccionador o
fusible de un tramo puente `DEFAULT` de unos 2 m, y el conversor funde el tramo pero deja
el equipo como `ElmCoup` entre dos barras (`puentes.py`). En EQ_1080_320414/15/16 eso da
línea → barra 432 → EQ_320415 → barra 431 → EQ_320416 → barra 433 → línea, y de la 431
sale EQ_320414 hacia la barra 1004 del trafomix M50226, que se excluye y deja la barra
sin nada. En el DGS de NA203 + NA205 hay 550 `ElmCoup` así: 464 extremos caen en una
barra que solo tiene una línea más, 88 en una barra sin nada y 119 barras están hechas
solo de acopladores. PowerFactory modela un seccionador en el extremo de una línea como
`StaSwitch` en su cubículo, sin barra propia: el cable queda corrido y la maniobra sigue
ahí.

En la misma red, la SED SE50195 se dibuja como triángulo (`SecSubProd`) sobre su barra
exterior NODE_2010_330217_SE50195, pero sin ninguna conexión dibujada entre los dos: al
mover la SED a mano en DIgSILENT, la barra y el fusible EQ_1080_875778 se quedan donde
estaban y el cable queda suelto. Pasa en toda SED, porque `dgs.py` escribe el triángulo
sin `IntGrfcon`.

Por último, en la web, el ajuste a la máxima con dos o más alimentadores dibuja la curva
del medidor de cabecera de uno solo y obliga a cambiarla en un desplegable: no se ve si
las máximas coinciden en el tiempo.

NA205 tiene una central térmica en serie en su troncal (en DIgSILENT, «NA203 NA205v1»:
GENERADOR NASCA, 9,9 MVA, en una barra de 22,9 kV con «Llegada de C. G.» desde la SET y
«Salida de C. G.» hacia la carga). El libro de medidores la trae como tres «alimentadores»
que no son de la red: CTBarra (CT_BH4 NA, la generación), CTLADOSET (CTNA_BH2, la
llegada) y CTLADOCARGA (CTNA_BH1, la salida). En sus registros de 2026 se cumple
BH4 = BH1 + BH2 (mediana −5 kW), y cabecera NA205 + BH2 da la demanda entre la SET y la
central (mediana 849 kW). Hoy el ajuste toma la máxima de cabecera de NA205 (2026-08-21
00:15, 10 585 kW) con la central parada (BH4 = −111 kW); la máxima demanda real es la del
2026-08-20 16:45, 10 753 kW, con la central dando 9 605 kW y solo 1 123 kW por la
cabecera. Los archivos de IGEA no traen la central: los proyectos que crea el conversor
no la tienen.

El objetivo es un diagrama sin barras de relleno, con las SED unidas a su barra, una
curva por alimentador en la misma gráfica y una calibración que tenga en cuenta la
central de un alimentador, con sus curvas a la vista.

## Usuarios / actores

Ingeniero de planificación que importa el DGS en DIgSILENT PowerFactory 2024 y trabaja
sobre su diagrama; el mismo ingeniero en la web, en el ajuste a la máxima (spec 006, 015).

## Historias de usuario

- H1: Como ingeniero quiero que un fusible o seccionador en el extremo de una línea no
  añada barras, para que el diagrama muestre el cable corrido como en campo.
- H2: Como ingeniero quiero que la SED quede unida a su barra en el diagrama, para poder
  moverla sin que el cable quede suelto.
- H3: Como ingeniero quiero ver juntas las curvas de cabecera de todos los alimentadores
  que calibro, para saber si sus máximas coinciden.
- H4: Como ingeniero quiero declarar la central térmica de un alimentador con sus tres
  medidores, para que la calibración use la demanda real y no solo lo que pasa por la
  cabecera.
- H5: Como ingeniero quiero ver las curvas de la central junto a la de cabecera, para
  saber cuándo genera y qué instante se calibra.

## Requisitos funcionales (EARS)

Maniobras de los tramos puente

- RF-1: CUANDO funde un tramo puente con un equipo de maniobra y uno de sus extremos es
  una barra a la que solo llega otra línea, EL SISTEMA escribirá el equipo como
  `StaSwitch` en el cubículo de esa línea del lado de la barra, en vez de como `ElmCoup`.
- RF-2: CUANDO aplica RF-1, EL SISTEMA fundirá en una sola las dos barras del tramo puente.
- RF-3: EL SISTEMA conservará en el `StaSwitch` el nombre, el estado normal (abierto o
  cerrado) y el uso (interruptor, seccionador, fusible) que tenía el equipo en la base.
- RF-4: SI el cubículo de la línea ya lleva un equipo de maniobra, ENTONCES EL SISTEMA
  dejará el equipo del puente como `ElmCoup`, como hasta ahora.
- RF-5: SI los dos extremos del puente cumplen RF-1, ENTONCES EL SISTEMA pondrá el equipo
  en la línea del lado de aguas arriba (el `FromNode` del puente).
- RF-6: MIENTRAS una barra está hecha solo de acopladores y cada uno de ellos cumple RF-1
  por su otro extremo, EL SISTEMA dejará un solo punto donde antes había varias barras
  (el caso EQ_1080_320415/16).
- RF-7: CUANDO la exclusión del trafomix deja una barra a la que solo llega un
  `ElmCoup`, EL SISTEMA no escribirá ni esa barra ni ese `ElmCoup`.
- RF-8: CUANDO aplica RF-7, EL SISTEMA contará cada equipo quitado en el informe de la
  exclusión del trafomix, con su nombre.
- RF-9: EL SISTEMA mantendrá el control de completitud: las maniobras de entrada son la
  suma de `StaSwitch`, `ElmCoup` de red y equipos quitados por RF-7.
- RF-10: EL SISTEMA aplicará RF-1 a RF-9 desde las reglas del proyecto, en toda
  conversión (TXT, MDB, VNR-GIS; un alimentador o la red unida).
- RF-11: DONDE las reglas son `SIN_REGLAS`, EL SISTEMA escribirá los puentes como hasta
  ahora.

SED unidas a su barra

- RF-12: EL SISTEMA dibujará cada SED unida en el diagrama a la barra de la que cuelga,
  de modo que al moverla en DIgSILENT la conexión la siga.
- RF-13: EL SISTEMA no cambiará con RF-12 la red eléctrica de la SED: el mismo
  transformador, las mismas barras de MT y BT y la misma carga.
- RF-14: CUANDO una SED cuelga de un fusible de derivación que cumple RF-1, EL SISTEMA
  dejará línea, fusible y SED como un solo trazo continuo hasta el triángulo (el caso
  SE50195 con EQ_1080_875778).

Estudios que leen las maniobras

- RF-15: EL SISTEMA seguirá reconociendo como punto de maniobra en la transferencia de
  carga (011:RF-112 a RF-118) a un seccionador escrito como `StaSwitch` por RF-1.
- RF-16: EL SISTEMA seguirá contando un seccionador escrito por RF-1 en el trecho del
  conductor del informe de estudio (017) y en el oráculo del «Caso base» (015).

Curvas de cabecera de varios alimentadores

- RF-17: MIENTRAS el ajuste a la máxima tiene dos o más alimentadores con máxima, EL
  SISTEMA dibujará en una sola gráfica la curva del medidor de cabecera de cada uno, con
  el mismo eje de tiempo.
- RF-18: EL SISTEMA dará a cada alimentador un color distinto y una leyenda con su nombre
  y su medidor.
- RF-19: EL SISTEMA marcará la máxima de cada alimentador con un punto de su color.
- RF-20: CUANDO el operador arrastra sobre la gráfica, EL SISTEMA ampliará ese tramo en
  todas las curvas a la vez.
- RF-21: CUANDO el operador pulsa un alimentador en la leyenda, EL SISTEMA ocultará o
  mostrará su curva, sin pedirla de nuevo al servidor.
- RF-22: MIENTRAS un alimentador tiene varios medidores, EL SISTEMA dibujará el que el
  operador eligió como cabecera, o el primero mientras no elija.
- RF-23: SI la curva de un alimentador no se puede leer, ENTONCES EL SISTEMA dibujará las
  demás y dirá en la leyenda cuál falta y por qué.
- RF-24: MIENTRAS hay un solo alimentador, EL SISTEMA mostrará la gráfica como hasta ahora
  (006:RF-32 a RF-38).

Central térmica en un tramo: declaración y medidas

- RF-25: DONDE el operador declara una central en un alimentador, EL SISTEMA le pedirá tres
  medidores (generación, llegada desde la SET y salida hacia la carga) y el nodo del
  troncal donde está la barra de la central.
- RF-26: EL SISTEMA ofrecerá como medidores de la central los del libro de medidores cuyo
  alimentador no es ninguno de la red, sin suponer nada por su nombre.
- RF-27: DONDE el perfil de empresa guarda la central de un alimentador, EL SISTEMA la
  propondrá ya rellena, y el operador podrá cambiarla.
- RF-28: EL SISTEMA comprobará en cada registro el balance de la barra de la central:
  generación = salida + llegada.
- RF-29: EL SISTEMA deducirá el signo de la llegada y de la salida como la combinación que
  deja la menor mediana de desbalance de RF-28.
- RF-30: SI la mediana del desbalance de RF-29 supera el 5 % de la generación máxima,
  ENTONCES EL SISTEMA avisará con esa mediana y no calibrará con la central.
- RF-31: EL SISTEMA calculará en cada registro la demanda de la zona aguas arriba como
  cabecera + llegada, y la de aguas abajo como la salida, con los signos de RF-29.
- RF-32: SI la zona aguas arriba de un registro queda a más de 3 rangos intercuartílicos de
  su mediana, ENTONCES EL SISTEMA no usará ese registro para la máxima y contará cuántos
  descartó (en NA205, 532 de 23 751: maniobras o transferencias).
- RF-33: MIENTRAS un alimentador tiene central, EL SISTEMA tomará como objetivo el registro
  de mayor demanda (aguas arriba + aguas abajo), no el de mayor kW de cabecera.
- RF-34: EL SISTEMA mostrará en la máxima de un alimentador con central: fecha, demanda,
  cada zona, generación, cabecera y la máxima de cabecera que se usaba antes.

Central térmica en la calibración

- RF-35: CUANDO calibra un alimentador con central, EL SISTEMA creará en «Sin proyecto» un
  generador estático en el nodo declarado, con la P y Q de la generación del registro
  objetivo.
- RF-36: SI en ese nodo ya está el generador que creó el sistema, ENTONCES EL SISTEMA solo
  le escribirá la P y Q, sin crear otro.
- RF-37: EL SISTEMA no tocará el «Caso base»: la central pasa a «Con proyecto» como parte de
  su copia (014).
- RF-38: SI el nodo declarado no está en el troncal del alimentador en DIgSILENT, ENTONCES
  EL SISTEMA rechazará el plan nombrando el nodo y el alimentador.
- RF-39: EL SISTEMA separará las cargas del alimentador en las de aguas arriba y las de
  aguas abajo del nodo de la central.
- RF-40: EL SISTEMA ajustará las cargas escaladas de aguas abajo con un factor de escala
  propio hasta que el flujo en la salida dé la medida de la salida.
- RF-41: EL SISTEMA ajustará las cargas escaladas de aguas arriba con otro factor de escala
  hasta que el flujo de cabecera + llegada dé la medida de la zona aguas arriba.
- RF-42: EL SISTEMA mantendrá las cargas fijas (clientes importantes) con su P y Q en la
  zona en la que estén (015).
- RF-43: EL SISTEMA dará la calibración por cuadrada solo si las dos zonas quedan dentro de
  la tolerancia.
- RF-44: EL SISTEMA dirá en el informe de la calibración: P y Q escritas en la central, lo
  que da en el flujo, el factor de cada zona y la cabecera calculada frente a la medida.
- RF-45: SI una zona no tiene cargas escaladas, ENTONCES EL SISTEMA dejará sus fijas como
  están y avisará de que esa zona no se puede ajustar.
- RF-46: MIENTRAS un alimentador no tiene central declarada, EL SISTEMA calibrará como hasta
  ahora (006, 015).

Curvas de la central en la web

- RF-47: DONDE un alimentador tiene central, EL SISTEMA dibujará en la gráfica de RF-17,
  además de la cabecera, la generación, la llegada, la salida y la demanda calculada.
- RF-48: EL SISTEMA marcará en la gráfica la máxima de demanda (el objetivo) y la máxima de
  cabecera, con su fecha.
- RF-49: EL SISTEMA aplicará a las curvas de la central el mismo tramo ampliado (RF-20) y la
  misma leyenda para ocultar o mostrar (RF-21).

Instante coincidente (añadido el 2026-10-17 a petición del usuario)

- RF-50: CUANDO el operador elige un instante coincidente, EL SISTEMA tomará como objetivo de
  cada alimentador marcado su registro en esa fecha y hora, no su máxima.
- RF-51: MIENTRAS haya instante coincidente, EL SISTEMA tomará las zonas y la generación de
  la central de ese mismo registro, y avisará si ese registro tiene la zona aguas arriba
  fuera de lo normal.
- RF-52: EL SISTEMA ofrecerá como instante coincidente la fecha y hora de la máxima de cada
  alimentador marcado.
- RF-53: SI un medidor no tiene registro en ese instante, ENTONCES EL SISTEMA lo dirá y ese
  alimentador no tendrá objetivo.

Calibración por proyecto (añadido el 2026-10-17; usuario, al ir a aplicar NA203 y luego
NA205: «la calibración se debe hacer por proyecto en DIgSILENT; si es un alimentador se
hace de ese y dos o más se hacen de todas según el proyecto, no de forma independiente»)

- RF-54: CUANDO el operador aplica el ajuste de dos o más alimentadores de un mismo
  proyecto, EL SISTEMA los calibrará en una sola ejecución de DIgSILENT, todos en los
  mismos flujos de carga de «Sin proyecto» (cambia 008:RF-12).
- RF-55: EL SISTEMA moverá en cada flujo el factor de escala de cada alimentador, o de cada
  zona si tiene central (RF-40), con lo medido en su cabecera o en su zona, y dará la
  calibración por cuadrada solo cuando todos cumplan la tolerancia en el mismo flujo.
- RF-56: SI el flujo no converge, ENTONCES EL SISTEMA aplicará los remedios de 006:RF-16 una
  vez para todo el proyecto y, si no cuadra, dejará todos los alimentadores con el último
  reparto común que convergió.
- RF-57: SI un alimentador no se puede preparar (sin cabecera, sin demanda que escalar),
  ENTONCES EL SISTEMA lo dirá en su informe y calibrará juntos los demás (cambia 008:RF-14).
- RF-58: SI el operador cancela, ENTONCES EL SISTEMA terminará el flujo en curso y dejará
  todos los alimentadores con el último reparto común que convergió (cambia 008:RF-15).
- RF-59: EL SISTEMA dará un informe por alimentador con lo medido en el flujo final común y
  dirá con qué alimentadores se calibró.
- RF-60: MIENTRAS el ajuste sea de un solo alimentador, EL SISTEMA lo calibrará como hasta
  ahora.

## Requisitos no funcionales

- Determinismo: el DGS sigue idéntico byte a byte con `workers=1` y `workers>1`.
- Escala: ninguna regla depende del número de alimentadores; las curvas se piden una vez
  por alimentador, no una vez por punto.
- Universal (constitución 13): nada depende del patrón de nombres de Electro Dunas; el
  trafomix de RF-7 es el que define el perfil.
- Idioma: español.

## Casos límite

- Puente con equipo cuyos dos extremos tienen dos o más líneas: queda `ElmCoup` (no hay
  un cubículo único donde ponerlo).
- Puente con equipo entre la fuente y la primera línea: la barra de la fuente nunca se
  funde.
- Dos puentes con equipo que acaban en la misma línea por el mismo lado: el primero por
  orden de tramo va al cubículo y el segundo queda `ElmCoup` (RF-4).
- Disposición reducida y completa del TXT: el resultado es el mismo.
- Red unida: los enlaces entre alimentadores siguen siendo `ElmCoup` abiertos.
- Un alimentador sin máxima en el ajuste no aparece en la gráfica.
- Central parada en el registro objetivo (generación ≤ 0): se escribe lo medido (sus
  servicios auxiliares) y la calibración sigue con las dos zonas.
- Un medidor de la central sin hoja en los libros de cabecera: se avisa y se calibra sin la
  central (RF-46).
- Registros de los medidores de la central con fechas que no casan con los de la cabecera:
  solo se usan los registros comunes a los cuatro.
- Una central declarada en un alimentador que no está entre los marcados: no se usa.

## Fuera de alcance

- Los proyectos ya importados en DIgSILENT no se modifican: hay que reimportar el DGS.
- Los acopladores internos de cada SED (`SW_SE…`) no cambian.
- Las curvas de otros pasos de la web (estudios, informes).
- Mover o redibujar las SED que el operador ya movió a mano.
- Más de una central por alimentador, y una central entre dos alimentadores.
- El modelo dinámico de la central (máquina síncrona, regulación de tensión, despacho):
  entra como generador estático con P y Q fijas.
- Leer la central de los archivos de IGEA: no la traen.

## Criterios de finalización

Cada RF citado por al menos una prueba (`grep -rnoE "021:RF-[0-9]+" tests`), suite en verde
con los datos reales (TXT y MDB), DGS idéntico con `workers=1` y `workers>1`, y NA203 +
NA205 reimportado en DIgSILENT: sin grupos de puntos en las derivaciones, SE50195 movida a
mano con el cable unido, flujo de «Caso base» igual que antes y transferencia con los
mismos seccionadores. NA205 calibrado con su central en DIgSILENT en el registro del
2026-08-20 16:45, con las dos zonas dentro de la tolerancia.

## Dudas abiertas

- Resuelta el 2026-10-17 (T6): en el NA205 que exporta PowerFactory el `SecSubProd` no
  tiene conectores propios y la línea entra en la barra de MT de dentro de la SED (131
  SED). RF-12 se cumple así: la barra de la que cuelga una SED sola pasa a ser su barra
  de MT, dentro del `ElmSubstat`, con su nombre y sin el acoplador `SW_SE…`. Probado en
  DIgSILENT con NA203 + NA205: al mover SE50195 el cable la sigue.
