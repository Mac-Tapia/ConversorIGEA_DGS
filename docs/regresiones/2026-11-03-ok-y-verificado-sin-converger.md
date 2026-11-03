# La web decía «OK» y «VERIFICADO» sin que el flujo convergiera

## Síntoma
La línea del trabajo decía «OK … convergencia» y el «Caso base», `VERIFICADO`, en un proyecto que DIgSILENT no calculó.

## Causa
Tres señales leían el flujo cada una a su manera: el código de salida del guion, que solo mira `errors`; `convergence_pass`, escondido en una columna; y `classify_convergence`, que solo miraba un dato nulo en esa vía. Corregido en la spec 078.

## Comprobación permanente
`powerfactory_metadata.estado_flujo` es la única lectura; la spec 081 le añade si está limpio y qué se corrigió.

## Prueba
- `tests/test_senales_de_convergencia.py::test_importacion_que_no_calcula_no_dice_ok`
- `tests/test_senales_de_convergencia.py::test_caso_base_verificado_solo_con_flujo_convergido`
- `tests/test_comprobacion_flujo.py::test_flujo_sin_servir_no_sale_limpio`
