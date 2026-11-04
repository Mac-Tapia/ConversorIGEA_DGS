# Guardar en otra unidad o en una ruta de red falla al final de la corrida

## Síntoma
Mensaje medido, con `Z:/` y con una ruta UNC: «Configure una raíz runtime o caché en el volumen del destino para publicar».

## Causa
`staging_para` solo conocía las raíces de ejecución y de caché, y publicar por cambio de nombre exige el mismo volumen.

## Comprobación permanente
Si ninguna raíz está en el volumen del destino, el temporal va junto al destino; en su volumen, sigue en la raíz y fuera del código (065:RF-11).

## Prueba
- `tests/test_datos_duraderos.py::test_otra_unidad_o_ruta_de_red_publica_junto_al_destino`
- `tests/test_datos_duraderos.py::test_escribir_de_verdad_con_el_destino_en_otro_volumen`
