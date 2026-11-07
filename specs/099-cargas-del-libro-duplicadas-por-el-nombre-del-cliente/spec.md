# Spec 099 — Cargas del libro duplicadas por el nombre del cliente

Estado: implementada · Fecha: 2026-11-07 · Origen: usuario, 2026-11-07, estudio de CA101 + CHN102: «considera uno solo de
Tierra Larga, la CH_23; la otra es duplicado; los duplicados no deben considerarse» y «debe hacer la comparativa con el
nombre del cliente».

## Contexto y objetivo

El libro de planificación `NuevosclientesMayoresv3.xlsx` trae dos filas de Tierra Larga en CA101: CH_20,
«SU-1770KW-Tierra Larga - Distrito el Camen- Provincia de chincha» (1 770 kW), y CH_23, «SU-1390KW-TierraLarga-Chincha»
(1 390 kW), del mismo expediente y a 2,6 km una de otra. 040:RF-1 solo une dos filas del mismo alimentador a 1 m o menos,
así que se creaban las dos y el alimentador recibía 3 160 kW de un solo cliente. El objetivo es reconocer el mismo cliente
por su nombre, en cualquier libro y de cualquier distribuidora, y quedarse con una sola fila: la última, que es la versión
vigente de la solicitud.

## Usuarios / actores

Operador que aplica las cargas nuevas en bloque desde la web («Cargas en DIgSILENT», 007 y 040).

## Requisitos funcionales (EARS)

- RF-1: ANTES de crear las cargas nuevas, EL SISTEMA tratará como el mismo cliente dos filas del mismo alimentador del
  libro cuyos nombres sean del mismo cliente (RF-2): creará solo la última del libro, no creará las anteriores y el informe
  dirá de cada una cuál es la que cuenta.
- RF-2: EL SISTEMA dará dos nombres por del mismo cliente cuando, quitadas las tildes, los signos, la potencia («1770KW»,
  «1,39 MW»), los números y las palabras que no distinguen a un cliente (tipo de solicitud, razón social y conectores),
  todas las palabras que distinguen al más corto estén en el otro, contando como una las palabras que un nombre escribe
  juntas y el otro separadas («TierraLarga» y «Tierra Larga»). Con una sola palabra distintiva, solo si los dos nombres
  son iguales: usuario, 2026-11-07, «PREDIO SUBLOTE N°01-FUNDO YANACA» y «YANACA» son clientes distintos.
- RF-3: Dos filas con el mismo cliente en alimentadores distintos del libro no son duplicadas (como 040:RF-2).
- RF-4: CUANDO dos filas del mismo alimentador están a 1 m o menos una de otra (040:RF-1), EL SISTEMA conservará también
  la última del libro. Cambia 040:RF-1, que conservaba la primera (usuario, 2026-11-07: «la última del libro»).
- RF-5: SI una variación de carga nueva ya creada guarda una fila que deja de contar por RF-1 o RF-4, ENTONCES EL SISTEMA
  la desactivará y la eliminará como 040:RF-6, solo si es una variación de carga nueva (040:RF-8), y lo dirá en el informe.
- RF-6: EL SISTEMA no usará nombres de clientes, de alimentadores ni de empresas en el código: las palabras que no
  distinguen a un cliente son del castellano de cualquier libro de solicitudes.
- RF-7: CUANDO el operador carga el libro de cargas nuevas en la web, EL SISTEMA mostrará en el plan, antes de simular
  o aplicar, cada fila repetida de los alimentadores o del sistema que se trabaja: la que no se crea, sus kW, la que
  cuenta, sus kW y si es por el mismo cliente o por el mismo punto (usuario, 2026-11-07: «en la web se debe informar al
  momento de cargar cuáles se repiten de ese alimentador o sistema que está trabajando»).

## Relación con otras specs

- Amplía 040:RF-1 (mismo punto) con el nombre del cliente y cambia cuál de las dos cuenta (RF-4).
- 040:RF-3 (ampliación de una SED existente) se mira después: la fila que cuenta puede ser una ampliación.

## Criterios de aceptación

- En el libro real, solo CH_20 → CH_23 (CA101), NA_28 → NA_36 (NA203) y NA_19 → NA_35 (NA205); YANACA no sale.
- `grep -rnoE "099:RF-[0-9]+" tests | sort -u` lista RF-1 a RF-7.
