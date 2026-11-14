# La edición de producto entrenaba y lanzaba la suite

## Síntoma
Con `CSG_EDICION=producto`, a las 22:00 la vigilancia lanzaba la suite de pruebas y con datos nuevos reentrenaba; `/api/asistente/equipo` y `digital-twin/episodes` respondían 200. Reproducido el 2026-11-04 sobre `7fd3780f`.

Revisión del 2026-11-13: el usuario ordenó lo contrario («nada debería estar apagado ni bloqueado», 086:RF-15 y RF-16 reescritos en `ccb81aa8`). Entrenar, la vigilancia y la suite en el producto ya no son un fallo, sino lo pedido; el fallo de entonces que sigue valiendo es otro: que la edición decidiera en silencio lo que hace cada vía, sin que lo mismo valga en las dos ediciones.

## Causa
La edición solo gobernaba las salidas a la red: nada más la consultaba. Con la orden del 2026-11-13, la edición gobierna solo las salidas a la red y la marca de las betas, y lo demás se comporta igual en las dos.

## Comprobación permanente
La vigilancia hace lo mismo en las dos ediciones; la suite solo corre donde están sus pruebas (en el instalado sin `tests/` no se lanza ni anota falsos fallos), y los servicios de entrenar responden en producto en lugar de negarse. Lo único que sigue fuera del instalado son las mejoras del código, que dicen que son de desarrollo.

## Prueba
- `tests/test_edicion_producto.py::test_la_vigilancia_hace_lo_mismo_en_las_dos_ediciones`
- `tests/test_edicion_producto.py::test_la_suite_corre_en_producto_donde_estan_sus_pruebas`
- `tests/test_edicion_producto.py::test_sin_pruebas_instaladas_la_vigilancia_no_anota_falsos_fallos`
- `tests/test_edicion_producto.py::test_los_servicios_ya_no_se_niegan_en_producto`
- `tests/test_edicion_producto.py::test_en_el_instalado_las_mejoras_dicen_que_son_de_desarrollo`
