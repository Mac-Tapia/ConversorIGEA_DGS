# Completar lo que falta

Cuándo: la conversión trae conductores cuyo código no está en el catálogo, o al sistema le faltan datos para el año 0.

## Conductores sin ficha

1. Al convertir, cada código nuevo se añade al catálogo como una fila, sin tocar las que ya hay (053:RF-1).
2. Si su familia tiene otra sección, se deduce de la más cercana (053:RF-2); si no se puede deducir, la fila queda sin valores,
   pendiente de ficha, y se avisa: nunca un tramo con impedancia cero sin aviso (053:RF-5).
3. El catálogo es uno y universal; el perfil de empresa no interviene (053:RF-8). Se escribe sin quedar a medias y se usa en la
   misma conversión (053:RF-7).
4. Lo que el catálogo trae lo usa la conversión de cualquier fuente: completa los códigos que la entrega no trae
   (`src/convertersmartgrid/reglas.py:11` («input/catalogo_parametros.xlsx»)).

## Datos del año 0 de un sistema

1. `POST /api/workspaces/<espacio>/system/missing-data` (`src/convertersmartgrid/web/app.py:2297`
   («'grid', 'base', 'missing-data'»)): un trabajo que lista los datos que faltan para el año 0
   (`src/convertersmartgrid/web/services.py:4676` («Datos que faltan para el año 0»)).
2. Lo que falte y no se pueda deducir lo pide el asistente al operador, nombrando el dato y su sitio. No lo inventa.
