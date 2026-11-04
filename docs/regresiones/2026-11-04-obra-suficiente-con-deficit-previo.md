# La obra elegida por la escalera salía como insuficiente en el informe, por una barra que ya estaba baja

## Síntoma
La escalera eligió la obra de un alimentador: la carga nueva quedó a 0,963 p.u. y la mínima de media tensión a 0,9449 p.u., en una barra de ramal, con límite 0,95. El informe de factibilidad concluía «Las obras evaluadas son insuficientes» y pedía corregir ese ramal. Con el mismo dato, nada separaba lo que causaba la carga de lo que ya estaba fuera de límites, y la evaluación solo guardaba la mínima, sin la barra ni su tensión previa.

## Causa
Dos criterios sobre el mismo flujo. `escalera_optima.cumple` (025:RF-50) comprueba la barra de cada carga nueva y que ninguna otra salga de límites ni empeore más que la tolerancia frente a «Sin proyecto»: una barra ya baja que no empeora pasa. `conclusion_factibilidad` miraba solo la mínima y los nodos fuera del caso con obras, sin comparar con el estado previo. Comprobado en el código; la confirmación en DIgSILENT queda en las corridas de la F6 de la spec 086.

## Comprobación permanente
`informes.clasificar_bajo_limite` reparte cada barra bajo el límite en causada, déficit previo o sin comparación, con la regla misma de la escalera, y una prueba sorteada comprueba que coincide con `cumple`. La evaluación guarda solo esas barras por variante (`bajo_limite`), y el informe las calcula de las medidas de sus estudios. Sirve para todo alimentador y toda fuente. La obra sigue suficiente solo si lo único fuera son barras que la carga no causa: una sobrecarga, una sobretensión o una barra de carga nueva baja no se disculpan. Mientras quede una de esas barras, ni el Word, ni el libro, ni la web dicen que el alimentador quede en la banda: `con_obras_deficit` lo dice con cada barra y su tensión. Sin la tensión previa se dice «sin comparación disponible», sin afirmar que sea previa.

## Prueba
- `tests/test_deficit_previo.py::test_barra_baja_que_no_empeora_es_deficit_previo_con_su_barra_y_tension`
- `tests/test_deficit_previo.py::test_barra_que_empeora_no_es_previa`
- `tests/test_deficit_previo.py::test_sin_dato_de_la_barra_no_se_afirma_que_sea_previa`
- `tests/test_deficit_previo.py::test_la_clasificacion_dice_lo_mismo_que_el_criterio_de_la_escalera`
- `tests/test_deficit_previo.py::test_conclusion_factible_con_barra_baja_que_no_empeora`
- `tests/test_informe_docx.py::test_factibilidad_lista_el_deficit_previo_con_su_barra_y_tension`
- `tests/test_informe_corrida.py::test_factibilidad_por_la_web_lista_el_deficit_previo`
- `tests/test_obras_pf_guion.py::test_evaluar_guarda_solo_las_barras_bajas_de_cada_variante`
- `tests/test_casos_por_anio.py::test_la_escalera_dice_las_barras_bajas_de_la_obra_que_elige`
