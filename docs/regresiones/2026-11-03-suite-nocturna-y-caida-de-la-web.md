# La suite nocturna quedó «empezada» sin resultado, y la web cayó sin causa conocida

## Síntoma
`suite.jsonl` se quedó en «empezada» sin ningún resultado, y la web no estaba abierta por la mañana. Nadie pudo decir por qué, ni que esa noche no se había probado nada.

## Causa
La suite corría en un hilo de la web y como su proceso hijo: moría con ella, y la fila «empezada» se escribía antes. De la caída concreta, causa sin confirmar. Se demostraron dos vías por las que la web se cierra sin dejar rastro en ella:

1. Un lanzador de otra carpeta (otro worktree) ve otra huella y, sin trabajos en curso, cierra la web y ocupa su puerto; la suite no cuenta como trabajo.
2. Un lanzador termina con `taskkill /T /F` a un servidor que tarda 8 s en contestar, con todo su árbol, suite incluida.

`pf_arnes.pedir_cierre_si_ocioso` no es una de ellas: cierra el servidor de DIgSILENT, no la web.

## Comprobación permanente
`tools/suite_por_tandas.py` corre por tandas, separada del árbol de la web, y registra siempre su resultado o «interrumpida»; la vigilancia cierra y avisa de la que quedó «empezada» con su proceso muerto. Un lanzador de otra carpeta deja la web y usa el puerto siguiente; al que no responde se le da un minuto. `web/cierre.py` registra cada arranque y cierre con su motivo, y un arranque sin su cierre se avisa: la próxima caída tendrá dato. La suite real es la T14 de la spec 081.

## Prueba
- `tests/test_suite_por_tandas.py::test_la_que_quedo_empezada_se_cierra_y_avisa`
- `tests/test_suite_por_tandas.py::test_separar_sale_del_arbol_de_la_web`
- `tests/test_suite_por_tandas.py::test_si_revienta_queda_interrumpida`
- `tests/test_cierre_web.py::test_caida_sin_cierre_se_avisa_al_arrancar`
- `tests/test_cierre_web.py::test_un_lanzador_de_otra_carpeta_no_cierra_la_web`
- `tests/test_cierre_web.py::test_no_se_termina_sin_dar_un_plazo`
