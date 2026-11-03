# El grafo cambió de física sin cambiar de versión

## Síntoma
Un alimentador real veía al 131 % un transformador que DIgSILENT medía al 65 %. La spec 074 corrigió el grafo para contar `ntnum`, las unidades en paralelo, pero el grafo siguió siendo la versión 2: los episodios con la física vieja y los de la nueva entraban juntos en el entrenamiento, sin forma de separarlos.

Al revisarlo aparecieron otros huecos del mismo tipo:

- En la red `csg`, el ángulo de la fuente no estaba impuesto y podía flotar.
- Los bancos se sumaban a la carga como potencia constante.
- Una central no entraba en el grafo.
- Una barra a 0 p.u. contaba como medida.

## Causa
La versión se comprobaba en `muestra_de_episodio`, pero nada obligaba a subirla al cambiar el significado del grafo. Lo que quedaba fuera, un regulador o un transformador de tres devanados, no se declaraba en ningún sitio. Un episodio excluido se descartaba sin decir por qué.

## Comprobación permanente
- `VERSION_GRAFO = 3`. El grafo de esa versión declara su alcance físico (`validar_alcance_fisico`), y lo no representado se rechaza con su motivo.
- Un episodio con un grafo anterior se conserva intacto y no enseña; `entrenar` cuenta cuántos excluye y por qué.
- Un modelo guarda con qué versión de grafo aprendió (`dominio.version_grafo`). Si no lo dice o es otra versión, queda fuera de dominio y decide la física.
- La red impone magnitud y ángulo en cada fuente, y `imponer_fronteras` corrige la predicción con lo que es dato.
- Una barra sin fuente no enseña 0 p.u.; una tensión que el grafo no explica se cuenta en `etiquetas_sin_fuente`.

## Prueba
- `tests/test_gemelo_contratos_v2.py::test_un_episodio_viejo_no_se_mezcla_en_silencio`
- `tests/test_gemelo_contratos_v2.py::test_v1_lectura_no_cambia_hash`
- `tests/test_benchmark_pinn.py::test_grafos_viejos_no_entran_en_las_particiones`
- `tests/test_benchmark_pinn.py::test_un_modelo_sin_dominio_o_de_otro_grafo_no_opina`
- `tests/test_pinn_fisica_y_fronteras.py::test_la_red_fija_magnitud_y_angulo_en_la_fuente`
- `tests/test_pinn_fisica_y_fronteras.py::test_isla_desenergizada_no_recibe_gold_cero`
- `tests/test_pinn_fisica_y_fronteras.py::test_fisica_incompleta_bloquea`
