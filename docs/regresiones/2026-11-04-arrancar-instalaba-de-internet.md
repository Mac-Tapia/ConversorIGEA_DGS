# Arrancar el programa instalaba de internet

## Síntoma
`run_gui.bat` ejecutaba `pip install -r requirements.txt` si faltaba una dependencia, y `npm ci` si el front estaba desfasado. Sin red, el acceso directo fallaba a medias; con red, una versión nueva de un paquete sin fijar cambiaba el programa sin que nadie lo decidiera.

## Causa
Comprobada leyendo el lanzador: preparar el entorno era parte de arrancar. Valía en un árbol de desarrollo, y nada lo separaba de un puesto de cliente.

## Comprobación permanente
Instalar solo se hace al instalar: `tools/instalar_candidato.py` usa `pip --no-index --require-hashes` contra un lock con una huella por rueda, tras comprobar cada fichero contra el manifiesto del candidato. El lanzador del producto lo escribe el instalador y no contiene ninguna orden de instalar. `run_gui.bat`, el de desarrollo, dice qué falta y cómo instalarlo, y sigue compilando el front, que no sale a internet.

## Prueba
- `tests/test_instalacion_programa.py::test_arrancar_no_instala`
- `tests/test_instalacion_programa.py::test_instala_sin_red_y_con_huellas`
- `tests/test_instalacion_programa.py::test_candidato_alterado_no_se_instala`
- `tests/test_auditoria_raiz.py::test_sin_paquetes_del_front_no_los_instala_al_arrancar`
- `tests/test_auditoria_raiz.py::test_sin_el_vigilante_no_arranca_una_web_degradada`
