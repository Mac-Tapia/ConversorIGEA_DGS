# La sección mayor de la empresa nunca se probó porque no había tipo en la red

## Síntoma
El operador pidió el conductor de 240 mm² en doble terna y la escalera no lo ofrecía.

## Causa
Comprobada: la escalera solo ofrecía tipos ya presentes en las bibliotecas, y en esa zona no había ningún tramo de esa sección. Crear el tipo en el proyecto biblioteca sin activarlo devuelve `None`.

## Comprobación permanente
Los conductores normalizados que faltan se crean desde su ficha, a la tensión leída de cada alimentador, en la biblioteca del proyecto activo; sección y terna se combinan sobre el mismo camino (042:RF-30, RF-40).

## Prueba
- `tests/test_escalera_optima.py::test_el_240_sale_de_su_ficha_y_va_en_doble_terna`
- `tests/test_escalera_optima.py::test_otra_empresa_sin_perfil_y_otra_tension_tiene_todas_las_obras`
