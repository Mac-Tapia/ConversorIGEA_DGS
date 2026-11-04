# Las obras reforzaban una rama que no era la de la carga

## Síntoma
Con la sección mayor en doble terna, una carga seguía a 0,855 p.u.: reforzar 4,4 km casi no cambiaba nada, y la carga pedía 58 A en una rama que llevaba 36 A.

## Causa
Causa sin confirmar del todo: en la lectura ningún alimentador tenía camino eléctrico, porque se buscaba solo por líneas y se cortaba en cada maniobra. Sin camino, las obras se colocaban por cercanía GPS. Lo confirmará una evaluación en DIgSILENT con el camino real.

## Comprobación permanente
El camino pasa por acopladores cerrados y equipos en serie, y solo sus líneas llevan obra (042:RF-44); si aun así no hay camino, se dice (042:RF-45).

## Prueba
- `tests/test_escalera_optima.py::test_el_camino_pasa_por_los_acopladores_y_solo_las_lineas_llevan_obra`
- `tests/test_obras_pf_guion_042.py::test_los_puentes_de_la_red`
