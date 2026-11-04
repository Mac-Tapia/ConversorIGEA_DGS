# Mover o renombrar la carpeta deja los espacios sin sus ficheros, o los datos atrás

## Síntoma
Tras mover la carpeta de datos, las entradas subidas no se encontraban y se perdían al guardar. Tras renombrar la carpeta del programa, la identidad y la raíz de datos cambiaban: medido, dos hashes distintos para el mismo programa.

## Causa
Las rutas de dentro del espacio se guardaban absolutas, y la identidad era un hash de la ruta del programa.

## Comprobación permanente
Las rutas de dentro se guardan como `espacio:<relativa>`, salvo los vínculos y el inventario, que llevan su huella; al migrar, las absolutas de un espacio ya movido se recolocan por el componente con su identificador. La identidad se escribe una vez en `.convertersmartgrid-instalacion.json`, junto al programa porque desde ahí se calcula la raíz: la instalación existente conserva su hash y su raíz, sin mover nada.

## Prueba
- `tests/test_datos_duraderos.py::test_mover_la_carpeta_de_datos_conserva_los_espacios`
- `tests/test_datos_duraderos.py::test_espacio_de_la_version_2_ya_movido_recupera_sus_rutas`
- `tests/test_datos_duraderos.py::test_renombrar_la_carpeta_no_cambia_la_identidad`
- `tests/test_datos_duraderos.py::test_instalacion_existente_conserva_su_raiz_al_fijar_identidad`
- `tests/test_datos_duraderos.py::test_retencion_ve_las_referencias_relativas`
