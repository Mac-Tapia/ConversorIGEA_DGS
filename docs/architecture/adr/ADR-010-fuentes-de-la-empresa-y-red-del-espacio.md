# ADR-010 · Los módulos toman la red y los libros de la empresa del espacio, no los vuelven a pedir

- Estado: vigente
- Fecha: 2026-11-17
- Specs: 109:RF-25, 109:RF-26
- Elementos C4: fuentes, workspaceStore, vnr, pit, vad, planning, frontend
- Tareas: 109 T20
- Evidencia: `src/convertersmartgrid/aplicacion/fuentes_empresa.py::registrar`, `src/convertersmartgrid/aplicacion/fuentes_empresa.py::vigente`, `src/convertersmartgrid/aplicacion/fuentes_empresa.py::red_del_espacio`, `src/convertersmartgrid/presentacion/web/fuentes_api.py::fuente_o_subida`
- Consumidores: `src/convertersmartgrid/presentacion/web/vnr_api.py::fuente_o_subida`, `src/convertersmartgrid/adaptadores/sources/vnr.py::fuentes_empresa`

## Contexto

Todos los módulos trabajan sobre la misma empresa y la misma red, convertida por el mismo conversor (orden del
usuario, 17-11). Cada pestaña nueva pedía, sin embargo, sus propios ficheros: la del VNR volvía a pedir el
inventario VNR-GIS y el SICODI aunque el espacio ya había convertido esa red, y no había ningún sitio común para los
libros regulatorios de la empresa, que además se reemplazan por periodo (SICODI por resolución, PIT por periodo, VAD
por grupo de años).

## Decisión

Las fuentes de la empresa viven en el espacio (`<espacio>/fuentes/<clase>/`, con un índice escrito de forma
atómica): cada libro con su clase, su periodo y su huella, la nueva de su clase y periodo vigente y las anteriores
conservadas. La carga deja la red convertida en `<espacio>/derivados/` con su fuente, su empresa y sus
alimentadores. Cada módulo toma por defecto la red del espacio y la fuente vigente de su clase; una subida desde
cualquier módulo se registra para todos (`fuente_o_subida`). En la web, un solo selector (`ElegirFuente`).

## Alternativa descartada

Que cada módulo guarde sus propias copias. Duplica los libros, deja a cada pestaña con una versión distinta del mismo
SICODI y obliga al operador a cargar lo mismo varias veces.

## Consecuencias

Un módulo nuevo no añade cargas propias de lo que ya es de la empresa: declara su clase y usa el selector. Lo que es
solo suyo (por ejemplo, el inventario anterior de las altas y bajas del VNR) sigue siendo una entrada propia, según
la matriz de vínculos (ADR-011).

## Contratos afectados

`GET/POST /api/workspaces/{wid}/fuentes`, `GET /api/workspaces/{wid}/fuentes/red`; los endpoints de los módulos
aceptan `fuente_<clase>=<id>` en lugar del fichero.

## Vuelta atrás

Los endpoints siguen aceptando el fichero subido; quitar el selector deja a cada módulo como antes, sin perder lo
registrado en `fuentes/`.
