# Un corte de luz puede dejar un fichero de estado vacío o a medias

## Síntoma
Con `write_json_atomic` no había ninguna llamada a `fsync`: medido, cero llamadas al guardar. El proceso que muere no daña nada, porque el nombre se cambia al final, pero un corte de luz sí puede dejar un fichero vacío.

## Causa
Escribir y cambiar el nombre no garantiza el orden en disco: el sistema puede grabar el cambio de nombre antes que los datos. Causa comprobada en el código; el corte real es la T33 de la spec 086.

## Comprobación permanente
`util.publicar_duradero` sincroniza antes de sustituir y es la vía del estado: espacios, registro de vínculos, manifiestos de ejecución y lo del asistente. El registro de solo añadir también sincroniza.

## Prueba
- `tests/test_datos_duraderos.py::test_fsync_antes_de_sustituir_el_fichero`
- `tests/test_datos_duraderos.py::test_registro_de_vinculos_y_almacen_tambien_sincronizan`
- `tests/test_datos_duraderos.py::test_matar_el_proceso_a_mitad_de_guardar_deja_un_espacio_legible`
