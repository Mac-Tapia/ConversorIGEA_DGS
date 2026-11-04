# La columna de COyM de los formatos F10 a F12 salía vacía aunque el perfil diera el dato

## Síntoma
Hallado en la revisión de la spec 076 (fila `formatos_pide-012`), no en una entrega: F10, F11 y F12 dejaban `COyM US$` en blanco con el motivo «el perfil no da el costo de operación y mantenimiento», y el costo anual quedaba en la anualidad con el aviso «costo anual sin COyM o sin pérdidas», también con `escalera.coym_pct_anual` en el perfil.

## Causa
Comprobada en el código: `propuesta_pide` llamaba a `evaluar` con `coym_anual=None`, y `filas_de_obras` y `_por_grupo` escribían `None` fijo en esa columna. El motivo del hueco culpaba al perfil, pero ningún valor del perfil podía llenarla. La escalera sí leía ese mismo dato (025:RF-53).

## Comprobación permanente
La propuesta recibe el porcentaje del perfil y calcula el COyM de cada obra con inversión conocida; las tres columnas leen ese valor de la evaluación, no un valor fijo. Sin el dato o sin inversión queda vacío y con su motivo, nunca en 0, y un grupo con alguna obra sin COyM no suma a medias (072:RF-22).

## Prueba
- `tests/test_formatos_pide.py::test_el_coym_del_perfil_llega_a_f10_f11_y_f12`
- `tests/test_formatos_pide.py::test_sin_coym_del_perfil_queda_el_hueco_nombrado`
- `tests/test_formatos_pide.py::test_el_coym_de_un_grupo_no_se_suma_a_medias`
