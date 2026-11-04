# El asistente gastaba licencia, salía a la red y repetía escrituras sin preguntar

## Síntoma
«Lee los proyectos» abría DIgSILENT sin confirmar, buscar en internet salía al escribir la orden, un guion guardado se lanzaba con una petición, y un 4002 en unas obras las volvía a lanzar. Reproducido el 2026-11-04 sobre `7fd3780f`.

## Causa
Solo `escribe` decidía si se confirmaba, y el reintento miraba el texto del error, no lo que hacía el trabajo.

## Comprobación permanente
Cada tarea declara su efecto en `EFECTOS`: una tarea nueva sin declarar hace fallar la prueba. Se repite solo lo declarado idempotente: `TRABAJOS_IDEMPOTENTES` y `TAREAS_IDEMPOTENTES`.

## Prueba
- `tests/test_edicion_producto.py::test_cada_tarea_declara_su_efecto`
- `tests/test_edicion_producto.py::test_una_lectura_de_digsilent_no_se_lanza_sola`
- `tests/test_edicion_producto.py::test_una_busqueda_en_internet_no_sale_sin_confirmar`
- `tests/test_edicion_producto.py::test_el_guion_guardado_exige_su_confirmacion`
- `tests/test_edicion_producto.py::test_la_vigilancia_solo_reintenta_lo_idempotente`
- `tests/test_edicion_producto.py::test_el_asistente_no_repite_un_plan_que_escribe`
