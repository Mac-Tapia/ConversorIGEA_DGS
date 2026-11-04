# La web mandaba reconvertir para llevar el catálogo al DGS, y el DGS seguía igual

## Síntoma
Hallado en la revisión de la spec 076 (filas `operacion_web-031` y `catalogo_parametros-003`): al subir el catálogo corregido, el Registro y la pantalla decían «Reconvierta para llevarlo al DGS.». Al reconvertir, el DGS salía con los mismos parámetros. Al quitarlo, la confirmación decía que las próximas conversiones volverían a los valores del export, que nunca habían dejado de usar.

## Causa
Comprobada en el código: 032:RF-2 dejó `Reglas.aplicar_fichas` en False, y `aplicar_reglas` solo aplica las correcciones con esa regla activa. Las fichas entran al calibrar «Sin proyecto» (032:RF-14). Las frases del aviso quedaron de antes, copiadas en el servidor y en la pantalla.

## Comprobación permanente
El aviso es una sola frase, `AVISO_CATALOGO_APLICADO`, que devuelve `apply_catalog` y que escriben el Registro y la pantalla. Una prueba ata esa frase a las reglas: mientras no se apliquen fichas al convertir, no puede mandar reconvertir (081:RF-70). Las filas del conjunto de la 076 que citaban la frase antigua se revisaron, porque su ancla ya falla si desaparece. Lo que se ve en el navegador queda en la tarea `[DIgSILENT]` T22 de la spec 081.

## Prueba
- `tests/test_aviso_catalogo.py::test_el_aviso_no_manda_reconvertir_porque_el_dgs_no_aplica_fichas`
- `tests/test_aviso_catalogo.py::test_subir_el_catalogo_registra_y_devuelve_el_aviso`
- `tests/test_aviso_catalogo.py::test_la_pantalla_no_repite_un_aviso_propio`
