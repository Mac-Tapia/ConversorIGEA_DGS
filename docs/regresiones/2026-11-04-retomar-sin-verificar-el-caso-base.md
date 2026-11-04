# Al retomar una corrida no se verificaba el «Caso base»

## Síntoma
`tools/sistema_web.py` verificaba el «Caso base» solo justo después de importar. Al retomar un proyecto ya importado, y en la vuelta de `--reconstruir`, que importa de nuevo y entra como si retomara, no se llamaba a la verificación: reproducido con la web falsa. Sin ella, `demanda/ajuste/plan` rechaza un alimentador sin verificar o deja fuera a los de un sistema.

## Causa
La llamada estaba dentro de las dos ramas que importan, y ninguna de ellas corre al retomar.

## Comprobación permanente
Un solo paso, por donde pasan importar, retomar y la vuelta de `--reconstruir`, antes de los libros y del plan. Lo que se va a reconstruir no se verifica: se verifica lo nuevo en su vuelta. Si la web rechaza la verificación se dice y se sigue (015:RF-13).

## Prueba
- `tests/test_sistema_web.py::test_al_retomar_tambien_verifica_el_caso_base`
- `tests/test_sistema_web.py::test_al_retomar_la_verificacion_que_no_se_puede_pedir_no_para`
- `tests/test_sistema_web.py::test_importar_verifica_una_sola_vez`
- `tests/test_sistema_web.py::test_reconstruir_verifica_el_proyecto_nuevo`
