# Una empresa nueva no tenía informe, y lo entregado llevaba convenciones de otra

## Síntoma
Con un perfil vacío el informe de estudio se negaba: «falta en el perfil de empresa informes.modelo_estudio, informes.bandas_tension_pct…». Con perfil, los dos informes y la pantalla rotulaban una moneda fija; el catálogo escribía 22,9 kV si nadie daba la tensión, y el mapa traía como constantes las bandas de un modelo de una empresa. Los nombres y las tensiones de una red concreta salían como ejemplo en la web, y el contrato VNR-GIS llevaba una ruta de una máquina.

## Causa
Comprobada en la revisión base `7fd3780f` (reproducción con `informes.ConfigInforme`, `catalog.construir_hojas` y `mapa_informe`): la primera empresa fue también el único caso, y nada comparaba lo entregado con una lista de términos.

## Comprobación permanente
`tools/comprobar_entrega.py` recorre lo que dice `config/entrega.json` con los términos de los perfiles excluidos, las huellas con sal y la lista local, y rechaza un candidato con un término, un peso o un fichero de datos. La moneda y las bandas salen del perfil; sin modelo sale la plantilla neutra y se dice.

## Prueba
- `tests/test_entrega_universal.py::test_nucleo_y_web_sin_terminos_en_el_codigo`
- `tests/test_entrega_universal.py::test_sin_modelo_sale_con_la_plantilla_neutra_y_lo_dice`
- `tests/test_entrega_universal.py::test_ninguna_moneda_fija_en_el_codigo`
- `tests/test_entrega_universal.py::test_candidato_con_el_nombre_de_una_empresa_se_rechaza`
