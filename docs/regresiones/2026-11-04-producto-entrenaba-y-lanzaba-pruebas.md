# La edición de producto entrenaba y lanzaba la suite

## Síntoma
Con `CSG_EDICION=producto`, a las 22:00 la vigilancia lanzaba la suite de pruebas y con datos nuevos reentrenaba; `/api/asistente/equipo` y `digital-twin/episodes` respondían 200. Reproducido el 2026-11-04 sobre `7fd3780f`.

## Causa
La edición solo gobernaba las salidas a la red: nada más la consultaba.

## Comprobación permanente
El alcance está en `edicion.py`, y un middleware niega sus rutas; `test_una_ruta_nueva_de_estas_nace_negada` recorre la API, y una ruta nueva de entrenar o del gemelo sin negar la hace fallar. Los servicios también se niegan, porque el asistente los llama sin pasar por la ruta.

## Prueba
- `tests/test_edicion_producto.py::test_la_vigilancia_no_lanza_suite_ni_entrena_en_producto`
- `tests/test_edicion_producto.py::test_ninguna_via_lanza_pruebas_en_producto`
- `tests/test_edicion_producto.py::test_una_ruta_nueva_de_estas_nace_negada`
- `tests/test_edicion_producto.py::test_los_servicios_tampoco_entrenan_aunque_les_llamen_directo`
