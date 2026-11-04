# Otra empresa, con un perfil incompleto, no habría podido proponer ninguna obra

## Síntoma
«el perfil de empresa no da estudios.tension_min_pu…», «Sin máxima ni medidor de su calibración…», «sin tasa de crecimiento…»: el trabajo terminaba en error, sin obra.

## Causa
Comprobada al revisar el flujo: cada dato técnico que faltaba paraba todo el análisis, y bancos y tipos solo existían para las tensiones de una empresa.

## Comprobación permanente
Lo técnico que falta se toma de referencia y se dice como supuesto, sin pisar lo de la empresa; se crean tipos a la tensión de cada alimentador; sin tasa ni medición se evalúa igual (042:RF-39 a RF-42).

## Prueba
- `tests/test_escalera_optima.py::test_otra_empresa_sin_perfil_y_otra_tension_tiene_todas_las_obras`
- `tests/test_set_nueva.py::test_sin_tasa_de_crecimiento_la_set_se_disena_igual`
- `tests/test_escalera_optima.py::test_sin_medicion_las_obras_se_evaluan_en_la_maxima`
