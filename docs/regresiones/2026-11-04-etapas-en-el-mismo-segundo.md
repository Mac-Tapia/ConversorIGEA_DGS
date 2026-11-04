# Cinco de catorce cargas nuevas no estaban en la red tras aplicarlas

## Síntoma
Las cargas salían aplicadas en el informe, pero sus barras no existían en DIgSILENT.

## Causa
Comprobada: las etapas nuevas caían en el mismo segundo y DIgSILENT no aplica las que comparten fecha cuando parten un tramo.

## Comprobación permanente
Cada etapa nueva toma un segundo propio, el libre más alto antes de la hora del estudio (042:RF-25).

## Prueba
- `tests/test_cargas_pf.py::test_cada_etapa_nueva_tiene_su_segundo_propio`
