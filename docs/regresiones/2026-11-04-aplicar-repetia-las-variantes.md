# Aplicar la obra elegida volvía a medir todas las variantes durante media hora por alimentador

## Síntoma
Tras evaluar, el paso de aplicar tardaba 32 min por alimentador.

## Causa
Comprobada: la aplicación repetía la evaluación completa con sus 200 sorteos.

## Comprobación permanente
Al aplicar solo se construye la obra que eligió su evaluación, y nada en el que ya cumple (042:RF-29).

## Prueba
- `tests/test_informe_factibilidad_un_paso.py::test_la_escalera_va_por_alimentador`
