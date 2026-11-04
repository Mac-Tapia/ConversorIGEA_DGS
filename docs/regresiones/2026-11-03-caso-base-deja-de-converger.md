# Tras una calibración fallida, el «Caso base» dejó de converger

## Síntoma
El «Caso base» convergía antes de calibrar y dejó de converger después, y ese caso no debe cambiar.

## Causa
Causa sin confirmar. Se sabe que los casos comparten la red (spec 015): un cambio en la red, como un banco mal conectado de la calibración, también se ve desde el «Caso base». Lo confirmará la huella real, que es la T12 de la spec 081.

## Comprobación permanente
`comprobacion_flujo.huella_de_caso` y `comparar_huellas`: su flujo y sus cargas, antes y después de calibrar. Si cambió, sale el fallo grave con lo que cambió y el plan para volver a su huella, y el trabajo termina `parcial` sin parar lo demás. Desde 086 T11 el guion escribe `caso_base_huella` (`2026-11-04-huella-del-caso-base-sin-escribir.md`); queda confirmarlo en DIgSILENT, que es la T12.

## Prueba
- `tests/test_comprobacion_flujo.py::test_huella_que_cambio_dice_que_y_como_volver`
- `tests/test_comprobacion_flujo.py::test_huella_que_cambio_no_para_y_sale_parcial`
- `tests/test_comprobacion_flujo.py::test_huella_misma_si_nada_cambia`
