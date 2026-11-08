# Una referencia inválida no autoriza aplicar obras

## Síntoma

El arnés de aceptación podía llamar al escritor después de una lectura fallida de Caso base o Sin proyecto. Un archivo ausente, JSON inválido, otro proyecto/caso o reapertura no confirmada no detenían la aplicación. Tras retirar el ensayo solo releía Con proyecto, por lo que podía omitir cambios posteriores en las referencias.

## Causa

etapa_obras guardaba las dos lecturas iniciales sin validar código, PID, identidad y contenido antes del escritor. El retiro comprobaba el nombre exacto retirado y Con proyecto, pero no volvía a comparar Base/Sin. Un resumen guardado no sustituye las lecturas al recalcular los veredictos.

## Comprobación permanente

Reusar releida, comparar_lecturas y los nombres canónicos de caso para exigir referencias completas, finitas, reabiertas y del proyecto/carpeta/alimentadores pedidos. Si falla alguna, conservar lecturas crudas y motivos, escribir preflight rechazado, no generar plan de aplicación ni invocar escritor/web de obras, y terminar con error. Sin referencia válida no se inventan veredictos físicos.

Después del retiro exacto de la variación nueva, releer Base/Sin en procesos propios y comparar con sus lecturas anteriores. Recalcular esa conservación desde archivos al volver a dictaminar; no confiar en el resumen ok del manifiesto. Una diferencia deja el retiro y048sin cierre. No restaurar campos, diarios u obras originales de forma automática.

El cálculo físico, sus tolerancias y la decisión aceptada o rechazo eléctrico se conservan. Ningún doble de pruebas cierra la aceptación nativa; los modelos y datos sintéticos solo ensayan el contrato del arnés.

## Prueba

- `tests/test_verificacion_top_k_nativa.py::test_preflight_fallido_no_llama_escritor_y_conserva_motivos` (044:RF-9).
- `tests/test_verificacion_top_k_nativa.py::test_retiro_relee_y_contrasta_ambas_referencias` (048:RF-9).
- `tests/test_verificacion_top_k_nativa.py::test_preflight_rechazado_no_inventa_veredictos_y_conserva_049` (044/049:RF-9).
- `tests/test_verificacion_top_k_nativa.py::test_veredictos_recalculan_conservacion_sin_confiar_en_resumen` (048:RF-9).
- `tests/test_verificacion_top_k_nativa.py::test_ensayo_retira_solo_la_variacion_que_acaba_de_crear` conserva el retiro exacto y las demás variaciones (098:RF-36).

Evidencia externa p25_nativo_universal_preparacion_20261108/correctivo_arnes: RED30inicial, RED10postretiro y controles adicionales de PID/replay; corte final53pruebas puras,6nativas deseleccionadas explícitamente. Sin PF/GPU/SQL/instalación; no aceptación eléctrica/científica ni cierre de las omisiones nativas por este cambio.
