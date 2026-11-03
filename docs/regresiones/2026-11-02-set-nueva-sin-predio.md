# Una SET nueva quedó en un punto elegido solo por criterio eléctrico

## Síntoma
Al revisar el plano, la SET nueva quedaba donde no hay predio: «debe quedar en un área libre, ni dentro de la calle ni encima de los alimentadores». Al moverla, las salidas cambiaron de longitud y hubo que repetir los dos flujos.

## Causa
Comprobada en el código: el punto de Weber y el ajuste por tensiones solo miran la electricidad, y acercar la SET a la barra que cae la lleva hacia el trazado de la red.

## Comprobación permanente
Cada punto se aparta de la red y de las calles locales antes de medirlo, con el retiro del perfil, y los dos flujos corren en el punto final. Sin datos de calles queda «sin verificar en plano»; nunca se afirma que el área esté libre. La comprobación en DIgSILENT es la tarea T8 de la spec 084.

## Prueba
- `tests/test_seis_reglas.py::test_el_guion_mide_cada_intento_ya_apartado_y_los_dos_flujos_en_el_final`
- `tests/test_seis_reglas.py::test_sin_calles_el_punto_queda_sin_verificar_en_plano`
- `tests/test_seis_reglas.py::test_nunca_dice_area_libre`
