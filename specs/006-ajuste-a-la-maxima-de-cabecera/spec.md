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
  DIgSILENT que elige el operador, con las cargas de SED de ese alimentador.
- RF-5: CUANDO una SED tiene clientes importantes cruzados (spec 004, RF-43), EL SISTEMA
  le asignará como kW la suma de la potencia máxima de esos clientes, en lugar de la
  demanda que tenga en DIgSILENT.
- RF-6: CUANDO una SED tiene clientes importantes, EL SISTEMA le asignará como kVAR la
  suma del de cada cliente, que da su potencia máxima con la relación entre su energía
  reactiva y su activa.
- RF-7: SI un cliente importante no trae energía activa o reactiva, ENTONCES EL SISTEMA
  usará para su kVAR el factor de potencia del objetivo y lo dirá.
- RF-8: EL SISTEMA repartirá entre las demás SED del alimentador el kW y el kVAR que
  faltan para el objetivo, en proporción a la potencia instalada (kVA) del
  transformador de cada una y sin tener en cuenta la demanda que tenga en DIgSILENT.
- RF-9: SI una SED con clientes importantes no está en el alimentador del proyecto,
  ENTONCES EL SISTEMA la omitirá, la listará en el informe y seguirá.
- RF-10: SI una SED a repartir no tiene en DIgSILENT transformador con potencia
  instalada, ENTONCES EL SISTEMA tomará su kVA de la entrada original cargada en la web
  (TXT o `.mdb`) y lo dirá.
- RF-24: SI la SED tampoco tiene kVA en la entrada original, o no hay entrada cargada,
  ENTONCES EL SISTEMA no la repartirá, la listará como error de datos y no aplicará el
  ajuste hasta corregirla.

Cuadre con las pérdidas

- RF-11: EL SISTEMA dará por cuadrado el alimentador cuando el flujo nativo converge y
  el kW que entra por la cabecera difiere del objetivo dentro de la tolerancia elegida.
  El kVAR nunca será criterio de aceptación ni bloqueará la conversión o los estudios.
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
- La trazabilidad fuente–modelo–relectura se apoya en la tesis doctoral de McMorran
  sobre intercambio de modelos CIM y consistencia semántica:
  [University of Strathclyde](https://stax.strath.ac.uk/concern/theses/cc08hf706).
- Mantener el Q resultante de la red permite que la compensación capacitiva siga siendo
  una variable física del flujo, coherente con la optimización de bancos estudiada por
  Sultana y Roy en *International Journal of Electrical Power & Energy Systems*, DOI
  [10.1016/j.ijepes.2013.07.011](https://doi.org/10.1016/j.ijepes.2013.07.011).

Estas referencias justifican el método y la trazabilidad; no sustituyen los datos del
catálogo aprobado ni la relectura efectiva del proyecto nativo.

## Casos límite

- Alimentador sin clientes importantes: todo se reparte por kVA.
- Todas las SED del alimentador tienen clientes importantes: no hay nada que repartir
  (RF-13).
- Dos clientes importantes en la misma SED: se suman.
- SED con clientes importantes y otros usuarios: lleva solo la de los clientes (RF-5).
- Carga desequilibrada (por fase): se conserva su reparto entre fases (spec 004, RF-9).
- Escenario de operación activo en el caso de estudio: las demandas irían a él y no a la
  variación (como en `tools/cargas_pf.py`).
- Alimentador sin `ElmFeeder`: no se puede medir lo que entra por su cabecera.
- El objetivo es menor que las pérdidas en vacío de la red.

## Fuera de alcance

- Varios alimentadores en una sola ejecución: uno cada vez, el de la máxima buscada.
- Repartir con la curva de carga de cada SED o por tipo de cliente; solo por kVA.
- Cambiar la topología, los taps o los tipos para que el flujo converja: los remedios de
  RF-16 solo tocan los ajustes del flujo de carga y el reparto.
- Rellenar el libro de demandas de la spec 004 con el resultado.
- Prueba real en DIgSILENT: la hace el usuario.

## Criterios de finalización

- `grep -rnoE "006:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-24.
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
