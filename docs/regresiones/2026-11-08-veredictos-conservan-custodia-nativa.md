# Recalcular un veredicto no vuelve nueva una captura alterada

## Síntoma

El subcomando de veredictos terminaba con código cero después de modificar un
testigo custodiado. El manifiesto adquiría la huella de los bytes nuevos, el commit
del recalculador y una fecha nueva; desaparecía la procedencia original. La
reproducción utiliza un archivo sintético y no acredita ejecución eléctrica.

## Causa

El comando asignaba commit, fecha y huellas antes del cálculo, tanto en una
captura como al revisar archivos existentes. No comprobaba la custodia anterior
y la ausencia del manifiesto se interpretaba como una primera captura legítima
incluso para el subcomando de revisión.

## Comprobación permanente

Antes de revisar o añadir otra etapa se comprueban esquema, inventario completo,
rutas y huellas anteriores. Una custodia ausente, incompleta o alterada devuelve
error sin llamar al cálculo o productor ni reescribir los archivos. La primera
captura requiere una carpeta vacía; una etapa ya capturada requiere otra carpeta
si se desea repetirla. Una etapa nueva conserva el origen previo y registra su
propia revisión de captura.

El recálculo conserva commit, fecha y huellas de captura. Su revisión y fecha se
registran separadamente, junto a la huella del manifiesto que se revisó. Antes de
publicar se verifica de nuevo la custodia y el manifiesto leído; la publicación
atómica evita truncar la custodia anterior ante un fallo de escritura. Estos
controles detectan alteraciones respecto del manifiesto disponible, no suplantan
una firma externa ni demuestran la aceptación física o científica. Las pruebas
nativas pendientes requieren su ejecución y relectura real autorizadas.

## Prueba

- `tests/test_verificacion_top_k_nativa.py::test_veredictos_rechazan_custodia_danada_sin_recertificar`
- `tests/test_verificacion_top_k_nativa.py::test_recalcular_con_otra_revision_conserva_procedencia_de_captura`
- `tests/test_verificacion_top_k_nativa.py::test_veredictos_sin_manifiesto_no_inventan_primera_captura`
- `tests/test_verificacion_top_k_nativa.py::test_captura_previa_danada_bloquea_otra_etapa`
- `tests/test_verificacion_top_k_nativa.py::test_primera_captura_y_etapa_posterior_preservan_origen`
- `tests/test_verificacion_top_k_nativa.py::test_primera_captura_no_sella_ficheros_previos_sin_custodia`
- `tests/test_verificacion_top_k_nativa.py::test_revision_no_publica_si_la_lectura_cambia_durante_el_calculo`
- `tests/test_verificacion_top_k_nativa.py::test_fallo_publicacion_conserva_manifiesto_y_no_deja_temporal`
- `tests/test_verificacion_top_k_nativa.py::test_captura_existente_no_se_sobrescribe`
