# «Con proyecto» usaba un nombre sin importarlo y reventaba en el plan completo de las zonas

## Síntoma
`con_proyecto_optimizar` usa `BIBLIOTECA_TIPOS` al ejecutar el plan completo de las zonas (042:RF-23), sin importarlo: `NameError` en esa rama. Lo
vio la revisión de la spec 002 leyendo el código; ninguna prueba pasa por ahí, y la suite estaba en verde.

## Causa
El nombre se importa dentro de cada función de `web/services.py`. El commit que añadió esa rama copió la llamada de `set_nueva_proponer`, que sí lo
importa, y no su importación. Python no detecta un nombre sin definir hasta ejecutar la línea.

## Comprobación permanente
Ningún nombre sin definir en `src/` ni en `tools/`: Ruff (F821) lo comprueba sin ejecutar el código, para todos los ficheros y no solo este.

## Prueba
- `tests/test_nombres_definidos.py::test_ningun_nombre_sin_definir`
