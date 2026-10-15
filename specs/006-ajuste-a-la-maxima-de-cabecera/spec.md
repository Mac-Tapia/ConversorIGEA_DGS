# Spec 006 — Ajuste de las demandas a la máxima de cabecera

Estado: aprobada (2026-10-09) · Fecha: 2026-10-09 · Origen: uso de la demanda medida (spec 004, RF-22 a RF-43) con los libros reales, 2026-10-09

## Contexto y objetivo

La demanda medida (spec 004) ya extrae la máxima de cabecera de un alimentador y cruza
los clientes importantes con su SED, pero solo la muestra y la descarga: el operador
reparte a mano esa máxima entre las SED del alimentador ya modelado en DIgSILENT. La
spec 004 lo dejó fuera de alcance. El usuario lo pide el 2026-10-09: la suma de las
demandas de todas las SED del alimentador, más las pérdidas de la red, tiene que dar en
la cabecera la máxima medida, con un error de 1 % como mucho. Las SED con clientes
importantes llevan la demanda de esos clientes; las demás se reparten lo que falta en
proporción a su transformador. Hoy el operador lo hace con prueba y error en DIgSILENT.

## Usuarios / actores

- Ingeniero de planificación que, desde la web, ajusta las demandas de un alimentador de
  un proyecto de DIgSILENT a la máxima medida en su cabecera.
- DIgSILENT PowerFactory 2024, por su API de Python, en el carril `powerfactory`.

## Historias de usuario

- H1: Como ingeniero quiero que las demandas de las SED de un alimentador sumen, con las
  pérdidas, la máxima medida en su cabecera, para estudiar la red en su punto real de
  máxima demanda.
- H2: Como ingeniero quiero que las SED con clientes importantes lleven la demanda medida
  de esos clientes, para no repartirla a ciegas donde ya se conoce.
- H3: Como ingeniero quiero saber por qué no converge el flujo y que el sistema lo
  intente resolver, para no tener que hacerlo a mano en DIgSILENT.

## Requisitos funcionales (EARS)

Objetivo de cabecera

- RF-1: EL SISTEMA tomará como objetivo el kW y el kVAR de la máxima que la demanda
  medida dio para el medidor del alimentador (spec 004, RF-27 y RF-28), el mismo valor
  que muestra su tabla.
- RF-2: SI la máxima buscada tiene más de un medidor, ENTONCES EL SISTEMA pedirá elegir
  el medidor de la cabecera y no ajustará hasta que se elija uno.
- RF-3: SI el medidor elegido no tiene máxima (spec 004, RF-32), ENTONCES EL SISTEMA no
  ajustará y lo dirá.

Demandas por SED

- RF-4: EL SISTEMA trabajará sobre el alimentador de la máxima en el proyecto de
  DIgSILENT que elige el operador, con las cargas de SED de ese alimentador. SI un solo
  medidor alimenta dos o más troncales que salen de la misma barra fuente, ENTONCES EL
  SISTEMA medirá la inyección común en el `ElmXnet`, no solo la rama apuntada por
  `ElmFeeder`; la suma de las troncales deberá cuadrar una sola vez contra la máxima del
  medidor y el informe dará también el flujo individual de cada troncal. Esta detección
  se ejecutará automáticamente en cada calibración y admitirá cualquier cantidad de
  troncales. SI hay dos o más troncales y no se demuestra exactamente un `ElmXnet`
  común activo, ENTONCES EL SISTEMA no calibrará usando una rama parcial y explicará la
  ambigüedad; con una sola troncal conservará la medición de `ElmFeeder`.
- RF-5: CUANDO una SED tiene clientes importantes cruzados (spec 004, RF-43), EL SISTEMA
  le asignará como kW la suma de la potencia máxima de esos clientes, en lugar de la
  demanda que tenga en DIgSILENT.
- RF-6: CUANDO una SED tiene clientes importantes, EL SISTEMA le asignará como kVAR la
  suma del de cada cliente, que da su potencia máxima con la relación entre su energía
  reactiva y su activa.
- RF-7: SI un cliente importante no trae energía activa o reactiva, ENTONCES EL SISTEMA
  usará para su kVAR el factor de potencia del objetivo y lo dirá.
