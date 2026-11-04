# La escalera midió sin las cargas nuevas y ninguna variante cumplía

## Síntoma
Todas las variantes de dos alimentadores salían «la carga nueva en NODE_T_… queda a ? p.u.», con la red casi descargada; el refuerzo de mayor sección parecía no servir.

## Causa
Causa sin confirmar del todo: 6 de 14 variaciones de cargas estaban desactivadas y nada las volvía a activar; lo más probable es que las dejara así una caída de DIgSILENT a mitad de una evaluación, porque se reponen en un `finally` que entonces no llega a correr.

## Comprobación permanente
Antes de la escalera por alimentador se activan en «Con proyecto» las variaciones de las cargas nuevas de esos alimentadores, y se dice cuáles (042:RF-32).

## Prueba
- `tests/test_informe_factibilidad_un_paso.py::test_la_escalera_repone_antes_las_cargas_apartadas`
- `tests/test_obras_pf_guion_042.py::test_reponer_cargas_activa_solo_las_pedidas`
