# Una función con el nombre de otra rompía las obras de migración

## Síntoma
`no se pudo crear la obra: _barras_de() takes 1 positional argument but 2 were given`. Toda obra de migración fallaba en `tools/obras_pf.py`; lo vio la
suite completa al integrar la 042 (2026-11-04). Las pruebas de la propia rama no pasaban por ahí.

## Causa
La georreferenciación de las obras (042:RF-36) añadió otro `_barras_de(objeto)` más abajo en el mismo guion. En Python gana la última definición, y Ruff
no lo avisa porque la primera se usa antes dentro de una función.

## Comprobación permanente
Ningún módulo de `src/` ni de `tools/` define dos veces la misma función o clase en su nivel superior.

## Prueba
- `tests/test_nombres_definidos.py::test_ninguna_funcion_definida_dos_veces`
