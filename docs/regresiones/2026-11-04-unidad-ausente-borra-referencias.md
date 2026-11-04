# Abrir un espacio con la unidad desconectada borra sus referencias para siempre

## Síntoma
Con los ficheros de una unidad ausente, `Workspace.load` devolvía las entradas y la demanda vacías, y al guardar quedaban vacías también en disco: al volver la unidad, el espacio ya no sabía de ellas. Lo mismo la ejecución activa, si no se encontraba su carpeta.

## Causa
La regla heredada de la interfaz de escritorio de no restaurar una ruta que no existe se aplicaba al cargar, y lo no restaurado no se volvía a escribir.

## Comprobación permanente
Lo que apunta a un fichero ausente queda en `no_disponibles`, fuera de los campos que se dan por existentes; `save` lo vuelve a escribir tal cual, `public` lo muestra y se repone solo cuando vuelve, incluso con la web abierta. Solo lo olvida una decisión del operador: otra entrada, quitarla o descartarla.

## Prueba
- `tests/test_datos_duraderos.py::test_unidad_ausente_no_borra_las_referencias_al_guardar`
- `tests/test_datos_duraderos.py::test_la_unidad_que_vuelve_con_la_web_abierta_repone_lo_suyo`
- `tests/test_datos_duraderos.py::test_la_ejecucion_activa_sin_su_carpeta_tampoco_se_pierde_al_guardar`
- `tests/test_datos_duraderos.py::test_descartar_por_api_y_aviso_en_el_espacio`