- RF-8: EL SISTEMA formará la población de SED uniendo la topología de `ElmFeeder` con
  todas las cargas cuya columna nativa `p:alimentador` corresponde al alimentador, sin
  omitir una carga solo porque `ElmFeeder.GetObjs` no la devuelve. Repartirá entre las
  SED no fijas el kW y el kVAR que faltan, en proporción a la potencia instalada (kVA)
  del transformador de cada una y sin usar su demanda anterior en DIgSILENT.
- RF-9: SI una SED con clientes importantes no está en el alimentador del proyecto,
  ENTONCES EL SISTEMA la omitirá, la listará en el informe y seguirá.
- RF-10: SI una SED a repartir no tiene en DIgSILENT transformador con potencia
  instalada, ENTONCES EL SISTEMA tomará su kVA de la entrada original cargada en la web
  (TXT o `.mdb`) y lo dirá.
- RF-24: SI la SED tampoco tiene kVA en la entrada original, o no hay entrada cargada,
  ENTONCES EL SISTEMA no la repartirá, la listará como error de datos y no aplicará el
  ajuste hasta corregirla.
- RF-25: EL SISTEMA mostrará en la tabla de clientes importantes una casilla por cliente,
  marcada por defecto, para dejarlo conectado o desconectarlo en el ajuste.
- RF-26: CUANDO el operador desmarca un cliente importante, EL SISTEMA no sumará su
  potencia a su SED (RF-5) y, si todos los clientes de esa SED están desmarcados, pondrá
  fuera de servicio la carga de la SED en la variación del ajuste, no le repartirá
  demanda y la listará en el informe.

Cuadre con las pérdidas

- RF-11: EL SISTEMA dará por cuadrado el alimentador cuando el flujo nativo converge y
  el kW que entra por la cabecera difiere del objetivo dentro de la tolerancia elegida.
  El kVAR nunca será criterio de aceptación ni bloqueará la conversión o los estudios.
  La potencia activa de cabecera menos la suma del consumo efectivo nativo
  (`m:Psum:bus1`) de todas las cargas no podrá ser negativa más allá del ruido numérico;
  si faltan esos resultados se usará, de forma conservadora, la suma nominal escrita.
  Una diferencia negativa dejará el ajuste como `VIOLACION_FISICA`, porque la frontera
  puede estar omitiendo una troncal o cargas. El informe identificará cuál de las dos
  bases se usó para calcular las pérdidas.
- RF-12: MIENTRAS el kW no esté cuadrado, EL SISTEMA corregirá únicamente el factor de
  potencia activa repartida para compensar pérdidas y volverá a ejecutar el flujo. La
  asignación inicial de Q se conserva y el Q final es el resultado de la red nativa.
- RF-13: SI las SED con clientes importantes ya superan el objetivo, o no dejan nada que
  repartir, ENTONCES EL SISTEMA las escalará también, junto con las demás, hasta cuadrar,
  y lo dirá.
- RF-14: SI el kW cumple la tolerancia, ENTONCES EL SISTEMA aceptará el ajuste con estado
  `OK` o `AVISO_KVAR`. El informe y la interfaz mostrarán siempre el objetivo de kVAR,
  el resultado del flujo nativo, la diferencia firmada y relativa, la tolerancia y
  `bloquea=false`; `AVISO_KVAR` se usa cuando la diferencia reactiva supera esa
  tolerancia, sin impedir la conversión, el ajuste ni los estudios.
- RF-40: EL SISTEMA releerá después del flujo P, Q, FP, estado e `i_scale` de cada SED y
  adjuntará los conteos de la unión topología/`p:alimentador`, junto con la relectura de
  bancos del vínculo del proyecto.
- RF-41: ANTES de crear una variación o escribir cargas, EL SISTEMA ejecutará el flujo y
  releerá el estado efectivo del alimentador en DIgSILENT. No considerará suficiente que
  existan objetos `ElmLod` o que sus potencias sean distintas de cero.
- RF-42: EL SISTEMA considerará el reparto ya cargado solamente si las cargas fijas
  coinciden con su P/Q calculada, las cargas escalables conservan un factor común de P y
  el factor Q calculado, `i_scale` identifica correctamente ambos grupos, no hay SED
  ambiguas o faltantes, el flujo converge y la cabecera cumple la tolerancia de kW.
- RF-43: SI RF-42 se cumple, ENTONCES EL SISTEMA devolverá
  `YA_CARGADO_VALIDADO`, no creará otra variación y no volverá a distribuir ni escribir
  las cargas. La prueba física también admitirá valores correctos cargados manualmente,
  sin exigir un recibo previo de esta aplicación.
