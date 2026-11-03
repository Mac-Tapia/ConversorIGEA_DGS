# El oráculo daba otra tensión que DIgSILENT y le quitaba demanda a una red sana

## Síntoma
Un alimentador con 3 bancos se importó con el 43 % de su demanda porque el oráculo daba 0,80 p.u., donde DIgSILENT daba 0,93 con esa misma carga. Otro, con ramales monofásicos, se importó a 0,79 p.u. con el oráculo diciendo 0,80.

## Causa
Causa comprobada contra DIgSILENT: el flujo del oráculo era equilibrado y no calculaba los bancos. También se saltaba sin decirlo las SED, cargas y maniobras sin barra, y un solo tramo sin impedancia dejaba sin calcular el alimentador. Además, `runpp_3ph` declara convergencia con todas las tensiones en nan.

## Comprobación permanente
`red_pandapower` informa `recuento`, por clase, y da el error `omitido_en_la_red` si el modelo y la red no cuadran. Lo incompleto se calcula como se puede y se anota. Con menos de tres fases el veredicto sale del flujo desequilibrado, y una barra alimentada sin tensión es no convergencia. Los reguladores llevan su impedancia serie (X = uk·Un/In), que faltaba y daba 0,92 puntos de error. El contraste con DIgSILENT es la tarea `[DIgSILENT]` T4 de la spec 082, ya cumplida; la T5 mide un catálogo con R0 distinta de R1.

## Prueba
- `tests/test_oraculo_por_fases.py::test_todas_las_clases_entran_en_la_red`
- `tests/test_oraculo_por_fases.py::test_un_tramo_imposible_se_calcula_como_conexion_y_sigue_el_error`
- `tests/test_oraculo_por_fases.py::test_un_nodo_sin_definir_entra_sin_alimentar_y_se_dice`
- `tests/test_oraculo_por_fases.py::test_un_banco_entrega_su_potencia_y_fuera_de_servicio_no`
- `tests/test_oraculo_por_fases.py::test_con_monofasicos_el_veredicto_es_del_desequilibrado`
- `tests/test_oraculo_por_fases.py::test_una_convergencia_sin_tensiones_no_es_convergencia`
- `tests/test_oraculo_por_fases.py::test_un_regulador_tiene_impedancia_y_no_cuenta_como_tramo`
