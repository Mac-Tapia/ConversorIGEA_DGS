# Las pruebas ML no sustituyen los recibos de campañas ejecutadas

## Síntoma

La edición completa añadía las pruebas ML a las puertas del núcleo, pero no exigía
recibos de campañas. El resumen no materializaba las identidades de datos y
modelos ni distinguía sus estados de implementación, pruebas y aceptación.

## Causa

El plan de comprobaciones solo incorporaba una suite de pruebas adicional. No
existía una entrada explícita de recibos ni un contraste de su cobertura con el
contrato canónico de familias y operaciones.

## Comprobación permanente

La edición completa exige un recibo por cada familia canónica, mediante la opción
repetible `--campana FAMILIA RUTA SHA256`. La lista se deriva del contrato del arnés.
El SHA indicado corresponde a los bytes del archivo, distinto de su sello interno.
No hay un selector para recortarla ni búsqueda del archivo más reciente. El lector
canónico comprueba sobre, sello, configuración y cobertura. La guarda de lectura
existente conserva los bytes mientras se valida cada recibo; sus SHA se comprueban
antes y después. Los conteos deben ser enteros reales, nunca booleanos.

Una campaña admitida exige modo runtime y operaciones completas con evidencia
de ejecución declarada. Contrato y replay permanecen como diagnóstico y bloquean
esa puerta. Un estado de promoción aislado, un resumen resellado con operaciones
ausentes o un recibo alterado tampoco la aprueban. Se revalidan los recibos después
de las demás puertas, sin ejecutar proveedores, entrenamiento ni motores.

El resultado conserva revisión de captura, ejecución, datos, modelos, artefactos
declarados y operaciones. Si cambia un recibo, mantiene las identidades leídas al
inicio y señala el fallo posterior. Los inventarios de datos del backend se
enlazan por ruta y SHA sin copiar fuentes. Implementación declarada, pruebas y
aceptación son estados distintos; leer un reporte no certifica verdad científica,
física, operación ni promoción. Esas aceptaciones continúan en falso.

Las pruebas positivas son dobles CPU del contrato del validador. No acreditan una
campaña real ni cierran las siete etapas de aprendizaje o las aceptaciones nativas.

## Prueba

- `tests/test_verificar_entrega_integral.py::test_completa_sin_recibos_no_aprueba_solo_por_tests_ml`
- `tests/test_verificar_entrega_integral.py::test_recibos_integros_resumen_origen_modelos_y_operaciones_sin_certificar`
- `tests/test_verificar_entrega_integral.py::test_recibos_faltantes_alterados_o_incompletos_bloquean`
- `tests/test_verificar_entrega_integral.py::test_recibo_contract_o_replay_es_diagnostico_no_campana_ejecutada`
- `tests/test_verificar_entrega_integral.py::test_recibo_no_puede_cambiar_mientras_se_valida`
- `tests/test_verificar_entrega_integral.py::test_cli_materializa_estados_y_revalida_recibos_tras_las_puertas`
- `tests/test_verificar_entrega_integral.py::test_backend_enlaza_inventarios_de_datos_por_sha_sin_recopiar_fuentes`
