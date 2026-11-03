# Una orden de limpiar un proyecto borró una SET nueva de otro

## Síntoma
La orden era revisar que no quedara una SET nueva en un proyecto donde no correspondía. Se aplicó también a otro, y desapareció su variación con la obra planificada para sus cargas nuevas: «no debiste eliminarlo». No se pudo recuperar por la API y hubo que recrearla desde la web.

## Causa
Comprobada: el borrado se hizo con una sonda a mano, y nada en el conversor comparaba el proyecto del objeto con el de la orden.

## Comprobación permanente
`pf_arnes.borrar_en_su_proyecto` no ejecuta `Delete` fuera del proyecto de la orden y lo usa lo que el operador ordena deshacer. El asistente no ejecuta una orden de borrar. Cada `Delete` del código está justificado en una lista que la prueba compara con el código. Una sonda a mano puede saltársela: eso sigue siendo regla de proceso.

## Prueba
- `tests/test_seis_reglas.py::test_borrar_solo_en_el_proyecto_de_la_orden`
- `tests/test_seis_reglas.py::test_el_asistente_no_borra`
- `tests/test_seis_reglas.py::test_deshacer_y_eliminar_no_borran_lo_de_otro_proyecto`
- `tests/test_seis_reglas.py::test_cada_borrado_en_digsilent_esta_justificado`
