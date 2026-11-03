# Con otra sesión en la GPU, la PINN no se promovía y el motivo era «falló la reapertura en un proceso nuevo: 2»

## Síntoma
`tests/test_digital_twin_oraculo.py` daba 25 de 25 con la GPU libre y seis fallos cuando otro proceso la ocupaba (`test_entrena_registra_y_promueve`,
`test_prediccion_con_incertidumbre_y_residuo`, `test_fuera_de_dominio_pide_digsilent`, `test_puertas_que_no_se_pasan_no_promueven`,
`test_la_puerta_real_rechaza_lo_que_no_mejora_la_fisica`, `test_volver_al_modelo_anterior`): el candidato del fixture no se promovía y las
demás pruebas no tenían modelo en uso. El motivo anotado era «falló la reapertura en un proceso nuevo: 2», sin decir por qué.

## Causa
Comprobada sin GPU, con un doble que toma la guardia común desde otro proceso. `oraculo.entrenar` no toma el turno de la GPU: lo hace quien lo
lanza (`tools/digital_twin_entrenar.py`), pero las pruebas lo llamaban directamente. La reapertura en otro proceso (043:RF-5) sí pide el turno
(`--reabrir-candidato`), y sin un token heredado (`entorno_hijo_gpu` solo lo pasa si este proceso es el dueño) lo encontraba ocupado y salía con
código 2 y `{"error": "GPU ocupada: otro proceso conserva la guardia"}`. `_decidir_promocion` leía el motivo en `error` y `motivo` del resultado, no
en el `payload` del hijo, y quedaba el código de salida.

## Comprobación permanente
El motivo de una reapertura fallida es el que da el hijo: con la guardia ajena dice «GPU ocupada». Toda prueba que entrena y reabre toma el turno
común, como un lanzador de `tools/`, con `apoyo.turno_gpu_esperando`: espera a que otra sesión lo suelte y, si no llega en su plazo
(`CSG_GPU_ESPERA_S`), falla diciendo «GPU ocupada». No se bajan puertas ni se promueve sin reapertura. Los lanzadores ya estaban vigilados por
`test_todo_lanzador_de_entrenamiento_toma_la_guardia`.

## Prueba
- `tests/test_experimentos_runner.py::test_reapertura_con_la_gpu_de_otro_dice_gpu_ocupada`
- `tests/test_experimentos_runner.py::test_con_el_turno_tomado_la_reapertura_lo_hereda`
- `tests/test_experimentos_runner.py::test_la_prueba_que_entrena_espera_su_turno`
