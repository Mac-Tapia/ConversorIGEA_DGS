# Reemplazar con datos del catálogo

Cuándo: un conductor tiene parámetros que no corresponden a su ficha, o una fila del catálogo pasó de «por_confirmar» a
«ficha» con los datos del fabricante.

1. Generar el catálogo y su auditoría: `POST /api/workspaces/<espacio>/catalog/build`
   (`src/convertersmartgrid/web/app.py:2659` («/api/workspaces/{wid}/catalog/build»)), un trabajo de
   `build_catalog` (`src/convertersmartgrid/web/services.py:4988` («def build_catalog»)). El fichero es
   `catalogo_parametros.xlsx` (`src/convertersmartgrid/catalog.py:58` («CATALOG_FILENAME = 'catalogo_parametros.xlsx'»)).
2. **Lo hace el operador:** corregir en el libro las filas con su ficha y marcarlas «ficha» o «derivado». El asistente no
   inventa parámetros: si no hay ficha, la pide.
3. Subir el libro corregido: `POST /api/workspaces/<espacio>/catalog/apply`
   (`src/convertersmartgrid/web/app.py:2666` («/api/workspaces/{wid}/catalog/apply»)). Solo cuentan las filas marcadas
   (`src/convertersmartgrid/web/services.py:5041` («def apply_catalog»)).
4. Calibrar «Sin proyecto»: las fichas entran ahí, no en el DGS, que conserva los parámetros de la entrada; reconvertir
   no las lleva al DGS (`src/convertersmartgrid/web/services.py:5037` («AVISO_CATALOGO_APLICADO»), 032:RF-2, 032:RF-14).
5. Para deshacerlo, `DELETE /api/workspaces/<espacio>/catalog` (`src/convertersmartgrid/web/app.py:2679`
   («@app.delete('/api/workspaces/{wid}/catalog')»)).

Al convertir, el «Caso base» queda como lo registró la distribuidora; las fichas se aplican después, en «Sin proyecto» y en sus
variaciones (spec 032).
