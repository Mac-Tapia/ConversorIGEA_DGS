# Una orden sobre un alimentador de otra fuente quedó lista sobre el alimentador vecino

## Síntoma
Al cerrar la spec 047, una orden con un código que no está en la fuente cargada, pero que se parece a otro, daba un plan listo para confirmar sobre el otro, sin una duda: pedir el 102 con el 101 cargado dejaba `alimentadores: [101]`. Lo mismo con los años en un nombre de proyecto. Y sin fuente cargada, una orden que escribe sobre una SET salía lista con un nombre sin comprobar. No llegó a ejecutarse: se halló probando el resolutor tarea por tarea, y el plan aún pedía confirmación.

## Causa
Comprobada en el código: `parecido` compara por semejanza de caracteres, y dos códigos que difieren en un dígito se parecen un 80 %, el corte de una errata. El aviso de contexto vinculado cubría alimentadores, proyecto y sistema, pero no la SET.

## Comprobación permanente
Dos nombres con números del mismo largo y distintos son dos entidades: no se reconocen como errata, sea cual sea el tipo. Un dígito omitido, un separador o las mayúsculas sí lo son. Toda tarea que escribe, con cualquier tipo de entidad, se recorre en las pruebas: sin contexto vinculado no queda lista, y un nombre ajeno no entra en sus datos.

## Prueba
- `tests/test_asistente_salida_estructurada.py::test_un_codigo_vecino_no_sustituye_al_pedido`
- `tests/test_asistente_salida_estructurada.py::test_la_errata_sigue_reconociendose`
- `tests/test_asistente_salida_estructurada.py::test_lo_que_escribe_sin_contexto_vinculado_no_es_ejecutable`
- `tests/test_asistente_salida_estructurada.py::test_ninguna_tarea_admite_una_entidad_ajena_al_contexto`
