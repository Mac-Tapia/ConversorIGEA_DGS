# El informe usaba el flujo de otra corrida o se quedaba sin el de su alimentador

## Síntoma
Con «Con proyecto» cancelado, agotado o fallido, el informe de factibilidad salía `factible` con el flujo de la corrida anterior, y nada lo decía. Reproducido con doble en `086 T10`, en los tres modos. El informe de estudio llevaba también esa etapa vieja. A la inversa, con AL01 estudiado y después AL02, el informe de AL01 decía que no había flujo. Un informe de flujo truncado hacía fallar el informe entero con un error de JSON.

## Causa
`_ultimo_estudio` tomaba el último `estudio_<caso>_flujo_*.json` por fecha, sin mirar el alimentador. Lo que no termina no deja fichero, así que «no terminó» no se distinguía de «no hay», y el flujo desequilibrado y el equilibrado podían ser de corridas distintas.

## Comprobación permanente
`estudios_ejecutar` registra su corrida en `estudios_corrida_<token>.json` desde que empieza y la actualiza tras cada estudio; `_corrida_del_alimentador` elige la última que pidió flujos de ese alimentador, y `_ultimo_estudio` solo lee de ella. Lo que falta se entrega sin convergencia, con `AVISO` en el Word y en los huecos de la web (`_avisos_de_la_corrida`), nunca con un flujo anterior. Los flujos guardados sin registro se siguen usando, por alimentador, y el informe dice que no están ligados a ninguna corrida. La regla de la cabecera del desequilibrado (063:RF-45) sigue igual.

## Prueba
- `tests/test_informe_corrida.py::test_estudio_con_proyecto_sin_terminar_no_usa_la_corrida_anterior`
- `tests/test_informe_corrida.py::test_factibilidad_con_obras_sin_terminar_nunca_factible`
- `tests/test_informe_corrida.py::test_estudio_con_la_web_caida_a_media_corrida`
- `tests/test_informe_corrida.py::test_el_desequilibrado_no_se_mezcla_con_el_de_otra_corrida`
- `tests/test_informe_corrida.py::test_informe_del_alimentador_pedido_no_de_la_ultima_corrida`
- `tests/test_informe_corrida.py::test_sin_registro_de_corrida_mira_el_alimentador_y_lo_dice`
- `tests/test_informe_corrida.py::test_regla_del_desequilibrado_que_no_cuadra_dentro_de_la_corrida`
