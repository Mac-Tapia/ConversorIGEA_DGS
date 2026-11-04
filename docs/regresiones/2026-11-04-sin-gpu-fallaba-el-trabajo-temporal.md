# Sin GPU fallaba el trabajo del gemelo temporal

## Síntoma
En un equipo sin CUDA, `modelo_temporal()` lanzaba `SinGPU` y el trabajo fallaba entero. Reproducido el 2026-11-04 sobre `7fd3780f`.

## Causa
Solo se contemplaba la falta de PyTorch, y esa se callaba.

## Comprobación permanente
Sin GPU o sin memoria en ella sigue el modelo estacional, que no entrena, con su aviso en el resultado y el Registro. La GRU nunca cae a la CPU. Un error que no sea de la GPU sigue siendo un fallo: `test_un_error_de_verdad_no_se_tapa_de_estacional`.

## Prueba
- `tests/test_edicion_producto.py::test_el_modelo_temporal_sin_gpu_sigue_con_aviso_y_sin_cpu`
- `tests/test_edicion_producto.py::test_si_la_gpu_se_queda_sin_memoria_entrenando_sigue`
- `tests/test_edicion_producto.py::test_un_error_de_verdad_no_se_tapa_de_estacional`
- `tests/test_edicion_producto.py::test_el_trabajo_temporal_termina_sin_gpu_y_lo_avisa`
