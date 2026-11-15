# ADR-009 · El editor sobre el plano usa el mismo modelo y guarda variaciones, sin grafo propio

- Estado: pendiente
- Fecha: 2026-11-14
- Specs: 111:RF-1, 111:RF-2, 111:RF-4, 111:RF-5, 111:RF-6
- Elementos C4: gisEditor, cmpSalida, security
- Tareas: 111 T3, 111 T4, 111 T5
- Evidencia: `src/convertersmartgrid/preview.py::build_preview_layers`, `src/convertersmartgrid/preview.py::layers_to_geojson`
- Pendiente en: 111 T3 a T5 (F-15 del Plan Maestro V1, Tanda 1, sin worktree todavía)

## Contexto

La spec 111 pide ver la red sobre el plano, elegir un equipo, proponer maniobras u obras y ver los resultados en el
mismo trazo. `preview.py` ya produce las capas GeoJSON de cada alimentador desde `FeederModel` y `geography.py`
valida el CRS. El Plan Maestro V1 (§30.2, punto 5) advierte que el editor no debe inventar un segundo grafo físico ni
convertir un mapa de fondo en fuente de topología.

## Decisión

El editor lee las capas que salen de `build_preview_layers` y `layers_to_geojson` sobre el mismo modelo que se
convierte, con el mismo código de cada elemento en el plano, la tabla y los resultados (111:RF-2). Cada edición
(maniobra, tramo nuevo con sus vértices tal como se dibujaron, equipo insertado) se guarda como variación del
escenario y nunca en el caso base (111:RF-4, RF-5). Dos tramos que se cruzan sin nodo ni equipo no se conectan
(111:RF-6).

## Alternativa descartada

Un modelo propio del editor en el navegador, sincronizado con el servidor. Duplicaría la topología, se desfasaría
del DGS y haría que lo que se ve no fuera lo que se calcula.

## Consecuencias

- El plano y el cálculo no pueden divergir: los dos salen del mismo modelo.
- El editor depende de la salida del motor; un cambio en las capas de `preview.py` es un cambio de contrato para él.

## Contratos afectados

El GeoJSON de `preview.py` (propiedades y código de cada elemento), las rutas nuevas de la API del plano de la 111 y
el formato de las variaciones del escenario.

## Vuelta atrás

El editor es una vista nueva: quitarlo no toca el caso base ni el motor, porque todo lo que escribe son variaciones.
