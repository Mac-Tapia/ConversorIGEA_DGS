# Las declaraciones de unidad no sobrescriben la fuente de costos

## Síntoma

Al declarar una unidad fija, el lector ignoraba la columna de unidad aunque
existiera. Una celda de equipo con unidad u podía quedar etiquetada como km.
También admitía una unidad vacía cuando solo se había declarado la cabecera.

## Causa

El fallback fijo eliminaba la columna de las columnas leídas y prevalecía sin
contrastar cada fila. El contrato solo permitía fallback global o por hoja,
insuficiente para declarar explícitamente las unidades de una tabla mixta.

## Comprobación permanente

El lector conserva unidad fija global y mapping por hoja como declaraciones del
operador. Ahora lee y contrasta la columna si está declarada y presente, exige
una unidad por fila y rechaza declaraciones contradictorias. La opción aditiva
unidades_por_codigo exige cobertura de cada código leído y acuerdo con las otras
declaraciones. El CLI recibe ese mapa como JSON por una opción independiente.

No se infiere unidad por el nombre de hoja o prefijo, ni se convierten precios,
cantidades o longitudes. Una declaración explícita sin columna sigue siendo una
declaración del operador, no una certificación automática de su corrección.
El fragmento oficial PHD-COU usado en la prueba conserva el precio del resumen;
la etiqueta de costo por metro procede de su hoja de valoración. No se recalculan
ni sustituyen cachés del libro oficial y no se aplica esa prueba a una red real.

## Prueba

- `tests/test_modulos_transmision.py::test_declaracion_no_sobrescribe_unidad_autentica_de_columna`
- `tests/test_modulos_transmision.py::test_modulo_sin_unidad_en_fila_no_se_inventa`
- `tests/test_modulos_transmision.py::test_unidades_por_codigo_no_pueden_contradecir_declaracion_fija`
- `tests/test_modulos_transmision.py::test_unidad_por_codigo_autentico_conserva_precio_y_archivo`
- `tests/test_modulos_transmision.py::test_mapa_por_codigo_exige_cobertura_y_declaraciones_compatibles`
- `tests/test_modulos_transmision.py::test_cli_pasa_mapa_por_codigo_sin_inferir_unidades`
- `tests/test_modulos_transmision.py::test_base_por_hojas_con_la_unidad_declarada`
