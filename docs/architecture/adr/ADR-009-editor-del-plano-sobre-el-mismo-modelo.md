# ADR-009 · El editor sobre el plano usa el mismo modelo y guarda variaciones, sin grafo propio

- Estado: vigente
- Fecha: 2026-11-15
- Specs: 111:RF-1, 111:RF-2, 111:RF-4, 111:RF-5, 111:RF-6
- Elementos C4: gisEditor, cmpSalida, security
- Tareas: 111 T3, 111 T4, 111 T5
- Evidencia: `src/convertersmartgrid/adaptadores/dgs.py::nombre_en_pf`, `src/convertersmartgrid/adaptadores/plano_red.py::identidad`, `src/convertersmartgrid/adaptadores/plano_red.py::vista`, `src/convertersmartgrid/adaptadores/plano_red.py::revision_red`, `src/convertersmartgrid/aplicacion/variacion_plano.py::editar`, `src/convertersmartgrid/aplicacion/variacion_plano.py::CARPETA`

## Contexto

La spec 111 pide ver la red sobre el plano, elegir un equipo, proponer maniobras u obras y ver los resultados en el
mismo trazo. `preview.py` ya produce las capas GeoJSON de cada alimentador desde `FeederModel` y `geography.py`
valida el CRS. El Plan Maestro V1 (§30.2, punto 5) advierte que el editor no debe inventar un segundo grafo físico ni
convertir un mapa de fondo en fuente de topología.

## Decisión

El editor lee el mismo modelo que se convierte y el manifiesto de geografía que escribe el lote
(`geography_to_dict`, los mismos vértices que pinta `preview.py`), con el mismo código de cada elemento en el plano, la tabla y los resultados (111:RF-2). Cada edición
(maniobra, tramo nuevo con sus vértices tal como se dibujaron, equipo insertado) se guarda como variación del
escenario y nunca en el caso base (111:RF-4, RF-5). Dos tramos que se cruzan sin nodo ni equipo no se conectan
(111:RF-6).

## Alternativa descartada

Un modelo propio del editor en el navegador, sincronizado con el servidor. Duplicaría la topología, se desfasaría
del DGS y haría que lo que se ve no fuera lo que se calcula.

## Consecuencias

- El plano y el cálculo no pueden divergir: los dos salen del mismo modelo.
- El editor depende de la salida del motor; un cambio en el manifiesto de geografía es un cambio de contrato para él.

## Contratos afectados

El GeoJSON de `preview.py` (propiedades y código de cada elemento), las rutas nuevas de la API del plano de la 111 y
el formato de las variaciones del escenario.

## Vuelta atrás

El editor es una vista nueva: quitarlo no toca el caso base ni el motor, porque todo lo que escribe son variaciones.
