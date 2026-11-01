# Plan — Spec 052

1. `tools/obras_pf.py --oraculo-datos`: en «Con proyecto», con todas las cargas nuevas activas,
   el grafo de `digital_twin_snapshot_pf.grafo`, la troncal y las barras de media de cada
   alimentador (lo de `--escalera-datos`) y, por variación de carga nueva (índice de la 040),
   el nodo del grafo de su carga y su P y Q. Una sola lectura por trabajo.
2. `src/igea_dgs/optimizacion_oraculo.py`: copia del grafo con una variante aplicada (banco,
   terna, sección, regulador), demanda con k cargas, flujo con `digital_twin.flujo`, medidas en
   la forma de `medida_para_criterio` (tensión por barra y cargabilidad por rama) y el criterio
   `escalera_optima.cumple`; búsqueda de k con `set_nueva.cuantas_caben` y elección con
   `escalera_optima.elegir`.
3. `web/services.optimizar_con_proyecto`: el oráculo busca y elige; DIgSILENT confirma con
   `obras_escalera` (la elegida con k y las más cercanas con k + 1, en el orden del oráculo y con
   «basta una»); discrepancias y tiempos en el informe; si el oráculo no puede, la búsqueda de la
   042 en DIgSILENT.
4. Pruebas con el doble de DIgSILENT y con redes sintéticas cuyo flujo se conoce; después, NA203
   + NA205 por la web.
