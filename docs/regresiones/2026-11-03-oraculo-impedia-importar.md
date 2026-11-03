# El oráculo o una carpeta mal escrita impedían importar

## Síntoma
Un alimentador que el oráculo no daba por bueno, o sin pandapower instalado, salía «no se importó». Con una carpeta mal escrita en el perfil, la web no lanzaba nada.

## Causa
El control previo era una puerta (057:RF-6, 065:RF-6) y la carpeta se validaba antes de todo (005:RF-4). Decisión del usuario: nada debe bloquear, salvo la red vacía.

## Comprobación permanente
`pandapower_preflight` deja los motivos en `no_convergen`, que solo avisa, y para únicamente con `red_vacia`. Tras importar, el estado lo da el flujo de DIgSILENT (spec 078). `decidir_carpeta` usa el nombre neutro y lo avisa.

## Prueba
- `tests/test_oraculo_corrige.py::test_la_importacion_sigue_si_el_oraculo_no_converge`
- `tests/test_preflight_contract.py::test_red_vacia_y_copia_sin_fijar_no_se_importan`
- `tests/test_carpeta_pf.py::test_web_carpeta_invalida_usa_la_neutra_y_lo_avisa`
- `tests/test_carpeta_por_empresa.py::test_carpeta_mal_escrita_no_da_error`
