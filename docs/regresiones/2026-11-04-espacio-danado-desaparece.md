# Un espacio con el fichero dañado desaparece de la lista, sin decir nada

## Síntoma
Con un `workspace.json` truncado, `store.list()` no lo devolvía y `store.get()` daba `None`: la web respondía «Espacio de trabajo no encontrado». Con `conversiones.json` dañado se leía vacío, y el siguiente guardado pisaba lo que quedaba.

## Causa
Los dos sitios capturaban el error de lectura y seguían; no existía ninguna copia de la versión anterior a la que volver.

## Comprobación permanente
Cada guardado deja `<nombre>.bak` con la versión anterior, y un fichero dañado nunca pisa esa copia. El espacio se lista como `danado`, con su motivo y si se puede restaurar; abrirlo da 409 con el motivo, y `POST /api/workspaces/{id}/restaurar-copia` lo recupera apartando lo dañado sin borrarlo.

## Prueba
- `tests/test_datos_duraderos.py::test_json_danado_se_ve_y_se_restaura`
- `tests/test_datos_duraderos.py::test_un_fichero_danado_no_pisa_la_copia_que_lo_arregla`
- `tests/test_datos_duraderos.py::test_conversiones_danadas_recuperan_su_copia`
- `tests/test_datos_duraderos.py::test_api_de_un_espacio_danado`
