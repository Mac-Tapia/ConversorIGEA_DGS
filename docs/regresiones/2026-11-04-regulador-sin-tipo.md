# Todas las variantes con regulador fallaban por un tipo que no existía

## Síntoma
«No está el tipo VR32_10kV_50A (TypVoltreg) en la biblioteca del proyecto CSG_Biblioteca_tipos»; un alimentador largo solo tenía esas variantes.

## Causa
Comprobada: `crear_tipos_regulador` existía, pero el flujo de la web nunca lo llamaba, y el regulador iba al final, detrás del tope de variantes.

## Comprobación permanente
Los tipos se crean antes de evaluar; en línea larga el regulador entra antes del tope, también con la doble terna, y las obras se combinan de hasta cuatro (042:RF-34, RF-35, RF-38).

## Prueba
- `tests/test_obras_pf_guion_042.py::test_el_tipo_de_regulador_se_crea_activando_la_biblioteca`
- `tests/test_escalera_optima.py::test_en_linea_larga_el_regulador_no_queda_fuera_del_tope`
- `tests/test_escalera_optima.py::test_las_obras_se_integran_de_tres_y_de_cuatro_sin_repetir`
