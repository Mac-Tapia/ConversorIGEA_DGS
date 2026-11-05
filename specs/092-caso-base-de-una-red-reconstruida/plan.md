# Plan 092 — El «Caso base» de una red reconstruida, con lo que hay en disco

## Dónde

- `src/convertersmartgrid/web/services.py`, `check_powerfactory_source_run`: con `exigir_red_cargada=False` (leer
  un proyecto importado, 018:RF-12) la reconstrucción se valida con `verify_reconstruction_contract` y el hash del
  sidecar; la comparación con la reconstrucción de la sesión solo si la sesión tiene una (RF-1 a RF-3). Con
  `exigir_red_cargada=True` (importar) queda igual (RF-4).

## Decisión

- Validar con el disco y no volver a cargar la red: la red cargada es siempre otra ejecución (la carga crea una
  nueva) y adoptar la del vínculo la invalida (018:RF-15); exigirla no se podía cumplir nunca. Descartado: no
  invalidar la red al adoptar la del vínculo, porque haría creer cargada una red de otra ejecución.

## Pruebas

- `tests/test_powerfactory_binding.py`: un DGS de reconstrucción con su informe en disco se verifica sin red cargada;
  con el informe cambiado, `POWERFACTORY_RECONSTRUCTION_MISMATCH`; importar sigue pidiendo la red.