- RF-44: DESPUÉS de una distribución nueva, EL SISTEMA repetirá RF-42 carga por carga. SI
  la relectura falla, ENTONCES devolverá `FALLO_VALIDACION_NATIVA`, retirará la variación
  defectuosa y no promoverá el resultado como una calibración aceptada.

Convergencia

- RF-15: SI el flujo de carga no converge, ENTONCES EL SISTEMA buscará la causa y la
  informará: barras sin tensión o aisladas, transformadores y líneas sobrecargados en el
  último flujo que convergió y la barra con la tensión más baja.
- RF-16: SI el flujo de carga no converge, ENTONCES EL SISTEMA aplicará, por orden y
  hasta que converja, estos remedios: acercarse al objetivo en pasos desde el último
  reparto que convergió, más iteraciones, ajuste automático del paso y cargas de
  impedancia constante por debajo de la tensión mínima.
- RF-17: EL SISTEMA dirá en el informe qué remedio aplicó y qué ajustes del flujo de
  carga cambió para converger.
- RF-18: SI tras todos los remedios el flujo sigue sin converger o sin cuadrar, ENTONCES
  EL SISTEMA dejará la variación con el último reparto que convergió, marcada como que
  no cumple el 1 %, con la diferencia alcanzada y la causa encontrada.

Ejecución e informe

- RF-19: CUANDO el operador lo pide, EL SISTEMA grabará las demandas en una variación
  nueva del proyecto, como hacen las cargas (spec 004, RF-3, RF-4 y RF-9).
- RF-20: CUANDO el operador pide simular, EL SISTEMA informará la demanda que tendría cada
  SED antes del cuadre con las pérdidas, sin escribir en el proyecto.
- RF-21: CUANDO termina, EL SISTEMA dará por SED su demanda antes y después, si es de
  clientes importantes o repartida, y para el alimentador el objetivo, lo que entra por
  la cabecera, las pérdidas, el error en kW y en kVAR y el número de flujos ejecutados.
- RF-22: SI se cancela, ENTONCES EL SISTEMA terminará el flujo en curso, dejará la
  variación con el último reparto que convergió y lo dirá.
- RF-23: EL SISTEMA ofrecerá el ajuste en la sección «Demanda medida», con el proyecto de
  DIgSILENT elegido en la misma pestaña y el alimentador de la máxima buscada.

Escenario de operación (cambio del 2026-10-12). SI213 cuadró a 1.621,8 kW y 796,8 kVAR
(objetivo 1.624 y 800), pero «Verificar la convergencia» midió 229,2 kW y 53,1 kVAR en
la cabecera: la potencia de una carga es dato de operación y, con el «Operation
Scenario» activo, manda la que guarda el escenario, que seguía siendo la de antes del
ajuste. Y «Sin proyecto» y «Con proyecto» copian ese escenario (011:RF-47). El usuario
lo ordena así: el escenario base lleva la red ajustada a la máxima —clientes
importantes con su demanda y el resto de las SED escaladas—, sus copias salen
calibradas, y solo las demandas en bloque y las cargas nuevas cambian después la
cabecera.

- RF-27: CUANDO termina el ajuste, EL SISTEMA grabará la demanda final de cada SED
  repartida, y el fuera de servicio de las de RF-26, también en el escenario de operación
  del caso en que se ajustó, si lo tiene.
- RF-28: MIENTRAS existan los tres casos de la spec 011, EL SISTEMA grabará la demanda
  final del ajuste también en el escenario de cada uno de los tres.
- RF-29: CUANDO termina el ajuste, EL SISTEMA medirá la cabecera con el escenario
  restaurado y la dará en el informe.
- RF-30: SI la cabecera medida con el escenario difiere de la ajustada más que la
  tolerancia, ENTONCES EL SISTEMA lo dirá en un aviso, con las dos medidas.

Curva del registro del medidor (cambio aprobado el 2026-10-12). El objetivo
del ajuste es un solo registro de todo el histórico del medidor, y la web solo da su
fecha: el operador no ve si esa máxima es un día típico o un pico aislado (una
maniobra, una transferencia de carga) que no conviene usar para calibrar. El usuario
pide ver en la caja del ajuste el registro entero, del primer dato al último, con el
mes de la máxima resaltado con una franja.

