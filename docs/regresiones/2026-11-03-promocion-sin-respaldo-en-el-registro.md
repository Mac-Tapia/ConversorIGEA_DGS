# La PINN se promovía sin reabrirse y las promociones de pronóstico salían «sin evidencia» en la web

## Síntoma
Al cerrar la spec 043, leyendo el código contra sus requisitos. La PINN pasaba a estar en uso con solo sus puertas: `oraculo.entrenar` movía `promovido.json` sin abrir el candidato en otro proceso y sin anotar su decisión en el registro común. En la tabla de modelos, una promoción real del pronóstico salía como «promoción sin evidencia verificable: sin candidato activo coincidente». Y el coordinador podía dar `PROMOVIDO` a un trabajador que lo decía sin candidato alguno. Ninguno llegó a un operador con un modelo roto: no consta ese caso, pero nada lo impedía.

## Causa
Comprobada en el código. La PINN era la única familia con promoción propia. El pronóstico anota en `pronostico_cabecera` y `pronostico_cliente` (046) y la web lo buscaba en `gru`. `_subproceso` guardaba `candidate_id` solo dentro de `result`, y la web lo leía en la etapa, de modo que nunca coincidía con el activo.

## Comprobación permanente
La PINN pasa por `_decidir_promocion`: reapertura en otro proceso, decisión en el registro y, solo entonces, el puntero; sin decisión anotada no hay promoción. `registros_de` dice en qué nombres del registro anota cada familia. El coordinador rebaja a `RECHAZADO` un `PROMOVIDO` sin candidato. Toda llamada que entrena desde `tools/` ha de estar dentro del turno de GPU, y una prueba recorre el código de los lanzadores para exigirlo. La reapertura correcta en CUDA de cada familia sigue en la 043 T9.

## Prueba
- `tests/test_experimentos_runner.py::test_pinn_no_reabierta_no_se_promueve`
- `tests/test_experimentos_runner.py::test_pinn_aprobada_queda_en_el_registro_y_en_su_puntero`
- `tests/test_experimentos_runner.py::test_smoke_fallido_no_promueve`
- `tests/test_experimentos_runner.py::test_runner_no_acepta_promovido_sin_candidato`
- `tests/test_modelos_web.py::test_el_pronostico_se_ve_en_la_familia_gru`
- `tests/test_training_coordinator.py::test_todo_lanzador_de_entrenamiento_toma_la_guardia`
