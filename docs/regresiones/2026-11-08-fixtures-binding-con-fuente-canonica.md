# Las pruebas de binding no alcanzaban sus informes

Specs 034 RF-21, 065 RF-6/RF-7 y 018 RF-9/RF-12: identidad de fuente y evidencia actual.

## Síntoma

Veinte casos de binding, informe actual y ejecución fuente fallaban antes de
alcanzar la frontera que pretendían comprobar. Unos recibían
`SOURCE_SELECTION_CHANGED`; otros intentaban reabrir un manifiesto sin archivos
custodiados. Varias negativas anteriores podían aprobar por un esquema inválido.

## Causa

Las fixtures asignaban identidad y huella manuales con instantáneas incompletas,
sin selección coherente, o escribían un manifiesto con `files: []` y huella
inventada. Esas preparaciones eran incompatibles con el contrato de custodia.
También ocultaban la causa real de un informe ajeno o alterado.

## Comprobación permanente

Un helper de pruebas compartido genera TXT sintéticos con `write_export` y usa
`set_input`, `load_dataset` y `convert`. La selección, recibo, run, huella, DGS y
sidecar proceden de esa ejecución. Los consumidores de importación, informe y
binding comparten este productor; los helpers nativos existentes se conservan.

La recuperación histórica reabre el Workspace real y compara bytes del DGS,
sin suplantar el lector de metadata. La negativa de otra huella parte de dos
fuentes válidas distintas. Los informes ajenos o alterados alcanzan el guion
falso y exigen sus motivos específicos, manteniendo intactos el resultado y
las evidencias previas cuando se rechazan.

## Prueba

- `tests/test_powerfactory_fresh_report.py::test_informe_actual_o_nada_de_mutacion`
- `tests/test_powerfactory_binding.py::test_018_rf9_rf10_espacio_nuevo_usa_la_ejecucion_con_la_que_se_acepto`
- `tests/test_powerfactory_binding.py::test_018_rf10_ejecucion_con_otra_huella_no_se_usa`
- `tests/test_powerfactory_source_run.py::test_same_name_historical_dgs_is_rejected`
- `tests/test_powerfactory_source_run.py::test_exact_active_source_run_is_accepted`
- `tests/test_senales_de_convergencia.py::test_fixture_importacion_custodia_la_fuente_convertida`
- `tests/test_senales_de_convergencia.py::test_fixture_importacion_cambiada_bloquea_antes_del_guion`

Evidencia roja y verde en `p25_g2_binding_fixtures_20261108`, bajo la implementación
externa del diagnóstico de producción. La migración reveló además el diagnóstico
de reinicio corregido por separado en `034:RF-20`: una carga de sesión ausente
no equivale a un cambio de selección. No se rebajan las guardas para acomodar
una fixture ni se convierten estos dobles en aceptación nativa o comercial.

La [maestría de Eriksson y Mosaddegh](https://fileadmin.cs.lth.se/cs/Personal/Lars_Bendix/Teaching/Lund/Theses/EM21/EM21-report.pdf),
el [doctorado de Strandberg](https://www.es.mdu.se/publications/6347-Automated_System_Level_Software_Testing_of_Industrial_Networked_Embedded_Systems)
y el [artículo indexado de Shahin, Ali Babar y Zhu](https://research.monash.edu/en/publications/continuous-integration-delivery-and-deployment-a-systematic-revie/)
sustentan feedback reproducible y contexto explícito. Son fuentes primarias
consultadas en la web y no certifican las afirmaciones eléctricas del programa.