- RF-31: CUANDO se busca la máxima de cabecera de un alimentador, EL SISTEMA conservará
  la curva de kW y kVAR de cada medidor, sin volver a abrir el libro para dibujarla.
- RF-32: EL SISTEMA mostrará en la caja del ajuste la curva del registro en orden
  cronológico, desde su primer registro hasta el último, con la fecha en el eje
  horizontal y el kW en el vertical.
- RF-33: EL SISTEMA sombreará con una franja el mes natural que contiene la máxima.
- RF-34: EL SISTEMA marcará el punto de la máxima con su fecha, hora y kW.
- RF-35: CUANDO el operador acerca la gráfica a un tramo de fechas, EL SISTEMA mostrará
  ese tramo con el detalle de cada registro.
- RF-36: CUANDO el operador lo pide, EL SISTEMA añadirá el kVAR del registro a la gráfica.
- RF-37: SI un registro no trae fecha o su kW no es numérico, ENTONCES EL SISTEMA lo
  dejará fuera de la curva y dirá cuántos dejó fuera.
- RF-38: DONDE el alimentador tiene varios medidores, EL SISTEMA dibujará la curva del
  medidor que da el objetivo, con un selector para ver la de los demás.
- RF-39: SI la curva tiene más puntos de los que la gráfica distingue, ENTONCES EL SISTEMA
  la reducirá conservando el máximo y el mínimo de cada intervalo, de modo que la máxima
  nunca desaparezca de la vista general.

## Requisitos no funcionales

- El ajuste corre en DIgSILENT: es un trabajo del carril `powerfactory`, con progreso
  por cada flujo de carga y cancelable (P7).
- El 1 % es el valor por defecto; el operador lo puede cambiar entre 0,1 % y 10 %.
- Universal (P13): ni el nombre de la cabecera, ni la tensión, ni la forma de los códigos
  de SED de una empresa como valor fijo.
- Datos de la distribuidora (P9): las pruebas usan libros y proyectos sintéticos; la
  prueba en DIgSILENT la hace el usuario.
- Escala: cualquier número de SED y de medidores por alimentador.

## Justificación científica y académica

