# Comparación del harness contra una referencia distinta del activo

## Síntoma

El puente al registro podía activar un candidato después de compararlo contra
otro modelo, aunque el puntero del modelo activo permaneciera igual al sellado.
La referencia evaluada y el activo tenían digests distintos; el informe y la
revalidación de los modelos evaluados seguían siendo internamente coherentes.

## Causa

La guarda comparaba el puntero activo con `activo_esperado`, sin releer su
candidato íntegro ni enlazar su manifiesto y artefactos con la referencia
evaluada. La estabilidad del puntero no prueba identidad del comparador.

## Comprobación permanente

`evaluacion_harness.integracion` relee el detalle íntegro del activo y exige que
su digest, configuración y mapa de artefactos coincidan con la referencia
sellada, además de su aprobación y recarga. Lo comprueba al preparar la etapa,
antes de ejecutarla y antes de registrar o activar el candidato. Un activo
corrupto, distinto o sustituido impide continuar sin reescribirlo.

Sin activo acreditado se conserva un diagnóstico rechazado con motivo explícito;
el bootstrap necesita otro protocolo y no habilita promoción por equivalencia
supuesta. La aplicación mantiene la admisión de un escritor por slot y el
coordinador conserva el control del recurso declarado. Estas pruebas de contrato
usan solo archivos sintéticos y registros temporales; no acreditan mejora
científica ni aceptación eléctrica.

## Prueba

Casos de la clase IntegracionTest:

- `tests/test_harness_integracion.py::test_referencia_ajena_al_activo_no_registra_ni_activa`
- `tests/test_harness_integracion.py::test_etapa_con_referencia_ajena_rechaza_antes_del_proveedor`
- `tests/test_harness_integracion.py::test_bootstrap_sin_activo_conserva_diagnostico_sin_promocion`
- `tests/test_harness_integracion.py::test_activacion_temporal_exige_dominio_recarga_e_identidad_y_se_relee`
- `tests/test_harness_integracion.py::test_artefacto_activo_corrupto_impide_registro`
- `tests/test_harness_integracion.py::test_activo_cambia_tras_crear_etapa_no_invoca_proveedor`
- `tests/test_harness_integracion.py::test_relectura_del_activo_antes_de_activar_detecta_bytes_alterados`
- `tests/test_harness_integracion.py::test_etapa_preserva_declaracion_de_recurso_sellada_sin_adquirir_gpu`
