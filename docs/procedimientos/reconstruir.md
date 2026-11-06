# Reconstruir lo que la fuente no trae

Cuándo: un alimentador cargado tiene tramos sin nodo, sin fuente, sin configuración de línea o sin coordenadas, y por eso no se
puede convertir. Nada bloquea salvo una red vacía: se reconstruye y se anota.

1. Diagnosticar la selección: `POST /api/workspaces/<espacio>/diagnose` (`src/convertersmartgrid/web/app.py:1272`
   («/api/workspaces/{wid}/diagnose»)). Dice qué falta en cada alimentador.
2. Reconstruir: `POST /api/workspaces/<espacio>/reconstruct` (`src/convertersmartgrid/web/app.py:1282`
   («/api/workspaces/{wid}/reconstruct»)) con los alimentadores elegidos.
3. La reconstrucción trabaja sobre una copia y anota cada cambio con su evidencia; el dato original no se toca
   (`src/convertersmartgrid/reconstruction_pipeline.py:32` («def reconstruir_seleccion»)). Sus pasos, en este orden:
   fuentes (`src/convertersmartgrid/reconstruction_pipeline.py:45` («'Fuentes'»)), configuraciones de línea
   (`src/convertersmartgrid/reconstruction_pipeline.py:47` («'Configuraciones de línea'»)), nodos
   (`src/convertersmartgrid/reconstruction_pipeline.py:49` («'Nodos'»)), continuidad
   (`src/convertersmartgrid/reconstruction_pipeline.py:51` («'Continuidad'»)), coordenadas
   (`src/convertersmartgrid/reconstruction_pipeline.py:53` («'Coordenadas'»)) y catálogo
   (`src/convertersmartgrid/reconstruction_pipeline.py:55` («'Catálogo'»)).
4. Un alimentador cortado de su red se une a la vecina por el tramo que falta y se reparte por medida (022:RF-57 a 022:RF-61).
   En la cadena de un sistema eléctrico es la opción `--reconstruir` de `tools/sistema_web.py`
   (`tools/sistema_web.py:623` («'--reconstruir'»)), que reconvierte e importa de nuevo: **el asistente no la usa sobre un
   proyecto ya trabajado**; se la propone al operador.
5. Revisar el informe de la reconstrucción antes de convertir: lo reconstruido es un supuesto anotado, no un dato.
