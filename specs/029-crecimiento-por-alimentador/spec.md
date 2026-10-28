# Spec 029 — Crecimiento de la demanda por alimentador desde la medición de cabecera

Estado: pedida por el usuario el 2026-10-28 («saca de los libros de cabecera para cada
alimentador; después implementamos un módulo de proyección de demanda según los datos históricos
con variables exógenas o variables externas, proyecciones econométricas»).

## Por qué

El PIDE (spec 024) proyecta la demanda a los años del horizonte con una sola tasa del perfil,
`crecimiento_demanda_anual`, que estaba vacía: sin ella solo diagnosticaba el año 00. La medición
de cabecera trae varios años (2025 y 2026 en carpetas de año, spec 025): de ella sale la tasa de
cada alimentador, que crece distinto según su zona y sus clientes.

## Requisitos

- RF-1: CUANDO se ejecute el PIDE de un proyecto de sistema eléctrico sin tasa de crecimiento en
  el perfil, EL SISTEMA calculará la tasa anual de cada alimentador con medidor desde los libros
  de cabecera de los años que haya.
- RF-2: EL SISTEMA comparará la máxima de cada alimentador en los meses que tienen los dos años
  (el primero y el último con datos), para no comparar un año entero con uno a medias, y dará la
  tasa compuesta entre ellos.
- RF-3: SI un alimentador no tiene medidor o no tiene dos años con meses comunes, ENTONCES EL
  SISTEMA le dará la mediana de las tasas de su sistema y lo dirá.
- RF-4: EL SISTEMA escalará en cada año del horizonte la demanda de cada alimentador con su propia
  tasa, y dejará las cargas como estaban al terminar (024:RF-51).
- RF-5: EL SISTEMA dirá en el informe del PIDE la tasa de cada alimentador, los meses y las
  máximas con que se calculó y si es medida o la mediana.
- RF-6: DONDE el perfil traiga `crecimiento_demanda_anual`, EL SISTEMA usará esa tasa para todos,
  como hasta ahora.
- RF-7: EL SISTEMA leerá los libros de cabecera en el proceso del trabajo, no en el de la API
  (027:RF-25).

## Fuera de alcance

- La proyección econométrica con variables exógenas (población, PBI, clientes, tarifas): será
  una spec aparte, la 031. Esta tasa sale solo de la demanda medida.
- Corregir la tasa por cargas nuevas puntuales (las cargas en bloque van por la spec 007).
