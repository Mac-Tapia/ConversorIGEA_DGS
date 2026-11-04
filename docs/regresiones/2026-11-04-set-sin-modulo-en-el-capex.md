# La SET no se proponía por no tener libro CAPEX o módulo que cubriera la potencia

## Síntoma
«La SET nueva se elige entre los módulos PIT del libro CAPEX: indique el libro (042:RF-7).» y las cargas quedaban sin obra.

## Causa
Comprobada: faltar el libro o el módulo terminaba en un aviso sin obra.

## Comprobación permanente
Sin libro o sin módulo, la SET se dimensiona con el menor transformador normalizado que cubre el diseño, con el costo por MVA del módulo más parecido, marcada por confirmar (042:RF-33).

## Prueba
- `tests/test_set_nueva.py::test_sin_modulo_que_cubra_la_set_se_deduce`
- `tests/test_set_nueva_web.py::test_sin_libro_capex_la_set_se_dimensiona_igual`
