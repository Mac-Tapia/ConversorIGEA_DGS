# Un programa antiguo rebaja y estropea el espacio de una versión más nueva

## Síntoma
Un `workspace.json` de la versión 99 se abría sin aviso, y al guardar quedaba en la versión 2 sin los campos que no conocía.

## Causa
`load` no miraba la versión, y `save` escribía siempre la suya.

## Comprobación permanente
La versión se lee y se compara: una futura no se abre ni se escribe, también si otro proceso la actualizó con el espacio abierto, y se lista como `version_futura` con su motivo. Las anteriores migran por pasos numerados en `MIGRACIONES`, con una copia `workspace.v<N>.json` previa que no se pisa.

## Prueba
- `tests/test_datos_duraderos.py::test_version_futura_no_se_sobrescribe_y_lo_dice`
- `tests/test_datos_duraderos.py::test_migra_con_copia_previa_y_por_pasos`
- `tests/test_datos_duraderos.py::test_un_paso_que_falla_no_toca_el_fichero`
