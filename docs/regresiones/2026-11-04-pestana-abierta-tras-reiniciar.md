# La pestaña abierta se quedaba atrás al reiniciar la web

## Síntoma
Tras reiniciar, una pestaña abierta pedía `since=67` y el proceso nuevo numeraba desde 1: el Registro no llegaba. Seguía viendo la fuente cargada, y convertir daba 400 hasta recargar. Reproducido el 2026-11-04 sobre `7fd3780f`.

## Causa
`EventLog` empezaba en 1 en cada proceso, y la pestaña no volvía a preguntar el estado al reconectar.

## Comprobación permanente
La numeración crece entre arranques; al reconectar, la pestaña relee el espacio, los trabajos y `/api/health`, y marca interrumpido lo que el servidor nuevo no conoce. Un 400 al lanzar un trabajo también la pone al día.

## Prueba
- `tests/test_edicion_producto.py::test_el_registro_sigue_tras_reiniciar_el_servidor`
- `tests/test_edicion_producto.py::test_el_registro_tras_reiniciar_por_la_api`
- `tests/test_edicion_producto.py::test_la_conversion_tras_reiniciar_lo_dice_y_el_espacio_ya_no_figura_cargado`
