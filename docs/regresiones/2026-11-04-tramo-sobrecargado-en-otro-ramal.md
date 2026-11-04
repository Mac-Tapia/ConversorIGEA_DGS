# Ninguna variante cumplía aunque las tensiones ya estaban bien

## Síntoma
Con la sección mayor en doble terna las barras quedaban a 0,97 p.u. y aun así «máxima no cumple», en todas las variantes.

## Causa
Causa sin confirmar del todo: un tramo de otro ramal se midió al 141 % en DIgSILENT y el límite de planeamiento es del 80 %; cada variante reforzaba un solo camino, el de una carga, de modo que ese tramo no entraba en ninguna. Lo confirmará una evaluación en DIgSILENT con este refuerzo.

## Comprobación permanente
Cada variante añade las ternas que necesita cualquier tramo sobrecargado del alimentador, y se prueba también ese refuerzo solo (042:RF-43).

## Prueba
- `tests/test_escalera_optima.py::test_cada_variante_refuerza_los_tramos_sobrecargados_de_cualquier_ramal`
