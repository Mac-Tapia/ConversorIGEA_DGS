# La guarda de la huella del «Caso base» no actuaba nunca

## Síntoma
`revisar_huellas` lee `caso_base_huella` del informe de la calibración, pero ningún guion la escribía: un «Caso base» cambiado por la calibración no daba el fallo grave. Reproducido corriendo el guion contra `fake_pf`: el informe no traía la clave.

## Causa
La spec 081 dejó el contrato con doble y la escritura real en su T12, que quedó pendiente de DIgSILENT. Las pruebas pasaban porque ponían la clave a mano.

## Comprobación permanente
`tools/ajuste_cabecera_pf.py` toma la huella antes de escribir nada, una vez y tras fijar la consigna, que el «Caso base» lleva a propósito (063:RF-29), y la vuelve a tomar al terminar, también si la calibración falló. Va en el primer informe del proyecto, y al navegador solo su resumen. Si no se puede leer, se avisa y se calibra. `comparar_huellas` no da por cambio lo que difiere el kW de dos flujos dentro de su ruido. Que la huella real sea igual antes y después se comprueba en DIgSILENT: 081 T12, corridas F6.

## Prueba
- `tests/test_huella_caso_base.py::test_una_calibracion_buena_escribe_la_misma_huella`
- `tests/test_huella_caso_base.py::test_el_caso_base_que_cambia_activa_la_guarda`
- `tests/test_huella_caso_base.py::test_con_los_bancos_la_huella_de_antes_es_la_de_la_primera_pasada`
- `tests/test_huella_caso_base.py::test_si_no_se_puede_leer_lo_dice_y_calibra`
- `tests/test_huella_caso_base.py::test_un_flujo_que_difiere_por_debajo_de_su_tolerancia_no_es_un_cambio`
