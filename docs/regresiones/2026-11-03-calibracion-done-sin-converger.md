# «Calibración: done» con alimentadores que no convergen

## Síntoma
El trabajo terminó `done` con la mayoría de los alimentadores del sistema en `NO_CONVERGE`. Había que leer cada informe para saberlo.

## Causa
`JobManager._run` daba `done` a todo trabajo que no lanzara una excepción: el resultado no contaba.

## Comprobación permanente
`comprobacion_flujo.veredicto_calibracion` da `parcial` o `no_converge`, con la lista por alimentador y su motivo. `parcial` y `no_converge` son estados del trabajo, en la API, la vigilancia, el asistente, `tools/sistema_web.py` y la interfaz; terminan con su resultado y no paran nada de lo que sigue. También las recalibraciones y las importaciones. Verlo en el navegador es la T13 de la spec 081.

## Prueba
- `tests/test_comprobacion_flujo.py::test_trabajo_calibracion_con_alguno_sin_converger_es_parcial`
- `tests/test_comprobacion_flujo.py::test_trabajo_calibracion_sin_ninguno_es_no_converge`
- `tests/test_comprobacion_flujo.py::test_trabajo_termina_con_su_estado_y_su_resultado`
- `tests/test_comprobacion_flujo.py::test_trabajo_recalibrar_con_fallos_es_parcial`
