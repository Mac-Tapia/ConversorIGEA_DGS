# La comparación de la revisión por roles salió sin respuesta en 23 de 24 revisiones

## Síntoma
Medida con un LLM real que razona: rol único 11 de 12 sin respuesta, equipo 12 de 12, con unos 505 tokens de salida por intervención frente a un tope de 512 y unos 24 s por caso. El informe solo decía `sin_respuesta`.

## Causa
Causa sin confirmar con una respuesta capturada, porque el informe no guardó el texto. Comprobado: el modelo declara la capacidad `thinking` en `/api/show`, el adaptador no enviaba `think`, y la evaluación de T6 ya medía ese modelo «sin pensamiento». Las cifras de tokens encajan con un razonamiento que agota `num_predict` antes de escribir el JSON. Lo confirmará la nueva medición, cuyo informe guarda el motivo de cada fallo.

## Comprobación permanente
La revisión pide `think: false` en cada intervención, y la configuración del cliente no lo reabre. Toda respuesta no reconocida guarda en el dictamen y en el informe qué devolvió Ollama: vacía tras razonar, JSON cortado en el tope o no válido, con su inicio. Un fallo así nunca cuenta como defecto hallado.

## Prueba
- `tests/test_asistente_revision_roles.py::test_respuesta_no_reconocida_guarda_el_motivo_en_el_informe`
- `tests/test_asistente_revision_roles.py::test_la_revision_pide_sin_razonar_sea_cual_sea_el_cliente`
- `tests/test_asistente_revision_roles.py::test_un_revisor_que_no_responde_no_cuenta_como_deteccion`
