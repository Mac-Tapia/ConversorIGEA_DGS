# Una carga de más de un MW quedó como ampliación de una SED mínima y el flujo no convergía

## Síntoma
«Cargas nuevas» no convergía tras aplicar el bloque.

## Causa
Comprobada: la cercanía a 30 m bastaba para tomar la fila como ampliación, aunque su demanda pasara muchas veces del transformador de la SED.

## Comprobación permanente
La fila cercana que no cabe en el transformador es SED nueva con el suyo, y se dice (042:RF-26).

## Prueba
- `tests/test_cargas_pf.py::test_la_fila_cercana_que_no_cabe_en_la_sed_es_sed_nueva`