- La separación entre medición de cabecera y asignación de cargas sigue la formulación
  de estimación/asignación de carga en redes de distribución de Carmona-Delgado et al.,
  *Electric Power Systems Research*, DOI
  [10.1016/j.epsr.2013.03.004](https://doi.org/10.1016/j.epsr.2013.03.004).
- La reasignación de cargas no monitorizadas para reconciliarlas con mediciones reales
  está desarrollada también por Sarić y Ranković en *Electric Power Systems Research*,
  DOI [10.1016/j.epsr.2011.10.003](https://doi.org/10.1016/j.epsr.2011.10.003).
- La estimación de cargas de un alimentador a partir de mediciones y perfiles se estudia
  en la tesis de maestría de Urvir Singh:
  [North Carolina State University](https://repository.lib.ncsu.edu/items/a3fd70d6-6f1a-43cf-a853-bb07191b8e75).
- El uso conjunto de mediciones limitadas, restricciones operativas y topologías radiales
  o generales para estimar cargas nodales se sustenta en la tesis doctoral de Jie Wan:
  [Drexel University](https://doi.org/10.17918/etd-201).
- La trazabilidad fuente–modelo–relectura se apoya en la tesis doctoral de McMorran
  sobre intercambio de modelos CIM y consistencia semántica:
  [University of Strathclyde](https://stax.strath.ac.uk/concern/theses/cc08hf706).
- Mantener el Q resultante de la red permite que la compensación capacitiva siga siendo
  una variable física del flujo, coherente con la optimización de bancos estudiada por
  Sultana y Roy en *International Journal of Electrical Power & Energy Systems*, DOI
  [10.1016/j.ijepes.2013.07.011](https://doi.org/10.1016/j.ijepes.2013.07.011).
- Un único medidor común obliga a usar la demanda coincidente agregada, no a repetir la
  misma máxima en cada salida. La diferencia entre máxima coincidente y suma de máximas
  individuales se sustenta en la tesis de maestría de Erickson:
  [University of Tennessee](https://trace.tennessee.edu/handle/20.500.14382/37180).

Estas referencias justifican el método y la trazabilidad; no sustituyen los datos del
catálogo aprobado ni la relectura efectiva del proyecto nativo.

## Casos límite

- Alimentador sin clientes importantes: todo se reparte por kVA.
- Un medidor y dos o más troncales: clientes importantes fijos donde están conectados,
  un solo factor por kVA para las demás SED de todas las troncales y cuadre de la suma
  una sola vez contra el medidor común.
- Dos o más troncales sin exactamente un `ElmXnet` común activo: no se calibra con la
  rama de `ElmFeeder`; se informa que la frontera única no pudo demostrarse.
- Todas las SED del alimentador tienen clientes importantes: no hay nada que repartir
  (RF-13).
- Dos clientes importantes en la misma SED: se suman.
- SED con clientes importantes y otros usuarios: lleva solo la de los clientes (RF-5).
- Carga desequilibrada (por fase): se conserva su reparto entre fases (spec 004, RF-9).
- Escenario de operación activo en el caso de estudio: las demandas irían a él y no a la
  variación (como en `tools/cargas_pf.py`); y, una vez restaurado, manda sobre la
  variación: por eso el resultado se graba también en él (RF-27, RF-28).
- Alimentador sin `ElmFeeder`: no se puede medir lo que entra por su cabecera.
- El objetivo es menor que las pérdidas en vacío de la red.

## Fuera de alcance

- Varios alimentadores en una sola ejecución: uno cada vez, el de la máxima buscada.
- Repartir con la curva de carga de cada SED o por tipo de cliente; solo por kVA.
- Cambiar la topología, los taps o los tipos para que el flujo converja: los remedios de
  RF-16 solo tocan los ajustes del flujo de carga y el reparto.
- Rellenar el libro de demandas de la spec 004 con el resultado.
- Elegir en la curva otro registro como objetivo del ajuste: la curva solo informa; el
  objetivo sigue siendo la máxima de la spec 004.
- Curvas de las SED o de los clientes importantes: solo la del medidor de cabecera.
- Prueba real en DIgSILENT: la hace el usuario.

## Criterios de finalización

- `grep -rnoE "006:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-39.
- Suite completa en verde.
- `npx tsc --noEmit -p .` (en `frontend/`) y `npm run build` correctos.
- Prueba real en DIgSILENT con un alimentador, a cargo del usuario.

## Dudas abiertas

Ninguna. Resueltas el 2026-10-09:

- SED sin kVA: no debería haberla; se busca en la entrada original y, si tampoco está,
  es un error de datos que se corrige antes de ajustar (RF-10, RF-24).
- Cabecera: cada alimentador tiene una sola medición, la del medidor que da la demanda
  medida; se compara con lo que entra por la cabecera del `ElmFeeder` (RF-1, RF-2).
- kVAR distinto, positivo o negativo: se conserva el resultado nativo, se informa con
  `OK`/`AVISO_KVAR` y nunca bloquea el cuadre de kW (RF-14).

## Cambios de la spec 014 (2026-10-14)

- El ajuste se hace en «Sin proyecto», nunca en «Caso base» ni en «Con proyecto»
  (014:RF-1, RF-2), y mide la cabecera con las variaciones del operador activas en
  «Sin proyecto» (014:RF-14).
- RF-28: la demanda del ajuste se graba en los escenarios de «Sin proyecto» y «Con
  proyecto», solo en las cargas existentes y sin pisar una carga con cambio manual de
  demanda, que entra en el ajuste como fija (014:RF-4, RF-9 a RF-11).
- Las cargas nuevas quedan fuera de servicio mientras se mide y vuelven a su estado al
  terminar o cancelar (014:RF-6 a RF-8).

## Cambios de la spec 015 (2026-10-14)

- RF-19, RF-27 a RF-30: la calibración ya no crea una variación. Se escribe y se mide con
  el escenario de «Sin proyecto» activo, que es donde queda la demanda; si existe «Con
  proyecto», su escenario recibe la misma (015:RF-26, 014:RF-4). Una sola medida de la
  cabecera, con el escenario, y no hay otra que pueda diferir (RF-30).
- RF-18: la marca fija o escalable se escribe en la red, que comparten los casos: el
  escenario no la guarda (sonda T1 de la 015; 015:RF-37).
- La calibración no comprueba la red ni da por verificado el vínculo del proyecto: eso es
  la verificación del «Caso base» (015:RF-17, RF-22).
- RF-42, RF-44 (2026-10-15): además de lo escrito, cada fija tiene que consumir en el flujo
  su P y su Q, y cada escalada su P por el factor de escala; el informe trae el balance de
  la cabecera (015:RF-47 a RF-52).
